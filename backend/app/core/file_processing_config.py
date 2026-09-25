"""
Phase 6: File Processing Enhancement Configuration

Configuration settings for enhanced file processing features.
"""

from typing import Dict, List, Set
from pydantic import BaseModel, Field


class FileProcessingConfig(BaseModel):
    """Configuration for file processing features"""

    # File size limits
    max_file_size_mb: int = Field(default=10, description="Maximum file size in MB")
    max_preview_generation_size_mb: int = Field(
        default=50, description="Max size for preview generation"
    )

    # Security settings
    enable_security_scanning: bool = Field(
        default=True, description="Enable security scanning"
    )
    enable_virus_scanning: bool = Field(
        default=False, description="Enable ClamAV virus scanning"
    )
    block_suspicious_patterns: bool = Field(
        default=True, description="Block files with suspicious patterns"
    )

    # Processing settings
    pdf_extraction_method: str = Field(
        default="hybrid", description="PDF extraction method: hybrid, pymupdf, pypdf2"
    )
    enable_preview_generation: bool = Field(
        default=True, description="Enable document preview generation"
    )
    preview_image_size: tuple = Field(
        default=(400, 300), description="Preview image dimensions"
    )
    preview_dpi: int = Field(default=150, description="Preview image DPI")

    # Content analysis
    enable_content_analysis: bool = Field(
        default=True, description="Enable content format detection"
    )
    max_text_preview_chars: int = Field(
        default=500, description="Max characters for text preview"
    )

    # Supported file types with MIME mappings
    supported_file_types: Dict[str, List[str]] = Field(
        default={
            "pdf": ["application/pdf"],
            "docx": [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.ms-word.document.macroEnabled.12",
                "application/octet-stream",
            ],
            "txt": ["text/plain", "text/txt"],
            "md": ["text/markdown", "text/plain", "text/x-markdown"],
        },
        description="Supported file extensions and their valid MIME types",
    )

    # Dangerous file signatures to block
    dangerous_signatures: Dict[str, str] = Field(
        default={
            "MZ": "Windows Executable",
            "7F454C46": "Linux Executable",
            "504B0304": "ZIP Archive (potential threat)",
        },
        description="Dangerous file signatures (hex) and descriptions",
    )

    # Malicious patterns to detect
    malicious_patterns: List[str] = Field(
        default=[
            "<script",
            "javascript:",
            "vbscript:",
            "onload=",
            "onclick=",
            "eval(",
            "exec(",
            "system(",
            "shell_exec",
            "base64_decode",
        ],
        description="Patterns to detect in file content",
    )

    # Preview generation settings
    preview_fonts: List[str] = Field(
        default=["arial.ttf", "DejaVuSans.ttf", "liberation-sans.ttf"],
        description="Preferred fonts for preview generation",
    )

    # Performance settings
    enable_parallel_processing: bool = Field(
        default=False, description="Enable parallel file processing"
    )
    max_processing_time_seconds: int = Field(
        default=300, description="Max processing time per file"
    )

    class Config:
        extra = "forbid"


# Default configuration instance
file_processing_config = FileProcessingConfig()


# Phase 6 feature flags
class Phase6Features:
    """Feature flags for Phase 6 capabilities"""

    ENHANCED_PDF_EXTRACTION = "enhanced_pdf_extraction"
    COMPREHENSIVE_DOCX_PROCESSING = "comprehensive_docx_processing"
    SECURITY_VALIDATION = "security_validation"
    PREVIEW_GENERATION = "preview_generation"
    METADATA_EXTRACTION = "metadata_extraction"
    FILE_DEDUPLICATION = "file_deduplication"
    CONTENT_ENCODING_DETECTION = "content_encoding_detection"
    VIRUS_SCANNING = "virus_scanning"

    @classmethod
    def get_all_features(cls) -> Set[str]:
        """Get all available Phase 6 features"""
        return {
            value
            for name, value in cls.__dict__.items()
            if not name.startswith("_") and isinstance(value, str)
        }

    @classmethod
    def get_enabled_features(cls) -> Dict[str, bool]:
        """Get current feature enablement status"""
        config = file_processing_config
        return {
            cls.ENHANCED_PDF_EXTRACTION: True,  # Always enabled
            cls.COMPREHENSIVE_DOCX_PROCESSING: True,  # Always enabled
            cls.SECURITY_VALIDATION: config.enable_security_scanning,
            cls.PREVIEW_GENERATION: config.enable_preview_generation,
            cls.METADATA_EXTRACTION: True,  # Always enabled
            cls.FILE_DEDUPLICATION: True,  # Always enabled
            cls.CONTENT_ENCODING_DETECTION: True,  # Always enabled
            cls.VIRUS_SCANNING: config.enable_virus_scanning,
        }


# File processing statistics
class FileProcessingStats(BaseModel):
    """Statistics for file processing operations"""

    total_files_processed: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    security_violations_blocked: int = 0
    previews_generated: int = 0
    duplicate_files_detected: int = 0

    # Processing time statistics
    avg_processing_time_ms: float = 0.0
    max_processing_time_ms: float = 0.0
    min_processing_time_ms: float = 0.0

    # File type statistics
    pdf_files_processed: int = 0
    docx_files_processed: int = 0
    text_files_processed: int = 0

    def add_processing_result(
        self, file_type: str, processing_time_ms: float, success: bool
    ):
        """Add a processing result to statistics"""
        self.total_files_processed += 1

        if success:
            self.successful_extractions += 1
        else:
            self.failed_extractions += 1

        # Update processing time stats
        if self.total_files_processed == 1:
            self.avg_processing_time_ms = processing_time_ms
            self.max_processing_time_ms = processing_time_ms
            self.min_processing_time_ms = processing_time_ms
        else:
            self.avg_processing_time_ms = (
                self.avg_processing_time_ms * (self.total_files_processed - 1)
                + processing_time_ms
            ) / self.total_files_processed
            self.max_processing_time_ms = max(
                self.max_processing_time_ms, processing_time_ms
            )
            self.min_processing_time_ms = min(
                self.min_processing_time_ms, processing_time_ms
            )

        # Update file type stats
        if file_type == "pdf":
            self.pdf_files_processed += 1
        elif file_type == "docx":
            self.docx_files_processed += 1
        elif file_type in ["txt", "md"]:
            self.text_files_processed += 1


# Global statistics instance
file_processing_stats = FileProcessingStats()
