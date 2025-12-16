"""
Unit Tests for Sentiment Analyzer
==================================
Tests for real sentiment analysis integrations.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.intelligence.real_sentiment_analyzer import RealSentimentAnalyzer


class TestRealSentimentAnalyzer:
    """Test suite for RealSentimentAnalyzer."""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return RealSentimentAnalyzer()
    
    @pytest.mark.asyncio
    async def test_initialization(self, analyzer):
        """Test analyzer initializes correctly."""
        assert analyzer is not None
    
    @pytest.mark.asyncio
    async def test_twitter_sentiment_with_mock(self, analyzer):
        """Test Twitter sentiment with mocked API."""
        # Mock Twitter API response
        mock_tweets = [
            Mock(
                text="Bitcoin looking bullish! 🚀",
                public_metrics={'like_count': 100, 'retweet_count': 50},
                created_at=datetime.utcnow()
            ),
            Mock(
                text="BTC to the moon!",
                public_metrics={'like_count': 200, 'retweet_count': 100},
                created_at=datetime.utcnow()
            )
        ]
        
        with patch.object(analyzer, '_fetch_twitter_data', return_value=mock_tweets):
            sentiment = await analyzer._analyze_twitter('BTCUSDT')
            
            assert isinstance(sentiment, float)
            assert -1.0 <= sentiment <= 1.0
    
    @pytest.mark.asyncio
    async def test_reddit_sentiment_with_mock(self, analyzer):
        """Test Reddit sentiment with mocked API."""
        # Mock Reddit submission
        mock_submission = Mock(
            title="Bitcoin analysis",
            selftext="Detailed BTC analysis showing bullish trends",
            score=500,
            num_comments=50,
            created_utc=datetime.utcnow().timestamp()
        )
        
        mock_subreddit = Mock()
        mock_subreddit.search.return_value = [mock_submission]
        
        with patch.object(analyzer, '_get_reddit_client', return_value=Mock(subreddit=lambda x: mock_subreddit)):
            sentiment = await analyzer._analyze_reddit('BTCUSDT')
            
            assert isinstance(sentiment, float)
            assert -1.0 <= sentiment <= 1.0
    
    @pytest.mark.asyncio
    async def test_news_sentiment_with_mock(self, analyzer):
        """Test news sentiment with mocked API."""
        mock_articles = {
            'articles': [
                {
                    'title': 'Bitcoin reaches new highs',
                    'description': 'Positive news about Bitcoin',
                    'source': {'name': 'CoinDesk'},
                    'publishedAt': datetime.utcnow().isoformat()
                }
            ]
        }
        
        with patch.object(analyzer, '_fetch_news_data', return_value=mock_articles):
            sentiment = await analyzer._analyze_news('BTCUSDT')
            
            assert isinstance(sentiment, float)
            assert -1.0 <= sentiment <= 1.0
    
    @pytest.mark.asyncio
    async def test_fear_greed_index(self, analyzer):
        """Test Fear & Greed Index fetching."""
        try:
            index = await analyzer._get_fear_greed_index()
            
            if index is not None:
                assert 0 <= index <= 100
        except Exception:
            # Network request may fail in test environment
            pytest.skip("Fear & Greed Index API not accessible")
    
    @pytest.mark.asyncio
    async def test_overall_sentiment_aggregation(self, analyzer):
        """Test overall sentiment aggregation from multiple sources."""
        # Mock individual sentiment sources
        with patch.object(analyzer, '_analyze_twitter', return_value=0.5), \
             patch.object(analyzer, '_analyze_reddit', return_value=0.3), \
             patch.object(analyzer, '_analyze_news', return_value=0.7), \
             patch.object(analyzer, '_get_fear_greed_index', return_value=65):
            
            overall = await analyzer.analyze_overall_sentiment('BTCUSDT')
            
            assert isinstance(overall, dict)
            assert 'overall_score' in overall
            assert 'sentiment_label' in overall
            assert -1.0 <= overall['overall_score'] <= 1.0
            assert overall['sentiment_label'] in ['VERY_BEARISH', 'BEARISH', 'NEUTRAL', 'BULLISH', 'VERY_BULLISH']
    
    def test_sentiment_scoring_without_ml(self, analyzer):
        """Test keyword-based sentiment scoring."""
        bullish_text = "Bitcoin looking great! Strong support, bullish momentum, breakout imminent"
        bearish_text = "Bitcoin crash incoming, sell now, weak hands, bearish divergence, dump"
        neutral_text = "Bitcoin price at 50000, volume steady, waiting for confirmation"
        
        bullish_score = analyzer._score_sentiment_keywords(bullish_text)
        bearish_score = analyzer._score_sentiment_keywords(bearish_text)
        neutral_score = analyzer._score_sentiment_keywords(neutral_text)
        
        assert bullish_score > neutral_score
        assert bearish_score < neutral_score
        assert -1.0 <= bullish_score <= 1.0
        assert -1.0 <= bearish_score <= 1.0
    
    @pytest.mark.asyncio
    async def test_engagement_weighting(self, analyzer):
        """Test that high engagement posts have more weight."""
        high_engagement = {
            'text': 'Bullish',
            'likes': 10000,
            'retweets': 5000
        }
        
        low_engagement = {
            'text': 'Bearish',
            'likes': 10,
            'retweets': 5
        }
        
        # High engagement should dominate
        weighted = analyzer._calculate_weighted_sentiment([
            (0.8, 15000),  # High engagement, bullish
            (-0.8, 15)     # Low engagement, bearish
        ])
        
        assert weighted > 0  # Should be positive due to high engagement


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/intelligence/real_sentiment_analyzer"])
