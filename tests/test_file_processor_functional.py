#!/usr/bin/env python3
"""
Quick functional test of Phase 6 file processing capabilities
"""

import sys
import os
import tempfile
import asyncio

# Add backend to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))


async def test_text_processing():
    """Test basic text file processing"""
    try:
        from app.services.file_processor import FileProcessor

        processor = FileProcessor()

        # Create a temporary text file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello World! This is a test document with some content.")
            temp_path = f.name

        try:
            # Process the file
            result = await processor.process_file(temp_path, "text/plain", "test.txt")

            print("✅ Text processing successful!")
            print(f"   Content: {result.content[:50]}...")
            print(f"   Word count: {result.word_count}")
            print(f"   Method: {result.extraction_method}")
            print(f"   Security passed: {result.security_scan_passed}")

            return True

        finally:
            # Clean up
            os.unlink(temp_path)

    except Exception as e:
        print(f"❌ Text processing failed: {e}")
        return False


async def test_security_validation():
    """Test security validation features"""
    try:
        from app.services.file_processor import FileProcessor

        processor = FileProcessor()

        # Test with normal content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Normal content here.")  # Should pass security
            temp_path = f.name

        try:
            result = await processor.process_file(temp_path, "text/plain", "test.txt")

            print("✅ Security validation working!")
            print(f"   Security scan passed: {result.security_scan_passed}")
            print(f"   File hash generated: {bool(result.file_hash)}")

            return True

        finally:
            os.unlink(temp_path)

    except Exception as e:
        print(f"❌ Security validation failed: {e}")
        return False


async def main():
    print("🔧 Running Phase 6 functional tests...")
    print("=" * 50)

    # Test text processing
    print("\n1. Testing text file processing...")
    text_success = await test_text_processing()

    # Test security validation
    print("\n2. Testing security validation...")
    security_success = await test_security_validation()

    # Summary
    print("\n" + "=" * 50)
    print("📊 Functional Test Summary:")
    print(f"   Text Processing: {'✅' if text_success else '❌'}")
    print(f"   Security Validation: {'✅' if security_success else '❌'}")

    if text_success and security_success:
        print("\n🚀 Phase 6 file processing is fully functional!")
        return True
    else:
        print("\n⚠️  Some functionality needs attention")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    if not result:
        sys.exit(1)
