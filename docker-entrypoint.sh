#!/bin/bash
set -e

echo "[STARTUP] Ensuring directory permissions..."

for dir in /app/logs /app/data; do
  mkdir -p "$dir"
  chown coinbourg:coinbourg "$dir"
  chmod 755 "$dir"
done

echo "[STARTUP] Permission validation successful"

# Drop privileges and run the command (using gosu instead of su-exec)
exec gosu coinbourg "$@"
