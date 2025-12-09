"""
Dynamic Coin Selector
====================
Scans all USDT pairs and ranks them by comprehensive metrics.
Provides dynamic coin selection instead of hardcoded trading pairs.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CoinMetrics:
    """Comprehensive metrics for a trading pair."""
    symbol: str
    price: float
    volume_24h: float
    volume_30d: float
    market_cap: Optional[float]
    price_change_24h: float
    price_change_7d: float
    price_change_30d: float
    volatility_30d: float
    momentum_score: float
    volume_trend: float
    spread_percent: float
    sharpe_ratio: Optional[float]
    max_drawdown: float
    win_rate: Optional[float]
    composite_score: float
    last_updated: datetime


class CoinSelector:
    """
    Dynamic coin selector that scans all USDT pairs and ranks them.
    
    Features:
    - Scan all USDT pairs on Binance
    - Filter by volume, market cap, age, spread
    - Compute comprehensive metrics
    - Rank coins by composite score
    - Refresh hourly
    """
    
    def __init__(self, binance_client):
        """
        Initialize coin selector.
        
        Args:
            binance_client: BinanceClient instance for market data
        """
        self.binance_client = binance_client
        self.settings = get_settings()
        
        # Configuration
        self.min_volume_24h = self.settings.MIN_VOLUME_USD
        self.max_coins_scan = self.settings.MAX_COINS_SCAN
        self.scan_interval = self.settings.SCAN_INTERVAL_HOURS * 3600
        
        # Cache
        self._ranked_coins: List[CoinMetrics] = []
        self._last_scan: Optional[datetime] = None
        self._scan_lock = asyncio.Lock()
        
        logger.info(f"CoinSelector initialized - Min volume: ${self.min_volume_24h:,.0f}, "
                   f"Max coins: {self.max_coins_scan}")
    
    async def scan_market(self, force_refresh: bool = False) -> List[CoinMetrics]:
        """
        Scan all USDT pairs and rank them.
        
        Args:
            force_refresh: Force refresh even if cache is valid
            
        Returns:
            List of ranked CoinMetrics
        """
        async with self._scan_lock:
            # Check if cached results are still valid
            if not force_refresh and self._ranked_coins and self._last_scan:
                elapsed = (datetime.utcnow() - self._last_scan).total_seconds()
                if elapsed < self.scan_interval:
                    logger.debug(f"Using cached coin rankings ({elapsed:.0f}s old)")
                    return self._ranked_coins
            
            logger.info("Starting market scan for all USDT pairs...")
            start_time = datetime.utcnow()
            
            try:
                # Get all USDT trading pairs
                all_symbols = await self._get_all_usdt_pairs()
                logger.info(f"Found {len(all_symbols)} USDT pairs")
                
                # Apply initial filters
                filtered_symbols = await self._apply_filters(all_symbols)
                logger.info(f"After filtering: {len(filtered_symbols)} pairs remain")
                
                # Compute metrics for filtered symbols
                coin_metrics = await self._compute_metrics(filtered_symbols)
                logger.info(f"Computed metrics for {len(coin_metrics)} coins")
                
                # Rank coins by composite score
                ranked = sorted(coin_metrics, key=lambda x: x.composite_score, reverse=True)
                
                # Keep only top N
                self._ranked_coins = ranked[:self.max_coins_scan]
                self._last_scan = datetime.utcnow()
                
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Market scan completed in {elapsed:.1f}s - "
                           f"Top coin: {self._ranked_coins[0].symbol} "
                           f"(score: {self._ranked_coins[0].composite_score:.2f})")
                
                return self._ranked_coins
                
            except Exception as e:
                logger.error(f"Market scan failed: {e}")
                return self._ranked_coins  # Return cached results if available
    
    async def _get_all_usdt_pairs(self) -> List[str]:
        """Get all active USDT trading pairs from Binance."""
        try:
            exchange_info = await self.binance_client.get_exchange_info()
            
            usdt_pairs = []
            for symbol_info in exchange_info.get('symbols', []):
                symbol = symbol_info['symbol']
                if (symbol.endswith('USDT') and 
                    symbol_info['status'] == 'TRADING' and
                    symbol_info['isSpotTradingAllowed']):
                    usdt_pairs.append(symbol)
            
            return usdt_pairs
            
        except Exception as e:
            logger.error(f"Failed to get USDT pairs: {e}")
            return []
    
    async def _apply_filters(self, symbols: List[str]) -> List[str]:
        """
        Apply filtering criteria to symbols.
        
        Filters:
        - 24h volume >= min threshold
        - Spread <= max threshold
        - Trading age >= min days
        - Valid price range
        """
        filtered = []
        
        # Get 24h tickers for all symbols
        tickers = await self.binance_client.get_24h_tickers()
        ticker_map = {t['symbol']: t for t in tickers}
        
        for symbol in symbols:
            ticker = ticker_map.get(symbol)
            if not ticker:
                continue
            
            try:
                volume_24h = float(ticker.get('quoteVolume', 0))
                price = float(ticker.get('lastPrice', 0))
                
                # Volume filter
                if volume_24h < self.min_volume_24h:
                    continue
                
                # Price range filter (avoid penny stocks and too expensive coins)
                if price < 0.0001 or price > 100000:
                    continue
                
                # Spread check (if available)
                bid = float(ticker.get('bidPrice', 0))
                ask = float(ticker.get('askPrice', 0))
                if bid > 0 and ask > 0:
                    spread_pct = ((ask - bid) / bid) * 100
                    if spread_pct > 1.0:  # Max 1% spread
                        continue
                
                filtered.append(symbol)
                
            except (ValueError, KeyError) as e:
                logger.debug(f"Error filtering {symbol}: {e}")
                continue
        
        return filtered
    
    async def _compute_metrics(self, symbols: List[str]) -> List[CoinMetrics]:
        """
        Compute comprehensive metrics for each symbol.
        
        Metrics computed:
        - Returns (24h, 7d, 30d)
        - Volatility (30d standard deviation)
        - Momentum score
        - Volume trend
        - Sharpe ratio (if enough data)
        - Max drawdown
        """
        coin_metrics = []
        
        # Process symbols in batches for efficiency
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batch_metrics = await asyncio.gather(
                *[self._compute_single_metric(symbol) for symbol in batch],
                return_exceptions=True
            )
            
            for metric in batch_metrics:
                if isinstance(metric, CoinMetrics):
                    coin_metrics.append(metric)
                elif isinstance(metric, Exception):
                    logger.debug(f"Failed to compute metric: {metric}")
        
        return coin_metrics
    
    async def _compute_single_metric(self, symbol: str) -> CoinMetrics:
        """Compute metrics for a single symbol."""
        try:
            # Get current ticker
            ticker = await self.binance_client.get_ticker(symbol)
            
            # Get historical data (30 days)
            klines = await self.binance_client.get_historical_klines(
                symbol=symbol,
                interval='1d',
                limit=30
            )
            
            if len(klines) < 7:
                raise ValueError(f"Insufficient data for {symbol}")
            
            # Extract prices
            closes = np.array([float(k[4]) for k in klines])  # Close prices
            volumes = np.array([float(k[5]) for k in klines])  # Volumes
            
            current_price = closes[-1]
            
            # Calculate returns
            price_change_24h = ((closes[-1] / closes[-2]) - 1) * 100 if len(closes) >= 2 else 0
            price_change_7d = ((closes[-1] / closes[-7]) - 1) * 100 if len(closes) >= 7 else 0
            price_change_30d = ((closes[-1] / closes[0]) - 1) * 100 if len(closes) >= 30 else 0
            
            # Calculate volatility (annualized)
            daily_returns = np.diff(closes) / closes[:-1]
            volatility_30d = np.std(daily_returns) * np.sqrt(365) * 100
            
            # Momentum score (rate of change)
            momentum_score = self._calculate_momentum(closes)
            
            # Volume trend
            volume_trend = self._calculate_volume_trend(volumes)
            
            # Sharpe ratio (if enough data)
            sharpe_ratio = self._calculate_sharpe(daily_returns) if len(daily_returns) >= 20 else None
            
            # Max drawdown
            max_drawdown = self._calculate_max_drawdown(closes)
            
            # Spread
            bid_price = float(ticker.get('bidPrice', current_price))
            ask_price = float(ticker.get('askPrice', current_price))
            spread_percent = ((ask_price - bid_price) / bid_price) * 100 if bid_price > 0 else 0
            
            # Composite score
            composite_score = self._calculate_composite_score(
                momentum=momentum_score,
                volume_trend=volume_trend,
                volatility=volatility_30d,
                sharpe=sharpe_ratio,
                drawdown=max_drawdown,
                price_change_7d=price_change_7d
            )
            
            return CoinMetrics(
                symbol=symbol,
                price=current_price,
                volume_24h=float(ticker.get('quoteVolume', 0)),
                volume_30d=float(np.sum(volumes)),
                market_cap=None,  # Would need additional API for this
                price_change_24h=price_change_24h,
                price_change_7d=price_change_7d,
                price_change_30d=price_change_30d,
                volatility_30d=volatility_30d,
                momentum_score=momentum_score,
                volume_trend=volume_trend,
                spread_percent=spread_percent,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                win_rate=None,  # Would need trade history
                composite_score=composite_score,
                last_updated=datetime.utcnow()
            )
            
        except Exception as e:
            raise ValueError(f"Failed to compute metrics for {symbol}: {e}")
    
    def _calculate_momentum(self, closes: np.ndarray) -> float:
        """Calculate momentum score (0-100)."""
        if len(closes) < 10:
            return 50.0
        
        # Use multiple timeframes
        mom_3d = ((closes[-1] / closes[-3]) - 1) * 100 if len(closes) >= 3 else 0
        mom_7d = ((closes[-1] / closes[-7]) - 1) * 100 if len(closes) >= 7 else 0
        mom_14d = ((closes[-1] / closes[-14]) - 1) * 100 if len(closes) >= 14 else 0
        
        # Weighted average
        momentum = (mom_3d * 0.5 + mom_7d * 0.3 + mom_14d * 0.2)
        
        # Normalize to 0-100
        return max(0, min(100, 50 + momentum * 2))
    
    def _calculate_volume_trend(self, volumes: np.ndarray) -> float:
        """Calculate volume trend (-1 to 1)."""
        if len(volumes) < 7:
            return 0.0
        
        recent_vol = np.mean(volumes[-7:])
        older_vol = np.mean(volumes[:-7]) if len(volumes) > 7 else recent_vol
        
        if older_vol == 0:
            return 0.0
        
        trend = (recent_vol / older_vol) - 1
        return max(-1.0, min(1.0, trend))
    
    def _calculate_sharpe(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 20:
            return 0.0
        
        mean_return = np.mean(returns) * 365
        std_return = np.std(returns) * np.sqrt(365)
        
        if std_return == 0:
            return 0.0
        
        sharpe = (mean_return - risk_free_rate) / std_return
        return sharpe
    
    def _calculate_max_drawdown(self, closes: np.ndarray) -> float:
        """Calculate maximum drawdown percentage."""
        peak = closes[0]
        max_dd = 0.0
        
        for price in closes:
            if price > peak:
                peak = price
            dd = ((price - peak) / peak) * 100
            if dd < max_dd:
                max_dd = dd
        
        return abs(max_dd)
    
    def _calculate_composite_score(
        self,
        momentum: float,
        volume_trend: float,
        volatility: float,
        sharpe: Optional[float],
        drawdown: float,
        price_change_7d: float
    ) -> float:
        """
        Calculate composite score (0-100) for ranking.
        
        Weights:
        - Momentum: 30%
        - Volume trend: 20%
        - Sharpe ratio: 20%
        - Low drawdown: 15%
        - Recent performance: 15%
        """
        score = 0.0
        
        # Momentum component (0-30)
        score += (momentum / 100) * 30
        
        # Volume trend component (0-20)
        score += ((volume_trend + 1) / 2) * 20
        
        # Sharpe component (0-20)
        if sharpe is not None:
            sharpe_normalized = max(0, min(1, (sharpe + 2) / 4))  # Normalize -2 to 2 range
            score += sharpe_normalized * 20
        else:
            score += 10  # Neutral score if no Sharpe
        
        # Drawdown component (0-15) - lower is better
        drawdown_score = max(0, 1 - (drawdown / 50))
        score += drawdown_score * 15
        
        # Recent performance component (0-15)
        perf_score = max(0, min(1, (price_change_7d + 20) / 40))  # Normalize -20% to +20%
        score += perf_score * 15
        
        return score
    
    def get_top_coins(self, n: int = 10) -> List[CoinMetrics]:
        """Get top N coins by composite score."""
        return self._ranked_coins[:n]
    
    def get_coin_metrics(self, symbol: str) -> Optional[CoinMetrics]:
        """Get metrics for a specific symbol."""
        for coin in self._ranked_coins:
            if coin.symbol == symbol:
                return coin
        return None
    
    async def refresh_if_needed(self):
        """Refresh rankings if cache expired."""
        if not self._last_scan:
            await self.scan_market()
        else:
            elapsed = (datetime.utcnow() - self._last_scan).total_seconds()
            if elapsed >= self.scan_interval:
                await self.scan_market()
