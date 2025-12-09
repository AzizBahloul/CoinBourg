#!/bin/bash
# CoinBourg Deployment Diagnostic Script
# Run this on the Azure VM to diagnose deployment issues

echo "=================================="
echo "CoinBourg Deployment Diagnostics"
echo "=================================="
echo ""

# Check Docker
echo "1. Docker Status"
echo "----------------"
if command -v docker &> /dev/null; then
    echo "✓ Docker is installed"
    docker --version
    docker compose version
else
    echo "✗ Docker not found"
fi
echo ""

# Check running containers
echo "2. Running Containers"
echo "---------------------"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# Check container logs
echo "3. Container Logs (last 20 lines)"
echo "----------------------------------"
echo "=== CoinBourg Bot ==="
docker compose logs --tail=20 coinbourg 2>/dev/null || echo "Container not running"
echo ""

# Check application health
echo "4. Application Health Check"
echo "----------------------------"
if curl -sf http://localhost:8000/health 2>/dev/null; then
    echo "✓ Application is responding"
    echo "Health response:"
    curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/health
else
    echo "✗ Application not responding on port 8000"
fi
echo ""

# Check ports
echo "5. Port Status"
echo "--------------"
echo "Listening ports:"
netstat -tuln | grep -E ':(8000|5432|6379|80|443)' || ss -tuln | grep -E ':(8000|5432|6379|80|443)'
echo ""

# Check .env file
echo "6. Environment Configuration"
echo "----------------------------"
if [ -f ~/CoinBourg/.env ]; then
    echo "✓ .env file exists"
    echo "Key environment variables:"
    grep -E '^(APP_NAME|ENVIRONMENT|BINANCE_TESTNET|RISK_LEVEL|API_PORT)' ~/CoinBourg/.env
else
    echo "✗ .env file not found"
fi
echo ""

# Check disk space
echo "7. Disk Space"
echo "-------------"
df -h / | tail -1
echo ""

# Check memory usage
echo "8. Memory Usage"
echo "---------------"
free -h
echo ""

# Check recent deployments
echo "9. Recent Deployment Logs"
echo "-------------------------"
if [ -f ~/deployment.log ]; then
    echo "Last 10 lines of deployment log:"
    tail -10 ~/deployment.log
else
    echo "No deployment log found"
fi
echo ""

# Test API endpoints
echo "10. API Endpoint Tests"
echo "----------------------"
echo "Testing /health endpoint:"
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8000/health 2>&1 | head -5

echo ""
echo "Testing root endpoint:"
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8000/ 2>&1 | head -5

echo ""
echo "=================================="
echo "Diagnostic Complete"
echo "=================================="
