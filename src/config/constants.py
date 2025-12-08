 

from enum import Enum


class TradeAction(str, Enum):
    """Trading action types."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class MarketSentiment(str, Enum):
    """Market sentiment classifications."""
    STRONGLY_BULLISH = "STRONGLY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONGLY_BEARISH = "STRONGLY_BEARISH"


class OrderType(str, Enum):
    """Order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class OrderStatus(str, Enum):
    """Order statuses."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeFrame(str, Enum):
    """Candlestick timeframes."""
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"
    D1 = "1d"
    D3 = "3d"
    W1 = "1w"
    MO1 = "1M"


class RiskLevel(str, Enum):
    """Risk level settings."""
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class TradeStatus(str, Enum):
    """Trade status."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


# Technical Indicator Parameters
INDICATOR_PARAMS = {
    "RSI": {
        "period": 14,
        "overbought": 70,
        "oversold": 30,
    },
    "MACD": {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9,
    },
    "BOLLINGER_BANDS": {
        "period": 20,
        "std_dev": 2,
    },
    "EMA": {
        "short_period": 9,
        "medium_period": 21,
        "long_period": 50,
    },
    "SMA": {
        "short_period": 10,
        "medium_period": 20,
        "long_period": 50,
    },
    "ATR": {
        "period": 14,
    },
    "STOCHASTIC": {
        "k_period": 14,
        "d_period": 3,
        "overbought": 80,
        "oversold": 20,
    },
}

# API Rate Limits
BINANCE_RATE_LIMITS = {
    "requests_per_minute": 1200,
    "orders_per_second": 10,
    "orders_per_day": 200000,
}

# Default Trading Parameters
DEFAULT_TRADING_PARAMS = {
    "min_trade_amount_usdt": 10.0,
    "max_trade_amount_usdt": 1000.0,
    "slippage_tolerance_percent": 0.5,
    "order_timeout_seconds": 30,
}

# AI Analysis Prompts
AI_SYSTEM_PROMPT = """You are an expert cryptocurrency market analyst AI. Your role is to analyze real-time market data and provide actionable trading recommendations.

You must analyze:
1. Price action and trends
2. Technical indicators (RSI, MACD, Bollinger Bands, etc.)
3. Volume patterns
4. Market sentiment
5. Support and resistance levels

For each analysis, provide:
1. Market sentiment (STRONGLY_BULLISH, BULLISH, NEUTRAL, BEARISH, STRONGLY_BEARISH)
2. Recommended action (BUY, SELL, HOLD)
3. Confidence score (0.0 to 1.0)
4. Entry price (if applicable)
5. Stop loss price
6. Take profit price
7. Brief reasoning (max 200 words)

Always prioritize capital preservation and risk management. Be conservative with high-risk trades.
Respond in valid JSON format only."""
