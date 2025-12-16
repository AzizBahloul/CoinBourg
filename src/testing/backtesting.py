"""
Backtesting Runner
==================
Test trading strategies on historical market data.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from src.core.binance_client import BinanceClient
from src.core.market_scanner import MarketScanner
from src.core.strategy_manager import StrategyManager
from src.core.deepseek_client import DeepSeekClient
from src.core.risk_manager import RiskManager
from src.config.settings import get_settings
from .test_engine import TestConfiguration, TestResult, PredictionRecord

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Backtesting engine for historical data analysis."""
    
    def __init__(self):
        self.settings = get_settings()
        self.binance_client = BinanceClient()
        self.market_scanner = MarketScanner(self.binance_client)
        self.strategy_manager = StrategyManager()
        self.deepseek_client = DeepSeekClient()
        self.risk_manager = RiskManager()
        
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """
        Run backtest on historical data.
        
        Args:
            config: Test configuration
            result: Test result object to populate
            
        Returns:
            Updated TestResult
        """
        logger.info(f"Running backtest: {config.start_date} to {config.end_date}")
        
        # Initialize portfolio
        portfolio = {
            'cash': config.initial_capital,
            'positions': {},
            'equity_history': [],
            'trades': []
        }
        
        # Fetch historical data for all symbols
        historical_data = await self._fetch_historical_data(
            config.symbols,
            config.start_date,
            config.end_date
        )
        
        # Run simulation
        for symbol in config.symbols:
            if symbol not in historical_data:
                logger.warning(f"No historical data for {symbol}")
                continue
                
            symbol_result = await self._backtest_symbol(
                symbol,
                historical_data[symbol],
                portfolio,
                config,
                result
            )
            
            result.symbol_results[symbol] = symbol_result
        
        # Calculate final metrics
        result.final_capital = portfolio['cash'] + sum(
            pos['quantity'] * pos['current_price']
            for pos in portfolio['positions'].values()
        )
        result.total_return = result.final_capital - result.initial_capital
        result.total_return_pct = (result.total_return / result.initial_capital) * 100
        
        # Calculate performance metrics
        result = self._calculate_metrics(result, portfolio)
        
        return result
    
    async def _fetch_historical_data(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """Fetch historical OHLCV data for all symbols."""
        historical_data = {}
        
        for symbol in symbols:
            try:
                klines = await self.binance_client.get_historical_klines(
                    symbol=symbol,
                    interval='1h',
                    start_time=int(start_date.timestamp() * 1000),
                    end_time=int(end_date.timestamp() * 1000)
                )
                
                if klines:
                    df = pd.DataFrame(klines, columns=[
                        'timestamp', 'open', 'high', 'low', 'close',
                        'volume', 'close_time', 'quote_volume', 'trades',
                        'taker_buy_base', 'taker_buy_quote', 'ignore'
                    ])
                    
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    
                    historical_data[symbol] = df
                    logger.info(f"Fetched {len(df)} candles for {symbol}")
                    
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
        
        return historical_data
    
    async def _backtest_symbol(
        self,
        symbol: str,
        data: pd.DataFrame,
        portfolio: Dict,
        config: TestConfiguration,
        result: TestResult
    ) -> Dict:
        """Backtest a single symbol."""
        symbol_trades = []
        symbol_predictions = []
        
        # Process each time period
        for i in range(50, len(data)):  # Start at 50 for sufficient history
            current_data = data.iloc[:i+1]
            current_price = float(current_data['close'].iloc[-1])
            current_time = current_data['timestamp'].iloc[-1]
            
            # Calculate indicators
            price_data = {
                'close': current_data['close'].tolist(),
                'high': current_data['high'].tolist(),
                'low': current_data['low'].tolist(),
                'volume': current_data['volume'].tolist()
            }
            
            indicators = await self.market_scanner.calculate_indicators(
                price_data,
                symbol
            )
            
            # Get strategy signals
            signals = await self.strategy_manager.get_consensus(
                symbol,
                price_data,
                indicators,
                {'current_price': current_price}
            )
            
            # Get AI prediction
            try:
                ai_signal = await self.deepseek_client.generate_trading_signals(
                    symbol=symbol,
                    indicators=indicators,
                    strategy_signals=[s.dict() for s in signals]
                )
                
                # Record prediction
                prediction = PredictionRecord(
                    test_run_id=result.test_run_id,
                    symbol=symbol,
                    prediction_time=current_time,
                    predicted_action=ai_signal.get('action', 'HOLD'),
                    predicted_price=current_price,
                    predicted_direction=ai_signal.get('direction', 'NEUTRAL'),
                    confidence=ai_signal.get('confidence', 0.0),
                    ai_reasoning=ai_signal.get('reasoning', '')
                )
                
                # Simulate trade execution
                if prediction.predicted_action == 'BUY':
                    trade = await self._execute_backtest_buy(
                        symbol,
                        current_price,
                        current_time,
                        portfolio,
                        config,
                        prediction
                    )
                    if trade:
                        symbol_trades.append(trade)
                        
                elif prediction.predicted_action == 'SELL':
                    trade = await self._execute_backtest_sell(
                        symbol,
                        current_price,
                        current_time,
                        portfolio,
                        prediction
                    )
                    if trade:
                        symbol_trades.append(trade)
                
                # Evaluate prediction outcome after N periods
                if i + 24 < len(data):  # Check 24 hours later
                    future_price = float(data['close'].iloc[i + 24])
                    prediction = self._evaluate_prediction(
                        prediction,
                        future_price
                    )
                
                symbol_predictions.append(prediction)
                result.predictions.append(prediction)
                result.total_predictions += 1
                
            except Exception as e:
                logger.error(f"Error processing {symbol} at {current_time}: {e}")
        
        # Calculate symbol-specific metrics
        successful = sum(1 for p in symbol_predictions if p.outcome == 'SUCCESS')
        total_pnl = sum(t.get('pnl', 0) for t in symbol_trades)
        
        return {
            'total_predictions': len(symbol_predictions),
            'successful_predictions': successful,
            'accuracy': (successful / len(symbol_predictions) * 100) if symbol_predictions else 0,
            'total_trades': len(symbol_trades),
            'total_pnl': total_pnl,
            'trades': symbol_trades
        }
    
    async def _execute_backtest_buy(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        portfolio: Dict,
        config: TestConfiguration,
        prediction: PredictionRecord
    ) -> Optional[Dict]:
        """Execute a buy order in backtest."""
        # Calculate position size
        position_size = portfolio['cash'] * 0.05  # 5% of portfolio
        if position_size < 10:  # Minimum trade size
            return None
        
        quantity = position_size / price
        cost = quantity * price
        
        if cost > portfolio['cash']:
            return None
        
        # Execute trade
        portfolio['cash'] -= cost
        portfolio['positions'][symbol] = {
            'quantity': quantity,
            'entry_price': price,
            'current_price': price,
            'timestamp': timestamp
        }
        
        return {
            'symbol': symbol,
            'side': 'BUY',
            'price': price,
            'quantity': quantity,
            'cost': cost,
            'timestamp': timestamp,
            'pnl': 0
        }
    
    async def _execute_backtest_sell(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        portfolio: Dict,
        prediction: PredictionRecord
    ) -> Optional[Dict]:
        """Execute a sell order in backtest."""
        if symbol not in portfolio['positions']:
            return None
        
        position = portfolio['positions'][symbol]
        quantity = position['quantity']
        entry_price = position['entry_price']
        
        # Calculate P&L
        proceeds = quantity * price
        cost = quantity * entry_price
        pnl = proceeds - cost
        pnl_pct = (pnl / cost) * 100
        
        # Execute trade
        portfolio['cash'] += proceeds
        del portfolio['positions'][symbol]
        
        return {
            'symbol': symbol,
            'side': 'SELL',
            'price': price,
            'quantity': quantity,
            'proceeds': proceeds,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'timestamp': timestamp,
            'entry_price': entry_price,
            'hold_time': (timestamp - position['timestamp']).total_seconds()
        }
    
    def _evaluate_prediction(
        self,
        prediction: PredictionRecord,
        actual_price: float
    ) -> PredictionRecord:
        """Evaluate if prediction was successful."""
        prediction.actual_price = actual_price
        
        # Determine actual direction
        price_change = ((actual_price - prediction.predicted_price) / 
                       prediction.predicted_price) * 100
        
        if price_change > 1:
            prediction.actual_direction = 'UP'
        elif price_change < -1:
            prediction.actual_direction = 'DOWN'
        else:
            prediction.actual_direction = 'NEUTRAL'
        
        # Evaluate outcome
        if prediction.predicted_direction == prediction.actual_direction:
            prediction.outcome = 'SUCCESS'
        elif prediction.predicted_direction == 'NEUTRAL':
            prediction.outcome = 'PARTIAL'
        else:
            prediction.outcome = 'FAILURE'
        
        prediction.profit_loss_pct = price_change
        
        return prediction
    
    def _calculate_metrics(
        self,
        result: TestResult,
        portfolio: Dict
    ) -> TestResult:
        """Calculate comprehensive performance metrics."""
        trades = portfolio.get('trades', [])
        
        if trades:
            winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
            
            result.total_trades = len(trades)
            result.winning_trades = len(winning_trades)
            result.losing_trades = len(losing_trades)
            result.win_rate = (len(winning_trades) / len(trades)) * 100
            
            if trades:
                result.avg_profit_per_trade = sum(t.get('pnl', 0) for t in trades) / len(trades)
        
        # Calculate prediction accuracy
        successful = sum(1 for p in result.predictions if p.outcome == 'SUCCESS')
        if result.predictions:
            result.accuracy = (successful / len(result.predictions)) * 100
            result.successful_predictions = successful
            result.failed_predictions = len(result.predictions) - successful
        
        return result
