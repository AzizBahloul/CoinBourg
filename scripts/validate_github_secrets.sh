#!/bin/bash
# ============================================
# GitHub Secrets Validation Script
# ============================================
# Run this locally to verify you have all required secrets
# This doesn't check the actual values, just guides you through setup

set -e

echo "🔐 GitHub Secrets Validation Checklist"
echo "========================================"
echo ""
echo "This script helps verify that all required GitHub secrets are configured."
echo "Go to: GitHub Repository → Settings → Secrets and variables → Actions"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Required secrets
declare -A SECRETS
SECRETS[AZURE_HOST]="Azure VM IP address (e.g., 4.235.122.138)"
SECRETS[AZURE_USERNAME]="SSH username for VM (e.g., bourguibaCoin)"
SECRETS[AZURE_PASSWORD]="SSH password for VM"
SECRETS[DEEPSEEK_API_KEY]="DeepSeek AI API key (from platform.deepseek.com)"
SECRETS[BINANCE_API_KEY]="Binance API key"
SECRETS[BINANCE_API_SECRET]="Binance API secret"
SECRETS[APP_SECRET_KEY]="App secret (generate: openssl rand -hex 32)"

# Check each secret
echo "📋 Required Secrets Checklist:"
echo ""

all_confirmed=true
for secret in "${!SECRETS[@]}"; do
    echo -e "${YELLOW}Secret: ${secret}${NC}"
    echo "   Purpose: ${SECRETS[$secret]}"
    read -p "   ✓ Is this configured in GitHub? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "   ${RED}❌ Not configured${NC}"
        all_confirmed=false
    else
        echo -e "   ${GREEN}✓ Confirmed${NC}"
    fi
    echo ""
done

echo "========================================"
echo ""

if [ "$all_confirmed" = true ]; then
    echo -e "${GREEN}✅ All secrets confirmed!${NC}"
    echo ""
    echo "You're ready to deploy! Try:"
    echo "  git add ."
    echo "  git commit -m 'Deploy to production'"
    echo "  git push origin main"
    echo ""
    echo "Monitor at: https://github.com/$(git config remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/actions"
else
    echo -e "${RED}❌ Some secrets are missing!${NC}"
    echo ""
    echo "Please configure missing secrets:"
    echo "1. Go to your GitHub repository"
    echo "2. Settings → Secrets and variables → Actions"
    echo "3. Click 'New repository secret'"
    echo "4. Add each missing secret"
    echo ""
    echo "See GITHUB_ACTIONS_SETUP.md for detailed instructions."
    exit 1
fi

echo ""
echo "🧪 Optional: Test SSH Connection"
echo "=================================="
echo ""
read -p "Do you want to test SSH connection to Azure VM? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter Azure VM IP (AZURE_HOST): " vm_host
    read -p "Enter SSH username (AZURE_USERNAME): " vm_user
    
    echo ""
    echo "Testing connection to $vm_user@$vm_host..."
    
    if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$vm_user@$vm_host" "echo 'Connection successful!'" 2>/dev/null; then
        echo -e "${GREEN}✅ SSH connection works!${NC}"
        echo ""
        echo "Checking Docker on VM..."
        if ssh -o StrictHostKeyChecking=no "$vm_user@$vm_host" "docker --version" 2>/dev/null; then
            echo -e "${GREEN}✅ Docker is installed on VM${NC}"
        else
            echo -e "${RED}❌ Docker not found on VM${NC}"
            echo "Run on VM: curl -fsSL https://get.docker.com | sh"
        fi
    else
        echo -e "${RED}❌ SSH connection failed${NC}"
        echo "Check:"
        echo "  - VM is running"
        echo "  - IP address is correct"
        echo "  - Username is correct"
        echo "  - Firewall allows SSH (port 22)"
    fi
fi

echo ""
echo "========================================"
echo "✨ Setup validation complete!"
echo "========================================"
