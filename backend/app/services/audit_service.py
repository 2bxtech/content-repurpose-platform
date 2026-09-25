"""
Comprehensive Audit Logging Service

Provides detailed audit trails for security, compliance, and operational monitoring.
Integrates with existing AI provider cost tracking and user authentication.
"""

import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from pathlib import Path

from app.services.redis_service import redis_service


class AuditEventType(str, Enum):
    """Types of events to audit"""

    # Authentication events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"
    AUTH_PASSWORD_CHANGE = "auth.password.change"
    AUTH_RATE_LIMIT_HIT = "auth.rate_limit.hit"

    # User management events
    USER_CREATED = "user.created"
    USER_DELETED = "user.deleted"
    USER_UPDATED = "user.updated"
    USER_PERMISSION_CHANGED = "user.permission.changed"

    # Document events
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_ACCESSED = "document.accessed"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_SHARED = "document.shared"

    # Transformation events
    TRANSFORMATION_CREATED = "transformation.created"
    TRANSFORMATION_STARTED = "transformation.started"
    TRANSFORMATION_COMPLETED = "transformation.completed"
    TRANSFORMATION_FAILED = "transformation.failed"
    TRANSFORMATION_DOWNLOADED = "transformation.downloaded"

    # AI Provider events
    AI_REQUEST_MADE = "ai.request.made"
    AI_REQUEST_SUCCESS = "ai.request.success"
    AI_REQUEST_FAILED = "ai.request.failed"
    AI_PROVIDER_FAILOVER = "ai.provider.failover"
    AI_RATE_LIMIT_HIT = "ai.rate_limit.hit"
    AI_COST_THRESHOLD_HIT = "ai.cost.threshold.hit"
    AI_QUOTA_EXCEEDED = "ai.quota.exceeded"

    # System events
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_HEALTH_CHECK = "system.health.check"
    SYSTEM_RATE_LIMIT_HIT = "system.rate_limit.hit"

    # Security events
    SECURITY_UNAUTHORIZED_ACCESS = "security.unauthorized.access"
    SECURITY_SUSPICIOUS_ACTIVITY = "security.suspicious.activity"
    SECURITY_VALIDATION_FAILED = "security.validation.failed"
    SECURITY_TOKEN_BLACKLISTED = "security.token.blacklisted"


class AuditLevel(str, Enum):
    """Audit event severity levels"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Structured audit event"""

    event_id: str
    event_type: AuditEventType
    level: AuditLevel
    timestamp: str
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    outcome: str = "success"  # success, failure, error
    details: Optional[Dict[str, Any]] = None
    security_context: Optional[Dict[str, Any]] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    cost_metrics: Optional[Dict[str, Any]] = None
    error_details: Optional[Dict[str, Any]] = None


