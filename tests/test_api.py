"""
Integration tests for the REST API: health, workspaces, documents,
transformations and request validation.
"""

import uuid
from typing import Any, Dict

import httpx
import pytest

pytestmark = pytest.mark.integration

NONEXISTENT_ID = "00000000-0000-0000-0000-000000000000"


class TestHealthEndpoints:
    """/api/health reports each dependency (the /api/health/* sub-endpoints were folded into it)."""

    async def test_basic_health_check(self, api_client: httpx.AsyncClient):
        response = await api_client.get("/api/health")
        assert response.status_code == 200

        health_data = response.json()
        assert health_data["status"] == "healthy"
        assert "timestamp" in health_data

    @pytest.mark.database
    async def test_database_health_check(self, api_client: httpx.AsyncClient):
        response = await api_client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["checks"]["database"]["status"] == "healthy"

    @pytest.mark.redis
    async def test_redis_health_check(self, api_client: httpx.AsyncClient):
        response = await api_client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["checks"]["redis"]["status"] == "healthy"


class TestWorkspaceEndpoints:
    """Test workspace management endpoints"""

    async def test_create_workspace(self, authenticated_client: httpx.AsyncClient):
        slug = f"api-test-{uuid.uuid4().hex[:8]}"
        workspace_data = {
            "name": "Test Workspace API",
            "slug": slug,
            "description": "Created by API integration tests",
            "plan": "free",
        }

        response = await authenticated_client.post("/api/workspaces", json=workspace_data)
        assert response.status_code == 201, response.text

        workspace = response.json()
        assert workspace["name"] == workspace_data["name"]
        assert workspace["slug"] == slug
        assert workspace["description"] == workspace_data["description"]
        assert workspace["plan"] == workspace_data["plan"]
        assert workspace["user_role"] == "owner"

        # Slugs are unique
        duplicate = await authenticated_client.post("/api/workspaces", json=workspace_data)
        assert duplicate.status_code == 400
        assert "already taken" in duplicate.json()["detail"]

    async def test_create_workspace_requires_valid_slug(self, authenticated_client: httpx.AsyncClient):
        response = await authenticated_client.post(
            "/api/workspaces", json={"name": "Bad slug", "slug": "Not A Slug!"}
        )
        assert response.status_code == 422

    async def test_list_workspaces(self, authenticated_client: httpx.AsyncClient, auth_user: dict):
        """Every registered user gets a default workspace"""
        response = await authenticated_client.get("/api/workspaces")
        assert response.status_code == 200

        workspaces = response.json()["workspaces"]
        assert [w["id"] for w in workspaces] == [auth_user["workspace_id"]]
        for field in ("id", "name", "slug", "plan"):
            assert field in workspaces[0]

    async def test_get_workspace_details(self, authenticated_client: httpx.AsyncClient, auth_user: dict):
        workspace_id = auth_user["workspace_id"]

        response = await authenticated_client.get(f"/api/workspaces/{workspace_id}")
        assert response.status_code == 200

        workspace = response.json()
        assert workspace["id"] == workspace_id
        assert workspace["user_role"] in ("owner", "admin", "member")

    async def test_workspace_isolation(self, api_client: httpx.AsyncClient, user_factory):
        """Unauthenticated callers are rejected and users cannot read another tenant's workspace"""
        assert (await api_client.get("/api/workspaces")).status_code == 401

        alice = await user_factory()
        bob = await user_factory()
        response = await api_client.get(
            f"/api/workspaces/{bob['workspace_id']}", headers=alice["headers"]
        )
        assert response.status_code == 403


