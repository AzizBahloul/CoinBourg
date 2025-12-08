"""
Tests for the Risk Manager module
"""

import pytest
from datetime import datetime, timedelta
from src.core.risk_manager import RiskManager, Position, RiskState
from src.config.constants import RiskLevel, TradeAction as OrderSide


class TestRiskManager:
    """Test suite for RiskManager class"""
    
    @pytest.fixture
    def risk_manager(self):
        """Create a fresh risk manager for each test"""
        return RiskManager(RiskLevel.CONSERVATIVE)
    
    @pytest.fixture
    def moderate_risk_manager(self):
        """Create a moderate risk manager"""
        return RiskManager(RiskLevel.MODERATE)
    
    def test_initialization(self, risk_manager):
        """Test risk manager initializes correctly"""
        assert risk_manager.risk_level == RiskLevel.CONSERVATIVE
        assert risk_manager.config["max_position_size_percent"] == 2.0
        assert risk_manager.config["stop_loss_percent"] == 1.5
        assert risk_manager.config["max_daily_trades"] == 5
    
    def test_set_risk_level(self, risk_manager):
        """Test changing risk level"""
        risk_manager.set_risk_level(RiskLevel.AGGRESSIVE)
        assert risk_manager.risk_level == RiskLevel.AGGRESSIVE
        assert risk_manager.config["max_position_size_percent"] == 10.0
    
    def test_update_portfolio_state(self, risk_manager):
        """Test portfolio state updates"""
        risk_manager.update_portfolio_state(10000.0, 5000.0)
        assert risk_manager.state.total_portfolio_value == 10000.0
        assert risk_manager.state.available_balance == 5000.0
        assert risk_manager.state.peak_portfolio_value == 10000.0
    
    def test_drawdown_calculation(self, risk_manager):
        """Test drawdown calculation"""
        # Set peak
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        assert risk_manager.state.current_drawdown == 0.0
        
        # Simulate loss
        risk_manager.update_portfolio_state(9000.0, 9000.0)
        assert risk_manager.state.current_drawdown == 10.0  # 10% drawdown
    
    def test_can_open_trade_success(self, risk_manager):
        """Test trade can be opened with valid conditions"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.75)
        assert can_trade is True
        assert reason == "Trade allowed"
    
    def test_can_open_trade_low_confidence(self, risk_manager):
        """Test trade blocked with low AI confidence"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.5)  # Below 0.7 threshold
        assert can_trade is False
        assert "confidence" in reason.lower()
    
    def test_can_open_trade_daily_limit(self, risk_manager):
        """Test daily trade limit enforcement"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        risk_manager.state.daily_trades = 5  # Max for conservative
        
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.8)
        assert can_trade is False
        assert "daily trade limit" in reason.lower()
    
    def test_can_open_trade_max_drawdown(self, risk_manager):
        """Test max drawdown blocks trading"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        risk_manager.update_portfolio_state(9400.0, 9400.0)  # 6% drawdown > 5% limit
        
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.8)
        assert can_trade is False
        assert "drawdown" in reason.lower()
    
    def test_can_open_trade_consecutive_losses(self, risk_manager):
        """Test consecutive losses block trading"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        risk_manager.state.consecutive_losses = 3  # Max for conservative
        
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.8)
        assert can_trade is False
        assert "consecutive losses" in reason.lower()
    
    def test_can_open_trade_existing_position(self, risk_manager):
        """Test can't open duplicate position"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49000.0, 52000.0
        )
        
        can_trade, reason = risk_manager.can_open_trade("BTCUSDT", 0.8)
        assert can_trade is False
        assert "already exists" in reason.lower()
    
    def test_calculate_position_size(self, risk_manager):
        """Test position size calculation"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        
        # High confidence = larger position
        size_high = risk_manager.calculate_position_size("BTCUSDT", 50000.0, 1.0)
        size_low = risk_manager.calculate_position_size("BTCUSDT", 50000.0, 0.7)
        
        assert size_high > size_low
        assert size_high > 0
    
    def test_calculate_position_size_during_drawdown(self, risk_manager):
        """Test position size reduced during drawdown"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        size_normal = risk_manager.calculate_position_size("BTCUSDT", 50000.0, 0.8)
        
        # Simulate drawdown
        risk_manager.update_portfolio_state(9500.0, 9500.0)
        size_drawdown = risk_manager.calculate_position_size("BTCUSDT", 50000.0, 0.8)
        
        assert size_drawdown < size_normal
    
    def test_calculate_stop_loss_buy(self, risk_manager):
        """Test stop loss calculation for buy orders"""
        stop_loss = risk_manager.calculate_stop_loss(50000.0, OrderSide.BUY)
        expected = 50000.0 * (1 - 1.5 / 100)  # 1.5% for conservative
        assert abs(stop_loss - expected) < 0.01
    
    def test_calculate_stop_loss_sell(self, risk_manager):
        """Test stop loss calculation for sell orders"""
        stop_loss = risk_manager.calculate_stop_loss(50000.0, OrderSide.SELL)
        expected = 50000.0 * (1 + 1.5 / 100)
        assert abs(stop_loss - expected) < 0.01
    
    def test_calculate_take_profit_buy(self, risk_manager):
        """Test take profit calculation for buy orders"""
        take_profit = risk_manager.calculate_take_profit(50000.0, OrderSide.BUY)
        expected = 50000.0 * (1 + 3.0 / 100)  # 3% for conservative
        assert abs(take_profit - expected) < 0.01
    
    def test_open_position(self, risk_manager):
        """Test opening a position"""
        position = risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        
        assert position.symbol == "BTCUSDT"
        assert position.entry_price == 50000.0
        assert risk_manager.has_position("BTCUSDT")
        assert risk_manager.state.daily_trades == 1
    
    def test_update_position_price(self, risk_manager):
        """Test updating position price"""
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        
        position = risk_manager.update_position_price("BTCUSDT", 51000.0)
        assert position.current_price == 51000.0
        assert position.unrealized_pnl == 100.0  # (51000 - 50000) * 0.1
    
    def test_close_position_profit(self, risk_manager):
        """Test closing a profitable position"""
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        
        trade = risk_manager.close_position("BTCUSDT", 51000.0, 0.8)
        
        assert trade is not None
        assert trade.pnl == 100.0
        assert trade.pnl_percent == 2.0
        assert not risk_manager.has_position("BTCUSDT")
        assert risk_manager.state.consecutive_losses == 0
    
    def test_close_position_loss(self, risk_manager):
        """Test closing a losing position"""
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        
        trade = risk_manager.close_position("BTCUSDT", 49500.0, 0.8)
        
        assert trade.pnl == -50.0
        assert risk_manager.state.consecutive_losses == 1
    
    def test_check_positions_for_exit_stop_loss(self, risk_manager):
        """Test stop loss trigger detection"""
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        risk_manager.update_position_price("BTCUSDT", 49000.0)  # Below stop loss
        
        exits = risk_manager.check_positions_for_exit()
        assert len(exits) == 1
        assert exits[0] == ("BTCUSDT", "stop_loss")
    
    def test_check_positions_for_exit_take_profit(self, risk_manager):
        """Test take profit trigger detection"""
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        risk_manager.update_position_price("BTCUSDT", 52000.0)  # Above take profit
        
        exits = risk_manager.check_positions_for_exit()
        assert len(exits) == 1
        assert exits[0] == ("BTCUSDT", "take_profit")
    
    def test_get_risk_metrics(self, risk_manager):
        """Test risk metrics calculation"""
        risk_manager.update_portfolio_state(10000.0, 10000.0)
        risk_manager.open_position(
            "BTCUSDT", OrderSide.BUY, 50000.0, 0.1, 49250.0, 51500.0
        )
        risk_manager.close_position("BTCUSDT", 51000.0, 0.8)
        
        metrics = risk_manager.get_risk_metrics()
        
        assert metrics["risk_level"] == "CONSERVATIVE"
        assert metrics["total_trades"] == 1
        assert metrics["winning_trades"] == 1
        assert metrics["win_rate"] == 100.0
        assert metrics["total_pnl"] == 100.0


