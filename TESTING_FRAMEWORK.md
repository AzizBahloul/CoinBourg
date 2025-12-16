# CoinBourg Testing Framework

## Overview
Comprehensive testing and validation system for AI trading predictions. Track which cryptocurrencies the model predicts successfully and evaluate strategy performance across 10 different test types.

## Test Types

### 1. Backtesting
Test trading strategies on historical market data to see how they would have performed.
- **Use case**: Validate strategy before live trading
- **Parameters**: Historical date range, symbols, initial capital
- **Output**: Returns, Sharpe ratio, win rate, trade history

### 2. Paper Trading
Real-time predictions and simulated trades without using real money.
- **Use case**: Live strategy testing without risk
- **Parameters**: Real-time monitoring duration
- **Output**: Real-time P&L, prediction accuracy, trade log

### 3. Forward Testing
Run strategy on new, unseen data after backtesting.
- **Use case**: Validate backtest results aren't overfit
- **Parameters**: Out-of-sample period
- **Output**: Comparison vs backtest performance

### 4. Out-of-Sample Testing
Train/design strategy on one dataset, validate on completely separate data.
- **Use case**: Prevent overfitting
- **Parameters**: Training period, validation period
- **Output**: Cross-validation metrics

### 5. Monte Carlo Simulation
Run thousands of randomized simulations to test robustness.
- **Use case**: Understand strategy risk distribution
- **Parameters**: Number of simulations, randomization method
- **Output**: Distribution of returns, VaR, CVaR

### 6. Signal Validation
Check if buy/sell signals actually lead to profitable price movements.
- **Use case**: Validate signal quality
- **Parameters**: Validation timeframes (1h, 4h, 24h)
- **Output**: Signal success rate by timeframe

### 7. Prediction Accuracy Evaluation
Measure how often price direction predictions are correct.
- **Use case**: Track AI model accuracy
- **Parameters**: Prediction horizon
- **Output**: Directional accuracy, confusion matrix

### 8. Benchmark Comparison
Compare strategy vs buy-and-hold or market index.
- **Use case**: Justify active trading vs passive
- **Parameters**: Benchmark selection
- **Output**: Relative performance, alpha, beta

### 9. Live Testing
Use very small real capital to verify in real market conditions.
- **Use case**: Final validation before scaling
- **Parameters**: Small capital amount
- **Output**: Real slippage, execution quality

### 10. Post-Trade Analysis
Review completed predictions and trades to identify improvements.
- **Use case**: Continuous improvement
- **Parameters**: Historical trade period
- **Output**: Error analysis, timing analysis

## Quick Start

### 1. Access Testing Dashboard
```bash
# Start the application
docker-compose up -d

# Open browser
http://localhost:8000/testing
```

### 2. Run a Test via Dashboard
1. Select test type (e.g., Backtesting)
2. Enter trading pairs (BTCUSDT, ETHUSDT, etc.)
3. Set date range (last 30 days recommended)
4. Set initial capital ($10,000 default)
5. Choose risk level (Conservative/Moderate/Aggressive)
6. Click "Run Test"

### 3. Run a Test via API
```bash
curl -X POST http://localhost:8000/api/tests/run \
  -H "Content-Type: application/json" \
  -d '{
    "test_type": "backtesting",
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "start_date": "2024-11-01T00:00:00",
    "end_date": "2024-12-01T00:00:00",
    "initial_capital": 10000,
    "risk_level": "MODERATE"
  }'
```

### 4. View Results
```bash
# Get all test results
curl http://localhost:8000/api/tests/results

# Get specific test
curl http://localhost:8000/api/tests/results?test_run_id=<id>

# Get best performing symbols
curl http://localhost:8000/api/tests/best-symbols
```

## Prediction Tracking

The system tracks every prediction made by the AI:

```python
{
  "symbol": "BTCUSDT",
  "prediction_time": "2024-12-16T10:00:00Z",
  "predicted_action": "BUY",
  "predicted_direction": "UP",
  "predicted_price": 42000.00,
  "confidence": 0.85,
  "actual_price": 42500.00,
  "actual_direction": "UP",
  "outcome": "SUCCESS",
  "profit_loss_pct": 1.19
}
```

