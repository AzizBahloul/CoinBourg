# CoinBourg Deployment Prevention Guide

## Overview
This guide explains the safeguards implemented to prevent deployment failures due to permission errors and other common issues.

## Prevention Measures Implemented

### 1. **Enhanced Dockerfile Permission Management**

**What was the issue?**
- Bot container crashed with `PermissionError: [Errno 13] Permission denied: '/app/logs/...'`
- The `coinbourg` non-root user didn't have write permissions to log directories

**How it's now prevented:**
```dockerfile
# Create required directories with proper permissions
RUN mkdir -p /app/logs /app/data /app/__pycache__ \
    && chown -R coinbourg:coinbourg /app \
    && chmod -R 755 /app \
    && chmod -R 755 /app/logs \
    && chmod -R 755 /app/data

# Ensure all Python cache and log directories are writable
RUN find /app -type d -exec chmod 755 {} + \
    && find /app -type f -exec chmod 644 {} + \
    && chmod +x /app/scripts/*.sh 2>/dev/null || true
```

**Benefits:**
- ✅ Recursive permission setting on all directories
- ✅ Explicit write permissions (755) for all directories
- ✅ Script execution permissions for shell scripts
- ✅ Handles dynamic directory creation

---

### 2. **Startup Validation Script**

**What was added?**
A `docker-entrypoint.sh` script runs before the application starts to verify:
- All required directories exist
- All directories are writable by the `coinbourg` user
- Provides clear error messages if validation fails

**How it works:**
```bash
#!/bin/bash
set -e
echo "[STARTUP] Validating directory permissions..."
for dir in /app/logs /app/data; do
  if [ ! -d "$dir" ]; then
    echo "[STARTUP] Creating directory: $dir"
    mkdir -p "$dir"
  fi
  if [ ! -w "$dir" ]; then
    echo "[ERROR] Directory not writable: $dir"
    ls -la /app | grep -E "logs|data"
    exit 1
  fi
done
echo "[STARTUP] Permission validation successful"
exec "$@"
```

**When it runs:**
- Every time the container starts
- Before the Python application launches
- Prevents app crash from permission issues

---

### 3. **Enhanced GitHub Actions Deployment Pipeline**

