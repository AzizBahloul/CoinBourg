"""
Strategy Performance Tracker
============================
Track every trade with strategy attribution and performance metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Individual trade record."""
    trade_id: str
    strategy_name: str
    symbol: str
    action: str  # BUY, SELL
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    entry_time: datetime
    exit_time: Optional[datetime]
    profit_loss: Optional[float] = None
    profit_loss_percent: Optional[float] = None
    fees: float = 0.0
    duration_seconds: Optional[int] = None
    was_successful: Optional[bool] = None
    notes: str = ""


@dataclass
class StrategyMetrics:
    """Performance metrics for a strategy."""
    strategy_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    total_loss: float
    net_profit: float
    avg_profit_per_trade: float
    avg_winning_trade: float
    avg_losing_trade: float
    largest_win: float
    largest_loss: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    avg_trade_duration_minutes: float
    sharpe_ratio: float
    max_drawdown: float
    total_fees: float
    profit_factor: float  # Total profits / Total losses
    last_updated: datetime


class PerformanceTracker:
    """
    Track and analyze strategy performance.
    
    Features:
    - Track every trade with strategy attribution
    - Calculate comprehensive metrics per strategy
    - Dynamic capital allocation based on performance
    - Identify winning/losing strategies
    - Pause underperforming strategies
    """
    
    def __init__(self):
        """Initialize performance tracker."""
        self.trades: List[Trade] = []
        self.strategy_metrics: Dict[str, StrategyMetrics] = {}
        self.capital_allocations: Dict[str, float] = {}
        
        # Performance thresholds
        self.min_trades_for_evaluation = 10
        self.pause_threshold_losses = 3  # Pause after 3 consecutive losses
        self.low_performance_threshold = 0.35  # < 35% win rate
        
        # Tracking
        self.consecutive_losses: Dict[str, int] = defaultdict(int)
        self.paused_strategies: set = set()
        
        logger.info("PerformanceTracker initialized")
    
    def record_trade(
        self,
        trade_id: str,
        strategy_name: str,
        symbol: str,
        action: str,
        entry_price: float,
        quantity: float,
        fees: float = 0.0,
        notes: str = ""
    ) -> Trade:
        """
        Record a new trade entry.
        
        Args:
            trade_id: Unique trade identifier
            strategy_name: Name of strategy that generated the signal
            symbol: Trading pair
            action: BUY or SELL
            entry_price: Entry price
            quantity: Trade quantity
            fees: Trading fees
            notes: Optional notes
            
        Returns:
            Trade object
        """
        trade = Trade(
            trade_id=trade_id,
            strategy_name=strategy_name,
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            exit_price=None,
            quantity=quantity,
            entry_time=datetime.utcnow(),
            exit_time=None,
            fees=fees,
            notes=notes
        )
        
        self.trades.append(trade)
        logger.info(f"Recorded trade entry: {trade_id} - {strategy_name} - {action} {symbol} @ {entry_price}")
        
        return trade
    
    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_fees: float = 0.0
    ) -> Optional[Trade]:
        """
        Close an existing trade and calculate P&L.
        
        Args:
            trade_id: Trade identifier
            exit_price: Exit price
            exit_fees: Exit fees
            
        Returns:
            Updated Trade object or None if not found
        """
        # Find trade
        trade = None
        for t in self.trades:
            if t.trade_id == trade_id and t.exit_price is None:
                trade = t
                break
        
        if not trade:
            logger.warning(f"Trade {trade_id} not found or already closed")
            return None
        
        # Calculate P&L
        trade.exit_price = exit_price
        trade.exit_time = datetime.utcnow()
        trade.fees += exit_fees
        
        if trade.action == "BUY":
            # Bought low, sold high
            trade.profit_loss = (exit_price - trade.entry_price) * trade.quantity - trade.fees
        else:
            # Sold high, bought low (short)
            trade.profit_loss = (trade.entry_price - exit_price) * trade.quantity - trade.fees
        
        trade.profit_loss_percent = (trade.profit_loss / (trade.entry_price * trade.quantity)) * 100
        trade.was_successful = trade.profit_loss > 0
        
        # Calculate duration
        if trade.exit_time and trade.entry_time:
            duration = trade.exit_time - trade.entry_time
            trade.duration_seconds = int(duration.total_seconds())
        
        # Update consecutive losses tracking
        if trade.was_successful:
            self.consecutive_losses[trade.strategy_name] = 0
        else:
            self.consecutive_losses[trade.strategy_name] += 1
            
            # Check if strategy should be paused
            if self.consecutive_losses[trade.strategy_name] >= self.pause_threshold_losses:
                self._pause_strategy(trade.strategy_name)
        
        # Update metrics
        self._update_strategy_metrics(trade.strategy_name)
        
        logger.info(
            f"Closed trade: {trade_id} - {trade.strategy_name} - "
            f"P&L: ${trade.profit_loss:.2f} ({trade.profit_loss_percent:+.2f}%) "
            f"Duration: {trade.duration_seconds}s"
        )
        
        return trade
    
    def _update_strategy_metrics(self, strategy_name: str):
        """Update metrics for a specific strategy."""
        # Get all closed trades for this strategy
        strategy_trades = [
            t for t in self.trades 
            if t.strategy_name == strategy_name and t.exit_price is not None
        ]
        
        if not strategy_trades:
            return
        
        # Calculate metrics
        total_trades = len(strategy_trades)
        winning_trades = sum(1 for t in strategy_trades if t.was_successful)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        profits = [t.profit_loss for t in strategy_trades if t.profit_loss and t.profit_loss > 0]
        losses = [abs(t.profit_loss) for t in strategy_trades if t.profit_loss and t.profit_loss < 0]
        
        total_profit = sum(profits) if profits else 0
        total_loss = sum(losses) if losses else 0
        net_profit = sum(t.profit_loss for t in strategy_trades if t.profit_loss)
        
        avg_profit_per_trade = net_profit / total_trades if total_trades > 0 else 0
        avg_winning_trade = sum(profits) / len(profits) if profits else 0
        avg_losing_trade = sum(losses) / len(losses) if losses else 0
        
        largest_win = max(profits) if profits else 0
        largest_loss = max(losses) if losses else 0
        
        # Calculate consecutive wins/losses
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_streak = 0
        
        for trade in strategy_trades:
            if trade.was_successful:
                current_streak = current_streak + 1 if current_streak > 0 else 1
                max_consecutive_wins = max(max_consecutive_wins, current_streak)
            else:
                current_streak = current_streak - 1 if current_streak < 0 else -1
                max_consecutive_losses = max(max_consecutive_losses, abs(current_streak))
        
        # Average trade duration
        durations = [t.duration_seconds for t in strategy_trades if t.duration_seconds]
        avg_duration_minutes = (sum(durations) / len(durations) / 60) if durations else 0
        
        # Sharpe ratio (simplified)
        returns = [t.profit_loss_percent for t in strategy_trades if t.profit_loss_percent]
        sharpe_ratio = 0
        if len(returns) > 1:
            import numpy as np
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = (mean_return / std_return) if std_return > 0 else 0
        
        # Max drawdown
        max_drawdown = self._calculate_max_drawdown(strategy_trades)
        
        # Profit factor
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        # Total fees
        total_fees = sum(t.fees for t in strategy_trades)
        
        # Create/update metrics
        metrics = StrategyMetrics(
            strategy_name=strategy_name,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_profit=total_profit,
            total_loss=total_loss,
            net_profit=net_profit,
            avg_profit_per_trade=avg_profit_per_trade,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            largest_win=largest_win,
            largest_loss=largest_loss,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            avg_trade_duration_minutes=avg_duration_minutes,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            total_fees=total_fees,
            profit_factor=profit_factor,
            last_updated=datetime.utcnow()
        )
        
        self.strategy_metrics[strategy_name] = metrics
        
        # Update capital allocation
        self._update_capital_allocation(strategy_name, metrics)
    
    def _calculate_max_drawdown(self, trades: List[Trade]) -> float:
        """Calculate maximum drawdown for a list of trades."""
        if not trades:
            return 0.0
        
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        
        for trade in trades:
            if trade.profit_loss:
                cumulative += trade.profit_loss
                if cumulative > peak:
                    peak = cumulative
                drawdown = peak - cumulative
                if drawdown > max_dd:
                    max_dd = drawdown
        
        return max_dd
    
    def _update_capital_allocation(self, strategy_name: str, metrics: StrategyMetrics):
        """
        Update capital allocation based on strategy performance.
        
        Winning strategies get more capital, losing strategies get less.
        """
        if metrics.total_trades < self.min_trades_for_evaluation:
            # Not enough trades, use default allocation
            self.capital_allocations[strategy_name] = 1.0
            return
        
        # Base allocation on win rate and profit factor
        allocation = 1.0
        
        # Increase allocation for high performers
        if metrics.win_rate >= 0.6 and metrics.profit_factor >= 1.5:
            allocation = 1.5
            logger.info(f"Increased allocation for {strategy_name}: 1.5x (win_rate={metrics.win_rate:.2f})")
        elif metrics.win_rate >= 0.55 and metrics.profit_factor >= 1.2:
            allocation = 1.25
        
        # Decrease allocation for low performers
        elif metrics.win_rate < 0.4 or metrics.profit_factor < 0.8:
            allocation = 0.5
            logger.warning(f"Decreased allocation for {strategy_name}: 0.5x (win_rate={metrics.win_rate:.2f})")
        elif metrics.win_rate < 0.45 or metrics.profit_factor < 1.0:
            allocation = 0.75
        
        self.capital_allocations[strategy_name] = allocation
    
    def _pause_strategy(self, strategy_name: str):
        """Pause a strategy after consecutive losses."""
        if strategy_name not in self.paused_strategies:
            self.paused_strategies.add(strategy_name)
            logger.warning(
                f"⚠️ STRATEGY PAUSED: {strategy_name} - "
                f"{self.consecutive_losses[strategy_name]} consecutive losses"
            )
    
    def unpause_strategy(self, strategy_name: str):
        """Manually unpause a strategy."""
        if strategy_name in self.paused_strategies:
            self.paused_strategies.remove(strategy_name)
            self.consecutive_losses[strategy_name] = 0
            logger.info(f"Strategy unpaused: {strategy_name}")
    
    def is_strategy_paused(self, strategy_name: str) -> bool:
        """Check if a strategy is paused."""
        return strategy_name in self.paused_strategies
    
    def get_strategy_metrics(self, strategy_name: str) -> Optional[StrategyMetrics]:
        """Get metrics for a specific strategy."""
        return self.strategy_metrics.get(strategy_name)
    
    def get_all_metrics(self) -> Dict[str, StrategyMetrics]:
        """Get metrics for all strategies."""
        return self.strategy_metrics
    
    def get_capital_allocation(self, strategy_name: str) -> float:
        """Get capital allocation multiplier for a strategy."""
        return self.capital_allocations.get(strategy_name, 1.0)
    
    def get_top_strategies(self, n: int = 5, metric: str = "net_profit") -> List[StrategyMetrics]:
        """
        Get top N strategies by a specific metric.
        
        Args:
            n: Number of strategies to return
            metric: Metric to sort by (net_profit, win_rate, profit_factor, sharpe_ratio)
            
        Returns:
            List of top StrategyMetrics
        """
        if not self.strategy_metrics:
            return []
        
        sorted_strategies = sorted(
            self.strategy_metrics.values(),
            key=lambda x: getattr(x, metric, 0),
            reverse=True
        )
        
        return sorted_strategies[:n]
    
    def export_trades(self, strategy_name: Optional[str] = None) -> List[Dict]:
        """
        Export trade history as list of dictionaries.
        
        Args:
            strategy_name: Optional filter by strategy
            
        Returns:
            List of trade dictionaries
        """
        trades = self.trades
        if strategy_name:
            trades = [t for t in trades if t.strategy_name == strategy_name]
        
        return [asdict(trade) for trade in trades]
    
    def get_summary(self) -> Dict:
        """Get overall performance summary."""
        closed_trades = [t for t in self.trades if t.exit_price is not None]
        
        if not closed_trades:
            return {
                "total_trades": 0,
                "active_trades": len(self.trades),
                "message": "No closed trades yet"
            }
        
        total_profit = sum(t.profit_loss for t in closed_trades if t.profit_loss)
        winning_trades = sum(1 for t in closed_trades if t.was_successful)
        
        return {
            "total_trades": len(closed_trades),
            "active_trades": len(self.trades) - len(closed_trades),
            "winning_trades": winning_trades,
            "losing_trades": len(closed_trades) - winning_trades,
            "overall_win_rate": winning_trades / len(closed_trades) if closed_trades else 0,
            "total_profit": total_profit,
            "paused_strategies": list(self.paused_strategies),
            "best_strategy": max(self.strategy_metrics.values(), key=lambda x: x.net_profit).strategy_name if self.strategy_metrics else None
        }