### Prediction Outcomes
- **SUCCESS**: Predicted direction matched actual movement
- **FAILURE**: Predicted opposite of actual movement
- **PARTIAL**: Neutral movement or small change

## Database Schema

### test_runs
Stores test execution metadata and overall results.
```sql
- id (UUID)
- test_type (backtesting, paper_trading, etc.)
- status (pending, running, completed, failed)
- symbols (array of trading pairs)
- start_date, end_date
- total_return, total_return_pct
- accuracy, win_rate, sharpe_ratio
- total_predictions, successful_predictions
```

### predictions
Individual prediction records with outcomes.
```sql
- id (UUID)
- test_run_id (FK to test_runs)
- symbol
- prediction_time
- predicted_action (BUY/SELL/HOLD)
- predicted_direction (UP/DOWN/NEUTRAL)
- predicted_price, actual_price
- outcome (SUCCESS/FAILURE/PARTIAL)
- profit_loss_pct
```

### symbol_performance
Aggregated performance by cryptocurrency.
```sql
- symbol
- test_type
- total_predictions, successful_predictions
- accuracy (percentage)
- total_profit_loss, avg_profit_per_trade
```

## Best Practices

### 1. Start with Backtesting
Always backtest strategy on historical data before paper trading or live testing.

### 2. Use Out-of-Sample Validation
Split data into training (70%) and validation (30%) periods.

### 3. Run Monte Carlo Simulations
Generate 1000+ simulations to understand risk distribution.

### 4. Track Symbol Performance
Focus on symbols with >70% prediction accuracy.

### 5. Paper Trade First
Run paper trading for at least 2 weeks before considering live capital.

### 6. Small Live Tests
Start with $100-500 for live testing, not full capital.

### 7. Continuous Monitoring
Use Post-Trade Analysis weekly to identify improvements.

## API Reference

### POST /api/tests/run
Start a test run.

**Request:**
```json
{
  "test_type": "backtesting",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "start_date": "2024-11-01T00:00:00",
  "end_date": "2024-12-01T00:00:00",
  "initial_capital": 10000,
  "risk_level": "MODERATE",
  "parameters": {}
}
```

**Response:**
```json
{
  "status": "Test started",
  "test_type": "backtesting",
  "message": "Test running in background"
}
```

### GET /api/tests/results
Get test results (supports filtering).

**Query Parameters:**
- `test_run_id`: Filter by specific test
- `test_type`: Filter by test type
- `limit`: Max results (default 100)

### GET /api/tests/{test_run_id}/predictions
Get predictions for specific test.

**Query Parameters:**
- `symbol`: Filter by cryptocurrency

### GET /api/tests/best-symbols
Get cryptocurrencies with highest prediction accuracy.

**Query Parameters:**
- `test_type`: Filter by test type
- `limit`: Max results (default 10)

## Troubleshooting

### Test Not Starting
```bash
# Check API logs
docker-compose logs -f coinbourg

# Verify database connection
docker-compose exec db psql -U coinbourg -d coinbourg -c "SELECT * FROM test_runs LIMIT 1;"
```

### No Predictions Showing
```bash
# Check if predictions table exists
docker-compose exec db psql -U coinbourg -d coinbourg -c "\dt predictions"

# Reinitialize database if needed
docker-compose down -v
docker-compose up -d
```

### Performance Issues
```bash
# Reduce number of symbols
# Use shorter date ranges for backtesting
# Increase Docker memory limits in docker-compose.yml
```

## Future Enhancements

- [ ] Real-time test progress tracking
- [ ] Export test results to CSV/Excel
- [ ] Custom strategy definition via UI
- [ ] A/B testing between strategies
- [ ] Machine learning model comparison
- [ ] Automated parameter optimization
- [ ] Alert system for prediction accuracy drops
- [ ] Integration with TradingView

## Support

For issues or questions:
1. Check logs: `docker-compose logs -f`
2. Review API docs: `http://localhost:8000/docs`
3. Check database: `scripts/diagnose.sh`
