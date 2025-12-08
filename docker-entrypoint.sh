#!/bin/bash
set -e

echo "[STARTUP] Ensuring directory permissions..."

# Ensure logs and data directories exist with correct permissions
for dir in /app/logs /app/data; do
  mkdir -p "$dir"
  chown coinbourg:coinbourg "$dir"
  chmod 755 "$dir"
done

echo "[STARTUP] Permission validation successful"

# Run the application as non-root user
exec su-exec coinbourg "$@"
