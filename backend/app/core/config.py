import os
from pathlib import Path
from typing import Annotated, List, Set, Optional
from urllib.parse import quote
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    PROJECT_NAME: str = "Content Repurposing Tool"
    API_V1_STR: str = "/api/v1"

    # Security: Production-grade JWT settings
    SECRET_KEY: str = Field(..., min_length=32)
    REFRESH_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Short-lived access tokens
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7-day refresh tokens

    # Password security
    PASSWORD_MIN_LENGTH: int = 12
    BCRYPT_ROUNDS: int = 12

    # Session management
    MAX_SESSIONS_PER_USER: int = 5

    # Rate limiting
    RATE_LIMIT_AUTH_ATTEMPTS: str = "5/15m"  # 5 attempts per 15 minutes
    RATE_LIMIT_API_CALLS: str = "100/1m"  # 100 calls per minute
    RATE_LIMIT_TRANSFORMATIONS: str = "30/1h"  # 30 transformations per hour
    TRUST_PROXY_HEADERS: bool = False

    # Comma-separated user IDs allowed to use operator endpoints (global AI provider
    # config, cost data, connection stats). Empty = nobody. IDs rather than emails:
    # registration doesn't verify email ownership, so an email allowlist could be
    # claimed by whoever registers the address first.
    PLATFORM_ADMIN_USER_IDS: str = ""

    @property
    def platform_admin_user_ids(self) -> Set[str]:
        return {u.strip().lower() for u in self.PLATFORM_ADMIN_USER_IDS.split(",") if u.strip()}

    # Redis settings for session management and rate limiting
    # REDIS_URL takes priority (Railway provides this as a single URL)
    REDIS_URL: Optional[str] = Field(default=None, description="Full Redis URL, e.g. redis://:password@host:6379")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # Celery settings for background task processing
    CELERY_BROKER_URL: str = Field(default="")
    CELERY_RESULT_BACKEND: str = Field(default="")
    # "celery": POST /api/transformations enqueues to a worker (default).
    # "inline": run the AI call in-request, for local runs without a worker.
    TRANSFORMATION_EXECUTION: str = Field(default="celery", pattern="^(celery|inline)$")

    def get_redis_url(self) -> str:
        """REDIS_URL if set, otherwise built from the REDIS_* components."""
        if self.REDIS_URL:
            return self.REDIS_URL
        auth = f":{quote(self.REDIS_PASSWORD, safe='')}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def get_celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.get_redis_url()

    def get_celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.get_redis_url()

    # AI Provider Configuration (Enhanced multi-provider support with failover)
    AI_PROVIDER: str = Field(
        default="openai", pattern="^(openai|anthropic|azure|local|mock)$"
    )

    # AI API Keys (configure based on chosen provider)
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    CLAUDE_API_KEY: str = Field(default="", description="Anthropic Claude API key")
    AZURE_OPENAI_API_KEY: str = Field(default="", description="Azure OpenAI API key")
    AZURE_OPENAI_ENDPOINT: str = Field(default="", description="Azure OpenAI endpoint")

    # AI Model Configuration
    DEFAULT_AI_MODEL: str = Field(
        default="gpt-4o-mini", description="Default AI model to use"
    )
    AI_MAX_TOKENS: int = Field(
        default=4000, description="Maximum tokens per AI request"
    )
    AI_TEMPERATURE: float = Field(
        default=0.7, ge=0.0, le=2.0, description="AI response creativity"
    )

    # Enhanced AI Provider Management
    AI_PROVIDER_SELECTION_STRATEGY: str = Field(
        default="primary_failover", description="Provider selection strategy"
    )
    AI_ENABLE_FAILOVER: bool = Field(
        default=True, description="Enable automatic provider failover"
    )
    AI_COST_TRACKING: bool = Field(
        default=True, description="Enable cost tracking and limits"
    )
    AI_RATE_LIMITING: bool = Field(
        default=True, description="Enable per-provider rate limiting"
    )

    # AI Cost Management
    AI_MAX_COST_PER_HOUR: float = Field(
        default=10.0, description="Maximum cost per hour across all providers"
    )
    AI_MAX_REQUESTS_PER_MINUTE: int = Field(
        default=60, description="Maximum requests per minute per provider"
    )
    AI_BUDGET_ALERT_THRESHOLD: float = Field(
        default=0.8, description="Alert when budget reaches this percentage"
    )

    # AI Performance Monitoring
    AI_RESPONSE_TIME_THRESHOLD_MS: int = Field(
        default=30000, description="Response time threshold for provider health"
    )
    AI_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=45.0,
        gt=0,
        le=300,
        description="Hard timeout for each provider API attempt",
    )
    AI_MAX_RETRIES: int = Field(
        default=2,
        ge=0,
        le=5,
        description="SDK retries for transient provider failures",
    )
    AI_ERROR_RATE_THRESHOLD: float = Field(
        default=0.1, description="Error rate threshold for provider health"
    )
    AI_PERFORMANCE_WINDOW_MINUTES: int = Field(
        default=60, description="Performance monitoring window"
    )

    # Database settings
    DATABASE_HOST: str = Field(default="localhost")
    DATABASE_PORT: int = Field(default=5433)
    DATABASE_NAME: str = Field(default="content_repurpose")
    DATABASE_USER: str = Field(default="postgres")
    DATABASE_PASSWORD: str = Field(default="postgres")
    DATABASE_URL: Optional[str] = Field(default=None)

    # Sync database URL for Alembic migrations
    DATABASE_URL_SYNC: Optional[str] = Field(default=None)
    SQL_ECHO: bool = False  # log every SQL statement (noisy; for debugging only)

    def get_database_url(self, async_driver: bool = True) -> str:
        """Construct database URL if not provided.

        Railway (and Heroku-style platforms) provide DATABASE_URL as
        'postgresql://...' or 'postgres://...'. SQLAlchemy's async engine
        requires 'postgresql+asyncpg://'. This method normalises the scheme.
        """
        if async_driver:
            url = self.DATABASE_URL or ""
            if url:
                # Normalise to asyncpg scheme
                if url.startswith("postgres://"):
                    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
                elif url.startswith("postgresql://"):
                    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
                elif not url.startswith("postgresql+asyncpg://"):
                    url = f"postgresql+asyncpg://{url}"
                return url
        else:
            if self.DATABASE_URL_SYNC:
                return self.DATABASE_URL_SYNC
            if self.DATABASE_URL:
                # Strip asyncpg prefix for sync (Alembic/psycopg2)
                url = self.DATABASE_URL
                url = url.replace("postgresql+asyncpg://", "postgresql://")
                url = url.replace("postgres://", "postgresql://")
                return url

        # Construct from components
        driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
        return f"{driver}://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"

    # CORS settings
    # NoDecode: pydantic-settings otherwise JSON-decodes List-typed env vars itself,
    # at the source level, before parse_cors_origins ever runs — which crashes on
    # both a plain comma-separated string and an unset/empty value. NoDecode hands
    # the raw string to the validator below instead.
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8000", 
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:8000",
            "http://0.0.0.0:3000",
            "http://0.0.0.0:3001",
            "http://0.0.0.0:8000"
        ]
    )

    # Regex matched against Origin as a fallback when it's not in CORS_ORIGINS —
    # for platforms like Vercel that mint a new preview URL on every deploy.
    # Example: ^https://content-repurpose-[a-zA-Z0-9-]+-2bxtechno\.vercel\.app$
    CORS_ORIGIN_REGEX: Optional[str] = Field(default=None)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS_ORIGINS from environment variable.

        Accepts two formats:
          JSON array (Railway / pydantic-settings v2 preferred):
            CORS_ORIGINS=["https://app.vercel.app","http://localhost:3000"]
          Comma-separated string (legacy / local .env):
            CORS_ORIGINS=https://app.vercel.app,http://localhost:3000
        """
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(o).strip() for o in parsed if str(o).strip()]
                except (json.JSONDecodeError, ValueError):
                    pass
            # Comma-separated fallback
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # File upload settings
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: Set[str] = {"pdf", "docx", "txt", "md"}

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_mode(cls, value):
        """Treat deployment labels as non-debug instead of failing startup."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod"}:
                return False
            if normalized in {"development", "dev"}:
                return True
        return value

    @field_validator("SECRET_KEY", "REFRESH_SECRET_KEY")
    @classmethod
    def validate_secret_keys(cls, v):
        if len(v) < 32:
            raise ValueError("Secret keys must be at least 32 characters long")
        return v

    @field_validator("PASSWORD_MIN_LENGTH")
    @classmethod
    def validate_password_length(cls, v):
        if v < 8:
            raise ValueError("Password minimum length must be at least 8")
        return v

    class Config:
        # Repo-root .env (commands often run from backend/), then a local override.
        # In the container neither exists and real env vars are used.
        env_file = (str(Path(__file__).resolve().parents[3] / ".env"), ".env")
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env file


settings = Settings()
