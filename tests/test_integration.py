"""
Professional Integration Tests for CoinBourg Trading Bot
=========================================================
These tests verify the actual functionality with real API connections.
Uses testnet for safe testing without real money.
"""

import os
import sys
import asyncio
import pytest
from datetime import datetime
from typing import Dict, Any

# Ensure we're using the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment
from dotenv import load_dotenv
load_dotenv()


class TestBinanceIntegration:
    """Integration tests for Binance API connectivity."""
    
    @pytest.fixture
    def binance_client(self):
        """Create Binance client with real credentials."""
        from src.core.binance_client import BinanceClient
        return BinanceClient()
    
    @pytest.mark.asyncio
    async def test_binance_connection(self, binance_client):
        """Test that we can connect to Binance API."""
        try:
            # Test server time endpoint (no auth required)
            server_time = await binance_client.get_server_time()
            assert server_time is not None
            assert isinstance(server_time, int)
            print(f"✓ Binance server time: {datetime.fromtimestamp(server_time/1000)}")
        finally:
            await binance_client.close()
    
    @pytest.mark.asyncio
    async def test_binance_price_fetch(self, binance_client):
        """Test fetching current price for BTCUSDT."""
        try:
            price = await binance_client.get_price("BTCUSDT")
            assert price is not None
            assert isinstance(price, float)
            assert price > 0
            print(f"✓ BTCUSDT price: ${price:,.2f}")
        finally:
            await binance_client.close()
    
    @pytest.mark.asyncio
    async def test_binance_account_info(self, binance_client):
        """Test fetching account information (requires API key with Spot permissions)."""
        try:
            account = await binance_client.get_account_info()
            assert account is not None
            assert "balances" in account or "makerCommission" in account
            print(f"✓ Account info retrieved successfully")
        except Exception as e:
            # API key may not have trading permissions enabled
            if "-2015" in str(e) or "permissions" in str(e).lower():
                pytest.skip("Binance API key doesn't have trading permissions (enable 'Spot & Margin Trading')")
            raise
        finally:
            await binance_client.close()
    
    @pytest.mark.asyncio
    async def test_binance_klines(self, binance_client):
        """Test fetching historical klines/candlestick data."""
        try:
            klines = await binance_client.get_klines("BTCUSDT", "1h", limit=10)
            assert klines is not None
            assert len(klines) > 0
            # Kline format: [open_time, open, high, low, close, volume, ...]
            assert len(klines[0]) >= 6
            print(f"✓ Retrieved {len(klines)} klines for BTCUSDT")
        finally:
            await binance_client.close()
    
    @pytest.mark.asyncio
    async def test_binance_order_book(self, binance_client):
        """Test fetching order book depth."""
        try:
            order_book = await binance_client.get_order_book("BTCUSDT", limit=5)
            assert order_book is not None
            assert "bids" in order_book
            assert "asks" in order_book
            print(f"✓ Order book: {len(order_book['bids'])} bids, {len(order_book['asks'])} asks")
        finally:
            await binance_client.close()
    
    @pytest.mark.asyncio
    async def test_binance_24hr_ticker(self, binance_client):
        """Test fetching 24hr ticker statistics."""
        try:
            ticker = await binance_client.get_24hr_ticker("BTCUSDT")
            assert ticker is not None
            assert "priceChangePercent" in ticker
            assert "volume" in ticker
            print(f"✓ 24hr change: {ticker['priceChangePercent']}%, Volume: {ticker['volume']}")
        finally:
            await binance_client.close()


