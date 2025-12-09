"""
Market Scanner
==============
Efficient parallel scanning of 100-500 symbols with comprehensive scoring.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class SignalStrength(Enum):
    """Signal strength classification."""
    VERY_STRONG = "very_strong"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NEUTRAL = "neutral"


@dataclass
class ScanResult:
    """Result from scanning a single symbol."""
    symbol: str
    price: float
    volume_24h: float
    price_change_24h: float
    
    # Scoring components
    momentum_score: float  # 0-100
    volume_score: float  # 0-100
    volatility_score: float  # 0-100
    sentiment_score: float  # 0-100
    trend_score: float  # 0-100
    risk_score: float  # 0-100
    
    # Composite
    total_score: float  # 0-100
    signal_strength: str
    recommendation: str  # BUY, SELL, HOLD
    
    # Metadata
    scan_timestamp: datetime
    confidence: float  # 0-1


class MarketScanner:
    """
    High-performance market scanner for hundreds of symbols.
    
    Features:
    - Parallel async scanning
    - Multi-component scoring system
    - Throttling to respect rate limits
    - Efficient batch processing
    """
    
    def __init__(self, binance_client, coin_selector):
        """
        Initialize market scanner.
        
        Args:
            binance_client: BinanceClient instance
            coin_selector: CoinSelector instance for symbol selection
        """
        self.binance_client = binance_client
        self.coin_selector = coin_selector
        
        # Concurrency control
        self.max_concurrent = 50
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        
        # Cache
        self._last_scan_results: Dict[str, ScanResult] = {}
        self._last_full_scan: Optional[datetime] = None
        
        logger.info(f"MarketScanner initialized - Max concurrent: {self.max_concurrent}")
    
    async def scan_all(
        self,
        symbols: Optional[List[str]] = None,
        include_sentiment: bool = False
    ) -> List[ScanResult]:
        """
        Scan all symbols in parallel with throttling.
        
        Args:
            symbols: Optional list of symbols to scan. If None, uses coin_selector top coins.
            include_sentiment: Whether to include sentiment analysis (slower)
            
        Returns:
            List of ScanResult objects sorted by total_score
        """
        start_time = datetime.utcnow()
        
        # Get symbols to scan
        if symbols is None:
            await self.coin_selector.refresh_if_needed()
            top_coins = self.coin_selector.get_top_coins(n=50)
            symbols = [coin.symbol for coin in top_coins]
        
        logger.info(f"Starting market scan for {len(symbols)} symbols...")
        
        # Scan symbols in parallel with semaphore limiting
        tasks = [self._scan_single(symbol, include_sentiment) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        scan_results = []
        for result in results:
            if isinstance(result, ScanResult):
                scan_results.append(result)
                self._last_scan_results[result.symbol] = result
            elif isinstance(result, Exception):
                logger.debug(f"Scan error: {result}")
        
        # Sort by total score
        scan_results.sort(key=lambda x: x.total_score, reverse=True)
        
        self._last_full_scan = datetime.utcnow()
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        logger.info(f"Market scan completed in {elapsed:.1f}s - "
                   f"Scanned: {len(scan_results)}/{len(symbols)} symbols")
        
        if scan_results:
            logger.info(f"Top signal: {scan_results[0].symbol} "
                       f"(score: {scan_results[0].total_score:.1f}, "
                       f"signal: {scan_results[0].signal_strength})")
        
        return scan_results
    
    async def _scan_single(
        self,
        symbol: str,
        include_sentiment: bool = False
    ) -> ScanResult:
        """
        Scan a single symbol with all scoring components.
        
        Args:
            symbol: Trading pair symbol
            include_sentiment: Include sentiment analysis
            
        Returns:
            ScanResult object
        """
        async with self.semaphore:
            try:
                # Get market data
                ticker = await self.binance_client.get_ticker(symbol)
                klines = await self.binance_client.get_historical_klines(
                    symbol=symbol,
                    interval='1h',
                    limit=168  # 7 days of hourly data
                )
                
                if len(klines) < 24:
                    raise ValueError(f"Insufficient data for {symbol}")
                
                # Extract data
                closes = np.array([float(k[4]) for k in klines])
                volumes = np.array([float(k[5]) for k in klines])
                highs = np.array([float(k[2]) for k in klines])
                lows = np.array([float(k[3]) for k in klines])
                
                current_price = closes[-1]
                volume_24h = float(ticker.get('quoteVolume', 0))
                price_change_24h = float(ticker.get('priceChangePercent', 0))
                
                # Calculate scoring components
                momentum_score = await self._score_momentum(closes)
                volume_score = await self._score_volume(volumes)
                volatility_score = await self._score_volatility(closes, highs, lows)
                trend_score = await self._score_trend(closes)
                risk_score = await self._score_risk(closes, highs, lows)
                
                # Sentiment score (placeholder if not included)
                sentiment_score = 50.0  # Neutral
                if include_sentiment:
                    # Would call sentiment analyzer here
                    pass
                
                # Calculate total score (weighted average)
                total_score = self._calculate_total_score(
                    momentum=momentum_score,
                    volume=volume_score,
                    volatility=volatility_score,
                    sentiment=sentiment_score,
                    trend=trend_score,
                    risk=risk_score
                )
                
                # Determine signal strength and recommendation
                signal_strength, recommendation, confidence = self._classify_signal(
                    total_score,
                    momentum_score,
                    trend_score
                )
                
                return ScanResult(
                    symbol=symbol,
                    price=current_price,
                    volume_24h=volume_24h,
                    price_change_24h=price_change_24h,
                    momentum_score=momentum_score,
                    volume_score=volume_score,
                    volatility_score=volatility_score,
                    sentiment_score=sentiment_score,
                    trend_score=trend_score,
                    risk_score=risk_score,
                    total_score=total_score,
                    signal_strength=signal_strength,
                    recommendation=recommendation,
                    scan_timestamp=datetime.utcnow(),
                    confidence=confidence
                )
                
            except Exception as e:
                raise ValueError(f"Failed to scan {symbol}: {e}")
    
    async def _score_momentum(self, closes: np.ndarray) -> float:
        """
        Score momentum (0-100).
        
        Uses multiple timeframes:
        - Short-term: Last 6 hours
        - Medium-term: Last 24 hours
        - Long-term: Last 7 days
        """
        if len(closes) < 6:
            return 50.0
        
        score = 0.0
        
        # Short-term momentum (6 hours)
        if len(closes) >= 6:
            mom_6h = ((closes[-1] / closes[-6]) - 1) * 100
            score += max(0, min(100, 50 + mom_6h * 5)) * 0.4
        
        # Medium-term momentum (24 hours)
        if len(closes) >= 24:
            mom_24h = ((closes[-1] / closes[-24]) - 1) * 100
            score += max(0, min(100, 50 + mom_24h * 2)) * 0.35
        
        # Long-term momentum (7 days)
        if len(closes) >= 168:
            mom_7d = ((closes[-1] / closes[-168]) - 1) * 100
            score += max(0, min(100, 50 + mom_7d)) * 0.25
        
        return score
    
    async def _score_volume(self, volumes: np.ndarray) -> float:
        """
        Score volume trend (0-100).
        
        Higher score = increasing volume = stronger signal
        """
        if len(volumes) < 24:
            return 50.0
        
        # Compare recent volume to average
        recent_volume = np.mean(volumes[-24:])  # Last 24 hours
        avg_volume = np.mean(volumes[:-24]) if len(volumes) > 24 else recent_volume
        
        if avg_volume == 0:
            return 50.0
        
        volume_ratio = recent_volume / avg_volume
        
        # Normalize to 0-100 (0.5x to 2x range)
        score = max(0, min(100, (volume_ratio - 0.5) / 1.5 * 100))
        
        return score
    
    async def _score_volatility(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> float:
        """
        Score volatility (0-100).
        
        Moderate volatility is preferred (50-70 range).
        Too low = no opportunity, too high = too risky.
        """
        if len(closes) < 24:
            return 50.0
        
        # Calculate ATR (Average True Range)
        atr_values = []
        for i in range(1, min(24, len(closes))):
            high_low = highs[-i] - lows[-i]
            high_close = abs(highs[-i] - closes[-i-1])
            low_close = abs(lows[-i] - closes[-i-1])
            true_range = max(high_low, high_close, low_close)
            atr_values.append(true_range)
        
        atr = np.mean(atr_values)
        atr_percent = (atr / closes[-1]) * 100
        
        # Optimal volatility is around 2-5%
        if 2 <= atr_percent <= 5:
            score = 100 - abs(3.5 - atr_percent) * 10
        elif atr_percent < 2:
            score = 30 + (atr_percent / 2) * 20  # Low volatility = lower score
        else:
            score = max(0, 100 - (atr_percent - 5) * 10)  # High volatility = risk
        
        return max(0, min(100, score))
    
    async def _score_trend(self, closes: np.ndarray) -> float:
        """
        Score trend strength (0-100).
        
        Uses simple moving averages to identify trend.
        """
        if len(closes) < 50:
            return 50.0
        
        current_price = closes[-1]
        
        # Calculate SMAs
        sma_10 = np.mean(closes[-10:])
        sma_20 = np.mean(closes[-20:]) if len(closes) >= 20 else sma_10
        sma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma_20
        
        score = 50.0  # Neutral baseline
        
        # Price above all SMAs = strong uptrend
        if current_price > sma_10 > sma_20 > sma_50:
            score = 90
        # Price above some SMAs = uptrend
        elif current_price > sma_10 and current_price > sma_20:
            score = 70
        elif current_price > sma_10:
            score = 60
        # Price below all SMAs = strong downtrend
        elif current_price < sma_10 < sma_20 < sma_50:
            score = 10
        # Price below some SMAs = downtrend
        elif current_price < sma_10 and current_price < sma_20:
            score = 30
        elif current_price < sma_10:
            score = 40
        
        return score
    
    async def _score_risk(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> float:
        """
        Score risk level (0-100).
        
        Higher score = lower risk.
        Considers: drawdown, price stability, support levels.
        """
        if len(closes) < 24:
            return 50.0
        
        risk_score = 100.0
        
        # Calculate recent drawdown
        recent_peak = np.max(closes[-24:])
        current_price = closes[-1]
        drawdown = ((current_price - recent_peak) / recent_peak) * 100
        
        # Penalize large drawdowns
        if drawdown < -10:
            risk_score -= 30
        elif drawdown < -5:
            risk_score -= 15
        
        # Calculate price stability (lower std dev = more stable = less risky)
        returns = np.diff(closes[-24:]) / closes[-25:-1]
        volatility = np.std(returns) * 100
        
        if volatility > 5:
            risk_score -= 20
        elif volatility > 3:
            risk_score -= 10
        
        # Check if price is near support (recent low)
        recent_low = np.min(lows[-24:])
        distance_from_low = ((current_price - recent_low) / recent_low) * 100
        
        # Near recent low = higher risk of further drop
        if distance_from_low < 2:
            risk_score -= 15
        
        return max(0, min(100, risk_score))
    
    def _calculate_total_score(
        self,
        momentum: float,
        volume: float,
        volatility: float,
        sentiment: float,
        trend: float,
        risk: float
    ) -> float:
        """
        Calculate weighted total score.
        
        Weights:
        - Trend: 25%
        - Momentum: 20%
        - Volume: 15%
        - Risk: 20%
        - Volatility: 10%
        - Sentiment: 10%
        """
        total = (
            trend * 0.25 +
            momentum * 0.20 +
            volume * 0.15 +
            risk * 0.20 +
            volatility * 0.10 +
            sentiment * 0.10
        )
        
        return total
    
    def _classify_signal(
        self,
        total_score: float,
        momentum_score: float,
        trend_score: float
    ) -> Tuple[str, str, float]:
        """
        Classify signal strength and recommendation.
        
        Returns:
            (signal_strength, recommendation, confidence)
        """
        # Determine signal strength
        if total_score >= 80:
            signal_strength = SignalStrength.VERY_STRONG.value
            confidence = 0.9
        elif total_score >= 70:
            signal_strength = SignalStrength.STRONG.value
            confidence = 0.75
        elif total_score >= 55:
            signal_strength = SignalStrength.MODERATE.value
            confidence = 0.6
        elif total_score >= 40:
            signal_strength = SignalStrength.WEAK.value
            confidence = 0.4
        else:
            signal_strength = SignalStrength.NEUTRAL.value
            confidence = 0.2
        
        # Determine recommendation
        if total_score >= 70 and momentum_score >= 60 and trend_score >= 60:
            recommendation = "BUY"
        elif total_score <= 30 and momentum_score <= 40 and trend_score <= 40:
            recommendation = "SELL"
        else:
            recommendation = "HOLD"
        
        return signal_strength, recommendation, confidence
    
    def get_top_opportunities(self, n: int = 10) -> List[ScanResult]:
        """Get top N trading opportunities from last scan."""
        if not self._last_scan_results:
            return []
        
        sorted_results = sorted(
            self._last_scan_results.values(),
            key=lambda x: x.total_score,
            reverse=True
        )
        
        return sorted_results[:n]
    
    def get_buy_signals(self, min_confidence: float = 0.6) -> List[ScanResult]:
        """Get all BUY signals above confidence threshold."""
        results = []
        for scan_result in self._last_scan_results.values():
            if (scan_result.recommendation == "BUY" and 
                scan_result.confidence >= min_confidence):
                results.append(scan_result)
        
        return sorted(results, key=lambda x: x.total_score, reverse=True)
    
    def export_results(self) -> List[Dict]:
        """Export scan results as list of dictionaries for storage."""
        return [asdict(result) for result in self._last_scan_results.values()]
