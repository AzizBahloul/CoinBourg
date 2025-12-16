"""
State Manager for CoinBourg Trading System
===========================================
Handles persistence of trading state to PostgreSQL database.
"""

import logging
import asyncpg
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
import json
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from contextlib import asynccontextmanager

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages persistent storage of trading engine state.
    
    Responsibilities:
    - Save/load positions to/from database
    - Save/load trades to/from database
    - Save/load metrics to/from database
    - Handle database transactions atomically
    - Provide state recovery after crashes
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize state manager.
        
        Args:
            database_url: PostgreSQL connection string (uses settings if None)
        """
        settings = get_settings()
        self.database_url = database_url or settings.DATABASE_URL
        self.conn = None
        try:
            self._ensure_tables()
        except Exception as e:
            logger.warning(f"Could not initialize database: {e}. State persistence will be limited.")
            self.conn = None
    
    def _get_connection(self):
        """Get or create database connection."""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(self.database_url)
        return self.conn
    
    def _ensure_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol VARCHAR(20) PRIMARY KEY,
                    entry_price DECIMAL(20, 8) NOT NULL,
                    current_price DECIMAL(20, 8) NOT NULL,
                    quantity DECIMAL(20, 8) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    entry_time TIMESTAMP NOT NULL,
                    stop_loss DECIMAL(20, 8),
                    take_profit DECIMAL(20, 8),
                    unrealized_pnl DECIMAL(20, 8),
                    unrealized_pnl_pct DECIMAL(10, 4),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    entry_price DECIMAL(20, 8) NOT NULL,
                    exit_price DECIMAL(20, 8),
                    quantity DECIMAL(20, 8) NOT NULL,
                    entry_time TIMESTAMP NOT NULL,
                    exit_time TIMESTAMP,
                    stop_loss DECIMAL(20, 8),
                    take_profit DECIMAL(20, 8),
                    pnl DECIMAL(20, 8),
                    pnl_pct DECIMAL(10, 4),
                    status VARCHAR(20) NOT NULL,
                    strategy VARCHAR(50),
                    ai_confidence DECIMAL(5, 4),
                    ai_reasoning TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS engine_metrics (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl DECIMAL(20, 8) DEFAULT 0,
                    total_pnl_pct DECIMAL(10, 4) DEFAULT 0,
                    win_rate DECIMAL(5, 4) DEFAULT 0,
                    average_win DECIMAL(20, 8) DEFAULT 0,
                    average_loss DECIMAL(20, 8) DEFAULT 0,
                    largest_win DECIMAL(20, 8) DEFAULT 0,
                    largest_loss DECIMAL(20, 8) DEFAULT 0,
                    current_streak INTEGER DEFAULT 0,
                    max_drawdown DECIMAL(10, 4) DEFAULT 0,
                    sharpe_ratio DECIMAL(10, 4) DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT single_row CHECK (id = 1)
                )
            """)
            
            # Insert default metrics row if not exists
            cursor.execute("""
                INSERT INTO engine_metrics (id) VALUES (1)
                ON CONFLICT (id) DO NOTHING
            """)
            
            conn.commit()
            logger.info("State management tables ensured")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating state tables: {e}")
            raise
        finally:
            cursor.close()
    
    async def save_state(self, engine):
        """
        Save complete engine state to database.
        
        Args:
            engine: TradingEngine instance
        """
        logger.info("Saving engine state to database...")
        
        try:
            await asyncio.gather(
                self.save_positions(engine.positions),
                self.save_trades(engine.trades),
                self.save_metrics(engine)
            )
            logger.info("Engine state saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving engine state: {e}")
            raise
    
    async def restore_state(self, engine):
        """
        Restore engine state from database.
        
        Args:
            engine: TradingEngine instance to restore into
        """
        logger.info("Restoring engine state from database...")
        
        try:
            positions, trades, metrics = await asyncio.gather(
                self.load_positions(),
                self.load_trades(),
                self.load_metrics()
            )
            
            engine.positions = positions
            engine.trades = trades
            
            # Restore metrics
            if metrics:
                for key, value in metrics.items():
                    if hasattr(engine, key):
                        setattr(engine, key, value)
            
            logger.info(f"State restored: {len(positions)} positions, {len(trades)} trades")
            
        except Exception as e:
            logger.error(f"Error restoring engine state: {e}")
            raise
    
    async def save_positions(self, positions: Dict):
        """Save positions to database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Clear existing positions
            cursor.execute("DELETE FROM positions")
            
            # Insert current positions
            for symbol, position in positions.items():
                cursor.execute("""
                    INSERT INTO positions (
                        symbol, entry_price, current_price, quantity, side,
                        entry_time, stop_loss, take_profit, unrealized_pnl, unrealized_pnl_pct
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    symbol,
                    position.entry_price,
                    position.current_price,
                    position.quantity,
                    position.side,
                    position.entry_time,
                    position.stop_loss,
                    position.take_profit,
                    position.unrealized_pnl,
                    position.unrealized_pnl_pct
                ))
            
            conn.commit()
            logger.debug(f"Saved {len(positions)} positions")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving positions: {e}")
            raise
        finally:
            cursor.close()
    
    async def load_positions(self) -> Dict:
        """Load positions from database."""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("SELECT * FROM positions")
            rows = cursor.fetchall()
            
            positions = {}
            for row in rows:
                # Import Position class here to avoid circular import
                from src.core.trading_engine import Position
                
                positions[row['symbol']] = Position(
                    symbol=row['symbol'],
                    entry_price=float(row['entry_price']),
                    current_price=float(row['current_price']),
                    quantity=float(row['quantity']),
                    side=row['side'],
                    entry_time=row['entry_time'],
                    stop_loss=float(row['stop_loss']) if row['stop_loss'] else None,
                    take_profit=float(row['take_profit']) if row['take_profit'] else None,
                    unrealized_pnl=float(row['unrealized_pnl']) if row['unrealized_pnl'] else 0.0,
                    unrealized_pnl_pct=float(row['unrealized_pnl_pct']) if row['unrealized_pnl_pct'] else 0.0
                )
            
            return positions
            
        except Exception as e:
            logger.error(f"Error loading positions: {e}")
            return {}
        finally:
            cursor.close()
    
    async def save_trades(self, trades: List):
        """Save trades to database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            for trade in trades:
                # Check if trade already exists
                cursor.execute("SELECT id FROM trades WHERE id = %s", (trade.id,))
                exists = cursor.fetchone()
                
                if exists:
                    # Update existing trade
                    cursor.execute("""
                        UPDATE trades SET
                            exit_price = %s,
                            exit_time = %s,
                            pnl = %s,
                            pnl_pct = %s,
                            status = %s
                        WHERE id = %s
                    """, (
                        trade.exit_price,
                        trade.exit_time,
                        trade.pnl,
                        trade.pnl_pct,
                        trade.status,
                        trade.id
                    ))
                else:
                    # Insert new trade
                    cursor.execute("""
                        INSERT INTO trades (
                            symbol, side, entry_price, exit_price, quantity,
                            entry_time, exit_time, stop_loss, take_profit,
                            pnl, pnl_pct, status, strategy, ai_confidence, ai_reasoning
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        trade.symbol,
                        trade.side,
                        trade.entry_price,
                        trade.exit_price,
                        trade.quantity,
                        trade.entry_time,
                        trade.exit_time,
                        trade.stop_loss,
                        trade.take_profit,
                        trade.pnl,
                        trade.pnl_pct,
                        trade.status,
                        getattr(trade, 'strategy', None),
                        getattr(trade, 'ai_confidence', None),
                        getattr(trade, 'ai_reasoning', None)
                    ))
            
            conn.commit()
            logger.debug(f"Saved {len(trades)} trades")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving trades: {e}")
            raise
        finally:
            cursor.close()
    
    async def load_trades(self, limit: int = 1000) -> List:
        """Load recent trades from database."""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT * FROM trades
                ORDER BY entry_time DESC
                LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            
            trades = []
            for row in rows:
                # Import Trade class here to avoid circular import
                from src.core.trading_engine import Trade
                
                trades.append(Trade(
                    id=row['id'],
                    symbol=row['symbol'],
                    side=row['side'],
                    entry_price=float(row['entry_price']),
                    exit_price=float(row['exit_price']) if row['exit_price'] else None,
                    quantity=float(row['quantity']),
                    entry_time=row['entry_time'],
                    exit_time=row['exit_time'],
                    stop_loss=float(row['stop_loss']) if row['stop_loss'] else None,
                    take_profit=float(row['take_profit']) if row['take_profit'] else None,
                    pnl=float(row['pnl']) if row['pnl'] else 0.0,
                    pnl_pct=float(row['pnl_pct']) if row['pnl_pct'] else 0.0,
                    status=row['status']
                ))
            
            return trades
            
        except Exception as e:
            logger.error(f"Error loading trades: {e}")
            return []
        finally:
            cursor.close()
    
    async def save_metrics(self, engine):
        """Save engine metrics to database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE engine_metrics SET
                    total_trades = %s,
                    winning_trades = %s,
                    losing_trades = %s,
                    total_pnl = %s,
                    total_pnl_pct = %s,
                    win_rate = %s,
                    average_win = %s,
                    average_loss = %s,
                    largest_win = %s,
                    largest_loss = %s,
                    current_streak = %s,
                    max_drawdown = %s,
                    sharpe_ratio = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (
                getattr(engine, 'total_trades', 0),
                getattr(engine, 'winning_trades', 0),
                getattr(engine, 'losing_trades', 0),
                getattr(engine, 'total_pnl', 0.0),
                getattr(engine, 'total_pnl_pct', 0.0),
                getattr(engine, 'win_rate', 0.0),
                getattr(engine, 'average_win', 0.0),
                getattr(engine, 'average_loss', 0.0),
                getattr(engine, 'largest_win', 0.0),
                getattr(engine, 'largest_loss', 0.0),
                getattr(engine, 'current_streak', 0),
                getattr(engine, 'max_drawdown', 0.0),
                getattr(engine, 'sharpe_ratio', 0.0)
            ))
            
            conn.commit()
            logger.debug("Saved engine metrics")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving metrics: {e}")
            raise
        finally:
            cursor.close()
    
    async def load_metrics(self) -> Dict:
        """Load engine metrics from database."""
        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("SELECT * FROM engine_metrics WHERE id = 1")
            row = cursor.fetchone()
            
            if row:
                return {
                    'total_trades': row['total_trades'],
                    'winning_trades': row['winning_trades'],
                    'losing_trades': row['losing_trades'],
                    'total_pnl': float(row['total_pnl']),
                    'total_pnl_pct': float(row['total_pnl_pct']),
                    'win_rate': float(row['win_rate']),
                    'average_win': float(row['average_win']),
                    'average_loss': float(row['average_loss']),
                    'largest_win': float(row['largest_win']),
                    'largest_loss': float(row['largest_loss']),
                    'current_streak': row['current_streak'],
                    'max_drawdown': float(row['max_drawdown']),
                    'sharpe_ratio': float(row['sharpe_ratio'])
                }
            return {}
            
        except Exception as e:
            logger.error(f"Error loading metrics: {e}")
            return {}
        finally:
            cursor.close()
    
    async def recover_incomplete_trades(self) -> List[Dict]:
        """
        Recover trades that were in progress when system stopped.
        
        Returns:
            List of incomplete trades as dictionaries
        """
        try:
            async with self.pool.acquire() as conn:
                trades = await conn.fetch("""
                    SELECT * FROM trades
                    WHERE status IN ('PENDING', 'OPEN')
                    ORDER BY entry_time DESC
                """)
                
                incomplete_trades = []
                for trade in trades:
                    # Convert to dict
                    logger.info(f"Found incomplete trade: {trade['symbol']} - {trade['status']}")
                    incomplete_trades.append(dict(trade))
                
                return incomplete_trades
        
        except Exception as e:
            logger.error(f"Failed to recover incomplete trades: {e}")
            return []
    
    async def test_connection(self) -> bool:
        """
        Test database connection.
        
        Returns:
            True if connection is healthy
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def close(self):
        """Close database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            logger.info("Database connection closed")
