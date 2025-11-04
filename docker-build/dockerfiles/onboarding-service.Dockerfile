# Production Dockerfile for Onboarding Service
# Multi-platform support: linux/amd64,linux/arm64
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright system dependencies (~50MB)
# These are required for Chromium browser to run properly
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libglib2.0-0 \
    libdbus-1-3 \
    libx11-6 \
    libxcb1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY onboarding-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Note: Playwright browser installation moved to runtime (entrypoint script)
# This reduces image size from 2GB to ~600MB
# Installation happens on container startup in background

# Copy application code
COPY onboarding-service/app /app/app
COPY onboarding-service/onboarding_migrations /app/onboarding_migrations
COPY onboarding-service/alembic.ini /app/alembic.ini
COPY onboarding-service/static /app/static

# Copy entrypoint script for runtime Playwright installation
COPY docker-build/entrypoints/onboarding-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app && \
    chown appuser:appuser /entrypoint.sh
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Set entrypoint for runtime setup (Playwright installation)
ENTRYPOINT ["/entrypoint.sh"]

# Run the application (passed to entrypoint script)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]