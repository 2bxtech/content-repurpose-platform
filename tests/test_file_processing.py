"""
File Processing Tests

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


class TestFileProcessor:
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

    @staticmethod
    async def _process(processor, name, content, content_type="text/plain"):
        path = processor.upload_dir / name
        path.write_bytes(content)
        return await processor.process_file(str(path), content_type, name)

    @pytest.mark.asyncio
    async def test_file_size_validation(self, file_processor):
        """Oversized and empty files are rejected by process_file"""
        result = await self._process(file_processor, "normal.txt", b"normal content " * 100)
        assert result.security_scan_passed is True

        large = await self._process(file_processor, "large.txt", b"x" * (11 * 1024 * 1024))
        assert large.security_scan_passed is False
        assert "File too large" in large.metadata["error"]

        empty = await self._process(file_processor, "empty.txt", b"")
        assert empty.security_scan_passed is False
        assert "Empty file not allowed" in empty.metadata["error"]

    @pytest.mark.asyncio
    async def test_file_type_validation(self, file_processor):
        """Unsupported extensions and executable signatures are rejected"""
        ok = await self._process(file_processor, "test.txt", b"plain text content")
        assert ok.security_scan_passed is True

        exe = await self._process(file_processor, "test.exe", b"MZ", "application/octet-stream")
        assert exe.security_scan_passed is False
        assert "Unsupported file type" in exe.metadata["error"]

        # A PE header disguised as a .txt file
        disguised = await self._process(file_processor, "test.txt", b"MZ\x90\x00 payload")
        assert disguised.security_scan_passed is False
        assert "Dangerous file signature" in disguised.metadata["error"]

    @pytest.mark.asyncio
    async def test_security_scan_basic(self, file_processor, malicious_content):
        """Script-like text is logged but not rejected: text documents are stored and
        rendered as plain text, so the scan only blocks executables (see _validate_file_security)."""
        clean = await self._process(
            file_processor, "clean.txt", b"This is clean content without any suspicious patterns."
        )
        assert clean.security_scan_passed is True

        scripted = await self._process(file_processor, "script.txt", malicious_content)
        assert scripted.security_scan_passed is True
        assert "<script>" in scripted.content

    @pytest.mark.asyncio
    async def test_text_processing_enhanced(self, file_processor, sample_text_content):
        """Test text extraction and metadata"""
        result = await self._process(file_processor, "sample.txt", sample_text_content)

        assert isinstance(result, ProcessingResult)
        assert result.security_scan_passed is True
        assert "sample text file" in result.content.lower()
        assert result.word_count > 0
        assert result.metadata["line_count"] == 3
        assert result.metadata["extraction_method"] == "text"
        assert len(result.file_hash) == 64
        # chardet reports pure-ASCII input as "ascii" (a subset of utf-8)
        assert result.content_encoding in ["ascii", "utf-8", "utf-8 (with replacements)"]

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


class TestContentSniffing:
    """The bytes must match the extension; needs libmagic (skipped where it's absent)."""

    @pytest.fixture(autouse=True)
    def _require_magic(self):
        from app.services import file_processor as fp

        if not fp.HAS_MAGIC:
            pytest.skip("libmagic not available")

    @pytest.fixture
    def processor(self):
        return FileProcessor()

    async def test_real_pdf_is_accepted(self, processor):
        import fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "A genuine PDF")
        await processor._validate_file_security(doc.tobytes(), "report.pdf")

    async def test_script_renamed_to_pdf_is_rejected(self, processor):
        script = b"#!/bin/sh\necho not really a pdf\n"
        with pytest.raises(ValueError, match="doesn't match its .pdf extension"):
            await processor._validate_file_security(script, "report.pdf")
