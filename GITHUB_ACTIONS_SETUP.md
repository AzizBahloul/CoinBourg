# GitHub Actions CI/CD Setup Guide

## 🎯 Overview

CoinBourg uses GitHub Actions for **automatic deployment** to your Azure VM. Every push to the `main` branch triggers a full deployment pipeline.

---

## 📋 Prerequisites

✅ GitHub repository with push access  
✅ Azure VM running Ubuntu 22.04 LTS  
✅ SSH access to the VM configured  
✅ API keys for DeepSeek and Binance  

---

## 🔐 Step 1: Configure GitHub Secrets

GitHub Actions needs secrets to connect to your VM and configure the application. **Never commit these to your repository!**

### How to Add Secrets

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret below:

### Required Secrets

| Secret Name | Description | How to Get It | Example |
|-------------|-------------|---------------|---------|
| **`AZURE_HOST`** | Azure VM IP address | From Azure Portal → VM → Overview | `4.235.122.138` |
| **`AZURE_USERNAME`** | SSH username | Your VM admin username | `bourguibaCoin` |
| **`AZURE_PASSWORD`** | SSH password | Your VM password (set during VM creation) | `1v@P3+8GrbT8` |
| **`DEEPSEEK_API_KEY`** | DeepSeek AI API key | https://platform.deepseek.com/api_keys | `sk-xxxxxxxxxxxxx` |
| **`BINANCE_API_KEY`** | Binance API key | https://www.binance.com/en/my/settings/api-management | `xxxxxxxxxx` |
| **`BINANCE_API_SECRET`** | Binance API secret | Same as above (keep secret!) | `xxxxxxxxxx` |
| **`APP_SECRET_KEY`** | Application secret | Generate: `openssl rand -hex 32` | `abc123...` (64 chars) |

### Screenshot Guide

```
GitHub Repository → Settings
    ↓
Secrets and variables → Actions
    ↓
New repository secret
    ↓
Name: AZURE_HOST
Value: 4.235.122.138
    ↓
Add secret
```

---

## 🚀 Step 2: How Deployment Works

### Automatic Trigger

The workflow runs automatically when you push to `main`:

```bash
git add .
git commit -m "Update trading strategy"
git push origin main
```

### Manual Trigger

You can also trigger deployment manually:

1. Go to **Actions** tab in GitHub
2. Select **Deploy to Azure VM** workflow
3. Click **Run workflow** → Select `main` branch → **Run workflow**

### What Happens During Deployment

The workflow performs these steps in order:

#### 1️⃣ **Preparation** (30 seconds)
- ✅ Checks out your code
- ✅ Frees up disk space on GitHub runner
- ✅ Creates deployment archive (excludes venv, .git, __pycache__)

#### 2️⃣ **Upload** (30 seconds)
- ✅ Installs SSH tools
- ✅ Uploads archive to Azure VM via SCP
- ✅ Connects via SSH

#### 3️⃣ **Deployment on VM** (2-3 minutes)
- ✅ Extracts archive to `~/CoinBourg/`
- ✅ Creates `.env` file from GitHub secrets
- ✅ Validates .env syntax (checks for shell expansion)
- ✅ Validates Docker Compose configuration
- ✅ Stops existing containers
- ✅ Removes old containers/networks
- ✅ Cleans Docker system (frees space)
- ✅ Rebuilds images with `--no-cache`
- ✅ Starts all services:
  - PostgreSQL database
  - Redis cache
  - CoinBourg API
  - Nginx reverse proxy (if configured)

#### 4️⃣ **Health Checks** (30 seconds)
- ✅ Waits 30s for containers to initialize
- ✅ Checks PostgreSQL: `pg_isready`
- ✅ Checks Redis: `redis-cli ping`
- ✅ Checks API: `curl http://localhost:8000/health`
  - Retries 10 times (3s intervals)
  - Shows logs if fails

#### 5️⃣ **Verification** (10 seconds)
- ✅ Displays container status
- ✅ Shows port bindings (8000, 5432, 6379)
- ✅ Shows recent application logs (last 20 lines)
- ✅ Prints access URL

### Total Time: **3-5 minutes** ⏱️

---

## 📊 Step 3: Monitor Deployment

### View Live Progress

1. Go to **Actions** tab in your GitHub repo
2. Click on the latest workflow run
3. Click **deploy** job
4. Expand steps to see real-time logs

### Check for Success

Look for these indicators:

✅ **Green checkmark** on workflow run  
✅ **"✓ Deployment successful!"** in logs  
✅ **All 4 services healthy** (PostgreSQL, Redis, CoinBourg, Nginx)  
✅ **API responds** at `http://YOUR_VM_IP:8000/health`  

### Common Success Output

```
=== Container Status ===
coinbourg-bot    Up 30 seconds   Healthy   0.0.0.0:8000->8000/tcp
coinbourg-db     Up 35 seconds   Healthy   5432/tcp
coinbourg-redis  Up 35 seconds   Healthy   6379/tcp

✓ PostgreSQL is ready
✓ Redis is ready
✓ CoinBourg API is healthy and responding on port 8000

=== Deployment Complete ===
Access the application at: http://4.235.122.138:8000
```

