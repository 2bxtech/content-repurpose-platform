# Content Transformation Platform

FastAPI backend with PostgreSQL multi-tenant architecture and content transformation API.

- **Multi-Tenant Architecture**: PostgreSQL Row-Level Security with workspace isolation, JWT authentication with refresh tokens
- **Transformation API**: Async implementation with document processing and workspace scoping
- **Background Processing**: Celery workers with Redis broker, task management, AI provider integration  
- **Real-Time Features**: WebSocket connections, transformation updates, Redis pub/sub messaging
- **Database**: SQLAlchemy async sessions with UUID handling, Alembic migrations, audit trails, soft deletes
- **Testing**: pytest framework with Docker automation, environment validation
- **Documentation**: Development insights, architectural patterns, testing approaches captured during implementation
- **Configuration**: Dependency injection, workspace context management, connection pooling

## Technology Stack

**API Layer**: FastAPI 0.104.1, Python 3.12+, OpenAPI documentation  
**Authentication**: JWT access (15min) + refresh (7day) tokens, BCrypt hashing, Redis session management  
**Database**: PostgreSQL 16 with Row-Level Security, SQLAlchemy async ORM, Alembic migrations  
**Background Processing**: Celery 5.3.4 workers, Redis 7-alpine broker, task status tracking  
**Real-Time**: WebSocket connections, Redis pub/sub messaging  
**AI Integration**: OpenAI/Anthropic providers with failover, rate limiting  
**Testing**: pytest with Docker isolation, multi-tenant testing, async API validation  
**Infrastructure**: Docker Compose orchestration, environment-based config, bytecode prevention  
**Documentation**: Development insights, architectural patterns, testing approaches

## System Architecture

Multi-tenant backend with async task processing, real-time WebSocket features, and workspace isolation:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  FastAPI        │    │  Celery Worker  │    │  PostgreSQL     │
│  • JWT Auth     │◄──►│  • Redis Broker │    │  • Row Level    │
│  • Workspace    │    │  • AI Tasks     │    │    Security     │
│  • WebSockets   │    │  • Status Track │    │  • Multi-tenant │
│  • OpenAPI      │    │  • Notifications│    │  • Async Driver │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         v                       v                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Redis       │    │   AI Providers  │    │   Testing       │
│  • Session Mgmt │    │  • OpenAI       │    │  • pytest       │
│  • Task Queue   │    │  • Anthropic    │    │  • Docker       │
│  • WebSocket    │    │  • Failover     │    │  • Validation   │
│  • Pub/Sub      │    │  • Rate Limits  │    │  • Auto-repair  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Implementation Status

### Phase 1-7 Complete
- **JWT Authentication**: Access/refresh token pattern, Redis session management, BCrypt hashing
- **Multi-Tenant Database**: PostgreSQL RLS policies, workspace isolation, audit trails, soft deletes  
- **Celery Background Processing**: Redis broker, task lifecycle tracking, AI provider integration
- **WebSocket Real-Time Features**: Live transformation updates, workspace presence, Redis pub/sub integration
- **Database Schema**: User/Document/Transformation models with workspace scoping, Alembic migrations
- **API Layer**: FastAPI with dependency injection, workspace context management, OpenAPI documentation
- **AI Provider Management**: Multi-provider system with OpenAI/Anthropic, automatic failover, cost tracking

### Phase 5b: Testing Framework Enhancement
- **Environment Validation**: Auto-detects missing dependencies and package structure issues
- **Docker Service Management**: Automated service orchestration with health checks
- **Test Discovery**: Phase-agnostic test execution with unit/integration/e2e categorization
- **Diagnostic Toolkit**: Root cause analysis with actionable solutions
- **Developer Setup**: One-command environment configuration

### Technical Implementation Details
- **Connection Pooling**: 20 base + 30 overflow connections for concurrent request handling
- **Task Management**: Real-time status tracking, cancellation support, worker monitoring endpoints
- **Multi-Provider AI**: OpenAI/Anthropic integration with automatic failover and rate limiting
- **Security**: Refresh token rotation, input validation, audit logging, workspace access control
- **Cross-Platform**: Windows/Linux compatible scripts, Git Bash support, Docker orchestration
- **WebSocket Implementation**: Redis pub/sub for multi-instance message broadcasting

