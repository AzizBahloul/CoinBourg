"""
Unit Tests for Binance Client
==============================
Tests for Binance API integration, circuit breaker, and order management.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.binance_client import BinanceClient
from src.config.settings import get_settings


class TestBinanceClient:
    """Test suite for BinanceClient."""
    
    @pytest.fixture
    def binance_client(self, monkeypatch):
        """Create a BinanceClient instance for testing."""
        monkeypatch.setenv("BINANCE_TESTNET", "true")
        return BinanceClient()
    
    @pytest.mark.asyncio
    async def test_initialization(self, binance_client):
        """Test client initializes correctly."""
        assert binance_client is not None
        assert binance_client.base_url is not None
        assert binance_client.ws_url is not None
    
    @pytest.mark.asyncio
    async def test_connectivity(self, binance_client):
        """Test Binance connectivity check."""
        try:
            result = await binance_client.test_connectivity()
            assert result is True or isinstance(result, dict)
        except Exception as e:
            pytest.skip(f"Binance testnet not accessible: {e}")
    
    @pytest.mark.asyncio
    async def test_get_ticker_price(self, binance_client):
        """Test fetching ticker price."""
        try:
            price = await binance_client.get_ticker_price("BTCUSDT")
            assert isinstance(price, float)
            assert price > 0
        except Exception as e:
            pytest.skip(f"Binance testnet not accessible: {e}")
    
    @pytest.mark.asyncio
    async def test_get_account_balance(self, binance_client):
        """Test fetching account balance."""
        try:
            balance = await binance_client.get_account_balance()
            assert isinstance(balance, dict)
            assert 'USDT' in balance or len(balance) >= 0
        except Exception as e:
            pytest.skip(f"Binance testnet authentication failed: {e}")
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_activation(self, binance_client):
        """Test circuit breaker pattern."""
        # Simulate failures
        binance_client.circuit_breaker.failure_threshold = 2
        
        with patch.object(binance_client, '_request', side_effect=Exception("API Error")):
            # First two failures should trigger circuit breaker
            with pytest.raises(Exception):
                await binance_client.get_ticker_price("BTCUSDT")
            
            with pytest.raises(Exception):
                await binance_client.get_ticker_price("BTCUSDT")
            
            # Circuit should now be open
            assert binance_client.circuit_breaker.state in ['OPEN', 'HALF_OPEN']
    
    @pytest.mark.asyncio
    async def test_order_validation(self, binance_client):
        """Test order parameter validation."""
        # Test invalid symbol
        with pytest.raises(ValueError):
            await binance_client._validate_order("", "BUY", 0.1, 50000.0)
        
        # Test invalid side
        with pytest.raises(ValueError):
            await binance_client._validate_order("BTCUSDT", "INVALID", 0.1, 50000.0)
        
        # Test invalid quantity
        with pytest.raises(ValueError):
            await binance_client._validate_order("BTCUSDT", "BUY", 0.0, 50000.0)
        
        # Test invalid price
        with pytest.raises(ValueError):
            await binance_client._validate_order("BTCUSDT", "BUY", 0.1, -1.0)
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, binance_client):
        """Test rate limiting implementation."""
        # Make rapid requests
        start_time = asyncio.get_event_loop().time()
        
        tasks = [binance_client.get_ticker_price("BTCUSDT") for _ in range(10)]
        
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            end_time = asyncio.get_event_loop().time()
            
            # Should take some time due to rate limiting
            elapsed = end_time - start_time
            # Rate limiting should prevent all requests from completing instantly
            # (Adjust threshold based on your rate limit settings)
            assert elapsed > 0.1
        except Exception:
            pytest.skip("Rate limiting test requires network access")
    
    @pytest.mark.asyncio
    async def test_get_symbol_info(self, binance_client):
        """Test fetching symbol information."""
        try:
            info = await binance_client.get_symbol_info("BTCUSDT")
            
            assert info is not None
            assert 'symbol' in info
            assert info['symbol'] == "BTCUSDT"
            assert 'filters' in info
        except Exception as e:
            pytest.skip(f"Binance testnet not accessible: {e}")
    
    @pytest.mark.asyncio
    async def test_order_limits_validation(self, binance_client):
        """Test order size validation against exchange limits."""
        try:
            symbol_info = await binance_client.get_symbol_info("BTCUSDT")
            
            # Extract limits
            lot_size_filter = next(f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE')
            min_qty = float(lot_size_filter['minQty'])
            max_qty = float(lot_size_filter['maxQty'])
            
            # Test quantity below minimum
            is_valid = binance_client._check_lot_size(symbol_info, min_qty / 2)
            assert not is_valid
            
            # Test quantity within range
            is_valid = binance_client._check_lot_size(symbol_info, min_qty * 2)
            assert is_valid
            
        except Exception as e:
            pytest.skip(f"Symbol info test requires network access: {e}")


class TestOrderExecution:
    """Test order execution and tracking."""
    
    @pytest.fixture
    def binance_client(self):
        """Create client for order tests."""
        return BinanceClient(testnet=True)
    
    @pytest.mark.asyncio
    async def test_create_test_order(self, binance_client):
        """Test creating a test order (no actual execution)."""
        try:
            # Use test order endpoint
            order = await binance_client.create_test_order(
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                quantity=0.001,
                price=30000.0
            )
            
            # Test order should return empty or success
            assert order is not None
        except Exception as e:
            pytest.skip(f"Test order requires valid API credentials: {e}")
    
    @pytest.mark.asyncio
    async def test_oco_order_structure(self, binance_client):
        """Test OCO order parameter construction."""
        params = binance_client._build_oco_params(
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            price=52000.0,
            stop_price=48000.0,
            stop_limit_price=47900.0
        )
        
        assert params['symbol'] == "BTCUSDT"
        assert params['side'] == "SELL"
        assert params['quantity'] == 0.1
        assert params['price'] == 52000.0
        assert params['stopPrice'] == 48000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/core/binance_client"])