class TestDeepSeekIntegration:
    """Integration tests for DeepSeek AI API connectivity."""
    
    @pytest.fixture
    def deepseek_client(self):
        """Create DeepSeek client with real credentials."""
        from src.core.deepseek_client import DeepSeekClient
        return DeepSeekClient()
    
    @pytest.mark.asyncio
    async def test_deepseek_connection(self, deepseek_client):
        """Test that we can connect to DeepSeek API."""
        try:
            # Simple test prompt
            response = await deepseek_client.chat(
                "Say 'Hello, CoinBourg!' and nothing else."
            )
            assert response is not None
            assert len(response) > 0
            print(f"✓ DeepSeek response: {response}")
        finally:
            await deepseek_client.close()
    
    @pytest.mark.asyncio
    async def test_deepseek_market_analysis(self, deepseek_client):
        """Test AI market analysis with sample data."""
        try:
            # Full market data for analyze_market method
            analysis = await deepseek_client.analyze_market(
                symbol="BTCUSDT",
                current_price=98000.0,
                price_change_24h=2.5,
                volume_24h=50000000000,
                high_24h=99500.0,
                low_24h=96000.0,
                technical_indicators={
                    "RSI": 55,
                    "MACD": {"macd": 150, "signal": 120, "histogram": 30},
                    "EMA_21": 97500.0,
                }
            )
            assert analysis is not None
            assert "sentiment" in analysis or "action" in analysis
            print(f"✓ Market analysis completed: {analysis.get('action', 'N/A')}")
        finally:
            await deepseek_client.close()


