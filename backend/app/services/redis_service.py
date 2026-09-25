import redis
import json
from typing import Any, Optional, Dict, List
from datetime import datetime
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class RedisService:
    """Redis service for session management, token blacklisting, and rate limiting"""

    def __init__(self):
        self.redis_client = None
        self._connect()

    def _connect(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                settings.get_redis_url(),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {str(e)}")
            logger.warning("Running without Redis - some features will be limited")
            self.redis_client = None
            # In development, we can continue without Redis, but log the issue
            if settings.ENVIRONMENT == "production":
                raise

    async def connect(self):
        """Async method to establish Redis connection for FastAPI lifespan"""
        self._connect()

    async def disconnect(self):
        """Async method to close Redis connection for FastAPI lifespan"""
        try:
            if self.redis_client:
                # For synchronous Redis client, we don't need to close it explicitly
                self.redis_client = None
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {str(e)}")

    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        try:
            if self.redis_client:
                self.redis_client.ping()
                return True
        except:
            pass
        return False

    async def health_check(self) -> bool:
        """Async health check for Redis connection"""
        try:
            if self.redis_client:
                self.redis_client.ping()
                return True
            return False
        except Exception as e:
            logger.error(f"Redis health check failed: {str(e)}")
            return False

    # Token blacklisting
    def blacklist_token(self, token_jti: str, expires_at: datetime) -> bool:
        """Add token to blacklist"""
        if not self.is_connected():
            return False

        try:
            key = f"blacklist:{token_jti}"
            expiry_seconds = int((expires_at - datetime.utcnow()).total_seconds())
            if expiry_seconds > 0:
                self.redis_client.setex(key, expiry_seconds, "true")
            return True
        except Exception as e:
            logger.error(f"Error blacklisting token: {str(e)}")
            return False

    def is_token_blacklisted(self, token_jti: str) -> bool:
        """Check if token is blacklisted"""
        if not self.is_connected():
            return False

        try:
            key = f"blacklist:{token_jti}"
            return self.redis_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking token blacklist: {str(e)}")
            return False

    # Session management
    def create_user_session(
        self, user_id: int, refresh_token_jti: str, device_info: Dict[str, Any]
    ) -> bool:
        """Create a new user session"""
        if not self.is_connected():
            return False

        try:
            session_data = {
                "user_id": user_id,
                "refresh_token_jti": refresh_token_jti,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "device_info": device_info,
            }

            key = f"session:{user_id}:{refresh_token_jti}"
            self.redis_client.setex(
                key,
                settings.REFRESH_TOKEN_EXPIRE_DAYS
                * 24
                * 3600,  # Convert days to seconds
                json.dumps(session_data),
            )

            # Manage session limit per user
            self._manage_user_session_limit(user_id)
            return True
        except Exception as e:
            logger.error(f"Error creating user session: {str(e)}")
            return False

    def get_user_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all active sessions for a user"""
        if not self.is_connected():
            return []

        try:
            pattern = f"session:{user_id}:*"
            keys = self.redis_client.keys(pattern)
            sessions = []

            for key in keys:
                session_data = self.redis_client.get(key)
                if session_data:
                    sessions.append(json.loads(session_data))

            return sessions
        except Exception as e:
            logger.error(f"Error getting user sessions: {str(e)}")
            return []

    def invalidate_user_session(self, user_id: int, refresh_token_jti: str) -> bool:
        """Invalidate a specific user session"""
        if not self.is_connected():
            return False

        try:
            key = f"session:{user_id}:{refresh_token_jti}"
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error invalidating session: {str(e)}")
            return False

    def consume_user_session(self, user_id: str, refresh_token_jti: str) -> Optional[bool]:
        """Atomically end a session so its refresh token can be exchanged once.

        DEL is atomic, so when two requests race with the same refresh token exactly
        one gets True. None means the session store is unavailable.
        """
        if not self.is_connected():
            return None
        try:
            return self.redis_client.delete(f"session:{user_id}:{refresh_token_jti}") == 1
        except Exception as e:
            logger.error(f"Error consuming session: {str(e)}")
            return None

    def user_session_exists(
        self, user_id: str, refresh_token_jti: str
    ) -> Optional[bool]:
        """Return None when the session store is unavailable."""
        if not self.is_connected():
            return None
        try:
            key = f"session:{user_id}:{refresh_token_jti}"
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Error checking session existence: {str(e)}")
            return None

    def invalidate_all_user_sessions(self, user_id: int) -> bool:
        """Invalidate all sessions for a user"""
        if not self.is_connected():
            return False

        try:
            pattern = f"session:{user_id}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Error invalidating all user sessions: {str(e)}")
            return False

    def _manage_user_session_limit(self, user_id: int):
        """Ensure user doesn't exceed maximum sessions"""
        try:
            sessions = self.get_user_sessions(user_id)
            if len(sessions) >= settings.MAX_SESSIONS_PER_USER:
                # Sort by last activity and remove oldest sessions
                sessions.sort(key=lambda x: x["last_activity"])
                sessions_to_remove = sessions[: -settings.MAX_SESSIONS_PER_USER + 1]

                for session in sessions_to_remove:
                    self.invalidate_user_session(user_id, session["refresh_token_jti"])
        except Exception as e:
            logger.error(f"Error managing session limit: {str(e)}")

    def update_session_activity(self, user_id: int, refresh_token_jti: str) -> bool:
        """Update last activity time for a session"""
        if not self.is_connected():
            return False

        try:
            key = f"session:{user_id}:{refresh_token_jti}"
            session_data = self.redis_client.get(key)
            if session_data:
                session = json.loads(session_data)
                session["last_activity"] = datetime.utcnow().isoformat()

                # Get remaining TTL to preserve expiry
                ttl = self.redis_client.ttl(key)
                if ttl > 0:
                    self.redis_client.setex(key, ttl, json.dumps(session))
                return True
        except Exception as e:
            logger.error(f"Error updating session activity: {str(e)}")
        return False

    # Rate limiting
    # Generic caching
    def set(self, key: str, value: Any, expire: int = None) -> bool:
        """Set a value in Redis with optional expiry"""
        if not self.is_connected():
            return False

        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            if expire:
                self.redis_client.setex(key, expire, value)
            else:
                self.redis_client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"Error setting Redis value: {str(e)}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """Get a value from Redis"""
        if not self.is_connected():
            return None

        try:
            value = self.redis_client.get(key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return None
        except Exception as e:
            logger.error(f"Error getting Redis value: {str(e)}")
            return None


# Global instance
redis_service = RedisService()
