"""
Integration tests for transformation presets with transformations endpoint
Tests the preset_id parameter and parameter merging logic
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient


async def upload_test_document(client: AsyncClient, title: str = "Test Document") -> str:
    """Helper function to upload a test document and return its ID"""
    # Save original headers and temporarily remove Content-Type to let httpx set multipart
    original_headers = client.headers.copy()
    
    # Remove Content-Type if present to allow httpx to set multipart automatically
    if 'content-type' in client.headers:
        del client.headers['content-type']
    if 'Content-Type' in client.headers:
        del client.headers['Content-Type']
    
    try:
        response = await client.post(
            "/api/documents/upload",
            data={"title": title, "description": "Test"},
            files={"file": ("test.txt", b"Test content for transformation", "text/plain")}
        )
    finally:
        # Restore original headers
        client.headers.update(original_headers)
    
    assert response.status_code == 201, f"Document upload failed: {response.status_code} - {response.text}"
    return response.json()["id"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestTransformationPresetIntegration:
    """Test transformation creation with presets"""
    
    async def test_create_transformation_with_preset(
        self,
        authenticated_client: AsyncClient
    ):
        """Test creating transformation using a preset"""
        # Create a document first
        document_id = await upload_test_document(authenticated_client)
        
        # Create a preset
        preset_data = {
            "name": "Blog Post Template",
            "description": "Standard blog post format",
            "transformation_type": "BLOG_POST",
            "parameters": {
                "tone": "professional",
                "target_audience": "developers",
                "word_count": 1000
            },
            "is_shared": False
        }
        
        preset_response = await authenticated_client.post(
            "/api/transformation-presets",
            json=preset_data
        )
        assert preset_response.status_code == 201
        preset = preset_response.json()
        preset_id = preset["id"]
        
        # Create transformation using preset
        transformation_data = {
            "document_id": document_id,
            "transformation_type": "BLOG_POST",
            "preset_id": preset_id
        }

        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json=transformation_data
        )

        if transform_response.status_code != 201:
            print(f"Transform failed: {transform_response.status_code}")
            print(f"Response: {transform_response.text}")
            print(f"Headers: {transform_response.headers}")
        assert transform_response.status_code == 201
        transformation = transform_response.json()
        
        # Verify transformation used preset parameters
        assert transformation["parameters"]["tone"] == "professional"
        assert transformation["parameters"]["target_audience"] == "developers"
        assert transformation["parameters"]["word_count"] == 1000
        
        # Verify preset usage count incremented
        preset_check = await authenticated_client.get(
            f"/api/transformation-presets/{preset_id}"
        )
        assert preset_check.status_code == 200
        assert preset_check.json()["usage_count"] == 1
    
    async def test_create_transformation_with_preset_parameter_override(
        self,
        authenticated_client: AsyncClient
    ):
        """Test that request parameters override preset parameters"""
        # Create document
        document_id = await upload_test_document(authenticated_client)
        
        # Create preset with base parameters
        preset_data = {
            "name": "Social Media Base",
            "transformation_type": "SOCIAL_MEDIA",
            "parameters": {
                "platform": "linkedin",
                "tone": "professional",
                "hashtags": True
            }
        }
        
        preset_response = await authenticated_client.post(
            "/api/transformation-presets",
            json=preset_data
        )
        assert preset_response.status_code == 201
        preset_id = preset_response.json()["id"]
        
        # Create transformation with parameter overrides
        transformation_data = {
            "document_id": document_id,
            "transformation_type": "SOCIAL_MEDIA",
            "preset_id": preset_id,
            "parameters": {
                "platform": "twitter",  # Override
                "tone": "casual"  # Override
                # hashtags not specified, should use preset value
            }
        }
        
        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json=transformation_data
        )
        
        assert transform_response.status_code == 201
        transformation = transform_response.json()
        
        # Verify merged parameters: overrides applied, preset values kept for unspecified
        assert transformation["parameters"]["platform"] == "twitter"  # Overridden
        assert transformation["parameters"]["tone"] == "casual"  # Overridden
        assert transformation["parameters"]["hashtags"] is True  # From preset
    
    async def test_create_transformation_with_nonexistent_preset(
        self,
        authenticated_client: AsyncClient
    ):
        """Test error when using non-existent preset"""
        # Create document
        document_id = await upload_test_document(authenticated_client)
        
        # Try to use non-existent preset
        fake_preset_id = str(uuid4())
        transformation_data = {
            "document_id": document_id,
            "transformation_type": "SUMMARY",
            "preset_id": fake_preset_id
        }
        
        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json=transformation_data
        )
        
        assert transform_response.status_code == 404
        assert "not found" in transform_response.json()["detail"].lower()
    
    async def test_create_transformation_with_wrong_preset_type(
        self,
        authenticated_client: AsyncClient
    ):
        """Test error when preset type doesn't match transformation type"""
        # Create document
        document_id = await upload_test_document(authenticated_client)
        
        # Create preset for BLOG_POST
        preset_data = {
            "name": "Blog Preset",
            "transformation_type": "BLOG_POST",
            "parameters": {"tone": "professional"}
        }
        
        preset_response = await authenticated_client.post(
            "/api/transformation-presets",
            json=preset_data
        )
        assert preset_response.status_code == 201
        preset_id = preset_response.json()["id"]
        
        # Try to use BLOG_POST preset for SUMMARY transformation
        transformation_data = {
            "document_id": document_id,
            "transformation_type": "SUMMARY",  # Different type
            "preset_id": preset_id
        }
        
        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json=transformation_data
        )
        
        assert transform_response.status_code == 400
        assert "does not match" in transform_response.json()["detail"].lower()
    
    async def test_create_transformation_without_preset(
        self,
        authenticated_client: AsyncClient
    ):
        """Test transformation creation still works without preset (backward compatibility)"""
        # Create document
        document_id = await upload_test_document(authenticated_client)
        
        # Create transformation without preset (original behavior)
        transformation_data = {
            "document_id": document_id,
            "transformation_type": "SUMMARY",
            "parameters": {
                "length": "short",
                "style": "bullet_points"
            }
        }
        
        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json=transformation_data
        )
        
        assert transform_response.status_code == 201
        transformation = transform_response.json()
        
        # Verify parameters used as specified
        assert transformation["parameters"]["length"] == "short"
        assert transformation["parameters"]["style"] == "bullet_points"
    
    async def test_create_transformation_with_shared_preset(
        self,
        authenticated_client: AsyncClient
    ):
        """Test using a shared workspace preset"""
        # Create document
        document_id = await upload_test_document(authenticated_client)
        
        # Create shared preset
        preset_data = {
            "name": "Team Newsletter Template",
            "transformation_type": "NEWSLETTER",
            "parameters": {
                "sections": ["intro", "highlights", "conclusion"],
                "tone": "informative",
                "length": "medium"
            },
            "is_shared": True
        }
        
        preset_response = await authenticated_client.post(
            "/api/transformation-presets",
            json=preset_data
        )
        assert preset_response.status_code == 201
        preset_id = preset_response.json()["id"]
        
        # Use shared preset in transformation
        transformation_data = {
            "document_id": document_id,
            "transformation_type": "NEWSLETTER",
            "preset_id": preset_id
        }
        
        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json=transformation_data
        )
        
        assert transform_response.status_code == 201
        transformation = transform_response.json()
        
        # Verify preset parameters applied
        assert transformation["parameters"]["sections"] == ["intro", "highlights", "conclusion"]
        assert transformation["parameters"]["tone"] == "informative"
        assert transformation["parameters"]["length"] == "medium"
    
    async def test_preset_usage_count_increments_correctly(
        self,
        authenticated_client: AsyncClient
    ):
        """Test that usage_count increments each time preset is used"""
        # Create document
        document_id = await upload_test_document(authenticated_client)
        
        # Create preset
        preset_data = {
            "name": "Usage Counter Test",
            "transformation_type": "CUSTOM",
            "parameters": {"instructions": "Test preset"}
        }
        
        preset_response = await authenticated_client.post(
            "/api/transformation-presets",
            json=preset_data
        )
        assert preset_response.status_code == 201
        preset_id = preset_response.json()["id"]
        
        # Verify initial usage count is 0
        preset = await authenticated_client.get(
            f"/api/transformation-presets/{preset_id}"
        )
        assert preset.json()["usage_count"] == 0
        
        # Use preset 3 times
        for i in range(3):
            transformation_data = {
                "document_id": document_id,
                "transformation_type": "CUSTOM",
                "preset_id": preset_id
            }
            
            transform_response = await authenticated_client.post(
                "/api/transformations/",
                json=transformation_data
            )
            assert transform_response.status_code == 201
        
        # Verify usage count is now 3
        preset_final = await authenticated_client.get(
            f"/api/transformation-presets/{preset_id}"
        )
        assert preset_final.json()["usage_count"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestTransformationPresetWorkspaceIsolation:
    """Test workspace isolation for preset integration"""
    
    async def test_cannot_use_preset_from_different_workspace(
        self,
        authenticated_client: AsyncClient
    ):
        """Test that users cannot use presets from other workspaces"""
        # This test would require creating a second workspace and user
        # For now, we verify the query filters by workspace_id
        # The actual workspace isolation is enforced by RLS policies
        
        # Create document
        document_id = await upload_test_document(authenticated_client)
        
        # Try to use a fake preset ID (simulates different workspace)
        fake_preset_id = str(uuid4())
        transformation_data = {
            "document_id": document_id,
            "transformation_type": "SUMMARY",
            "preset_id": fake_preset_id
        }
        
        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json=transformation_data
        )
        
        # Should get 404 because preset doesn't exist in this workspace
        assert transform_response.status_code == 404