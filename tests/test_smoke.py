"""
Simple smoke tests to verify testing framework setup
"""

import pytest
import sys
import os


class TestFrameworkSetup:
    """Basic tests to verify testing framework is working"""

    @pytest.mark.unit
    def test_python_version(self):
        """Test that we have a compatible Python version"""
        assert sys.version_info >= (3, 8), "Python 3.8+ is required"

    @pytest.mark.unit
    def test_project_structure(self):
        """Test that we have the expected project structure"""
        # Check that we're in the right directory
        project_root = os.path.dirname(os.path.dirname(__file__))

        expected_files = [
            "backend/main.py",
            "backend/requirements.txt",
            "docker-compose.yml",
            "docker-compose.test.yml",
        ]

        for file_path in expected_files:
            full_path = os.path.join(project_root, file_path)
            assert os.path.exists(full_path), f"Expected file not found: {file_path}"

    @pytest.mark.unit
    def test_test_dependencies(self):
        """Test that required test dependencies are available"""
        required_modules = ["pytest", "httpx", "asyncio"]

        for module_name in required_modules:
            try:
                __import__(module_name)
            except ImportError:
                pytest.fail(f"Required test dependency not available: {module_name}")

    @pytest.mark.unit
    async def test_async_support(self):
        """Test that async test support is working"""
        import asyncio

        # Simple async operation
        result = await asyncio.sleep(0.1, result="async_works")
        assert result == "async_works"

    @pytest.mark.unit
    def test_environment_variables(self):
        """Test that test environment variables are set correctly"""
        # These should be set by conftest.py
        expected_env_vars = {
            "ENVIRONMENT": "testing",
            "DEBUG": "true",
            "CELERY_TASK_ALWAYS_EAGER": "true",
        }

        for var_name, expected_value in expected_env_vars.items():
            actual_value = os.environ.get(var_name)
            assert actual_value == expected_value, (
                f"Environment variable {var_name} should be '{expected_value}', got '{actual_value}'"
            )


class TestMockServices:
    """Test that mock services work correctly"""

    @pytest.mark.unit
    def test_mock_auth_service(self):
        """Test that mock auth service works as expected"""
        from tests.test_auth import MockAuthService

        auth_service = MockAuthService()

        # Test password validation
        with pytest.raises(ValueError):
            auth_service.validate_password_strength("weak")

        # Strong password should not raise
        auth_service.validate_password_strength("StrongPassword123!")

        # Test token creation and verification
        user_data = {"user_id": "test", "email": "test@example.com"}
        token = auth_service.create_access_token(user_data)
        assert token == "mock-jwt-token"

        decoded = auth_service.verify_access_token(token)
        assert decoded["user_id"] == "test-user-id"

    @pytest.mark.unit
    def test_mock_ai_provider(self, mock_ai_provider):
        """Test that mock AI provider fixture works"""
        assert hasattr(mock_ai_provider, "generate_completion")
        assert hasattr(mock_ai_provider, "generate_summary")
        assert hasattr(mock_ai_provider, "generate_blog_post")

        # Test call counting
        initial_count = mock_ai_provider.call_count
        mock_ai_provider.generate_completion("test prompt")
        assert mock_ai_provider.call_count == initial_count + 1
