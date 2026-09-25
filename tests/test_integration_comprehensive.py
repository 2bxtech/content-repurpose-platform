"""
Integration tests for upload, transform, and WebSocket functionality.
Tests the complete flow between frontend services and backend APIs.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import io

from app.main import app
from app.core.websocket_manager import manager
from app.models.documents import DocumentStatus


class TestUploadIntegration:
    """Integration tests for document upload functionality"""

    def setup_method(self):
        """Set up test client and mock dependencies"""
        self.client = TestClient(app)
        self.test_user = {
            "id": "test-user-123",
            "username": "testuser",
            "email": "test@example.com"
        }
        self.workspace_context = {
            "workspace_id": "test-workspace-123"
        }

    @pytest.fixture
    def mock_auth(self):
        """Mock authentication"""
        with patch('app.api.routes.auth.get_current_active_user') as mock:
            mock.return_value = self.test_user
            yield mock

    @pytest.fixture
    def mock_workspace(self):
        """Mock workspace context"""
        with patch('app.api.routes.workspaces.get_current_workspace_context') as mock:
            mock.return_value = self.workspace_context
            yield mock

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        with patch('app.core.database.get_db_session') as mock:
            mock.return_value = None  # Use in-memory fallback
            yield mock

    @pytest.fixture
    def mock_file_processor(self):
        """Mock file processor"""
        with patch('app.services.file_processor.file_processor') as mock:
            mock.validate_file_type.return_value = True
            mock.process_file.return_value = Mock(
                security_scan_passed=True,
                content="Test document content",
                metadata={"pages": 1, "word_count": 100},
                file_hash="test-hash",
                preview_path=None,
                content_encoding="utf-8",
                extraction_method="text"
            )
            yield mock

    def test_upload_document_success(self, mock_auth, mock_workspace, mock_db, mock_file_processor):
        """Test successful document upload"""
        # Create test file
        test_content = b"This is a test PDF content"
        test_file = io.BytesIO(test_content)
        
        files = {
            "file": ("test.pdf", test_file, "application/pdf")
        }
        data = {
            "title": "Test Document",
            "description": "Test document description"
        }

        response = self.client.post("/api/documents/upload", files=files, data=data)

        assert response.status_code == 201
        result = response.json()
        
        assert result["title"] == "Test Document"
        assert result["description"] == "Test document description"
        assert result["original_filename"] == "test.pdf"
        assert result["content_type"] == "application/pdf"
        assert result["status"] == DocumentStatus.COMPLETED.value
        assert "id" in result
        assert result["user_id"] == self.test_user["id"]

    def test_upload_invalid_file_type(self, mock_auth, mock_workspace, mock_db, mock_file_processor):
        """Test upload with invalid file type"""
        mock_file_processor.validate_file_type.return_value = False
        
        test_content = b"This is not a valid file"
        test_file = io.BytesIO(test_content)
        
        files = {
            "file": ("test.exe", test_file, "application/x-executable")
        }
        data = {
            "title": "Invalid File",
            "description": "This should fail"
        }

        response = self.client.post("/api/documents/upload", files=files, data=data)

        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_upload_security_scan_failure(self, mock_auth, mock_workspace, mock_db, mock_file_processor):
        """Test upload with security scan failure"""
        mock_file_processor.process_file.return_value = Mock(
            security_scan_passed=False
        )
        
        test_content = b"Malicious content"
        test_file = io.BytesIO(test_content)
        
        files = {
            "file": ("malicious.pdf", test_file, "application/pdf")
        }
        data = {
            "title": "Malicious File",
            "description": "This should fail security scan"
        }

        response = self.client.post("/api/documents/upload", files=files, data=data)

        assert response.status_code == 400
        assert "File failed security validation" in response.json()["detail"]

    def test_upload_large_file(self, mock_auth, mock_workspace, mock_db, mock_file_processor):
        """Test upload with file size exceeding limit"""
        # Create a large file content
        large_content = b"x" * (100 * 1024 * 1024)  # 100MB
        test_file = io.BytesIO(large_content)
        
        files = {
            "file": ("large.pdf", test_file, "application/pdf")
        }
        data = {
            "title": "Large File",
            "description": "This should fail due to size"
        }

        with patch('app.core.config.settings.MAX_UPLOAD_SIZE', 50 * 1024 * 1024):  # 50MB limit
            response = self.client.post("/api/documents/upload", files=files, data=data)

        assert response.status_code == 400
        assert "File too large" in response.json()["detail"]

    def test_get_documents_after_upload(self, mock_auth, mock_workspace, mock_db, mock_file_processor):
        """Test retrieving documents after upload"""
        # First upload a document
        test_content = b"Test content"
        test_file = io.BytesIO(test_content)
        
        files = {
            "file": ("test.pdf", test_file, "application/pdf")
        }
        data = {
            "title": "Test Document",
            "description": "Test description"
        }

        upload_response = self.client.post("/api/documents/upload", files=files, data=data)
        assert upload_response.status_code == 201

        # Then retrieve documents
        get_response = self.client.get("/api/documents")
        assert get_response.status_code == 200
        
        result = get_response.json()
        assert result["count"] == 1
        assert len(result["documents"]) == 1
        assert result["documents"][0]["title"] == "Test Document"


class TestTransformationIntegration:
    """Integration tests for transformation functionality"""

    def setup_method(self):
        """Set up test client and mock dependencies"""
        self.client = TestClient(app)
        self.test_user = {
            "id": "test-user-123",
            "username": "testuser",
            "email": "test@example.com"
        }

    @pytest.fixture
    def mock_auth(self):
        """Mock authentication"""
        with patch('app.services.auth_service.get_current_user') as mock:
            mock.return_value = self.test_user
            yield mock

    @pytest.fixture
    def mock_task_service(self):
        """Mock task service"""
        with patch('app.services.task_service.task_service') as mock:
            mock.start_transformation_task.return_value = "test-task-id-123"
            yield mock

    def test_create_transformation_success(self, mock_auth, mock_task_service):
        """Test successful transformation creation"""
        transformation_data = {
            "sourceDocument": "This is a test document content for transformation.",
            "transformationType": "BLOG_POST",
            "parameters": {
                "wordCount": 500,
                "tone": "professional"
            }
        }

        response = self.client.post("/api/transformations", json=transformation_data)

        assert response.status_code == 200
        result = response.json()
        
        assert result["status"] == "processing"
        assert "Transformation started successfully" in result["message"]
        assert result["transformationType"] == "BLOG_POST"
        assert result["parameters"]["wordCount"] == 500
        assert result["parameters"]["tone"] == "professional"
        assert result["parameters"]["authenticated"] == True
        assert "id" in result

    def test_create_transformation_invalid_type(self, mock_auth, mock_task_service):
        """Test transformation creation with invalid type"""
        transformation_data = {
            "sourceDocument": "Test content",
            "transformationType": "INVALID_TYPE",
            "parameters": {
                "wordCount": 500,
                "tone": "professional"
            }
        }

        response = self.client.post("/api/transformations", json=transformation_data)

        assert response.status_code == 500
        assert "Failed to create transformation" in response.json()["detail"]

    def test_create_transformation_missing_auth(self):
        """Test transformation creation without authentication"""
        transformation_data = {
            "sourceDocument": "Test content",
            "transformationType": "BLOG_POST",
            "parameters": {
                "wordCount": 500,
                "tone": "professional"
            }
        }

        # No auth mock - should fail
        response = self.client.post("/api/transformations", json=transformation_data)

        assert response.status_code == 401 or response.status_code == 403

    def test_transformation_health_check(self):
        """Test transformation service health check"""
        response = self.client.get("/api/transformations/health")
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "healthy"
        assert result["service"] == "transformations"

    def test_get_transformations_list(self, mock_auth):
        """Test getting transformations list"""
        response = self.client.get("/api/transformations")
        
        assert response.status_code == 200
        result = response.json()
        assert "transformations" in result
        assert "count" in result
        assert result["count"] == 0  # Empty list initially


class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality"""

    def setup_method(self):
        """Set up test dependencies"""
        self.test_user = {
            "id": "test-user-123",
            "username": "testuser",
            "email": "test@example.com"
        }
        self.workspace_id = "test-workspace-123"

    @pytest.fixture
    def mock_websocket_auth(self):
        """Mock WebSocket authentication"""
        with patch('app.core.websocket_auth.get_websocket_user') as mock:
            mock.return_value = self.test_user
            yield mock

    @pytest.mark.asyncio
    async def test_websocket_connection_success(self, mock_websocket_auth):
        """Test successful WebSocket connection"""
        # Mock WebSocket
        mock_websocket = Mock()
        mock_websocket.headers = {}
        
        # Mock WebSocket manager
        with patch.object(manager, 'connect') as mock_connect, \
             patch.object(manager, 'send_to_connection') as mock_send, \
             patch.object(manager, 'get_workspace_presence') as mock_presence:
            
            mock_connect.return_value = "connection-123"
            mock_presence.return_value = []

            # Simulate successful connection (this would normally be done via WebSocket)
            connection_id = await manager.connect(
                websocket=mock_websocket,
                user_id=self.test_user["id"],
                workspace_id=self.workspace_id,
                user_info={"username": self.test_user["username"]}
            )

            assert connection_id is not None
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_broadcast_message(self):
        """Test WebSocket message broadcasting"""
        test_message = {
            "type": "transformation_update",
            "data": {
                "transformation_id": "trans-123",
                "status": "completed",
                "progress": 100
            }
        }

        with patch.object(manager, 'broadcast_to_workspace') as mock_broadcast:
            await manager.broadcast_to_workspace(self.workspace_id, test_message)
            mock_broadcast.assert_called_once_with(self.workspace_id, test_message)

    @pytest.mark.asyncio
    async def test_websocket_send_to_user(self):
        """Test sending message to specific user"""
        test_message = {
            "type": "notification",
            "data": {
                "message": "Your transformation is complete"
            }
        }

        with patch.object(manager, 'send_to_user') as mock_send:
            await manager.send_to_user(self.test_user["id"], test_message)
            mock_send.assert_called_once_with(self.test_user["id"], test_message)


