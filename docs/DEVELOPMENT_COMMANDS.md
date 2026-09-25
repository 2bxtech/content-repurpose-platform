# Development Commands Reference

*Common commands and procedures for FastAPI development with Docker*

## Overview

This document provides a reference of development commands for working with FastAPI applications in Docker environments, focusing on debugging and validation procedures.

## Environment Setup

### Initial Setup
```bash
# Clone and setup
git clone <repository-url>
cd content-repurpose
cp .env.example .env
# Edit .env with your configuration

# Automated environment setup
python setup_dev_environment.py

# Manual Docker setup
docker-compose up -d postgres redis
cd backend && python -m alembic upgrade head
```

### Environment Validation
```bash
# Quick environment validation
python setup_dev_environment.py --validate

# Full validation with auto-repair
python testing/run_tests.py --validate --fix

# Check service health
curl http://localhost:8000/health
```

## Docker Operations

### Container Management
```bash
# Start services
docker-compose up -d

# Restart specific service
docker-compose restart api

# View logs
docker-compose logs api
docker-compose logs -f api  # Follow logs

# Stop services
docker-compose down
docker-compose down -v  # Remove volumes
```

### Building and Cache Management
```bash
# Build with cache
docker-compose build

# Build without cache (fresh build)
docker-compose build --no-cache

# Build and start
docker-compose up --build -d

# Nuclear option: complete rebuild
docker system prune -f
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Container Debugging
```bash
# Execute commands in container
docker-compose exec api bash
docker-compose exec api python -c "import sys; print(sys.version)"

# Check environment variables
docker-compose exec api env | grep PYTHON

# Check Python bytecode prevention
docker-compose exec api python -c "import os; print(os.environ.get('PYTHONDONTWRITEBYTECODE'))"
```

## API Testing

### Authentication
```bash
# Login to get token
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'

# Set token for subsequent requests
export TOKEN="your_jwt_token_here"
```

### API Endpoints
```bash
# Test transformations endpoint
curl -X GET "http://localhost:8000/api/transformations/" \
  -H "Authorization: Bearer $TOKEN"

# Create transformation
curl -X POST "http://localhost:8000/api/transformations/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "document-uuid",
    "transformation_type": "SUMMARY",
    "parameters": {"length": "short"}
  }'

# Get documents
curl -X GET "http://localhost:8000/api/documents/" \
  -H "Authorization: Bearer $TOKEN"

# Health check
curl -X GET "http://localhost:8000/health"
```

### API Documentation
```bash
# Open API documentation
open http://localhost:8000/docs        # Swagger UI
open http://localhost:8000/redoc       # ReDoc
```

## Database Operations

### Alembic Migrations
```bash
# Generate migration
cd backend
python -m alembic revision --autogenerate -m "Description"

# Apply migrations
python -m alembic upgrade head

# Check migration status
python -m alembic current
python -m alembic history

# Downgrade migration
python -m alembic downgrade -1
```

### Database Access
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U postgres -d content_repurpose

# Database queries
docker-compose exec postgres psql -U postgres -d content_repurpose \
  -c "SELECT id, email FROM users LIMIT 5;"

# Export database
docker-compose exec postgres pg_dump -U postgres content_repurpose > backup.sql
```

## Testing

### Test Execution
```bash
# Full test suite
python testing/run_tests.py

# Specific test categories
python testing/run_tests.py --unit
python testing/run_tests.py --integration
python testing/run_tests.py --quick

# Pytest directly
cd backend
pytest tests/ -v
pytest tests/test_transformations.py -v
pytest tests/test_auth.py::test_login -v
```

### Test Environment
```bash
# Test environment setup
docker-compose -f docker-compose.test.yml up -d

# Run tests in container
docker-compose exec api pytest tests/ -v

# Clean test environment
docker-compose -f docker-compose.test.yml down -v
```

## Development Server

### Local Development
```bash
# Start FastAPI server
cd backend
python main.py

# Start with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery worker
celery -A app.core.celery_app worker --loglevel=info

# Start Redis CLI
docker-compose exec redis redis-cli
```

### Frontend Development
```bash
# Start React development server
cd frontend
npm install
npm start

# Build for production
npm run build

# Update dependencies
npm update
npx update-browserslist-db@latest
```

## Debugging Commands

### Service Health
```bash
# Check all services
docker-compose ps

# Check specific service health
curl -f http://localhost:8000/health || echo "API unhealthy"
docker-compose exec postgres pg_isready -U postgres || echo "Database unhealthy"
docker-compose exec redis redis-cli ping || echo "Redis unhealthy"
```

### Log Analysis
```bash
# View recent logs
docker-compose logs --tail=50 api

# Follow logs with timestamps
docker-compose logs -f -t api

# Search logs
docker-compose logs api | grep "ERROR"
docker-compose logs api | grep "transformation"
```

### Performance Monitoring
```bash
# Check container resource usage
docker stats

# Check disk usage
docker system df

# Monitor API response times
time curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/transformations/
```

## Troubleshooting

### Common Issues
```bash
# Clear Python cache
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +

# Reset Docker completely
docker-compose down -v
docker system prune -f
docker volume prune -f

# Check port conflicts
netstat -tlnp | grep :8000
lsof -i :8000  # macOS/Linux
```

### Environment Reset
```bash
# Complete environment reset
docker-compose down -v
docker system prune -f
rm -rf .pytest_cache
rm -rf backend/__pycache__
rm -rf backend/app/__pycache__

# Rebuild from scratch
docker-compose build --no-cache
docker-compose up -d
```

### Validation Commands
```bash
# Validate Python environment
python -c "import sys; print(f'Python: {sys.version}')"
python -c "import asyncio; print('Asyncio available')"

# Validate Docker setup
docker --version
docker-compose --version

# Validate database connection
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
async def test():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/content_repurpose')
    async with engine.begin() as conn:
        result = await conn.execute('SELECT 1')
        print(f'Database: {result.scalar()}')
asyncio.run(test())
"
```

## Git Operations

### Branch Management
```bash
# Create feature branch
git checkout -b feature/new-feature

# Stage and commit changes
git add .
git commit -m "Description of changes"

# Push to remote
git push origin feature/new-feature

# Merge to main
git checkout main
git merge feature/new-feature
```

### Deployment
```bash
# Tag release
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# Deploy to staging
git push staging main

# Deploy to production
git push production main
```

---

*This reference provides common commands for development, testing, and debugging of FastAPI applications with Docker and PostgreSQL.*