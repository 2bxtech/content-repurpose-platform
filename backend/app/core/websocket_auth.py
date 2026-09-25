"""
WebSocket authentication utilities.
Provides JWT token validation for WebSocket connections.
"""

import jwt
from jwt.exceptions import InvalidTokenError as JWTError  # noqa: F401 (used in caller catch blocks)
from typing import Dict, Any, Optional
from fastapi import WebSocketException, status

from app.services.auth_service import auth_service


async def authenticate_websocket_token(token: str) -> Dict[str, Any]:
    """
    Authenticate WebSocket connection using JWT token

    Args:
        token: JWT access token

    Returns:
        User information dictionary

    Raises:
        WebSocketException: If authentication fails
    """
    try:
        # Verify JWT token using auth service
        token_data = auth_service.verify_token(token, "access")

        if not token_data:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid authentication token",
            )

        # Extract user information from token data
        user_id = token_data.user_id
        username = token_data.username
        email = token_data.email

        if not user_id:
            raise WebSocketException(
                code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload"
            )

        return {
            "id": user_id,
            "username": username,
            "email": email,
            "workspace_id": token_data.workspace_id,
        }

    except jwt.ExpiredSignatureError:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token"
        )
    except WebSocketException:
        raise
    except Exception:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token"
        )


def extract_token_from_query(query_params: str) -> Optional[str]:
    """
    Extract token from WebSocket query parameters

    Args:
        query_params: Query string from WebSocket connection

    Returns:
        JWT token if found, None otherwise
    """
    try:
        # Parse query parameters
        params = {}
        if query_params:
            for param in query_params.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

        # Look for token in various parameter names
        token = (
            params.get("token")
            or params.get("access_token")
            or params.get("auth_token")
        )
        return token

    except Exception:
        return None


def extract_token_from_headers(headers: Dict[str, str]) -> Optional[str]:
    """
    Extract token from WebSocket headers

    Args:
        headers: WebSocket headers dictionary

    Returns:
        JWT token if found, None otherwise
    """
    try:
        # Check Authorization header
        auth_header = headers.get("authorization") or headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove 'Bearer ' prefix

        # Check custom auth headers
        return headers.get("X-Auth-Token") or headers.get("x-auth-token")

    except Exception:
        return None


async def get_websocket_user(
    query_params: str = None, headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    Get authenticated user for WebSocket connection

    Args:
        query_params: WebSocket query parameters
        headers: WebSocket headers

    Returns:
        User information dictionary

    Raises:
        WebSocketException: If authentication fails
    """
    # Try to extract token from query parameters first
    token = None
    if query_params:
        token = extract_token_from_query(query_params)

    # Fallback to headers if no token in query params
    if not token and headers:
        token = extract_token_from_headers(headers)

    if not token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Authentication token required"
        )

    return await authenticate_websocket_token(token)