---

## 🐛 Step 4: Troubleshooting

### Deployment Failed?

#### Check Secrets

❌ **Error**: `Permission denied (publickey,password)`  
✅ **Fix**: Verify `AZURE_USERNAME` and `AZURE_PASSWORD` are correct

#### Check API Keys

❌ **Error**: `Invalid API key`  
✅ **Fix**: Verify `DEEPSEEK_API_KEY` and `BINANCE_API_KEY` are valid

#### Check VM Connection

❌ **Error**: `Connection timed out`  
✅ **Fix**: 
- Verify VM is running in Azure Portal
- Check firewall allows SSH (port 22)
- Verify `AZURE_HOST` IP is correct

#### Check Docker on VM

❌ **Error**: `docker: command not found`  
✅ **Fix**: SSH to VM and run:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

#### Check Container Health

❌ **Error**: `App failed to respond after 10 attempts`  
✅ **Fix**: SSH to VM and check logs:
```bash
cd ~/CoinBourg
docker compose ps
docker compose logs coinbourg
```

### View Deployment Logs on VM

```bash
# SSH into VM
ssh bourguibaCoin@4.235.122.138

# Check container status
docker compose ps

# View application logs
docker compose logs -f coinbourg

# Check health endpoint
curl http://localhost:8000/health
```

### Re-run Deployment

If deployment fails, fix the issue and either:
- Push a new commit to `main`
- Or manually trigger workflow (Actions tab → Run workflow)

---

## 🔒 Step 5: Security Best Practices

### ✅ Do This

✅ **Use GitHub Secrets** - Never commit API keys  
✅ **Rotate passwords** - Change VM password periodically  
✅ **Enable 2FA** - On GitHub account  
✅ **Review logs** - Check for unauthorized access  
✅ **Use testnet first** - Set `BINANCE_TESTNET=true` initially  
✅ **Monitor deployments** - Review each workflow run  

### ❌ Don't Do This

❌ **Never commit .env** - Already in .gitignore  
❌ **Don't share secrets** - Keep GitHub secrets private  
❌ **Don't disable SSL verification** - Security risk  
❌ **Don't skip health checks** - Catches deployment issues  

---

## 📝 Step 6: What Gets Deployed

### Files Included
✅ All Python source code (`src/`)  
✅ Configuration files (`docker-compose.yml`, `Dockerfile`)  
✅ Scripts (`scripts/`)  
✅ Frontend (`src/static/`)  
✅ Requirements (`requirements.txt`)  
✅ Database schema (`scripts/init-db.sql`)  

### Files Excluded
❌ Virtual environments (`venv/`, `.venv/`)  
❌ Git history (`.git/`)  
❌ Python cache (`__pycache__/`, `*.pyc`)  
❌ Test cache (`.pytest_cache/`)  
❌ Local .env files  

### Generated on VM
- `.env` file (created from GitHub secrets)
- Docker volumes (PostgreSQL data, Redis data)
- Log files (`logs/`)

---

## 🎓 Step 7: Advanced Configuration

### Deploy to Multiple Environments

Create separate workflows for staging/production:

```yaml
# .github/workflows/deploy-staging.yml
on:
  push:
    branches: [ develop ]

# Use different secrets:
# - STAGING_AZURE_HOST
# - STAGING_AZURE_USERNAME
# - STAGING_AZURE_PASSWORD
```

### Add Pre-Deployment Tests

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          pip install -r requirements.txt
          pytest tests/

  deploy:
    needs: test  # Only deploy if tests pass
    runs-on: ubuntu-latest
    steps:
      # ... deployment steps
```

### Slack Notifications

Add to workflow:

```yaml
- name: Notify Slack
  if: always()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

---

## ✅ Checklist: Ready to Deploy?

Before your first push to `main`, verify:

- [ ] All 7 GitHub secrets configured
- [ ] Azure VM is running
- [ ] SSH access works from your machine
- [ ] Docker installed on VM
- [ ] `.env.example` exists in repo (for reference)
- [ ] `.env` is in `.gitignore`
- [ ] Tested locally with Docker Compose
- [ ] README.md updated with VM IP
- [ ] Firewall allows port 8000 (or 80/443)

---

## 🆘 Need Help?

- **GitHub Actions failing?** Check logs in Actions tab
- **Can't access API?** Verify firewall settings
- **Database issues?** Check `docker compose logs db`
- **Out of memory?** VM may need more RAM (upgrade from B1s)

---

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Azure VM Documentation](https://docs.microsoft.com/en-us/azure/virtual-machines/)
- [CoinBourg README](./README.md)
- [Deployment Checklist](./DEPLOYMENT_CHECKLIST.md) (if exists)

---

**🎉 You're all set! Push to `main` and watch the magic happen!** 🚀
