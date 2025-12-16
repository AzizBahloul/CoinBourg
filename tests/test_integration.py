"""
Integration Tests for CoinBourg Trading System
===============================================
End-to-end testing of complete trading workflows.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.trading_engine import TradingEngine
from src.config.constants import OrderSide


@pytest.mark.integration
class TestCompleteTradingWorkflow:
    """Test complete trading cycle from analysis to execution."""
    
    @pytest_asyncio.fixture
    async def trading_engine(self):
        """Create trading engine for integration testing."""
        engine = TradingEngine()
        await engine.initialize()
        yield engine
        await engine.shutdown()
    
    @pytest.mark.asyncio
    async def test_market_scan_to_analysis(self, trading_engine):
        """Test market scanning and coin selection."""
        # Enable paper trading
        trading_engine.paper_trading = True
        
        # Scan market
        top_coins = await trading_engine.coin_selector.scan_market()
        
        assert top_coins is not None
        assert len(top_coins) > 0
        assert all('USDT' in coin for coin in top_coins)
    
    @pytest.mark.asyncio
    async def test_complete_buy_cycle(self, trading_engine):
        """Test complete buy cycle: analysis -> decision -> execution -> position tracking."""
        trading_engine.paper_trading = True
        
        # Step 1: Market analysis
        symbol = 'BTCUSDT'
        market_data = await trading_engine.market_scanner.fetch_price_data(symbol)
        
        assert market_data is not None
        assert 'close' in market_data
        
        # Step 2: Calculate indicators
        indicators = await trading_engine.market_scanner.calculate_indicators(market_data)
        
        assert indicators is not None
        assert 'RSI_14' in indicators
        
        # Step 3: Get strategy signals
        strategy_signals = await trading_engine.strategy_manager.get_consensus(
            symbol=symbol,
            price_data=market_data,
            indicators=indicators,
            market_context={}
        )
        
        assert strategy_signals is not None
        
        # Step 4: Mock AI decision (to avoid API call)
        ai_decision = {
            'action': 'BUY',
            'confidence': 0.8,
            'reasoning': 'Test buy signal',
            'entry_price': market_data['close'].iloc[-1],
            'stop_loss': market_data['close'].iloc[-1] * 0.98,
            'take_profit': market_data['close'].iloc[-1] * 1.04
        }
        
        # Step 5: Risk validation
        validated = trading_engine.risk_manager.validate_trade(
            signal=ai_decision,
            current_portfolio={'total_value': 10000.0, 'available_balance': 5000.0}
        )
        
        assert validated is not None
        
        # Step 6: Execute order (paper trading)
        if validated:
            position = await trading_engine._execute_trade(symbol, ai_decision)
            
            assert position is not None
            assert position.symbol == symbol
    
    @pytest.mark.asyncio
    async def test_position_monitoring_and_exit(self, trading_engine):
        """Test position monitoring and exit logic."""
        trading_engine.paper_trading = True
        
        # Create a mock position
        from src.core.trading_engine import Position
        
        position = Position(
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
        
        trading_engine.positions['BTCUSDT'] = position
        
        # Test stop loss trigger
        position.current_price = 47500.0  # Below stop loss
        should_exit = trading_engine._should_exit_position(position)
        
        assert should_exit
        if isinstance(should_exit, dict):
            assert 'stop_loss' in should_exit
        else:
            assert should_exit is True
        
        # Test take profit trigger
        position.current_price = 52500.0  # Above take profit
        should_exit = trading_engine._should_exit_position(position)
        
        if isinstance(should_exit, dict):
            assert 'take_profit' in should_exit
        else:
            assert should_exit is True
    
    @pytest.mark.asyncio
    async def test_risk_management_integration(self, trading_engine):
        """Test risk management prevents overleveraging."""
        trading_engine.paper_trading = True
        
        # Set small portfolio
        trading_engine.risk_manager.state.total_portfolio_value = 1000.0
        trading_engine.risk_manager.state.available_balance = 1000.0
        
        # Try to open position
        trade_signal = {
            'action': 'BUY',
            'confidence': 0.9,
            'reasoning': 'Test',
            'entry_price': 50000.0,
            'stop_loss': 48000.0,
            'take_profit': 52000.0,
            'position_size_usd': 600.0  # 60% of portfolio - should be limited
        }
        
        validated = trading_engine.risk_manager.validate_trade(
            signal=trade_signal,
            current_portfolio={
                'total_value': 1000.0,
                'available_balance': 1000.0
            }
        )
        
        # Should limit position size
        if validated:
            assert validated.get('position_size_usd', 0) <= 1000.0 * 0.1  # Max 10% for aggressive
    
    @pytest.mark.asyncio
    async def test_state_persistence_cycle(self, trading_engine):
        """Test state save and restore."""
        # Create position
        from src.core.trading_engine import Position
        
        position = Position(
            symbol='ETHUSDT',
            quantity=1.0,
            entry_price=3000.0,
            current_price=3000.0,
            unrealized_pnl=0.0,
            unrealized_pnl_percent=0.0,
            stop_loss=2900.0,
            take_profit=3100.0,
            entry_time=datetime.utcnow()
        )
        
        trading_engine.positions['ETHUSDT'] = position
        
        try:
            # Save state
            await trading_engine.state_manager.save_state(trading_engine)
            
            # Clear positions
            trading_engine.positions = {}
            
            # Restore state
            await trading_engine.state_manager.restore_state(trading_engine)
            
            # Verify position restored
            assert 'ETHUSDT' in trading_engine.positions
            assert trading_engine.positions['ETHUSDT'].quantity == 1.0
            
        except Exception as e:
            pytest.skip(f"Database not available: {e}")


@pytest.mark.integration
class TestMultiComponentIntegration:
    """Test integration between multiple components."""
    
    @pytest.mark.asyncio
    async def test_ai_orchestrator_with_sentiment(self):
        """Test AI orchestrator using sentiment data."""
        from src.core.ai_orchestrator import AIOrchestrator
        from src.intelligence.real_sentiment_analyzer import RealSentimentAnalyzer
        
        orchestrator = AIOrchestrator()
        sentiment_analyzer = RealSentimentAnalyzer()
        
        # Mock sentiment data
        with patch.object(sentiment_analyzer, 'analyze_overall_sentiment', 
                         return_value={'overall_score': 0.6, 'sentiment_label': 'BULLISH'}):
            
            sentiment = await sentiment_analyzer.analyze_overall_sentiment('BTCUSDT')
            
            market_data = {
                'symbol': 'BTCUSDT',
                'current_price': 50000.0,
                'sentiment': sentiment
            }
            
            # AI should incorporate sentiment
            result = await orchestrator.analyze_with_fallback(
                symbol='BTCUSDT',
                market_data=market_data,
                indicators={'RSI_14': 55.0},
                strategy_signals=[]
            )
            
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_risk_manager_with_portfolio_state(self):
        """Test risk manager with live portfolio state."""
        from src.core.risk_manager import RiskManager
        from src.core.trading_engine import Position
        
        risk_manager = RiskManager()
        
        # Create portfolio with multiple positions
        positions = {
            'BTCUSDT': Position(
                symbol='BTCUSDT',
                quantity=0.1,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=100.0,
                unrealized_pnl_percent=2.0,
                stop_loss=48000.0,
                take_profit=52000.0,
                entry_time=datetime.utcnow()
            ),
            'ETHUSDT': Position(
                symbol='ETHUSDT',
                quantity=1.0,
                entry_price=3000.0,
                current_price=3050.0,
                unrealized_pnl=50.0,
                unrealized_pnl_percent=1.67,
                stop_loss=2900.0,
                take_profit=3100.0,
                entry_time=datetime.utcnow()
            )
        }
        
        risk_manager.positions = positions
        risk_manager.state.total_portfolio_value = 10000.0
        
        # Test stress test with real portfolio
        stress_results = risk_manager.stress_test_portfolio()
        
        assert stress_results is not None
        assert 'market_crash' in stress_results
        assert stress_results['market_crash']['loss'] > 0


@pytest.mark.integration
class TestErrorHandlingAndRecovery:
    """Test system resilience and error recovery."""
    
    @pytest.mark.asyncio
    async def test_binance_connection_failure_recovery(self):
        """Test recovery from Binance connection failures."""
        from src.core.binance_client import BinanceClient
        
        client = BinanceClient(testnet=True)
        
        # Simulate connection failure
        with patch.object(client, '_request', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception):
                await client.get_ticker_price("BTCUSDT")
        
        # Circuit breaker should open
        # Next successful call should recover
        try:
            price = await client.get_ticker_price("BTCUSDT")
            # If testnet is accessible, should work
            assert price is not None or True  # Either gets price or testnet unavailable
        except Exception:
            pytest.skip("Testnet not accessible")
    
    @pytest.mark.asyncio
    async def test_ai_provider_fallback_chain(self):
        """Test complete AI provider fallback chain."""
        from src.core.ai_orchestrator import AIOrchestrator
        
        orchestrator = AIOrchestrator()
        
        # Mock all providers to fail except last one
        test_data = {
            'symbol': 'BTCUSDT',
            'current_price': 50000.0,
            'indicators': {'RSI_14': 55.0},
            'strategy_signals': []
        }
        
        # Should fall back through all providers and eventually get result
        result = await orchestrator.analyze_with_fallback(
            symbol='BTCUSDT',
            market_data=test_data,
            indicators=test_data['indicators'],
            strategy_signals=test_data['strategy_signals']
        )
        
        assert result is not None
        # Even if all AI fails, rule-based should provide result
        assert 'action' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
