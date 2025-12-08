"""
CoinBourg Risk Manager
Comprehensive risk management for safe trading
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

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
            self.state.daily_reset_time = now
    
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
        ai_confidence: float
    ) -> float:
        """
        Calculate the optimal position size based on risk parameters
        
        Args:
            symbol: Trading pair symbol
            current_price: Current asset price
            ai_confidence: AI model confidence (0-1)
            
        Returns:
            Position size in base currency (e.g., BTC amount)
        """
        if self.state.available_balance <= 0:
            logger.warning("No available balance for position sizing")
            return 0.0
        
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
            f"(Value: ${position_value:.2f}, "
            f"Confidence: {ai_confidence:.2%}, "
            f"Adjusted %: {adjusted_percent:.2f}%)"
        )
        
        return quantity
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        side: OrderSide,
        volatility_factor: float = 1.0
    ) -> float:
        """
        Calculate stop-loss price
        
        Args:
            entry_price: Entry price of the position
            side: BUY or SELL
            volatility_factor: Multiplier based on current volatility (default: 1.0)
            
        Returns:
            Stop-loss price
        """
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
        self.state.last_trade_time = exit_time
        
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


# Create global risk manager instance lazily
def get_risk_manager() -> RiskManager:
    """Get risk manager instance."""
    settings = get_settings()
    return RiskManager(risk_level=RiskLevel(settings.RISK_LEVEL))
