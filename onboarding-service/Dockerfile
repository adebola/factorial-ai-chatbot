# Production Dockerfile for Onboarding Service (Intel/AMD64 platform specified in build command)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright

# Install system dependencies including Playwright dependencies
# These are required for Chromium browser to run
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    # Playwright Chromium dependencies
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
    libatspi2.0-0 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app /app/app
COPY onboarding_migrations /app/onborading_migrations
COPY alembic.ini /app/alembic.ini
COPY static /app/static

# Copy entrypoint script (from docker-build directory during build)
# This will be copied from: ../docker-build/entrypoints/onboarding-entrypoint.sh
# Make it executable before changing to non-root user
COPY ../docker-build/entrypoints/onboarding-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create non-root user and setup directories with proper permissions
RUN adduser --disabled-password --gecos '' appuser && \
    mkdir -p /app/.cache/ms-playwright && \
    chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Use entrypoint script for startup
ENTRYPOINT ["/app/entrypoint.sh"]

# Run the application (passed to entrypoint as $@)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]