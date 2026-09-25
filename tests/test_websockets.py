"""
Test suite for Phase 5 WebSocket functionality
Systematic testing of real-time features and WebSocket infrastructure
"""

import pytest
import asyncio
import json
import uuid
import websockets
from datetime import datetime


class TestWebSocketInfrastructure:
    """Test core WebSocket infrastructure"""

    @pytest.mark.asyncio
    async def test_websocket_connection_establishment(self, websocket_client):
        """Test basic WebSocket connection and welcome message"""
        # Wait for welcome message
        welcome_raw = await asyncio.wait_for(websocket_client.recv(), timeout=5.0)
        welcome = json.loads(welcome_raw)

        assert welcome["type"] == "connection_established"
        assert "connection_id" in welcome["data"]
        assert "user_id" in welcome["data"]
        assert "workspace_id" in welcome["data"]

    @pytest.mark.asyncio
    async def test_websocket_ping_pong(self, websocket_client, ws_helper):
        """Test WebSocket heartbeat mechanism"""
        # Send ping
        ping_message = {
            "type": "ping",
            "data": {"timestamp": datetime.utcnow().isoformat()},
        }

        # Wait for pong response
        pong = await ws_helper.send_and_wait_for_response(
            websocket_client, ping_message, "pong", timeout=5.0
        )

        assert pong["type"] == "pong"
        assert "timestamp" in pong["data"]

    @pytest.mark.asyncio
    async def test_workspace_presence(self, websocket_client, ws_helper):
        """Test workspace presence functionality"""
        # Request workspace presence
        presence_request = {"type": "get_workspace_presence", "data": {}}

        # Wait for presence response
        presence = await ws_helper.send_and_wait_for_response(
            websocket_client, presence_request, "workspace_presence", timeout=5.0
        )

        assert presence["type"] == "workspace_presence"
        assert "workspace_id" in presence["data"]
        assert "users" in presence["data"]
        assert isinstance(presence["data"]["users"], list)

    @pytest.mark.asyncio
    async def test_workspace_message_broadcasting(self, websocket_client, ws_helper):
        """Test workspace message broadcasting"""
        # Send workspace message
        test_message = {
            "type": "workspace_message",
            "data": {"message": "Test broadcast message", "test_id": str(uuid.uuid4())},
        }

        await websocket_client.send(json.dumps(test_message))

        # Should receive the broadcasted message back
        response = await ws_helper.wait_for_message_type(
            websocket_client, "workspace_message", timeout=5.0
        )

        assert response["type"] == "workspace_message"
        assert response["data"]["message"] == "Test broadcast message"


class TestRealTimeTransformations:
    """Test real-time transformation progress updates"""

    @pytest.mark.asyncio
    async def test_transformation_progress_updates(
        self,
        websocket_client,
        mock_transformation_task,
        ws_helper,
        authenticated_client,
    ):
        """Test that transformation progress is sent via WebSocket"""
        transformation = mock_transformation_task["transformation"]
        transformation_id = transformation["id"]

        # Listen for transformation updates
        update_messages = []

        # Collect transformation messages for 10 seconds
        start_time = asyncio.get_event_loop().time()
        timeout = 10.0

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                message_raw = await asyncio.wait_for(
                    websocket_client.recv(), timeout=1.0
                )
                message = json.loads(message_raw)

                if (
                    message.get("type")
                    in [
                        "transformation_started",
                        "transformation_progress",
                        "transformation_completed",
                        "transformation_failed",
                    ]
                    and message["data"].get("transformation_id") == transformation_id
                ):
                    update_messages.append(message)

                    # If we get completion, break early
                    if message.get("type") in [
                        "transformation_completed",
                        "transformation_failed",
                    ]:
                        break

            except asyncio.TimeoutError:
                continue
            except json.JSONDecodeError:
                continue

        # Verify we received transformation updates
        assert len(update_messages) > 0, (
            "No transformation updates received via WebSocket"
        )

        # Check for expected message types
        message_types = [msg["type"] for msg in update_messages]

        # Should have at least one progress-related message
        progress_types = [
            "transformation_started",
            "transformation_progress",
            "transformation_completed",
            "transformation_failed",
        ]

        assert any(msg_type in progress_types for msg_type in message_types), (
            f"No transformation progress messages found. Got: {message_types}"
        )


