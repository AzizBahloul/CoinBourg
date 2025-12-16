"""
Pytest Configuration and Shared Fixtures
=========================================
Global test configuration and reusable fixtures.
"""

import pytest
import asyncio
import os
import sys
from datetime import datetime
from unittest.mock import Mock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.BINANCE_API_KEY = "test_api_key"
    settings.BINANCE_SECRET_KEY = "test_secret_key"
    settings.BINANCE_TESTNET = True
    settings.DEEPSEEK_API_KEY = "test_deepseek_key"
    settings.PAPER_TRADING = True
    settings.TRADING_ENABLED = False
    settings.RISK_LEVEL = "MODERATE"
    settings.MAX_POSITION_SIZE_PERCENT = 5.0
    settings.STOP_LOSS_PERCENT = 2.5
    settings.DATABASE_URL = "postgresql://test:test@localhost:5432/test_db"
    return settings


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return {
        'symbol': 'BTCUSDT',
        'current_price': 50000.0,
        'price_change_24h': 2.5,
        'volume_24h': 1000000000.0,
        'high_24h': 51000.0,
        'low_24h': 49000.0,
        'timestamp': datetime.utcnow()
    }


@pytest.fixture
def sample_indicators():
    """Sample technical indicators for testing."""
    return {
        'RSI_14': 55.0,
        'RSI_7': 58.0,
        'MACD': {'macd': 100.0, 'signal': 95.0, 'histogram': 5.0},
        'BB_upper': 51000.0,
        'BB_middle': 50000.0,
        'BB_lower': 49000.0,
        'ATR_14': 500.0,
        'Stochastic': {'k': 60.0, 'd': 55.0},
        'EMA_20': 49800.0,
        'EMA_50': 49500.0,
        'Volume_SMA_20': 950000000.0
    }


@pytest.fixture
def sample_position():
    """Sample position for testing."""
    from src.core.trading_engine import Position
    
    return Position(
        symbol='BTCUSDT',
        quantity=0.1,
        entry_price=50000.0,
        current_price=50000.0,
        unrealized_pnl=0.0,
        unrealized_pnl_percent=0.0,
        stop_loss=48000.0,
        take_profit=52000.0,
        entry_time=datetime.utcnow()
    )


@pytest.fixture
def sample_trade_history():
    """Sample trade history for testing."""
    from src.core.risk_manager import TradeRecord
    from src.config.constants import OrderSide
    
    trades = []
    for i in range(20):
        trade = TradeRecord(
            symbol='BTCUSDT',
            side=OrderSide.BUY,
            entry_price=50000.0,
            exit_price=50500.0 if i % 2 == 0 else 49500.0,
            quantity=0.1,
            entry_time=datetime.utcnow(),
            exit_time=datetime.utcnow(),
            pnl=50.0 if i % 2 == 0 else -50.0,
            pnl_percent=1.0 if i % 2 == 0 else -1.0,
            ai_confidence=0.7 + (i % 3) * 0.1
        )
        trades.append(trade)
    
    return trades


# Test database setup
@pytest.fixture(scope="session")
def test_database_url():
    """Test database URL."""
    return os.getenv('TEST_DATABASE_URL', 'postgresql://test:test@localhost:5432/test_db')


# Markers for different test categories
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "network: Tests requiring network access")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "database: Tests requiring database")
