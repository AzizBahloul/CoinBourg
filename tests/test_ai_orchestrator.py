"""
Unit Tests for AI Orchestrator
===============================
Tests for multi-provider AI orchestration, fallbacks, and ensemble.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.ai_orchestrator import AIOrchestrator, AIProvider


class TestAIOrchestrator:
    """Test suite for AIOrchestrator."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator instance."""
        return AIOrchestrator()
    
    @pytest.mark.asyncio
    async def test_initialization(self, orchestrator):
        """Test orchestrator initializes correctly."""
        assert orchestrator is not None
        assert orchestrator.providers is not None
        assert len(orchestrator.providers) > 0
    
    @pytest.mark.asyncio
    async def test_provider_registration(self, orchestrator):
        """Test provider registration."""
        initial_count = len(orchestrator.providers)
        
        # Add a mock provider
        mock_provider = Mock(spec=AIProvider)
        mock_provider.name = "TestProvider"
        mock_provider.priority = 10
        
        orchestrator.register_provider(mock_provider)
        
        assert len(orchestrator.providers) == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_fallback_mechanism(self, orchestrator):
        """Test fallback to secondary providers."""
        # Mock primary provider to fail
        with patch.object(orchestrator.providers[0], 'analyze', side_effect=Exception("Primary failed")):
            # Should fall back to next provider
            test_data = {
                'symbol': 'BTCUSDT',
                'indicators': {'RSI_14': 55.0},
                'strategy_signals': []
            }
            
            result = await orchestrator.analyze_with_fallback(
                symbol='BTCUSDT',
                market_data=test_data,
                indicators=test_data['indicators'],
                strategy_signals=test_data['strategy_signals']
            )
            
            # Should get result from fallback provider
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_ensemble_mode(self, orchestrator):
        """Test ensemble analysis combining multiple providers."""
        test_data = {
            'symbol': 'BTCUSDT',
            'current_price': 50000.0,
            'indicators': {
                'RSI_14': 55.0,
                'MACD': {'macd': 100, 'signal': 95}
            },
            'strategy_signals': []
        }
        
        # Mock multiple providers returning different signals
        mock_results = [
            {
                'action': 'BUY',
                'confidence': 0.8,
                'reasoning': 'Provider 1 says buy',
                'entry_price': 50000.0,
                'stop_loss': 48000.0,
                'take_profit': 52000.0
            },
            {
                'action': 'BUY',
                'confidence': 0.7,
                'reasoning': 'Provider 2 says buy',
                'entry_price': 50000.0,
                'stop_loss': 48500.0,
                'take_profit': 51500.0
            }
        ]
        
        with patch.object(orchestrator, '_call_provider', side_effect=mock_results):
            result = await orchestrator.analyze_with_ensemble(
                symbol='BTCUSDT',
                market_data=test_data,
                indicators=test_data['indicators'],
                strategy_signals=test_data['strategy_signals']
            )
            
            assert result is not None
            assert 'action' in result
            assert 'confidence' in result
            # Ensemble should aggregate confidences
            assert result['confidence'] <= 1.0
    
    @pytest.mark.asyncio
    async def test_response_validation(self, orchestrator):
        """Test AI response validation."""
        # Valid response
        valid_response = {
            'action': 'BUY',
            'confidence': 0.75,
            'reasoning': 'Valid reasoning',
            'entry_price': 50000.0,
            'stop_loss': 48000.0,
            'take_profit': 52000.0
        }
        
        assert orchestrator._validate_response(valid_response) is True
        
        # Invalid responses
        invalid_responses = [
            {'action': 'INVALID'},  # Missing fields
            {'action': 'BUY', 'confidence': 1.5, 'reasoning': 'test'},  # Invalid confidence
            {'action': 'HOLD', 'confidence': 0.7, 'reasoning': 'test', 'entry_price': -100},  # Negative price
        ]
        
        for invalid in invalid_responses:
            assert orchestrator._validate_response(invalid) is False
    
    @pytest.mark.asyncio
    async def test_provider_health_monitoring(self, orchestrator):
        """Test provider health tracking."""
        provider = orchestrator.providers[0]
        
        # Record successful call
        orchestrator._record_provider_success(provider.name)
        
        # Record failure
        orchestrator._record_provider_failure(provider.name)
        
        # Get health stats
        health = orchestrator.get_provider_health(provider.name)
        
        assert 'success_rate' in health
        assert 'total_calls' in health
        assert 'last_success' in health or 'last_failure' in health


class TestRuleBasedFallback:
    """Test rule-based analysis as final fallback."""
    
    @pytest.mark.asyncio
    async def test_rule_based_analysis(self):
        """Test rule-based analysis when all AI providers fail."""
        from src.core.ai_orchestrator import RuleBasedAnalyzer
        
        analyzer = RuleBasedAnalyzer()
        
        indicators = {
            'RSI_14': 70.0,  # Overbought
            'MACD': {'macd': -50, 'signal': -30},  # Bearish
            'BB_upper': 51000.0,
            'BB_middle': 50000.0,
            'BB_lower': 49000.0
        }
        
        market_data = {
            'current_price': 50800.0,  # Near upper band
            'price_change_24h': -2.0
        }
        
        result = await analyzer.analyze(
            symbol='BTCUSDT',
            market_data=market_data,
            indicators=indicators,
            strategy_signals=[]
        )
        
        assert result is not None
        assert result['action'] in ['BUY', 'SELL', 'HOLD']
        assert 0 <= result['confidence'] <= 1.0
        assert 'reasoning' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/core/ai_orchestrator"])
