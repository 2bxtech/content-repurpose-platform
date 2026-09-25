"""
Upload endpoint behaviour, in-process.

Auth, workspace context and the DB session are overridden (see `unit_client`), so
the route uses its in-memory fallback. The file processor is the real one unless a
test swaps it, which exercises validation end to end without Postgres.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.routes import documents as documents_route
from app.core.config import settings
from app.models.documents import DocumentStatus

pytestmark = pytest.mark.unit

TEXT = b"This is a test document.\nIt has a couple of lines of content.\n"


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Keep uploads and the in-memory document store per-test."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(documents_route, "DOCUMENTS_DB", [])


def _upload(client, filename="test.txt", body=TEXT, content_type="text/plain", title="Test Document"):
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, body, content_type)},
        data={"title": title, "description": "Test document description"},
    )


def test_upload_document_success(unit_client, fake_user):
    response = _upload(unit_client)

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["title"] == "Test Document"
    assert result["description"] == "Test document description"
    assert result["original_filename"] == "test.txt"
    assert result["content_type"] == "text/plain"
    assert result["status"] == DocumentStatus.COMPLETED.value
    assert result["user_id"] == fake_user["id"]
    assert "id" in result


def test_upload_invalid_file_type(unit_client):
    response = _upload(unit_client, "test.exe", b"MZ\x90\x00", "application/x-msdownload")

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_mismatched_mime_type(unit_client):
    response = _upload(unit_client, "test.pdf", TEXT, "text/plain")
    assert response.status_code == 400


@pytest.mark.xfail(
    reason="bug: upload route's `except Exception` turns its own 400 HTTPException into a 500",
    strict=True,
)
def test_upload_security_scan_failure(unit_client, tmp_path):
    """An executable disguised as a .txt is rejected and its temp file removed"""
    response = _upload(unit_client, "malicious.txt", b"MZ\x90\x00 not really text")

    assert response.status_code == 400
    assert "File failed security validation" in response.json()["detail"]
    assert list(tmp_path.glob("*malicious.txt")) == []


@pytest.mark.xfail(
    reason="bug: upload route's `except Exception` turns its own 400 HTTPException into a 500",
    strict=True,
)
def test_upload_security_scan_failure_from_processor(unit_client):
    """The route trusts the processor's verdict"""
    rejected = SimpleNamespace(security_scan_passed=False)
    with patch.object(documents_route.file_processor, "process_file", AsyncMock(return_value=rejected)):
        response = _upload(unit_client)

    assert response.status_code == 400
    assert "File failed security validation" in response.json()["detail"]


def test_upload_large_file(unit_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 1024)

    response = _upload(unit_client, body=b"x" * 2048)

    assert response.status_code == 400
    assert "File too large" in response.json()["detail"]


def test_upload_empty_file(unit_client):
    response = _upload(unit_client, body=b"")

    assert response.status_code == 400
    assert "Empty file" in response.json()["detail"]


def test_get_documents_after_upload(unit_client):
    upload_response = _upload(unit_client)
    assert upload_response.status_code == 201

    get_response = unit_client.get("/api/documents")
    assert get_response.status_code == 200

    result = get_response.json()
    assert result["count"] == 1
    assert result["documents"][0]["title"] == "Test Document"

    content = unit_client.get(f"/api/documents/{upload_response.json()['id']}/content")
    assert content.status_code == 200
    assert "couple of lines" in content.json()["extracted_text"]


def test_upload_requires_authentication():
    from fastapi.testclient import TestClient

    from main import app

    response = TestClient(app).post(
        "/api/documents/upload",
        files={"file": ("test.txt", TEXT, "text/plain")},
        data={"title": "Anonymous"},
    )
    assert response.status_code == 401
