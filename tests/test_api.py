"""
Integration tests for API endpoints
Tests all major API functionality including CRUD operations, validation, etc.
"""

import pytest
import httpx
from typing import Dict, Any


class TestHealthEndpoints:
    """Test health check and monitoring endpoints"""

    @pytest.mark.integration
    async def test_basic_health_check(self, api_client: httpx.AsyncClient):
        """Test basic health endpoint"""
        response = await api_client.get("/api/health")
        assert response.status_code == 200

        health_data = response.json()
        assert "status" in health_data
        assert health_data["status"] == "healthy"
        assert "timestamp" in health_data

    @pytest.mark.integration
    @pytest.mark.database
    async def test_database_health_check(self, api_client: httpx.AsyncClient):
        """Test database health endpoint"""
        response = await api_client.get("/api/health/database")
        assert response.status_code == 200

        db_health = response.json()
        assert "status" in db_health
        assert "connection" in db_health
        assert db_health["status"] == "healthy"

    @pytest.mark.integration
    @pytest.mark.redis
    async def test_redis_health_check(self, api_client: httpx.AsyncClient):
        """Test Redis health endpoint"""
        response = await api_client.get("/api/health/redis")
        assert response.status_code == 200

        redis_health = response.json()
        assert "status" in redis_health
        assert "connected" in redis_health


class TestWorkspaceEndpoints:
    """Test workspace management endpoints"""

    @pytest.mark.integration
    async def test_create_workspace(self, authenticated_client: httpx.AsyncClient):
        """Test workspace creation"""
        workspace_data = {
            "name": "Test Workspace API",
            "description": "Created by API integration tests",
            "plan": "free",
        }

        response = await authenticated_client.post(
            "/api/workspaces", json=workspace_data
        )

        if response.status_code == 201:
            # New workspace created
            workspace = response.json()
            assert workspace["name"] == workspace_data["name"]
            assert workspace["description"] == workspace_data["description"]
            assert workspace["plan"] == workspace_data["plan"]
            assert "id" in workspace
            assert "slug" in workspace
        elif response.status_code == 409:
            # Workspace already exists
            assert "already exists" in response.text.lower()
        else:
            pytest.fail(
                f"Unexpected status code: {response.status_code}, {response.text}"
            )

    @pytest.mark.integration
    async def test_list_workspaces(self, authenticated_client: httpx.AsyncClient):
        """Test listing user workspaces"""
        response = await authenticated_client.get("/api/workspaces")
        assert response.status_code == 200

        workspaces_data = response.json()
        assert "workspaces" in workspaces_data
        assert isinstance(workspaces_data["workspaces"], list)

        # Should have at least one workspace (from test_workspace fixture)
        assert len(workspaces_data["workspaces"]) >= 1

        # Verify workspace structure
        if workspaces_data["workspaces"]:
            workspace = workspaces_data["workspaces"][0]
            assert "id" in workspace
            assert "name" in workspace
            assert "slug" in workspace
            assert "plan" in workspace

    @pytest.mark.integration
    async def test_get_workspace_details(
        self, authenticated_client: httpx.AsyncClient, test_workspace: Dict[str, Any]
    ):
        """Test getting workspace details"""
        workspace_id = test_workspace["id"]

        response = await authenticated_client.get(f"/api/workspaces/{workspace_id}")
        assert response.status_code == 200

        workspace = response.json()
        assert workspace["id"] == workspace_id
        assert workspace["name"] == test_workspace["name"]

    @pytest.mark.integration
    async def test_workspace_isolation(self, api_client: httpx.AsyncClient):
        """Test that workspaces properly isolate user data"""
        # This would require creating multiple users and workspaces
        # For now, test that unauthorized access is blocked

        response = await api_client.get("/api/workspaces")
        assert response.status_code == 401  # Unauthorized without token


class TestDocumentEndpoints:
    """Test document management endpoints"""

    @pytest.mark.integration
    async def test_create_document(self, authenticated_client: httpx.AsyncClient):
        """Test document creation"""
        document_data = {
            "title": "API Test Document",
            "content": "This is a test document created by API integration tests. It contains sample content for testing various transformations.",
            "source_type": "text",
            "metadata": {"test": True, "source": "api_integration_test"},
        }

        response = await authenticated_client.post("/api/documents", json=document_data)
        assert response.status_code == 201

        document = response.json()
        assert document["title"] == document_data["title"]
        assert document["content"] == document_data["content"]
        assert document["source_type"] == document_data["source_type"]
        assert "id" in document
        assert "created_at" in document

    @pytest.mark.integration
    async def test_list_documents(self, authenticated_client: httpx.AsyncClient):
        """Test listing user documents"""
        response = await authenticated_client.get("/api/documents")
        assert response.status_code == 200

        documents_data = response.json()
        assert "documents" in documents_data
        assert isinstance(documents_data["documents"], list)

        # Should have at least one document (from test_document fixture)
        assert len(documents_data["documents"]) >= 1

        # Verify document structure
        if documents_data["documents"]:
            document = documents_data["documents"][0]
            assert "id" in document
            assert "title" in document
            assert "created_at" in document

    @pytest.mark.integration
    async def test_get_document_details(
        self, authenticated_client: httpx.AsyncClient, test_document: Dict[str, Any]
    ):
        """Test getting document details"""
        document_id = test_document["id"]

        response = await authenticated_client.get(f"/api/documents/{document_id}")
        assert response.status_code == 200

        document = response.json()
        assert document["id"] == document_id
        assert document["title"] == test_document["title"]
        assert document["content"] == test_document["content"]

    @pytest.mark.integration
    async def test_update_document(
        self, authenticated_client: httpx.AsyncClient, test_document: Dict[str, Any]
    ):
        """Test updating document"""
        document_id = test_document["id"]

        update_data = {
            "title": "Updated Test Document",
            "content": "Updated content for testing purposes.",
        }

        response = await authenticated_client.put(
            f"/api/documents/{document_id}", json=update_data
        )
        assert response.status_code == 200

        updated_document = response.json()
        assert updated_document["title"] == update_data["title"]
        assert updated_document["content"] == update_data["content"]

    @pytest.mark.integration
    async def test_delete_document(self, authenticated_client: httpx.AsyncClient):
        """Test document deletion"""
        # Create a document to delete
        document_data = {
            "title": "Document to Delete",
            "content": "This document will be deleted in the test.",
            "source_type": "text",
        }

        create_response = await authenticated_client.post(
            "/api/documents", json=document_data
        )
        assert create_response.status_code == 201

        document = create_response.json()
        document_id = document["id"]

        # Delete the document
        delete_response = await authenticated_client.delete(
            f"/api/documents/{document_id}"
        )
        assert delete_response.status_code in [200, 204]

        # Verify document is deleted
        get_response = await authenticated_client.get(f"/api/documents/{document_id}")
        assert get_response.status_code == 404


