#!/bin/bash

# ===========================================
# CoinBourg Azure VM Deployment Script
# ===========================================
# Complete setup script for Azure Student B1s VM
# Run this script on a fresh Ubuntu 22.04 LTS VM

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "=============================================="
echo "  CoinBourg AI Trading Bot - Deployment"
echo "=============================================="
echo -e "${NC}"

# ===========================================
# System Update
# ===========================================
echo -e "${YELLOW}[1/8] Updating system packages...${NC}"
sudo apt update && sudo apt upgrade -y

# ===========================================
# Install Docker
# ===========================================
echo -e "${YELLOW}[2/8] Installing Docker...${NC}"

# Remove old versions
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Install prerequisites
sudo apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Set up the stable repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER

echo -e "${GREEN}✓ Docker installed successfully${NC}"

# ===========================================
# Install Docker Compose
# ===========================================
echo -e "${YELLOW}[3/8] Installing Docker Compose...${NC}"

sudo apt install -y docker-compose-plugin

# Verify installation
docker compose version

echo -e "${GREEN}✓ Docker Compose installed successfully${NC}"

# ===========================================
# Configure Firewall
# ===========================================
echo -e "${YELLOW}[4/8] Configuring firewall...${NC}"

sudo apt install -y ufw

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow CoinBourg API (optional - for direct access)
sudo ufw allow 8000/tcp

# Enable firewall
sudo ufw --force enable

echo -e "${GREEN}✓ Firewall configured${NC}"

# ===========================================
# Create Application Directory
# ===========================================
echo -e "${YELLOW}[5/8] Setting up application directory...${NC}"

# Create directories
mkdir -p ~/coinbourg
mkdir -p ~/coinbourg/logs
mkdir -p ~/coinbourg/data
mkdir -p ~/coinbourg/nginx/ssl

echo -e "${GREEN}✓ Application directory created${NC}"

# ===========================================
# Configure System for Low Memory
# ===========================================
echo -e "${YELLOW}[6/8] Optimizing system for low memory...${NC}"

# Add swap if not exists (important for B1s with 1GB RAM)
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# Configure swappiness
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

# Configure Docker daemon for low memory
sudo mkdir -p /etc/docker
cat <<EOF | sudo tee /etc/docker/daemon.json
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF

sudo systemctl restart docker

echo -e "${GREEN}✓ System optimized for low memory${NC}"

# ===========================================
# Install Additional Tools
# ===========================================
echo -e "${YELLOW}[7/8] Installing additional tools...${NC}"

sudo apt install -y \
    htop \
    iotop \
    ncdu \
    git \
    vim \
    tmux \
    fail2ban

# Configure fail2ban for SSH protection
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

echo -e "${GREEN}✓ Additional tools installed${NC}"

# ===========================================
# Create Systemd Service
# ===========================================
echo -e "${YELLOW}[8/8] Creating systemd service...${NC}"

cat <<EOF | sudo tee /etc/systemd/system/coinbourg.service
[Unit]
Description=CoinBourg AI Trading Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/${USER}/coinbourg
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=${USER}
Group=docker

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable coinbourg.service

echo -e "${GREEN}✓ Systemd service created${NC}"

# ===========================================
# Print Next Steps
# ===========================================
echo ""
echo -e "${GREEN}=============================================="
echo "  Deployment Script Complete!"
echo "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Upload your CoinBourg project files to ~/coinbourg/"
echo "   scp -r ./* ${USER}@YOUR_VM_IP:~/coinbourg/"
echo ""
echo "2. Configure your .env file:"
echo "   cd ~/coinbourg"
echo "   cp .env.example .env"
echo "   nano .env"
echo ""
echo "3. Start the application:"
echo "   cd ~/coinbourg"
echo "   docker compose up -d"
echo ""
echo "4. Check logs:"
echo "   docker compose logs -f"
echo ""
echo "5. Access the API:"
echo "   http://YOUR_VM_IP:8000/docs"
echo ""
echo -e "${YELLOW}IMPORTANT: Log out and log back in for Docker group changes to take effect!${NC}"
echo ""
echo "For production, consider:"
echo "- Setting up SSL certificates (Let's Encrypt)"
echo "- Configuring a domain name"
echo "- Setting up monitoring (Prometheus/Grafana)"
