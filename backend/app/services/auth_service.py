from fastapi import Request
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid
import secrets
import logging

from app.core.config import settings
from app.models.auth import TokenData, DeviceInfo
from app.services.redis_service import redis_service

logger = logging.getLogger(__name__)


class AuthService:
    """Enhanced authentication service with production-grade security"""

    def __init__(self):
        self.pwd_context = CryptContext(
            schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS
        )
        self.oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")

    # Password management
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        try:
            return self.pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            logger.error(f"Password verification error: {str(e)}")
            return False

    def get_password_hash(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return self.pwd_context.hash(password)

    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """Validate password strength according to security requirements"""
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            return (
                False,
                f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long",
            )

        checks = [
            (
                any(c.isupper() for c in password),
                "Password must contain at least one uppercase letter",
            ),
            (
                any(c.islower() for c in password),
                "Password must contain at least one lowercase letter",
            ),
            (
                any(c.isdigit() for c in password),
                "Password must contain at least one digit",
            ),
            (
                any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password),
                "Password must contain at least one special character",
            ),
        ]

        for check, message in checks:
            if not check:
                return False, message

        return True, "Password is strong"

    # JWT Token management
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Create a short-lived access token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

        # Add standard JWT claims
        to_encode.update(
            {
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "access",
                "jti": str(uuid.uuid4()),  # JWT ID for tracking
            }
        )

        encoded_jwt = jwt.encode(
            to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Create a long-lived refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        # Add standard JWT claims
        to_encode.update(
            {
                "exp": expire,
                "iat": datetime.utcnow(),
                "type": "refresh",
                "jti": str(uuid.uuid4()),  # JWT ID for tracking
            }
        )

        encoded_jwt = jwt.encode(
            to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    def create_email_verification_token(self, user_id: uuid.UUID, email: str) -> str:
        """Single-purpose token for the verification link (its own `type`, so it
        can't be used as an access token, and vice versa)."""
        now = datetime.utcnow()
        return jwt.encode(
            {
                "sub": str(user_id),
                "email": email,
                "type": "email_verify",
                "iat": now,
                "exp": now + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
                "jti": str(uuid.uuid4()),
            },
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    def verify_token(
        self, token: str, token_type: str = "access"
    ) -> Optional[TokenData]:
        """Verify and decode a JWT token"""
        try:
            # Choose the correct secret based on token type
            secret_key = (
                settings.REFRESH_SECRET_KEY
                if token_type == "refresh"
                else settings.SECRET_KEY
            )

            payload = jwt.decode(token, secret_key, algorithms=[settings.JWT_ALGORITHM])

            # Verify token type matches expected
            if payload.get("type") != token_type:
                return None

            # Check if token is blacklisted
            jti = payload.get("jti")
            if jti and redis_service.is_token_blacklisted(jti):
                return None

            return TokenData(
                user_id=uuid.UUID(payload.get("sub")),  # Convert to UUID
                email=payload.get("email"),
                username=payload.get("username"),
                workspace_id=(
                    uuid.UUID(payload["workspace_id"])
                    if payload.get("workspace_id")
                    else None
                ),
                jti=jti,
                token_type=payload.get("type"),
            )
        except JWTError as e:
            logger.warning(f"JWT verification failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return None

    def blacklist_token(self, token: str, token_type: str = "access") -> bool:
        """Add a token to the blacklist"""
        try:
            secret_key = (
                settings.REFRESH_SECRET_KEY
                if token_type == "refresh"
                else settings.SECRET_KEY
            )
            payload = jwt.decode(token, secret_key, algorithms=[settings.JWT_ALGORITHM])

            jti = payload.get("jti")
            exp = payload.get("exp")

            if jti and exp:
                expires_at = datetime.utcfromtimestamp(exp)
                return redis_service.blacklist_token(jti, expires_at)
        except Exception as e:
            logger.error(f"Error blacklisting token: {str(e)}")
        return False

    # Device and session management
    def extract_device_info(self, request: Request) -> DeviceInfo:
        """Extract device information from request"""
        user_agent = request.headers.get("user-agent", "Unknown")

        # Basic device type detection
        device_type = "desktop"
        if "mobile" in user_agent.lower():
            device_type = "mobile"
        elif "tablet" in user_agent.lower():
            device_type = "tablet"

        # Basic browser detection
        browser = "unknown"
        if "chrome" in user_agent.lower():
            browser = "chrome"
        elif "firefox" in user_agent.lower():
            browser = "firefox"
        elif "safari" in user_agent.lower():
            browser = "safari"
        elif "edge" in user_agent.lower():
            browser = "edge"

        return DeviceInfo(
            user_agent=user_agent[:500],  # Truncate to prevent abuse
            ip_address=self._get_client_ip(request),
            device_type=device_type,
            browser=browser,
        )

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, handling proxies"""
        # Check for forwarded IP first (common in production)
        forwarded_for = request.headers.get("x-forwarded-for")
        if settings.TRUST_PROXY_HEADERS and forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("x-real-ip")
        if settings.TRUST_PROXY_HEADERS and real_ip:
            return real_ip

        # Fall back to direct connection IP
        return request.client.host if request.client else "unknown"

    # Rate limiting
    # Session management
    def create_session(
        self, user_id, refresh_token: str, device_info: DeviceInfo
    ) -> bool:
        """Create a new user session"""
        try:
            # Extract JWT ID from refresh token
            payload = jwt.decode(
                refresh_token,
                settings.REFRESH_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            refresh_jti = payload.get("jti")

            if not refresh_jti:
                return False

            return redis_service.create_user_session(
                user_id=str(user_id),  # Convert to string for Redis storage
                refresh_token_jti=refresh_jti,
                device_info=device_info.dict(),
            )
        except Exception as e:
            logger.error(f"Error creating user session: {str(e)}")
            return False

    def invalidate_session(self, user_id, refresh_token: str) -> bool:
        """Invalidate a specific session"""
        try:
            payload = jwt.decode(
                refresh_token,
                settings.REFRESH_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            refresh_jti = payload.get("jti")

            if refresh_jti:
                return redis_service.invalidate_user_session(str(user_id), refresh_jti)
        except Exception as e:
            logger.error(f"Error invalidating session: {str(e)}")
        return False

    def invalidate_all_sessions(self, user_id) -> bool:
        """Invalidate all sessions for a user"""
        return redis_service.invalidate_all_user_sessions(str(user_id))

    def get_user_sessions(self, user_id) -> list:
        """Get all active sessions for a user"""
        return redis_service.get_user_sessions(str(user_id))

    # Security utilities
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate a cryptographically secure random token"""
        return secrets.token_urlsafe(length)

    def constant_time_compare(self, val1: str, val2: str) -> bool:
        """Constant-time string comparison to prevent timing attacks"""
        return secrets.compare_digest(val1, val2)


# Global instance
auth_service = AuthService()