class TestRiskManager:
    """Unit tests for Risk Manager - no external dependencies."""
    
    @pytest.fixture
    def risk_manager(self):
        """Create a fresh risk manager for each test."""
        from src.core.risk_manager import RiskManager
        from src.config.constants import RiskLevel
        return RiskManager(RiskLevel.CONSERVATIVE)
    
    def test_initialization(self, risk_manager):
        """Test risk manager initializes correctly."""
        from src.config.constants import RiskLevel
        assert risk_manager.risk_level == RiskLevel.CONSERVATIVE
        assert risk_manager.config["max_position_size_percent"] == 2.0
        assert risk_manager.config["stop_loss_percent"] == 1.5
        assert risk_manager.config["max_daily_trades"] == 5
        print("✓ Risk manager initialized with conservative settings")
    
    def test_risk_level_change(self, risk_manager):
        """Test changing risk level dynamically."""
        from src.config.constants import RiskLevel
        risk_manager.set_risk_level(RiskLevel.AGGRESSIVE)
        assert risk_manager.risk_level == RiskLevel.AGGRESSIVE
        assert risk_manager.config["max_position_size_percent"] == 10.0
        print("✓ Risk level changed to aggressive")
    
    def test_portfolio_state_tracking(self, risk_manager):
        """Test portfolio state updates."""
        risk_manager.update_portfolio_state(10000.0, 5000.0)
        assert risk_manager.state.total_portfolio_value == 10000.0
        assert risk_manager.state.available_balance == 5000.0
        assert risk_manager.state.peak_portfolio_value == 10000.0
        print("✓ Portfolio state tracked correctly")
    
    def test_drawdown_calculation(self, risk_manager):
        """Test drawdown calculation accuracy."""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        assert risk_manager.state.current_drawdown == 0.0
        
        risk_manager.update_portfolio_state(9000.0, 9000.0)
        assert risk_manager.state.current_drawdown == 10.0  # 10% drawdown
        print("✓ Drawdown calculated correctly: 10%")
    
    def test_trade_approval_success(self, risk_manager):
        """Test trade can be approved with valid conditions."""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.75)
        assert can_trade is True
        assert reason == "Trade allowed"
        print("✓ Trade approved with high confidence")
    
    def test_trade_blocked_low_confidence(self, risk_manager):
        """Test trade blocked with low AI confidence."""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.5)
        assert can_trade is False
        assert "confidence" in reason.lower()
        print("✓ Trade blocked due to low confidence")
    
    def test_trade_blocked_daily_limit(self, risk_manager):
        """Test daily trade limit enforcement."""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        risk_manager.state.daily_trades = 5
        
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.8)
        assert can_trade is False
        assert "daily trade limit" in reason.lower()
        print("✓ Trade blocked due to daily limit")
    
    def test_trade_blocked_max_drawdown(self, risk_manager):
        """Test max drawdown protection."""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        risk_manager.update_portfolio_state(9400.0, 9400.0)  # 6% drawdown > 5% limit
        
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.8)
        assert can_trade is False
        assert "drawdown" in reason.lower()
        print("✓ Trade blocked due to max drawdown")
    
    def test_position_sizing(self, risk_manager):
        """Test position size calculation."""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        
        size_high = risk_manager.calculate_position_size("BTCUSDT", 50000.0, 1.0)
        size_low = risk_manager.calculate_position_size("BTCUSDT", 50000.0, 0.7)
        
        assert size_high > size_low
        assert size_high > 0
        print(f"✓ Position sizing: High conf={size_high:.6f}, Low conf={size_low:.6f}")
    
    def test_stop_loss_calculation(self, risk_manager):
        """Test stop-loss price calculation."""
        from src.config.constants import TradeAction as OrderSide
        
        stop_loss_buy = risk_manager.calculate_stop_loss(50000.0, OrderSide.BUY)
        expected_buy = 50000.0 * (1 - 1.5 / 100)  # 1.5% for conservative
        assert abs(stop_loss_buy - expected_buy) < 0.01
        
        stop_loss_sell = risk_manager.calculate_stop_loss(50000.0, OrderSide.SELL)
        expected_sell = 50000.0 * (1 + 1.5 / 100)
        assert abs(stop_loss_sell - expected_sell) < 0.01
        print(f"✓ Stop-loss: BUY@${stop_loss_buy:.2f}, SELL@${stop_loss_sell:.2f}")
    
    def test_take_profit_calculation(self, risk_manager):
        """Test take-profit price calculation."""
        from src.config.constants import TradeAction as OrderSide
        
        take_profit_buy = risk_manager.calculate_take_profit(50000.0, OrderSide.BUY)
        expected_buy = 50000.0 * (1 + 3.0 / 100)  # 3% for conservative
        assert abs(take_profit_buy - expected_buy) < 0.01
        print(f"✓ Take-profit calculated: ${take_profit_buy:.2f}")
    
    def test_position_pnl_tracking(self, risk_manager):
        """Test position P&L tracking."""
        from src.config.constants import TradeAction as OrderSide
        
        position = risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        
        position = risk_manager.update_position_price("BTCUSDT", 51000.0)
        assert position.current_price == 51000.0
        assert position.unrealized_pnl == 100.0  # (51000 - 50000) * 0.1
        print(f"✓ Position P&L: ${position.unrealized_pnl:.2f}")
    
    def test_close_profitable_position(self, risk_manager):
        """Test closing a profitable position."""
        from src.config.constants import TradeAction as OrderSide
        
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        
        trade = risk_manager.close_position("BTCUSDT", 51000.0, 0.8)
        
        assert trade is not None
        assert trade.pnl == 100.0
        assert trade.pnl_percent == 2.0
        assert not risk_manager.has_position("BTCUSDT")
        print(f"✓ Closed profitable position: PnL=${trade.pnl:.2f} ({trade.pnl_percent:.1f}%)")


class TestConfigurationLoading:
    """Test configuration loading from environment."""
    
    def test_settings_load(self):
        """Test that settings load correctly from environment."""
        from src.config.settings import get_settings
        
        settings = get_settings()
        
        # Check required settings are present
        assert settings.DEEPSEEK_API_KEY is not None
        assert len(settings.DEEPSEEK_API_KEY) > 10
        
        assert settings.BINANCE_API_KEY is not None
        assert len(settings.BINANCE_API_KEY) > 10
        
        assert settings.BINANCE_API_SECRET is not None
        assert len(settings.BINANCE_API_SECRET) > 10
        
        print("✓ All API keys loaded successfully")
        print(f"  DeepSeek Key: {settings.DEEPSEEK_API_KEY[:8]}...")
        print(f"  Binance Key: {settings.BINANCE_API_KEY[:8]}...")
    
    def test_risk_settings_defaults(self):
        """Test risk settings default values."""
        from src.config.settings import get_settings
        
        settings = get_settings()
        
        assert settings.RISK_LEVEL in ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]
        assert 0 < settings.MAX_POSITION_SIZE_PERCENT <= 100
        assert settings.MAX_DAILY_TRADES > 0
        print(f"✓ Risk settings: {settings.RISK_LEVEL}, Max Position: {settings.MAX_POSITION_SIZE_PERCENT}%")
    
    def test_trading_pairs_configured(self):
        """Test trading pairs are configured."""
        from src.config.settings import get_settings
        
        settings = get_settings()
        
        assert len(settings.TRADING_PAIRS) > 0
        assert "BTCUSDT" in settings.TRADING_PAIRS
        print(f"✓ Trading pairs configured: {settings.TRADING_PAIRS}")


