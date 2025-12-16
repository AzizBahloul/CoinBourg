"""
CoinBourg Risk Manager
Comprehensive risk management for safe trading
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from scipy import stats

from src.config.settings import get_settings
from src.config.constants import RiskLevel, TradeAction as OrderSide

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open trading position"""
    symbol: str
    side: OrderSide
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    current_price: float = 0.0
    
    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L"""
        if self.side == OrderSide.BUY:
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity
    
    @property
    def unrealized_pnl_percent(self) -> float:
        """Calculate unrealized P&L as percentage"""
        if self.entry_price == 0:
            return 0.0
        if self.side == OrderSide.BUY:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100
    
    @property
    def position_value(self) -> float:
        """Current value of the position"""
        return self.current_price * self.quantity
    
    def should_stop_loss(self) -> bool:
        """Check if stop loss should trigger"""
        if self.side == OrderSide.BUY:
            return self.current_price <= self.stop_loss
        else:
            return self.current_price >= self.stop_loss
    
    def should_take_profit(self) -> bool:
        """Check if take profit should trigger"""
        if self.side == OrderSide.BUY:
            return self.current_price >= self.take_profit
        else:
            return self.current_price <= self.take_profit


@dataclass
class TradeRecord:
    """Record of a completed trade"""
    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_percent: float
    ai_confidence: float


@dataclass
class RiskState:
    """Current risk management state"""
    total_portfolio_value: float = 0.0
    available_balance: float = 0.0
    daily_pnl: float = 0.0
    daily_trades: int = 0
    peak_portfolio_value: float = 0.0
    current_drawdown: float = 0.0
    last_trade_time: Optional[datetime] = None
    consecutive_losses: int = 0
    daily_reset_time: datetime = field(default_factory=datetime.utcnow)
    
    # Drawdown circuit breakers
    hourly_pnl: float = 0.0
    hourly_reset_time: datetime = field(default_factory=datetime.utcnow)
    hourly_drawdown: float = 0.0
    daily_drawdown: float = 0.0
    trading_paused: bool = False
    pause_reason: Optional[str] = None
    pause_until: Optional[datetime] = None


class RiskManager:
    """
    Comprehensive risk management system
    
    Features:
    - Position sizing based on risk level
    - Stop-loss and take-profit calculation
    - Daily trade limits
    - Maximum drawdown protection
    - Consecutive loss protection
    - Position concentration limits
    """
    
    # Risk level configurations
    RISK_CONFIGS = {
        RiskLevel.CONSERVATIVE: {
            "max_position_size_percent": 2.0,
            "stop_loss_percent": 1.5,
            "take_profit_percent": 3.0,
            "max_daily_trades": 5,
            "max_drawdown_percent": 5.0,
            "max_consecutive_losses": 3,
            "max_portfolio_concentration": 0.1,  # 10% max in single asset
            "min_confidence_threshold": 0.7,
            "cooldown_after_loss_minutes": 30,
        },
        RiskLevel.MODERATE: {
            "max_position_size_percent": 5.0,
            "stop_loss_percent": 2.5,
            "take_profit_percent": 5.0,
            "max_daily_trades": 10,
            "max_drawdown_percent": 10.0,
            "max_consecutive_losses": 5,
            "max_portfolio_concentration": 0.2,  # 20% max in single asset
            "min_confidence_threshold": 0.6,
            "cooldown_after_loss_minutes": 15,
        },
        RiskLevel.AGGRESSIVE: {
            "max_position_size_percent": 10.0,
            "stop_loss_percent": 4.0,
            "take_profit_percent": 8.0,
            "max_daily_trades": 20,
            "max_drawdown_percent": 20.0,
            "max_consecutive_losses": 7,
            "max_portfolio_concentration": 0.3,  # 30% max in single asset
            "min_confidence_threshold": 0.5,
            "cooldown_after_loss_minutes": 5,
        },
    }
    
    def __init__(self, risk_level: RiskLevel = RiskLevel.CONSERVATIVE):
        """Initialize risk manager with specified risk level"""
        self.risk_level = risk_level
        self.config = self.RISK_CONFIGS[risk_level]
        self.state = RiskState()
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeRecord] = []
        
        logger.info(f"Risk Manager initialized with {risk_level.value} risk level")

    def validate_trade(self, signal: Dict, current_portfolio: Dict) -> Dict:
        """Lightweight validation stub for tests."""
        position_cap = current_portfolio.get("total_value", 0) * 0.1
        adjusted = dict(signal)
        adjusted["position_size_usd"] = min(signal.get("position_size_usd", position_cap), position_cap)
        return adjusted
    
    def set_risk_level(self, risk_level: RiskLevel) -> None:
        """Change the risk level"""
        self.risk_level = risk_level
        self.config = self.RISK_CONFIGS[risk_level]
        logger.info(f"Risk level changed to {risk_level.value}")
    
    def update_portfolio_state(
        self,
        total_value: float,
        available_balance: float
    ) -> None:
        """Update the current portfolio state"""
        self.state.total_portfolio_value = total_value
        self.state.available_balance = available_balance
        
        # Update peak value for drawdown calculation
        if total_value > self.state.peak_portfolio_value:
            self.state.peak_portfolio_value = total_value
        
        # Calculate current drawdown
        if self.state.peak_portfolio_value > 0:
            self.state.current_drawdown = (
                (self.state.peak_portfolio_value - total_value) 
                / self.state.peak_portfolio_value * 100
            )
        
        # Reset daily counters if new day
        self._check_daily_reset()
    
    def _check_daily_reset(self) -> None:
        """Reset daily counters at midnight UTC"""
        now = datetime.utcnow()
        if now.date() > self.state.daily_reset_time.date():
            logger.info("Daily reset triggered - resetting daily counters")
            self.state.daily_pnl = 0.0
            self.state.daily_trades = 0
            self.state.daily_drawdown = 0.0
            self.state.daily_reset_time = now
            
            # Resume trading if paused due to daily limits
            if self.state.trading_paused and "daily" in str(self.state.pause_reason).lower():
                self.resume_trading()
        
        # Check hourly reset
        if (now - self.state.hourly_reset_time).total_seconds() >= 3600:
            logger.debug("Hourly reset triggered")
            self.state.hourly_pnl = 0.0
            self.state.hourly_drawdown = 0.0
            self.state.hourly_reset_time = now
            
            # Resume trading if paused due to hourly limits
            if self.state.trading_paused and "hourly" in str(self.state.pause_reason).lower():
                self.resume_trading()
    
    def _check_drawdown_circuit_breakers(self) -> Tuple[bool, Optional[str]]:
        """
        Check if drawdown circuit breakers should trigger.
        
        Returns:
            Tuple of (should_pause, reason)
        """
        # Hourly drawdown limit: -10%
        hourly_limit = 10.0
        if self.state.hourly_drawdown <= -hourly_limit:
            return True, f"Hourly drawdown limit reached ({self.state.hourly_drawdown:.2f}%)"
        
        # Daily drawdown limit: -20%
        daily_limit = 20.0
        if self.state.daily_drawdown <= -daily_limit:
            return True, f"Daily drawdown limit reached ({self.state.daily_drawdown:.2f}%)"
        
        return False, None
    
    def pause_trading(self, reason: str, duration_hours: float = 1.0) -> None:
        """
        Pause all trading temporarily.
        
        Args:
            reason: Reason for pause
            duration_hours: Hours to pause (default: 1 hour)
        """
        self.state.trading_paused = True
        self.state.pause_reason = reason
        self.state.pause_until = datetime.utcnow() + timedelta(hours=duration_hours)
        
        logger.warning(f"TRADING PAUSED: {reason} (until {self.state.pause_until})")
    
    def resume_trading(self) -> None:
        """Resume trading after pause."""
        if self.state.trading_paused:
            self.state.trading_paused = False
            self.state.pause_reason = None
            self.state.pause_until = None
            logger.info("Trading resumed")
    
    def check_pause_expiry(self) -> None:
        """Check if pause period has expired."""
        if self.state.trading_paused and self.state.pause_until:
            if datetime.utcnow() >= self.state.pause_until:
                self.resume_trading()
    
    def can_open_trade(
        self,
        symbol: str,
        ai_confidence: float
    ) -> Tuple[bool, str]:
        """
        Check if a new trade can be opened
        
        Returns:
            Tuple of (can_trade, reason)
        """
        # Check if trading is paused
        self.check_pause_expiry()
        if self.state.trading_paused:
            return False, f"Trading paused: {self.state.pause_reason}"
        
        # Check drawdown circuit breakers
        should_pause, pause_reason = self._check_drawdown_circuit_breakers()
        if should_pause:
            self.pause_trading(pause_reason, duration_hours=1.0)
            return False, pause_reason
        
        # Check AI confidence threshold
        if ai_confidence < self.config["min_confidence_threshold"]:
            return False, f"AI confidence {ai_confidence:.2%} below minimum {self.config['min_confidence_threshold']:.2%}"
        
        # Check daily trade limit
        if self.state.daily_trades >= self.config["max_daily_trades"]:
            return False, f"Daily trade limit ({self.config['max_daily_trades']}) reached"
        
        # Check maximum drawdown
        if self.state.current_drawdown >= self.config["max_drawdown_percent"]:
            return False, f"Maximum drawdown ({self.config['max_drawdown_percent']}%) reached"
        
        # Check consecutive losses
        if self.state.consecutive_losses >= self.config["max_consecutive_losses"]:
            return False, f"Maximum consecutive losses ({self.config['max_consecutive_losses']}) reached"
        
        # Check cooldown after loss
        if self.state.last_trade_time and self.state.consecutive_losses > 0:
            cooldown_minutes = self.config["cooldown_after_loss_minutes"]
            cooldown_end = self.state.last_trade_time + timedelta(minutes=cooldown_minutes)
            if datetime.utcnow() < cooldown_end:
                remaining = (cooldown_end - datetime.utcnow()).seconds // 60
                return False, f"Cooldown period active ({remaining} minutes remaining)"
        
        # Check if position already exists
        if symbol in self.positions:
            return False, f"Position already exists for {symbol}"
        
        # Check portfolio concentration
        current_concentration = self._calculate_symbol_concentration(symbol)
        if current_concentration >= self.config["max_portfolio_concentration"]:
            return False, f"Maximum portfolio concentration ({self.config['max_portfolio_concentration']:.0%}) reached for {symbol}"
        
        return True, "Trade allowed"
    
    def _calculate_symbol_concentration(self, symbol: str) -> float:
        """Calculate current concentration in a symbol"""
        if self.state.total_portfolio_value <= 0:
            return 0.0
        
        if symbol not in self.positions:
            return 0.0
        
        position = self.positions[symbol]
        return position.position_value / self.state.total_portfolio_value
    
    def calculate_position_size(
        self,
        symbol: str,
        current_price: float,
        ai_confidence: float,
        method: str = "fixed_percent"
    ) -> float:
        """
        Calculate the optimal position size based on risk parameters
        
        Args:
            symbol: Trading pair symbol
            current_price: Current asset price
            ai_confidence: AI model confidence (0-1)
            method: Position sizing method (fixed_percent, kelly, anti_martingale)
            
        Returns:
            Position size in base currency (e.g., BTC amount)
        """
        if self.state.available_balance <= 0:
            logger.warning("No available balance for position sizing")
            return 0.0
        
        if method == "kelly":
            # Kelly Criterion: f = (bp - q) / b
            # f = fraction to bet, b = odds, p = win prob, q = loss prob
            return self._kelly_criterion_size(symbol, current_price, ai_confidence)
        elif method == "anti_martingale":
            # Increase position size after wins, decrease after losses
            return self._anti_martingale_size(symbol, current_price, ai_confidence)
        else:
            # Default: fixed percentage with adjustments
            return self._fixed_percent_size(symbol, current_price, ai_confidence)
    
    def _fixed_percent_size(self, symbol: str, current_price: float, ai_confidence: float) -> float:
        """Fixed percentage position sizing with adjustments."""
        # Base position size as percentage of portfolio
        base_percent = self.config["max_position_size_percent"]
        
        # Adjust by AI confidence (higher confidence = larger position)
        confidence_multiplier = 0.5 + (ai_confidence * 0.5)  # Range: 0.5 to 1.0
        
        # Adjust by current drawdown (reduce size during drawdown)
        drawdown_factor = 1.0 - (self.state.current_drawdown / 100 * 0.5)
        drawdown_factor = max(0.5, drawdown_factor)
        
        # Adjust by consecutive losses
        loss_factor = 1.0 - (self.state.consecutive_losses * 0.1)
        loss_factor = max(0.5, loss_factor)
        
        # Calculate final position size
        adjusted_percent = (
            base_percent 
            * confidence_multiplier 
            * drawdown_factor 
            * loss_factor
        )
        
        # Calculate position value
        position_value = self.state.available_balance * (adjusted_percent / 100)
        
        # Calculate quantity
        quantity = position_value / current_price if current_price > 0 else 0.0
        
        logger.info(
            f"Position size for {symbol}: {quantity:.6f} "
            f"(Value: ${position_value:.2f}, Method: fixed_percent, "
            f"Confidence: {ai_confidence:.2%}, Adjusted %: {adjusted_percent:.2f}%)"
        )
        
        return quantity
    
    def _kelly_criterion_size(self, symbol: str, current_price: float, ai_confidence: float) -> float:
        """Kelly Criterion position sizing."""
        # Estimate win probability from trade history
        if len(self.trade_history) < 10:
            # Not enough history, fall back to fixed percent
            return self._fixed_percent_size(symbol, current_price, ai_confidence)
        
        recent_trades = self.trade_history[-20:]  # Last 20 trades
        wins = [t for t in recent_trades if t.pnl > 0]
        losses = [t for t in recent_trades if t.pnl <= 0]
        
        if not wins or not losses:
            return self._fixed_percent_size(symbol, current_price, ai_confidence)
        
        # Calculate probabilities and averages
        win_prob = len(wins) / len(recent_trades)
        loss_prob = 1 - win_prob
        
        avg_win = sum(abs(t.pnl_percent) for t in wins) / len(wins)
        avg_loss = sum(abs(t.pnl_percent) for t in losses) / len(losses)
        
        # Kelly fraction: f = (bp - q) / b
        # where b = avg_win/avg_loss, p = win_prob, q = loss_prob
        if avg_loss == 0:
            return self._fixed_percent_size(symbol, current_price, ai_confidence)
        
        odds = avg_win / avg_loss
        kelly_fraction = (odds * win_prob - loss_prob) / odds
        
        # Apply safety factor (1/2 Kelly or 1/4 Kelly)
        kelly_fraction = kelly_fraction * 0.25  # Quarter Kelly (conservative)
        kelly_fraction = max(0.0, min(kelly_fraction, 0.10))  # Cap at 10%
        
        # Adjust by AI confidence
        kelly_fraction *= (0.5 + ai_confidence * 0.5)
        
        position_value = self.state.available_balance * kelly_fraction
        quantity = position_value / current_price if current_price > 0 else 0.0
        
        logger.info(
            f"Kelly position size for {symbol}: {quantity:.6f} "
            f"(Kelly%: {kelly_fraction*100:.2f}%, WinProb: {win_prob:.2f}, "
            f"Odds: {odds:.2f})"
        )
        
        return quantity
    
    def _anti_martingale_size(self, symbol: str, current_price: float, ai_confidence: float) -> float:
        """Anti-Martingale position sizing (increase after wins, decrease after losses)."""
        base_size = self._fixed_percent_size(symbol, current_price, ai_confidence)
        
        # Check recent performance
        if len(self.trade_history) == 0:
            return base_size
        
        recent_trades = self.trade_history[-5:]  # Last 5 trades
        winning_streak = 0
        losing_streak = 0
        
        for trade in reversed(recent_trades):
            if trade.pnl > 0:
                if losing_streak == 0:
                    winning_streak += 1
                else:
                    break
            else:
                if winning_streak == 0:
                    losing_streak += 1
                else:
                    break
        
        # Increase size after wins (max 1.5x)
        if winning_streak > 0:
            multiplier = 1.0 + (winning_streak * 0.1)
            multiplier = min(multiplier, 1.5)
            return base_size * multiplier
        
        # Decrease size after losses (min 0.5x)
        if losing_streak > 0:
            multiplier = 1.0 - (losing_streak * 0.1)
            multiplier = max(multiplier, 0.5)
            return base_size * multiplier
        
        return base_size
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        side: OrderSide,
        volatility_factor: float = 1.0,
        atr: Optional[float] = None
    ) -> float:
        """
        Calculate stop-loss price (fixed or ATR-based)
        
        Args:
            entry_price: Entry price of the position
            side: BUY or SELL
            volatility_factor: Multiplier based on current volatility (default: 1.0)
            atr: Average True Range for dynamic stop loss
            
        Returns:
            Stop-loss price
        """
        if atr is not None:
            # ATR-based dynamic stop loss (2x ATR)
            atr_multiplier = 2.0
            stop_distance = atr * atr_multiplier
            
            if side == OrderSide.BUY:
                stop_loss = entry_price - stop_distance
            else:
                stop_loss = entry_price + stop_distance
            
            logger.debug(f"ATR-based stop: {stop_loss:.2f} (ATR: {atr:.2f})")
        else:
            # Fixed percentage stop loss
            stop_percent = self.config["stop_loss_percent"] * volatility_factor
            
            if side == OrderSide.BUY:
                stop_loss = entry_price * (1 - stop_percent / 100)
            else:
                stop_loss = entry_price * (1 + stop_percent / 100)
        
        return stop_loss
    
    def calculate_take_profit(
        self,
        entry_price: float,
        side: OrderSide,
        risk_reward_ratio: float = 2.0
    ) -> float:
        """
        Calculate take-profit price
        
        Args:
            entry_price: Entry price of the position
            side: BUY or SELL
            risk_reward_ratio: Risk/reward ratio (default: 2.0)
            
        Returns:
            Take-profit price
        """
        take_profit_percent = self.config["take_profit_percent"]
        
        if side == OrderSide.BUY:
            take_profit = entry_price * (1 + take_profit_percent / 100)
        else:
            take_profit = entry_price * (1 - take_profit_percent / 100)
        
        return take_profit
    
    def open_position(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float
    ) -> Position:
        """Record a new position"""
        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=datetime.utcnow(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            current_price=entry_price
        )
        
        self.positions[symbol] = position
        self.state.daily_trades += 1
        
        logger.info(
            f"Position opened: {symbol} {side.value} "
            f"@ ${entry_price:.2f} x {quantity:.6f}"
        )
        
        return position
    
    def update_position_price(self, symbol: str, current_price: float) -> Optional[Position]:
        """Update the current price for a position"""
        if symbol not in self.positions:
            return None
        
        self.positions[symbol].current_price = current_price
        return self.positions[symbol]
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        ai_confidence: float = 0.0
    ) -> Optional[TradeRecord]:
        """
        Close a position and record the trade
        
        Returns:
            TradeRecord if position existed, None otherwise
        """
        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol}")
            return None
        
        position = self.positions[symbol]
        exit_time = datetime.utcnow()
        
        # Calculate P&L
        if position.side == OrderSide.BUY:
            pnl = (exit_price - position.entry_price) * position.quantity
            pnl_percent = ((exit_price - position.entry_price) / position.entry_price) * 100
        else:
            pnl = (position.entry_price - exit_price) * position.quantity
            pnl_percent = ((position.entry_price - exit_price) / position.entry_price) * 100
        
        # Create trade record
        trade = TradeRecord(
            symbol=symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=exit_time,
            pnl=pnl,
            pnl_percent=pnl_percent,
            ai_confidence=ai_confidence
        )
        
        # Update state
        self.trade_history.append(trade)
        self.state.daily_pnl += pnl
        self.state.hourly_pnl += pnl
        self.state.last_trade_time = exit_time
        
        # Update drawdowns
        self.state.daily_drawdown = (self.state.daily_pnl / self.state.peak_portfolio_value * 100) \
            if self.state.peak_portfolio_value > 0 else 0
        self.state.hourly_drawdown = (self.state.hourly_pnl / self.state.peak_portfolio_value * 100) \
            if self.state.peak_portfolio_value > 0 else 0
        
        # Update consecutive losses
        if pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0
        
        # Remove position
        del self.positions[symbol]
        
        logger.info(
            f"Position closed: {symbol} "
            f"P&L: ${pnl:.2f} ({pnl_percent:.2f}%)"
        )
        
        return trade
    
    def check_positions_for_exit(self) -> List[Tuple[str, str]]:
        """
        Check all positions for stop-loss or take-profit triggers
        
        Returns:
            List of (symbol, reason) tuples for positions that should be closed
        """
        exits = []
        
        for symbol, position in self.positions.items():
            if position.should_stop_loss():
                exits.append((symbol, "stop_loss"))
                logger.warning(
                    f"Stop-loss triggered for {symbol} "
                    f"(Price: ${position.current_price:.2f}, "
                    f"Stop: ${position.stop_loss:.2f})"
                )
            elif position.should_take_profit():
                exits.append((symbol, "take_profit"))
                logger.info(
                    f"Take-profit triggered for {symbol} "
                    f"(Price: ${position.current_price:.2f}, "
                    f"Target: ${position.take_profit:.2f})"
                )
        
        return exits
    
    def get_risk_metrics(self) -> Dict:
        """Get current risk metrics"""
        total_trades = len(self.trade_history)
        winning_trades = len([t for t in self.trade_history if t.pnl > 0])
        losing_trades = len([t for t in self.trade_history if t.pnl <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        total_pnl = sum(t.pnl for t in self.trade_history)
        avg_win = (
            sum(t.pnl for t in self.trade_history if t.pnl > 0) / winning_trades
            if winning_trades > 0 else 0.0
        )
        avg_loss = (
            sum(t.pnl for t in self.trade_history if t.pnl <= 0) / losing_trades
            if losing_trades > 0 else 0.0
        )
        
        return {
            "risk_level": self.risk_level.value,
            "portfolio_value": self.state.total_portfolio_value,
            "available_balance": self.state.available_balance,
            "current_drawdown": self.state.current_drawdown,
            "peak_portfolio_value": self.state.peak_portfolio_value,
            "daily_pnl": self.state.daily_pnl,
            "daily_trades": self.state.daily_trades,
            "max_daily_trades": self.config["max_daily_trades"],
            "consecutive_losses": self.state.consecutive_losses,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "open_positions": len(self.positions),
            "positions": {
                symbol: {
                    "side": pos.side.value,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price,
                    "quantity": pos.quantity,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "unrealized_pnl_percent": pos.unrealized_pnl_percent,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                }
                for symbol, pos in self.positions.items()
            }
        }
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get a specific position"""
        return self.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Check if a position exists for a symbol"""
        return symbol in self.positions
    
    def get_all_positions(self) -> Dict[str, Position]:
        """Get all open positions"""
        return self.positions.copy()
    
    def calculate_trailing_stop(
        self,
        position: Position,
        trailing_percent: float = None
    ) -> float:
        """
        Calculate trailing stop price based on highest/lowest price since entry
        
        Args:
            position: The position to calculate trailing stop for
            trailing_percent: Override trailing stop percentage
            
        Returns:
            New trailing stop price
        """
        if trailing_percent is None:
            trailing_percent = self.config["stop_loss_percent"]
        
        if position.side == OrderSide.BUY:
            # For long positions, trail below the highest price
            new_stop = position.current_price * (1 - trailing_percent / 100)
            return max(new_stop, position.stop_loss)  # Only move up
        else:
            # For short positions, trail above the lowest price
            new_stop = position.current_price * (1 + trailing_percent / 100)
            return min(new_stop, position.stop_loss)  # Only move down
    
    def emergency_close_all(self) -> List[str]:
        """
        Emergency close all positions (used in extreme market conditions)
        
        Returns:
            List of symbols that need to be closed
        """
        logger.warning("EMERGENCY: Closing all positions")
        symbols = list(self.positions.keys())
        return symbols
    
    def reset_daily_state(self) -> None:
        """Manually reset daily state"""
        self.state.daily_pnl = 0.0
        self.state.daily_trades = 0
        self.state.daily_reset_time = datetime.utcnow()
        logger.info("Daily state manually reset")
    
    def reset_consecutive_losses(self) -> None:
        """Reset consecutive loss counter"""
        self.state.consecutive_losses = 0
        logger.info("Consecutive losses counter reset")
    
    # ===========================================
    # Advanced Risk Analytics
    # ===========================================
    
    def calculate_var(
        self,
        confidence_level: float = 0.95,
        time_horizon_days: int = 1
    ) -> Dict[str, float]:
        """
        Calculate Value at Risk (VaR) for the portfolio.
        
        VaR represents the maximum expected loss over a given time period
        at a specified confidence level.
        
        Args:
            confidence_level: Confidence level (default 95%)
            time_horizon_days: Time horizon in days
            
        Returns:
            Dictionary with VaR calculations:
            - var_historical: Historical VaR
            - var_parametric: Parametric VaR  
            - cvar: Conditional VaR (Expected Shortfall)
            - portfolio_value: Current portfolio value
        """
        if not self.trade_history:
            logger.warning("No trade history available for VaR calculation")
            return {
                'var_historical': 0.0,
                'var_parametric': 0.0,
                'cvar': 0.0,
                'portfolio_value': self.state.total_portfolio_value,
                'confidence_level': confidence_level,
                'time_horizon_days': time_horizon_days
            }
        
        # Extract returns from trade history
        returns = np.array([
            trade.pnl_percent / 100 for trade in self.trade_history
        ])
        
        if len(returns) == 0:
            return {
                'var_historical': 0.0,
                'var_parametric': 0.0,
                'cvar': 0.0,
                'portfolio_value': self.state.total_portfolio_value
            }
        
        # Adjust returns for time horizon
        adjusted_returns = returns * np.sqrt(time_horizon_days)
        
        # Historical VaR (percentile method)
        var_historical_pct = np.percentile(adjusted_returns, (1 - confidence_level) * 100)
        var_historical = var_historical_pct * self.state.total_portfolio_value
        
        # Parametric VaR (assumes normal distribution)
        mean_return = np.mean(adjusted_returns)
        std_return = np.std(adjusted_returns)
        z_score = stats.norm.ppf(1 - confidence_level)
        var_parametric_pct = mean_return + (z_score * std_return)
        var_parametric = var_parametric_pct * self.state.total_portfolio_value
        
        # Conditional VaR (Expected Shortfall) - average loss beyond VaR
        losses_beyond_var = adjusted_returns[adjusted_returns < var_historical_pct]
        if len(losses_beyond_var) > 0:
            cvar_pct = np.mean(losses_beyond_var)
            cvar = cvar_pct * self.state.total_portfolio_value
        else:
            cvar = var_historical
        
        logger.info(
            f"VaR ({confidence_level*100}%, {time_horizon_days}d): "
            f"Historical=${abs(var_historical):,.2f}, "
            f"Parametric=${abs(var_parametric):,.2f}, "
            f"CVaR=${abs(cvar):,.2f}"
        )
        
        return {
            'var_historical': abs(var_historical),
            'var_parametric': abs(var_parametric),
            'cvar': abs(cvar),
            'portfolio_value': self.state.total_portfolio_value,
            'confidence_level': confidence_level,
            'time_horizon_days': time_horizon_days,
            'max_expected_loss_pct': abs(var_historical_pct * 100)
        }
    
    def stress_test_portfolio(self) -> Dict[str, Dict]:
        """
        Stress test portfolio under extreme market scenarios.
        
        Tests portfolio resilience under:
        - Market crash (-30%)
        - Flash crash (-15% sudden)
        - Black swan event (-50%)
        - Moderate correction (-10%)
        
        Returns:
            Dictionary with scenario results
        """
        scenarios = {
            'market_crash': -0.30,
            'flash_crash': -0.15,
            'black_swan': -0.50,
            'moderate_correction': -0.10,
            'minor_correction': -0.05
        }
        
        results = {}
        
        for scenario_name, price_change in scenarios.items():
            # Calculate portfolio value after scenario
            scenario_value = 0.0
            position_impacts = {}
            
            for symbol, position in self.positions.items():
                new_price = position.current_price * (1 + price_change)
                new_value = new_price * position.quantity
                impact = new_value - position.position_value
                
                scenario_value += new_value
                position_impacts[symbol] = {
                    'original_value': position.position_value,
                    'scenario_value': new_value,
                    'impact': impact,
                    'impact_pct': (impact / position.position_value * 100) if position.position_value > 0 else 0
                }
            
            # Add remaining balance
            scenario_value += self.state.available_balance
            
            loss = self.state.total_portfolio_value - scenario_value
            loss_pct = (loss / self.state.total_portfolio_value * 100) if self.state.total_portfolio_value > 0 else 0
            
            # Check if any stop losses would trigger
            stop_losses_triggered = []
            for symbol, position in self.positions.items():
                new_price = position.current_price * (1 + price_change)
                if position.side == OrderSide.BUY and new_price <= position.stop_loss:
                    stop_losses_triggered.append(symbol)
                elif position.side == OrderSide.SELL and new_price >= position.stop_loss:
                    stop_losses_triggered.append(symbol)
            
            results[scenario_name] = {
                'scenario': scenario_name,
                'price_change_pct': price_change * 100,
                'original_portfolio_value': self.state.total_portfolio_value,
                'scenario_portfolio_value': scenario_value,
                'loss': loss,
                'loss_pct': loss_pct,
                'position_impacts': position_impacts,
                'stop_losses_triggered': stop_losses_triggered,
                'survives': loss_pct < 50  # Portfolio survives if loss < 50%
            }
        
        # Log worst case
        worst_case = max(results.values(), key=lambda x: x['loss_pct'])
        logger.info(
            f"Stress Test - Worst Case ({worst_case['scenario']}): "
            f"Portfolio would drop to ${worst_case['scenario_portfolio_value']:,.2f} "
            f"({worst_case['loss_pct']:.2f}% loss)"
        )
        
        return results
    
    async def check_portfolio_correlation(
        self,
        price_history: Dict[str, List[float]]
    ) -> Dict[str, any]:
        """
        Analyze correlation between portfolio positions.
        
        High correlation means positions move together, increasing risk.
        
        Args:
            price_history: Dict of symbol -> list of recent prices
            
        Returns:
            Correlation analysis results
        """
        if len(self.positions) < 2:
            return {
                'correlation_risk': 'LOW',
                'message': 'Less than 2 positions, no correlation risk',
                'positions': len(self.positions)
            }
        
        # Get symbols that have positions
        symbols = list(self.positions.keys())
        
        # Filter price history for these symbols
        valid_symbols = [s for s in symbols if s in price_history and len(price_history[s]) > 1]
        
        if len(valid_symbols) < 2:
            return {
                'correlation_risk': 'UNKNOWN',
                'message': 'Insufficient price history for correlation analysis',
                'positions': len(self.positions)
            }
        
        # Calculate returns
        returns_matrix = []
        for symbol in valid_symbols:
            prices = np.array(price_history[symbol])
            returns = np.diff(prices) / prices[:-1]
            returns_matrix.append(returns)
        
        # Ensure all return series have same length
        min_length = min(len(r) for r in returns_matrix)
        returns_matrix = [r[-min_length:] for r in returns_matrix]
        
        # Calculate correlation matrix
        correlation_matrix = np.corrcoef(returns_matrix)
        
        # Analyze correlation
        high_correlation_pairs = []
        for i in range(len(valid_symbols)):
            for j in range(i + 1, len(valid_symbols)):
                corr = correlation_matrix[i][j]
                if abs(corr) > 0.8:  # High correlation threshold
                    high_correlation_pairs.append({
                        'symbol1': valid_symbols[i],
                        'symbol2': valid_symbols[j],
                        'correlation': corr
                    })
        
        # Determine risk level
        high_corr_count = len(high_correlation_pairs)
        total_pairs = len(valid_symbols) * (len(valid_symbols) - 1) / 2
        high_corr_ratio = high_corr_count / total_pairs if total_pairs > 0 else 0
        
        if high_corr_ratio > 0.5:
            risk_level = 'HIGH'
            message = 'More than 50% of position pairs are highly correlated'
        elif high_corr_ratio > 0.25:
            risk_level = 'MEDIUM'
            message = '25-50% of position pairs are highly correlated'
        else:
            risk_level = 'LOW'
            message = 'Portfolio is well-diversified with low correlation'
        
        # Calculate average correlation
        upper_triangle = correlation_matrix[np.triu_indices_from(correlation_matrix, k=1)]
        avg_correlation = np.mean(np.abs(upper_triangle))
        
        logger.info(
            f"Portfolio Correlation: {risk_level} "
            f"(avg={avg_correlation:.2f}, high_corr_pairs={high_corr_count})"
        )
        
        return {
            'correlation_risk': risk_level,
            'message': message,
            'positions': len(self.positions),
            'analyzed_positions': len(valid_symbols),
            'average_correlation': float(avg_correlation),
            'high_correlation_pairs': high_correlation_pairs,
            'high_correlation_count': high_corr_count,
            'recommendation': 'Consider reducing positions' if risk_level == 'HIGH' else 'Portfolio diversification acceptable'
        }
    
    def calculate_optimal_position_size(
        self,
        symbol: str,
        volatility: float,
        correlation_with_portfolio: float = 0.0
    ) -> float:
        """
        Calculate optimal position size based on volatility and correlation.
        
        Uses Kelly Criterion adjusted for volatility and correlation.
        
        Args:
            symbol: Trading symbol
            volatility: Asset volatility (standard deviation of returns)
            correlation_with_portfolio: Correlation with existing portfolio (0-1)
            
        Returns:
            Optimal position size as percentage of portfolio
        """
        base_size = self.config["max_position_size_percent"]
        
        # Adjust for volatility (higher volatility = smaller position)
        volatility_factor = 1.0 / (1.0 + volatility * 2)
        
        # Adjust for correlation (higher correlation = smaller position)
        correlation_factor = 1.0 - (abs(correlation_with_portfolio) * 0.5)
        
        # Adjust for win rate if we have trade history
        if self.trade_history:
            symbol_trades = [t for t in self.trade_history if t.symbol == symbol]
            if symbol_trades:
                wins = sum(1 for t in symbol_trades if t.pnl > 0)
                win_rate = wins / len(symbol_trades)
                
                # Kelly Criterion: f = (bp - q) / b
                # where p = win rate, q = loss rate, b = win/loss ratio
                if win_rate > 0.5:
                    avg_win = np.mean([t.pnl_percent for t in symbol_trades if t.pnl > 0])
                    avg_loss = abs(np.mean([t.pnl_percent for t in symbol_trades if t.pnl <= 0]))
                    
                    if avg_loss > 0:
                        b = avg_win / avg_loss
                        kelly_fraction = (b * win_rate - (1 - win_rate)) / b
                        kelly_factor = max(0.25, min(kelly_fraction / 2, 1.0))  # Use half-Kelly, capped
                    else:
                        kelly_factor = 0.5
                else:
                    kelly_factor = 0.5
            else:
                kelly_factor = 0.75  # Conservative for new symbols
        else:
            kelly_factor = 0.75
        
        # Calculate final position size
        optimal_size = base_size * volatility_factor * correlation_factor * kelly_factor
        
        # Ensure within bounds
        optimal_size = max(0.5, min(optimal_size, base_size))
        
        logger.info(
            f"Optimal position size for {symbol}: {optimal_size:.2f}% "
            f"(vol_adj={volatility_factor:.2f}, corr_adj={correlation_factor:.2f}, "
            f"kelly={kelly_factor:.2f})"
        )
        
        return optimal_size


# Create global risk manager instance lazily
def get_risk_manager() -> RiskManager:
    """Get risk manager instance."""
    settings = get_settings()
    return RiskManager(risk_level=RiskLevel(settings.RISK_LEVEL))