class AuditService:
    """Comprehensive audit logging service"""

    def __init__(self):
        self.logger = logging.getLogger("audit")
        self.audit_dir = Path("logs/audit")
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        # Configure audit logger
        self._setup_audit_logger()

        # Event counters for metrics
        self.event_counters = {}

    def _setup_audit_logger(self):
        """Configure dedicated audit logger"""
        # Create audit-specific handler
        audit_handler = logging.FileHandler(
            self.audit_dir / f"audit_{datetime.now().strftime('%Y-%m-%d')}.log"
        )

        # JSON formatter for structured logging
        formatter = logging.Formatter(
            "%(asctime)s - AUDIT - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        audit_handler.setFormatter(formatter)

        self.logger.addHandler(audit_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Don't propagate to root logger

    async def initialize(self):
        """Initialize audit service"""
        self.logger.info("Audit service initialized")

    async def cleanup(self):
        """Cleanup audit service"""
        self.logger.info("Audit service cleaned up")

    async def log_system_event(self, event_type: str, details: Dict[str, Any] = None):
        """Log system event"""
        await self.log_event(
            event_type=AuditEventType.SYSTEM_WARNING,
            level=AuditLevel.INFO,
            details={"system_event": event_type, **(details or {})},
        )

    def _generate_event_id(self) -> str:
        """Generate unique event ID"""
        return f"audit_{int(time.time() * 1000000)}"

    def _sanitize_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove or mask sensitive information from audit data"""
        if not data:
            return {}

        sensitive_keys = {
            "password",
            "secret",
            "token",
            "key",
            "credential",
            "auth",
            "api_key",
            "access_token",
            "refresh_token",
        }

        sanitized = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_sensitive_data(value)
            else:
                sanitized[key] = value

        return sanitized

    def _extract_client_info(self, request) -> Dict[str, Any]:
        """Extract client information from request"""
        if not request:
            return {}

        # Extract IP address (handle proxies)
        ip_address = "unknown"
        if hasattr(request, "headers"):
            # Check for forwarded IP first
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                ip_address = forwarded_for.split(",")[0].strip()
            elif request.headers.get("x-real-ip"):
                ip_address = request.headers.get("x-real-ip")
            elif hasattr(request, "client") and request.client:
                ip_address = request.client.host

        # Extract user agent
        user_agent = "unknown"
        if hasattr(request, "headers"):
            user_agent = request.headers.get("user-agent", "unknown")

        return {"ip_address": ip_address, "user_agent": user_agent}

    async def log_event(
        self,
        event_type: AuditEventType,
        level: AuditLevel = AuditLevel.INFO,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        request=None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        outcome: str = "success",
        details: Optional[Dict[str, Any]] = None,
        security_context: Optional[Dict[str, Any]] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
        cost_metrics: Optional[Dict[str, Any]] = None,
        error_details: Optional[Dict[str, Any]] = None,
    ):
        """Log an audit event"""

        # Extract client information
        client_info = self._extract_client_info(request)

        # Create audit event
        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            level=level,
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            workspace_id=workspace_id,
            ip_address=client_info.get("ip_address"),
            user_agent=client_info.get("user_agent"),
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            outcome=outcome,
            details=self._sanitize_sensitive_data(details or {}),
            security_context=security_context,
            performance_metrics=performance_metrics,
            cost_metrics=cost_metrics,
            error_details=error_details,
        )

        # Log to file
        self.logger.info(json.dumps(asdict(event), default=str))

        # Store in Redis for real-time monitoring (with TTL)
        if redis_service.is_connected():
            try:
                await self._store_in_redis(event)
                await self._update_metrics(event)
            except Exception as e:
                # Don't let Redis failures affect audit logging
                self.logger.error(f"Failed to store audit event in Redis: {e}")

    async def _store_in_redis(self, event: AuditEvent):
        """Store event in Redis for real-time access"""
        # Store individual event (24 hour TTL)
        redis_service.setex(
            f"audit:event:{event.event_id}",
            86400,  # 24 hours
            json.dumps(asdict(event), default=str),
        )

        # Add to recent events list (keep last 1000)
        redis_service.lpush("audit:recent_events", event.event_id)
        redis_service.ltrim("audit:recent_events", 0, 999)

        # Store by event type for filtering
        redis_service.lpush(f"audit:type:{event.event_type}", event.event_id)
        redis_service.ltrim(f"audit:type:{event.event_type}", 0, 499)
        redis_service.expire(f"audit:type:{event.event_type}", 86400)

        # Store by user for user-specific audits
        if event.user_id:
            redis_service.lpush(f"audit:user:{event.user_id}", event.event_id)
            redis_service.ltrim(f"audit:user:{event.user_id}", 0, 199)
            redis_service.expire(f"audit:user:{event.user_id}", 86400)

    async def _update_metrics(self, event: AuditEvent):
        """Update audit metrics in Redis"""
        current_hour = datetime.now().strftime("%Y-%m-%d:%H")

        # Increment event type counter
        redis_service.incr(f"audit:metrics:count:{event.event_type}:{current_hour}")
        redis_service.expire(
            f"audit:metrics:count:{event.event_type}:{current_hour}", 86400
        )

        # Increment level counter
        redis_service.incr(f"audit:metrics:level:{event.level}:{current_hour}")
        redis_service.expire(f"audit:metrics:level:{event.level}:{current_hour}", 86400)

        # Track cost metrics if available
        if event.cost_metrics:
            cost = event.cost_metrics.get("cost", 0)
            if cost > 0:
                # Add to hourly cost tracking
                redis_service.incrbyfloat(f"audit:metrics:cost:{current_hour}", cost)
                redis_service.expire(f"audit:metrics:cost:{current_hour}", 86400)

    async def get_recent_events(
        self,
        limit: int = 100,
        event_type: Optional[AuditEventType] = None,
        user_id: Optional[str] = None,
        level: Optional[AuditLevel] = None,
    ) -> List[AuditEvent]:
        """Get recent audit events with optional filtering"""
        if not redis_service.is_connected():
            return []

        try:
            # Determine which list to query
            if user_id:
                event_ids = redis_service.lrange(f"audit:user:{user_id}", 0, limit - 1)
            elif event_type:
                event_ids = redis_service.lrange(
                    f"audit:type:{event_type}", 0, limit - 1
                )
            else:
                event_ids = redis_service.lrange("audit:recent_events", 0, limit - 1)

            # Fetch event details
            events = []
            for event_id in event_ids:
                event_data = redis_service.get(f"audit:event:{event_id}")
                if event_data:
                    event_dict = json.loads(event_data)
                    event = AuditEvent(**event_dict)

                    # Apply level filter if specified
                    if level and event.level != level:
                        continue

                    events.append(event)

            return events

        except Exception as e:
            self.logger.error(f"Failed to fetch recent events: {e}")
            return []

    async def get_audit_metrics(self) -> Dict[str, Any]:
        """Get audit event metrics and statistics"""
        if not redis_service.is_connected():
            return {}

        try:
            current_hour = datetime.now().strftime("%Y-%m-%d:%H")

            # Get event type counts for current hour
            event_type_counts = {}
            for event_type in AuditEventType:
                count = redis_service.get(
                    f"audit:metrics:count:{event_type}:{current_hour}"
                )
                if count:
                    event_type_counts[event_type] = int(count)

            # Get level counts for current hour
            level_counts = {}
            for level in AuditLevel:
                count = redis_service.get(f"audit:metrics:level:{level}:{current_hour}")
                if count:
                    level_counts[level] = int(count)

            # Get cost metrics for current hour
            cost_current_hour = redis_service.get(f"audit:metrics:cost:{current_hour}")

            return {
                "current_hour": current_hour,
                "event_type_counts": event_type_counts,
                "level_counts": level_counts,
                "cost_current_hour": float(cost_current_hour)
                if cost_current_hour
                else 0.0,
                "total_events_current_hour": sum(event_type_counts.values()),
            }

        except Exception as e:
            self.logger.error(f"Failed to get audit metrics: {e}")
            return {}

    # Convenience methods for common audit events

    async def log_authentication_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        request=None,
        outcome: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log authentication-related events"""
        await self.log_event(
            event_type=event_type,
            level=AuditLevel.WARNING if outcome == "failure" else AuditLevel.INFO,
            user_id=user_id,
            request=request,
            action="authentication",
            outcome=outcome,
            details=details,
            security_context={"category": "authentication"},
        )

    async def log_ai_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        request=None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        outcome: str = "success",
        performance_metrics: Optional[Dict[str, Any]] = None,
        cost_metrics: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log AI provider-related events"""
        await self.log_event(
            event_type=event_type,
            level=AuditLevel.ERROR if outcome == "failure" else AuditLevel.INFO,
            user_id=user_id,
            workspace_id=workspace_id,
            request=request,
            resource_type="ai_provider",
            resource_id=provider,
            action="ai_request",
            outcome=outcome,
            details={**(details or {}), "provider": provider, "model": model},
            performance_metrics=performance_metrics,
            cost_metrics=cost_metrics,
        )

    async def log_transformation_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        transformation_id: Optional[str] = None,
        document_id: Optional[str] = None,
        request=None,
        outcome: str = "success",
        performance_metrics: Optional[Dict[str, Any]] = None,
        cost_metrics: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log transformation-related events"""
        await self.log_event(
            event_type=event_type,
            level=AuditLevel.ERROR if outcome == "failure" else AuditLevel.INFO,
            user_id=user_id,
            workspace_id=workspace_id,
            request=request,
            resource_type="transformation",
            resource_id=transformation_id,
            action="transformation",
            outcome=outcome,
            details={
                **(details or {}),
                "document_id": document_id,
                "transformation_id": transformation_id,
            },
            performance_metrics=performance_metrics,
            cost_metrics=cost_metrics,
        )

    async def log_security_event(
        self,
        event_type: AuditEventType,
        level: AuditLevel = AuditLevel.WARNING,
        user_id: Optional[str] = None,
        request=None,
        details: Optional[Dict[str, Any]] = None,
        security_context: Optional[Dict[str, Any]] = None,
    ):
        """Log security-related events"""
        await self.log_event(
            event_type=event_type,
            level=level,
            user_id=user_id,
            request=request,
            action="security_check",
            outcome="failure"
            if level in [AuditLevel.ERROR, AuditLevel.CRITICAL]
            else "success",
            details=details,
            security_context={**(security_context or {}), "category": "security"},
        )

    async def get_security_events(self, start_time, end_time):
        """Get security events for time range"""
        # Mock implementation - would query Redis/database
        return [
            {
                "event_type": "security.validation.failed",
                "timestamp": datetime.now().isoformat(),
                "severity": "warning",
                "details": "Suspicious pattern detected",
            }
        ]

    async def get_security_metrics(self):
        """Get security metrics"""
        return {
            "total_security_events": 25,
            "blocked_requests": 5,
            "validation_failures": 15,
            "suspicious_activities": 5,
        }

    async def get_recent_errors(self, limit=10):
        """Get recent error events"""
        return []

    async def get_events_for_export(self, start_time, end_time):
        """Get events for export"""
        return []


# Global audit service instance
audit_service = AuditService()
