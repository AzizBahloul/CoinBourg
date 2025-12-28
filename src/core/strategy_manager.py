"""
Multi-Strategy Engine
====================
Pluggable trading strategies with weighted voting and consensus mechanism.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Strategy classification."""
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    SCALPING = "scalping"
    MOONSHOT = "moonshot"
    AI_PREDICTION = "ai_prediction"
    VWAP = "vwap"
    GRID_TRADING = "grid_trading"
    ARBITRAGE = "arbitrage"
    ORDER_FLOW = "order_flow"
    WHALE_TRACKING = "whale_tracking"
    MULTI_TIMEFRAME = "multi_timeframe"
    ICT_SMC = "ict_smc"  # Inner Circle Trader / Smart Money Concepts
    FIBONACCI = "fibonacci"


@dataclass
class StrategySignal:
    """Signal from a trading strategy."""
    strategy_name: str
    strategy_type: StrategyType
    action: str  # BUY, SELL, HOLD
    confidence: float  # 0-1
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_percent: float = 5.0
    reasoning: str = ""
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class BaseStrategy(ABC):
    """Base class for all trading strategies."""
    
    def __init__(self, name: str, strategy_type: StrategyType):
        self.name = name
        self.strategy_type = strategy_type
        self.enabled = True
        self.weight = 1.0  # Can be adjusted based on performance
        
        # Performance tracking
        self.signals_generated = 0
        self.successful_signals = 0
        self.total_profit = 0.0
        
    @abstractmethod
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """
        Analyze market and generate signal.
        
        Args:
            symbol: Trading pair
            price_data: OHLCV data
            indicators: Technical indicators
            market_context: Additional market context
            
        Returns:
            StrategySignal
        """
        pass
    
    def update_performance(self, profit: float):
        """Update strategy performance metrics."""
        self.total_profit += profit
        if profit > 0:
            self.successful_signals += 1
    
    def get_win_rate(self) -> float:
        """Calculate win rate."""
        if self.signals_generated == 0:
            return 0.0
        return self.successful_signals / self.signals_generated


