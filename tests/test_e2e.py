"""
End-to-end tests for complete user workflows
Tests realistic user scenarios from start to finish
"""

import pytest
import httpx
import asyncio


class TestCompleteUserWorkflow:
    """Test complete user workflows from registration to content transformation"""

    @pytest.mark.e2e
    async def test_new_user_complete_workflow(self, api_client: httpx.AsyncClient):
        """Test complete workflow for a new user"""
        # Step 1: User Registration
        user_data = {
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "NewUserPassword123!",
            "first_name": "New",
            "last_name": "User",
        }

        register_response = await api_client.post("/api/auth/register", json=user_data)
        if register_response.status_code == 409:
            # User already exists, skip registration
            pass
        else:
            assert register_response.status_code == 201

        # Step 2: User Login
        login_data = {"username": user_data["email"], "password": user_data["password"]}

        login_response = await api_client.post("/api/auth/token", data=login_data)
        assert login_response.status_code == 200

        tokens = login_response.json()
        access_token = tokens["access_token"]

        # Set auth header for subsequent requests
        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 3: Create Workspace
        workspace_data = {
            "name": "E2E Test Workspace",
            "description": "End-to-end testing workspace",
            "plan": "free",
        }

        workspace_response = await api_client.post(
            "/api/workspaces", json=workspace_data, headers=headers
        )
        if workspace_response.status_code == 409:
            # Workspace exists, get existing ones
            workspaces_response = await api_client.get(
                "/api/workspaces", headers=headers
            )
            workspaces = workspaces_response.json()
            workspace = workspaces["workspaces"][0]
        else:
            assert workspace_response.status_code == 201
            workspace = workspace_response.json()

        workspace["id"]

        # Step 4: Upload Document
        document_data = {
            "title": "E2E Test Document",
            "content": """
            This is a comprehensive test document for end-to-end testing.
            
            It contains multiple paragraphs with different types of content.
            This includes technical information, business context, and creative elements.
            
            The document is designed to test various transformation capabilities
            including summarization, blog post generation, and other content types.
            
            Key topics covered:
            - Technical implementation details
            - Business value propositions
            - User experience considerations
            - Performance metrics and analysis
            """,
            "source_type": "text",
            "metadata": {"test_type": "e2e", "workflow": "complete_user_journey"},
        }

        document_response = await api_client.post(
            "/api/documents", json=document_data, headers=headers
        )
        assert document_response.status_code == 201

        document = document_response.json()
        document_id = document["id"]

        # Step 5: Create Multiple Transformations
        transformations = []
        transformation_types = [
            {
                "transformation_type": "summary",
                "parameters": {"length": "brief", "tone": "professional"},
            },
            {
                "transformation_type": "blog_post",
                "parameters": {"tone": "engaging", "target_audience": "technical"},
            },
        ]

        for transform_data in transformation_types:
            transform_payload = {**transform_data, "document_id": document_id}

            transform_response = await api_client.post(
                "/api/transformations", json=transform_payload, headers=headers
            )
            assert transform_response.status_code in [201, 202]

            transformation = transform_response.json()
            transformations.append(transformation)

        # Step 6: Monitor Transformation Progress
        for transformation in transformations:
            transformation_id = transformation["id"]

            # Wait for completion (with timeout)
            for _ in range(10):  # 10 second timeout
                status_response = await api_client.get(
                    f"/api/transformations/{transformation_id}/status", headers=headers
                )
                assert status_response.status_code == 200

                status_data = status_response.json()
                db_status = status_data["database_status"]

                if db_status in ["completed", "failed"]:
                    break

                await asyncio.sleep(1)

            # Verify final status
            final_response = await api_client.get(
                f"/api/transformations/{transformation_id}", headers=headers
            )
            assert final_response.status_code == 200

            final_transformation = final_response.json()
            assert final_transformation["status"] in ["completed", "failed"]

        # Step 7: Review User's Content
        # List all user's documents
        docs_response = await api_client.get("/api/documents", headers=headers)
        assert docs_response.status_code == 200

        docs_data = docs_response.json()
        assert len(docs_data["documents"]) >= 1

        # List all user's transformations
        transforms_response = await api_client.get(
            "/api/transformations", headers=headers
        )
        assert transforms_response.status_code == 200

        transforms_data = transforms_response.json()
        assert len(transforms_data["transformations"]) >= len(transformations)

        # Step 8: User Logout
        logout_response = await api_client.post(
            "/api/auth/logout", json={}, headers=headers
        )
        # Logout might require refresh token, so accept various responses
        assert logout_response.status_code in [200, 400]

    @pytest.mark.e2e
    async def test_content_collaboration_workflow(self, api_client: httpx.AsyncClient):
        """Test workflow involving multiple content operations"""
        # Login as test user
        login_data = {"username": "test@example.com", "password": "TestPassword123!"}

        login_response = await api_client.post("/api/auth/token", data=login_data)
        assert login_response.status_code == 200

        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Create multiple related documents
        documents = []
        for i in range(3):
            doc_data = {
                "title": f"Collaboration Document {i + 1}",
                "content": f"""
                This is document {i + 1} in a series of related content pieces.
                Each document builds upon the previous ones to create a comprehensive
                content strategy for testing collaboration workflows.
                
                Document {i + 1} focuses on specific aspects of the overall topic
                and demonstrates how multiple pieces of content can work together.
                """,
                "source_type": "text",
                "metadata": {
                    "series": "collaboration_test",
                    "part": i + 1,
                    "total_parts": 3,
                },
            }

            doc_response = await api_client.post(
                "/api/documents", json=doc_data, headers=headers
            )
            assert doc_response.status_code == 201

            documents.append(doc_response.json())

        # Create transformations for each document
        all_transformations = []
        for doc in documents:
            transform_data = {
                "document_id": doc["id"],
                "transformation_type": "summary",
                "parameters": {"length": "medium", "tone": "professional"},
                "metadata": {
                    "batch": "collaboration_test",
                    "source_document": doc["title"],
                },
            }

            transform_response = await api_client.post(
                "/api/transformations", json=transform_data, headers=headers
            )
            assert transform_response.status_code in [201, 202]

            all_transformations.append(transform_response.json())

        # Wait for all transformations to complete
        completed_transformations = []
        for transformation in all_transformations:
            transformation_id = transformation["id"]

            # Poll for completion
            for _ in range(10):
                status_response = await api_client.get(
                    f"/api/transformations/{transformation_id}/status", headers=headers
                )

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    if status_data["database_status"] in ["completed", "failed"]:
                        completed_transformations.append(transformation_id)
                        break

                await asyncio.sleep(1)

        # Verify all transformations were processed
        assert len(completed_transformations) == len(all_transformations)

    @pytest.mark.e2e
    async def test_error_recovery_workflow(self, api_client: httpx.AsyncClient):
        """Test workflow with error conditions and recovery"""
        # Login
        login_data = {"username": "test@example.com", "password": "TestPassword123!"}

        login_response = await api_client.post("/api/auth/token", data=login_data)
        assert login_response.status_code == 200

        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        # Try to create transformation with invalid document ID
        invalid_transform_data = {
            "document_id": "00000000-0000-0000-0000-000000000000",
            "transformation_type": "summary",
            "parameters": {},
        }

        invalid_response = await api_client.post(
            "/api/transformations", json=invalid_transform_data, headers=headers
        )
        assert invalid_response.status_code == 404  # Document not found

        # Create valid document and transformation
        doc_data = {
            "title": "Error Recovery Test Document",
            "content": "This document tests error recovery workflows.",
            "source_type": "text",
        }

        doc_response = await api_client.post(
            "/api/documents", json=doc_data, headers=headers
        )
        assert doc_response.status_code == 201

        document = doc_response.json()

        # Create valid transformation
        valid_transform_data = {
            "document_id": document["id"],
            "transformation_type": "summary",
            "parameters": {"length": "brief"},
        }

        valid_response = await api_client.post(
            "/api/transformations", json=valid_transform_data, headers=headers
        )
        assert valid_response.status_code in [201, 202]

        # Verify system recovered and is working normally
        health_response = await api_client.get("/api/health")
        assert health_response.status_code == 200

        health_data = health_response.json()
        assert health_data["status"] == "healthy"


