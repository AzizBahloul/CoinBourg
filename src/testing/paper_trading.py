"""
Paper Trading Runner
====================
Real-time simulation without using real money.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List
import uuid

from src.core.trading_engine import TradingEngine
from .test_engine import TestConfiguration, TestResult, PredictionRecord

logger = logging.getLogger(__name__)


class PaperTradingRunner:
    """Paper trading engine for real-time simulation."""
    
    def __init__(self):
        self.trading_engine = None
        
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """
        Run paper trading simulation.
        
        Args:
            config: Test configuration
            result: Test result object to populate
            
        Returns:
            Updated TestResult
        """
        logger.info("Starting paper trading simulation")
        
        # Initialize trading engine in paper mode
        self.trading_engine = TradingEngine()
        self.trading_engine.paper_trading = True
        
        # Track predictions and trades
        start_time = datetime.utcnow()
        duration = (config.end_date - config.start_date).total_seconds()
        
        try:
            # Run for specified duration
            await asyncio.wait_for(
                self._monitor_and_trade(config, result),
                timeout=min(duration, 3600)  # Max 1 hour for paper trading
            )
        except asyncio.TimeoutError:
            logger.info("Paper trading duration completed")
        
        # Collect results
        result = self._collect_results(result)
        
        return result
    
    async def _monitor_and_trade(
        self,
        config: TestConfiguration,
        result: TestResult
    ):
        """Monitor market and execute paper trades."""
        while True:
            for symbol in config.symbols:
                try:
                    # Get current market analysis
                    analysis = await self.trading_engine._analyze_symbol(symbol)
                    
                    if analysis and 'action' in analysis:
                        # Record prediction
                        prediction = PredictionRecord(
                            test_run_id=result.test_run_id,
                            symbol=symbol,
                            prediction_time=datetime.utcnow(),
                            predicted_action=analysis['action'],
                            predicted_price=analysis.get('current_price', 0),
                            predicted_direction=analysis.get('direction', 'NEUTRAL'),
                            confidence=analysis.get('confidence', 0),
                            ai_reasoning=analysis.get('reasoning', '')
                        )
                        
                        result.predictions.append(prediction)
                        result.total_predictions += 1
                        
                        logger.info(f"Paper trade prediction: {symbol} {prediction.predicted_action}")
                        
                except Exception as e:
                    logger.error(f"Error in paper trading {symbol}: {e}")
            
            await asyncio.sleep(60)  # Check every minute
    
    def _collect_results(self, result: TestResult) -> TestResult:
        """Collect final paper trading results."""
        if self.trading_engine:
            result.total_trades = self.trading_engine.stats['total_trades']
            result.winning_trades = self.trading_engine.stats.get('winning_trades', 0)
            result.losing_trades = self.trading_engine.stats.get('losing_trades', 0)
            
            if result.total_trades > 0:
                result.win_rate = (result.winning_trades / result.total_trades) * 100
            
            result.final_capital = self.trading_engine.portfolio['total_value']
            result.total_return = result.final_capital - result.initial_capital
            result.total_return_pct = (result.total_return / result.initial_capital) * 100
        
        return result
