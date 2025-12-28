"""
CoinGecko API Client
====================
Free API for additional market data, trending coins, and global market stats.
No API key required for basic endpoints.

Rate Limits (Free tier):
- 10-30 calls/minute
- No API key required

Endpoints used:
- /coins/markets - Market data for multiple coins
- /search/trending - Trending coins
- /global - Global market data
- /coins/{id}/market_chart - Historical data
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import aiohttp
import json

logger = logging.getLogger(__name__)


@dataclass
class TrendingCoin:
    """Trending coin data from CoinGecko."""
    id: str
    symbol: str
    name: str
    market_cap_rank: int
    price_btc: float
    score: int  # Trending score (0 = most trending)


@dataclass
class GlobalMarketData:
    """Global cryptocurrency market data."""
    total_market_cap_usd: float
    total_volume_24h_usd: float
    btc_dominance: float
    eth_dominance: float
    market_cap_change_24h: float
    active_cryptocurrencies: int
    markets: int
    defi_market_cap: float
    defi_volume_24h: float
    fear_greed_index: Optional[int] = None


@dataclass
class CoinMarketData:
    """Individual coin market data."""
    id: str
    symbol: str
    name: str
    current_price: float
    market_cap: float
    market_cap_rank: int
    total_volume: float
    price_change_24h: float
    price_change_percentage_24h: float
    price_change_percentage_7d: Optional[float] = None
    price_change_percentage_30d: Optional[float] = None
    ath: float = 0
    ath_change_percentage: float = 0
    atl: float = 0
    atl_change_percentage: float = 0
    circulating_supply: float = 0
    total_supply: Optional[float] = None
    sparkline_7d: Optional[List[float]] = None


class CoinGeckoClient:
    """
    CoinGecko API client for free market data.
    
    Features:
    - Trending coins detection
    - Global market sentiment
    - Price data for 1000s of coins
    - Historical price data
    - No API key required
    """
    
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    def __init__(self):
        """Initialize CoinGecko client."""
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict = {}
        self._cache_ttl = 60  # 60 seconds cache
        self._last_request_time = 0
        self._min_request_interval = 2.5  # 2.5 seconds between requests (safe for free tier)
        
        # Mapping from Binance symbols to CoinGecko IDs
        self._symbol_to_id: Dict[str, str] = {}
        
        logger.info("CoinGeckoClient initialized - Free API, no key required")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Accept": "application/json",
                    "User-Agent": "CoinBourg Trading Bot"
                }
            )
        return self.session
    
    async def _rate_limit(self):
        """Enforce rate limiting."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()
    
    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make a rate-limited API request."""
        cache_key = f"{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        
        # Check cache
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if datetime.utcnow() - cached_time < timedelta(seconds=self._cache_ttl):
                return cached_data
        
        await self._rate_limit()
        
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{endpoint}"
            
            async with session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    self._cache[cache_key] = (data, datetime.utcnow())
                    return data
                elif response.status == 429:
                    logger.warning("CoinGecko rate limit hit, backing off...")
                    await asyncio.sleep(60)
                    return None
                else:
                    logger.error(f"CoinGecko API error: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"CoinGecko request failed: {e}")
            return None
    
    async def get_trending_coins(self) -> List[TrendingCoin]:
        """
        Get trending coins on CoinGecko.
        These are coins getting the most attention right now.
        
        Returns:
            List of trending coins
        """
        data = await self._request("/search/trending")
        
        if not data or 'coins' not in data:
            return []
        
        trending = []
        for i, coin_data in enumerate(data['coins']):
            item = coin_data.get('item', {})
            trending.append(TrendingCoin(
                id=item.get('id', ''),
                symbol=item.get('symbol', '').upper(),
                name=item.get('name', ''),
                market_cap_rank=item.get('market_cap_rank', 0),
                price_btc=item.get('price_btc', 0),
                score=i  # Lower is more trending
            ))
        
        logger.info(f"Found {len(trending)} trending coins on CoinGecko")
        return trending
    
    async def get_global_market_data(self) -> Optional[GlobalMarketData]:
        """
        Get global cryptocurrency market data.
        Useful for determining overall market sentiment.
        
        Returns:
            GlobalMarketData object
        """
        data = await self._request("/global")
        
        if not data or 'data' not in data:
            return None
        
        d = data['data']
        
        return GlobalMarketData(
            total_market_cap_usd=d.get('total_market_cap', {}).get('usd', 0),
            total_volume_24h_usd=d.get('total_volume', {}).get('usd', 0),
            btc_dominance=d.get('market_cap_percentage', {}).get('btc', 0),
            eth_dominance=d.get('market_cap_percentage', {}).get('eth', 0),
            market_cap_change_24h=d.get('market_cap_change_percentage_24h_usd', 0),
            active_cryptocurrencies=d.get('active_cryptocurrencies', 0),
            markets=d.get('markets', 0),
            defi_market_cap=d.get('defi_market_cap', 0),
            defi_volume_24h=d.get('defi_volume', 0)
        )
    
    async def get_market_data(
        self,
        vs_currency: str = "usd",
        per_page: int = 250,
        page: int = 1,
        sparkline: bool = True
    ) -> List[CoinMarketData]:
        """
        Get market data for top coins by market cap.
        
        Args:
            vs_currency: Quote currency (usd, btc, etc.)
            per_page: Results per page (max 250)
            page: Page number
            sparkline: Include 7-day sparkline
            
        Returns:
            List of CoinMarketData objects
        """
        params = {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": str(sparkline).lower(),
            "price_change_percentage": "24h,7d,30d"
        }
        
        data = await self._request("/coins/markets", params)
        
        if not data:
            return []
        
        coins = []
        for coin in data:
            # Build symbol to ID mapping
            symbol = coin.get('symbol', '').upper()
            self._symbol_to_id[symbol] = coin.get('id', '')
            
            coins.append(CoinMarketData(
                id=coin.get('id', ''),
                symbol=symbol,
                name=coin.get('name', ''),
                current_price=coin.get('current_price', 0),
                market_cap=coin.get('market_cap', 0),
                market_cap_rank=coin.get('market_cap_rank', 0),
                total_volume=coin.get('total_volume', 0),
                price_change_24h=coin.get('price_change_24h', 0),
                price_change_percentage_24h=coin.get('price_change_percentage_24h', 0),
                price_change_percentage_7d=coin.get('price_change_percentage_7d_in_currency'),
                price_change_percentage_30d=coin.get('price_change_percentage_30d_in_currency'),
                ath=coin.get('ath', 0),
                ath_change_percentage=coin.get('ath_change_percentage', 0),
                atl=coin.get('atl', 0),
                atl_change_percentage=coin.get('atl_change_percentage', 0),
                circulating_supply=coin.get('circulating_supply', 0),
                total_supply=coin.get('total_supply'),
                sparkline_7d=coin.get('sparkline_in_7d', {}).get('price')
            ))
        
        logger.info(f"Retrieved market data for {len(coins)} coins")
        return coins
    
    async def get_top_gainers_losers(
        self,
        top_n: int = 20
    ) -> Tuple[List[CoinMarketData], List[CoinMarketData]]:
        """
        Get top gainers and losers in the last 24h.
        
        Args:
            top_n: Number of top gainers/losers to return
            
        Returns:
            (gainers, losers) tuple
        """
        # Get top 250 coins by market cap
        coins = await self.get_market_data(per_page=250, sparkline=False)
        
        if not coins:
            return [], []
        
        # Sort by 24h change
        sorted_coins = sorted(
            [c for c in coins if c.price_change_percentage_24h is not None],
            key=lambda x: x.price_change_percentage_24h,
            reverse=True
        )
        
        gainers = sorted_coins[:top_n]
        losers = sorted_coins[-top_n:][::-1]  # Reverse to get biggest losers first
        
        return gainers, losers
    
    async def get_coin_history(
        self,
        coin_id: str,
        days: int = 30,
        interval: str = "daily"
    ) -> Optional[Dict]:
        """
        Get historical market data for a coin.
        
        Args:
            coin_id: CoinGecko coin ID
            days: Number of days of history
            interval: Data interval (daily, hourly for < 90 days)
            
        Returns:
            Dict with prices, market_caps, total_volumes lists
        """
        params = {
            "vs_currency": "usd",
            "days": days,
            "interval": interval if days <= 90 else "daily"
        }
        
        data = await self._request(f"/coins/{coin_id}/market_chart", params)
        
        if not data:
            return None
        
        return {
            "prices": [p[1] for p in data.get('prices', [])],
            "timestamps": [p[0] for p in data.get('prices', [])],
            "market_caps": [m[1] for m in data.get('market_caps', [])],
            "volumes": [v[1] for v in data.get('total_volumes', [])]
        }
    
    async def get_market_sentiment(self) -> Dict:
        """
        Analyze overall market sentiment based on global data.
        
        Returns:
            Dict with sentiment analysis
        """
        global_data = await self.get_global_market_data()
        
        if not global_data:
            return {"sentiment": "NEUTRAL", "score": 50, "reasoning": "Unable to fetch data"}
        
        score = 50  # Neutral baseline
        reasons = []
        
        # Market cap change analysis
        if global_data.market_cap_change_24h > 3:
            score += 15
            reasons.append(f"Market cap up {global_data.market_cap_change_24h:.1f}% (bullish)")
        elif global_data.market_cap_change_24h < -3:
            score -= 15
            reasons.append(f"Market cap down {global_data.market_cap_change_24h:.1f}% (bearish)")
        
        # BTC dominance analysis
        if global_data.btc_dominance > 55:
            score -= 5
            reasons.append(f"High BTC dominance {global_data.btc_dominance:.1f}% (risk-off)")
        elif global_data.btc_dominance < 45:
            score += 5
            reasons.append(f"Low BTC dominance {global_data.btc_dominance:.1f}% (altcoin season)")
        
        # Volume analysis
        if global_data.total_volume_24h_usd > global_data.total_market_cap_usd * 0.1:
            score += 10
            reasons.append("High trading volume (active market)")
        
        # Determine sentiment
        if score >= 70:
            sentiment = "VERY_BULLISH"
        elif score >= 60:
            sentiment = "BULLISH"
        elif score <= 30:
            sentiment = "VERY_BEARISH"
        elif score <= 40:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"
        
        return {
            "sentiment": sentiment,
            "score": score,
            "reasoning": "; ".join(reasons) if reasons else "Market neutral",
            "btc_dominance": global_data.btc_dominance,
            "market_cap_change_24h": global_data.market_cap_change_24h,
            "total_market_cap": global_data.total_market_cap_usd
        }
    
    def symbol_to_coingecko_id(self, symbol: str) -> Optional[str]:
        """Convert Binance symbol to CoinGecko ID."""
        # Remove USDT suffix
        base = symbol.replace("USDT", "").upper()
        return self._symbol_to_id.get(base)
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()


# Singleton instance
_coingecko_client: Optional[CoinGeckoClient] = None


def get_coingecko_client() -> CoinGeckoClient:
    """Get or create CoinGecko client singleton."""
    global _coingecko_client
    if _coingecko_client is None:
        _coingecko_client = CoinGeckoClient()
    return _coingecko_client