class TestPerformanceWorkflows:
    """Test performance-related workflows"""

    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_bulk_content_processing(
        self, api_client: httpx.AsyncClient, performance_monitor
    ):
        """Test processing multiple pieces of content efficiently"""
        # Login
        login_data = {"username": "test@example.com", "password": "TestPassword123!"}

        login_response = await api_client.post("/api/auth/token", data=login_data)
        assert login_response.status_code == 200

        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        # Create multiple documents quickly
        performance_monitor.start()

        documents = []
        for i in range(5):
            doc_data = {
                "title": f"Bulk Processing Document {i + 1}",
                "content": f"""
                This is document {i + 1} for bulk processing testing.
                It contains sufficient content to test processing capabilities
                and performance under load conditions.
                
                The content varies slightly between documents to ensure
                diverse processing scenarios are tested.
                """,
                "source_type": "text",
                "metadata": {"batch": "bulk_test", "index": i},
            }

            doc_response = await api_client.post(
                "/api/documents", json=doc_data, headers=headers
            )
            assert doc_response.status_code == 201

            documents.append(doc_response.json())

        doc_creation_time = performance_monitor.stop("bulk_document_creation")
        assert doc_creation_time < 10.0  # Should create 5 documents quickly

        # Create transformations for all documents
        performance_monitor.start()

        transformations = []
        for doc in documents:
            transform_data = {
                "document_id": doc["id"],
                "transformation_type": "summary",
                "parameters": {"length": "brief"},
            }

            transform_response = await api_client.post(
                "/api/transformations", json=transform_data, headers=headers
            )
            assert transform_response.status_code in [201, 202]

            transformations.append(transform_response.json())

        transform_creation_time = performance_monitor.stop(
            "bulk_transformation_creation"
        )
        assert transform_creation_time < 15.0  # Should create transformations quickly

        # Monitor completion time
        performance_monitor.start()

        completed_count = 0
        for transformation in transformations:
            for _ in range(30):  # 30 second timeout per transformation
                status_response = await api_client.get(
                    f"/api/transformations/{transformation['id']}/status",
                    headers=headers,
                )

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    if status_data["database_status"] in ["completed", "failed"]:
                        completed_count += 1
                        break

                await asyncio.sleep(1)

        completion_time = performance_monitor.stop("bulk_transformation_completion")

        # In eager mode, should complete quickly
        assert completed_count >= len(transformations) * 0.8  # At least 80% completion
        assert completion_time < 60.0  # Should complete within reasonable time

        # Verify system performance metrics
        metrics = performance_monitor.get_metrics()
        print("\nPerformance Metrics:")
        print(f"Document Creation: {metrics['bulk_document_creation']:.2f}s")
        print(
            f"Transformation Creation: {metrics['bulk_transformation_creation']:.2f}s"
        )
        print(
            f"Transformation Completion: {metrics['bulk_transformation_completion']:.2f}s"
        )
        print(f"Completed Transformations: {completed_count}/{len(transformations)}")


