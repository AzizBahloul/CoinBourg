
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order execution status."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class BacktestOrder:
    """Simulated order in backtest."""
    order_id: str
    symbol: str
    side: str  # BUY, SELL
    order_type: str  # MARKET, LIMIT
    quantity: float
    price: Optional[float]
    timestamp: datetime
    status: OrderStatus
    filled_price: Optional[float] = None
    filled_timestamp: Optional[datetime] = None
    commission: float = 0.0


@dataclass
class BacktestPosition:
    """Position in backtest."""
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    buy_and_hold_return: float
    buy_and_hold_return_pct: float
    excess_return: float
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Performance metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    calmar_ratio: float
    
    # Risk metrics
    volatility: float
    downside_deviation: float
    value_at_risk_95: float
    
    # Trading metrics
    avg_trade_return: float
    avg_winning_trade: float
    avg_losing_trade: float
    largest_win: float
    largest_loss: float
    profit_factor: float
    avg_trade_duration: float
    
    # Costs
    total_commission: float
    total_slippage: float
    
    # Time series data
    equity_curve: List[Tuple[datetime, float]]
    drawdown_series: List[Tuple[datetime, float]]
    trade_log: List[Dict]


class BacktestEngine:
    """
    Comprehensive backtesting engine for strategy validation.
    
    Features:
    - Realistic order simulation with slippage and fees
    - Multi-symbol support
    - Multiple order types (market, limit)
    - Historical data replay
    - Comprehensive performance metrics
    - Cross-validation support
    """
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,  # 0.1%
        slippage_pct: float = 0.0005,  # 0.05%
        risk_free_rate: float = 0.02  # 2% annual
    ):
        """
        Initialize backtest engine.
        
        Args:
            initial_capital: Starting capital
            commission_rate: Commission per trade (as decimal)
            slippage_pct: Slippage percentage
            risk_free_rate: Risk-free rate for Sharpe calculation
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_pct = slippage_pct
        self.risk_free_rate = risk_free_rate
        
        # State
        self.capital = initial_capital
        self.positions: Dict[str, BacktestPosition] = {}
        self.orders: List[BacktestOrder] = []
        self.trade_history: List[Dict] = []
        self.equity_history: List[Tuple[datetime, float]] = []
        
        # Metrics tracking
        self.peak_capital = initial_capital
        self.current_drawdown = 0.0
        self.max_drawdown = 0.0
        self.max_drawdown_duration = 0
        self.drawdown_start: Optional[datetime] = None
        
        logger.info(f"BacktestEngine initialized - Capital: ${initial_capital:,.2f}")
    
    def reset(self):
        """Reset backtest state."""
        self.capital = self.initial_capital
        self.positions = {}
        self.orders = []
        self.trade_history = []
        self.equity_history = []
        self.peak_capital = self.initial_capital
        self.current_drawdown = 0.0
        self.max_drawdown = 0.0
        self.max_drawdown_duration = 0
        self.drawdown_start = None
    
    async def run_backtest(
        self,
        strategy,
        symbol: str,
        data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResult:
        """
        Run backtest for a strategy on historical data.
        
        Args:
            strategy: Strategy instance with analyze() method
            symbol: Trading pair symbol
            data: DataFrame with OHLCV data (columns: timestamp, open, high, low, close, volume)
            start_date: Start date for backtest
            end_date: End date for backtest
            
        Returns:
            BacktestResult with comprehensive metrics
        """
        self.reset()
        
        # Filter data by date range
        if start_date:
            data = data[data['timestamp'] >= start_date]
        if end_date:
            data = data[data['timestamp'] <= end_date]
        
        if len(data) < 50:
            raise ValueError("Insufficient data for backtesting (need at least 50 periods)")
        
        logger.info(f"Starting backtest: {symbol} from {data['timestamp'].iloc[0]} to {data['timestamp'].iloc[-1]}")
        
        # Calculate buy and hold benchmark
        buy_and_hold_return = (data['close'].iloc[-1] / data['close'].iloc[0]) - 1
        
        # Main backtest loop
        for i in range(50, len(data)):  # Start after 50 periods for indicators
            current_bar = data.iloc[i]
            timestamp = current_bar['timestamp']
            current_price = current_bar['close']
            
            # Update positions
            self._update_positions(symbol, current_price)
            
            # Record equity
            total_equity = self._calculate_total_equity()
            self.equity_history.append((timestamp, total_equity))
            
            # Update drawdown
            self._update_drawdown(total_equity, timestamp)
            
            # Prepare data for strategy
            historical_data = data.iloc[:i+1]
            price_data = {
                'close': historical_data['close'].values,
                'high': historical_data['high'].values,
                'low': historical_data['low'].values,
                'volume': historical_data['volume'].values,
                'open': historical_data['open'].values
            }
            
            # Calculate indicators (simplified - strategy should do this)
            indicators = self._calculate_indicators(historical_data)
            
            # Get strategy signal
            try:
                signal = await strategy.analyze(symbol, price_data, indicators)
            except Exception as e:
                logger.error(f"Strategy analysis failed at {timestamp}: {e}")
                continue
            
            # Execute signal
            if signal.action == "BUY" and symbol not in self.positions:
                self._execute_buy(symbol, current_price, timestamp, signal)
            elif signal.action == "SELL" and symbol in self.positions:
                self._execute_sell(symbol, current_price, timestamp, signal)
        
        # Close any remaining positions
        for symbol in list(self.positions.keys()):
            final_price = data['close'].iloc[-1]
            final_timestamp = data['timestamp'].iloc[-1]
            self._execute_sell(symbol, final_price, final_timestamp, None)
        
        # Calculate results
        result = self._calculate_results(
            strategy_name=strategy.name,
            symbol=symbol,
            start_date=data['timestamp'].iloc[0],
            end_date=data['timestamp'].iloc[-1],
            buy_and_hold_return=buy_and_hold_return
        )
        
        logger.info(f"Backtest complete: {strategy.name} - Return: {result.total_return_pct:.2f}%, "
                   f"Sharpe: {result.sharpe_ratio:.2f}, Max DD: {result.max_drawdown:.2f}%")
        
        return result
    
    def _execute_buy(self, symbol: str, price: float, timestamp: datetime, signal):
        """Execute buy order."""
        # Calculate position size
        position_size_pct = getattr(signal, 'position_size_percent', 5.0) / 100
        position_value = self.capital * position_size_pct
        
        # Apply slippage (buy at higher price)
        execution_price = price * (1 + self.slippage_pct)
        
        # Calculate quantity
        commission = position_value * self.commission_rate
        quantity = (position_value - commission) / execution_price
        
        if quantity <= 0 or position_value > self.capital:
            return
        
        # Create order
        order = BacktestOrder(
            order_id=f"order_{len(self.orders)}",
            symbol=symbol,
            side="BUY",
            order_type="MARKET",
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            status=OrderStatus.FILLED,
            filled_price=execution_price,
            filled_timestamp=timestamp,
            commission=commission
        )
        self.orders.append(order)
        
        # Update capital
        self.capital -= (quantity * execution_price + commission)
        
        # Create position
        self.positions[symbol] = BacktestPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=execution_price,
            entry_time=timestamp,
            current_price=price,
            unrealized_pnl=0.0
        )
        
        logger.debug(f"BUY {symbol}: {quantity:.6f} @ ${execution_price:.2f}")
    
    def _execute_sell(self, symbol: str, price: float, timestamp: datetime, signal):
        """Execute sell order."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # Apply slippage (sell at lower price)
        execution_price = price * (1 - self.slippage_pct)
        
        # Calculate proceeds
        proceeds = position.quantity * execution_price
        commission = proceeds * self.commission_rate
        net_proceeds = proceeds - commission
        
        # Create order
        order = BacktestOrder(
            order_id=f"order_{len(self.orders)}",
            symbol=symbol,
            side="SELL",
            order_type="MARKET",
            quantity=position.quantity,
            price=price,
            timestamp=timestamp,
            status=OrderStatus.FILLED,
            filled_price=execution_price,
            filled_timestamp=timestamp,
            commission=commission
        )
        self.orders.append(order)
        
        # Calculate P&L
        cost_basis = position.quantity * position.entry_price
        pnl = net_proceeds - cost_basis
        pnl_pct = (pnl / cost_basis) * 100
        
        # Update capital
        self.capital += net_proceeds
        
        # Record trade
        duration = (timestamp - position.entry_time).total_seconds() / 3600  # hours
        trade = {
            'symbol': symbol,
            'entry_time': position.entry_time,
            'exit_time': timestamp,
            'entry_price': position.entry_price,
            'exit_price': execution_price,
            'quantity': position.quantity,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'duration_hours': duration,
            'commission': commission + self.orders[-2].commission if len(self.orders) >= 2 else commission
        }
        self.trade_history.append(trade)
        
        # Remove position
        del self.positions[symbol]
        
        logger.debug(f"SELL {symbol}: {position.quantity:.6f} @ ${execution_price:.2f} - P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
    
    def _update_positions(self, symbol: str, current_price: float):
        """Update position with current price."""
        if symbol in self.positions:
            position = self.positions[symbol]
            position.current_price = current_price
            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
    
    def _calculate_total_equity(self) -> float:
        """Calculate total equity (cash + positions)."""
        equity = self.capital
        for position in self.positions.values():
            equity += position.quantity * position.current_price
        return equity
    
    def _update_drawdown(self, equity: float, timestamp: datetime):
        """Update drawdown metrics."""
        if equity > self.peak_capital:
            self.peak_capital = equity
            self.drawdown_start = None
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = ((equity - self.peak_capital) / self.peak_capital) * 100
            if abs(self.current_drawdown) > abs(self.max_drawdown):
                self.max_drawdown = self.current_drawdown
            
            if self.drawdown_start is None:
                self.drawdown_start = timestamp
            else:
                duration = (timestamp - self.drawdown_start).days
                if duration > self.max_drawdown_duration:
                    self.max_drawdown_duration = duration
    
    def _calculate_indicators(self, data: pd.DataFrame) -> Dict:
        """Calculate technical indicators."""
        close = data['close'].values
        
        indicators = {}
        
        # RSI
        if len(close) >= 14:
            deltas = np.diff(close)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            avg_gain = np.mean(gains[-14:])
            avg_loss = np.mean(losses[-14:])
            
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                indicators['rsi'] = 100 - (100 / (1 + rs))
            else:
                indicators['rsi'] = 100
        
        # MACD (simplified)
        if len(close) >= 26:
            ema_12 = pd.Series(close).ewm(span=12).mean().iloc[-1]
            ema_26 = pd.Series(close).ewm(span=26).mean().iloc[-1]
            macd_line = ema_12 - ema_26
            signal_line = pd.Series([macd_line]).ewm(span=9).mean().iloc[-1]
            
            indicators['macd'] = {
                'macd': macd_line,
                'signal': signal_line,
                'histogram': macd_line - signal_line
            }
        
        return indicators
    
    def _calculate_results(
        self,
        strategy_name: str,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        buy_and_hold_return: float
    ) -> BacktestResult:
        """Calculate comprehensive backtest results."""
        final_capital = self._calculate_total_equity()
        total_return = final_capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        # Trade statistics
        trades = self.trade_history
        total_trades = len(trades)
        
        if total_trades == 0:
            return self._empty_result(strategy_name, symbol, start_date, end_date)
        
        winning_trades = sum(1 for t in trades if t['pnl'] > 0)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Returns analysis
        returns = [t['pnl_pct'] for t in trades]
        positive_returns = [r for r in returns if r > 0]
        negative_returns = [r for r in returns if r < 0]
        
        avg_trade_return = np.mean(returns) if returns else 0
        avg_winning_trade = np.mean(positive_returns) if positive_returns else 0
        avg_losing_trade = np.mean(negative_returns) if negative_returns else 0
        largest_win = max(returns) if returns else 0
        largest_loss = min(returns) if returns else 0
        
        # Profit factor
        total_wins = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        total_losses = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Duration
        avg_trade_duration = np.mean([t['duration_hours'] for t in trades]) if trades else 0
        
        # Sharpe ratio
        equity_returns = []
        for i in range(1, len(self.equity_history)):
            ret = (self.equity_history[i][1] / self.equity_history[i-1][1]) - 1
            equity_returns.append(ret)
        
        if equity_returns:
            mean_return = np.mean(equity_returns)
            std_return = np.std(equity_returns)
            sharpe_ratio = (mean_return - self.risk_free_rate / 252) / std_return * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Sortino ratio
        downside_returns = [r for r in equity_returns if r < 0]
        downside_deviation = np.std(downside_returns) if downside_returns else 0.0001
        sortino_ratio = (mean_return - self.risk_free_rate / 252) / downside_deviation * np.sqrt(252) if equity_returns else 0
        
        # Calmar ratio
        calmar_ratio = (total_return_pct / abs(self.max_drawdown)) if self.max_drawdown != 0 else 0
        
        # Volatility
        volatility = np.std(equity_returns) * np.sqrt(252) * 100 if equity_returns else 0
        
        # VaR 95%
        value_at_risk_95 = np.percentile(equity_returns, 5) * 100 if equity_returns else 0
        
        # Commissions and slippage
        total_commission = sum(o.commission for o in self.orders)
        total_slippage = sum(t['quantity'] * t['entry_price'] * self.slippage_pct for t in trades)
        
        # Drawdown series
        drawdown_series = []
        peak = self.initial_capital
        for ts, equity in self.equity_history:
            if equity > peak:
                peak = equity
            dd = ((equity - peak) / peak) * 100
            drawdown_series.append((ts, dd))
        
        # Buy and hold metrics
        buy_and_hold_return_pct = buy_and_hold_return * 100
        excess_return = total_return_pct - buy_and_hold_return_pct
        
        return BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            buy_and_hold_return=buy_and_hold_return * self.initial_capital,
            buy_and_hold_return_pct=buy_and_hold_return_pct,
            excess_return=excess_return,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=self.max_drawdown,
            max_drawdown_duration=self.max_drawdown_duration,
            calmar_ratio=calmar_ratio,
            volatility=volatility,
            downside_deviation=downside_deviation * 100,
            value_at_risk_95=value_at_risk_95,
            avg_trade_return=avg_trade_return,
            avg_winning_trade=avg_winning_trade,
            avg_losing_trade=avg_losing_trade,
            largest_win=largest_win,
            largest_loss=largest_loss,
            profit_factor=profit_factor,
            avg_trade_duration=avg_trade_duration,
            total_commission=total_commission,
            total_slippage=total_slippage,
            equity_curve=self.equity_history,
            drawdown_series=drawdown_series,
            trade_log=trades
        )
    
    def _empty_result(self, strategy_name: str, symbol: str, start_date: datetime, end_date: datetime) -> BacktestResult:
        """Return empty result when no trades."""
        return BacktestResult(
            strategy_name=strategy_name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=self.initial_capital,
            total_return=0,
            total_return_pct=0,
            buy_and_hold_return=0,
            buy_and_hold_return_pct=0,
            excess_return=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            max_drawdown=0,
            max_drawdown_duration=0,
            calmar_ratio=0,
            volatility=0,
            downside_deviation=0,
            value_at_risk_95=0,
            avg_trade_return=0,
            avg_winning_trade=0,
            avg_losing_trade=0,
            largest_win=0,
            largest_loss=0,
            profit_factor=0,
            avg_trade_duration=0,
            total_commission=0,
            total_slippage=0,
            equity_curve=[],
            drawdown_series=[],
            trade_log=[]
        )
    
    def export_results(self, result: BacktestResult, filename: str):
        """Export backtest results to JSON."""
        import json
        
        export_data = {
            'strategy_name': result.strategy_name,
            'symbol': result.symbol,
            'start_date': result.start_date.isoformat(),
            'end_date': result.end_date.isoformat(),
            'performance': {
                'total_return_pct': result.total_return_pct,
                'buy_and_hold_return_pct': result.buy_and_hold_return_pct,
                'excess_return': result.excess_return,
                'sharpe_ratio': result.sharpe_ratio,
                'sortino_ratio': result.sortino_ratio,
                'max_drawdown': result.max_drawdown,
                'calmar_ratio': result.calmar_ratio,
                'win_rate': result.win_rate
            },
            'trades': result.trade_log
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        logger.info(f"Results exported to {filename}")
