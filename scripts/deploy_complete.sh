#!/bin/bash
# ===========================================
# CoinBourg Deployment Script for Azure VM
# ===========================================

set -e  # Exit on error

echo "🚀 CoinBourg Deployment Script"
echo "================================"
echo ""

# Check if running on correct environment
if [ -z "$AZURE_VM" ]; then
    read -p "Are you deploying to Azure VM? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Deployment cancelled."
        exit 1
    fi
fi

# Update system packages
echo "📦 Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install required system dependencies
echo "📚 Installing system dependencies..."
sudo apt-get install -y \
    git \
    python3-pip \
    python3-venv \
    docker.io \
    docker-compose \
    nginx \
    postgresql-client \
    redis-tools

# Navigate to project directory or clone
if [ ! -d "/home/coinbourg/CoinBourg" ]; then
    echo "📥 Cloning repository..."
    cd /home/coinbourg
    git clone https://github.com/AzizBahloul/CoinBourg.git
fi

cd /home/coinbourg/CoinBourg

# Pull latest changes
echo "🔄 Pulling latest changes..."
git pull origin main

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found!"
    echo "Please create .env file with required configuration."
    echo "Copy from .env.example and fill in your API keys."
    exit 1
fi

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose down || true

# Build and start services
echo "🏗️  Building Docker images..."
docker-compose build --no-cache

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 10

# Check service health
echo "🏥 Checking service health..."
docker-compose ps

# Initialize database if needed
echo "💾 Initializing database..."
docker-compose exec -T db psql -U coinbourg -d coinbourg -f /docker-entrypoint-initdb.d/init-db.sql || echo "Database already initialized"

# Show logs
echo ""
echo "📋 Recent logs:"
docker-compose logs --tail=50

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🌐 Services:"
echo "  - API: http://$(hostname -I | awk '{print $1}'):8000"
echo "  - Dashboard: http://$(hostname -I | awk '{print $1}'):8000/"
echo "  - Testing Dashboard: http://$(hostname -I | awk '{print $1}'):8000/testing"
echo "  - API Docs: http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "📊 Useful commands:"
echo "  - View logs: docker-compose logs -f"
echo "  - Restart: docker-compose restart"
echo "  - Stop: docker-compose down"
echo "  - Shell: docker-compose exec coinbourg bash"
echo ""
