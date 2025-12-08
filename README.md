# CoinBourg - AI-Powered Cryptocurrency Trading Bot

<div align="center">

![CoinBourg Logo](https://img.shields.io/badge/CoinBourg-AI%20Trading%20Bot-6366f1?style=for-the-badge&logo=bitcoin&logoColor=white)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

**An intelligent, automated cryptocurrency trading system powered by DeepSeek AI**

[Features](#-features) •
[Quick Start](#-quick-start) •
[Architecture](#-architecture) •
[Configuration](#-configuration) •
[Deployment](#-deployment) •
[API Reference](#-api-reference)

</div>

---

## 🎯 Overview

CoinBourg is a professional-grade, AI-powered cryptocurrency trading bot designed to analyze real-time market data and execute trades automatically. It uses **DeepSeek AI** for intelligent market analysis and **Binance** for trade execution.

### Why CoinBourg?

- 🤖 **AI-Powered Analysis**: Uses DeepSeek-V3.2 for sophisticated market sentiment analysis
- 📊 **Technical Indicators**: RSI, MACD, Bollinger Bands, ATR, Stochastic, and more
- 🛡️ **Risk Management**: Configurable risk levels (Conservative, Moderate, Aggressive)
- 💰 **Free to Run**: Uses free-tier services (Azure Student, Binance API, DeepSeek API)
- 🐳 **Docker Ready**: One-command deployment with Docker Compose
- 📱 **Web Dashboard**: Real-time monitoring and control interface

---

## ✨ Features

### Trading Features
- ✅ Real-time market monitoring
- ✅ AI-powered buy/sell signals
- ✅ Automatic stop-loss and take-profit
- ✅ Multiple trading pairs support
- ✅ Position sizing based on portfolio percentage
- ✅ Daily trade limits
- ✅ Maximum drawdown protection

### Technical Analysis
- ✅ RSI (Relative Strength Index)
- ✅ MACD (Moving Average Convergence Divergence)
- ✅ Bollinger Bands
- ✅ EMA/SMA Moving Averages
- ✅ ATR (Average True Range)
- ✅ Stochastic Oscillator
- ✅ Order book analysis
- ✅ Volume analysis

### Risk Management
| Risk Level | Max Position | Stop Loss | Take Profit | Daily Trades | Max Drawdown |
|------------|--------------|-----------|-------------|--------------|--------------|
| Conservative | 2% | 1.5% | 3% | 5 | 5% |
| Moderate | 5% | 2.5% | 5% | 10 | 10% |
| Aggressive | 10% | 4% | 8% | 20 | 20% |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Binance Account with API keys
- DeepSeek API key

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/CoinBourg.git
cd CoinBourg
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit with your API keys
nano .env
```

**Required configuration:**
```env
# DeepSeek AI (Get from: https://platform.deepseek.com/api_keys)
DEEPSEEK_API_KEY=your_deepseek_key

# Binance API (Get from: https://www.binance.com/en/my/settings/api-management)
BINANCE_API_KEY=your_binance_key
BINANCE_API_SECRET=your_binance_secret
BINANCE_TESTNET=true  # Set to false for live trading
```

### 3. Start with Docker

```bash
# Build and start all services
docker compose up -d

# View logs
docker compose logs -f coinbourg
```

### 4. Access the Dashboard

Open your browser to: `http://localhost:8000`

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CoinBourg System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     ┌───────────────┐     ┌──────────────┐   │
│  │   DeepSeek   │────▶│    Trading    │────▶│   Binance    │   │
│  │   AI (LLM)   │◀────│    Engine     │◀────│     API      │   │
│  └──────────────┘     └───────────────┘     └──────────────┘   │
│         │                    │                     │            │
│         │                    ▼                     │            │
│         │            ┌───────────────┐             │            │
│         │            │  Risk Manager │             │            │
│         │            └───────────────┘             │            │
│         │                    │                     │            │
│         ▼                    ▼                     ▼            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    FastAPI REST API                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│         │                    │                     │            │
│         ▼                    ▼                     ▼            │
│  ┌──────────────┐     ┌───────────────┐     ┌──────────────┐   │
│  │  PostgreSQL  │     │     Redis     │     │ Web Dashboard │   │
│  └──────────────┘     └───────────────┘     └──────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
CoinBourg/
├── src/
│   ├── api/                 # FastAPI REST API
│   │   ├── __init__.py
│   │   └── main.py          # API endpoints
│   ├── config/              # Configuration
│   │   ├── __init__.py
│   │   ├── settings.py      # Environment settings
│   │   └── constants.py     # Constants and enums
│   ├── core/                # Core trading logic
│   │   ├── __init__.py
│   │   ├── binance_client.py    # Binance API wrapper
│   │   ├── deepseek_client.py   # DeepSeek AI client
│   │   └── trading_engine.py    # Main trading engine
│   ├── static/              # Web dashboard
│   │   └── index.html
│   └── main.py              # Application entry point
├── scripts/
│   ├── deploy-azure.sh      # Azure VM deployment script
│   ├── start.sh             # Quick start script
│   ├── backup.sh            # Database backup script
│   └── init-db.sql          # Database initialization
├── nginx/
│   └── nginx.conf           # Nginx reverse proxy config
├── docker-compose.yml       # Docker services configuration
├── Dockerfile               # Application container
├── requirements.txt         # Python dependencies
├── .env.example            # Example environment file
└── README.md               # This file
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | Required |
| `BINANCE_API_KEY` | Binance API key | Required |
| `BINANCE_API_SECRET` | Binance API secret | Required |
| `BINANCE_TESTNET` | Use Binance testnet | `true` |
| `RISK_LEVEL` | Risk level preset | `CONSERVATIVE` |
| `TRADING_PAIRS` | Trading pairs to monitor | `["BTCUSDT", "ETHUSDT"]` |
| `ANALYSIS_INTERVAL_SECONDS` | AI analysis interval | `300` |

### Risk Presets

You can change the risk level at runtime through the API or dashboard:

```bash
# Change risk level via API
curl -X POST http://localhost:8000/risk-settings \
  -H "Content-Type: application/json" \
  -d '{"risk_level": "MODERATE"}'
```

---

## 🚢 Deployment

### ✅ Pre-Deployment Safeguards

Before deploying, always run the pre-flight check to catch issues early:

```bash
# Run comprehensive deployment validation
bash scripts/preflight-check.sh
```

This validates:
- ✓ Docker and Docker Compose installation
- ✓ Required files and directory structure
- ✓ .env file syntax and required variables
- ✓ Docker Compose configuration
- ✓ Python requirements
- ✓ Secret protection (.env not in image)

**See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for quick reference before each deployment.**

### Deploy to Azure Student VM

1. **Create Azure VM** (Ubuntu 22.04 LTS, B1s - Free tier)

2. **SSH into your VM:**
```bash
ssh your_username@YOUR_VM_IP
```

3. **Upload files:**
```bash
# From your local machine
scp -r ./* your_username@YOUR_VM_IP:~/coinbourg/
```

4. **Run pre-flight checks:**
```bash
cd ~/coinbourg
bash scripts/preflight-check.sh  # Must pass before proceeding
```

5. **Configure and start:**
```bash
cp .env.example .env
nano .env  # Add your API keys (BINANCE_API_KEY, BINANCE_API_SECRET, DEEPSEEK_API_KEY)
docker compose up -d --build
```

6. **Verify deployment:**
```bash
docker compose ps           # Check all containers are healthy
docker compose logs -f      # Monitor logs in real-time
curl http://localhost:8000/health  # Verify app is responding
```

### Automated Deployment (GitHub Actions)

Push to `main` branch to trigger automatic deployment:

1. **Commit and push:**
```bash
git add .
git commit -m "Your changes"
git push origin main
```

2. **Workflow automatically:**
   - ✅ Creates deployment archive
   - ✅ Uploads to Azure VM via SSH
   - ✅ Validates .env syntax
   - ✅ Rebuilds Docker containers
   - ✅ Verifies app health
   - ✅ Logs deployment status

3. **Monitor workflow:**
   - GitHub Actions: https://github.com/AzizBahloul/CoinBourg/actions
   - Check "Deploy to Azure VM" step for status

### Runtime Safeguards

The bot includes startup validation that automatically:
- ✅ Ensures all required directories exist with correct permissions
- ✅ Verifies logging directory is writable
- ✅ Prevents crashes due to permission errors
- ✅ Provides clear error messages if validation fails

**See [DEPLOYMENT_PREVENTION_GUIDE.md](DEPLOYMENT_PREVENTION_GUIDE.md) for detailed information on all safeguards.**

### Access Points

- **API Documentation**: `http://YOUR_VM_IP:8000/docs`
- **Dashboard**: `http://YOUR_VM_IP:8000`
- **Health Check**: `http://YOUR_VM_IP:8000/health`
- **AI Thought Feed**: Real-time decision tracking in dashboard

---

## 📚 API Reference

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Bot status and metrics |
| `/trades` | GET | Recent trades list |
| `/positions` | GET | Open positions |
| `/analyze` | POST | Run AI analysis on symbol |
| `/start` | POST | Start automated trading |
| `/stop` | POST | Stop automated trading |
| `/risk-settings` | GET/POST | View/update risk settings |

### Example: Run Analysis

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT"}'
```

**Response:**
```json
{
  "symbol": "BTCUSDT",
  "sentiment": "BULLISH",
  "action": "BUY",
  "confidence": 0.75,
  "entry_price": 42150.00,
  "stop_loss": 41307.00,
  "take_profit": 43836.00,
  "reasoning": "Strong bullish momentum with RSI at 55..."
}
```

### Example: Get Status

```bash
curl http://localhost:8000/status
```

**Response:**
```json
{
  "is_running": true,
  "portfolio_value": 1000.00,
  "total_pnl": 45.50,
  "total_trades": 15,
  "winning_trades": 10,
  "losing_trades": 5,
  "win_rate": 66.67,
  "open_positions": 1,
  "risk_level": "MODERATE"
}
```

---

## 🛡️ Security Best Practices

1. **Never commit API keys** - Always use environment variables
2. **Use testnet first** - Test thoroughly before live trading
3. **Start conservative** - Use CONSERVATIVE risk level initially
4. **Monitor regularly** - Check the dashboard daily
5. **Set up alerts** - Configure Telegram notifications (optional)
6. **Regular backups** - Use the backup script weekly

---

## 📈 Performance Tips

### For Azure B1s (1GB RAM)

1. **Memory optimization** is already configured in docker-compose.yml
2. **Swap is enabled** by the deployment script (2GB)
3. **PostgreSQL is tuned** for low memory
4. **Redis has memory limits** configured

### Monitoring Commands

```bash
# Check container status
docker compose ps

# View real-time logs
docker compose logs -f coinbourg

# Check resource usage
docker stats

# View database
docker exec -it coinbourg-db psql -U coinbourg -d coinbourg
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## ⚠️ Disclaimer

**IMPORTANT**: This software is for educational purposes only. Cryptocurrency trading involves substantial risk of loss. The developers are not responsible for any financial losses incurred through the use of this software.

- Always use testnet for testing
- Never invest more than you can afford to lose
- Past performance does not guarantee future results
- This is not financial advice

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ for the crypto community**

[Report Bug](https://github.com/yourusername/CoinBourg/issues) •
[Request Feature](https://github.com/yourusername/CoinBourg/issues)

</div>