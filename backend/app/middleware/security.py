"""
Security Middleware

Provides comprehensive security headers, content security policy,
input validation, and security monitoring for production deployment.
"""

import time
import json
from typing import Dict, Any, Optional
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import re
import logging

from app.core.config import settings
from app.services.audit_service import audit_service, AuditEventType, AuditLevel


logger = logging.getLogger(__name__)


class SecurityConfig:
    """Security configuration and policies"""

    # Content Security Policy
    CSP_POLICY = {
        "default-src": ["'self'"],
        "script-src": ["'self'", "'unsafe-inline'", "'unsafe-eval'"],
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "img-src": ["'self'", "data:", "https:"],
        "connect-src": ["'self'", "ws://localhost:*", "wss://localhost:*"],
        "frame-ancestors": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    }

    # Security headers
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
    }

    # HSTS settings (only for HTTPS)
    HSTS_MAX_AGE = 31536000  # 1 year
    HSTS_INCLUDE_SUBDOMAINS = True
    HSTS_PRELOAD = True

    # Input validation patterns
    SUSPICIOUS_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # Script tags
        r"javascript:",  # JavaScript URLs
        r"vbscript:",  # VBScript URLs
        r"on\w+\s*=",  # Event handlers
        r"expression\s*\(",  # CSS expressions
        r"\beval\s*\(",  # eval() calls
        r"\balert\s*\(",  # alert() calls
        r"document\.cookie",  # Cookie access
        r"document\.write",  # DOM manipulation
        r"window\.location",  # Location changes
        r"\.\./\.\.",  # Path traversal
        r"\.\.\\\.\.\\",  # Windows path traversal
        r"/etc/passwd",  # Unix system files
        r"cmd\.exe",  # Windows commands
        r"powershell",  # PowerShell
        r"union\s+select",  # SQL injection
        r"drop\s+table",  # SQL injection
        r"insert\s+into",  # SQL injection
        r"delete\s+from",  # SQL injection
    ]

    # Rate limiting thresholds for security events
    MAX_SECURITY_VIOLATIONS_PER_MINUTE = 5
    MAX_VALIDATION_FAILURES_PER_MINUTE = 10


