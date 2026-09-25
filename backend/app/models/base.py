"""
Base models for Content Repurpose API
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from enum import Enum


class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class APIResponse(BaseModel):
    """Generic API response wrapper"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    errors: Optional[List[str]] = None


class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class HealthCheck(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    checks: Dict[str, str]


class WorkerStatus(BaseModel):
    worker_name: str
    status: str
    active_tasks: int
    processed_tasks: int
    load_average: List[float]


class QueueInfo(BaseModel):
    queue_name: str
    pending_tasks: int
    active_tasks: int
    failed_tasks: int


class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


class RateLimitInfo(BaseModel):
    allowed: bool
    remaining: int
    reset_time: int
    limit_type: str


class AIProviderConfig(BaseModel):
    provider: str
    model: str
    max_tokens: int
    temperature: float
    api_key_configured: bool


class AIUsageStats(BaseModel):
    provider: str
    requests_count: int
    tokens_used: int
    cost_estimate: float
    avg_response_time: float