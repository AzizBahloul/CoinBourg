"""
Signal Validator
=================
Validate buy/sell signals against actual price movements.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import numpy as np

from src.core.binance_client import BinanceClient
from .test_engine import TestConfiguration, TestResult, PredictionRecord

logger = logging.getLogger(__name__)


class SignalValidator:
    """Validate trading signals against actual outcomes."""
    
    def __init__(self):
        self.binance_client = BinanceClient()
        
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """
        Validate signals by checking actual price movements.
        
        Args:
            config: Test configuration
            result: Test result object to populate
            
        Returns:
            Updated TestResult
        """
        logger.info("Starting signal validation")
        
        validation_periods = config.parameters.get('validation_periods', [1, 4, 24])  # Hours
        
        for symbol in config.symbols:
            try:
                symbol_result = await self._validate_symbol_signals(
                    symbol,
                    validation_periods,
                    config,
                    result
                )
                result.symbol_results[symbol] = symbol_result
            except Exception as e:
                logger.error(f"Error validating {symbol}: {e}")
        
        # Calculate overall accuracy
        if result.predictions:
            successful = sum(1 for p in result.predictions if p.outcome == 'SUCCESS')
            result.successful_predictions = successful
            result.failed_predictions = len(result.predictions) - successful
            result.accuracy = (successful / len(result.predictions)) * 100
        
        return result
    
    async def _validate_symbol_signals(
        self,
        symbol: str,
        validation_periods: List[int],
        config: TestConfiguration,
        result: TestResult
    ) -> Dict:
        """Validate signals for a single symbol."""
        # Get recent signals from database or generate new ones
        signals = await self._generate_test_signals(symbol, config)
        
        validated_predictions = []
        
        for signal in signals:
            for period_hours in validation_periods:
                # Get price after period
                try:
                    future_price = await self._get_future_price(
                        symbol,
                        signal['timestamp'],
                        period_hours
                    )
                    
                    if future_price:
                        prediction = PredictionRecord(
                            test_run_id=result.test_run_id,
                            symbol=symbol,
                            prediction_time=signal['timestamp'],
                            predicted_action=signal['action'],
                            predicted_price=signal['price'],
                            predicted_direction=signal['direction'],
                            confidence=signal.get('confidence', 0.5),
                            actual_price=future_price,
                            time_to_outcome=period_hours * 3600
                        )
                        
                        # Evaluate signal accuracy
                        prediction = self._evaluate_signal(prediction, period_hours)
                        validated_predictions.append(prediction)
                        result.predictions.append(prediction)
                        result.total_predictions += 1
                        
                except Exception as e:
                    logger.error(f"Error validating signal for {symbol}: {e}")
        
        # Calculate symbol-specific metrics
        successful = sum(1 for p in validated_predictions if p.outcome == 'SUCCESS')
        
        return {
            'total_signals': len(validated_predictions),
            'successful_signals': successful,
            'accuracy': (successful / len(validated_predictions) * 100) if validated_predictions else 0,
            'validation_periods': validation_periods
        }
    
    async def _generate_test_signals(
        self,
        symbol: str,
        config: TestConfiguration
    ) -> List[Dict]:
        """Generate test signals for validation."""
        # This would typically come from your strategy or AI
        # For now, generate sample signals
        signals = []
        current_price = await self._get_current_price(symbol)
        
        if current_price:
            signals.append({
                'symbol': symbol,
                'action': 'BUY',
                'direction': 'UP',
                'price': current_price,
                'timestamp': datetime.utcnow(),
                'confidence': 0.7
            })
        
        return signals
    
    async def _get_current_price(self, symbol: str) -> float:
        """Get current price for symbol."""
        try:
            ticker = await self.binance_client.get_ticker(symbol)
            return float(ticker.get('lastPrice', 0))
        except:
            return 0
    
    async def _get_future_price(
        self,
        symbol: str,
        signal_time: datetime,
        hours_ahead: int
    ) -> float:
        """Get price N hours after signal."""
        try:
            # If signal is in the past, get historical data
            target_time = signal_time + timedelta(hours=hours_ahead)
            
            if target_time <= datetime.utcnow():
                klines = await self.binance_client.get_historical_klines(
                    symbol=symbol,
                    interval='1h',
                    start_time=int(target_time.timestamp() * 1000),
                    limit=1
                )
                if klines:
                    return float(klines[0][4])  # Close price
            else:
                # Future time - get current price
                return await self._get_current_price(symbol)
        except Exception as e:
            logger.error(f"Error getting future price: {e}")
        
        return 0
    
    def _evaluate_signal(
        self,
        prediction: PredictionRecord,
        period_hours: int
    ) -> PredictionRecord:
        """Evaluate if signal was accurate."""
        if not prediction.actual_price or not prediction.predicted_price:
            prediction.outcome = 'FAILURE'
            return prediction
        
        # Calculate actual price movement
        price_change_pct = (
            (prediction.actual_price - prediction.predicted_price) / 
            prediction.predicted_price
        ) * 100
        
        prediction.profit_loss_pct = price_change_pct
        
        # Determine actual direction
        if price_change_pct > 1:
            prediction.actual_direction = 'UP'
        elif price_change_pct < -1:
            prediction.actual_direction = 'DOWN'
        else:
            prediction.actual_direction = 'NEUTRAL'
        
        # Evaluate success based on prediction vs actual
        if prediction.predicted_action == 'BUY':
            if prediction.actual_direction == 'UP':
                prediction.outcome = 'SUCCESS'
            elif prediction.actual_direction == 'NEUTRAL':
                prediction.outcome = 'PARTIAL'
            else:
                prediction.outcome = 'FAILURE'
        elif prediction.predicted_action == 'SELL':
            if prediction.actual_direction == 'DOWN':
                prediction.outcome = 'SUCCESS'
            elif prediction.actual_direction == 'NEUTRAL':
                prediction.outcome = 'PARTIAL'
            else:
                prediction.outcome = 'FAILURE'
        else:
            prediction.outcome = 'PARTIAL'
        
        return prediction