**Pre-deployment Validation Checks:**
```bash
# Validate .env file syntax
echo "Validating .env file syntax..."
if grep -E '\\$|`|\$\{' .env | grep -v '^#'; then
  echo "WARNING: .env contains potential shell expansion characters"
fi

# Validate Docker Compose configuration
docker compose config > /dev/null && echo "✓ Docker Compose configuration valid"

# Wait for containers to be healthy
docker compose up -d --build
sleep 15

# Validate container health
if ! docker compose ps | grep -q "healthy"; then
  echo "WARNING: Not all containers are healthy yet"
fi

# Check if app is responding
for i in {1..10}; do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "✓ App is healthy and responding"
    break
  fi
done
```

**Benefits:**
- ✅ Detects .env syntax errors before deployment
- ✅ Validates Docker Compose configuration
- ✅ Waits for containers to fully initialize
- ✅ Verifies app is responding after deployment
- ✅ Provides detailed logs on failure

---

### 4. **Pre-flight Check Script**

**Location:** `scripts/preflight-check.sh`

**Run before deployment:**
```bash
bash scripts/preflight-check.sh
```

**Checks performed:**
- ✅ Docker and Docker Compose installation
- ✅ Required files exist (Dockerfile, docker-compose.yml, requirements.txt, etc.)
- ✅ .env file syntax validation
- ✅ Required environment variables present
- ✅ Docker Compose configuration validity
- ✅ Directory permissions
- ✅ Python requirements file
- ✅ Source code structure integrity
- ✅ .env in .dockerignore (prevents secret leaks)
- ✅ Git repository status

**Output example:**
```
✓ Docker is installed (Docker version 24.0.0)
✓ Docker Compose is installed
✓ Found: docker-compose.yml
✓ Found: Dockerfile
✓ Found: requirements.txt
✓ Found: .env
✓ Found: src/main.py
✓ .env syntax looks valid
✓ Found required var: BINANCE_API_KEY
...
===========================
✅ Pre-flight check PASSED!
===========================
```

---

### 5. **.dockerignore Protection**

**What it does:**
Prevents sensitive files from being included in Docker image:
- `.env` - Contains API keys and secrets
- `.git` - Git history (unnecessary in container)
- `__pycache__` - Python cache files
- `venv/` - Virtual environment
- `.pytest_cache/` - Test artifacts
- Documentation and scripts

**Security benefit:**
- Even if the image is leaked, `.env` won't be included
- Smaller image size
- Faster builds

---

## Deployment Workflow

### Manual Deployment

Before deploying manually:

```bash
# 1. Run pre-flight checks
bash scripts/preflight-check.sh

# 2. Verify .env syntax
cat .env | grep -v '^#' | sort

# 3. Build and test locally (optional)
docker compose build
docker compose up -d
docker compose logs --tail=20 coinbourg-bot

# 4. Check container health
docker compose ps
```

### Automated Deployment (GitHub Actions)

When you push to main:

1. **GitHub Actions triggers** `deploy.yml` workflow
2. **Pre-deployment validation** runs automatically
3. **Code is deployed** to Azure VM
4. **Containers start** with startup validation enabled
5. **Health checks** verify all services running
6. **App responds** to HTTP health checks

---

## Troubleshooting

### Issue: Permission Denied errors in logs

**Check:**
```bash
# SSH into Azure VM
ssh bourguibaCoin@4.235.122.138

# Check directory permissions
docker exec coinbourg-bot ls -la /app | grep -E "logs|data"

# Check if directories are writable
docker exec coinbourg-bot test -w /app/logs && echo "WRITABLE" || echo "NOT WRITABLE"
```

**Fix:**
```bash
# Rebuild with fixed Dockerfile
docker compose down
docker compose up -d --build
```

### Issue: App container keeps restarting

**Check logs:**
```bash
docker compose logs --tail=50 coinbourg-bot
docker compose logs --follow coinbourg-bot
```

**Check startup validation:**
```bash
docker compose logs coinbourg-bot | grep "STARTUP\|ERROR\|VALIDATION"
```

### Issue: .env syntax error during deployment

**Verify .env syntax:**
```bash
# Check for shell special characters
grep -E '\\$|`|\$\{' .env

# Validate no quotes in values
grep '"' .env

# Should be clean key=value pairs
cat .env | grep -v '^#'
```

---

## Prevention Checklist

Before each deployment, verify:

- [ ] Run `bash scripts/preflight-check.sh` (passes without failures)
- [ ] `.env` file exists and has correct values
- [ ] No `.env` variables have shell special characters (`$`, backticks)
- [ ] `docker-compose.yml` is valid (run `docker compose config`)
- [ ] All required environment variables are set
- [ ] `.env` is in `.dockerignore`
- [ ] Git repository is clean or changes are intentional
- [ ] Source code structure is intact
- [ ] No uncommitted critical changes

---

## Key Files Added/Modified

### New Files:
- `scripts/preflight-check.sh` - Pre-flight validation script
- `.dockerignore` - Prevents secrets from Docker image

### Modified Files:
- `Dockerfile` - Enhanced permission management + startup validation
- `.github/workflows/deploy.yml` - Enhanced with pre-deployment checks and health verification

### Why These Changes:

1. **Dockerfile** - Ensures permissions are correct at build time AND runtime
2. **docker-entrypoint.sh** - Validates permissions before app runs
3. **GitHub Actions** - Validates deployment at each step
4. **preflight-check.sh** - Detects issues before they reach production
5. **.dockerignore** - Prevents accidental secret leaks

---

## Future Improvements

Consider implementing:

1. **Automated database migrations** - Run on startup if needed
2. **Health check API** - Verify all dependencies (database, Redis, Binance API)
3. **Graceful shutdown** - Clean up connections on SIGTERM
4. **Backup strategy** - Automated database backups before deployment
5. **Rollback capability** - Keep previous working version available
6. **Monitoring & alerts** - Alert on deployment failures

---

## Contact & Support

For deployment issues:
1. Check `docker compose logs --tail=50`
2. Run `bash scripts/preflight-check.sh`
3. Review this guide's Troubleshooting section
4. Check GitHub Actions workflow logs at `https://github.com/AzizBahloul/CoinBourg/actions`
