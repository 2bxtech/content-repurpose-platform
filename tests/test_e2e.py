"""
End-to-end user workflows against the running stack (API + worker + Postgres + Redis).

Also covers the upload -> transform flows formerly in test_integration_comprehensive.py.
"""

import asyncio
import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.e2e

LONG_TEXT = """
Artificial Intelligence is revolutionizing content creation across industries.
From automated writing assistants to sophisticated content optimization tools,
AI is changing how we approach content strategy and production.

Key benefits include faster content generation, improved consistency,
data-driven optimization and personalization at scale. Challenges remain:
maintaining an authentic voice, quality control, and balancing automation
with human creativity.
"""


async def _create_text_document(client, headers, title, content=LONG_TEXT) -> dict:
    r = await client.post("/api/documents/text", data={"title": title, "content": content}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _transform(client, headers, document_id, transformation_type="SUMMARY", parameters=None) -> dict:
    r = await client.post(
        "/api/transformations",
        json={
            "document_id": document_id,
            "transformation_type": transformation_type,
            "parameters": parameters or {},
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestCompleteUserWorkflow:
    """Registration through to transformed content"""

    async def test_new_user_complete_workflow(
        self, api_client: httpx.AsyncClient, wait_for_transformation, jwt_claims
    ):
        suffix = uuid.uuid4().hex[:8]
        user = {"email": f"e2e_{suffix}@example.com", "username": f"e2e_{suffix}", "password": "NewUserPassword123!"}

        # 1. Register and log in
        assert (await api_client.post("/api/auth/register", json=user)).status_code == 201
        login = await api_client.post("/api/auth/token", data={"username": user["email"], "password": user["password"]})
        assert login.status_code == 200
        tokens = login.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # 2. A default workspace is provisioned at sign-up and carried in the token
        workspaces = (await api_client.get("/api/workspaces", headers=headers)).json()["workspaces"]
        assert [w["id"] for w in workspaces] == [jwt_claims(tokens["access_token"])["workspace_id"]]

        # 3. Add content and transform it into two formats
        document = await _create_text_document(api_client, headers, "E2E Test Document")
        created = [
            await _transform(api_client, headers, document["id"], "SUMMARY", {"length": "brief"}),
            await _transform(api_client, headers, document["id"], "BLOG_POST", {"tone": "engaging"}),
        ]

        # 4. Worker finishes both
        for transformation in created:
            final = await wait_for_transformation(api_client, transformation["id"], headers=headers)
            assert final["status"] == "COMPLETED"
            assert final["result"]

        # 5. Library shows everything
        docs = (await api_client.get("/api/documents", headers=headers)).json()
        assert [d["id"] for d in docs["documents"]] == [document["id"]]
        transforms = (await api_client.get("/api/transformations", headers=headers)).json()
        assert {t["id"] for t in transforms["transformations"]} == {t["id"] for t in created}

        # 6. Log out; the refresh token is revoked
        logout = await api_client.post(
            "/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}, headers=headers
        )
        assert logout.status_code == 200
        refresh = await api_client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refresh.status_code == 401

    async def test_complete_upload_transform_workflow(
        self, authenticated_client: httpx.AsyncClient, wait_for_transformation
    ):
        """Upload a file, then transform its extracted text"""
        upload = await authenticated_client.post(
            "/api/documents/upload",
            data={"title": "Comprehensive Test Document", "description": "Upload workflow"},
            files={"file": ("comprehensive_test.md", LONG_TEXT.encode(), "text/markdown")},
        )
        assert upload.status_code == 201, upload.text
        document = upload.json()

        docs = (await authenticated_client.get("/api/documents")).json()
        assert docs["count"] == 1
        assert docs["documents"][0]["id"] == document["id"]

        transformation = await _transform(authenticated_client, {}, document["id"], "BLOG_POST", {"word_count": 800})
        final = await wait_for_transformation(authenticated_client, transformation["id"])
        assert final["status"] == "COMPLETED"
        assert final["transformation_type"] == "BLOG_POST"

    async def test_content_batch_workflow(
        self, authenticated_client: httpx.AsyncClient, wait_for_transformation
    ):
        """Several related documents processed together all complete"""
        started = time.perf_counter()
        documents = [
            await _create_text_document(
                authenticated_client, {}, f"Batch Document {i + 1}",
                f"Document {i + 1} of a series. " + LONG_TEXT,
            )
            for i in range(3)
        ]
        transformations = [
            await _transform(authenticated_client, {}, doc["id"], "SUMMARY", {"length": "medium"})
            for doc in documents
        ]
        assert time.perf_counter() - started < 15.0  # creation doesn't wait on AI calls

        finals = await asyncio.gather(
            *[wait_for_transformation(authenticated_client, t["id"], timeout=90) for t in transformations]
        )
        assert [f["status"] for f in finals] == ["COMPLETED"] * len(documents)
        assert sorted(f["document_id"] for f in finals) == sorted(d["id"] for d in documents)

    async def test_error_recovery_workflow(self, authenticated_client: httpx.AsyncClient, wait_for_transformation):
        # Unknown document
        r = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": "00000000-0000-0000-0000-000000000000", "transformation_type": "SUMMARY", "parameters": {}},
        )
        assert r.status_code == 404

        # Unsupported upload
        r = await authenticated_client.post(
            "/api/documents/upload",
            data={"title": "Invalid File"},
            files={"file": ("invalid.exe", b"Invalid content", "application/x-msdownload")},
        )
        assert r.status_code == 400

        # Unknown transformation type
        document = await _create_text_document(authenticated_client, {}, "Error Recovery Test Document")
        r = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": document["id"], "transformation_type": "INVALID_TYPE", "parameters": {}},
        )
        assert r.status_code == 422

        # After the errors, normal work still succeeds
        transformation = await _transform(authenticated_client, {}, document["id"])
        final = await wait_for_transformation(authenticated_client, transformation["id"])
        assert final["status"] == "COMPLETED"

        health = (await authenticated_client.get("/api/health")).json()
        assert health["status"] == "healthy"


class TestUserJourneyScenarios:
    """Test realistic user journey scenarios"""

    async def test_content_creator_journey(self, authenticated_client: httpx.AsyncClient, wait_for_transformation):
        """Create content, repurpose it into every major format, then iterate on one result"""
        document = await _create_text_document(authenticated_client, {}, "The Future of AI in Content Creation")

        requests = [
            ("SUMMARY", {"length": "short", "style": "paragraph"}),
            ("BLOG_POST", {"tone": "engaging", "target_audience": "business"}),
            ("SOCIAL_MEDIA", {"platform": "linkedin", "hashtags": True}),
            ("EMAIL_SEQUENCE", {"sequence_length": 3}),
        ]
        created = [
            await _transform(authenticated_client, {}, document["id"], t_type, params) for t_type, params in requests
        ]
        assert len({t["id"] for t in created}) == len(requests)

        finals = [await wait_for_transformation(authenticated_client, t["id"]) for t in created]
        assert [(f["transformation_type"], f["status"]) for f in finals] == [
            (t_type, "COMPLETED") for t_type, _ in requests
        ]

        # Iterate: refine the blog post (runs synchronously and returns a new transformation)
        blog = finals[1]
        refined = await authenticated_client.post(
            f"/api/transformations/{blog['id']}/refine", json={"instruction": "Make it shorter."}
        )
        assert refined.status_code == 201, refined.text
        refined_body = refined.json()
        assert refined_body["id"] != blog["id"]
        assert refined_body["document_id"] == document["id"]
        assert refined_body["transformation_type"] == "BLOG_POST"
        assert refined_body["status"] == "COMPLETED"

        library = (await authenticated_client.get("/api/transformations")).json()
        assert library["count"] == len(requests) + 1