class TestWebSocketAPI:
    """Test WebSocket-related HTTP API endpoints"""

    @pytest.mark.asyncio
    async def test_websocket_stats_endpoint(self, authenticated_client):
        """Test WebSocket statistics endpoint"""
        response = await authenticated_client.get("/api/ws/stats")

        assert response.status_code == 200

        stats = response.json()
        assert "websocket_stats" in stats
        assert "total_connections" in stats["websocket_stats"]
        assert "unique_users" in stats["websocket_stats"]
        assert "active_workspaces" in stats["websocket_stats"]

    @pytest.mark.asyncio
    async def test_websocket_broadcast_api(self, authenticated_client):
        """Test HTTP broadcast API for server-side messaging"""
        broadcast_data = {
            "type": "test_broadcast",
            "data": {
                "message": "Test API broadcast",
                "timestamp": datetime.utcnow().isoformat(),
            },
            "target": "broadcast",
        }

        response = await authenticated_client.post(
            "/api/ws/broadcast", json=broadcast_data
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "message_sent"
        assert result["type"] == "test_broadcast"


class TestWebSocketErrorHandling:
    """Test WebSocket error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_invalid_message_format(self, websocket_client):
        """Test handling of invalid JSON messages"""
        # Send invalid JSON
        await websocket_client.send("invalid json {")

        # Should receive error response
        error_raw = await asyncio.wait_for(websocket_client.recv(), timeout=5.0)
        error = json.loads(error_raw)

        assert error["type"] == "error"
        assert "Invalid JSON format" in error["data"]["message"]

    @pytest.mark.asyncio
    async def test_unknown_message_type(self, websocket_client):
        """Test handling of unknown message types"""
        unknown_message = {"type": "unknown_message_type", "data": {"test": "data"}}

        await websocket_client.send(json.dumps(unknown_message))

        # Should receive error response
        error_raw = await asyncio.wait_for(websocket_client.recv(), timeout=5.0)
        error = json.loads(error_raw)

        assert error["type"] == "error"
        assert "Unknown message type" in error["data"]["message"]


class TestWebSocketAuthentication:
    """Test WebSocket authentication and authorization"""

    @pytest.mark.asyncio
    async def test_websocket_without_token(self, websocket_url, test_workspace_id):
        """Test WebSocket connection without authentication token"""
        ws_url_no_auth = f"{websocket_url}?workspace_id={test_workspace_id}"

        with pytest.raises(websockets.exceptions.ConnectionClosedError):
            async with websockets.connect(ws_url_no_auth) as websocket:
                # Should be closed immediately due to auth failure
                await websocket.recv()

    @pytest.mark.asyncio
    async def test_websocket_with_invalid_token(self, websocket_url, test_workspace_id):
        """Test WebSocket connection with invalid token"""
        ws_url_bad_auth = (
            f"{websocket_url}?token=invalid_token&workspace_id={test_workspace_id}"
        )

        with pytest.raises(websockets.exceptions.ConnectionClosedError):
            async with websockets.connect(ws_url_bad_auth) as websocket:
                # Should be closed due to invalid token
                await websocket.recv()


# Performance and load testing
class TestWebSocketPerformance:
    """Test WebSocket performance characteristics"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_multiple_connections(
        self, authenticated_client, websocket_url, test_workspace_id
    ):
        """Test multiple WebSocket connections from same user"""
        # Extract token
        auth_header = authenticated_client.headers.get("Authorization", "")
        token = auth_header[7:]  # Remove "Bearer "

        ws_url_with_auth = (
            f"{websocket_url}?token={token}&workspace_id={test_workspace_id}"
        )

        # Create multiple connections
        connections = []
        try:
            for i in range(3):
                websocket = await websockets.connect(ws_url_with_auth)
                connections.append(websocket)

                # Wait for welcome message
                welcome_raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                welcome = json.loads(welcome_raw)
                assert welcome["type"] == "connection_established"

            # Test that all connections are active
            assert len(connections) == 3

        finally:
            # Clean up connections
            for ws in connections:
                try:
                    await ws.close()
                except:
                    pass

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_rapid_message_sending(self, websocket_client):
        """Test rapid message sending doesn't break connection"""
        # Send multiple ping messages rapidly
        for i in range(10):
            ping_message = {
                "type": "ping",
                "data": {"sequence": i, "timestamp": datetime.utcnow().isoformat()},
            }
            await websocket_client.send(json.dumps(ping_message))

        # Should still be connected and responsive
        final_ping = {"type": "ping", "data": {"final": True}}
        await websocket_client.send(json.dumps(final_ping))

        # Should receive at least the final pong
        response_raw = await asyncio.wait_for(websocket_client.recv(), timeout=5.0)
        response = json.loads(response_raw)

        # Might be any of the pong responses, just verify connection works
        assert response["type"] == "pong"