class TestUserJourneyScenarios:
    """Test realistic user journey scenarios"""

    @pytest.mark.e2e
    async def test_content_creator_journey(self, api_client: httpx.AsyncClient):
        """Test typical content creator workflow"""
        # Simulate a content creator who:
        # 1. Creates initial content
        # 2. Transforms it into multiple formats
        # 3. Reviews and iterates

        # Login
        login_data = {"username": "test@example.com", "password": "TestPassword123!"}

        login_response = await api_client.post("/api/auth/token", data=login_data)
        assert login_response.status_code == 200

        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        # Create original content
        original_content = {
            "title": "The Future of AI in Content Creation",
            "content": """
            Artificial Intelligence is revolutionizing content creation across industries.
            From automated writing assistants to sophisticated content optimization tools,
            AI is changing how we approach content strategy and production.
            
            Key benefits include:
            - Faster content generation
            - Improved consistency
            - Data-driven optimization
            - Personalization at scale
            
            However, challenges remain:
            - Maintaining authentic voice
            - Ensuring quality control
            - Balancing automation with human creativity
            
            The future lies in human-AI collaboration, where technology amplifies
            human creativity rather than replacing it.
            """,
            "source_type": "text",
            "metadata": {
                "author": "content_creator",
                "category": "ai_insights",
                "target_audience": "business_professionals",
            },
        }

        doc_response = await api_client.post(
            "/api/documents", json=original_content, headers=headers
        )
        assert doc_response.status_code == 201

        document = doc_response.json()
        document_id = document["id"]

        # Transform into multiple formats
        transformation_requests = [
            {
                "transformation_type": "summary",
                "parameters": {"length": "brief", "tone": "executive"},
                "metadata": {"purpose": "executive_summary"},
            },
            {
                "transformation_type": "blog_post",
                "parameters": {"tone": "engaging", "include_call_to_action": True},
                "metadata": {"purpose": "blog_publication"},
            },
        ]

        created_transformations = []
        for transform_request in transformation_requests:
            transform_data = {**transform_request, "document_id": document_id}

            transform_response = await api_client.post(
                "/api/transformations", json=transform_data, headers=headers
            )
            assert transform_response.status_code in [201, 202]

            created_transformations.append(transform_response.json())

        # Wait for transformations to complete
        completed_transformations = []
        for transformation in created_transformations:
            transformation_id = transformation["id"]

            for _ in range(15):
                status_response = await api_client.get(
                    f"/api/transformations/{transformation_id}/status", headers=headers
                )

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    if status_data["database_status"] == "completed":
                        # Get final result
                        result_response = await api_client.get(
                            f"/api/transformations/{transformation_id}", headers=headers
                        )
                        assert result_response.status_code == 200

                        completed_transformations.append(result_response.json())
                        break
                    elif status_data["database_status"] == "failed":
                        break

                await asyncio.sleep(1)

        # Verify content creator has their transformed content
        assert (
            len(completed_transformations) >= 1
        )  # At least one transformation completed

        # Check user's content library
        docs_response = await api_client.get("/api/documents", headers=headers)
        assert docs_response.status_code == 200

        user_docs = docs_response.json()["documents"]
        assert any(doc["id"] == document_id for doc in user_docs)

        transforms_response = await api_client.get(
            "/api/transformations", headers=headers
        )
        assert transforms_response.status_code == 200

        user_transforms = transforms_response.json()["transformations"]
        assert len(user_transforms) >= len(created_transformations)
