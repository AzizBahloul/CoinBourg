#!/bin/bash

# Configuration
REMOTE_USER="bourguibaCoin"
REMOTE_HOST="4.235.122.138"
REMOTE_DIR="~/CoinBourg"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Preparing deployment to $REMOTE_HOST...${NC}"

# Create archive
echo "Creating project archive..."
tar -czf coinbourg.tar.gz \
    --exclude='venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    .

echo -e "${GREEN}Uploading files... (Please enter password: 1v@P3+8GrbT8)${NC}"
scp coinbourg.tar.gz $REMOTE_USER@$REMOTE_HOST:~/

echo -e "${GREEN}Executing remote setup... (Please enter password: 1v@P3+8GrbT8)${NC}"
ssh -t $REMOTE_USER@$REMOTE_HOST << EOF
    # Create directory if it doesn't exist
    mkdir -p $REMOTE_DIR
    
    # Extract files
    echo "Extracting files..."
    tar -xzf ~/coinbourg.tar.gz -C $REMOTE_DIR
    
    # Cleanup archive
    rm ~/coinbourg.tar.gz
    
    # Run deployment script
    cd $REMOTE_DIR
    echo "Making scripts executable..."
    chmod +x scripts/*.sh
    
    echo "Starting Azure deployment script..."
    # We run this interactively or it might fail if it asks for input
    ./scripts/deploy-azure.sh
    
    echo "Building and starting application..."
    # Ensure we are in the right directory
    cd $REMOTE_DIR
    
    # Stop any running containers first
    docker compose down || true
    
    # Build and start in detached mode
    docker compose up -d --build
    
    echo "Application started! Logs:"
    # Show last 10 lines of logs to confirm startup
    docker compose logs --tail=10
EOF

# Cleanup local archive
rm coinbourg.tar.gz

echo -e "${GREEN}Deployment process finished!${NC}"
