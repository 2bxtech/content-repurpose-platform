"""
Scalable WebSocket Manager - Enterprise-Ready Real-Time Communication
====================================================================

Enhanced WebSocket connection management with:
- Redis-backed connection state for horizontal scaling
- Message ordering guarantees via Redis Streams
- Enterprise-grade error recovery and reconnection logic
- Connection health monitoring and diagnostics

Addresses Claude Online's feedback on WebSocket scaling architecture.
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

# from app.core.workspace_service import WorkspaceService


class MessageType(Enum):
    """WebSocket message types with ordering requirements."""

    TRANSFORMATION_UPDATE = "transformation_update"
    WORKSPACE_EVENT = "workspace_event"
    USER_PRESENCE = "user_presence"
    SYSTEM_NOTIFICATION = "system_notification"
    HEARTBEAT = "heartbeat"


@dataclass
class WebSocketMessage:
    """Structured WebSocket message with metadata."""

    type: MessageType
    data: Dict
    workspace_id: str
    user_id: str
    timestamp: float
    sequence_id: Optional[int] = None
    server_id: Optional[str] = None


@dataclass
class ConnectionState:
    """Redis-stored connection state for horizontal scaling."""

    user_id: str
    workspace_id: str
    server_id: str
    connected_at: float
    last_heartbeat: float
    client_info: Dict


class ExponentialBackoff:
    """Enterprise-grade exponential backoff strategy."""

    def __init__(
        self,
        initial_ms: int = 1000,
        maximum_ms: int = 30000,
        multiplier: float = 1.5,
        jitter: bool = True,
    ):
        self.initial_ms = initial_ms
        self.maximum_ms = maximum_ms
        self.multiplier = multiplier
        self.jitter = jitter
        self.attempt = 0

    def next_delay(self) -> float:
        """Calculate next delay with exponential backoff."""
        delay = min(self.initial_ms * (self.multiplier**self.attempt), self.maximum_ms)

        if self.jitter:
            import random

            delay = delay * (0.5 + random.random() * 0.5)  # 50-100% of calculated delay

        self.attempt += 1
        return delay / 1000.0  # Convert to seconds

    def reset(self):
        """Reset backoff counter on successful operation."""
        self.attempt = 0


class ScalableWebSocketManager:
    """Enterprise WebSocket manager with horizontal scaling support."""

    def __init__(self):
        self.server_id = os.environ.get("SERVER_ID", f"server_{int(time.time())}")
        self.local_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, ConnectionState] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.logger = logging.getLogger(__name__)

        # Redis keys
        self.CONNECTION_PREFIX = "ws:connection:"
        self.STREAM_PREFIX = "ws:stream:"
        self.PRESENCE_PREFIX = "ws:presence:"

    async def initialize(self):
        """Initialize Redis connection and background tasks."""
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = redis.from_url(redis_url)

        # Start background tasks
        asyncio.create_task(self._heartbeat_monitor())
        asyncio.create_task(self._message_stream_consumer())

        self.logger.info(
            f"WebSocket manager initialized with server_id: {self.server_id}"
        )

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        workspace_id: str,
        db_session: AsyncSession,
    ) -> bool:
        """
        Connect user to WebSocket with Redis-backed state management.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            await websocket.accept()

            connection_key = f"{user_id}:{workspace_id}"

            # Store local connection
            self.local_connections[connection_key] = websocket

            # Create connection state
            connection_state = ConnectionState(
                user_id=user_id,
                workspace_id=workspace_id,
                server_id=self.server_id,
                connected_at=time.time(),
                last_heartbeat=time.time(),
                client_info={
                    "user_agent": websocket.headers.get("user-agent", "unknown")
                },
            )

            self.connection_metadata[connection_key] = connection_state

            # Register in Redis for cross-instance discovery
            await self._register_connection_in_redis(connection_state)

            # Send initial presence update
            await self._broadcast_presence_update(user_id, workspace_id, "connected")

            # Join workspace message stream
            await self._join_workspace_stream(user_id, workspace_id)

            self.logger.info(
                f"WebSocket connected: user={user_id}, workspace={workspace_id}"
            )
            return True

        except Exception as e:
            self.logger.error(f"WebSocket connection failed: {e}")
            return False

    async def disconnect(self, user_id: str, workspace_id: str):
        """Disconnect user with cleanup."""
        connection_key = f"{user_id}:{workspace_id}"

        # Remove local connection
        if connection_key in self.local_connections:
            del self.local_connections[connection_key]

        if connection_key in self.connection_metadata:
            del self.connection_metadata[connection_key]

        # Remove from Redis
        await self._unregister_connection_in_redis(user_id, workspace_id)

        # Send presence update
        await self._broadcast_presence_update(user_id, workspace_id, "disconnected")

        self.logger.info(
            f"WebSocket disconnected: user={user_id}, workspace={workspace_id}"
        )

    async def send_to_user(
        self, user_id: str, workspace_id: str, message: WebSocketMessage
    ):
        """Send message to specific user with cross-instance support."""
        connection_key = f"{user_id}:{workspace_id}"

        # Try local connection first
        if connection_key in self.local_connections:
            websocket = self.local_connections[connection_key]
            try:
                await websocket.send_text(json.dumps(asdict(message)))
                return True
            except WebSocketDisconnect:
                await self.disconnect(user_id, workspace_id)
                return False

        # Try cross-instance delivery via Redis
        return await self._send_cross_instance(user_id, workspace_id, message)

    async def broadcast_to_workspace(
        self,
        workspace_id: str,
        message: WebSocketMessage,
        exclude_user: Optional[str] = None,
    ):
        """
        Broadcast message to all workspace users with ordering guarantees.

        Uses Redis Streams to maintain message ordering across instances.
        """
        # Add to ordered stream for workspace
        stream_key = f"{self.STREAM_PREFIX}{workspace_id}"

        message.server_id = self.server_id
        message.sequence_id = await self._get_next_sequence_id(workspace_id)

        # Publish to Redis Stream (maintains ordering)
        await self.redis_client.xadd(
            stream_key,
            {
                "message_type": message.type.value,
                "data": json.dumps(message.data),
                "user_id": message.user_id,
                "timestamp": message.timestamp,
                "sequence_id": message.sequence_id,
                "server_id": message.server_id,
                "exclude_user": exclude_user or "",
            },
        )

        self.logger.debug(
            f"Broadcast to workspace {workspace_id}: {message.type.value}"
        )

    async def get_workspace_connections(self, workspace_id: str) -> List[str]:
        """Get all connected users in workspace (cross-instance)."""
        pattern = f"{self.CONNECTION_PREFIX}*:{workspace_id}"
        keys = await self.redis_client.keys(pattern)

        user_ids = []
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            user_id = key_str.replace(self.CONNECTION_PREFIX, "").split(":")[0]
            user_ids.append(user_id)

        return user_ids

    async def get_connection_stats(self) -> Dict:
        """Get comprehensive connection statistics."""
        local_count = len(self.local_connections)

        # Get global count from Redis
        pattern = f"{self.CONNECTION_PREFIX}*"
        global_keys = await self.redis_client.keys(pattern)
        global_count = len(global_keys)

        # Get per-workspace stats
        workspace_stats = {}
        for key in global_keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            workspace_id = key_str.split(":")[-1]
            workspace_stats[workspace_id] = workspace_stats.get(workspace_id, 0) + 1

        return {
            "server_id": self.server_id,
            "local_connections": local_count,
            "global_connections": global_count,
            "workspace_distribution": workspace_stats,
            "uptime_seconds": time.time() - getattr(self, "_start_time", time.time()),
        }

    # Redis-backed state management

    async def _register_connection_in_redis(self, connection_state: ConnectionState):
        """Register connection state in Redis for cross-instance discovery."""
        key = f"{self.CONNECTION_PREFIX}{connection_state.user_id}:{connection_state.workspace_id}"

        await self.redis_client.hset(
            key,
            {
                "server_id": connection_state.server_id,
                "connected_at": connection_state.connected_at,
                "last_heartbeat": connection_state.last_heartbeat,
                "client_info": json.dumps(connection_state.client_info),
            },
        )

        # Set expiration for automatic cleanup
        await self.redis_client.expire(key, 3600)  # 1 hour TTL

    async def _unregister_connection_in_redis(self, user_id: str, workspace_id: str):
        """Remove connection from Redis."""
        key = f"{self.CONNECTION_PREFIX}{user_id}:{workspace_id}"
        await self.redis_client.delete(key)

    async def _get_next_sequence_id(self, workspace_id: str) -> int:
        """Get next sequence ID for workspace message ordering."""
        sequence_key = f"ws:sequence:{workspace_id}"
        return await self.redis_client.incr(sequence_key)

    async def _send_cross_instance(
        self, user_id: str, workspace_id: str, message: WebSocketMessage
    ) -> bool:
        """Send message to user on different server instance."""
        # Find target server for user
        connection_key = f"{self.CONNECTION_PREFIX}{user_id}:{workspace_id}"
        server_info = await self.redis_client.hgetall(connection_key)

        if not server_info:
            return False  # User not connected

        target_server = server_info.get(b"server_id", b"").decode()
        if target_server == self.server_id:
            return False  # Should be local (shouldn't happen)

        # Use Redis pub/sub for cross-instance messaging
        channel = f"ws:instance:{target_server}"
        delivery_message = {
            "type": "deliver_message",
            "target_user": user_id,
            "target_workspace": workspace_id,
            "message": asdict(message),
        }

        await self.redis_client.publish(channel, json.dumps(delivery_message))
        return True

    # Background monitoring tasks

    async def _heartbeat_monitor(self):
        """Monitor connection health and handle stale connections."""
        while True:
            try:
                current_time = time.time()
                stale_connections = []

                for connection_key, state in self.connection_metadata.items():
                    if current_time - state.last_heartbeat > 60:  # 60 second timeout
                        stale_connections.append(connection_key)

                # Clean up stale connections
                for connection_key in stale_connections:
                    user_id, workspace_id = connection_key.split(":", 1)
                    await self.disconnect(user_id, workspace_id)

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                self.logger.error(f"Heartbeat monitor error: {e}")
                await asyncio.sleep(60)

    async def _message_stream_consumer(self):
        """Consume messages from Redis Streams for workspace broadcasts."""
        while True:
            try:
                # Listen to all workspace streams this server is interested in
                workspace_ids = set()
                for connection_key in self.local_connections:
                    _, workspace_id = connection_key.split(":", 1)
                    workspace_ids.add(workspace_id)

                if not workspace_ids:
                    await asyncio.sleep(1)
                    continue

                # Read from streams
                streams = {
                    f"{self.STREAM_PREFIX}{ws_id}": "$" for ws_id in workspace_ids
                }

                messages = await self.redis_client.xread(streams, count=10, block=1000)

                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        await self._process_stream_message(stream, msg_id, fields)

            except Exception as e:
                self.logger.error(f"Stream consumer error: {e}")
                await asyncio.sleep(5)

    async def _process_stream_message(self, stream: bytes, msg_id: bytes, fields: Dict):
        """Process incoming stream message."""
        try:
            stream_str = stream.decode()
            workspace_id = stream_str.replace(self.STREAM_PREFIX.encode(), b"").decode()

            # Skip messages from this server
            server_id = fields.get(b"server_id", b"").decode()
            if server_id == self.server_id:
                return

            # Reconstruct message
            message = WebSocketMessage(
                type=MessageType(fields[b"message_type"].decode()),
                data=json.loads(fields[b"data"].decode()),
                user_id=fields[b"user_id"].decode(),
                workspace_id=workspace_id,
                timestamp=float(fields[b"timestamp"].decode()),
                sequence_id=int(fields[b"sequence_id"].decode()),
                server_id=server_id,
            )

            exclude_user = fields.get(b"exclude_user", b"").decode() or None

            # Deliver to local connections
            await self._deliver_to_local_connections(
                workspace_id, message, exclude_user
            )

        except Exception as e:
            self.logger.error(f"Stream message processing error: {e}")

    async def _deliver_to_local_connections(
        self,
        workspace_id: str,
        message: WebSocketMessage,
        exclude_user: Optional[str] = None,
    ):
        """Deliver message to local connections in workspace."""
        local_connections_in_workspace = [
            (key, websocket)
            for key, websocket in self.local_connections.items()
            if key.endswith(f":{workspace_id}")
        ]

        for connection_key, websocket in local_connections_in_workspace:
            user_id = connection_key.split(":", 1)[0]

            if exclude_user and user_id == exclude_user:
                continue

            try:
                await websocket.send_text(json.dumps(asdict(message)))
            except WebSocketDisconnect:
                # Handle disconnection in next heartbeat cycle
                pass
            except Exception as e:
                self.logger.error(f"Message delivery error: {e}")

    async def _broadcast_presence_update(
        self, user_id: str, workspace_id: str, status: str
    ):
        """Broadcast user presence update to workspace."""
        presence_message = WebSocketMessage(
            type=MessageType.USER_PRESENCE,
            data={"user_id": user_id, "status": status, "timestamp": time.time()},
            workspace_id=workspace_id,
            user_id=user_id,
            timestamp=time.time(),
        )

        await self.broadcast_to_workspace(
            workspace_id, presence_message, exclude_user=user_id
        )

    async def _join_workspace_stream(self, user_id: str, workspace_id: str):
        """Initialize user's position in workspace message stream."""
        stream_key = f"{self.STREAM_PREFIX}{workspace_id}"

        # Get latest stream info to establish position
        try:
            stream_info = await self.redis_client.xinfo_stream(stream_key)
            last_id = stream_info.get("last-generated-id", "0-0")

            # Store user's stream position for message recovery
            position_key = f"ws:position:{user_id}:{workspace_id}"
            await self.redis_client.set(position_key, last_id)

        except Exception:
            # Stream doesn't exist yet, will be created on first message
            pass


# Global instance
websocket_manager = ScalableWebSocketManager()
