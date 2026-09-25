# Dockerfile for Content Repurpose API
# bookworm (Debian 12) avoids unfixed perl CVEs present in Debian Trixie (13)
FROM python:3.12-slim-bookworm

# Prevent Python from writing bytecode files and ensure unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# libmagic backs python-magic's content sniffing for uploads; without it the
# check silently turns off.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY backend/ .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app

# start.sh: runs alembic upgrade head then exec uvicorn (with lock/statement timeouts)
# Copy and mark executable while still root, before dropping privileges.
COPY backend/start.sh /start.sh
RUN chmod +x /start.sh

USER appuser

# Expose port
EXPOSE 8000

# Health check (pure Python — no curl dependency needed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run application
CMD ["/start.sh"]