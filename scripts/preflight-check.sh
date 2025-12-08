#!/bin/bash
# CoinBourg Pre-flight Deployment Check Script
# This script validates the environment before deployment to prevent runtime errors

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

# Print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        pass)
            echo -e "${GREEN}✓${NC} $message"
            ((CHECKS_PASSED++))
            ;;
        fail)
            echo -e "${RED}✗${NC} $message"
            ((CHECKS_FAILED++))
            ;;
        warn)
            echo -e "${YELLOW}⚠${NC} $message"
            ((CHECKS_WARNING++))
            ;;
        info)
            echo -e "${YELLOW}ℹ${NC} $message"
            ;;
    esac
}

echo "=================================================="
echo "  CoinBourg Pre-flight Deployment Check"
echo "=================================================="
echo ""

# 1. Check Docker and Docker Compose
print_status info "Checking Docker installation..."
if command -v docker &> /dev/null; then
    print_status pass "Docker is installed ($(docker --version))"
else
    print_status fail "Docker is not installed"
fi

if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    print_status pass "Docker Compose is installed"
else
    print_status fail "Docker Compose is not installed"
fi

# 2. Check required files
print_status info "Checking required files..."
REQUIRED_FILES=(
    "docker-compose.yml"
    "Dockerfile"
    "requirements.txt"
    ".env"
    "src/main.py"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$file" ]; then
        print_status pass "Found: $file"
    else
        print_status fail "Missing: $file"
    fi
done

# 3. Check .env file syntax
print_status info "Validating .env file syntax..."
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Check for common issues
    if grep -E '\\$|`|\$\{' "$PROJECT_ROOT/.env" | grep -v '^#'; then
        print_status warn ".env contains potential shell expansion characters (needs review)"
    else
        print_status pass ".env syntax looks valid"
    fi
    
    # Check for required variables
    REQUIRED_VARS=(
        "BINANCE_API_KEY"
        "BINANCE_API_SECRET"
        "BINANCE_TESTNET"
        "DATABASE_URL"
        "REDIS_URL"
        "DEEPSEEK_API_KEY"
    )
    
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^$var=" "$PROJECT_ROOT/.env"; then
            print_status pass "Found required var: $var"
        else
            print_status fail "Missing required var: $var"
        fi
    done
else
    print_status fail ".env file not found"
fi

# 4. Check Docker Compose configuration
print_status info "Validating Docker Compose configuration..."
cd "$PROJECT_ROOT"
if docker compose config > /dev/null 2>&1; then
    print_status pass "Docker Compose configuration is valid"
else
    print_status fail "Docker Compose configuration has errors"
    docker compose config 2>&1 | head -20
fi

# 5. Check directory permissions
print_status info "Checking directory permissions..."
for dir in "logs" "data" "__pycache__"; do
    if [ ! -d "$PROJECT_ROOT/$dir" ]; then
        mkdir -p "$PROJECT_ROOT/$dir"
        print_status pass "Created directory: $dir"
    else
        print_status pass "Directory exists: $dir"
    fi
done

# 6. Check Python requirements
print_status info "Checking Python requirements..."
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    LINES=$(wc -l < "$PROJECT_ROOT/requirements.txt")
    print_status pass "Found requirements.txt with $LINES dependencies"
else
    print_status fail "requirements.txt not found"
fi

# 7. Check source code structure
print_status info "Checking source code structure..."
REQUIRED_DIRS=(
    "src/api"
    "src/core"
    "src/config"
    "src/utils"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        print_status pass "Found: $dir"
    else
        print_status fail "Missing: $dir"
    fi
done

# 8. Check for .env in .dockerignore (to prevent leaking secrets)
print_status info "Checking .env is properly ignored..."
if [ -f "$PROJECT_ROOT/.dockerignore" ] && grep -q "^\.env" "$PROJECT_ROOT/.dockerignore"; then
    print_status pass ".env is in .dockerignore (secrets protected)"
elif [ ! -f "$PROJECT_ROOT/.dockerignore" ]; then
    print_status warn ".dockerignore not found (creating it)"
    cat > "$PROJECT_ROOT/.dockerignore" << 'EOF'
.env
.git
.gitignore
__pycache__
*.pyc
*.pyo
*.egg-info
dist
build
.pytest_cache
venv
EOF
    print_status pass "Created .dockerignore"
else
    print_status warn ".env not in .dockerignore (consider adding it)"
fi

# 9. Check git status
print_status info "Checking git status..."
if [ -d "$PROJECT_ROOT/.git" ]; then
    if git -C "$PROJECT_ROOT" status > /dev/null 2>&1; then
        UNCOMMITTED=$(git -C "$PROJECT_ROOT" status --porcelain | wc -l)
        if [ $UNCOMMITTED -eq 0 ]; then
            print_status pass "Git repository is clean"
        else
            print_status warn "Git repository has $UNCOMMITTED uncommitted changes"
        fi
    fi
else
    print_status warn "Not a git repository"
fi

# 10. Summary
echo ""
echo "=================================================="
echo "  Pre-flight Check Summary"
echo "=================================================="
echo -e "${GREEN}Passed:${NC} $CHECKS_PASSED"
echo -e "${RED}Failed:${NC} $CHECKS_FAILED"
echo -e "${YELLOW}Warnings:${NC} $CHECKS_WARNING"
echo ""

if [ $CHECKS_FAILED -gt 0 ]; then
    echo -e "${RED}❌ Pre-flight check FAILED!${NC}"
    echo "Please fix the errors above before deploying."
    exit 1
elif [ $CHECKS_WARNING -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Pre-flight check passed with warnings${NC}"
    echo "Review warnings before proceeding."
    exit 0
else
    echo -e "${GREEN}✅ Pre-flight check PASSED!${NC}"
    echo "Ready for deployment."
    exit 0
fi