### Phase 6-7: File Processing & AI Provider Management Complete
- **File Processing**: Enhanced PDF/DOCX parsing with security validation 
- **Multi-Provider AI System**: OpenAI/Anthropic integration with automatic failover
- **Cost Tracking**: Token usage monitoring and budget management per provider
- **Provider Management**: REST API for provider status, testing, and configuration

### Phase 8: Advanced Security & Monitoring (Complete)
- **Security Hardening**: Security headers, API rate limiting, secret management
- **Audit Logging**: Comprehensive logging for AI usage, costs, and user actions  
- **Health Monitoring**: Service health checks, metrics collection, alerting
- **Production Readiness**: Monitoring infrastructure and operational observability

### Phase 9: Deployment Patterns & Containerization (Complete)
- **Container Optimization**: Multi-stage Docker builds with production and development configurations
- **Environment Management**: Staging and production deployment with security hardening and configuration templates
- **Database Operations**: Cross-platform migration scripts with backup and recovery automation
- **Monitoring Infrastructure**: Complete observability stack with Prometheus, Grafana, AlertManager, and Jaeger
- **CI/CD Pipeline**: GitHub Actions with security scanning, quality gates, and automated deployment workflows
- **Production Optimization**: Performance-tuned PostgreSQL and Redis configurations with operational procedures

### Phase 10b: Transformation API & Documentation Complete ✅
- **Transformation API**: Async implementation with GET/POST endpoints, workspace scoping, and UUID handling
- **Multi-Tenant Data Access**: Workspace isolation with dependency injection patterns
- **Database Integration**: SQLAlchemy async implementation with UUID conversion and relationship handling
- **Debugging Documentation**: Systematic debugging approaches and Docker cache issue resolution
- **Architecture Documentation**: Technical insights covering async patterns, multi-tenancy, and performance considerations
- **Testing Documentation**: Testing patterns for async APIs, multi-tenant systems, and Docker environments
- **Development Reference**: Implementation insights and technical decision documentation

## Screenshots

The application includes working Dashboard and Document Detail pages:


### Dashboard View
Recent documents and transformations with API integration and workspace isolation.
<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/857bf259-276e-40f9-9989-ee6d922f30b6" />


### Document Detail View  
Document processing with transformation options and results display.
<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/08bcab8c-2f12-45e9-835d-3aee5914402d" />


### Transformation Results
Transformation workflow with multiple content types (summaries, bullets, headlines, social posts).
<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/885aeaed-e299-445e-8265-620fe91086e1" />

<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/2f115607-1fee-4df2-b1ec-8b0ed94b091e" />

<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/762f96c7-e14c-4948-814d-2317bcf5ed45" />

<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/a59d07d5-8313-4f86-b643-ac4b21d9fe70" />


### API Documentation
Swagger UI with transformation endpoints, authentication, and multi-tenant support.
<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/2b8248e4-c834-4503-becb-06a7b17f2e91" />


## Next Phase

### Phase 11: Frontend Enhancement & UX
- **Modern React Patterns**: Upgrade to hooks, context, suspense with TypeScript integration
- **Real-time Integration**: WebSocket frontend integration with live transformation updates
- **Professional UX**: Drag-and-drop uploads, loading states, animations, responsive design
- **Admin Dashboard**: System metrics, AI provider status, and monitoring integration
- **Accessibility**: Keyboard shortcuts, screen reader support, WCAG compliance

### Development Status
✅ **Phase 10b Complete**: Transformation API implemented with documentation  
🔄 **Current**: Working system with backend functionality  
⏭️ **Next**: Frontend modernization and user experience improvements

## Quick Start

### Prerequisites
- Python 3.12+
- Docker and Docker Compose
- AI API key (OpenAI or Anthropic)

### Setup
```bash
git clone https://github.com/2bxtech/content-repurpose.git
cd content-repurpose
cp .env.example .env
# Edit .env with your AI API key and database settings

# One-command setup (recommended)
python setup_dev_environment.py

# Manual setup
docker-compose up -d postgres redis
cd backend && python -m alembic upgrade head
```

