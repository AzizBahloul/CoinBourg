# Dynamic Coin Selection 🎯

## Overview

Instead of trading only 5 hardcoded coins, CoinBourg can **automatically scan ALL Binance USDT pairs** (100-500 coins) and select the top performers based on volume, momentum, and technical indicators.

---

## How It Works

### 1. **Market Scanning** 🔍

Every hour (configurable), the bot:
1. Fetches **all USDT trading pairs** from Binance (typically 300-500 pairs)
2. Filters out low-quality coins
3. Computes comprehensive metrics for each coin
4. Ranks coins by composite score
5. Selects top N coins (default: 30)

### 2. **Filtering Criteria** ✅

Coins must pass these filters:

| Filter | Criteria | Purpose |
|--------|----------|---------|
| **Volume** | 24h volume > $1M USD | Ensures liquidity |
| **Status** | Trading enabled | Avoids delisted coins |
| **Spread** | < 0.5% | Reduces slippage |
| **Age** | Listed > 7 days | Avoids new, unstable coins |

### 3. **Scoring Metrics** 📊

Each coin is scored on:

| Metric | Weight | Description |
|--------|--------|-------------|
| **Momentum** | 30% | Price momentum (24h, 7d, 30d changes) |
| **Sharpe Ratio** | 20% | Risk-adjusted returns |
| **Volume Trend** | 15% | Volume growth over 30 days |
| **Volatility** | 15% | 30-day volatility (higher = more opportunities) |
| **Max Drawdown** | 10% | Recent drawdown (lower = safer) |
| **Spread** | 10% | Bid-ask spread (lower = better) |

### 4. **Composite Score** 🏆

```python
composite_score = (
    momentum_score * 0.30 +
    sharpe_ratio * 0.20 +
    volume_trend * 0.15 +
    volatility_score * 0.15 +
    drawdown_score * 0.10 +
    spread_score * 0.10
)
```

Top scoring coins are selected for trading.

---

## Configuration ⚙️

### Enable Dynamic Selection

Add to your `.env` file:

```env
# Enable dynamic coin scanning
DYNAMIC_PAIR_SELECTION=true

# Minimum 24h volume in USD (filters out low-volume coins)
MIN_VOLUME_USD=1000000

# Maximum number of coins to trade simultaneously
MAX_COINS_SCAN=30

# Hours between market scans (coin list refresh)
SCAN_INTERVAL_HOURS=1
```

### Settings Explained

#### `DYNAMIC_PAIR_SELECTION`
- **`true`**: Scans ALL Binance pairs, selects top performers
- **`false`**: Uses fixed `TRADING_PAIRS` list (5 coins)

#### `MIN_VOLUME_USD`
- Minimum 24h trading volume in USD
- **$1M** = Good liquidity, low slippage
- **$5M** = Very liquid, institutional-grade
- **$100K** = High risk, may have slippage

#### `MAX_COINS_SCAN`
- How many top coins to analyze/trade
- **10-20**: Conservative, focus on best
- **30-50**: Moderate, more diversification
- **100+**: Aggressive, requires more API calls

#### `SCAN_INTERVAL_HOURS`
- How often to refresh coin rankings
- **1 hour**: Responsive to market changes
- **4 hours**: Balanced
- **24 hours**: Stable, less API usage

---

## Example: What Gets Selected

### Typical Top 30 Coins (by composite score)

```
Rank  Symbol       Score   Volume 24h   Price Change 24h   Momentum
----  ----------   -----   ----------   ----------------   --------
1     BTCUSDT      92.5    $45.2B       +3.2%              High ↑
2     ETHUSDT      89.3    $28.1B       +4.1%              High ↑
3     BNBUSDT      87.1    $2.8B        +2.8%              Medium ↑
4     SOLUSDT      85.9    $5.1B        +8.2%              Very High ↑
5     XRPUSDT      84.2    $4.2B        +1.5%              Medium ↑
...
30    ARBUSDT      72.1    $980M        -0.5%              Low →
```

### Coins That Get Filtered Out

