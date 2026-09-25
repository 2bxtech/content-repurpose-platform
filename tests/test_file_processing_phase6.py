"""
Phase 6: File Processing Enhancement Tests

Tests for robust PDF/DOCX parsing, security validation, and preview generation.
These are UNIT tests that test the file processor directly without requiring
a running API server.
"""

import pytest
import os
import tempfile
import sys

# Add backend to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.file_processor import FileProcessor, ProcessingResult


class TestFileProcessorPhase6:
    """Test the enhanced file processor"""

    @pytest.fixture
    def file_processor(self):
        """Create a file processor instance for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            processor = FileProcessor(upload_dir=temp_dir)
            yield processor

    @pytest.fixture
    def sample_text_content(self):
        return b"This is a sample text file.\nIt has multiple lines.\nAnd some content for testing."

    @pytest.fixture
    def malicious_content(self):
        return b"<script>alert('xss')</script>\nSome normal content\njavascript:void(0)"

    def test_file_size_validation(self, file_processor):
        """Test file size validation"""
        # Test normal size
        normal_content = b"normal content" * 100
        file_processor._validate_file_size(normal_content)  # Should not raise

        # Test oversized file
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        with pytest.raises(ValueError, match="File too large"):
            file_processor._validate_file_size(large_content)

        # Test empty file
        with pytest.raises(ValueError, match="Empty file not allowed"):
            file_processor._validate_file_size(b"")

    def test_file_type_validation(self, file_processor):
        """Test file type validation"""
        # Test valid file types
        file_processor._validate_file_type("test.pdf", b"%PDF-1.4")  # Should not raise
        file_processor._validate_file_type(
            "test.txt", b"plain text content"
        )  # Should not raise

        # Test invalid extension
        with pytest.raises(ValueError, match="Unsupported file type"):
            file_processor._validate_file_type("test.exe", b"MZ")

        # Test dangerous signatures
        with pytest.raises(ValueError, match="Dangerous file signature"):
            file_processor._validate_file_type(
                "test.pdf", b"MZ\x90\x00"
            )  # PE signature

    def test_security_scan_basic(self, file_processor, malicious_content):
        """Test basic security scanning"""
        # Test clean content
        clean_content = b"This is clean content without any suspicious patterns."
        result = file_processor._security_scan(clean_content, "test.txt")
        assert result["is_safe"] is True
        assert len(result["threats_detected"]) == 0

        # Test malicious content
        with pytest.raises(ValueError, match="Security scan failed"):
            file_processor._security_scan(malicious_content, "test.txt")

    @pytest.mark.asyncio
    async def test_text_processing_enhanced(self, file_processor, sample_text_content):
        """Test enhanced text processing"""
        result = await file_processor._process_text_enhanced("", sample_text_content)

        assert isinstance(result, ProcessingResult)
        assert "sample text file" in result.content.lower()
        assert result.word_count > 0
        assert result.metadata["line_count"] == 3
        assert result.metadata["extraction_method"] == "text"
        assert result.content_encoding in ["utf-8", "utf-8 (with replacements)"]

    def test_file_hash_generation(self, file_processor):
        """Test file hash generation for deduplication"""
        content1 = b"identical content"
        content2 = b"identical content"
        content3 = b"different content"

        hash1 = file_processor._generate_file_hash(content1)
        hash2 = file_processor._generate_file_hash(content2)
        hash3 = file_processor._generate_file_hash(content3)

        assert hash1 == hash2  # Same content should have same hash
        assert hash1 != hash3  # Different content should have different hash
        assert len(hash1) == 64  # SHA-256 produces 64-character hex string

    def test_validate_file_type_method(self, file_processor):
        """Test the public validate_file_type method"""
        # Valid combinations
        assert file_processor.validate_file_type("text/plain", "test.txt") is True
        assert file_processor.validate_file_type("application/pdf", "test.pdf") is True
        assert (
            file_processor.validate_file_type(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "test.docx",
            )
            is True
        )

        # Invalid combinations
        assert file_processor.validate_file_type("text/plain", "test.pdf") is False
        assert file_processor.validate_file_type("application/pdf", "test.txt") is False
        assert (
            file_processor.validate_file_type("image/jpeg", "test.jpg") is False
        )  # Not supported


# Standalone tests that don't require API server
class TestFileProcessorStandalone:
    """Standalone file processor tests"""

    def test_imports_work(self):
        """Test that we can import the file processor without errors"""
        try:
            from app.services.file_processor import FileProcessor, ProcessingResult

            assert FileProcessor is not None
            assert ProcessingResult is not None
        except ImportError as e:
            pytest.skip(f"Cannot import file processor: {e}")

    def test_basic_functionality(self):
        """Test basic file processor functionality"""
        try:
            from app.services.file_processor import FileProcessor

            processor = FileProcessor(upload_dir=tempfile.gettempdir())

            # Test hash generation
            hash1 = processor._generate_file_hash(b"test content")
            hash2 = processor._generate_file_hash(b"test content")
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA-256

        except ImportError as e:
            pytest.skip(f"Cannot import file processor: {e}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
