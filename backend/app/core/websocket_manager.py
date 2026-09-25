"""
WebSocket connection manager for real-time features.
Handles user sessions, presence tracking, and message broadcasting.
"""

import json
import uuid
import asyncio
from typing import Dict, List, Set, Any, Optional
from datetime import datetime, timedelta
from fastapi import WebSocket
from pydantic import BaseModel

from app.services.redis_service import redis_service


class UserPresence(BaseModel):
    """User presence information"""

    user_id: str
    workspace_id: str
    connection_id: str
    connected_at: datetime
    last_activity: datetime
    user_info: Dict[str, Any] = {}


class WebSocketMessage(BaseModel):
    """WebSocket message structure"""

    type: str
    data: Dict[str, Any]
    target: Optional[str] = None  # 'user', 'workspace', 'broadcast'
    target_id: Optional[str] = None
    sender_id: Optional[str] = None
    timestamp: datetime = None

    def __init__(self, **data):
        if data.get("timestamp") is None:
            data["timestamp"] = datetime.utcnow()
        super().__init__(**data)


class ConnectionManager:
    """Manages WebSocket connections and real-time messaging"""

    def __init__(self):
        # Active connections by connection_id
        self.active_connections: Dict[str, WebSocket] = {}

        # User connections mapping: user_id -> Set[connection_id]
        self.user_connections: Dict[str, Set[str]] = {}

        # Workspace connections mapping: workspace_id -> Set[connection_id]
        self.workspace_connections: Dict[str, Set[str]] = {}

        # Connection metadata: connection_id -> UserPresence
        self.connection_metadata: Dict[str, UserPresence] = {}

        # Redis pub/sub channels
        self.pubsub = None
        self.redis_listener_task = None

    async def start_redis_listener(self):
        """Start Redis pub/sub listener for distributed messaging"""
        if not redis_service.is_connected():
            return

        try:
            self.pubsub = redis_service.redis_client.pubsub()
            self.pubsub.subscribe("websocket:broadcast")  # Remove await here

            self.redis_listener_task = asyncio.create_task(self._redis_listener())
        except Exception as e:
            print(f"Failed to start Redis listener: {e}")

    async def stop_redis_listener(self):
        """Stop Redis pub/sub listener"""
        if self.redis_listener_task:
            self.redis_listener_task.cancel()
            try:
                await self.redis_listener_task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.unsubscribe("websocket:broadcast")
            await self.pubsub.close()

    async def _redis_listener(self):
        """Listen for Redis pub/sub messages"""
        try:
            # Use get_message() in a loop instead of async for
            while True:
                try:
                    message = self.pubsub.get_message(timeout=1.0)
                    if message and message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            ws_message = WebSocketMessage(**data)
                            await self._handle_redis_message(ws_message)
                        except Exception as e:
                            print(f"Error processing Redis message: {e}")
                    await asyncio.sleep(0.01)  # Small delay to prevent tight loop
                except Exception as e:
                    print(f"Error getting Redis message: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Redis listener error: {e}")

    async def _handle_redis_message(self, message: WebSocketMessage):
        """Handle message received from Redis pub/sub"""
        if message.target == "broadcast":
            await self.broadcast_to_all(message)
        elif message.target == "workspace" and message.target_id:
            await self.broadcast_to_workspace(message.target_id, message)
        elif message.target == "user" and message.target_id:
            await self.send_to_user(message.target_id, message)

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        workspace_id: str,
        user_info: Dict[str, Any] = None,
    ) -> str:
        """Accept WebSocket connection and register user"""
        await websocket.accept()

        # Generate unique connection ID
        connection_id = str(uuid.uuid4())

        # Store connection
        self.active_connections[connection_id] = websocket

        # Add to user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)

        # Add to workspace connections
        if workspace_id not in self.workspace_connections:
            self.workspace_connections[workspace_id] = set()
        self.workspace_connections[workspace_id].add(connection_id)

        # Store connection metadata
        presence = UserPresence(
            user_id=user_id,
            workspace_id=workspace_id,
            connection_id=connection_id,
            connected_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            user_info=user_info or {},
        )
        self.connection_metadata[connection_id] = presence

        # Notify workspace about new presence
        await self._broadcast_presence_update(
            workspace_id,
            "user_connected",
            {
                "user_id": user_id,
                "user_info": user_info,
                "connected_at": presence.connected_at.isoformat(),
            },
        )

        print(
            f"WebSocket connected: {connection_id} (user: {user_id}, workspace: {workspace_id})"
        )
        return connection_id

    async def disconnect(self, connection_id: str):
        """Disconnect WebSocket and clean up"""
        if connection_id not in self.active_connections:
            return

        # Get connection metadata
        presence = self.connection_metadata.get(connection_id)

        # Remove from active connections
        del self.active_connections[connection_id]

        if presence:
            user_id = presence.user_id
            workspace_id = presence.workspace_id

            # Remove from user connections
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(connection_id)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

            # Remove from workspace connections
            if workspace_id in self.workspace_connections:
                self.workspace_connections[workspace_id].discard(connection_id)
                if not self.workspace_connections[workspace_id]:
                    del self.workspace_connections[workspace_id]

            # Remove metadata
            del self.connection_metadata[connection_id]

            # Notify workspace about disconnection
            await self._broadcast_presence_update(
                workspace_id,
                "user_disconnected",
                {"user_id": user_id, "disconnected_at": datetime.utcnow().isoformat()},
            )

        print(f"WebSocket disconnected: {connection_id}")

    async def send_personal_message(
        self, message: WebSocketMessage, websocket: WebSocket
    ):
        """Send message to a specific WebSocket connection"""
        try:
            await websocket.send_text(json.dumps(message.dict(), default=str))
        except Exception as e:
            print(f"Error sending personal message: {e}")

    async def send_to_connection(self, connection_id: str, message: WebSocketMessage):
        """Send message to specific connection"""
        websocket = self.active_connections.get(connection_id)
        if websocket:
            await self.send_personal_message(message, websocket)

    async def send_to_user(self, user_id: str, message: WebSocketMessage):
        """Send message to all connections of a specific user"""
        connection_ids = self.user_connections.get(user_id, set())
        for (
            connection_id
        ) in connection_ids.copy():  # Copy to avoid modification during iteration
            await self.send_to_connection(connection_id, message)

    async def broadcast_to_workspace(
        self, workspace_id: str, message: WebSocketMessage
    ):
        """Broadcast message to all users in a workspace"""
        connection_ids = self.workspace_connections.get(workspace_id, set())
        for connection_id in connection_ids.copy():
            await self.send_to_connection(connection_id, message)

    async def broadcast_to_all(self, message: WebSocketMessage):
        """Broadcast message to all connected users"""
        for connection_id in list(self.active_connections.keys()):
            await self.send_to_connection(connection_id, message)

    async def _broadcast_presence_update(
        self, workspace_id: str, event_type: str, data: Dict[str, Any]
    ):
        """Broadcast presence updates to workspace"""
        message = WebSocketMessage(
            type="presence_update",
            data={"event": event_type, "workspace_id": workspace_id, **data},
        )
        await self.broadcast_to_workspace(workspace_id, message)

    async def publish_to_redis(self, message: WebSocketMessage):
        """Publish message to Redis for distributed broadcasting"""
        if not redis_service.is_connected():
            return

        try:
            # Use synchronous publish, not async
            redis_service.redis_client.publish(
                "websocket:broadcast", json.dumps(message.dict(), default=str)
            )
        except Exception as e:
            print(f"Error publishing to Redis: {e}")

    def get_workspace_presence(self, workspace_id: str) -> List[UserPresence]:
        """Get list of users present in a workspace"""
        connection_ids = self.workspace_connections.get(workspace_id, set())
        users = {}

        for connection_id in connection_ids:
            presence = self.connection_metadata.get(connection_id)
            if presence:
                # Only include the latest connection per user
                if (
                    presence.user_id not in users
                    or presence.connected_at > users[presence.user_id].connected_at
                ):
                    users[presence.user_id] = presence

        return list(users.values())

    def get_connection_count(self) -> Dict[str, int]:
        """Get connection statistics"""
        return {
            "total_connections": len(self.active_connections),
            "unique_users": len(self.user_connections),
            "active_workspaces": len(self.workspace_connections),
        }

    async def update_activity(self, connection_id: str):
        """Update last activity timestamp for a connection"""
        if connection_id in self.connection_metadata:
            self.connection_metadata[connection_id].last_activity = datetime.utcnow()

    async def cleanup_stale_connections(self):
        """Clean up stale connections (older than 30 minutes)"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=30)
        stale_connections = []

        for connection_id, presence in self.connection_metadata.items():
            if presence.last_activity < cutoff_time:
                stale_connections.append(connection_id)

        for connection_id in stale_connections:
            await self.disconnect(connection_id)


# Global connection manager instance
manager = ConnectionManager()