class TestPosition:
    """Test suite for Position dataclass"""
    
    @pytest.fixture
    def long_position(self):
        """Create a long position"""
        return Position(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=50000.0,
            quantity=0.1,
            entry_time=datetime.utcnow(),
            stop_loss=49250.0,
            take_profit=51500.0,
            current_price=50500.0
        )
    
    @pytest.fixture
    def short_position(self):
        """Create a short position"""
        return Position(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            entry_price=50000.0,
            quantity=0.1,
            entry_time=datetime.utcnow(),
            stop_loss=50750.0,
            take_profit=48500.0,
            current_price=49500.0
        )
    
    def test_unrealized_pnl_long_profit(self, long_position):
        """Test P&L calculation for profitable long"""
        assert long_position.unrealized_pnl == 50.0  # (50500 - 50000) * 0.1
    
    def test_unrealized_pnl_percent_long(self, long_position):
        """Test P&L percent calculation for long"""
        assert long_position.unrealized_pnl_percent == 1.0  # 1% profit
    
    def test_unrealized_pnl_short_profit(self, short_position):
        """Test P&L calculation for profitable short"""
        assert short_position.unrealized_pnl == 50.0  # (50000 - 49500) * 0.1
    
    def test_position_value(self, long_position):
        """Test position value calculation"""
        assert long_position.position_value == 5050.0  # 50500 * 0.1
    
    def test_should_stop_loss_long(self, long_position):
        """Test stop loss trigger for long position"""
        assert long_position.should_stop_loss() is False
        long_position.current_price = 49000.0
        assert long_position.should_stop_loss() is True
    
    def test_should_take_profit_long(self, long_position):
        """Test take profit trigger for long position"""
        assert long_position.should_take_profit() is False
        long_position.current_price = 52000.0
        assert long_position.should_take_profit() is True
    
    def test_should_stop_loss_short(self, short_position):
        """Test stop loss trigger for short position"""
        assert short_position.should_stop_loss() is False
        short_position.current_price = 51000.0
        assert short_position.should_stop_loss() is True
    
    def test_should_take_profit_short(self, short_position):
        """Test take profit trigger for short position"""
        assert short_position.should_take_profit() is False
        short_position.current_price = 48000.0
        assert short_position.should_take_profit() is True


class TestRiskLevelConfigs:
    """Test different risk level configurations"""
    
    def test_conservative_config(self):
        """Test conservative risk settings"""
        rm = RiskManager(RiskLevel.CONSERVATIVE)
        assert rm.config["max_position_size_percent"] == 2.0
        assert rm.config["stop_loss_percent"] == 1.5
        assert rm.config["max_daily_trades"] == 5
        assert rm.config["min_confidence_threshold"] == 0.7
    
    def test_moderate_config(self):
        """Test moderate risk settings"""
        rm = RiskManager(RiskLevel.MODERATE)
        assert rm.config["max_position_size_percent"] == 5.0
        assert rm.config["stop_loss_percent"] == 2.5
        assert rm.config["max_daily_trades"] == 10
        assert rm.config["min_confidence_threshold"] == 0.6
    
    def test_aggressive_config(self):
        """Test aggressive risk settings"""
        rm = RiskManager(RiskLevel.AGGRESSIVE)
        assert rm.config["max_position_size_percent"] == 10.0
        assert rm.config["stop_loss_percent"] == 4.0
        assert rm.config["max_daily_trades"] == 20
        assert rm.config["min_confidence_threshold"] == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
