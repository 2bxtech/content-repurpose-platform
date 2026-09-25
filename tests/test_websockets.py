"""
Real-time features: the /api/ws socket, its HTTP helpers, and the ConnectionManager.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

import pytest
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from app.core.websocket_manager import ConnectionManager, WebSocketMessage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.integration
class TestWebSocketInfrastructure:
    """Test core WebSocket infrastructure"""

    async def test_websocket_connection_establishment(self, websocket_client, auth_user, ws_helper):
        welcome = await ws_helper.wait_for_message_type(websocket_client, "connection_established", 5.0)

        assert welcome["data"]["connection_id"]
        assert welcome["data"]["user_id"] == auth_user["user_id"]
        assert welcome["data"]["workspace_id"] == auth_user["workspace_id"]

    async def test_websocket_ping_pong(self, websocket_client, ws_helper):
        timestamp = _now()
        pong = await ws_helper.send_and_wait_for_response(
            websocket_client, {"type": "ping", "timestamp": timestamp}, "pong"
        )
        assert pong["data"]["timestamp"] == timestamp

    async def test_workspace_presence(self, websocket_client, auth_user, ws_helper):
        # Sent unprompted after connecting, and again on request
        await ws_helper.wait_for_message_type(websocket_client, "workspace_presence", 5.0)
        presence = await ws_helper.send_and_wait_for_response(
            websocket_client, {"type": "get_workspace_presence", "data": {}}, "workspace_presence"
        )

        assert presence["data"]["workspace_id"] == auth_user["workspace_id"]
        users = presence["data"]["users"]
        assert [u["user_id"] for u in users] == [auth_user["user_id"]]

    async def test_workspace_message_broadcasting(self, websocket_client, auth_user, ws_helper):
        test_id = str(uuid.uuid4())
        response = await ws_helper.send_and_wait_for_response(
            websocket_client,
            {"type": "workspace_message", "data": {"message": "Test broadcast message", "test_id": test_id}},
            "workspace_message",
        )

        assert response["data"] == {"message": "Test broadcast message", "test_id": test_id}
        assert response["sender_id"] == auth_user["user_id"]
        assert response["target_id"] == auth_user["workspace_id"]


@pytest.mark.integration
class TestRealTimeTransformations:
    """Transformation progress is pushed to the owner's workspace"""

    async def test_transformation_progress_updates(
        self, websocket_client, authenticated_client, test_document, sample_transformation_data, ws_helper
    ):
        await ws_helper.wait_for_message_type(websocket_client, "connection_established", 5.0)

        response = await authenticated_client.post(
            "/api/transformations", json={**sample_transformation_data, "document_id": test_document["id"]}
        )
        assert response.status_code == 201
        transformation_id = response.json()["id"]

        async def collect():
            seen = []
            while True:
                message = json.loads(await websocket_client.recv())
                if message["type"].startswith("transformation_"):
                    assert message["data"]["transformation_id"] == transformation_id
                    seen.append(message["type"])
                    if message["type"] in ("transformation_completed", "transformation_failed"):
                        return seen

        message_types = await asyncio.wait_for(collect(), 60)

        assert message_types[0] == "transformation_started"
        assert message_types[-1] == "transformation_completed"


@pytest.mark.integration
class TestWebSocketAPI:
    """WebSocket-related HTTP endpoints"""

    async def test_websocket_stats_endpoint_requires_platform_admin(self, authenticated_client):
        response = await authenticated_client.get("/api/ws/stats")
        assert response.status_code == 403

    async def test_websocket_broadcast_api(self, authenticated_client, websocket_client, ws_helper):
        """The HTTP broadcast reaches the caller's own workspace; client targets are ignored"""
        await ws_helper.wait_for_message_type(websocket_client, "connection_established", 5.0)

        response = await authenticated_client.post(
            "/api/ws/broadcast",
            json={
                "type": "test_broadcast",
                "data": {"message": "Test API broadcast", "timestamp": _now()},
                "target": "broadcast",
            },
        )
        assert response.status_code == 200
        assert response.json() == {"status": "message_sent", "type": "test_broadcast"}

        delivered = await ws_helper.wait_for_message_type(websocket_client, "test_broadcast", 5.0)
        assert delivered["data"]["message"] == "Test API broadcast"
        assert delivered["target"] == "workspace"


@pytest.mark.integration
class TestWebSocketErrorHandling:
    """Test WebSocket error handling and edge cases"""

    async def test_invalid_message_format(self, websocket_client, ws_helper):
        error = await ws_helper.send_and_wait_for_response(websocket_client, "invalid json {", "error")
        assert "Invalid JSON format" in error["data"]["message"]

    async def test_unknown_message_type(self, websocket_client, ws_helper):
        error = await ws_helper.send_and_wait_for_response(
            websocket_client, {"type": "unknown_message_type", "data": {"test": "data"}}, "error"
        )
        assert "Unknown message type" in error["data"]["message"]