class MomentumStrategy(BaseStrategy):
    """Momentum-based strategy following strong trends."""
    
    def __init__(self):
        super().__init__("Momentum", StrategyType.MOMENTUM)
        self.momentum_threshold = 3.0  # % change threshold
        self.volume_multiplier = 1.5  # Volume must be 1.5x average
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze momentum and generate signal."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        volumes = price_data.get('volume', [])
        
        if len(closes) < 24:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data"
            )
        
        # Calculate momentum
        momentum_24h = ((closes[-1] / closes[-24]) - 1) * 100
        momentum_7h = ((closes[-1] / closes[-7]) - 1) * 100 if len(closes) >= 7 else 0
        
        # Check volume
        recent_volume = np.mean(volumes[-6:])
        avg_volume = np.mean(volumes[:-6]) if len(volumes) > 6 else recent_volume
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
        
        # RSI check (if available)
        rsi = indicators.get('rsi', 50)
        
        # Generate signal
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # Strong upward momentum with volume
        if (momentum_7h > self.momentum_threshold and 
            volume_ratio > self.volume_multiplier and 
            rsi < 70):
            action = "BUY"
            confidence = min(0.9, 0.5 + (momentum_7h / 10) + (volume_ratio - 1) * 0.2)
            reasoning = f"Strong upward momentum {momentum_7h:.2f}% with {volume_ratio:.1f}x volume"
        
        # Strong downward momentum
        elif (momentum_7h < -self.momentum_threshold and 
              volume_ratio > self.volume_multiplier and 
              rsi > 30):
            action = "SELL"
            confidence = min(0.9, 0.5 + (abs(momentum_7h) / 10) + (volume_ratio - 1) * 0.2)
            reasoning = f"Strong downward momentum {momentum_7h:.2f}% with {volume_ratio:.1f}x volume"
        
        else:
            reasoning = "No strong momentum detected"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=closes[-1] if action != "HOLD" else None,
            stop_loss=closes[-1] * 0.97 if action == "BUY" else closes[-1] * 1.03,
            take_profit=closes[-1] * 1.05 if action == "BUY" else closes[-1] * 0.95,
            position_size_percent=min(8.0, 3.0 + confidence * 5),
            reasoning=reasoning
        )


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy for oversold/overbought conditions."""
    
    def __init__(self):
        super().__init__("MeanReversion", StrategyType.MEAN_REVERSION)
        self.bb_std = 2.0  # Bollinger Bands standard deviation
        self.rsi_oversold = 30
        self.rsi_overbought = 70
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze mean reversion opportunities."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        
        if len(closes) < 20:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data"
            )
        
        current_price = closes[-1]
        
        # Calculate Bollinger Bands
        sma_20 = np.mean(closes[-20:])
        std_20 = np.std(closes[-20:])
        bb_upper = sma_20 + (self.bb_std * std_20)
        bb_lower = sma_20 - (self.bb_std * std_20)
        
        # Get RSI
        rsi = indicators.get('rsi', 50)
        
        # Calculate distance from bands
        distance_from_lower = ((current_price - bb_lower) / bb_lower) * 100
        distance_from_upper = ((bb_upper - current_price) / bb_upper) * 100
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # Oversold - potential bounce
        if current_price < bb_lower and rsi < self.rsi_oversold:
            action = "BUY"
            confidence = min(0.85, 0.5 + (self.rsi_oversold - rsi) / 50)
            reasoning = f"Oversold: Price below BB lower, RSI={rsi:.0f}"
        
        # Overbought - potential reversal
        elif current_price > bb_upper and rsi > self.rsi_overbought:
            action = "SELL"
            confidence = min(0.85, 0.5 + (rsi - self.rsi_overbought) / 50)
            reasoning = f"Overbought: Price above BB upper, RSI={rsi:.0f}"
        
        # Near lower band but not oversold
        elif distance_from_lower < 2 and rsi < 40:
            action = "BUY"
            confidence = 0.6
            reasoning = f"Approaching oversold: Near BB lower, RSI={rsi:.0f}"
        
        else:
            reasoning = "No mean reversion opportunity"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=current_price if action != "HOLD" else None,
            stop_loss=bb_lower * 0.98 if action == "BUY" else bb_upper * 1.02,
            take_profit=sma_20 if action == "BUY" else sma_20,
            position_size_percent=min(7.0, 3.0 + confidence * 4),
            reasoning=reasoning
        )


class BreakoutStrategy(BaseStrategy):
    """Breakout strategy for range breakouts and new highs/lows."""
    
    def __init__(self):
        super().__init__("Breakout", StrategyType.BREAKOUT)
        self.lookback_period = 20
        self.volume_threshold = 1.8
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze breakout opportunities."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        highs = price_data.get('high', [])
        lows = price_data.get('low', [])
        volumes = price_data.get('volume', [])
        
        if len(closes) < self.lookback_period:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data"
            )
        
        current_price = closes[-1]
        
        # Calculate range
        period_high = np.max(highs[-(self.lookback_period+1):-1])
        period_low = np.min(lows[-(self.lookback_period+1):-1])
        
        # Volume analysis
        recent_volume = volumes[-1]
        avg_volume = np.mean(volumes[-(self.lookback_period+1):-1])
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # Upward breakout
        if (current_price > period_high and 
            volume_ratio > self.volume_threshold):
            action = "BUY"
            breakout_strength = ((current_price - period_high) / period_high) * 100
            confidence = min(0.9, 0.6 + breakout_strength * 2 + (volume_ratio - 1.5) * 0.2)
            reasoning = f"Upward breakout above {period_high:.2f} with {volume_ratio:.1f}x volume"
        
        # Downward breakdown
        elif (current_price < period_low and 
              volume_ratio > self.volume_threshold):
            action = "SELL"
            breakdown_strength = ((period_low - current_price) / period_low) * 100
            confidence = min(0.9, 0.6 + breakdown_strength * 2 + (volume_ratio - 1.5) * 0.2)
            reasoning = f"Downward breakdown below {period_low:.2f} with {volume_ratio:.1f}x volume"
        
        # Approaching breakout
        elif current_price > period_high * 0.98 and volume_ratio > 1.3:
            action = "BUY"
            confidence = 0.5
            reasoning = f"Approaching breakout level {period_high:.2f}"
        
        else:
            reasoning = "No breakout detected"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=current_price if action != "HOLD" else None,
            stop_loss=period_high * 0.985 if action == "BUY" else period_low * 1.015,
            take_profit=current_price * 1.08 if action == "BUY" else current_price * 0.92,
            position_size_percent=min(10.0, 4.0 + confidence * 6),
            reasoning=reasoning
        )


class ScalpingStrategy(BaseStrategy):
    """Short-term scalping strategy for quick profits."""
    
    def __init__(self):
        super().__init__("Scalping", StrategyType.SCALPING)
        self.profit_target = 0.5  # 0.5% profit target
        self.stop_loss = 0.3  # 0.3% stop loss
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze scalping opportunities (requires 1m-5m data)."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        
        if len(closes) < 10:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data"
            )
        
        current_price = closes[-1]
        
        # Very short-term momentum
        momentum_5 = ((closes[-1] / closes[-5]) - 1) * 100 if len(closes) >= 5 else 0
        
        # Get MACD if available
        macd = indicators.get('macd', {})
        macd_value = macd.get('macd', 0)
        signal_value = macd.get('signal', 0)
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # Quick upward move with MACD crossover
        if momentum_5 > 0.2 and macd_value > signal_value:
            action = "BUY"
            confidence = min(0.75, 0.5 + abs(momentum_5) * 5)
            reasoning = f"Short-term upward momentum {momentum_5:.2f}%, MACD bullish"
        
        # Quick downward move
        elif momentum_5 < -0.2 and macd_value < signal_value:
            action = "SELL"
            confidence = min(0.75, 0.5 + abs(momentum_5) * 5)
            reasoning = f"Short-term downward momentum {momentum_5:.2f}%, MACD bearish"
        
        else:
            reasoning = "No scalping opportunity"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=current_price if action != "HOLD" else None,
            stop_loss=current_price * (1 - self.stop_loss/100) if action == "BUY" else current_price * (1 + self.stop_loss/100),
            take_profit=current_price * (1 + self.profit_target/100) if action == "BUY" else current_price * (1 - self.profit_target/100),
            position_size_percent=3.0,  # Small positions for scalping
            reasoning=reasoning
        )


# ============================================================================
# ADVANCED PROFESSIONAL TRADING STRATEGIES
# ============================================================================

class VWAPStrategy(BaseStrategy):
    """
    Volume Weighted Average Price Strategy.
    Institutional traders use VWAP to get the best average price.
    Buy below VWAP, sell above VWAP.
    """
    
    def __init__(self):
        super().__init__("VWAP", StrategyType.VWAP)
        self.deviation_threshold = 1.5  # % deviation from VWAP
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze VWAP-based opportunities."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        highs = price_data.get('high', [])
        lows = price_data.get('low', [])
        volumes = price_data.get('volume', [])
        
        if len(closes) < 24:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data for VWAP"
            )
        
        # Calculate VWAP
        typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs[-24:], lows[-24:], closes[-24:])]
        vols = volumes[-24:]
        
        cumulative_tp_vol = sum(tp * v for tp, v in zip(typical_prices, vols))
        cumulative_vol = sum(vols)
        vwap = cumulative_tp_vol / cumulative_vol if cumulative_vol > 0 else closes[-1]
        
        current_price = closes[-1]
        deviation = ((current_price - vwap) / vwap) * 100
        
        # Standard deviation bands
        squared_deviations = [(tp - vwap) ** 2 * v for tp, v in zip(typical_prices, vols)]
        variance = sum(squared_deviations) / cumulative_vol if cumulative_vol > 0 else 0
        std_dev = np.sqrt(variance)
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # Price significantly below VWAP - potential buy
        if deviation < -self.deviation_threshold:
            action = "BUY"
            confidence = min(0.85, 0.5 + abs(deviation) / 5)
            reasoning = f"Price {abs(deviation):.1f}% below VWAP (${vwap:.4f}) - institutional discount"
        
        # Price significantly above VWAP - potential sell  
        elif deviation > self.deviation_threshold:
            action = "SELL"
            confidence = min(0.85, 0.5 + abs(deviation) / 5)
            reasoning = f"Price {deviation:.1f}% above VWAP (${vwap:.4f}) - overextended"
        
        else:
            reasoning = f"Price near VWAP (${vwap:.4f}), deviation: {deviation:.2f}%"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=current_price if action != "HOLD" else None,
            stop_loss=vwap if action == "BUY" else current_price * 1.02,
            take_profit=vwap if action == "SELL" else vwap * 1.01,
            position_size_percent=min(7.0, 4.0 + confidence * 3),
            reasoning=reasoning
        )


class OrderFlowStrategy(BaseStrategy):
    """
    Order Flow / Volume Profile Strategy.
    Analyzes buying vs selling pressure using volume delta.
    """
    
    def __init__(self):
        super().__init__("OrderFlow", StrategyType.ORDER_FLOW)
        self.imbalance_threshold = 0.6  # 60% imbalance needed
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze order flow patterns."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        opens = price_data.get('open', closes)
        volumes = price_data.get('volume', [])
        
        if len(closes) < 20:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data for order flow"
            )
        
        # Calculate volume delta (buying vs selling pressure)
        buy_volume = 0
        sell_volume = 0
        
        for i in range(-10, 0):
            if closes[i] > opens[i]:
                buy_volume += volumes[i]
            else:
                sell_volume += volumes[i]
        
        total_volume = buy_volume + sell_volume
        buy_ratio = buy_volume / total_volume if total_volume > 0 else 0.5
        sell_ratio = sell_volume / total_volume if total_volume > 0 else 0.5
        
        # Volume spike detection
        recent_vol = np.mean(volumes[-5:])
        avg_vol = np.mean(volumes[-20:-5]) if len(volumes) > 20 else recent_vol
        vol_spike = recent_vol / avg_vol if avg_vol > 0 else 1
        
        # Delta momentum
        delta_5 = sum([1 if c > o else -1 for c, o in zip(closes[-5:], opens[-5:])])
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # Strong buying pressure with volume spike
        if buy_ratio > self.imbalance_threshold and vol_spike > 1.5:
            action = "BUY"
            confidence = min(0.9, 0.5 + (buy_ratio - 0.5) + (vol_spike - 1) * 0.2)
            reasoning = f"Strong buy pressure: {buy_ratio*100:.0f}% buyers, {vol_spike:.1f}x volume"
        
        # Strong selling pressure with volume spike
        elif sell_ratio > self.imbalance_threshold and vol_spike > 1.5:
            action = "SELL"
            confidence = min(0.9, 0.5 + (sell_ratio - 0.5) + (vol_spike - 1) * 0.2)
            reasoning = f"Strong sell pressure: {sell_ratio*100:.0f}% sellers, {vol_spike:.1f}x volume"
        
        # Momentum shift
        elif delta_5 >= 4 and buy_ratio > 0.55:
            action = "BUY"
            confidence = 0.65
            reasoning = f"Momentum shift bullish: {delta_5}/5 green candles"
        
        elif delta_5 <= -4 and sell_ratio > 0.55:
            action = "SELL"
            confidence = 0.65
            reasoning = f"Momentum shift bearish: {abs(delta_5)}/5 red candles"
        
        else:
            reasoning = f"Order flow neutral: Buy {buy_ratio*100:.0f}% / Sell {sell_ratio*100:.0f}%"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=closes[-1] if action != "HOLD" else None,
            stop_loss=closes[-1] * 0.97 if action == "BUY" else closes[-1] * 1.03,
            take_profit=closes[-1] * 1.05 if action == "BUY" else closes[-1] * 0.95,
            position_size_percent=min(8.0, 4.0 + confidence * 4),
            reasoning=reasoning
        )


class WhaleTrackingStrategy(BaseStrategy):
    """
    Whale Tracking Strategy.
    Follows large order movements and accumulation patterns.
    """
    
    def __init__(self):
        super().__init__("WhaleTracking", StrategyType.WHALE_TRACKING)
        self.whale_threshold = 2.0  # Volume must be 2x average for whale detection
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Detect whale accumulation/distribution patterns."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        opens = price_data.get('open', closes)
        volumes = price_data.get('volume', [])
        highs = price_data.get('high', closes)
        lows = price_data.get('low', closes)
        
        if len(closes) < 30:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data for whale tracking"
            )
        
        # Identify whale candles (high volume with price impact)
        avg_vol = np.mean(volumes[-30:-5])
        whale_candles = []
        
        for i in range(-10, 0):
            vol_ratio = volumes[i] / avg_vol if avg_vol > 0 else 1
            if vol_ratio > self.whale_threshold:
                whale_candles.append({
                    'index': i,
                    'vol_ratio': vol_ratio,
                    'bullish': closes[i] > opens[i],
                    'body_size': abs(closes[i] - opens[i]) / opens[i] * 100,
                    'wick_ratio': (highs[i] - lows[i]) / abs(closes[i] - opens[i] + 0.0001)
                })
        
        # Analyze whale activity
        bullish_whales = sum(1 for w in whale_candles if w['bullish'])
        bearish_whales = len(whale_candles) - bullish_whales
        
        # Accumulation pattern: price stable/down but whale buys
        recent_change = ((closes[-1] / closes[-10]) - 1) * 100
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        if len(whale_candles) >= 2:
            if bullish_whales > bearish_whales and recent_change < 3:
                action = "BUY"
                confidence = min(0.85, 0.5 + bullish_whales * 0.1 + len(whale_candles) * 0.05)
                reasoning = f"Whale accumulation: {bullish_whales} bullish whale candles detected"
            
            elif bearish_whales > bullish_whales and recent_change > -3:
                action = "SELL"
                confidence = min(0.85, 0.5 + bearish_whales * 0.1 + len(whale_candles) * 0.05)
                reasoning = f"Whale distribution: {bearish_whales} bearish whale candles detected"
        
        elif len(whale_candles) == 1:
            w = whale_candles[0]
            if w['bullish'] and w['vol_ratio'] > 3:
                action = "BUY"
                confidence = 0.65
                reasoning = f"Single whale buy: {w['vol_ratio']:.1f}x volume spike"
            elif not w['bullish'] and w['vol_ratio'] > 3:
                action = "SELL"
                confidence = 0.65
                reasoning = f"Single whale sell: {w['vol_ratio']:.1f}x volume spike"
        
        if action == "HOLD":
            reasoning = f"No significant whale activity ({len(whale_candles)} whale candles)"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=closes[-1] if action != "HOLD" else None,
            stop_loss=closes[-1] * 0.96 if action == "BUY" else closes[-1] * 1.04,
            take_profit=closes[-1] * 1.08 if action == "BUY" else closes[-1] * 0.92,
            position_size_percent=min(10.0, 5.0 + confidence * 5),
            reasoning=reasoning
        )


class MultiTimeframeStrategy(BaseStrategy):
    """
    Multi-Timeframe Analysis Strategy.
    Aligns signals across multiple timeframes for higher probability trades.
    """
    
    def __init__(self):
        super().__init__("MultiTimeframe", StrategyType.MULTI_TIMEFRAME)
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze multiple timeframes for confluence."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        
        if len(closes) < 96:  # Need at least 96 data points for multi-TF
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data for multi-timeframe"
            )
        
        # Simulate different timeframes from the data
        # Short-term (recent 4 candles)
        st_trend = "UP" if closes[-1] > closes[-4] else "DOWN"
        st_strength = abs((closes[-1] / closes[-4]) - 1) * 100
        
        # Medium-term (recent 24 candles)
        mt_trend = "UP" if closes[-1] > closes[-24] else "DOWN"
        mt_strength = abs((closes[-1] / closes[-24]) - 1) * 100
        
        # Long-term (recent 96 candles)
        lt_trend = "UP" if closes[-1] > closes[-96] else "DOWN"
        lt_strength = abs((closes[-1] / closes[-96]) - 1) * 100
        
        # Calculate SMAs for trend confirmation
        sma_8 = np.mean(closes[-8:])
        sma_21 = np.mean(closes[-21:])
        sma_55 = np.mean(closes[-55:]) if len(closes) >= 55 else np.mean(closes)
        
        sma_alignment = 0
        if sma_8 > sma_21 > sma_55:
            sma_alignment = 1  # Bullish alignment
        elif sma_8 < sma_21 < sma_55:
            sma_alignment = -1  # Bearish alignment
        
        # Count trend alignment
        bullish_count = sum([st_trend == "UP", mt_trend == "UP", lt_trend == "UP"])
        bearish_count = 3 - bullish_count
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # All timeframes aligned bullish
        if bullish_count == 3 and sma_alignment == 1:
            action = "BUY"
            confidence = min(0.9, 0.65 + (st_strength + mt_strength) / 30)
            reasoning = f"Triple TF bullish alignment: ST {st_strength:.1f}%, MT {mt_strength:.1f}%, LT {lt_strength:.1f}%"
        
        # All timeframes aligned bearish
        elif bearish_count == 3 and sma_alignment == -1:
            action = "SELL"
            confidence = min(0.9, 0.65 + (st_strength + mt_strength) / 30)
            reasoning = f"Triple TF bearish alignment: ST {st_strength:.1f}%, MT {mt_strength:.1f}%, LT {lt_strength:.1f}%"
        
        # Strong confluence (2/3 aligned with SMA confirmation)
        elif bullish_count >= 2 and sma_alignment == 1:
            action = "BUY"
            confidence = 0.6
            reasoning = f"Double TF bullish: {bullish_count}/3 timeframes aligned up"
        
        elif bearish_count >= 2 and sma_alignment == -1:
            action = "SELL"
            confidence = 0.6
            reasoning = f"Double TF bearish: {bearish_count}/3 timeframes aligned down"
        
        else:
            reasoning = f"Mixed timeframe signals: {bullish_count}/3 bullish, SMA alignment: {sma_alignment}"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=closes[-1] if action != "HOLD" else None,
            stop_loss=closes[-1] * 0.96 if action == "BUY" else closes[-1] * 1.04,
            take_profit=closes[-1] * 1.08 if action == "BUY" else closes[-1] * 0.92,
            position_size_percent=min(8.0, 4.0 + confidence * 4),
            reasoning=reasoning
        )


class ICTSmartMoneyStrategy(BaseStrategy):
    """
    ICT / Smart Money Concepts Strategy.
    Based on Inner Circle Trader methodology - order blocks, fair value gaps, liquidity sweeps.
    """
    
    def __init__(self):
        super().__init__("ICT_SMC", StrategyType.ICT_SMC)
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze smart money concepts."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        opens = price_data.get('open', closes)
        highs = price_data.get('high', closes)
        lows = price_data.get('low', closes)
        
        if len(closes) < 50:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data for ICT analysis"
            )
        
        current_price = closes[-1]
        
        # 1. Find Order Blocks (last down/up candle before strong move)
        bullish_ob = None
        bearish_ob = None
        
        for i in range(-20, -3):
            # Bullish Order Block: Last red candle before strong up move
            if closes[i] < opens[i]:  # Red candle
                if closes[i+1] > opens[i+1] and closes[i+2] > opens[i+2]:  # Followed by 2 green
                    if ((closes[i+2] / closes[i]) - 1) > 0.02:  # 2%+ move up
                        bullish_ob = {'low': lows[i], 'high': highs[i], 'index': i}
            
            # Bearish Order Block: Last green candle before strong down move
            if closes[i] > opens[i]:  # Green candle
                if closes[i+1] < opens[i+1] and closes[i+2] < opens[i+2]:  # Followed by 2 red
                    if ((closes[i] / closes[i+2]) - 1) > 0.02:  # 2%+ move down
                        bearish_ob = {'low': lows[i], 'high': highs[i], 'index': i}
        
        # 2. Find Fair Value Gaps (FVG) - gaps between candle 1 high and candle 3 low
        bullish_fvg = None
        bearish_fvg = None
        
        for i in range(-15, -2):
            # Bullish FVG: Gap up (candle 1 high < candle 3 low)
            if lows[i+2] > highs[i]:
                bullish_fvg = {'bottom': highs[i], 'top': lows[i+2]}
            
            # Bearish FVG: Gap down (candle 1 low > candle 3 high)
            if highs[i+2] < lows[i]:
                bearish_fvg = {'top': lows[i], 'bottom': highs[i+2]}
        
        # 3. Liquidity sweep detection (wick beyond recent high/low then reversal)
        recent_high = max(highs[-15:-1])
        recent_low = min(lows[-15:-1])
        
        liquidity_sweep_high = highs[-1] > recent_high and closes[-1] < opens[-1]
        liquidity_sweep_low = lows[-1] < recent_low and closes[-1] > opens[-1]
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        # Price returning to bullish order block
        if bullish_ob and bullish_ob['low'] <= current_price <= bullish_ob['high']:
            action = "BUY"
            confidence = 0.75
            reasoning = f"Price at bullish order block (${bullish_ob['low']:.4f}-${bullish_ob['high']:.4f})"
        
        # Price returning to bearish order block
        elif bearish_ob and bearish_ob['low'] <= current_price <= bearish_ob['high']:
            action = "SELL"
            confidence = 0.75
            reasoning = f"Price at bearish order block (${bearish_ob['low']:.4f}-${bearish_ob['high']:.4f})"
        
        # Liquidity sweep then reversal (high probability)
        elif liquidity_sweep_low:
            action = "BUY"
            confidence = 0.8
            reasoning = f"Liquidity sweep below ${recent_low:.4f} with bullish rejection"
        
        elif liquidity_sweep_high:
            action = "SELL"
            confidence = 0.8
            reasoning = f"Liquidity sweep above ${recent_high:.4f} with bearish rejection"
        
        # Fair Value Gap fill
        elif bullish_fvg and bullish_fvg['bottom'] <= current_price <= bullish_fvg['top']:
            action = "BUY"
            confidence = 0.65
            reasoning = f"Price in bullish FVG zone"
        
        elif bearish_fvg and bearish_fvg['bottom'] <= current_price <= bearish_fvg['top']:
            action = "SELL"
            confidence = 0.65
            reasoning = f"Price in bearish FVG zone"
        
        else:
            reasoning = "No smart money setup detected"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=current_price if action != "HOLD" else None,
            stop_loss=current_price * 0.97 if action == "BUY" else current_price * 1.03,
            take_profit=current_price * 1.06 if action == "BUY" else current_price * 0.94,
            position_size_percent=min(8.0, 4.0 + confidence * 4),
            reasoning=reasoning
        )


class FibonacciStrategy(BaseStrategy):
    """
    Fibonacci Retracement/Extension Strategy.
    Uses golden ratio levels for entries and targets.
    """
    
    def __init__(self):
        super().__init__("Fibonacci", StrategyType.FIBONACCI)
        self.fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]  # Key retracement levels
        self.fib_tolerance = 0.01  # 1% tolerance around levels
    
    async def analyze(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> StrategySignal:
        """Analyze Fibonacci retracement levels."""
        self.signals_generated += 1
        
        closes = price_data.get('close', [])
        highs = price_data.get('high', closes)
        lows = price_data.get('low', closes)
        
        if len(closes) < 50:
            return StrategySignal(
                strategy_name=self.name,
                strategy_type=self.strategy_type,
                action="HOLD",
                confidence=0.0,
                reasoning="Insufficient data for Fibonacci"
            )
        
        # Find swing high and swing low in last 50 candles
        swing_high = max(highs[-50:])
        swing_low = min(lows[-50:])
        swing_high_idx = list(highs[-50:]).index(swing_high)
        swing_low_idx = list(lows[-50:]).index(swing_low)
        
        current_price = closes[-1]
        price_range = swing_high - swing_low
        
        # Determine trend (uptrend if low came before high)
        is_uptrend = swing_low_idx < swing_high_idx
        
        # Calculate Fib levels
        if is_uptrend:
            # In uptrend, retrace from high to low
            fib_prices = {level: swing_high - (price_range * level) for level in self.fib_levels}
        else:
            # In downtrend, retrace from low to high
            fib_prices = {level: swing_low + (price_range * level) for level in self.fib_levels}
        
        # Check if price is at a Fib level
        at_fib_level = None
        for level, price in fib_prices.items():
            if abs(current_price - price) / price < self.fib_tolerance:
                at_fib_level = level
                break
        
        # RSI for confirmation
        rsi = indicators.get('rsi', 50)
        
        action = "HOLD"
        confidence = 0.0
        reasoning = ""
        
        if at_fib_level:
            # Golden ratio levels (0.618, 0.382) are strongest
            level_strength = 0.8 if at_fib_level in [0.618, 0.382] else 0.6
            
            if is_uptrend and rsi < 45:
                # Uptrend + retracement to Fib + oversold = BUY
                action = "BUY"
                confidence = min(0.85, level_strength + 0.1 * (45 - rsi) / 15)
                reasoning = f"Uptrend at {at_fib_level*100:.1f}% Fib (${fib_prices[at_fib_level]:.4f}), RSI={rsi:.0f}"
            
            elif not is_uptrend and rsi > 55:
                # Downtrend + retracement to Fib + overbought = SELL
                action = "SELL"
                confidence = min(0.85, level_strength + 0.1 * (rsi - 55) / 15)
                reasoning = f"Downtrend at {at_fib_level*100:.1f}% Fib (${fib_prices[at_fib_level]:.4f}), RSI={rsi:.0f}"
        
        # Check for Fib extension targets being hit
        if action == "HOLD":
            ext_161 = swing_high + (price_range * 0.618) if is_uptrend else swing_low - (price_range * 0.618)
            if is_uptrend and current_price > ext_161 * 0.99:
                action = "SELL"
                confidence = 0.7
                reasoning = f"Price hit 161.8% Fib extension (${ext_161:.4f}) - potential reversal"
            elif not is_uptrend and current_price < ext_161 * 1.01:
                action = "BUY"
                confidence = 0.7
                reasoning = f"Price hit 161.8% Fib extension (${ext_161:.4f}) - potential reversal"
        
        if action == "HOLD":
            reasoning = f"No Fib setup. Trend: {'UP' if is_uptrend else 'DOWN'}, Range: ${swing_low:.4f}-${swing_high:.4f}"
        
        return StrategySignal(
            strategy_name=self.name,
            strategy_type=self.strategy_type,
            action=action,
            confidence=confidence,
            entry_price=current_price if action != "HOLD" else None,
            stop_loss=swing_low * 0.98 if action == "BUY" else swing_high * 1.02,
            take_profit=swing_high if action == "BUY" else swing_low,
            position_size_percent=min(7.0, 4.0 + confidence * 3),
            reasoning=reasoning
        )


class StrategyManager:
    """
    Manages multiple strategies and aggregates their signals.
    
    Features:
    - Run multiple strategies in parallel
    - Weighted voting mechanism
    - Dynamic weight adjustment based on performance
    - Consensus aggregation
    - 10 Professional Trading Strategies
    """
    
    def __init__(self):
        """Initialize strategy manager with all strategies."""
        self.strategies: List[BaseStrategy] = [
            # Basic Strategies
            MomentumStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
            ScalpingStrategy(),
            # Advanced Professional Strategies
            VWAPStrategy(),
            OrderFlowStrategy(),
            WhaleTrackingStrategy(),
            MultiTimeframeStrategy(),
            ICTSmartMoneyStrategy(),
            FibonacciStrategy(),
        ]
        
        logger.info(f"StrategyManager initialized with {len(self.strategies)} strategies (including 6 PRO strategies)")
    
    async def analyze_all(
        self,
        symbol: str,
        price_data: Dict,
        indicators: Dict,
        market_context: Optional[Dict] = None
    ) -> List[StrategySignal]:
        """
        Run all enabled strategies in parallel.
        
        Args:
            symbol: Trading pair
            price_data: OHLCV data
            indicators: Technical indicators
            market_context: Additional market context
            
        Returns:
            List of signals from all strategies
        """
        tasks = []
        for strategy in self.strategies:
            if strategy.enabled:
                tasks.append(
                    strategy.analyze(symbol, price_data, indicators, market_context)
                )
        
        signals = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_signals = []
        for signal in signals:
            if isinstance(signal, StrategySignal):
                valid_signals.append(signal)
            elif isinstance(signal, Exception):
                logger.error(f"Strategy error: {signal}")
        
        return valid_signals
    
    def weighted_vote(self, signals: List[StrategySignal]) -> Tuple[str, float, List[str]]:
        """
        Aggregate signals using weighted voting.
        
        Args:
            signals: List of strategy signals
            
        Returns:
            (action, confidence, reasoning_list)
        """
        if not signals:
            return "HOLD", 0.0, ["No signals available"]
        
        # Calculate weighted votes
        buy_score = 0.0
        sell_score = 0.0
        hold_score = 0.0
        reasoning = []
        
        for signal in signals:
            strategy = self._get_strategy(signal.strategy_name)
            weight = strategy.weight if strategy else 1.0
            weighted_confidence = signal.confidence * weight
            
            if signal.action == "BUY":
                buy_score += weighted_confidence
                reasoning.append(f"{signal.strategy_name}: BUY ({signal.confidence:.2f}) - {signal.reasoning}")
            elif signal.action == "SELL":
                sell_score += weighted_confidence
                reasoning.append(f"{signal.strategy_name}: SELL ({signal.confidence:.2f}) - {signal.reasoning}")
            else:
                hold_score += weighted_confidence
                reasoning.append(f"{signal.strategy_name}: HOLD - {signal.reasoning}")
        
        # Determine consensus
        total_score = buy_score + sell_score + hold_score
        if total_score == 0:
            return "HOLD", 0.0, reasoning
        
        # Normalize scores
        buy_normalized = buy_score / total_score
        sell_normalized = sell_score / total_score
        
        # Determine action (require significant majority)
        if buy_normalized > 0.6:
            return "BUY", buy_normalized, reasoning
        elif sell_normalized > 0.6:
            return "SELL", sell_normalized, reasoning
        else:
            return "HOLD", max(buy_normalized, sell_normalized), reasoning
    
    def _get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """Get strategy by name."""
        for strategy in self.strategies:
            if strategy.name == name:
                return strategy
        return None
    
    def adjust_weights(self):
        """Dynamically adjust strategy weights based on performance."""
        for strategy in self.strategies:
            win_rate = strategy.get_win_rate()
            
            # Increase weight for successful strategies
            if win_rate > 0.6 and strategy.signals_generated >= 10:
                strategy.weight = min(2.0, 1.0 + (win_rate - 0.5))
            # Decrease weight for unsuccessful strategies
            elif win_rate < 0.4 and strategy.signals_generated >= 10:
                strategy.weight = max(0.5, 1.0 - (0.5 - win_rate))
            
            logger.info(f"Strategy {strategy.name}: Win rate={win_rate:.2f}, Weight={strategy.weight:.2f}")
    
    def get_performance_summary(self) -> Dict:
        """Get performance summary for all strategies."""
        summary = {}
        for strategy in self.strategies:
            summary[strategy.name] = {
                "type": strategy.strategy_type.value,
                "enabled": strategy.enabled,
                "weight": strategy.weight,
                "signals_generated": strategy.signals_generated,
                "successful_signals": strategy.successful_signals,
                "win_rate": strategy.get_win_rate(),
                "total_profit": strategy.total_profit
            }
        return summary
    
    def calculate_dynamic_leverage(self, confidence: float, base_leverage: float = 1.0, max_leverage: float = 3.0) -> float:
        """
        Calculate dynamic leverage based on signal confidence.
        
        Args:
            confidence: Signal confidence (0-1)
            base_leverage: Base leverage
            max_leverage: Maximum allowed leverage
            
        Returns:
            Leverage multiplier
        """
        # Map confidence to leverage (0.5 -> 1x, 1.0 -> max_leverage)
        if confidence < 0.5:
            return base_leverage
        
        leverage = base_leverage + (confidence - 0.5) * 2 * (max_leverage - base_leverage)
        return min(leverage, max_leverage)
