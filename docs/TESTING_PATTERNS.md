# Testing Patterns for Async APIs

*Testing strategies for FastAPI applications with multi-tenant architecture*

## Overview

This document outlines testing patterns specifically designed for async FastAPI applications with multi-tenant architecture, focusing on practical testing approaches.

## Testing Principles

### 1. Async Database Testing
Proper async test patterns for SQLAlchemy sessions:

```python
import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session

@pytest.fixture
async def async_db_session():
    """Async database session for testing"""
    async for session in get_db_session():
        yield session
        await session.rollback()  # Cleanup after test

@pytest.mark.asyncio
async def test_transformation_creation(async_db_session: AsyncSession):
    """Test transformation creation with proper async patterns"""
    # Test implementation with actual async session
    pass
```

### 2. Multi-Tenant Testing
Verify workspace isolation between tenants:

```python
@pytest.mark.asyncio
async def test_workspace_isolation():
    """Verify users cannot access other workspace data"""
    # Create two separate workspaces
    workspace1 = await create_test_workspace("tenant1")
    workspace2 = await create_test_workspace("tenant2")
    
    # Create user in workspace1
    user1 = await create_test_user("user1@test.com", workspace1.id)
    
    # Create document in workspace2
    doc2 = await create_test_document("test.txt", workspace2.id)
    
    # Verify user1 cannot access doc2
    with pytest.raises(HTTPException) as exc_info:
        await get_document(doc2.id, user1.id)
    assert exc_info.value.status_code == 404
```

## API Testing Patterns

### 1. Authentication Testing
```python
class TestAuthentication:
    @pytest.mark.asyncio
    async def test_login_returns_valid_tokens(self):
        response = await async_client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "testpass123"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify token structure
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
```

### 2. UUID Conversion Testing
```python
class TestUUIDHandling:
    @pytest.mark.asyncio
    async def test_api_returns_string_uuids(self):
        """Verify all UUID fields are returned as strings"""
        response = await authenticated_client.get("/api/documents")
        assert response.status_code == 200
        
        data = response.json()
        documents = data["documents"]
        
        for doc in documents:
            # All ID fields should be strings, not objects
            assert isinstance(doc["id"], str)
            assert isinstance(doc["user_id"], str)
            
            # Should be valid UUID format
            import uuid
            uuid.UUID(doc["id"])  # Should not raise exception
```

### 3. Async Endpoint Testing
```python
class TestAsyncEndpoints:
    @pytest.mark.asyncio
    async def test_transformation_endpoint_async_safety(self):
        """Test transformation endpoint doesn't have greenlet issues"""
        # Create multiple concurrent requests
        tasks = []
        for i in range(5):
            task = asyncio.create_task(
                authenticated_client.get("/api/transformations/")
            )
            tasks.append(task)
        
        # All should complete without greenlet errors
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for response in responses:
            assert not isinstance(response, Exception)
            assert response.status_code in [200, 404]
```

## Docker Testing

### 1. Environment Validation
```python
def test_python_environment_variables():
    """Verify Python environment variables are set correctly"""
    
    result = subprocess.run([
        "docker-compose", "exec", "api",
        "python", "-c", 
        "import os; print(f'PYTHONDONTWRITEBYTECODE={os.environ.get(\"PYTHONDONTWRITEBYTECODE\")}')"
    ], capture_output=True, text=True)
    
    assert "PYTHONDONTWRITEBYTECODE=1" in result.stdout
```

### 2. Container Health Testing
```python
def test_api_container_health():
    """Test API container responds to health checks"""
    response = requests.get("http://localhost:8000/health")
    assert response.status_code == 200
```

## Integration Testing

### 1. End-to-End API Testing
```python
class TestTransformationWorkflow:
    @pytest.mark.asyncio
    async def test_complete_transformation_workflow(self):
        """Test document upload → transformation creation → result retrieval"""
        
        # Step 1: Upload document
        with open("test_document.txt", "rb") as f:
            upload_response = await authenticated_client.post(
                "/api/documents/upload",
                files={"file": f},
                data={"title": "Test Document"}
            )
        
        assert upload_response.status_code == 201
        document_id = upload_response.json()["id"]
        
        # Step 2: Create transformation
        transform_response = await authenticated_client.post(
            "/api/transformations/",
            json={
                "document_id": document_id,
                "transformation_type": "SUMMARY",
                "parameters": {"length": "short"}
            }
        )
        
        assert transform_response.status_code == 201
        transformation = transform_response.json()
        
        # Step 3: Verify result
        assert transformation["status"] == "COMPLETED"
        assert transformation["result"] is not None
```

### 2. CORS Testing
```python
class TestCORSIntegration:
    def test_cors_preflight_requests(self):
        """Test CORS OPTIONS requests work correctly"""
        
        origins_to_test = [
            "http://localhost:3000",
            "http://localhost:3001",
        ]
        
        for origin in origins_to_test:
            response = requests.options(
                "http://localhost:8000/api/transformations/",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization"
                }
            )
            
            assert response.status_code == 200
            assert origin in response.headers.get("Access-Control-Allow-Origin", "")
```

## Test Configuration

### 1. Pytest Configuration
```python
# conftest.py
import pytest
import asyncio
from httpx import AsyncClient
from app.main import app

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def async_client():
    """Async HTTP client for API testing"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

### 2. Test Data Management
```python
class TestDataFactory:
    @staticmethod
    async def create_isolated_test_environment():
        """Create completely isolated test environment"""
        
        # Create unique workspace
        workspace = await create_test_workspace(f"test-ws-{uuid.uuid4()}")
        
        # Create user in that workspace
        user = await create_test_user(
            f"test-{uuid.uuid4()}@test.com", 
            workspace.id
        )
        
        return {
            "workspace": workspace,
            "user": user,
            "auth_token": create_test_token(user.id)
        }
```

## Performance Testing

### 1. Concurrent Load Testing
```python
@pytest.mark.asyncio
async def test_concurrent_api_performance():
    """Test API performance under concurrent load"""
    
    import aiohttp
    
    async def make_request(session, url, headers):
        async with session.get(url, headers=headers) as response:
            return response.status, await response.text()
    
    # Test concurrent requests
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(20):
            task = make_request(
                session,
                "http://localhost:8000/api/transformations/",
                {"Authorization": f"Bearer {test_token}"}
            )
            tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time
        
        # Verify performance and no errors
        assert elapsed < 5.0  # Should complete within 5 seconds
        for result in results:
            assert not isinstance(result, Exception)
```

## Best Practices

### Test Organization
1. **Isolated Test Environments**: Each test creates its own workspace and user data
2. **Async Fixtures**: Use proper async fixtures for database sessions and HTTP clients
3. **UUID String Validation**: Verify API responses return UUID strings, not objects
4. **Multi-Tenant Isolation**: Test that workspace isolation prevents cross-tenant access
5. **Performance Benchmarks**: Include basic performance tests for critical endpoints

### Error Testing
1. **Authentication Errors**: Test expired tokens and invalid credentials
2. **Authorization Errors**: Test cross-tenant access attempts
3. **Validation Errors**: Test invalid input data handling
4. **Database Errors**: Test behavior when database is unavailable

### Environment Testing
1. **Docker Configuration**: Verify environment variables and container health
2. **Database Connections**: Test connection pooling and async session handling
3. **Service Dependencies**: Test behavior when external services are unavailable

---

*This document provides practical testing patterns for async FastAPI applications with focus on multi-tenant architecture validation and performance testing.*