❌ **Low volume**: `RARE/USDT` ($50K volume)  
❌ **Wide spread**: `LAZIO/USDT` (1.2% spread)  
❌ **Recently listed**: `TOKEN/USDT` (3 days old)  
❌ **Not trading**: `LUNA/USDT` (delisted)  

---

## Benefits of Dynamic Selection 🎁

### ✅ Advantages

1. **Captures Trends** - Automatically finds trending coins
2. **Adapts to Market** - Portfolio changes with market conditions
3. **Reduces Risk** - Filters out low-quality coins
4. **Maximizes Opportunities** - 30 coins vs. 5 = 6x more trades
5. **No Manual Updates** - No need to edit TRADING_PAIRS constantly

### ⚠️ Considerations

1. **More API Calls** - Scanning 300+ coins uses more Binance API quota
2. **Higher Complexity** - More coins = more to monitor
3. **Needs Good Internet** - More data to fetch
4. **Rate Limits** - May hit Binance limits if too aggressive

---

## Performance Comparison 📈

### Fixed Pairs (5 coins)
```
BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT
```
- ✅ Predictable, stable
- ✅ Low API usage
- ❌ Misses trending altcoins
- ❌ Limited diversification
- **Average Daily Opportunities**: 5-10 signals

### Dynamic Selection (30 coins)
```
Top 30 coins by volume/momentum (changes hourly)
```
- ✅ Catches trending coins early
- ✅ Better diversification
- ✅ Adapts to market conditions
- ⚠️ More API calls
- **Average Daily Opportunities**: 30-60 signals

---

## Implementation Details 🔧

### Code Flow

```python
# 1. Get all USDT pairs from Binance
all_symbols = await binance_client.get_exchange_info()
usdt_pairs = [s for s in all_symbols if s.endswith('USDT')]
# Result: 300-500 pairs

# 2. Filter by volume
filtered = [s for s in usdt_pairs if volume(s) > MIN_VOLUME_USD]
# Result: ~100-200 pairs

# 3. Compute metrics for each
metrics = await compute_metrics(filtered)
# Calculates: momentum, Sharpe, volatility, etc.

# 4. Rank by composite score
ranked = sorted(metrics, key=lambda x: x.composite_score, reverse=True)

# 5. Select top N
top_coins = ranked[:MAX_COINS_SCAN]
# Result: Top 30 coins

# 6. Cache for 1 hour
cache(top_coins, ttl=SCAN_INTERVAL_HOURS * 3600)
```

### Performance

- **Scan Time**: 20-60 seconds (depending on Binance API speed)
- **Memory**: ~5-10 MB for coin data
- **API Calls**: ~300-500 calls per scan
- **Cache**: Results cached for 1 hour (default)

---

## Monitoring Dynamic Selection 📊

### View Selected Coins in Logs

```bash
# Start bot and watch logs
docker compose logs -f coinbourg

# You'll see:
[INFO] CoinSelector - Starting market scan for all USDT pairs...
[INFO] CoinSelector - Found 387 USDT pairs
[INFO] CoinSelector - After filtering: 142 pairs remain
[INFO] CoinSelector - Computed metrics for 142 coins
[INFO] CoinSelector - Market scan completed in 35.2s - Top coin: BTCUSDT (score: 92.5)
[INFO] TradingEngine - Dynamic scan returned 30 coins: BTCUSDT, ETHUSDT, BNBUSDT, ...
```

### View in Dashboard

The Live AI Thought Process will show analysis for all selected coins in rotation.

---

## Troubleshooting 🔧

### Issue: "Dynamic scan failed, using default pairs"

**Cause**: Binance API error or rate limit  
**Fix**:
```env
# Reduce scan frequency
SCAN_INTERVAL_HOURS=4

# Or disable dynamic selection temporarily
DYNAMIC_PAIR_SELECTION=false
```

### Issue: "Only analyzing 5 coins"

**Cause**: `DYNAMIC_PAIR_SELECTION=false` or not set  
**Fix**:
```env
DYNAMIC_PAIR_SELECTION=true
```