### Testing and Validation
```bash
# Environment validation with auto-repair
python testing/run_tests.py --validate --fix

# Quick validation (< 1 second)
python testing/run_tests.py --quick-validate

# Full test suite
python testing/run_tests.py
```

### Development
```bash
# Start API server
cd backend && python main.py

# Start Celery worker (separate terminal)
cd backend && celery -A app.core.celery_app worker --loglevel=info
```

### API Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **WebSocket Endpoint**: ws://localhost:8000/api/ws

## Documentation

Technical insights and architectural patterns developed during Phase 10b implementation:

### Public Documentation
- **`docs/TECHNICAL_PATTERNS.md`**: FastAPI + SQLAlchemy async patterns, multi-tenant design, UUID handling
- **`docs/TESTING_PATTERNS.md`**: API testing patterns, multi-tenant validation, Docker testing approaches
- **`docs/DEVELOPMENT_COMMANDS.md`**: Command reference for debugging, Docker operations, and API testing

### Implementation Insights
- **Async Architecture Patterns**: SQLAlchemy async session configuration, relationship loading strategies
- **Multi-Tenant Design**: Workspace isolation, dependency injection patterns, security considerations  
- **UUID Integration**: Database query patterns, API response formatting, asyncpg handling
- **Docker Development**: Environment setup, cache management, testing strategies
- **API Testing**: Integration testing patterns, async validation, multi-tenant isolation
- **Performance Considerations**: Connection pooling, caching strategies, query optimization

### Key Technical Decisions
- SQLAlchemy async sessions with `expire_on_commit=False` for relationship handling
- UUID-first data model for horizontal scaling and security
- Workspace context injection for automatic tenant isolation
- Docker bytecode prevention for consistent development environments
- Testing patterns for async multi-tenant APIs

## Development

### Architecture Decisions
- **PostgreSQL RLS**: Chosen for automatic multi-tenant data isolation at database level
- **JWT + Redis Pattern**: Reduces database auth queries while maintaining stateless API design  
- **Celery Task Queue**: Prevents HTTP request blocking during AI processing operations
- **WebSocket + Redis Pub/Sub**: Enables real-time updates across multiple application instances
- **Docker-First Testing**: Ensures consistent test environments across development machines
- **Async-First Design**: SQLAlchemy async sessions with expire_on_commit=False for proper relationship handling
- **UUID-First Data Model**: Enables horizontal scaling and prevents ID enumeration attacks
- **Workspace Context Injection**: Enforces tenant isolation at the dependency injection level

### Environment Management
```bash
# Clone and setup
git clone https://github.com/2bxtech/content-repurpose.git
cd content-repurpose && cp .env.example .env

# Automated setup
python setup_dev_environment.py

# Validation and diagnostics
python testing/run_tests.py --validate --fix
python testing/run_tests.py --diagnose --fix
```

### Testing Framework
```bash
# Test execution
python testing/run_tests.py                     # Full test suite
python testing/run_tests.py --unit              # Unit tests only
python testing/run_tests.py --integration       # Integration tests only
python testing/run_tests.py --quick             # Fast validation tests

# WebSocket testing
python validate_phase5.py                       # Phase 5 validation
python test_phase5_automated.py                 # WebSocket integration tests

# Advanced testing patterns (see docs/TESTING_PATTERNS.md)
pytest tests/test_transformations.py -v         # Transformation API tests
pytest tests/test_multi_tenant.py -v            # Multi-tenant isolation tests  
pytest tests/test_async_patterns.py -v          # Async SQLAlchemy patterns
```

### Debugging and Development
```bash
# Environment validation with comprehensive checks
python setup_dev_environment.py                 # Enhanced environment setup
python testing/run_tests.py --validate --fix    # Auto-repair validation

# Debugging commands (see docs/DEVELOPMENT_COMMANDS.md)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/transformations/
docker-compose build --no-cache && docker-compose restart api
docker system prune -f && docker-compose up --build -d
```

## License

MIT License - see [LICENSE](LICENSE) file for details.
