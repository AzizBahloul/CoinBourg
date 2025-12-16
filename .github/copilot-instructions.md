# CoinBourg AI Agent Instructions

## Project Overview
CoinBourg is an AI-powered cryptocurrency trading bot using **DeepSeek AI** for market analysis and **Binance** for execution. The system is 45% complete (Phase 1 done, Phase 2 in progress).

## Architecture & Data Flow

```
BinanceClient → MarketScanner → StrategyManager → DeepSeekClient → TradingEngine → RiskManager → BinanceClient (execution)
                     ↓              ↓                   ↓                ↓              ↓
              CoinSelector    WebSocketClient      AI Analysis    Position Mgmt   Stop-Loss/TP
```

### Core Components (`src/core/`)
- **`trading_engine.py`** (861 lines): Orchestrates all operations. Uses async event loop with configurable intervals (`ANALYSIS_INTERVAL_SECONDS=300`, `PRICE_CHECK_INTERVAL_SECONDS=10`). Key: `Trade` and `Position` dataclasses track state.
- **`coin_selector.py`**: Dynamic pair selection - scans ALL Binance USDT pairs (100-500), filters by volume (`MIN_VOLUME_USD=1M`), ranks by composite score (momentum 30%, Sharpe 20%, etc.). Caches for `SCAN_INTERVAL_HOURS`.
- **`market_scanner.py`**: Parallel analysis of top N coins (from `CoinSelector`). Computes RSI, MACD, Bollinger Bands, ATR, Stochastic using `ta` library.
- **`strategy_manager.py`**: 4 strategies (Momentum, MeanReversion, Breakout, Scalping) generate `StrategySignal` objects. Uses weighted voting for consensus.
- **`deepseek_client.py`**: AI analysis with rate limiting (token bucket), exponential backoff, health checks every 5min. Returns `generate_trading_signals()` with specific params.
- **`binance_client.py`**: Exchange interface with circuit breaker, OCO orders, TWAP execution, slippage checks. Testnet-aware (`BINANCE_TESTNET=true`).
- **`websocket_client.py`**: Real-time price/orderbook streaming. Tracks large orders (>$100k whale watching).
- **`risk_manager.py`** (812 lines): Position sizing, stop-loss/take-profit, drawdown protection. Uses `RISK_PRESETS` from settings.

### Configuration (`src/config/`)
- **`settings.py`**: Pydantic settings with validators. Critical toggles: `DYNAMIC_PAIR_SELECTION=true`, `PAPER_TRADING=true` (default), `TRADING_ENABLED=false` (master kill switch).
- **`constants.py`**: Enums (`TradeAction`, `MarketSentiment`, `OrderType`, `TimeFrame`, etc.) and `INDICATOR_PARAMS` dict.

### Risk Levels (in `settings.py`)
```python
RISK_PRESETS = {
    "CONSERVATIVE": {"max_position_size_percent": 2.0, "stop_loss_percent": 1.5, ...},
    "MODERATE": {"max_position_size_percent": 5.0, "stop_loss_percent": 2.5, ...},
    "AGGRESSIVE": {"max_position_size_percent": 10.0, "stop_loss_percent": 4.0, ...}
}
```

## Development Workflows

### Running the Bot
```bash
# API only (default - runs FastAPI + dashboard)
python src/main.py --mode api

# Trading engine only
python src/main.py --mode bot

# Both (API handles bot lifecycle in background)
python src/main.py --mode both
```

### Docker Deployment
```bash
# Full stack (app + PostgreSQL + Redis)
docker compose up -d

# View logs
docker compose logs -f coinbourg

# Optimized for Azure B1s (1 vCPU, 1GB RAM) - memory limits in docker-compose.yml
```

### Testing
```bash
# Run all tests
pytest

# Specific test file
pytest tests/test_risk_manager.py

# System verification (checks Binance + DeepSeek connectivity)
python scripts/verify_system.py
```

### Database
- PostgreSQL schema initialized via `scripts/init-db.sql`
- Connection: `DATABASE_URL=postgresql://coinbourg:coinbourg_secure_password@db:5432/coinbourg`
- Redis for caching: `REDIS_URL=redis://redis:6379/0`

## Critical Patterns & Conventions

### Safety-First Approach
**NEVER enable live trading without extensive testing.** Three-tier safety:
1. `PAPER_TRADING=true` (default) - simulated orders only
2. `TRADING_ENABLED=false` (default) - master kill switch
3. `BINANCE_TESTNET=true` (default) - uses testnet even if above are enabled