### Issue: "Rate limit exceeded"

**Cause**: Too many API calls  
**Fix**:
```env
# Reduce max coins
MAX_COINS_SCAN=15

# Increase scan interval
SCAN_INTERVAL_HOURS=2
```

### Issue: "Scan takes too long (>2 minutes)"

**Cause**: Slow network or too many pairs  
**Fix**:
```env
# Increase minimum volume (fewer coins)
MIN_VOLUME_USD=5000000
```

---

## Best Practices 🌟

### Conservative Strategy
```env
DYNAMIC_PAIR_SELECTION=true
MIN_VOLUME_USD=5000000       # $5M+ only (very liquid)
MAX_COINS_SCAN=10            # Top 10 only
SCAN_INTERVAL_HOURS=4        # Every 4 hours
```

### Moderate Strategy (Recommended)
```env
DYNAMIC_PAIR_SELECTION=true
MIN_VOLUME_USD=1000000       # $1M+ (good liquidity)
MAX_COINS_SCAN=30            # Top 30
SCAN_INTERVAL_HOURS=1        # Every hour
```

### Aggressive Strategy
```env
DYNAMIC_PAIR_SELECTION=true
MIN_VOLUME_USD=500000        # $500K+ (moderate liquidity)
MAX_COINS_SCAN=50            # Top 50
SCAN_INTERVAL_HOURS=1        # Every hour
```

---

## API Rate Limits ⚠️

### Binance Limits

- **Weight Limit**: 1200 per minute
- **Order Limit**: 10 per second

### Dynamic Selection Usage

| Action | Weight | Frequency |
|--------|--------|-----------|
| Get exchange info | 10 | Once per scan |
| Get 24h ticker | 40 | Once per scan |
| Get klines (per symbol) | 1 | Once per symbol |

**Estimated Total**: ~150-200 weight per scan

### Stay Under Limits

✅ Keep `SCAN_INTERVAL_HOURS >= 1`  
✅ Keep `MAX_COINS_SCAN <= 50`  
✅ Add delays between API calls (built-in)  
✅ Cache results (automatic)  

---

## Migration Guide 🚀

### Switching from Fixed to Dynamic

1. **Backup current config**:
```bash
cp .env .env.backup
```

2. **Add dynamic settings**:
```env
DYNAMIC_PAIR_SELECTION=true
MIN_VOLUME_USD=1000000
MAX_COINS_SCAN=30
SCAN_INTERVAL_HOURS=1
```

3. **Restart bot**:
```bash
docker compose restart coinbourg
```

4. **Monitor logs**:
```bash
docker compose logs -f coinbourg | grep "CoinSelector"
```

5. **Verify it's working**:
Look for: `"Dynamic scan returned 30 coins"`

### Reverting to Fixed Pairs

```env
DYNAMIC_PAIR_SELECTION=false
```

Bot will use `TRADING_PAIRS` list immediately.

---

## FAQ ❓

**Q: How many coins does Binance have?**  
A: ~400-500 USDT pairs, but ~150-200 meet volume criteria.

**Q: Can I use both dynamic and fixed pairs?**  
A: No, it's either/or. Use `DYNAMIC_PAIR_SELECTION=true` or `false`.

**Q: Does this work on Binance testnet?**  
A: Yes, but testnet has fewer pairs (~50 vs 400).

**Q: Will this increase my trading costs?**  
A: No, trading fees are the same. You just get more opportunities.

**Q: Can I exclude certain coins?**  
A: Not yet, but coming in Phase 2. For now, use `MIN_VOLUME_USD` to filter.

**Q: How do I see which coins are selected?**  
A: Check logs or add endpoint to API (coming soon).

---

## Summary ✨

**Before** (Fixed):
- 5 hardcoded coins
- Manual updates needed
- Limited opportunities

**After** (Dynamic):
- Top 30 coins automatically
- Adapts to market hourly
- 6x more opportunities
- AI analyzes all continuously

Enable it now:
```env
DYNAMIC_PAIR_SELECTION=true
```

Push to GitHub and deploy! 🚀
