"""
Simplified test configuration that assumes Docker containers are already running.
No complex Docker client dependencies - just HTTP requests.
"""

import os
from types import SimpleNamespace
import pytest
import httpx
from typing import AsyncGenerator

os.environ["ENVIRONMENT"] = "testing"
# Unit tests import app.core.config, which requires signing keys; use throwaway values.
os.environ.setdefault("SECRET_KEY", "test-only-access-signing-key-0123456789abcdef")
os.environ.setdefault("REFRESH_SECRET_KEY", "test-only-refresh-signing-key-0123456789abcdef")
if not os.getenv("TEST_API_URL"):
    # Unit mode: in-process TestClient apps must never reach a developer's local Postgres
    # (the default component config points at localhost:5433). Port 9 is unreachable.
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://unit:unit@127.0.0.1:9/unit_tests"
os.environ["DEBUG"] = "true"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"


@pytest.fixture
def mock_ai_provider():
    provider = SimpleNamespace(call_count=0)

    def generate_completion(*_args, **_kwargs):
        provider.call_count += 1
        return "mock completion"

    provider.generate_completion = generate_completion
    provider.generate_summary = generate_completion
    provider.generate_blog_post = generate_completion
    return provider

# Test configuration
# Integration tests only run when TEST_API_URL is set explicitly (make test-integration),
# so a plain `pytest` never writes to whatever happens to be listening on :8000.
TEST_API_URL = os.getenv("TEST_API_URL")
TEST_DB_URL = (
    "postgresql://postgres:test_password@localhost:5434/content_repurpose_test"
)
TEST_REDIS_URL = "redis://localhost:6380"


@pytest.fixture(scope="function", autouse=False)  # Changed to function scope
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Simple HTTP client for API testing.
    Targets TEST_API_URL; skipped when it is unset.
    
    Note: Tests must explicitly request this fixture to use it.
    Schema validation tests don't request it, so they won't try to connect to API.
    """
    if not TEST_API_URL:
        pytest.skip("Integration test: set TEST_API_URL or run `make test-integration`")
    timeout = httpx.Timeout(30.0)

    async with httpx.AsyncClient(
        base_url=TEST_API_URL,
        timeout=timeout,
    ) as client:
        # Verify API is accessible
        try:
            response = await client.get("/api/health")
        except httpx.TransportError as e:
            # TEST_API_URL was set on purpose, so an unreachable API is a failure, not a skip.
            pytest.fail(f"Cannot reach test API at {TEST_API_URL}: {e}")
        if response.status_code != 200:
            pytest.fail(f"API health check failed: {response.status_code}")

        yield client


@pytest.fixture(scope="function")  # Changed to function scope
async def authenticated_client(
    api_client: httpx.AsyncClient,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    API client with authentication token.
    """
    # Create test user and get token with unique email for each test
    import uuid
    test_id = str(uuid.uuid4())[:8]
    test_user = {
        "username": f"testuser_{test_id}",
        "email": f"test_{test_id}@example.com",
        "password": "TestPassword123!",  # Must meet password requirements
    }

    # Register user
    register_resp = await api_client.post("/api/auth/register", json=test_user)
    if register_resp.status_code != 201:
        pytest.fail(f"Failed to register test user: {register_resp.status_code} - {register_resp.text}")

    # Login to get token (using /token endpoint with form data)
    # OAuth2 username field should contain the email
    login_data = {"username": test_user["email"], "password": test_user["password"]}

    # OAuth2 requires form-urlencoded, not JSON
    response = await api_client.post(
        "/api/auth/token", 
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    if response.status_code != 200:
        try:
            error_detail = response.json()
            pytest.fail(f"Failed to authenticate test user: {response.status_code} - {error_detail}")
        except Exception:
            pytest.fail(f"Failed to authenticate test user: {response.status_code}")

    token_data = response.json()
    access_token = token_data["access_token"]

    # Create new client with auth header
    api_client.headers.update({"Authorization": f"Bearer {access_token}"})

    yield api_client


@pytest.fixture(autouse=False)  # Changed to False - only runs when explicitly needed
async def cleanup_test_data(api_client: httpx.AsyncClient):
    """
    Clean up test data before and after each test.
    This assumes your API has cleanup endpoints or test workspace isolation.
    
    Note: Tests must explicitly request this fixture to enable auto-cleanup.
    """
    # Setup: Clean before test
    yield
    # Teardown: Clean after test (if needed)
    pass


# Test data fixtures
@pytest.fixture
def sample_text():
    """Sample text for transformation tests."""
    return "This is a sample text for testing content transformation features."


@pytest.fixture
def sample_transformation_config():
    """Sample transformation configuration."""
    return {
        "target_platform": "linkedin",
        "content_type": "post",
        "tone": "professional",
        "length": "medium",
    }


# Mock fixtures for AI services
@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    return {
        "choices": [
            {
                "message": {
                    "content": "This is a professional LinkedIn post created from your content."
                }
            }
        ]
    }


@pytest.fixture
def mock_anthropic_response():
    """Mock Anthropic API response."""
    return {
        "content": [{"text": "This is content transformed using Anthropic's Claude."}]
    }