### Async/Await Throughout
All I/O operations use `async`/`await`. Main loop in `TradingEngine.run()` uses `asyncio.gather()` for parallel tasks. Never use blocking calls in core modules.

### Dataclass-First State
Use `@dataclass` for structured data (`Trade`, `Position`, `StrategySignal`, `CoinMetrics`). Avoids dict hell and provides type hints.

### Logging Standards
```python
logger = logging.getLogger(__name__)
logger.info(f"Symbol: {symbol}, Price: ${price:.2f}")  # Use f-strings
```
Logs go to `logs/coinbourg_YYYYMMDD.log`. Log level from `LOG_LEVEL` env var.

### Error Handling
```python
# BinanceClient uses CircuitBreaker
try:
    result = await self.binance_client.create_order(...)
except Exception as e:
    logger.error(f"Order failed: {e}")
    # Graceful degradation - don't crash main loop
```

### Settings Access
```python
from src.config.settings import get_settings, RISK_PRESETS

settings = get_settings()  # Cached singleton
risk = RISK_PRESETS[settings.RISK_LEVEL]
```

## API Reference (`src/api/main.py`)

FastAPI server on port 8000. Key endpoints:
- `GET /health` - Health check
- `GET /api/status` - Bot status, positions, P&L
- `GET /api/positions` - Open positions
- `GET /api/trades` - Trade history
- `POST /api/start` - Start trading engine
- `POST /api/stop` - Stop trading engine
- `POST /api/analyze/{symbol}` - Force analysis on symbol

Rate limited: 100 req/min per IP. No auth (development mode).

## Important Files for Context

- **`IMPLEMENTATION_STATUS.md`**: 400-line detailed roadmap. Check before adding features.
- **`QUICK_REFERENCE.md`**: Phase 1 summary, test commands, safety checklist.
- **`PHASE1_COMPLETE.md`**: What's implemented vs. what's pending.
- **`README.md`**: User-facing docs, quick start, architecture diagram.

## Integration Points

### External APIs
- **Binance REST API**: `https://api.binance.com` (prod) or `https://testnet.binance.vision` (testnet)
- **Binance WebSocket**: `wss://stream.binance.com:9443/ws/<stream>`
- **DeepSeek API**: `https://api.deepseek.com` - uses `deepseek-chat` model

### Inter-Component Communication
- `TradingEngine` → `CoinSelector.scan_market()` → top N coins
- `MarketScanner.analyze_market(symbols)` → parallel fetch indicators
- `StrategyManager.get_consensus(symbol, data, indicators)` → weighted signal
- `DeepSeekClient.generate_trading_signals(symbol, indicators, signals)` → AI decision
- `RiskManager.validate_trade(signal, portfolio)` → risk-adjusted order
- `BinanceClient.create_oco_order(symbol, qty, take_profit, stop_loss)` → execution

### Data Flow Example
```python
# 1. Select coins (hourly)
coins = await coin_selector.scan_market()

# 2. Scan markets (every 5 min)
for symbol in coins[:30]:
    data = await market_scanner.fetch_price_data(symbol)
    indicators = await market_scanner.calculate_indicators(data)
    
    # 3. Get strategy signals
    signals = await strategy_manager.get_consensus(symbol, data, indicators)
    
    # 4. AI analysis
    ai_decision = await deepseek_client.generate_trading_signals(symbol, indicators, signals)
    
    # 5. Risk validation
    if risk_manager.validate_trade(ai_decision):
        # 6. Execute
        await binance_client.create_oco_order(...)
```

## When Modifying Code

### Adding New Strategies
1. Subclass `BaseStrategy` in `strategy_manager.py`
2. Implement `async def analyze(symbol, price_data, indicators, market_context)`
3. Return `StrategySignal` with confidence 0-1
4. Register in `StrategyManager.__init__()` with weight

### Changing Risk Parameters
Edit `RISK_PRESETS` in `settings.py`. Don't hardcode values in modules - always use `get_settings()`.

### Database Schema Changes
1. Update `scripts/init-db.sql`
2. Add migration logic or rebuild: `docker compose down -v && docker compose up -d`

### Environment Variables
1. Add to `Settings` class in `settings.py` with `Field(...)` validator
2. Document in `README.md` config table
3. Add to `.env.example` (not in repo, create locally)

## Common Gotchas