class SecurityMiddleware(BaseHTTPMiddleware):
    """Comprehensive security middleware"""

    def __init__(self, app, config: SecurityConfig = None):
        super().__init__(app)
        self.config = config or SecurityConfig()
        self.security_violations = {}  # IP -> violations tracking

    async def dispatch(self, request: Request, call_next):
        """Process request through security filters"""
        time.time()

        try:
            # Pre-request security checks
            await self._pre_request_security_checks(request)

            # Process request
            response = await call_next(request)

            # Post-request security enhancements
            await self._enhance_response_security(request, response)

            # Log successful request
            if response.status_code >= 400:
                await audit_service.log_security_event(
                    event_type=AuditEventType.SECURITY_VALIDATION_FAILED,
                    level=AuditLevel.WARNING,
                    request=request,
                    details={
                        "status_code": response.status_code,
                        "path": str(request.url.path),
                        "method": request.method,
                    },
                )

            return response

        except HTTPException as e:
            # Handle known security violations
            await self._handle_security_violation(request, e)
            raise

        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Security middleware error: {e}")
            await audit_service.log_security_event(
                event_type=AuditEventType.SYSTEM_ERROR,
                level=AuditLevel.ERROR,
                request=request,
                details={"error": str(e)},
            )
            raise

    async def _pre_request_security_checks(self, request: Request):
        """Perform security checks before processing request"""

        # Check for suspicious patterns in URL
        url_path = str(request.url.path)
        if self._contains_suspicious_patterns(url_path):
            await self._log_and_block_request(
                request, "Suspicious patterns detected in URL", {"url_path": url_path}
            )

        # Check query parameters
        query_params = str(request.url.query)
        if query_params and self._contains_suspicious_patterns(query_params):
            await self._log_and_block_request(
                request,
                "Suspicious patterns detected in query parameters",
                {"query_params": query_params},
            )

        # Check User-Agent for suspicious patterns
        user_agent = request.headers.get("user-agent", "")
        if self._is_suspicious_user_agent(user_agent):
            await self._log_and_block_request(
                request, "Suspicious User-Agent detected", {"user_agent": user_agent}
            )

        # Check for security violation rate limiting
        client_ip = self._get_client_ip(request)
        if self._is_security_rate_limited(client_ip):
            await self._log_and_block_request(
                request, "Security rate limit exceeded", {"client_ip": client_ip}
            )

        # Check Content-Length for extremely large payloads
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 100 * 1024 * 1024:  # 100MB
            await self._log_and_block_request(
                request,
                "Extremely large payload detected",
                {"content_length": content_length},
            )

        # Validate request method
        if request.method not in [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "OPTIONS",
            "HEAD",
        ]:
            await self._log_and_block_request(
                request, "Invalid HTTP method", {"method": request.method}
            )

    async def _enhance_response_security(self, request: Request, response: Response):
        """Add security headers to response"""

        # Add standard security headers
        for header, value in self.config.SECURITY_HEADERS.items():
            response.headers[header] = value

        # Add Content Security Policy
        csp_policy = self._build_csp_header()
        response.headers["Content-Security-Policy"] = csp_policy

        # Add HSTS header for HTTPS
        if request.url.scheme == "https" or settings.ENVIRONMENT == "production":
            hsts_value = f"max-age={self.config.HSTS_MAX_AGE}"
            if self.config.HSTS_INCLUDE_SUBDOMAINS:
                hsts_value += "; includeSubDomains"
            if self.config.HSTS_PRELOAD:
                hsts_value += "; preload"
            response.headers["Strict-Transport-Security"] = hsts_value

        # Add custom security headers
        response.headers["X-API-Version"] = "2.0.0"
        response.headers["X-Security-Enhanced"] = "true"

        # Remove server identification headers (use del instead of pop for MutableHeaders)
        if "Server" in response.headers:
            del response.headers["Server"]
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

    def _build_csp_header(self) -> str:
        """Build Content Security Policy header"""
        csp_parts = []
        for directive, sources in self.config.CSP_POLICY.items():
            sources_str = " ".join(sources)
            csp_parts.append(f"{directive} {sources_str}")
        return "; ".join(csp_parts)

    def _contains_suspicious_patterns(self, text: str) -> bool:
        """Check if text contains suspicious patterns"""
        text_lower = text.lower()
        for pattern in self.config.SUSPICIOUS_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False

    def _is_suspicious_user_agent(self, user_agent: str) -> bool:
        """Check if User-Agent appears suspicious"""
        suspicious_agents = [
            "sqlmap",
            "nikto",
            "nmap",
            "masscan",
            "zap",
            "burp",
            "w3af",
            "skipfish",
            "dirb",
            "gobuster",
            "nessus",
            "openvas",
            "acunetix",
            "appscan",
        ]

        user_agent_lower = user_agent.lower()
        return any(agent in user_agent_lower for agent in suspicious_agents)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        # Check for forwarded IP first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct connection IP
        return request.client.host if request.client else "unknown"

    def _is_security_rate_limited(self, client_ip: str) -> bool:
        """Check if client IP has exceeded security violation limits"""
        current_minute = int(time.time() // 60)

        if client_ip not in self.security_violations:
            self.security_violations[client_ip] = {}

        # Clean old entries
        for minute in list(self.security_violations[client_ip].keys()):
            if current_minute - minute > 5:  # Keep last 5 minutes
                del self.security_violations[client_ip][minute]

        # Count violations in current minute
        violations_this_minute = self.security_violations[client_ip].get(
            current_minute, 0
        )
        return violations_this_minute >= self.config.MAX_SECURITY_VIOLATIONS_PER_MINUTE

    def _record_security_violation(self, client_ip: str):
        """Record a security violation for rate limiting"""
        current_minute = int(time.time() // 60)

        if client_ip not in self.security_violations:
            self.security_violations[client_ip] = {}

        self.security_violations[client_ip][current_minute] = (
            self.security_violations[client_ip].get(current_minute, 0) + 1
        )

    async def _log_and_block_request(
        self, request: Request, reason: str, details: Optional[Dict[str, Any]] = None
    ):
        """Log security violation and block request"""
        client_ip = self._get_client_ip(request)

        # Record violation for rate limiting
        self._record_security_violation(client_ip)

        # Log security event
        await audit_service.log_security_event(
            event_type=AuditEventType.SECURITY_UNAUTHORIZED_ACCESS,
            level=AuditLevel.ERROR,
            request=request,
            details={"reason": reason, "blocked": True, **(details or {})},
            security_context={
                "violation_type": "blocked_request",
                "client_ip": client_ip,
            },
        )

        # Raise HTTP exception to block request
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Request blocked due to security violation",
                "code": "SECURITY_VIOLATION",
                "details": "Your request has been blocked for security reasons",
            },
        )

    async def _handle_security_violation(
        self, request: Request, exception: HTTPException
    ):
        """Handle security violations"""
        client_ip = self._get_client_ip(request)

        # Log the violation
        await audit_service.log_security_event(
            event_type=AuditEventType.SECURITY_SUSPICIOUS_ACTIVITY,
            level=AuditLevel.WARNING,
            request=request,
            details={
                "status_code": exception.status_code,
                "detail": str(exception.detail),
                "client_ip": client_ip,
            },
        )


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Input validation and sanitization middleware"""

    def __init__(self, app):
        super().__init__(app)
        self.validation_failures = {}  # Track validation failures per IP

    async def dispatch(self, request: Request, call_next):
        """Validate and sanitize input"""

        # Skip validation for certain paths
        if self._should_skip_validation(request.url.path):
            return await call_next(request)

        try:
            # Validate request body for POST/PUT requests
            if request.method in ["POST", "PUT", "PATCH"]:
                await self._validate_request_body(request)

            # Process request
            response = await call_next(request)
            return response

        except HTTPException as e:
            # Log validation failure
            await self._log_validation_failure(request, str(e.detail))
            raise

        except Exception as e:
            logger.error(f"Input validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request format"
            )

    def _should_skip_validation(self, path: str) -> bool:
        """Determine if validation should be skipped for this path"""
        skip_paths = ["/docs", "/redoc", "/openapi.json", "/health", "/favicon.ico"]
        return any(path.startswith(skip_path) for skip_path in skip_paths)

    async def _validate_request_body(self, request: Request):
        """Validate request body content"""
        try:
            # Only validate JSON content
            content_type = request.headers.get("content-type", "")
            if "application/json" not in content_type:
                return

            # Read and parse body
            body = await request.body()
            if not body:
                return

            # Parse JSON
            try:
                json_data = json.loads(body)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format",
                )

            # Validate structure
            await self._validate_json_structure(json_data, request)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Body validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body validation failed",
            )

    async def _validate_json_structure(self, data: Any, request: Request):
        """Validate JSON data structure and content"""

        # Check for deeply nested objects (potential DoS)
        if self._check_nesting_depth(data, max_depth=10):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request structure too deeply nested",
            )

        # Check for extremely large arrays (potential DoS)
        if self._check_array_sizes(data, max_size=1000):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request contains arrays that are too large",
            )

        # Check for suspicious content in string values
        if self._contains_malicious_content(data):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request contains potentially malicious content",
            )

    def _check_nesting_depth(
        self, obj: Any, current_depth: int = 0, max_depth: int = 10
    ) -> bool:
        """Check if object nesting exceeds maximum depth"""
        if current_depth > max_depth:
            return True

        if isinstance(obj, dict):
            return any(
                self._check_nesting_depth(value, current_depth + 1, max_depth)
                for value in obj.values()
            )
        elif isinstance(obj, list):
            return any(
                self._check_nesting_depth(item, current_depth + 1, max_depth)
                for item in obj
            )

        return False

    def _check_array_sizes(self, obj: Any, max_size: int = 1000) -> bool:
        """Check if any arrays exceed maximum size"""
        if isinstance(obj, list):
            if len(obj) > max_size:
                return True
            return any(self._check_array_sizes(item, max_size) for item in obj)
        elif isinstance(obj, dict):
            return any(
                self._check_array_sizes(value, max_size) for value in obj.values()
            )

        return False

    def _contains_malicious_content(self, obj: Any) -> bool:
        """Check for malicious content in string values"""
        if isinstance(obj, str):
            # Check for suspicious patterns
            suspicious_patterns = [
                r"<script[^>]*>.*?</script>",
                r"javascript:",
                r"vbscript:",
                r"on\w+\s*=",
                r"expression\s*\(",
                r"\beval\s*\(",
                r"\.\./\.\.",
                r"union\s+select",
                r"drop\s+table",
            ]

            text_lower = obj.lower()
            return any(
                re.search(pattern, text_lower, re.IGNORECASE)
                for pattern in suspicious_patterns
            )

        elif isinstance(obj, dict):
            return any(
                self._contains_malicious_content(value) for value in obj.values()
            )
        elif isinstance(obj, list):
            return any(self._contains_malicious_content(item) for item in obj)

        return False

    async def _log_validation_failure(self, request: Request, reason: str):
        """Log input validation failure"""
        await audit_service.log_security_event(
            event_type=AuditEventType.SECURITY_VALIDATION_FAILED,
            level=AuditLevel.WARNING,
            request=request,
            details={
                "reason": reason,
                "path": str(request.url.path),
                "method": request.method,
            },
        )
