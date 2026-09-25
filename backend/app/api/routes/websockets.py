"""
WebSocket API routes for real-time features.
Handles WebSocket connections, real-time messaging, and presence tracking.
"""

from fastapi import (
    APIRouter,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from typing import Dict, Any
import json

from app.core.websocket_manager import manager, WebSocketMessage
from app.core.websocket_auth import get_websocket_user
from app.api.routes.auth import get_current_active_user


router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """
    Main WebSocket endpoint for real-time communication

    Authentication: JWT token via query parameter
    Authorization: User must have access to the specified workspace
    """
    connection_id = None
    user = None

    try:
        # Authenticate user
        user = await get_websocket_user(
            query_params=f"token={token}", headers=dict(websocket.headers)
        )

        # Bind the connection to the tenant carried by the signed token. Accepting
        # an arbitrary workspace query parameter would allow cross-tenant broadcasts.
        token_workspace_id = user.get("workspace_id")
        if not token_workspace_id or str(token_workspace_id) != workspace_id:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Access denied to this workspace",
            )

        # Connect to WebSocket manager
        connection_id = await manager.connect(
            websocket=websocket,
            user_id=str(user["id"]),
            workspace_id=workspace_id,
            user_info={"username": user.get("username"), "email": user.get("email")},
        )

        # Send welcome message
        welcome_message = WebSocketMessage(
            type="connection_established",
            data={
                "connection_id": connection_id,
                "user_id": str(user["id"]),
                "workspace_id": workspace_id,
                "message": "WebSocket connection established successfully",
            },
        )
        await manager.send_to_connection(connection_id, welcome_message)

        # Send current workspace presence
        presence_list = manager.get_workspace_presence(workspace_id)
        presence_message = WebSocketMessage(
            type="workspace_presence",
            data={
                "workspace_id": workspace_id,
                "users": [
                    {
                        "user_id": p.user_id,
                        "user_info": p.user_info,
                        "connected_at": p.connected_at.isoformat(),
                        "last_activity": p.last_activity.isoformat(),
                    }
                    for p in presence_list
                ],
            },
        )
        await manager.send_to_connection(connection_id, presence_message)

        # Listen for incoming messages
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                # Parse incoming message
                message_data = json.loads(data)
                message_type = message_data.get("type")

                # Update activity timestamp
                await manager.update_activity(connection_id)

                # Handle different message types
                if message_type == "ping":
                    # Respond to ping with pong
                    pong_message = WebSocketMessage(
                        type="pong", data={"timestamp": message_data.get("timestamp")}
                    )
                    await manager.send_to_connection(connection_id, pong_message)

                elif message_type == "get_workspace_presence":
                    # Send current workspace presence
                    presence_list = manager.get_workspace_presence(workspace_id)
                    presence_message = WebSocketMessage(
                        type="workspace_presence",
                        data={
                            "workspace_id": workspace_id,
                            "users": [
                                {
                                    "user_id": p.user_id,
                                    "user_info": p.user_info,
                                    "connected_at": p.connected_at.isoformat(),
                                    "last_activity": p.last_activity.isoformat(),
                                }
                                for p in presence_list
                            ],
                        },
                    )
                    await manager.send_to_connection(connection_id, presence_message)

                elif message_type == "workspace_message":
                    # Broadcast message to workspace
                    broadcast_message = WebSocketMessage(
                        type="workspace_message",
                        data=message_data.get("data", {}),
                        sender_id=str(user["id"]),
                    )
                    await manager.broadcast_to_workspace(
                        workspace_id, broadcast_message
                    )

                else:
                    # Unknown message type
                    error_message = WebSocketMessage(
                        type="error",
                        data={
                            "message": f"Unknown message type: {message_type}",
                            "original_message": message_data,
                        },
                    )
                    await manager.send_to_connection(connection_id, error_message)

            except json.JSONDecodeError:
                # Invalid JSON
                error_message = WebSocketMessage(
                    type="error",
                    data={"message": "Invalid JSON format", "received_data": data},
                )
                await manager.send_to_connection(connection_id, error_message)

            except Exception as e:
                # Other errors
                error_message = WebSocketMessage(
                    type="error",
                    data={
                        "message": f"Error processing message: {str(e)}",
                        "received_data": data,
                    },
                )
                await manager.send_to_connection(connection_id, error_message)

    except WebSocketDisconnect:
        # Client disconnected
        if connection_id:
            await manager.disconnect(connection_id)

    except Exception as e:
        # Authentication or other errors
        print(f"WebSocket connection error: {e}")
        if connection_id:
            await manager.disconnect(connection_id)
        # Send error and close connection
        try:
            await websocket.close(code=1008, reason=str(e))
        except:
            pass


@router.post("/ws/broadcast")
async def broadcast_message(
    message_data: Dict[str, Any], current_user: dict = Depends(get_current_active_user)
):
    """
    HTTP endpoint to broadcast messages via WebSocket

    This is primarily for server-side broadcasting (e.g., from Celery tasks)
    """
    message = WebSocketMessage(
        type=message_data.get("type", "broadcast"),
        data=message_data.get("data", {}),
        target=message_data.get("target", "broadcast"),
        target_id=message_data.get("target_id"),
    )

    if message.target == "workspace" and message.target_id:
        await manager.broadcast_to_workspace(message.target_id, message)
    elif message.target == "user" and message.target_id:
        await manager.send_to_user(message.target_id, message)
    else:
        await manager.broadcast_to_all(message)

    return {"status": "message_sent", "type": message.type}


@router.get("/ws/stats")
async def get_websocket_stats():
    """
    Get WebSocket connection statistics

    TODO: Add admin authentication
    """
    stats = manager.get_connection_count()
    return {"websocket_stats": stats, "status": "ok"}
