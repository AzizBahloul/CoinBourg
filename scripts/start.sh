#!/bin/bash

# ===========================================
# CoinBourg Quick Start Script
# ===========================================
# Run this script to quickly start the bot locally

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}"
echo "=============================================="
echo "  CoinBourg AI Trading Bot - Quick Start"
echo "=============================================="
echo -e "${NC}"

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${RED}Please edit .env file with your API keys before continuing!${NC}"
    echo "nano .env"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Create required directories
mkdir -p logs data

# Build and start containers
echo -e "${YELLOW}Building and starting containers...${NC}"
docker compose up -d --build

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Check health
echo -e "${YELLOW}Checking service health...${NC}"
if curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${GREEN}✓ CoinBourg API is running!${NC}"
else
    echo -e "${RED}✗ API health check failed${NC}"
    docker compose logs coinbourg
    exit 1
fi

echo ""
echo -e "${GREEN}=============================================="
echo "  CoinBourg is now running!"
echo "==============================================${NC}"
echo ""
echo "API Endpoints:"
echo "  - Health: http://localhost:8000/health"
echo "  - Status: http://localhost:8000/status"
echo "  - Docs:   http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  - View logs:     docker compose logs -f"
echo "  - Stop:          docker compose down"
echo "  - Restart:       docker compose restart"
echo ""