@pytest.mark.integration
class TestWebSocketAuthentication:
    """The handshake is refused (HTTP 403) before the socket is accepted"""

    async def test_websocket_without_token(self, websocket_url, auth_user):
        with pytest.raises((InvalidStatusCode, ConnectionClosed)):
            async with websockets.connect(f"{websocket_url}?workspace_id={auth_user['workspace_id']}") as ws:
                await asyncio.wait_for(ws.recv(), 5)

    async def test_websocket_with_invalid_token(self, websocket_url, auth_user):
        with pytest.raises((InvalidStatusCode, ConnectionClosed)):
            async with websockets.connect(
                f"{websocket_url}?token=invalid_token&workspace_id={auth_user['workspace_id']}"
            ) as ws:
                await asyncio.wait_for(ws.recv(), 5)


@pytest.mark.integration
class TestWebSocketPerformance:
    """Test WebSocket performance characteristics"""

    @pytest.mark.slow
    async def test_multiple_connections(self, auth_user, websocket_url, ws_helper):
        url = f"{websocket_url}?token={auth_user['token']}&workspace_id={auth_user['workspace_id']}"
        connections = []
        try:
            for _ in range(3):
                ws = await websockets.connect(url)
                connections.append(ws)
                await ws_helper.wait_for_message_type(ws, "connection_established", 5.0)

            # Presence de-duplicates connections of the same user
            presence = await ws_helper.send_and_wait_for_response(
                connections[-1], {"type": "get_workspace_presence", "data": {}}, "workspace_presence"
            )
            assert len(presence["data"]["users"]) == 1
        finally:
            for ws in connections:
                await ws.close()

    @pytest.mark.slow
    async def test_rapid_message_sending(self, websocket_client):
        count = 10
        for i in range(count):
            await websocket_client.send(json.dumps({"type": "ping", "timestamp": str(i)}))

        async def pongs():
            received = []
            while len(received) < count:
                message = json.loads(await websocket_client.recv())
                if message["type"] == "pong":
                    received.append(message["data"]["timestamp"])
            return received

        # Every ping is answered, in order
        assert await asyncio.wait_for(pongs(), 10) == [str(i) for i in range(count)]


class FakeWebSocket:
    """Just enough of starlette's WebSocket for ConnectionManager."""

    def __init__(self):
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    def types(self):
        return [m["type"] for m in self.sent]


@pytest.mark.unit
class TestConnectionManager:
    """In-process routing rules of ConnectionManager (no Redis)"""

    @pytest.fixture
    def manager(self):
        return ConnectionManager()

    async def test_connect_registers_presence(self, manager):
        ws = FakeWebSocket()
        connection_id = await manager.connect(ws, "user-1", "ws-1", {"username": "alice"})

        assert ws.accepted
        presence = manager.get_workspace_presence("ws-1")
        assert [(p.user_id, p.connection_id) for p in presence] == [("user-1", connection_id)]
        assert manager.get_connection_count() == {
            "total_connections": 1,
            "unique_users": 1,
            "active_workspaces": 1,
        }
        # The workspace (including the new connection) is told someone joined
        assert ws.sent[-1]["type"] == "presence_update"
        assert ws.sent[-1]["data"]["event"] == "user_connected"

    async def test_broadcast_stays_inside_workspace(self, manager):
        alice, bob, mallory = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
        await manager.connect(alice, "alice", "ws-a")
        await manager.connect(bob, "bob", "ws-a")
        await manager.connect(mallory, "mallory", "ws-b")

        await manager.broadcast_to_workspace(
            "ws-a", WebSocketMessage(type="transformation_update", data={"transformation_id": "t-1"})
        )

        assert "transformation_update" in alice.types()
        assert "transformation_update" in bob.types()
        assert "transformation_update" not in mallory.types()

    async def test_send_to_user_reaches_all_their_connections(self, manager):
        phone, laptop, other = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
        await manager.connect(phone, "user-1", "ws-1")
        await manager.connect(laptop, "user-1", "ws-1")
        await manager.connect(other, "user-2", "ws-1")

        await manager.send_to_user("user-1", WebSocketMessage(type="notification", data={"message": "done"}))

        assert "notification" in phone.types()
        assert "notification" in laptop.types()
        assert "notification" not in other.types()

    async def test_fan_out_without_redis_delivers_locally(self, manager):
        member, outsider = FakeWebSocket(), FakeWebSocket()
        await manager.connect(member, "user-1", "ws-1")
        await manager.connect(outsider, "user-2", "ws-2")

        await manager.fan_out(
            WebSocketMessage(type="workspace_message", data={}, target="workspace", target_id="ws-1")
        )

        assert "workspace_message" in member.types()
        assert "workspace_message" not in outsider.types()

    async def test_disconnect_cleans_up(self, manager):
        leaving, staying = FakeWebSocket(), FakeWebSocket()
        leaving_id = await manager.connect(leaving, "user-1", "ws-1")
        await manager.connect(staying, "user-2", "ws-1")

        await manager.disconnect(leaving_id)

        assert [p.user_id for p in manager.get_workspace_presence("ws-1")] == ["user-2"]
        assert "user-1" not in manager.user_connections
        assert staying.sent[-1]["data"]["event"] == "user_disconnected"
        # Disconnecting twice is harmless
        await manager.disconnect(leaving_id)
