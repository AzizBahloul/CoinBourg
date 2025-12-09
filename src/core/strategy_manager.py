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


class StrategyManager:
    """
    Manages multiple strategies and aggregates their signals.
    
    Features:
    - Run multiple strategies in parallel
    - Weighted voting mechanism
    - Dynamic weight adjustment based on performance
    - Consensus aggregation
    """
    
    def __init__(self):
        """Initialize strategy manager with all strategies."""
        self.strategies: List[BaseStrategy] = [
            MomentumStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
            ScalpingStrategy(),
        ]
        
        logger.info(f"StrategyManager initialized with {len(self.strategies)} strategies")
    
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
