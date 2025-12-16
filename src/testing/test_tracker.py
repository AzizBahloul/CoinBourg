"""
Test Database Manager
=====================
Manages test results in PostgreSQL database.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
import json
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from contextlib import asynccontextmanager

from src.config.settings import get_settings
from .test_engine import TestResult, PredictionRecord, TestType

logger = logging.getLogger(__name__)


class TestDatabaseManager:
    """Database manager for test results and predictions."""
    
    def __init__(self):
        self.settings = get_settings()
        self.connection = None
        
    async def connect(self):
        """Connect to database."""
        try:
            self.connection = psycopg2.connect(
                self.settings.DATABASE_URL,
                cursor_factory=RealDictCursor
            )
            logger.info("Connected to test database")
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
    
    async def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")
    
    async def save_test_result(self, result: TestResult) -> bool:
        """Save test result to database."""
        if not self.connection:
            await self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            # Save test run
            cursor.execute("""
                INSERT INTO test_runs (
                    id, test_type, status, symbols, start_date, end_date,
                    initial_capital, final_capital, total_return, total_return_pct,
                    sharpe_ratio, max_drawdown, win_rate, profit_factor,
                    total_predictions, successful_predictions, failed_predictions, accuracy,
                    total_trades, winning_trades, losing_trades, avg_profit_per_trade,
                    configuration, symbol_results, details, errors, execution_time,
                    created_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                result.test_run_id, result.test_type.value, result.status.value,
                result.symbols, result.start_date, result.end_date,
                result.initial_capital, result.final_capital,
                result.total_return, result.total_return_pct,
                result.sharpe_ratio, result.max_drawdown,
                result.win_rate, result.profit_factor,
                result.total_predictions, result.successful_predictions,
                result.failed_predictions, result.accuracy,
                result.total_trades, result.winning_trades,
                result.losing_trades, result.avg_profit_per_trade,
                Json({}), Json(result.symbol_results), Json(result.details),
                result.errors, result.execution_time,
                result.created_at, result.completed_at
            ))
            
            # Save predictions
            for prediction in result.predictions:
                await self.save_prediction(prediction)
            
            # Save equity curve
            for point in result.equity_curve:
                cursor.execute("""
                    INSERT INTO test_equity_curve (
                        test_run_id, timestamp, equity_value, drawdown
                    ) VALUES (%s, %s, %s, %s)
                """, (
                    result.test_run_id,
                    point.get('timestamp'),
                    point.get('equity'),
                    point.get('drawdown', 0)
                ))
            
            self.connection.commit()
            logger.info(f"Saved test result {result.test_run_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving test result: {e}")
            self.connection.rollback()
            return False
    
    async def save_prediction(self, prediction: PredictionRecord) -> bool:
        """Save prediction record."""
        if not self.connection:
            await self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("""
                INSERT INTO predictions (
                    test_run_id, symbol, prediction_time,
                    predicted_action, predicted_price, predicted_direction, confidence,
                    actual_price, actual_direction, outcome,
                    profit_loss, profit_loss_pct, time_to_outcome,
                    ai_reasoning, ai_confidence
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                prediction.test_run_id, prediction.symbol, prediction.prediction_time,
                prediction.predicted_action, prediction.predicted_price,
                prediction.predicted_direction, prediction.confidence,
                prediction.actual_price, prediction.actual_direction, prediction.outcome,
                prediction.profit_loss, prediction.profit_loss_pct, prediction.time_to_outcome,
                prediction.ai_reasoning, prediction.confidence
            ))
            
            self.connection.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error saving prediction: {e}")
            self.connection.rollback()
            return False
    
    async def get_test_results(
        self,
        test_run_id: Optional[str] = None,
        test_type: Optional[TestType] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get test results from database."""
        if not self.connection:
            await self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            query = "SELECT * FROM test_runs WHERE 1=1"
            params = []
            
            if test_run_id:
                query += " AND id = %s"
                params.append(test_run_id)
            
            if test_type:
                query += " AND test_type = %s"
                params.append(test_type.value)
            
            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting test results: {e}")
            return []
    
    async def get_predictions(
        self,
        symbol: Optional[str] = None,
        test_run_id: Optional[str] = None
    ) -> List[Dict]:
        """Get prediction records."""
        if not self.connection:
            await self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            query = "SELECT * FROM predictions WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = %s"
                params.append(symbol)
            
            if test_run_id:
                query += " AND test_run_id = %s"
                params.append(test_run_id)
            
            query += " ORDER BY prediction_time DESC LIMIT 1000"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting predictions: {e}")
            return []
    
    async def get_best_symbols(
        self,
        test_type: Optional[TestType] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Get best performing symbols."""
        if not self.connection:
            await self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            query = """
                SELECT 
                    symbol,
                    test_type,
                    total_predictions,
                    successful_predictions,
                    accuracy,
                    total_profit_loss,
                    avg_profit_per_trade
                FROM symbol_performance
            """
            
            params = []
            if test_type:
                query += " WHERE test_type = %s"
                params.append(test_type.value)
            
            query += " ORDER BY accuracy DESC, total_profit_loss DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting best symbols: {e}")
            return []
    
    async def update_symbol_performance(
        self,
        symbol: str,
        test_type: str,
        prediction_result: PredictionRecord
    ):
        """Update symbol performance statistics."""
        if not self.connection:
            await self.connect()
        
        try:
            cursor = self.connection.cursor()
            
            # Upsert symbol performance
            cursor.execute("""
                INSERT INTO symbol_performance (
                    symbol, test_type, total_predictions, successful_predictions,
                    accuracy, total_profit_loss, avg_profit_per_trade
                ) VALUES (
                    %s, %s, 1, %s, %s, %s, %s
                )
                ON CONFLICT (symbol, test_type) DO UPDATE SET
                    total_predictions = symbol_performance.total_predictions + 1,
                    successful_predictions = symbol_performance.successful_predictions + EXCLUDED.successful_predictions,
                    accuracy = ((symbol_performance.successful_predictions + EXCLUDED.successful_predictions)::FLOAT / 
                               (symbol_performance.total_predictions + 1)::FLOAT * 100),
                    total_profit_loss = symbol_performance.total_profit_loss + EXCLUDED.total_profit_loss,
                    avg_profit_per_trade = (symbol_performance.total_profit_loss + EXCLUDED.total_profit_loss) / 
                                          (symbol_performance.total_predictions + 1),
                    last_updated = NOW()
            """, (
                symbol, test_type,
                1 if prediction_result.outcome == 'SUCCESS' else 0,
                100.0 if prediction_result.outcome == 'SUCCESS' else 0.0,
                prediction_result.profit_loss or 0,
                prediction_result.profit_loss or 0
            ))
            
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error updating symbol performance: {e}")
            self.connection.rollback()