class TestTransformationEndpoints:
    """Test transformation processing endpoints"""

    @pytest.mark.integration
    async def test_create_transformation(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: Dict[str, Any],
        sample_transformation_data: Dict[str, Any],
    ):
        """Test transformation creation"""
        transformation_data = {
            **sample_transformation_data,
            "document_id": test_document["id"],
        }

        response = await authenticated_client.post(
            "/api/transformations", json=transformation_data
        )
        assert response.status_code in [
            201,
            202,
        ]  # Created or Accepted for background processing

        transformation = response.json()
        assert "id" in transformation
        assert transformation["document_id"] == test_document["id"]
        assert (
            transformation["transformation_type"]
            == transformation_data["transformation_type"]
        )

    @pytest.mark.integration
    async def test_list_transformations(self, authenticated_client: httpx.AsyncClient):
        """Test listing user transformations"""
        response = await authenticated_client.get("/api/transformations")
        assert response.status_code == 200

        transformations_data = response.json()
        assert "transformations" in transformations_data
        assert isinstance(transformations_data["transformations"], list)

        # Verify transformation structure if any exist
        if transformations_data["transformations"]:
            transformation = transformations_data["transformations"][0]
            assert "id" in transformation
            assert "document_id" in transformation
            assert "transformation_type" in transformation
            assert "status" in transformation

    @pytest.mark.integration
    async def test_get_transformation_status(
        self,
        authenticated_client: httpx.AsyncClient,
        test_document: Dict[str, Any],
        sample_transformation_data: Dict[str, Any],
    ):
        """Test getting transformation status"""
        # Create transformation
        transformation_data = {
            **sample_transformation_data,
            "document_id": test_document["id"],
        }

        create_response = await authenticated_client.post(
            "/api/transformations", json=transformation_data
        )
        assert create_response.status_code in [201, 202]

        transformation = create_response.json()
        transformation_id = transformation["id"]

        # Get status
        status_response = await authenticated_client.get(
            f"/api/transformations/{transformation_id}/status"
        )
        assert status_response.status_code == 200

        status_data = status_response.json()
        assert "database_status" in status_data
        assert status_data["database_status"] in [
            "pending",
            "processing",
            "completed",
            "failed",
        ]


class TestAPIValidation:
    """Test API input validation and error handling"""

    @pytest.mark.integration
    async def test_invalid_json_handling(self, authenticated_client: httpx.AsyncClient):
        """Test handling of invalid JSON data"""
        headers = {"Content-Type": "application/json"}
        invalid_json = '{"invalid": json}'

        response = await authenticated_client.post(
            "/api/documents", content=invalid_json, headers=headers
        )
        assert response.status_code == 422  # Unprocessable Entity

    @pytest.mark.integration
    async def test_missing_required_fields(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test validation of required fields"""
        # Try to create document without required fields
        incomplete_data = {
            "title": "Test"
            # Missing content and source_type
        }

        response = await authenticated_client.post(
            "/api/documents", json=incomplete_data
        )
        assert response.status_code == 422

        error_data = response.json()
        assert "detail" in error_data

    @pytest.mark.integration
    async def test_invalid_field_types(self, authenticated_client: httpx.AsyncClient):
        """Test validation of field types"""
        invalid_data = {
            "title": 123,  # Should be string
            "content": "Valid content",
            "source_type": "text",
        }

        response = await authenticated_client.post("/api/documents", json=invalid_data)
        assert response.status_code == 422

    @pytest.mark.integration
    async def test_unauthorized_access(self, api_client: httpx.AsyncClient):
        """Test that endpoints properly require authentication"""
        protected_endpoints = [
            "/api/workspaces",
            "/api/documents",
            "/api/transformations",
            "/api/auth/me",
        ]

        for endpoint in protected_endpoints:
            response = await api_client.get(endpoint)
            assert response.status_code == 401, (
                f"Endpoint {endpoint} should require authentication"
            )

    @pytest.mark.integration
    async def test_nonexistent_resource_access(
        self, authenticated_client: httpx.AsyncClient
    ):
        """Test accessing nonexistent resources"""
        nonexistent_id = "00000000-0000-0000-0000-000000000000"

        endpoints_to_test = [
            f"/api/documents/{nonexistent_id}",
            f"/api/transformations/{nonexistent_id}",
            f"/api/workspaces/{nonexistent_id}",
        ]

        for endpoint in endpoints_to_test:
            response = await authenticated_client.get(endpoint)
            assert response.status_code == 404, (
                f"Endpoint {endpoint} should return 404 for nonexistent resource"
            )
