# ===========================================
# CoinBourg Dockerfile
# ===========================================
# Multi-stage build for optimal image size

# Stage 1: Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Production stage
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash coinbourg

# Create required directories with proper permissions
# These need to be writable by the coinbourg user for logs and data storage
RUN mkdir -p /app/logs /app/data /app/__pycache__ \
    && chown -R coinbourg:coinbourg /app \
    && chmod -R 755 /app \
    && chmod -R 755 /app/logs \
    && chmod -R 755 /app/data

# Copy application code with proper ownership
COPY --chown=coinbourg:coinbourg . .

# Ensure all Python cache and log directories are writable
RUN find /app -type d -exec chmod 755 {} + \
    && find /app -type f -exec chmod 644 {} + \
    && chmod +x /app/scripts/*.sh 2>/dev/null || true

# Switch to non-root user
USER coinbourg

# Expose port
EXPOSE 8000

# Create startup validation script to prevent permission errors at runtime
RUN printf '#!/bin/bash\nset -e\necho "[STARTUP] Validating directory permissions..."\nfor dir in /app/logs /app/data; do\n  if [ ! -d "$dir" ]; then\n    echo "[STARTUP] Creating directory: $dir"\n    mkdir -p "$dir"\n  fi\n  if [ ! -w "$dir" ]; then\n    echo "[ERROR] Directory not writable: $dir"\n    ls -la /app | grep -E "logs|data"\n    exit 1\n  fi\ndone\necho "[STARTUP] Permission validation successful"\nexec "$@"' > /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Use entrypoint script for validation before running app
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "src.main", "--mode", "api"]
