# Quick Deployment Checklist

Use this before every deployment to catch issues early.

## Pre-Deployment (Local Machine)

- [ ] **Run pre-flight checks**
  ```bash
  bash scripts/preflight-check.sh
  ```
  ✓ Must see: "✅ Pre-flight check PASSED!"

- [ ] **Verify .env file**
  ```bash
  cat .env | grep -v '^#' | sort
  ```
  ✓ Should have: BINANCE_API_KEY, BINANCE_API_SECRET, DATABASE_URL, REDIS_URL, DEEPSEEK_API_KEY
  ✗ Should NOT have: Escaped quotes, special shell characters

- [ ] **Test locally (optional but recommended)**
  ```bash
  docker compose down
  docker compose up -d --build
  sleep 10
  docker compose ps
  docker compose logs --tail=20 coinbourg-bot
  ```
  ✓ All containers should be "Up" and healthy

- [ ] **Verify no uncommitted secrets**
  ```bash
  git status
  ```
  ✗ .env should NOT be in git
  ✓ .env should be in .gitignore

## Git Commit & Push

- [ ] **Commit changes (except .env)**
  ```bash
  git add .
  git reset .env  # Don't commit .env!
  git commit -m "Your message"
  git push origin main
  ```

- [ ] **Watch GitHub Actions** 
  - Go to: https://github.com/AzizBahloul/CoinBourg/actions
  - ✓ Workflow should complete successfully
  - Check "Deploy to Azure VM" step logs for:
    - "✓ Docker Compose configuration valid"
    - "✓ App is healthy and responding"

## Post-Deployment (Azure VM)

- [ ] **SSH into Azure VM**
  ```bash
  ssh bourguibaCoin@4.235.122.138
  cd ~/CoinBourg
  ```

- [ ] **Check container status**
  ```bash
  docker compose ps
  ```
  ✓ All 3 containers should show "Up"
  ✓ Status should show "healthy" for db and redis

- [ ] **Check app is responding**
  ```bash
  curl http://localhost:8000/health
  ```
  ✓ Should return: `{"status":"healthy"}`

- [ ] **Check no permission errors**
  ```bash
  docker compose logs --tail=30 coinbourg-bot | grep -i "permission\|error"
  ```
  ✗ Should NOT see permission errors
  ✓ Should see: "Permission validation successful"

- [ ] **Verify logs are being written**
  ```bash
  ls -la /home/bourguibaCoin/CoinBourg/logs/
  ```
  ✓ Recent log file should exist

## Monitor Dashboard

- [ ] **Access web dashboard**
  - Open: http://4.235.122.138:8000/
  - ✓ Should see portfolio stats
  - ✓ Live AI Thought Process should be populating

- [ ] **Monitor for errors (5-10 minutes)**
  ```bash
  docker compose logs -f coinbourg-bot
  ```
  - Watch for any crashed containers
  - Verify trading decisions are being made

## Rollback (If Issues)

```bash
# Stop current deployment
docker compose down

# Check recent changes
git log --oneline -5

# Revert to previous version
git revert HEAD
git push origin main

# OR rebuild from last known-good commit
git reset --hard <commit-hash>
git push origin main --force
```

## Common Issues & Quick Fixes

| Issue | Check | Fix |
|-------|-------|-----|
| Permission denied on logs | `docker compose logs coinbourg-bot \| grep -i permission` | `docker compose down && docker compose up -d --build` |
| .env syntax error | `cat .env \| grep -E '\$\|\`' ` | Remove special chars, or recreate .env |
| Containers not starting | `docker compose ps` | Check: `docker compose logs` |
| App not responding | `curl http://localhost:8000/health` | Wait 30 seconds, check logs |
| Database connection error | `docker compose logs db` | Check DATABASE_URL in .env |

## Contact for Help

- **GitHub Actions logs**: https://github.com/AzizBahloul/CoinBourg/actions
- **Local testing**: Run `docker compose logs --tail=100`
- **Full guide**: See DEPLOYMENT_PREVENTION_GUIDE.md