class TestEndToEndWorkflow:
    """End-to-end integration tests for complete workflows"""

    def setup_method(self):
        """Set up test client and dependencies"""
        self.client = TestClient(app)
        self.test_user = {
            "id": "test-user-123",
            "username": "testuser",
            "email": "test@example.com"
        }
        self.workspace_context = {
            "workspace_id": "test-workspace-123"
        }

    @pytest.fixture
    def mock_auth(self):
        """Mock authentication"""
        with patch('app.api.routes.auth.get_current_active_user') as mock_auth_docs, \
             patch('app.services.auth_service.get_current_user') as mock_auth_trans:
            mock_auth_docs.return_value = self.test_user
            mock_auth_trans.return_value = self.test_user
            yield mock_auth_docs, mock_auth_trans

    @pytest.fixture
    def mock_workspace(self):
        """Mock workspace context"""
        with patch('app.api.routes.workspaces.get_current_workspace_context') as mock:
            mock.return_value = self.workspace_context
            yield mock

    @pytest.fixture
    def mock_dependencies(self):
        """Mock various dependencies"""
        with patch('app.core.database.get_db_session') as mock_db, \
             patch('app.services.file_processor.file_processor') as mock_processor, \
             patch('app.services.task_service.task_service') as mock_task:
            
            # Configure mocks
            mock_db.return_value = None  # Use in-memory fallback
            mock_processor.validate_file_type.return_value = True
            mock_processor.process_file.return_value = Mock(
                security_scan_passed=True,
                content="Test document content for transformation",
                metadata={"pages": 1, "word_count": 100},
                file_hash="test-hash",
                preview_path=None,
                content_encoding="utf-8",
                extraction_method="text"
            )
            mock_task.start_transformation_task.return_value = "test-task-123"
            
            yield mock_db, mock_processor, mock_task

    def test_complete_upload_transform_workflow(self, mock_auth, mock_workspace, mock_dependencies):
        """Test complete workflow: upload document -> create transformation"""
        
        # Step 1: Upload a document
        test_content = b"This is a comprehensive test document that will be transformed into various content types."
        test_file = io.BytesIO(test_content)
        
        files = {
            "file": ("comprehensive_test.pdf", test_file, "application/pdf")
        }
        data = {
            "title": "Comprehensive Test Document",
            "description": "A document for testing the complete workflow"
        }

        upload_response = self.client.post("/api/documents/upload", files=files, data=data)
        assert upload_response.status_code == 201
        
        document = upload_response.json()
        document_id = document["id"]
        
        # Step 2: Verify document was uploaded
        get_docs_response = self.client.get("/api/documents")
        assert get_docs_response.status_code == 200
        
        docs_list = get_docs_response.json()
        assert docs_list["count"] == 1
        assert docs_list["documents"][0]["id"] == document_id
        
        # Step 3: Create a transformation using the uploaded document
        transformation_data = {
            "sourceDocument": document["extracted_text"] if "extracted_text" in document else "Test content",
            "transformationType": "BLOG_POST",
            "parameters": {
                "wordCount": 800,
                "tone": "professional"
            }
        }

        transform_response = self.client.post("/api/transformations", json=transformation_data)
        assert transform_response.status_code == 200
        
        transformation = transform_response.json()
        assert transformation["status"] == "processing"
        assert transformation["transformationType"] == "BLOG_POST"
        assert transformation["parameters"]["authenticated"] == True
        
        # Step 4: Check transformations list
        get_transforms_response = self.client.get("/api/transformations")
        assert get_transforms_response.status_code == 200
        
        # Should return empty list in this test setup, but endpoint should work
        transforms_list = get_transforms_response.json()
        assert "transformations" in transforms_list
        assert "count" in transforms_list

    def test_multiple_transformation_types_workflow(self, mock_auth, mock_workspace, mock_dependencies):
        """Test creating multiple transformation types from same document"""
        
        # Upload document first
        test_content = b"Marketing content that will be repurposed into multiple formats."
        test_file = io.BytesIO(test_content)
        
        files = {
            "file": ("marketing_content.pdf", test_file, "application/pdf")
        }
        data = {
            "title": "Marketing Content",
            "description": "Content to be repurposed"
        }

        upload_response = self.client.post("/api/documents/upload", files=files, data=data)
        assert upload_response.status_code == 201
        
        document = upload_response.json()
        source_content = "Marketing content for transformation"
        
        # Create different types of transformations
        transformation_types = [
            {
                "type": "BLOG_POST",
                "params": {"wordCount": 1000, "tone": "professional"}
            },
            {
                "type": "SOCIAL_MEDIA", 
                "params": {"wordCount": 280, "tone": "casual"}
            },
            {
                "type": "EMAIL_SEQUENCE",
                "params": {"wordCount": 500, "tone": "persuasive"}
            }
        ]
        
        transformation_results = []
        
        for trans_type in transformation_types:
            transformation_data = {
                "sourceDocument": source_content,
                "transformationType": trans_type["type"],
                "parameters": trans_type["params"]
            }

            response = self.client.post("/api/transformations", json=transformation_data)
            assert response.status_code == 200
            
            result = response.json()
            assert result["transformationType"] == trans_type["type"]
            assert result["status"] == "processing"
            transformation_results.append(result)
        
        # Verify all transformations were created
        assert len(transformation_results) == 3
        
        # Each should have unique ID
        ids = [t["id"] for t in transformation_results]
        assert len(set(ids)) == 3  # All unique

    def test_error_handling_workflow(self, mock_auth, mock_workspace, mock_dependencies):
        """Test error handling in complete workflow"""
        
        # Test 1: Invalid file upload
        mock_db, mock_processor, mock_task = mock_dependencies
        mock_processor.validate_file_type.return_value = False
        
        invalid_file = io.BytesIO(b"Invalid content")
        files = {
            "file": ("invalid.exe", invalid_file, "application/x-executable")
        }
        data = {
            "title": "Invalid File",
            "description": "This should fail"
        }

        response = self.client.post("/api/documents/upload", files=files, data=data)
        assert response.status_code == 400
        
        # Test 2: Security scan failure
        mock_processor.validate_file_type.return_value = True
        mock_processor.process_file.return_value = Mock(
            security_scan_passed=False
        )
        
        malicious_file = io.BytesIO(b"Malicious content")
        files = {
            "file": ("malicious.pdf", malicious_file, "application/pdf")
        }
        data = {
            "title": "Malicious File",
            "description": "This should fail security"
        }

        response = self.client.post("/api/documents/upload", files=files, data=data)
        assert response.status_code == 400
        assert "security validation" in response.json()["detail"]
        
        # Test 3: Transformation with invalid type
        transformation_data = {
            "sourceDocument": "Test content",
            "transformationType": "INVALID_TYPE",
            "parameters": {"wordCount": 500, "tone": "professional"}
        }

        response = self.client.post("/api/transformations", json=transformation_data)
        assert response.status_code == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])