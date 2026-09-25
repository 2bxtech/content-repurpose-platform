# backend/main.py
# Production-grade FastAPI application with comprehensive CORS handling

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import os
import re
import time
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db, close_db, database_health_check
from app.middleware.rate_limit import RateLimitMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def is_origin_allowed(origin: str) -> bool:
    """Check an Origin header against CORS_ORIGINS (exact) and CORS_ORIGIN_REGEX (pattern).

    The regex exists for platforms like Vercel that mint a new preview URL on
    every deploy — CORS_ORIGINS alone would need a manual update each time.
    """
    if origin in settings.CORS_ORIGINS:
        return True
    if settings.CORS_ORIGIN_REGEX and re.match(settings.CORS_ORIGIN_REGEX, origin):
        return True
    return False


class EnhancedCORSMiddleware(BaseHTTPMiddleware):
    """
    Enhanced CORS middleware that ensures CORS headers are present on ALL responses,
    including error responses that might bypass the standard CORS middleware
    """

    async def dispatch(self, request: Request, call_next):
        # Get the origin from the request
        origin = request.headers.get("origin")

        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = JSONResponse({"message": "OK"})
            if origin and is_origin_allowed(origin):
                response.headers["access-control-allow-origin"] = origin
                response.headers["access-control-allow-credentials"] = "true"
                response.headers["access-control-allow-methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                response.headers["access-control-allow-headers"] = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
                response.headers["access-control-max-age"] = "3600"
            return response

        # Process the request
        response = await call_next(request)

        # Add CORS headers if they're missing and origin is allowed
        if origin and is_origin_allowed(origin):
            if "access-control-allow-origin" not in response.headers:
                response.headers["access-control-allow-origin"] = origin
            if "access-control-allow-credentials" not in response.headers:
                response.headers["access-control-allow-credentials"] = "true"
            if "vary" not in response.headers:
                response.headers["vary"] = "Origin"

        return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("🚀 Starting Content Repurpose API v3.0.0")
    
    # Initialize database
    if settings.ENVIRONMENT == "development":
        try:
            await init_db()
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ Database initialization failed: {e}")
    
    # Test database connection
    try:
        health = await database_health_check()
        if health["status"] == "healthy":
            logger.info("✅ Database connection verified")
        else:
            logger.warning(f"⚠️ Database health check: {health['message']}")
    except Exception as e:
        logger.warning(f"⚠️ Database health check failed: {e}")
    
    # Test Redis (if available)
    try:
        from app.services.redis_service import redis_service
        await redis_service.health_check()
        logger.info("✅ Redis connection verified")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection failed: {e}")
    
    yield
    
    # Shutdown
    try:
        await close_db()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.warning(f"⚠️ Database cleanup failed: {e}")
    
    logger.info("🛑 Content Repurpose API shutdown complete")

# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-grade API for AI-powered content transformation with multi-tenant support",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Add standard CORS middleware first
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add enhanced CORS middleware for error responses
app.add_middleware(EnhancedCORSMiddleware)
app.add_middleware(RateLimitMiddleware)

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time and request ID headers"""
    start_time = time.time()
    
    # Add request ID for tracking
    import uuid
    request_id = str(uuid.uuid4())[:8]
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"
    response.headers["X-Request-ID"] = request_id
    
    return response

# Enhanced global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with guaranteed CORS headers"""
    content = {"detail": exc.detail}
    if settings.DEBUG:
        content["status_code"] = exc.status_code
        content["path"] = str(request.url)
    
    response = JSONResponse(
        status_code=exc.status_code,
        content=content
    )
    
    # Ensure CORS headers are present
    origin = request.headers.get("origin")
    if origin and is_origin_allowed(origin):
        response.headers["access-control-allow-origin"] = origin
        response.headers["access-control-allow-credentials"] = "true"
        response.headers["access-control-allow-methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["access-control-allow-headers"] = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
        response.headers["vary"] = "Origin"
    
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with CORS support and detailed logging"""
    # Log the full exception with context
    logger.error(
        f"Unhandled exception in {request.method} {request.url}: {exc}",
        exc_info=True,
        extra={
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "exception_type": type(exc).__name__
        }
    )
    
    # Prepare response content
    if settings.DEBUG:
        content = {
            "error": "Internal server error",
            "detail": str(exc),
            "type": type(exc).__name__,
            "path": str(request.url)
        }
    else:
        content = {"error": "Internal server error"}
    
    response = JSONResponse(
        status_code=500,
        content=content
    )
    
    # Ensure CORS headers are present even for 500 errors
    origin = request.headers.get("origin")
    if origin and is_origin_allowed(origin):
        response.headers["access-control-allow-origin"] = origin
        response.headers["access-control-allow-credentials"] = "true"
        response.headers["access-control-allow-methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["access-control-allow-headers"] = "Content-Type, Authorization, Accept, Origin, X-Requested-With"
        response.headers["vary"] = "Origin"
    
    return response

# Root endpoint
@app.get("/")
async def root():
    """API root with comprehensive information"""
    return {
        "message": settings.PROJECT_NAME,
        "status": "running",
        "version": "3.0.0",
        "environment": settings.ENVIRONMENT,
        "endpoints": {
            "auth": "/api/auth",
            "transformations": "/api/transformations",
            "documents": "/api/documents",
            "health": "/api/health"
        },
        "features": [
            "JWT Authentication",
            "Multi-tenant Support",
            "Async Database Operations",
            "Comprehensive Error Handling",
            "CORS-Enabled API",
            "Production-Grade Logging",
            "AI Content Transformations"
        ]
    }

# Debug endpoint to list all routes
@app.get("/api/debug/routes")
async def list_routes():
    """List all registered routes for debugging"""
    routes_info = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            routes_info.append({
                "path": route.path,
                "methods": list(route.methods) if route.methods else [],
                "name": route.name if hasattr(route, "name") else "unknown"
            })
    return {"total": len(routes_info), "routes": routes_info}

# Enhanced health check endpoint
@app.get("/api/health")
async def health():
    """Comprehensive health check with detailed component status"""
    health_status = {
        "status": "healthy",
        "service": "content-repurpose-api",
        "version": "3.0.0",
        "environment": settings.ENVIRONMENT,
        "timestamp": time.time(),
        "checks": {}
    }
    
    # Database health check
    try:
        db_health = await database_health_check()
        health_status["checks"]["database"] = db_health
        if db_health["status"] != "healthy":
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "error",
            "message": str(e)
        }
        health_status["status"] = "degraded"
    
    # Redis health check
    try:
        from app.services.redis_service import redis_service
        await redis_service.health_check()
        health_status["checks"]["redis"] = {"status": "healthy", "message": "Connected"}
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "degraded",
            "message": f"Connection failed: {str(e)}"
        }
        # Redis is optional, don't mark overall status as degraded
    
    # AI provider readiness. Report registration/availability only; never expose
    # credentials or raw provider errors through this public endpoint.
    try:
        from app.services.ai_providers.manager import get_ai_provider_manager

        provider_manager = get_ai_provider_manager()
        providers = {
            name: {
                "enabled": provider_manager.provider_configs[name].enabled,
                "available": provider.is_available(),
            }
            for name, provider in provider_manager.providers.items()
        }
        real_provider_available = any(
            info["enabled"] and info["available"]
            for name, info in providers.items()
            if name != "mock"
        )
        health_status["checks"]["ai_provider"] = {
            "status": "healthy" if real_provider_available else "unhealthy",
            "providers": providers,
            "real_provider_available": real_provider_available,
        }
        if settings.ENVIRONMENT.lower() == "production" and not real_provider_available:
            health_status["status"] = "degraded"
    except Exception:
        logger.exception("AI provider health check failed")
        health_status["checks"]["ai_provider"] = {"status": "error"}
        health_status["status"] = "degraded"
    
    return health_status

# Include routers with comprehensive error handling
routers_loaded = []

try:
    from app.api.routes.auth import router as auth_router
    app.include_router(auth_router, prefix="/api/auth", tags=["authentication"])
    routers_loaded.append("auth")
    logger.info("✅ Auth router loaded successfully")
except Exception as e:
    logger.error(f"❌ Failed to load auth router: {e}")

try:
    from app.api.routes.transformations import router as transformations_router
    app.include_router(transformations_router, prefix="/api/transformations", tags=["transformations"])
    routers_loaded.append("transformations")
    logger.info("✅ Transformations router loaded successfully")
except Exception as e:
    logger.error(f"❌ Failed to load transformations router: {e}")

try:
    from app.api.routes.transformation_presets import router as transformation_presets_router
    logger.info(f"📋 Transformation Presets router has {len(transformation_presets_router.routes)} routes")
    app.include_router(transformation_presets_router, prefix="/api/transformation-presets", tags=["transformation-presets"])
    routers_loaded.append("transformation-presets")
    logger.info("✅ Transformation Presets router loaded successfully")
except Exception as e:
    logger.error(f"❌ Failed to load transformation presets router: {e}", exc_info=True)

try:
    from app.api.routes.documents import router as documents_router
    app.include_router(documents_router, prefix="/api", tags=["documents"])
    routers_loaded.append("documents")
    logger.info("✅ Documents router loaded successfully")
except Exception as e:
    logger.error(f"❌ Failed to load documents router: {e}")

# Optional routers
try:
    from app.api.routes.workspaces import router as workspaces_router
    app.include_router(workspaces_router, prefix="/api", tags=["workspaces"])
    routers_loaded.append("workspaces")
    logger.info("✅ Workspaces router loaded successfully")
except Exception as e:
    logger.debug(f"Workspaces router not available: {e}")

# Startup logging
@app.on_event("startup")
async def log_startup_info():
    """Log comprehensive startup information"""
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.PROJECT_NAME} v3.0.0 - STARTUP COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"CORS Origins: {settings.CORS_ORIGINS}")
    logger.info(f"Loaded Routers: {', '.join(routers_loaded)}")
    
    # Log all registered routes
    logger.info("📋 REGISTERED API ROUTES:")
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = ", ".join(sorted(route.methods)) if route.methods else "N/A"
            auth_indicator = "🔐" if "/auth" not in route.path and route.path not in ["/", "/api/health"] else "🔓"
            logger.info(f"  {methods:20} {route.path:40} {auth_indicator}")
    
    logger.info("=" * 60)

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"""
    🚀 {settings.PROJECT_NAME} v3.0.0 - Production Mode
    📍 URL: http://localhost:{port}
    🔐 Authentication: JWT Bearer Token Required
    🏢 Multi-tenant: Workspace-based isolation
    ⚡ Async Operations: SQLAlchemy + AsyncPG
    🛡️  CORS: Comprehensive cross-origin support
    🤖 AI Provider: {settings.AI_PROVIDER}
    
    Quick Start:
    1. Register: POST /api/auth/register
    2. Login: POST /api/auth/token  
    3. Upload: POST /api/documents
    4. Transform: POST /api/transformations
    
    Test Transformation:
    curl -X POST http://localhost:{port}/api/transformations \\
      -H "Content-Type: application/json" \\
      -H "Origin: http://localhost:3000" \\
      -H "Authorization: Bearer <your-jwt-token>" \\
      -d '{{"document_id": "<uuid>", "transformation_type": "SUMMARY", "parameters": {{}}}}'
    
    Health Check: GET /api/health
    """)
    
    uvicorn.run(
        "main:app", 
        host=host, 
        port=port, 
        reload=settings.DEBUG,
        log_level="info" if settings.ENVIRONMENT == "production" else "debug",
        access_log=True
    )