class TestHelperUtilities:
    """Test utility helper functions."""
    
    def test_rsi_calculation(self):
        """Test RSI calculation."""
        from src.utils.helpers import calculate_rsi
        
        # Sample prices with upward trend
        prices = [100, 101, 102, 101, 103, 104, 103, 105, 106, 105, 
                  107, 108, 107, 109, 110, 109, 111, 112]
        
        rsi = calculate_rsi(prices, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100
        print(f"✓ RSI calculated: {rsi:.2f}")
    
    def test_moving_average(self):
        """Test moving average calculation."""
        from src.utils.helpers import moving_average
        
        data = [10, 12, 14, 16, 18, 20, 22, 24, 26, 28]
        ma = moving_average(data, 5)
        
        assert ma is not None
        assert ma == 24.0  # Average of last 5: (20+22+24+26+28)/5
        print(f"✓ Moving average: {ma}")
    
    def test_percentage_change(self):
        """Test percentage change calculation."""
        from src.utils.helpers import calculate_percentage_change
        
        change = calculate_percentage_change(100, 110)
        assert change == 10.0
        
        change_neg = calculate_percentage_change(100, 90)
        assert change_neg == -10.0
        print("✓ Percentage change calculated correctly")
    
    def test_price_rounding(self):
        """Test price rounding to tick size."""
        from src.utils.helpers import round_price
        
        price = round_price(50123.456789, tick_size=0.01)
        assert price == 50123.45
        print(f"✓ Price rounded: {price}")
    
    def test_quantity_rounding(self):
        """Test quantity rounding to step size."""
        from src.utils.helpers import round_quantity
        
        qty = round_quantity(0.123456789, step_size=0.00001)
        assert qty == 0.12345
        print(f"✓ Quantity rounded: {qty}")


class TestValidators:
    """Test input validators."""
    
    def test_symbol_validation(self):
        """Test symbol validation."""
        from src.utils.validators import validate_symbol
        
        # Valid symbols
        is_valid, _ = validate_symbol("BTCUSDT")
        assert is_valid is True
        
        is_valid, _ = validate_symbol("ETHUSDT")
        assert is_valid is True
        
        # Invalid symbols
        is_valid, error = validate_symbol("")
        assert is_valid is False
        
        is_valid, error = validate_symbol("INVALID")
        assert is_valid is False
        print("✓ Symbol validation working correctly")
    
    def test_quantity_validation(self):
        """Test quantity validation."""
        from src.utils.validators import validate_quantity
        
        # Test with proper step-size aligned quantity
        is_valid, _ = validate_quantity(0.1)
        assert is_valid is True
        
        is_valid, error = validate_quantity(-1.0)
        assert is_valid is False
        print("✓ Quantity validation working correctly")
    
    def test_risk_level_validation(self):
        """Test risk level validation."""
        from src.utils.validators import validate_risk_level
        
        is_valid, _ = validate_risk_level("CONSERVATIVE")
        assert is_valid is True
        
        is_valid, _ = validate_risk_level("MODERATE")
        assert is_valid is True
        
        is_valid, error = validate_risk_level("INVALID")
        assert is_valid is False
        print("✓ Risk level validation working correctly")


# Run all tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
