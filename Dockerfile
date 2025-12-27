# ===========================================
# CoinBourg Dockerfile
# ===========================================
# Multi-stage build for optimal image size

# Stage 1: Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Ensure project root is on Python path for module imports
ENV PYTHONPATH="/app"

# Install build dependencies (single line to avoid escape issues)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/* && apt-get clean

# Copy requirements first for better caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# Install pip packages in stages to manage disk space
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    find /opt/venv -type f -name '*.pyc' -delete && \
    find /opt/venv -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type d -name 'test' -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true

# Stage 2: Production stage
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies (single line to avoid escape issues)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash coinbourg

# Copy application code first with proper ownership
COPY --chown=coinbourg:coinbourg . .

# Create required directories with proper permissions
# These need to be writable by the coinbourg user for logs and data storage
RUN mkdir -p /app/logs /app/data /app/__pycache__ \
    && chown -R coinbourg:coinbourg /app \
    && chmod -R 755 /app

# Switch to non-root user
USER coinbourg

# Expose API port
EXPOSE 8000

# Default command: run both API and trading loop
CMD ["python", "-m", "src.main", "--mode", "both"]
