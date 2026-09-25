# Technical Patterns and Architecture

*Key architectural patterns and technical decisions for FastAPI + SQLAlchemy async applications*

## Overview

This document outlines the technical patterns and architectural decisions implemented in the content transformation platform, focusing on async FastAPI applications with multi-tenant architecture.

## Core Architecture Patterns

### 1. Async-First Design
All layers designed to be async-native from the start to avoid greenlet errors and performance issues.

```python
# Async endpoint with async dependencies
@router.get("/")
async def get_transformations(
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> TransformationListResponse:
    async with db:
        stmt = select(TransformationDB).where(
            TransformationDB.workspace_id == current_user.workspace_id
        )
        result = await db.execute(stmt)
        transformations = result.scalars().all()
    
    return TransformationListResponse(
        transformations=[transformation_to_response(t) for t in transformations],
        count=len(transformations)
    )
```

### 2. Multi-Tenant Data Isolation
Enforce tenant isolation at the database query level to prevent data leakage.

```python
# Workspace-aware queries
async def get_user_documents(
    db: AsyncSession, 
    user_id: str,
    workspace_id: str
) -> List[DocumentDB]:
    stmt = select(DocumentDB).where(
        and_(
            DocumentDB.user_id == user_id,
            DocumentDB.workspace_id == workspace_id  # Critical filter
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()
```

### 3. UUID-First Data Model
Use UUIDs for all primary keys and foreign keys to enable horizontal scaling and prevent ID enumeration attacks.

```python
class DocumentDB(Base):
    __tablename__ = "documents"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("workspaces.id"), 
        nullable=False
    )
```

## SQLAlchemy Async Configuration

### Session Configuration
Critical async session configuration to prevent lazy loading errors:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    echo=DEBUG,
    pool_pre_ping=True,
    pool_recycle=3600
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # CRITICAL: Prevents lazy loading issues
    autoflush=False,
    autocommit=False
)
```

### UUID Conversion Patterns
asyncpg returns UUID objects that need string conversion for JSON serialization:

```python
def transformation_to_response(transformation: TransformationDB) -> TransformationResponse:
    return TransformationResponse(
        id=str(transformation.id),  # Convert UUID to string
        user_id=str(transformation.user_id),
        workspace_id=str(transformation.workspace_id),
        # ... other fields
    )
```

## FastAPI Dependency Injection

### Workspace Context Injection
Inject workspace context into all protected endpoints:

```python
async def get_current_user_workspace(
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> WorkspaceContext:
    stmt = select(UserDB).options(
        selectinload(UserDB.workspace)
    ).where(UserDB.id == current_user.id)
    
    result = await db.execute(stmt)
    user_with_workspace = result.scalar_one()
    
    return WorkspaceContext(
        user=user_with_workspace,
        workspace=user_with_workspace.workspace,
        workspace_id=str(user_with_workspace.workspace_id)
    )
```

## Authentication & Authorization

### JWT Token Pattern
Stateless JWT with workspace context:

```python
def create_access_token(user: UserDB) -> str:
    payload = {
        "sub": str(user.id),
        "workspace_id": str(user.workspace_id),  # Include workspace
        "email": user.email,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
```

## Docker Configuration

### Environment Variables
Critical Docker environment variables for Python applications:

```dockerfile
# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
```

### Multi-Stage Builds
Optimize Docker builds for development and production:

```dockerfile
# Development stage
FROM python:3.12-slim as development
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
# ... development setup

# Production stage  
FROM python:3.12-slim as production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# ... production optimizations
```

## CORS Configuration

### Environment-Aware CORS
CORS configuration with security headers:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        # ... other headers
    ],
    max_age=3600,
)
```

## Performance Optimization

### Database Query Optimization
Optimize N+1 queries with proper loading strategies:

```python
# Use selectinload for one-to-many relationships
stmt = select(DocumentDB).options(
    selectinload(DocumentDB.transformations)
).where(
    and_(
        DocumentDB.workspace_id == workspace_id,
        DocumentDB.user_id == user_id
    )
).order_by(DocumentDB.created_at.desc())
```

### Connection Pooling
Proper async connection pool configuration:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600
)
```

## Key Technical Decisions

### Architecture Principles
1. **Async-First Design**: All layers async-native to prevent greenlet errors
2. **Multi-Tenant by Default**: Workspace filtering enforced at query level
3. **UUID-First**: Horizontal scaling and security from the start
4. **Dependency Injection**: Workspace context automatically injected
5. **Docker-First Development**: Consistent environments across development machines

### Performance Considerations
1. **expire_on_commit=False**: Prevents async relationship loading issues
2. **Explicit Relationship Loading**: selectinload/joinedload instead of lazy loading
3. **Connection Pooling**: Proper async pool sizing for concurrent requests
4. **UUID String Conversion**: Handle asyncpg UUID objects at API boundaries

### Security Patterns
1. **Workspace Isolation**: Multi-tenant data separation at database level
2. **JWT with Context**: Include workspace information in tokens
3. **Input Validation**: Comprehensive Pydantic validation
4. **Security Headers**: CORS and security middleware configuration

---

*This document focuses on reusable technical patterns and architectural decisions that can be applied to similar FastAPI + SQLAlchemy async applications.*