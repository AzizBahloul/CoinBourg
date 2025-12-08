"""
Tests for the FastAPI endpoints
Uses mocking to avoid real API connections
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockTradingEngine:
    """Mock trading engine for testing."""
    
    def __init__(self):
        self.is_running = False
        self.positions = {}
        self.trades = []
        self.metrics = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "current_value": 10000.0,
            "peak_value": 10000.0,
        }
        self.settings = MagicMock()
        self.settings.RISK_LEVEL = "CONSERVATIVE"
        self.max_position_size_percent = 5.0
        self.stop_loss_percent = 2.0
        self.take_profit_percent = 4.0
        self.max_daily_trades = 10
        self.max_drawdown_percent = 10.0
        self.min_confidence_score = 0.65
        self.daily_trades_count = 0
        
        # Mock binance and deepseek
        self.binance = MagicMock()
        self.binance.test_connectivity = AsyncMock(return_value=True)
        self.binance.get_balances = AsyncMock(return_value={"USDT": {"free": 10000, "locked": 0}})
        self.binance.get_portfolio_value = AsyncMock(return_value=10000.0)
        
        self.deepseek = MagicMock()
        self.deepseek.test_connection = AsyncMock(return_value=True)
    
    async def initialize(self):
        pass
    
    async def shutdown(self):
        pass
    
    async def run(self):
        self.is_running = True
    
    async def analyze_and_decide(self, symbol):
        return {
            "sentiment": "NEUTRAL",
            "action": "HOLD",
            "confidence": 0.5,
            "stop_loss": 50000.0,
            "take_profit": 55000.0,
            "reasoning": "Test analysis",
            "timestamp": "2025-12-08T00:00:00Z"
        }
    
    async def get_market_data(self, symbol):
        return {
            "symbol": symbol,
            "current_price": 50000.0,
            "price_change_24h": 1.5,
            "volume_24h": 1000000000,
            "high_24h": 51000.0,
            "low_24h": 49000.0,
        }
    
    def get_status(self):
        return {
            "is_running": self.is_running,
            "portfolio_value": self.metrics['current_value'],
            "total_pnl": self.metrics['total_pnl'],
            "total_trades": self.metrics['total_trades'],
            "winning_trades": self.metrics['winning_trades'],
            "losing_trades": self.metrics['losing_trades'],
            "win_rate": 0,
            "open_positions": len(self.positions),
            "positions": {},
            "daily_trades": self.daily_trades_count,
            "max_daily_trades": self.max_daily_trades,
            "risk_level": self.settings.RISK_LEVEL
        }


@pytest.fixture
def mock_trading_engine():
    """Create mock trading engine."""
    return MockTradingEngine()


@pytest.fixture
def client(mock_trading_engine):
    """Create test client with mocked trading engine."""
    with patch.dict(os.environ, {
        "DEEPSEEK_API_KEY": "test_key",
        "BINANCE_API_KEY": "test_key",
        "BINANCE_API_SECRET": "test_secret",
        "BINANCE_TESTNET": "true",
        "DEBUG": "true",
        "ENVIRONMENT": "development"
    }):
        # Import after patching environment
        from src.api.main import app, get_engine
        
        # Override the dependency
        async def override_get_engine():
            return mock_trading_engine
        
        app.dependency_overrides[get_engine] = override_get_engine
        
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
        
        # Clean up
        app.dependency_overrides.clear()


class TestRootEndpoint:
    """Test root endpoint."""
    
    def test_root(self, client):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "status" in data


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_check(self, client):
        """Test health endpoint returns OK."""
        response = client.get("/health")
        # Health check may return degraded if connections fail
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "timestamp" in data


class TestStatusEndpoint:
    """Test status endpoint."""
    
    def test_status_endpoint(self, client):
        """Test status endpoint returns expected fields."""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields exist
        assert "is_running" in data
        assert "risk_level" in data
        assert "portfolio_value" in data
        assert "total_trades" in data


class TestRiskSettingsEndpoint:
    """Test risk settings endpoint."""
    
    def test_get_risk_settings(self, client):
        """Test getting risk settings."""
        response = client.get("/risk-settings")
        assert response.status_code == 200
        data = response.json()
        
        assert "risk_level" in data
        assert "max_position_size_percent" in data
        assert "available_presets" in data
    
    def test_update_risk_settings_valid(self, client):
        """Test updating risk settings with valid data."""
        response = client.post(
            "/risk-settings",
            json={"risk_level": "MODERATE"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data["risk_level"] == "MODERATE"
    
    def test_update_risk_settings_invalid(self, client):
        """Test updating risk settings with invalid data."""
        response = client.post(
            "/risk-settings",
            json={"risk_level": "INVALID_LEVEL"}
        )
        assert response.status_code in [400, 422]  # Validation error


class TestTradesEndpoint:
    """Test trades endpoint."""
    
    def test_get_trades(self, client):
        """Test getting trades list."""
        response = client.get("/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_trades_with_limit(self, client):
        """Test getting trades with limit parameter."""
        response = client.get("/trades?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestPositionsEndpoint:
    """Test positions endpoint."""
    
    def test_get_positions(self, client):
        """Test getting positions."""
        response = client.get("/positions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


class TestAnalyzeEndpoint:
    """Test analyze endpoint."""
    
    def test_analyze_valid_symbol(self, client):
        """Test analyzing a valid symbol."""
        response = client.post(
            "/analyze",
            json={"symbol": "BTCUSDT"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sentiment" in data
        assert "action" in data
        assert "confidence" in data
    
    def test_analyze_invalid_symbol(self, client):
        """Test analyzing with invalid symbol."""
        response = client.post(
            "/analyze",
            json={"symbol": ""}
        )
        assert response.status_code == 422  # Validation error


class TestMetricsEndpoint:
    """Test metrics endpoint."""
    
    def test_get_metrics(self, client):
        """Test getting metrics."""
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_trades" in data
        assert "win_rate" in data
        assert "portfolio_value" in data


class TestControlEndpoints:
    """Test start/stop control endpoints."""
    
    def test_start_endpoint(self, client):
        """Test starting the bot."""
        response = client.post("/start")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
    
    def test_stop_endpoint(self, client):
        """Test stopping the bot."""
        response = client.post("/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


class TestInputValidation:
    """Test input validation on endpoints."""
    
    def test_analyze_symbol_validation(self, client):
        """Test symbol validation on analyze endpoint."""
        # Too short
        response = client.post(
            "/analyze",
            json={"symbol": "BTC"}
        )
        assert response.status_code == 422
    
    def test_trade_action_validation(self, client):
        """Test action validation on trade endpoint."""
        response = client.post(
            "/trade",
            json={
                "symbol": "BTCUSDT",
                "action": "INVALID",
                "quantity": 0.1
            }
        )
        assert response.status_code == 422


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
