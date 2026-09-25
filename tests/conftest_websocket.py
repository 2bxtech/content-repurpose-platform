"""
Phase 5 WebSocket Testing Framework
Extends existing pytest framework with WebSocket-specific tests
"""

import pytest
import asyncio
import json
from typing import Dict, Any
import websockets
import httpx
from datetime import datetime


@pytest.fixture(scope="session")
def websocket_url():
    """WebSocket connection URL for testing"""
    return "ws://localhost:8000/api/ws"


@pytest.fixture(scope="session")
async def test_workspace_id(authenticated_client: httpx.AsyncClient) -> str:
    """Create or get a test workspace for WebSocket testing"""
    workspace_data = {
        "name": f"Test Workspace {datetime.now().isoformat()}",
        "description": "WebSocket testing workspace",
    }

    response = await authenticated_client.post("/api/workspaces", json=workspace_data)

    if response.status_code == 201:
        workspace = response.json()
        return str(workspace["id"])
    else:
        # Use default workspace if creation fails
        response = await authenticated_client.get("/api/workspaces")
        workspaces = response.json()
        if workspaces["workspaces"]:
            return str(workspaces["workspaces"][0]["id"])
        else:
            pytest.fail("No test workspace available")


@pytest.fixture
async def websocket_client(
    authenticated_client: httpx.AsyncClient, websocket_url: str, test_workspace_id: str
):
    """WebSocket client with authentication"""
    # Extract token from authenticated client
    auth_header = authenticated_client.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        pytest.fail("No authentication token available")

    token = auth_header[7:]  # Remove "Bearer " prefix

    # Build WebSocket URL with auth
    ws_url_with_auth = f"{websocket_url}?token={token}&workspace_id={test_workspace_id}"

    # Connect to WebSocket
    try:
        websocket = await websockets.connect(ws_url_with_auth)
        yield websocket
        await websocket.close()
    except Exception as e:
        pytest.fail(f"Failed to connect to WebSocket: {e}")


@pytest.fixture
async def mock_transformation_task(
    authenticated_client: httpx.AsyncClient, test_workspace_id: str
):
    """Create a mock transformation for testing real-time updates"""
    # First create a document
    document_data = {
        "title": "Test Document for WebSocket",
        "content": "This is test content for WebSocket transformation testing.",
        "file_type": "text/plain",
    }

    doc_response = await authenticated_client.post("/api/documents", json=document_data)
    if doc_response.status_code != 201:
        pytest.fail(f"Failed to create test document: {doc_response.status_code}")

    document = doc_response.json()

    # Create transformation
    transformation_data = {
        "document_id": document["id"],
        "transformation_type": "blog_post",
        "parameters": {"tone": "professional", "word_count": 300},
    }

    transform_response = await authenticated_client.post(
        "/api/transformations", json=transformation_data
    )
    if transform_response.status_code != 201:
        pytest.fail(
            f"Failed to create transformation: {transform_response.status_code}"
        )

    transformation = transform_response.json()

    yield {
        "document": document,
        "transformation": transformation,
        "workspace_id": test_workspace_id,
    }

    # Cleanup
    try:
        await authenticated_client.delete(
            f"/api/transformations/{transformation['id']}"
        )
        await authenticated_client.delete(f"/api/documents/{document['id']}")
    except:
        pass  # Cleanup failure is not critical


class WebSocketTestHelper:
    """Helper class for WebSocket testing operations"""

    @staticmethod
    async def send_and_wait_for_response(
        websocket,
        message: Dict[str, Any],
        expected_type: str = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """Send message and wait for specific response type"""
        await websocket.send(json.dumps(message))

        start_time = asyncio.get_event_loop().time()

        while True:
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise asyncio.TimeoutError(
                    f"No response of type '{expected_type}' received within {timeout}s"
                )

            try:
                response_raw = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                response = json.loads(response_raw)

                if expected_type is None or response.get("type") == expected_type:
                    return response

            except asyncio.TimeoutError:
                continue
            except json.JSONDecodeError:
                continue

    @staticmethod
    async def wait_for_message_type(
        websocket, message_type: str, timeout: float = 10.0
    ) -> Dict[str, Any]:
        """Wait for a specific message type"""
        start_time = asyncio.get_event_loop().time()

        while True:
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise asyncio.TimeoutError(
                    f"No message of type '{message_type}' received within {timeout}s"
                )

            try:
                response_raw = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                response = json.loads(response_raw)

                if response.get("type") == message_type:
                    return response

            except asyncio.TimeoutError:
                continue
            except json.JSONDecodeError:
                continue


@pytest.fixture
def ws_helper():
    """WebSocket test helper instance"""
    return WebSocketTestHelper()
