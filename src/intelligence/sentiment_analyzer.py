"""
Sentiment Analyzer
==================
Multi-source sentiment analysis for trading signals.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import aiohttp
import re
from collections import Counter

logger = logging.getLogger(__name__)


class SentimentScore(Enum):
    """Sentiment classification."""
    VERY_BEARISH = -2
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1
    VERY_BULLISH = 2


@dataclass
class SentimentData:
    """Sentiment data point."""
    source: str
    symbol: str
    sentiment: SentimentScore
    confidence: float
    text: str
    timestamp: datetime
    metrics: Dict[str, float]  # engagement, reach, etc.


@dataclass
class AggregateSentiment:
    """Aggregated sentiment across sources."""
    symbol: str
    overall_sentiment: SentimentScore
    confidence: float
    score: float  # -1 to +1
    sources: Dict[str, SentimentScore]
    total_mentions: int
    bullish_count: int
    bearish_count: int
    neutral_count: int
    timestamp: datetime


class SentimentAnalyzer:
    """
    Multi-source sentiment analysis.
    
    Sources:
    - Twitter/X (via API or scraping)
    - Reddit (r/cryptocurrency, r/bitcoin, etc.)
    - News APIs (CryptoPanic, NewsAPI)
    - Fear & Greed Index
    - Social volume metrics
    
    Note: This implementation provides structure and mock data.
    Real implementation requires API keys and may face rate limits.
    """
    
    def __init__(
        self,
        twitter_bearer_token: Optional[str] = None,
        reddit_client_id: Optional[str] = None,
        reddit_client_secret: Optional[str] = None,
        news_api_key: Optional[str] = None
    ):
        """
        Initialize sentiment analyzer.
        
        Args:
            twitter_bearer_token: Twitter API v2 bearer token
            reddit_client_id: Reddit API client ID
            reddit_client_secret: Reddit API client secret
            news_api_key: News API key
        """
        self.twitter_token = twitter_bearer_token
        self.reddit_id = reddit_client_id
        self.reddit_secret = reddit_client_secret
        self.news_key = news_api_key
        
        # Sentiment keywords
        self.bullish_keywords = {
            'moon', 'bullish', 'bull', 'pump', 'rally', 'breakout', 
            'rocket', 'lambo', 'buy', 'long', 'hodl', 'accumulate',
            'undervalued', 'breakout', 'surge', 'soar'
        }
        self.bearish_keywords = {
            'crash', 'dump', 'bearish', 'bear', 'sell', 'short',
            'overvalued', 'bubble', 'drop', 'fall', 'decline',
            'correction', 'panic', 'fear', 'scam', 'rug'
        }
        
        # Cache
        self.sentiment_cache: Dict[str, AggregateSentiment] = {}
        self.cache_ttl = 300  # 5 minutes
        
        logger.info("SentimentAnalyzer initialized")
    
    async def analyze_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> AggregateSentiment:
        """
        Analyze sentiment across all sources.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            lookback_hours: Hours to look back
            
        Returns:
            AggregateSentiment with aggregated data
        """
        # Check cache
        cache_key = f"{symbol}_{lookback_hours}"
        if cache_key in self.sentiment_cache:
            cached = self.sentiment_cache[cache_key]
            age = (datetime.now() - cached.timestamp).total_seconds()
            if age < self.cache_ttl:
                logger.debug(f"Using cached sentiment for {symbol}")
                return cached
        
        logger.info(f"Analyzing sentiment for {symbol} (last {lookback_hours}h)")
        
        # Collect from all sources in parallel
        tasks = [
            self._analyze_twitter(symbol, lookback_hours),
            self._analyze_reddit(symbol, lookback_hours),
            self._analyze_news(symbol, lookback_hours),
            self._get_fear_greed_index()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        all_sentiments = []
        source_sentiments = {}
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error in sentiment source {i}: {result}")
                continue
            
            if result:
                all_sentiments.extend(result)
                
                # Group by source
                for sent in result:
                    source_sentiments[sent.source] = sent.sentiment
        
        # Aggregate sentiments
        if not all_sentiments:
            logger.warning(f"No sentiment data found for {symbol}")
            return self._default_sentiment(symbol)
        
        aggregate = self._aggregate_sentiments(symbol, all_sentiments, source_sentiments)
        
        # Cache result
        self.sentiment_cache[cache_key] = aggregate
        
        logger.info(f"Sentiment for {symbol}: {aggregate.overall_sentiment.name} "
                   f"(score: {aggregate.score:.2f}, confidence: {aggregate.confidence:.2f})")
        
        return aggregate
    
    async def _analyze_twitter(
        self,
        symbol: str,
        lookback_hours: int
    ) -> List[SentimentData]:
        """
        Analyze Twitter sentiment.
        
        Note: Requires Twitter API v2 access.
        This is a mock implementation.
        """
        if not self.twitter_token:
            logger.debug("Twitter API not configured, skipping")
            return []
        
        # Extract base symbol (BTC from BTCUSDT)
        base_symbol = symbol.replace('USDT', '').replace('USD', '')
        
        # In real implementation, use Twitter API v2
        # Example: GET /2/tweets/search/recent?query=$BTC
        
        # Mock data for demonstration
        logger.debug(f"Fetching Twitter data for {base_symbol}")
        
        # Simulate API call
        await asyncio.sleep(0.1)
        
        # Mock sentiment data
        mock_tweets = [
            {"text": f"${base_symbol} looking bullish! 🚀", "engagement": 150},
            {"text": f"Time to buy {base_symbol}, huge potential", "engagement": 80},
            {"text": f"${base_symbol} correction incoming", "engagement": 60},
        ]
        
        sentiments = []
        for tweet in mock_tweets:
            sentiment = self._classify_text_sentiment(tweet['text'])
            
            sentiments.append(SentimentData(
                source='twitter',
                symbol=symbol,
                sentiment=sentiment,
                confidence=0.7,
                text=tweet['text'],
                timestamp=datetime.now(),
                metrics={'engagement': tweet['engagement']}
            ))
        
        return sentiments
    
    async def _analyze_reddit(
        self,
        symbol: str,
        lookback_hours: int
    ) -> List[SentimentData]:
        """
        Analyze Reddit sentiment from crypto subreddits.
        
        Note: Requires Reddit API credentials.
        This is a mock implementation.
        """
        if not self.reddit_id or not self.reddit_secret:
            logger.debug("Reddit API not configured, skipping")
            return []
        
        base_symbol = symbol.replace('USDT', '').replace('USD', '')
        
        # In real implementation, use Reddit API
        # Subreddits: r/cryptocurrency, r/bitcoin, r/ethtrader, etc.
        
        logger.debug(f"Fetching Reddit data for {base_symbol}")
        
        # Simulate API call
        await asyncio.sleep(0.1)
        
        # Mock sentiment data
        mock_posts = [
            {"text": f"{base_symbol} is the future of finance", "score": 250},
            {"text": f"Just bought more {base_symbol}, DCA strategy", "score": 120},
            {"text": f"{base_symbol} overvalued at current price", "score": 90},
        ]
        
        sentiments = []
        for post in mock_posts:
            sentiment = self._classify_text_sentiment(post['text'])
            
            sentiments.append(SentimentData(
                source='reddit',
                symbol=symbol,
                sentiment=sentiment,
                confidence=0.65,
                text=post['text'],
                timestamp=datetime.now(),
                metrics={'score': post['score']}
            ))
        
        return sentiments
    
    async def _analyze_news(
        self,
        symbol: str,
        lookback_hours: int
    ) -> List[SentimentData]:
        """
        Analyze news sentiment.
        
        Sources: CryptoPanic, NewsAPI, CoinDesk, etc.
        """
        base_symbol = symbol.replace('USDT', '').replace('USD', '')
        
        # In real implementation, use CryptoPanic or NewsAPI
        
        logger.debug(f"Fetching news for {base_symbol}")
        
        # Simulate API call
        await asyncio.sleep(0.1)
        
        # Mock news data
        mock_news = [
            {"title": f"{base_symbol} reaches new milestone", "sentiment": "positive"},
            {"title": f"Analysts predict {base_symbol} surge", "sentiment": "positive"},
            {"title": f"{base_symbol} faces regulatory concerns", "sentiment": "negative"},
        ]
        
        sentiments = []
        for article in mock_news:
            if article['sentiment'] == 'positive':
                sentiment = SentimentScore.BULLISH
            elif article['sentiment'] == 'negative':
                sentiment = SentimentScore.BEARISH
            else:
                sentiment = SentimentScore.NEUTRAL
            
            sentiments.append(SentimentData(
                source='news',
                symbol=symbol,
                sentiment=sentiment,
                confidence=0.8,
                text=article['title'],
                timestamp=datetime.now(),
                metrics={}
            ))
        
        return sentiments
    
    async def _get_fear_greed_index(self) -> List[SentimentData]:
        """
        Get Fear & Greed Index from alternative.me.
        
        This is a real API call (no auth required).
        """
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if 'data' in data and len(data['data']) > 0:
                            fng_data = data['data'][0]
                            value = int(fng_data['value'])
                            classification = fng_data['value_classification']
                            
                            # Map to sentiment
                            if value <= 20:
                                sentiment = SentimentScore.VERY_BEARISH
                            elif value <= 40:
                                sentiment = SentimentScore.BEARISH
                            elif value <= 60:
                                sentiment = SentimentScore.NEUTRAL
                            elif value <= 80:
                                sentiment = SentimentScore.BULLISH
                            else:
                                sentiment = SentimentScore.VERY_BULLISH
                            
                            logger.info(f"Fear & Greed Index: {value}/100 ({classification})")
                            
                            return [SentimentData(
                                source='fear_greed',
                                symbol='MARKET',
                                sentiment=sentiment,
                                confidence=0.9,
                                text=f"Fear & Greed: {value}/100 - {classification}",
                                timestamp=datetime.now(),
                                metrics={'value': value}
                            )]
        
        except Exception as e:
            logger.error(f"Error fetching Fear & Greed Index: {e}")
        
        return []
    
    def _classify_text_sentiment(self, text: str) -> SentimentScore:
        """
        Classify text sentiment using keyword analysis.
        
        Args:
            text: Text to analyze
            
        Returns:
            SentimentScore
        """
        text_lower = text.lower()
        words = set(re.findall(r'\w+', text_lower))
        
        bullish_count = len(words & self.bullish_keywords)
        bearish_count = len(words & self.bearish_keywords)
        
        # Check for negation
        has_negation = any(neg in text_lower for neg in ['not', "don't", 'never', 'no'])
        
        if has_negation:
            # Flip sentiment if negation detected
            bullish_count, bearish_count = bearish_count, bullish_count
        
        if bullish_count > bearish_count + 1:
            return SentimentScore.BULLISH
        elif bearish_count > bullish_count + 1:
            return SentimentScore.BEARISH
        else:
            return SentimentScore.NEUTRAL
    
    def _aggregate_sentiments(
        self,
        symbol: str,
        sentiments: List[SentimentData],
        source_sentiments: Dict[str, SentimentScore]
    ) -> AggregateSentiment:
        """
        Aggregate sentiments from multiple sources.
        
        Args:
            symbol: Trading symbol
            sentiments: List of sentiment data
            source_sentiments: Sentiment by source
            
        Returns:
            AggregateSentiment
        """
        # Count sentiment types
        sentiment_counts = Counter([s.sentiment for s in sentiments])
        
        bullish_count = sentiment_counts.get(SentimentScore.BULLISH, 0) + \
                       sentiment_counts.get(SentimentScore.VERY_BULLISH, 0)
        bearish_count = sentiment_counts.get(SentimentScore.BEARISH, 0) + \
                       sentiment_counts.get(SentimentScore.VERY_BEARISH, 0)
        neutral_count = sentiment_counts.get(SentimentScore.NEUTRAL, 0)
        
        # Calculate weighted score
        total = len(sentiments)
        scores = [s.sentiment.value * s.confidence for s in sentiments]
        confidences = [s.confidence for s in sentiments]
        
        avg_score = sum(scores) / sum(confidences) if confidences else 0
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Normalize score to -1 to +1
        normalized_score = max(-1, min(1, avg_score / 2))
        
        # Determine overall sentiment
        if normalized_score >= 0.5:
            overall = SentimentScore.VERY_BULLISH
        elif normalized_score >= 0.15:
            overall = SentimentScore.BULLISH
        elif normalized_score <= -0.5:
            overall = SentimentScore.VERY_BEARISH
        elif normalized_score <= -0.15:
            overall = SentimentScore.BEARISH
        else:
            overall = SentimentScore.NEUTRAL
        
        return AggregateSentiment(
            symbol=symbol,
            overall_sentiment=overall,
            confidence=avg_confidence,
            score=normalized_score,
            sources=source_sentiments,
            total_mentions=total,
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            neutral_count=neutral_count,
            timestamp=datetime.now()
        )
    
    def _default_sentiment(self, symbol: str) -> AggregateSentiment:
        """Return default neutral sentiment."""
        return AggregateSentiment(
            symbol=symbol,
            overall_sentiment=SentimentScore.NEUTRAL,
            confidence=0.0,
            score=0.0,
            sources={},
            total_mentions=0,
            bullish_count=0,
            bearish_count=0,
            neutral_count=0,
            timestamp=datetime.now()
        )
    
    async def get_trending_coins(self, limit: int = 10) -> List[Tuple[str, float]]:
        """
        Get trending coins by social volume.
        
        Args:
            limit: Number of trending coins
            
        Returns:
            List of (symbol, sentiment_score) tuples
        """
        # In real implementation, use social volume APIs
        # LunarCrush, Santiment, or CoinGecko trending
        
        logger.info(f"Fetching top {limit} trending coins")
        
        # Mock data
        trending = [
            ('BTCUSDT', 0.65),
            ('ETHUSDT', 0.45),
            ('SOLUSDT', 0.75),
            ('ADAUSDT', 0.30),
            ('DOTUSDT', 0.20)
        ]
        
        return trending[:limit]
    
    def get_sentiment_signal(
        self,
        sentiment: AggregateSentiment,
        threshold: float = 0.5
    ) -> Tuple[str, float]:
        """
        Convert sentiment to trading signal.
        
        Args:
            sentiment: AggregateSentiment
            threshold: Confidence threshold
            
        Returns:
            (action, confidence) tuple
        """
        if sentiment.confidence < threshold:
            return ("HOLD", sentiment.confidence)
        
        if sentiment.score >= 0.5:
            return ("BUY", sentiment.confidence)
        elif sentiment.score >= 0.2:
            return ("BUY_WEAK", sentiment.confidence * 0.7)
        elif sentiment.score <= -0.5:
            return ("SELL", sentiment.confidence)
        elif sentiment.score <= -0.2:
            return ("SELL_WEAK", sentiment.confidence * 0.7)
        else:
            return ("HOLD", sentiment.confidence)
