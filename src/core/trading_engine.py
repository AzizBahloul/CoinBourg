"""
Trading Engine
==============
Core trading engine that orchestrates all trading operations.
Coordinates between market data, AI analysis, and order execution.
"""

import asyncio
import logging
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import json

from src.config.settings import get_settings, RISK_PRESETS
from src.config.constants import (
    TradeAction, MarketSentiment, OrderType, OrderStatus,
    TimeFrame, TradeStatus, INDICATOR_PARAMS, OrderSide
)
from src.core.binance_client import BinanceClient
from src.core.deepseek_client import DeepSeekClient
from src.core.state_manager import StateManager
from src.core.coin_selector import CoinSelector
from src.core.market_scanner import MarketScanner
from src.core.strategy_manager import StrategyManager
from src.core.risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Represents a trade executed by the bot."""
    id: str
    symbol: str
    side: str
    entry_price: float
    quantity: float
    status: TradeStatus = TradeStatus.OPEN
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    entry_time: datetime = field(default_factory=datetime.utcnow)
    exit_time: Optional[datetime] = None
    ai_confidence: float = 0.0
    ai_reasoning: str = ""


@dataclass
class Position:
    """Represents an open position with enhanced tracking."""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    side: str = OrderSide.BUY
    unrealized_pnl: float = 0.0
    unrealized_pnl_percent: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    # Enhanced tracking
    trailing_stop_enabled: bool = False
    trailing_stop_distance: float = 0.0  # As percentage
    highest_price: float = 0.0  # Track highest price for trailing stop
    lowest_price: float = float('inf')  # Track lowest price for short positions
    partial_exits: List[Dict] = field(default_factory=list)
    entry_time: datetime = field(default_factory=datetime.utcnow)

    @property
    def position_value(self) -> float:
        """Current notional value of the position."""
        return self.quantity * self.current_price if self.current_price is not None else 0.0
    
    def update_trailing_stop(self, side: str) -> Optional[float]:
        """Update trailing stop based on price movement."""
        if not self.trailing_stop_enabled or self.trailing_stop_distance <= 0:
            return self.stop_loss
        
        if side == "BUY":
            # Long position - trail below highest price
            if self.current_price > self.highest_price:
                self.highest_price = self.current_price
                new_stop = self.highest_price * (1 - self.trailing_stop_distance / 100)
                if self.stop_loss is None or new_stop > self.stop_loss:
                    self.stop_loss = new_stop
                    return new_stop
        else:
            # Short position - trail above lowest price
            if self.current_price < self.lowest_price:
                self.lowest_price = self.current_price
                new_stop = self.lowest_price * (1 + self.trailing_stop_distance / 100)
                if self.stop_loss is None or new_stop < self.stop_loss:
                    self.stop_loss = new_stop
                    return new_stop
        
        return None


class TradingEngine:
    """
    Main trading engine that coordinates all bot operations.
    
    Features:
    - Real-time market monitoring
    - AI-powered analysis integration
    - Risk management
    - Order execution
    - Position management
    - Performance tracking
    """
    
    def __init__(self):
        """Initialize the trading engine."""
        self.settings = get_settings()
        
        # Initialize clients
        self.binance = BinanceClient()
        self.deepseek = DeepSeekClient()
        self.state_manager = StateManager()  # State persistence

        # Initialize real trading components (pass dependencies)
        self.coin_selector = CoinSelector(self.binance)
        self.market_scanner = MarketScanner(self.binance, self.coin_selector)
        self.strategy_manager = StrategyManager()
        self.risk_manager = RiskManager()
        self.paper_trading = self.settings.PAPER_TRADING
        
        # Trading state
        # Internal state
        self.is_running = False
        self.binance_available = False  # Track if Binance is available
        self.deepseek_available = False  # Track if AI is available
        self.positions: Dict[str, Position] = {}
        self.open_orders: Dict[str, Dict] = {}
        self.trades: List[Trade] = []
        self.daily_trades_count = 0
        self.last_trade_date = datetime.utcnow().date()
        
        # Performance metrics
        self.metrics = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "peak_value": 0.0,
            "current_value": 0.0,
        }
        
        
        self._load_risk_preset()
        
        # Analysis cache
        self._analysis_cache: Dict[str, Dict] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        
        # AI Thought History (for UI)
        self.ai_thoughts: List[Dict] = []
        
        logger.info("TradingEngine initialized")
    
    def _load_risk_preset(self):
        """Load risk management settings from preset."""
        preset = RISK_PRESETS.get(self.settings.RISK_LEVEL, RISK_PRESETS["MODERATE"])
        
        self.max_position_size_percent = preset["max_position_size_percent"]
        self.stop_loss_percent = preset["stop_loss_percent"]
        self.take_profit_percent = preset["take_profit_percent"]
        self.max_daily_trades = preset["max_daily_trades"]
        self.max_drawdown_percent = preset["max_drawdown_percent"]
        self.min_confidence_score = preset["min_confidence_score"]
        
        logger.info(f"Loaded risk preset: {self.settings.RISK_LEVEL}")
    
    async def initialize(self):
        """Initialize connections and verify setup."""
        logger.info("Initializing trading engine...")
        
        # Restore previous state from database (positions, trades, etc.)
        try:
            await self.state_manager.restore_state(self)
            logger.info("✓ Previous state restored from database")
        except Exception as e:
            logger.warning(f"Could not restore previous state: {e}")
        
        # Test Binance connection
        if not await self.binance.test_connectivity():
            logger.warning("⚠ Binance connection failed - using demo mode")
            self.binance_available = False
        else:
            logger.info("✓ Binance connection established")
            self.binance_available = True
        
        # Test DeepSeek connection (optional - bot can work without AI)
        try:
            logger.info("Testing DeepSeek AI connection...")
            if await self.deepseek.test_connection():
                logger.info("✓ DeepSeek connection established - AI analysis enabled")
                self.deepseek_available = True
            else:
                logger.warning("⚠ DeepSeek connection test returned False - AI features disabled")
                logger.warning("  Check your DEEPSEEK_API_KEY in .env file")
                self.deepseek_available = False
        except Exception as e:
            logger.error(f"⚠ DeepSeek initialization failed: {type(e).__name__}: {e}")
            logger.error("  Verify DEEPSEEK_API_KEY is valid and network allows connections to api.deepseek.com")
            logger.warning("  Running with basic technical analysis only (no AI)")
            self.deepseek_available = False
        
        # Determine initial capital based on mode
        initial_capital = getattr(self.settings, 'PAPER_TRADING_INITIAL_CAPITAL', 100.0)
        
        # Set portfolio value based on trading mode
        if self.paper_trading:
            # Paper trading mode - always use paper trading capital
            self.metrics["current_value"] = initial_capital
            self.metrics["peak_value"] = initial_capital
            logger.info(f"✓ PAPER TRADING MODE: ${initial_capital:,.2f} portfolio")
        elif self.binance_available:
            # Live trading with Binance - get real balance
            try:
                await self.binance.get_exchange_info()
                logger.info("✓ Exchange info loaded")
                
                self.metrics["current_value"] = await self.binance.get_portfolio_value()
                self.metrics["peak_value"] = max(self.metrics["peak_value"], self.metrics["current_value"])
                logger.info(f"✓ Live portfolio value: ${self.metrics['current_value']:,.2f}")
            except Exception as e:
                logger.warning(f"⚠ Failed to load account info: {e}")
                self.binance_available = False
                # Fall back to paper trading
                self.metrics["current_value"] = initial_capital
                self.metrics["peak_value"] = initial_capital
                logger.info(f"✓ Fallback to paper trading: ${initial_capital:,.2f}")
        else:
            # Demo mode (no Binance connection)
            self.metrics["current_value"] = initial_capital
            self.metrics["peak_value"] = initial_capital
            logger.info(f"✓ DEMO MODE: ${initial_capital:,.2f} portfolio")
        
        # Check for incomplete trades (only if Binance available and not paper trading)
        if self.binance_available and not self.paper_trading:
            try:
                await self.state_manager.recover_incomplete_trades(self)
            except Exception as e:
                logger.warning(f"Error recovering incomplete trades: {e}")
        
        logger.info(f"Trading engine initialized - Portfolio: ${self.metrics['current_value']:,.2f}")
    
    async def shutdown(self):
        """Gracefully shutdown the trading engine."""
        logger.info("Shutting down trading engine...")
        self.is_running = False
        
        # Save current state to database
        try:
            await self.state_manager.save_state(self)
            logger.info("✓ Engine state saved to database")
        except Exception as e:
            logger.error(f"Error saving engine state: {e}")
        
        await self.binance.close()
        await self.deepseek.close()
        
        # Close database connection
        self.state_manager.close()
        
        logger.info("Trading engine shutdown complete")
    
    # ===========================================
    # Market Data Methods
    # ===========================================
    
    async def get_market_data(self, symbol: str) -> Dict:
        """
        Get comprehensive market data for a symbol.
        
        Returns:
            Dictionary containing price, indicators, and analysis data
        """
        try:
            ticker = await self.binance.get_ticker_24h(symbol)
            klines_1h = await self.binance.get_klines(symbol, "1h", limit=100)
            klines_4h = await self.binance.get_klines(symbol, "4h", limit=50)
            klines_1d = await self.binance.get_klines(symbol, "1d", limit=30)

            indicators = self._calculate_indicators(klines_1h, klines_4h, klines_1d)
            orderbook = await self.binance.get_orderbook(symbol, limit=20)
            orderbook_summary = self._analyze_orderbook(orderbook)

            return {
                "symbol": symbol,
                "current_price": float(ticker['lastPrice']),
                "price_change_24h": float(ticker['priceChangePercent']),
                "volume_24h": float(ticker['quoteVolume']),
                "high_24h": float(ticker['highPrice']),
                "low_24h": float(ticker['lowPrice']),
                "technical_indicators": indicators,
                "indicators": indicators,
                "orderbook_summary": orderbook_summary,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as exc:
            logger.warning(f"Falling back to demo market data for {symbol}: {exc}")
            self.binance_available = False
            return self._generate_demo_market_data(symbol)

    def _generate_demo_market_data(self, symbol: str) -> Dict:
        """Return synthetic market data when Binance is unavailable."""
        # Deterministic-ish baseline per symbol to keep tests stable
        seed = sum(ord(c) for c in symbol)
        random.seed(seed)
        base_price = 100 + (seed % 3000)  # simple spread across symbols
        # Simulate a gentle intraday move using sine so values look realistic
        wave = math.sin(datetime.utcnow().timestamp() / 3600) * 0.01
        current_price = round(base_price * (1 + wave), 2)
        price_change = round(wave * 100, 2)
        volume = float(1_000_000 + (seed % 500_000))

        indicators = {
            "RSI_14": 50 + (wave * 100),
            "SMA_20": round(current_price * 0.99, 2),
            "SMA_50": round(current_price * 0.97, 2),
            "EMA_9": round(current_price * 0.995, 2),
            "EMA_21": round(current_price * 0.992, 2),
            "MACD": {"macd": wave * 10, "signal": wave * 8, "histogram": wave * 2},
            "Bollinger_Bands": {
                "upper": round(current_price * 1.02, 2),
                "middle": round(current_price, 2),
                "lower": round(current_price * 0.98, 2)
            },
            "ATR_14": round(current_price * 0.01, 4),
            "Stochastic": {"k": 50 + (wave * 100), "d": 50},
            "Volume_SMA_20": volume * 0.95,
            "Volume_Ratio": 1.05
        }

        orderbook_summary = {
            "spread": round(current_price * 0.0005, 4),
            "buy_pressure": 0.55,
            "sell_pressure": 0.45,
            "bid_volume": volume * 0.55,
            "ask_volume": volume * 0.45,
            "imbalance": "BUY"
        }

        return {
            "symbol": symbol,
            "current_price": current_price,
            "price_change_24h": price_change,
            "volume_24h": volume,
            "high_24h": round(current_price * 1.02, 2),
            "low_24h": round(current_price * 0.98, 2),
            "technical_indicators": indicators,
            "indicators": indicators,
            "orderbook_summary": orderbook_summary,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _calculate_indicators(
        self,
        klines_1h: List,
        klines_4h: List,
        klines_1d: List
    ) -> Dict:
        """Calculate technical indicators from kline data."""
        
        # Extract closing prices
        closes_1h = [float(k[4]) for k in klines_1h]
        closes_4h = [float(k[4]) for k in klines_4h]
        closes_1d = [float(k[4]) for k in klines_1d]
        
        # Extract high, low, volume
        highs_1h = [float(k[2]) for k in klines_1h]
        lows_1h = [float(k[3]) for k in klines_1h]
        volumes_1h = [float(k[5]) for k in klines_1h]
        
        indicators = {}
        
        # RSI (14 period)
        indicators['RSI_14'] = self._calculate_rsi(closes_1h, 14)
        
        # Moving Averages
        indicators['SMA_20'] = self._calculate_sma(closes_1h, 20)
        indicators['SMA_50'] = self._calculate_sma(closes_1h, 50)
        indicators['EMA_9'] = self._calculate_ema(closes_1h, 9)
        indicators['EMA_21'] = self._calculate_ema(closes_1h, 21)
        
        # MACD
        indicators['MACD'] = self._calculate_macd(closes_1h)
        
        # Bollinger Bands
        indicators['Bollinger_Bands'] = self._calculate_bollinger_bands(closes_1h, 20)
        
        # ATR
        indicators['ATR_14'] = self._calculate_atr(highs_1h, lows_1h, closes_1h, 14)
        
        # Stochastic
        indicators['Stochastic'] = self._calculate_stochastic(highs_1h, lows_1h, closes_1h)
        
        # Volume Analysis
        indicators['Volume_SMA_20'] = self._calculate_sma(volumes_1h, 20)
        indicators['Volume_Ratio'] = volumes_1h[-1] / indicators['Volume_SMA_20'] if indicators['Volume_SMA_20'] > 0 else 1.0
        
        # Trend Analysis
        indicators['Trend'] = self._determine_trend(closes_1d)
        
        return indicators
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def _calculate_sma(self, prices: List[float], period: int) -> float:
        """Calculate Simple Moving Average."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        return round(sum(prices[-period:]) / period, 6)
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema
        
        return round(ema, 6)
    
    def _calculate_macd(self, prices: List[float]) -> Dict:
        """Calculate MACD indicator."""
        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)
        
        macd_line = ema_12 - ema_26
        
        # For signal line, we'd need to calculate EMA of MACD values
        # Simplified version
        signal_line = macd_line * 0.9  # Approximation
        histogram = macd_line - signal_line
        
        return {
            "macd_line": round(macd_line, 6),
            "signal_line": round(signal_line, 6),
            "histogram": round(histogram, 6),
            "crossover": "BULLISH" if macd_line > signal_line else "BEARISH"
        }
    
    def _calculate_bollinger_bands(self, prices: List[float], period: int = 20) -> Dict:
        """Calculate Bollinger Bands."""
        if len(prices) < period:
            return {"upper": 0, "middle": 0, "lower": 0, "width": 0}
        
        sma = self._calculate_sma(prices, period)
        
        # Calculate standard deviation
        variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
        std_dev = variance ** 0.5
        
        upper = sma + (std_dev * 2)
        lower = sma - (std_dev * 2)
        
        current_price = prices[-1]
        position = (current_price - lower) / (upper - lower) if upper != lower else 0.5
        
        return {
            "upper": round(upper, 6),
            "middle": round(sma, 6),
            "lower": round(lower, 6),
            "width": round((upper - lower) / sma * 100, 2),
            "position": round(position, 2)  # 0 = at lower, 1 = at upper
        }
    
    def _calculate_atr(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> float:
        """Calculate Average True Range."""
        if len(highs) < period + 1:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)
        
        return round(sum(true_ranges[-period:]) / period, 6)
    
    def _calculate_stochastic(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        k_period: int = 14
    ) -> Dict:
        """Calculate Stochastic oscillator."""
        if len(highs) < k_period:
            return {"k": 50, "d": 50, "signal": "NEUTRAL"}
        
        highest_high = max(highs[-k_period:])
        lowest_low = min(lows[-k_period:])
        current_close = closes[-1]
        
        if highest_high == lowest_low:
            k = 50
        else:
            k = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100
        
        # Simplified D calculation
        d = k * 0.9 + 5
        
        signal = "OVERBOUGHT" if k > 80 else "OVERSOLD" if k < 20 else "NEUTRAL"
        
        return {
            "k": round(k, 2),
            "d": round(d, 2),
            "signal": signal
        }
    
    def _determine_trend(self, prices: List[float]) -> str:
        """Determine overall market trend."""
        if len(prices) < 10:
            return "UNKNOWN"
        
        sma_10 = self._calculate_sma(prices, 10)
        sma_20 = self._calculate_sma(prices[-20:], 20) if len(prices) >= 20 else sma_10
        
        current = prices[-1]
        
        if current > sma_10 > sma_20:
            return "STRONG_UPTREND"
        elif current > sma_10:
            return "UPTREND"
        elif current < sma_10 < sma_20:
            return "STRONG_DOWNTREND"
        elif current < sma_10:
            return "DOWNTREND"
        else:
            return "SIDEWAYS"
    
    def _analyze_orderbook(self, orderbook: Dict) -> Dict:
        """Analyze order book for buy/sell pressure."""
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return {}
        
        # Calculate total bid and ask volume
        bid_volume = sum(float(b[1]) for b in bids[:10])
        ask_volume = sum(float(a[1]) for a in asks[:10])
        
        # Calculate spread
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread = ((best_ask - best_bid) / best_bid) * 100
        
        # Buy/sell pressure ratio
        total_volume = bid_volume + ask_volume
        buy_pressure = bid_volume / total_volume if total_volume > 0 else 0.5
        
        return {
            "spread": round(spread, 4),
            "buy_pressure": round(buy_pressure, 2),
            "sell_pressure": round(1 - buy_pressure, 2),
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "imbalance": "BUY" if buy_pressure > 0.55 else "SELL" if buy_pressure < 0.45 else "NEUTRAL"
        }
    
    # ===========================================
    # Trading Logic Methods
    # ===========================================
    
    async def analyze_and_decide(self, symbol: str) -> Optional[Dict]:
        """
        Analyze a symbol and make a trading decision.
        
        Returns:
            Trading decision with action, confidence, and targets
        """
        # Check cache
        if symbol in self._analysis_cache:
            cache_time = self._cache_expiry.get(symbol)
            if cache_time and datetime.utcnow() < cache_time:
                return self._analysis_cache[symbol]
        
        # Get market data
        market_data = await self.get_market_data(symbol)
        
        # Get AI analysis if available, otherwise use basic analysis
        if self.deepseek_available:
            try:
                # Remove fields not accepted by analyze_market (timestamp and duplicate 'indicators')
                ai_data = {k: v for k, v in market_data.items() if k not in ['timestamp', 'indicators']}
                analysis = await self.deepseek.analyze_market(**ai_data)
            except Exception as e:
                logger.warning(f"AI analysis failed for {symbol}: {e}, using basic analysis")
                analysis = self._basic_technical_analysis(market_data)
        else:
            analysis = self._basic_technical_analysis(market_data)
        
        # Apply risk management filters
        decision = self._apply_risk_filters(analysis, symbol, market_data['current_price'])
        
        # Cache the result
        self._analysis_cache[symbol] = decision
        self._cache_expiry[symbol] = datetime.utcnow() + timedelta(minutes=5)
        
        # Record thought for UI
        self._record_ai_thought(symbol, decision, market_data)
        
        return decision
    
    def _record_ai_thought(self, symbol: str, decision: Dict, market_data: Dict):
        """Record AI analysis for the UI feed and database."""
        thought = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "action": decision.get("action", "HOLD"),
            "confidence": decision.get("confidence", 0.0),
            "reasoning": decision.get("reasoning", "No reasoning provided"),
            "price": market_data.get("current_price", 0.0),
            "sentiment": decision.get("sentiment", "NEUTRAL"),
            "filtered_reason": decision.get("filtered_reason", None)
        }
        
        # Keep last 50 thoughts in memory
        self.ai_thoughts.insert(0, thought)
        if len(self.ai_thoughts) > 50:
            self.ai_thoughts.pop()
        
        # Persist to database for history
        try:
            asyncio.create_task(self._save_thought_to_db(thought))
        except Exception as e:
            logger.debug(f"Could not save thought to database: {e}")
    
    async def _save_thought_to_db(self, thought: Dict):
        """Save AI thought to database for historical tracking."""
        try:
            conn = self.state_manager._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_thoughts 
                (timestamp, symbol, action, confidence, reasoning, price, sentiment, filtered_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                thought['timestamp'],
                thought['symbol'],
                thought['action'],
                thought['confidence'],
                thought['reasoning'],
                thought['price'],
                thought['sentiment'],
                thought.get('filtered_reason')
            ))
            conn.commit()
            cursor.close()
        except Exception as e:
            logger.debug(f"Database save failed (non-critical): {e}")
    
    def _basic_technical_analysis(self, market_data: Dict) -> Dict:
        """Basic technical analysis fallback when AI is unavailable."""
        indicators = (
            market_data.get('technical_indicators')
            or market_data.get('indicators')
            or {}
        )
        current_price = market_data.get('current_price', 0)
        
        # Simple RSI-based strategy
        rsi = indicators.get('RSI_14', indicators.get('rsi', 50))
        sma_20 = indicators.get('SMA_20', indicators.get('sma_20', current_price))
        
        action = "HOLD"
        confidence = 0.3  # Low confidence for basic analysis
        reasoning = "Basic technical analysis (AI unavailable): "
        
        if rsi < 30 and current_price < sma_20:
            action = "BUY"
            confidence = 0.4
            reasoning += f"Oversold (RSI: {rsi:.1f}) and below SMA20"
        elif rsi > 70 and current_price > sma_20:
            action = "SELL"
            confidence = 0.4
            reasoning += f"Overbought (RSI: {rsi:.1f}) and above SMA20"
        else:
            reasoning += f"Neutral signals (RSI: {rsi:.1f})"
        
        return {
            "action": action,
            "confidence": confidence,
            "reasoning": reasoning,
            "sentiment": "NEUTRAL",
            "stop_loss_percent": self.stop_loss_percent,
            "take_profit_percent": self.take_profit_percent,
            "entry_targets": [],
            "key_levels": []
        }
    
    def _apply_risk_filters(
        self,
        analysis: Dict,
        symbol: str,
        current_price: float
    ) -> Dict:
        """Apply risk management filters to trading decision."""
        
        decision = analysis.copy()
        
        # Check confidence threshold
        if decision['confidence'] < self.min_confidence_score:
            decision['action'] = 'HOLD'
            decision['filtered_reason'] = f"Confidence {decision['confidence']:.2f} below threshold {self.min_confidence_score}"
        
        # Check daily trade limit
        if self._should_reset_daily_count():
            self.daily_trades_count = 0
            self.last_trade_date = datetime.utcnow().date()
        
        if self.daily_trades_count >= self.max_daily_trades:
            decision['action'] = 'HOLD'
            decision['filtered_reason'] = f"Daily trade limit ({self.max_daily_trades}) reached"
        
        # Check drawdown limit
        if self._check_drawdown_exceeded():
            decision['action'] = 'HOLD'
            decision['filtered_reason'] = f"Max drawdown ({self.max_drawdown_percent}%) exceeded"
        
        # Check if already have position in this symbol
        if symbol in self.positions and decision['action'] == 'BUY':
            decision['action'] = 'HOLD'
            decision['filtered_reason'] = "Already have open position"
        
        # Adjust stop loss and take profit based on risk settings
        if decision['action'] in ['BUY', 'SELL']:
            decision['stop_loss'] = current_price * (1 - self.stop_loss_percent / 100)
            decision['take_profit'] = current_price * (1 + self.take_profit_percent / 100)
            decision['current_price'] = current_price  # Include for paper trading
        
        return decision
    
    def _should_reset_daily_count(self) -> bool:
        """Check if daily trade count should be reset."""
        return datetime.utcnow().date() > self.last_trade_date
    
    def _check_drawdown_exceeded(self) -> bool:
        """Check if max drawdown has been exceeded."""
        if self.metrics['peak_value'] == 0:
            return False
        
        current_drawdown = (
            (self.metrics['peak_value'] - self.metrics['current_value']) /
            self.metrics['peak_value'] * 100
        )
        
        return current_drawdown >= self.max_drawdown_percent
    
    async def execute_trade(
        self,
        symbol: str,
        action: str,
        analysis: Dict
    ) -> Optional[Trade]:
        """
        Execute a trade based on the analysis.
        
        Args:
            symbol: Trading pair symbol
            action: BUY or SELL
            analysis: AI analysis with targets
            
        Returns:
            Trade object if successful, None otherwise
        """
        # Paper trading simulation - execute virtual trades
        if not self.binance_available or self.paper_trading:
            return await self._execute_paper_trade(symbol, action, analysis)
        
        try:
            # Calculate position size
            portfolio_value = await self.binance.get_portfolio_value()
            position_value = portfolio_value * (self.max_position_size_percent / 100)
            
            current_price = await self.binance.get_ticker_price(symbol)
            quantity = position_value / current_price
            
            # Get symbol info for precision
            symbol_info = await self.binance.get_symbol_info(symbol)
            
            logger.info(f"Executing {action} order: {symbol} - Qty: {quantity:.6f} @ ${current_price:.2f}")
            
            # Execute order
            if action == 'BUY':
                order = await self.binance.market_buy(symbol, quantity=quantity)
            else:
                # For sell, we need to have the position
                if symbol not in self.positions:
                    logger.warning(f"No position to sell for {symbol}")
                    return None
                quantity = self.positions[symbol].quantity
                order = await self.binance.market_sell(symbol, quantity=quantity)
            
            # Create trade record
            trade = Trade(
                id=str(order['orderId']),
                symbol=symbol,
                side=action,
                entry_price=float(order.get('fills', [{}])[0].get('price', current_price)),
                quantity=float(order.get('executedQty', quantity)),
                stop_loss=analysis.get('stop_loss'),
                take_profit=analysis.get('take_profit'),
                ai_confidence=analysis.get('confidence', 0),
                ai_reasoning=analysis.get('reasoning', '')
            )
            
            # Update state
            self.trades.append(trade)
            self.daily_trades_count += 1
            self.metrics['total_trades'] += 1
            
            if action == 'BUY':
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=trade.quantity,
                    entry_price=trade.entry_price,
                    current_price=current_price,
                    stop_loss=trade.stop_loss,
                    take_profit=trade.take_profit
                )
            elif action == 'SELL' and symbol in self.positions:
                # Close position
                position = self.positions.pop(symbol)
                trade.exit_price = current_price
                trade.status = TradeStatus.CLOSED
                trade.exit_time = datetime.utcnow()
                trade.pnl = (trade.exit_price - position.entry_price) * trade.quantity
                trade.pnl_percent = ((trade.exit_price - position.entry_price) / position.entry_price) * 100
                
                # Update metrics
                self.metrics['total_pnl'] += trade.pnl
                if trade.pnl > 0:
                    self.metrics['winning_trades'] += 1
                else:
                    self.metrics['losing_trades'] += 1
            
            logger.info(f"Trade executed: {trade.id} - {action} {symbol}")
            return trade
            
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return None
    
    async def _execute_paper_trade(
        self,
        symbol: str,
        action: str,
        analysis: Dict
    ) -> Optional[Trade]:
        """
        Execute a simulated paper trade.
        
        Args:
            symbol: Trading pair symbol
            action: BUY or SELL
            analysis: AI analysis with targets
            
        Returns:
            Trade object if successful, None otherwise
        """
        try:
            # Get current price from any available source
            current_price = analysis.get('current_price', 0)
            if current_price <= 0:
                # Try to get price from cached market data
                cached = self._analysis_cache.get(symbol, {})
                current_price = cached.get('price', 0)
            
            if current_price <= 0:
                logger.warning(f"Cannot execute paper trade for {symbol}: no price available")
                return None
            
            # Calculate position size based on portfolio
            portfolio_value = self.metrics.get("current_value", 100.0)
            position_value = portfolio_value * (self.max_position_size_percent / 100)
            quantity = position_value / current_price
            
            # Generate unique trade ID (UUID format for database compatibility)
            import uuid
            trade_id = str(uuid.uuid4())
            
            # Calculate stop loss and take profit
            confidence = analysis.get('confidence', 0.65)
            stop_loss_pct = self.stop_loss_percent
            take_profit_pct = self.take_profit_percent
            
            if action == 'BUY':
                stop_loss = current_price * (1 - stop_loss_pct / 100)
                take_profit = current_price * (1 + take_profit_pct / 100)
            else:
                stop_loss = current_price * (1 + stop_loss_pct / 100)
                take_profit = current_price * (1 - take_profit_pct / 100)
            
            logger.info(f"📝 PAPER TRADE: {action} {symbol}")
            logger.info(f"   Price: ${current_price:.2f} | Qty: {quantity:.6f} | Value: ${position_value:.2f}")
            logger.info(f"   SL: ${stop_loss:.2f} | TP: ${take_profit:.2f} | Confidence: {confidence:.0%}")
            
            if action == 'BUY':
                # Check if we already have a position
                if symbol in self.positions:
                    logger.info(f"   Already have position in {symbol}, skipping")
                    return None
                
                # Check if we have enough balance
                if position_value > portfolio_value * 0.95:  # Don't use more than 95% of portfolio
                    logger.info(f"   Insufficient paper balance for {symbol}")
                    return None
                
                # Create position
                position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=current_price,
                    current_price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                self.positions[symbol] = position
                
                # Deduct from paper balance
                self.metrics["current_value"] -= position_value
                
                # Create trade record
                trade = Trade(
                    id=trade_id,
                    symbol=symbol,
                    side='BUY',
                    entry_price=current_price,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    ai_confidence=confidence,
                    ai_reasoning=analysis.get('reasoning', 'Paper trade based on AI signal')
                )
                
            else:  # SELL
                # Check if we have a position to sell
                if symbol not in self.positions:
                    logger.info(f"   No position to sell for {symbol}")
                    return None
                
                position = self.positions.pop(symbol)
                pnl = (current_price - position.entry_price) * position.quantity
                pnl_percent = ((current_price - position.entry_price) / position.entry_price) * 100
                
                # Add back to paper balance (original + profit/loss)
                original_value = position.entry_price * position.quantity
                self.metrics["current_value"] += original_value + pnl
                self.metrics["total_pnl"] += pnl
                
                if pnl > 0:
                    self.metrics['winning_trades'] += 1
                    logger.info(f"   💰 PROFIT: +${pnl:.2f} ({pnl_percent:+.2f}%)")
                else:
                    self.metrics['losing_trades'] += 1
                    logger.info(f"   📉 LOSS: ${pnl:.2f} ({pnl_percent:+.2f}%)")
                
                # Create trade record
                trade = Trade(
                    id=trade_id,
                    symbol=symbol,
                    side='SELL',
                    entry_price=position.entry_price,
                    quantity=position.quantity,
                    exit_price=current_price,
                    pnl=pnl,
                    pnl_percent=pnl_percent,
                    ai_confidence=confidence,
                    ai_reasoning=analysis.get('reasoning', 'Paper trade closed'),
                    status=TradeStatus.CLOSED,
                    exit_time=datetime.utcnow()
                )
            
            # Update metrics
            self.trades.append(trade)
            self.daily_trades_count += 1
            self.metrics['total_trades'] += 1
            
            # Update peak value for drawdown calculation
            if self.metrics["current_value"] > self.metrics["peak_value"]:
                self.metrics["peak_value"] = self.metrics["current_value"]
            
            # Save state after trade
            try:
                await self.state_manager.save_state(self)
            except Exception as e:
                logger.warning(f"Failed to save state after paper trade: {e}")
            
            logger.info(f"   📊 Portfolio: ${self.metrics['current_value']:.2f} | Total PnL: ${self.metrics['total_pnl']:.2f}")
            return trade
            
        except Exception as e:
            logger.error(f"Paper trade execution failed: {e}", exc_info=True)
            return None

    async def check_stop_loss_take_profit(self):
        """Check and execute stop loss / take profit for open positions."""
        for symbol, position in list(self.positions.items()):
            try:
                # Get current price - try Binance first, then use cached price
                current_price = None
                if self.binance_available:
                    try:
                        current_price = await self.binance.get_ticker_price(symbol)
                    except:
                        pass
                
                # Fallback to cached price from analysis
                if not current_price:
                    cached = self._analysis_cache.get(symbol, {})
                    current_price = cached.get('price', position.current_price)
                
                if not current_price:
                    continue
                
                position.current_price = current_price
                position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
                position.unrealized_pnl_percent = (
                    (current_price - position.entry_price) / position.entry_price * 100
                )
                
                # Check stop loss
                if position.stop_loss and current_price <= position.stop_loss:
                    logger.info(f"🛑 Stop loss triggered for {symbol} @ ${current_price:.2f}")
                    await self.execute_trade(symbol, 'SELL', {
                        'stop_loss': position.stop_loss,
                        'current_price': current_price,
                        'reasoning': f'Stop loss triggered at ${current_price:.2f}'
                    })
                
                # Check take profit
                elif position.take_profit and current_price >= position.take_profit:
                    logger.info(f"🎯 Take profit triggered for {symbol} @ ${current_price:.2f}")
                    await self.execute_trade(symbol, 'SELL', {
                        'take_profit': position.take_profit,
                        'current_price': current_price,
                        'reasoning': f'Take profit triggered at ${current_price:.2f}'
                    })
                    
            except Exception as e:
                logger.error(f"Error checking SL/TP for {symbol}: {e}")
    
    # ===========================================
    # Main Trading Loop
    # ===========================================
    
    async def run(self):
        """Main trading loop."""
        # Don't reinitialize - lifespan already did that
        if not hasattr(self, 'settings'):
            await self.initialize()
        
        self.is_running = True
        logger.info("=" * 60)
        logger.info("Starting main trading loop...")
        logger.info(f"Analysis interval: {self.settings.ANALYSIS_INTERVAL_SECONDS}s")
        logger.info(f"Binance available: {self.binance_available}")
        logger.info(f"DeepSeek available: {self.deepseek_available}")
        logger.info(f"Demo mode: {'YES' if not self.binance_available else 'NO'}")
        logger.info("=" * 60)
        
        analysis_interval = self.settings.ANALYSIS_INTERVAL_SECONDS
        price_check_interval = self.settings.PRICE_CHECK_INTERVAL_SECONDS
        state_save_interval = 300  # Save state every 5 minutes
        
        last_analysis_time = datetime.min
        last_state_save_time = datetime.min
        
        while self.is_running:
            try:
                current_time = datetime.utcnow()
                
                # Periodic state save
                if (current_time - last_state_save_time).total_seconds() >= state_save_interval:
                    try:
                        await self.state_manager.save_state(self)
                        logger.debug("Periodic state save completed")
                        last_state_save_time = current_time
                    except Exception as e:
                        logger.warning(f"Periodic state save failed: {e}")
                
                # Update portfolio value (if Binance available)
                if self.binance_available:
                    try:
                        self.metrics['current_value'] = await self.binance.get_portfolio_value()
                        if self.metrics['current_value'] > self.metrics['peak_value']:
                            self.metrics['peak_value'] = self.metrics['current_value']
                    except Exception as e:
                        logger.warning(f"Failed to get portfolio value: {e}")
                
                # Check stop loss / take profit (if Binance available)
                if self.binance_available:
                    await self.check_stop_loss_take_profit()
                
                # Perform analysis if interval has passed
                if (current_time - last_analysis_time).total_seconds() >= analysis_interval:
                    logger.info(f"\n{'='*50}")
                    logger.info(f"Starting analysis cycle at {current_time.strftime('%H:%M:%S')}")
                    logger.info(f"{'='*50}")
                    
                    # Get symbols to analyze
                    if self.settings.DYNAMIC_PAIR_SELECTION and self.binance_available:
                        try:
                            coin_metrics = await self.coin_selector.scan_market()
                            # Extract symbol names from CoinMetrics objects
                            symbols_to_analyze = [coin.symbol for coin in coin_metrics]
                            logger.info(f"Dynamic scan returned {len(symbols_to_analyze)} coins: {', '.join(symbols_to_analyze[:10])}{'...' if len(symbols_to_analyze) > 10 else ''}")
                        except Exception as e:
                            logger.warning(f"Dynamic scan failed, using default pairs: {e}")
                            symbols_to_analyze = self.settings.TRADING_PAIRS
                    else:
                        # Use default pairs in demo mode or when dynamic selection is off
                        symbols_to_analyze = self.settings.TRADING_PAIRS
                        logger.info(f"Using default pairs: {symbols_to_analyze}")
                    
                    # Analyze all symbols (don't stop after 5)
                    analyzed_count = 0
                    for symbol in symbols_to_analyze:
                        try:
                            decision = await self.analyze_and_decide(symbol)
                            analyzed_count += 1
                            
                            if decision and decision['action'] in ['BUY', 'SELL']:
                                if 'filtered_reason' not in decision:
                                    await self.execute_trade(
                                        symbol,
                                        decision['action'],
                                        decision
                                    )
                                else:
                                    logger.info(f"{symbol}: {decision['action']} filtered - {decision['filtered_reason']}")
                            else:
                                logger.debug(f"{symbol}: HOLD (confidence: {decision.get('confidence', 0):.2f})")
                                
                        except Exception as e:
                            logger.error(f"Error analyzing {symbol}: {e}")
                        
                        # Small delay between symbols to avoid rate limits
                        await asyncio.sleep(1)
                    
                    logger.info(f"\n{'='*50}")
                    logger.info(f"Analysis cycle complete: {analyzed_count}/{len(symbols_to_analyze)} coins analyzed")
                    logger.info(f"Next analysis in {analysis_interval} seconds")
                    logger.info(f"{'='*50}\n")
                    last_analysis_time = current_time
                
                # Wait before next iteration
                await asyncio.sleep(price_check_interval)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received, shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                # Don't exit on errors - keep running
                await asyncio.sleep(10)
        
        logger.info("Trading loop stopped, shutting down...")
        await self.shutdown()
    
    def get_status(self) -> Dict:
        """Get current trading engine status."""
        return {
            "is_running": self.is_running,
            "portfolio_value": self.metrics['current_value'],
            "total_pnl": self.metrics['total_pnl'],
            "total_trades": self.metrics['total_trades'],
            "winning_trades": self.metrics['winning_trades'],
            "losing_trades": self.metrics['losing_trades'],
            "win_rate": (
                self.metrics['winning_trades'] / self.metrics['total_trades'] * 100
                if self.metrics['total_trades'] > 0 else 0
            ),
            "open_positions": len(self.positions),
            "positions": {
                symbol: {
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_percent": pos.unrealized_pnl_percent
                }
                for symbol, pos in self.positions.items()
            },
            "daily_trades": self.daily_trades_count,
            "max_daily_trades": self.max_daily_trades,
            "risk_level": self.settings.RISK_LEVEL,
            "analysis_interval": self.settings.ANALYSIS_INTERVAL_SECONDS,
            "paper_trading": self.paper_trading,
            "paper_trading_capital": getattr(self.settings, 'PAPER_TRADING_INITIAL_CAPITAL', 100.0)
        }

    async def _execute_trade(self, symbol: str, ai_decision: Dict) -> Position:
        """Minimal trade execution stub for integration tests."""
        quantity = ai_decision.get("quantity", 0.1)
        entry_price = ai_decision.get("entry_price", ai_decision.get("price", 0))
        position = Position(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            stop_loss=ai_decision.get("stop_loss"),
            take_profit=ai_decision.get("take_profit"),
            entry_time=datetime.utcnow(),
        )
        position.side = ai_decision.get("action", OrderSide.BUY)
        self.positions[symbol] = position
        return position

    def _should_exit_position(self, position: Position) -> bool:
        """Simple exit logic based on stop loss/take profit."""
        if position.stop_loss is not None and position.current_price <= position.stop_loss:
            return {"stop_loss": True}
        if position.take_profit is not None and position.current_price >= position.take_profit:
            return {"take_profit": True}
        return False