class TestDocumentEndpoints:
    """Test document management endpoints"""

    async def test_create_document(self, authenticated_client: httpx.AsyncClient, auth_user: dict):
        content = (
            "This is a test document created by API integration tests. "
            "It contains sample content for testing various transformations."
        )
        response = await authenticated_client.post(
            "/api/documents/text",
            data={"title": "API Test Document", "content": content, "description": "from text"},
        )
        assert response.status_code == 201, response.text

        document = response.json()
        assert document["title"] == "API Test Document"
        assert document["description"] == "from text"
        assert document["content_type"] == "text/plain"
        assert document["status"] == "COMPLETED"
        assert document["user_id"] == auth_user["user_id"]
        assert "id" in document
        assert "created_at" in document

    async def test_upload_document(self, authenticated_client: httpx.AsyncClient):
        body = b"Uploaded notes.\nThey have a few lines of plain text.\n"
        response = await authenticated_client.post(
            "/api/documents/upload",
            data={"title": "Uploaded"},
            files={"file": ("notes.txt", body, "text/plain")},
        )
        assert response.status_code == 201, response.text
        document = response.json()
        assert document["original_filename"] == "notes.txt"
        assert document["status"] == "COMPLETED"

        content = await authenticated_client.get(f"/api/documents/{document['id']}/content")
        assert content.status_code == 200
        assert "plain text" in content.json()["extracted_text"]

    async def test_upload_rejects_unsupported_type(self, authenticated_client: httpx.AsyncClient):
        response = await authenticated_client.post(
            "/api/documents/upload",
            data={"title": "Nope"},
            files={"file": ("tool.exe", b"MZ\x90\x00", "application/x-msdownload")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    async def test_list_documents(self, authenticated_client: httpx.AsyncClient, test_document: Dict[str, Any]):
        response = await authenticated_client.get("/api/documents")
        assert response.status_code == 200

        documents_data = response.json()
        assert documents_data["count"] == len(documents_data["documents"]) == 1
        document = documents_data["documents"][0]
        assert document["id"] == test_document["id"]
        assert document["title"] == test_document["title"]
        assert "created_at" in document

    async def test_get_document_details(self, authenticated_client: httpx.AsyncClient, test_document: Dict[str, Any]):
        document_id = test_document["id"]

        response = await authenticated_client.get(f"/api/documents/{document_id}")
        assert response.status_code == 200
        document = response.json()
        assert document["id"] == document_id
        assert document["title"] == test_document["title"]

        content = await authenticated_client.get(f"/api/documents/{document_id}/content")
        assert content.status_code == 200
        assert content.json()["extracted_text"] == test_document["content"]

    async def test_delete_document(self, authenticated_client: httpx.AsyncClient, test_document: Dict[str, Any]):
        document_id = test_document["id"]

        delete_response = await authenticated_client.delete(f"/api/documents/{document_id}")
        assert delete_response.status_code == 204

        get_response = await authenticated_client.get(f"/api/documents/{document_id}")
        assert get_response.status_code == 404
        listed = (await authenticated_client.get("/api/documents")).json()
        assert document_id not in [d["id"] for d in listed["documents"]]


class TestTransformationEndpoints:
    """Test transformation processing endpoints"""

    async def test_create_transformation(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: Dict[str, Any],
        sample_transformation_data: Dict[str, Any],
    ):
        transformation_data = {**sample_transformation_data, "document_id": test_document["id"]}

        response = await authenticated_client.post("/api/transformations", json=transformation_data)
        assert response.status_code == 201, response.text

        transformation = response.json()
        assert transformation["document_id"] == test_document["id"]
        assert transformation["transformation_type"] == transformation_data["transformation_type"]
        assert transformation["parameters"] == transformation_data["parameters"]
        # Queued for the Celery worker rather than run inline
        assert transformation["status"] in ("PENDING", "PROCESSING")
        assert transformation["task_id"]

    async def test_list_transformations(self, authenticated_client: httpx.AsyncClient, test_document, sample_transformation_data):
        response = await authenticated_client.get("/api/transformations")
        assert response.status_code == 200
        assert response.json() == {"transformations": [], "count": 0}  # fresh user

        created = await authenticated_client.post(
            "/api/transformations", json={**sample_transformation_data, "document_id": test_document["id"]}
        )
        assert created.status_code == 201

        listed = (await authenticated_client.get("/api/transformations")).json()
        assert listed["count"] == 1
        transformation = listed["transformations"][0]
        assert transformation["id"] == created.json()["id"]
        for field in ("document_id", "transformation_type", "status"):
            assert field in transformation

    async def test_get_transformation_status(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: Dict[str, Any],
        sample_transformation_data: Dict[str, Any],
        wait_for_transformation,
    ):
        """Status is read from GET /api/transformations/{id} (the /status sub-endpoint was removed)"""
        create_response = await authenticated_client.post(
            "/api/transformations", json={**sample_transformation_data, "document_id": test_document["id"]}
        )
        assert create_response.status_code == 201
        transformation_id = create_response.json()["id"]

        status_response = await authenticated_client.get(f"/api/transformations/{transformation_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] in ("PENDING", "PROCESSING", "COMPLETED", "FAILED")

        final = await wait_for_transformation(authenticated_client, transformation_id)
        assert final["status"] == "COMPLETED"
        assert final["result"]

    async def test_available_transformation_types(self, authenticated_client: httpx.AsyncClient):
        response = await authenticated_client.get("/api/transformations/types/available")
        assert response.status_code == 200

        data = response.json()
        types = {t["type"] for t in data["transformation_types"]}
        assert types == {"BLOG_POST", "SOCIAL_MEDIA", "EMAIL_SEQUENCE", "NEWSLETTER", "SUMMARY", "CUSTOM"}
        assert data["count"] == len(types)

    async def test_create_transformation_invalid_type(self, authenticated_client: httpx.AsyncClient, test_document):
        response = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": test_document["id"], "transformation_type": "INVALID_TYPE", "parameters": {}},
        )
        assert response.status_code == 422

    async def test_create_transformation_requires_auth(self, api_client: httpx.AsyncClient):
        response = await api_client.post(
            "/api/transformations",
            json={"document_id": NONEXISTENT_ID, "transformation_type": "SUMMARY", "parameters": {}},
        )
        assert response.status_code == 401


class TestAPIValidation:
    """Test API input validation and error handling"""

    async def test_invalid_json_handling(self, authenticated_client: httpx.AsyncClient):
        response = await authenticated_client.post(
            "/api/transformations",
            content='{"invalid": json}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    async def test_missing_required_fields(self, authenticated_client: httpx.AsyncClient):
        response = await authenticated_client.post("/api/documents/text", data={"title": "Test"})
        assert response.status_code == 422
        assert "detail" in response.json()

        response = await authenticated_client.post("/api/transformations", json={"transformation_type": "SUMMARY"})
        assert response.status_code == 422

    async def test_invalid_field_types(self, authenticated_client: httpx.AsyncClient):
        response = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": "not-a-uuid", "transformation_type": "SUMMARY", "parameters": {}},
        )
        assert response.status_code == 422

        response = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": NONEXISTENT_ID, "transformation_type": "SUMMARY", "parameters": "oops"},
        )
        assert response.status_code == 422

    async def test_unauthorized_access(self, api_client: httpx.AsyncClient):
        for endpoint in ["/api/workspaces", "/api/documents", "/api/transformations", "/api/auth/me"]:
            response = await api_client.get(endpoint)
            assert response.status_code == 401, f"{endpoint} should require authentication"

    async def test_nonexistent_resource_access(self, authenticated_client: httpx.AsyncClient):
        for endpoint in [
            f"/api/documents/{NONEXISTENT_ID}",
            f"/api/transformations/{NONEXISTENT_ID}",
        ]:
            response = await authenticated_client.get(endpoint)
            assert response.status_code == 404, f"{endpoint} should return 404"

        # Workspace access is membership-checked before lookup, so any foreign id is 403
        response = await authenticated_client.get(f"/api/workspaces/{NONEXISTENT_ID}")
        assert response.status_code == 403

        response = await authenticated_client.post(
            "/api/transformations",
            json={"document_id": NONEXISTENT_ID, "transformation_type": "SUMMARY", "parameters": {}},
        )
        assert response.status_code == 404