- **Async Context Managers**: Use `async with` for BinanceClient, WebSocketClient operations
- **USDT Pairs Only**: System currently hardcoded to USDT base (see `CoinSelector._get_all_usdt_pairs()`)
- **Memory Constraints**: Docker setup assumes 1GB RAM total (Azure B1s). Watch container limits in `docker-compose.yml`
- **Testnet Data**: Binance testnet has limited pairs vs. mainnet. Dynamic selection may return fewer coins.
- **Rate Limits**: Binance: 1200 req/min, 10 orders/sec. DeepSeekClient handles this internally.

## Recommended Next Steps (from IMPLEMENTATION_STATUS.md)

Phase 2 priorities:
1. **Backtesting Engine** (`src/backtesting/backtest_engine.py` exists but incomplete)
2. **Advanced Trading Engine** features (partial exits, trailing stops)
3. **Sentiment Analyzer** (web scraping, social media)
4. **ML Predictor** (XGBoost/LightGBM price forecasting)

Always run `scripts/verify_system.py` after major changes to validate Binance + DeepSeek connectivity.

## Testing & Validation Framework (NEW)

### Testing Module (`src/testing/`)
Comprehensive testing system with 10 test types:

1. **Backtesting** (`backtesting.py`) - Historical data analysis
2. **Paper Trading** (`paper_trading.py`) - Real-time simulation
3. **Forward Testing** (`forward_testing.py`) - Out-of-sample validation
4. **Monte Carlo** (`monte_carlo.py`) - Robustness testing with randomized simulations
5. **Signal Validation** (`signal_validator.py`) - Buy/sell signal accuracy
6. **Prediction Accuracy** (`prediction_evaluator.py`) - Directional prediction evaluation
7. **Benchmark Comparison** (`benchmark_comparator.py`) - vs buy-and-hold
8. **Out-of-Sample** (`out_of_sample.py`) - Separate dataset validation
9. **Live Testing** (`live_tester.py`) - Small capital real testing
10. **Post-Trade Analysis** (`post_trade_analyzer.py`) - Completed trade review

### Testing API Endpoints
- `POST /api/tests/run` - Start a test run with configuration
- `GET /api/tests/results` - Retrieve test results (filterable)
- `GET /api/tests/{test_run_id}/predictions` - Get predictions for specific test
- `GET /api/tests/best-symbols` - Cryptocurrencies with best accuracy
- `GET /api/tests/types` - List all available test types

### Testing Dashboard
Access at `http://localhost:8000/testing`
- Select test type from 10 options
- Configure parameters (symbols, dates, capital, risk level)
- View results in real-time with auto-refresh
- Track prediction accuracy by cryptocurrency
- See which symbols the model predicts best

### Database Schema (added to `init-db.sql`)
- `test_runs` - Test execution metadata and results
- `predictions` - Individual prediction records with outcomes
- `test_equity_curve` - Time-series equity data
- `symbol_performance` - Aggregated performance by symbol

### Prediction Tracking Pattern
```python
# Record prediction
prediction = PredictionRecord(
    test_run_id=test_run_id,
    symbol=symbol,
    prediction_time=datetime.utcnow(),
    predicted_action='BUY',  # or SELL, HOLD
    predicted_price=current_price,
    predicted_direction='UP',  # or DOWN, NEUTRAL
    confidence=0.75,
    ai_reasoning="Strong upward momentum..."
)

# Later, evaluate outcome
prediction.actual_price = future_price
prediction.outcome = 'SUCCESS'  # or FAILURE, PARTIAL
prediction.profit_loss_pct = calculate_pnl()

# Save to database
await db_manager.save_prediction(prediction)
await db_manager.update_symbol_performance(symbol, test_type, prediction)
```

### Running Tests
```python
from src.testing.test_engine import TestEngine, TestType, TestConfiguration

engine = TestEngine(db_manager)

config = TestConfiguration(
    test_type=TestType.BACKTESTING,
    symbols=['BTCUSDT', 'ETHUSDT'],
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 1),
    initial_capital=10000.0,
    risk_level='MODERATE'
)

result = await engine.run_test(TestType.BACKTESTING, config)
# Result includes: accuracy, returns, sharpe ratio, predictions, symbol_results
```

### Deployment
```bash
# Complete deployment to Azure VM
./scripts/deploy_complete.sh

# Access dashboards
# Main: http://your-vm-ip:8000/
# Testing: http://your-vm-ip:8000/testing
# API Docs: http://your-vm-ip:8000/docs
```

