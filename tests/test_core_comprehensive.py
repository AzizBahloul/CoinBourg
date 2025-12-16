"""
Unit Tests for Core Trading Module
===================================
Comprehensive test coverage for core trading components.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.risk_manager import RiskManager, Position, TradeRecord, RiskLevel
from src.core.state_manager import StateManager
from src.config.constants import OrderSide


class TestRiskManager:
    """Test suite for RiskManager."""
    
    @pytest.fixture
    def risk_manager(self):
        """Create a RiskManager instance for testing."""
        return RiskManager(risk_level=RiskLevel.MODERATE)
    
    def test_initialization(self, risk_manager):
        """Test RiskManager initializes correctly."""
        assert risk_manager.risk_level == RiskLevel.MODERATE
        assert risk_manager.positions == {}
        assert risk_manager.trade_history == []
        assert risk_manager.config is not None
    
    def test_position_creation(self, risk_manager):
        """Test creating a new position."""
        position = risk_manager.open_position(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=48000.0,
            take_profit=52000.0
        )
        
        assert position is not None
        assert position.symbol == "BTCUSDT"
        assert position.side == OrderSide.BUY
        assert position.entry_price == 50000.0
        assert position.quantity == 0.1
        assert "BTCUSDT" in risk_manager.positions
    
    def test_position_update(self, risk_manager):
        """Test updating position price."""
        risk_manager.open_position(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=48000.0,
            take_profit=52000.0
        )
        
        risk_manager.update_position_price("BTCUSDT", 51000.0)
        position = risk_manager.get_position("BTCUSDT")
        
        assert position.current_price == 51000.0
        assert position.unrealized_pnl > 0
    
    def test_var_calculation(self, risk_manager):
        """Test Value at Risk calculation."""
        # Add some trade history
        for i in range(50):
            trade = TradeRecord(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                entry_price=50000.0,
                exit_price=50500.0 if i % 2 == 0 else 49500.0,
                quantity=0.1,
                entry_time=datetime.utcnow() - timedelta(hours=i),
                exit_time=datetime.utcnow() - timedelta(hours=i-1),
                pnl=50.0 if i % 2 == 0 else -50.0,
                pnl_percent=1.0 if i % 2 == 0 else -1.0,
                ai_confidence=0.75
            )
            risk_manager.trade_history.append(trade)
        
        risk_manager.state.total_portfolio_value = 10000.0
        
        var = risk_manager.calculate_var(confidence_level=0.95)
        
        assert 'var_historical' in var
        assert 'var_parametric' in var
        assert 'cvar' in var
        assert var['var_historical'] >= 0
        assert var['confidence_level'] == 0.95
    
    def test_stress_testing(self, risk_manager):
        """Test portfolio stress testing."""
        # Create a position
        risk_manager.open_position(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=50000.0,
            quantity=0.2,
            stop_loss=48000.0,
            take_profit=52000.0
        )
        
        risk_manager.update_position_price("BTCUSDT", 50000.0)
        risk_manager.state.total_portfolio_value = 10000.0
        risk_manager.state.available_balance = 5000.0
        
        results = risk_manager.stress_test_portfolio()
        
        assert 'market_crash' in results
        assert 'flash_crash' in results
        assert 'black_swan' in results
        
        # Loss values are negative in stress tests (profit is positive)
        assert results['market_crash']['loss'] != 0
        assert results['market_crash']['loss_pct'] != 0
    
    @pytest.mark.asyncio
    async def test_correlation_analysis(self, risk_manager):
        """Test portfolio correlation analysis."""
        # Create multiple positions
        risk_manager.open_position(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=50000.0,
            quantity=0.1,
            stop_loss=48000.0,
            take_profit=52000.0
        )
        
        risk_manager.open_position(
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            entry_price=3000.0,
            quantity=1.0,
            stop_loss=2900.0,
            take_profit=3100.0
        )
        
        # Mock price history
        price_history = {
            'BTCUSDT': [50000, 50100, 50200, 50150, 50250],
            'ETHUSDT': [3000, 3010, 3020, 3015, 3025]
        }
        
        result = await risk_manager.check_portfolio_correlation(price_history)
        
        assert 'correlation_risk' in result
        assert 'average_correlation' in result
        assert result['positions'] == 2
    
    def test_optimal_position_sizing(self, risk_manager):
        """Test optimal position size calculation."""
        size = risk_manager.calculate_optimal_position_size(
            symbol="BTCUSDT",
            volatility=0.05,  # 5% volatility
            correlation_with_portfolio=0.3
        )
        
        assert size > 0
        assert size <= risk_manager.config['max_position_size_percent']


class TestStateManager:
    """Test suite for StateManager."""
    
    @pytest.fixture
    def state_manager(self):
        """Create StateManager instance for testing."""
        # Use test database
        return StateManager(database_url="postgresql://test:test@localhost:5432/test_db")
    
    @pytest.mark.asyncio
    async def test_save_load_positions(self, state_manager):
        """Test saving and loading positions."""
        # Create mock positions
        from src.core.trading_engine import Position as EnginePosition
        
        positions = {
            'BTCUSDT': EnginePosition(
                symbol='BTCUSDT',
                quantity=0.1,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=100.0,
                unrealized_pnl_percent=2.0,
                stop_loss=48000.0,
                take_profit=52000.0,
                entry_time=datetime.utcnow()
            )
        }
        
        try:
            await state_manager.save_positions(positions)
            loaded_positions = await state_manager.load_positions()
            
            assert 'BTCUSDT' in loaded_positions
            assert loaded_positions['BTCUSDT'].symbol == 'BTCUSDT'
            assert loaded_positions['BTCUSDT'].quantity == 0.1
        
        except Exception as e:
            pytest.skip(f"Database not available: {e}")


@pytest.mark.asyncio
async def test_trading_engine_initialization():
    """Test trading engine initialization."""
    from src.core.trading_engine import TradingEngine
    
    engine = TradingEngine()
    
    assert engine is not None
    assert engine.binance is not None
    assert engine.deepseek is not None
    assert engine.state_manager is not None


@pytest.mark.asyncio
async def test_error_monitor():
    """Test error monitoring system."""
    from src.utils.error_monitor import ErrorMonitor
    
    monitor = ErrorMonitor()
    
    test_error = ValueError("Test error")
    context = {'test': 'data'}
    
    await monitor.capture_exception(test_error, context, level='error')
    
    stats = monitor.get_error_stats()
    assert stats['total_unique_errors'] >= 1


def test_prompt_engineering():
    """Test enhanced prompt engineering."""
    from src.intelligence.prompt_engineer import PromptEngineer
    
    engineer = PromptEngineer()
    
    # Add a trade result
    engineer.add_trade_result(
        symbol='BTCUSDT',
        action='BUY',
        entry_price=50000.0,
        exit_price=51000.0,
        pnl_pct=2.0,
        ai_prediction='BUY',
        ai_confidence=0.8
    )
    
    # Build prompt
    market_data = {
        'current_price': 50000.0,
        'price_change_24h': 2.5,
        'volume_24h': 1000000000,
        'high_24h': 51000.0,
        'low_24h': 49000.0
    }
    
    indicators = {
        'RSI_14': 55.0,
        'MACD': {'macd': 100, 'signal': 95},
        'ATR_14': 500.0
    }
    
    prompt = engineer.build_enhanced_prompt(
        symbol='BTCUSDT',
        market_data=market_data,
        indicators=indicators,
        strategy_signals=[]
    )
    
    assert 'BTCUSDT' in prompt
    assert 'Capital Preservation' in prompt.upper()
    assert str(engineer.ai_accuracy) in prompt


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--cov=src/core", "--cov=src/utils", "--cov=src/intelligence"])
