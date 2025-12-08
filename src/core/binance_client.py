"""
Binance API Client
==================
Professional Binance API wrapper with comprehensive trading functionality.
Supports both live and testnet environments.
"""

import asyncio
import hashlib
import hmac
import time
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from decimal import Decimal, ROUND_DOWN
from functools import wraps
from enum import Enum
import aiohttp
from urllib.parse import urlencode

from src.config.settings import get_settings
from src.config.constants import (
    OrderType, OrderStatus, TimeFrame,
    BINANCE_RATE_LIMITS
)

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for resilient API calls.
    
    Prevents cascading failures by temporarily disabling calls to
    a failing service.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_requests: int = 1
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_successes = 0
    
    def can_execute(self) -> bool:
        """Check if request can be executed."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_successes = 0
                    logger.info("Circuit breaker entering HALF_OPEN state")
                    return True
            return False
        
        # HALF_OPEN: allow limited requests
        return True
    
    def record_success(self):
        """Record a successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            if self.half_open_successes >= self.half_open_requests:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker CLOSED after recovery")
        else:
            self.failure_count = 0
    
    def record_failure(self):
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker OPEN after half-open failure")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")


async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (aiohttp.ClientError, asyncio.TimeoutError)
):
    """
    Retry an async function with exponential backoff.
    
    Args:
        func: Async function to call
        max_retries: Maximum number of retries
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exceptions to retry on
    
    Returns:
        Result of the function call
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(f"Max retries ({max_retries}) exceeded")
                raise
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            
            # Add jitter
            if jitter:
                delay = delay * (0.5 + random.random())
            
            logger.warning(
                f"Request failed (attempt {attempt + 1}/{max_retries + 1}), "
                f"retrying in {delay:.2f}s: {e}"
            )
            await asyncio.sleep(delay)
    
    raise last_exception


class BinanceClient:
    """
    Async Binance API Client with comprehensive trading functionality.
    
    Features:
    - Spot trading (buy/sell)
    - Account balance management
    - Real-time price data
    - Historical candlestick data
    - Order management
    - WebSocket support for real-time updates
    """
    
    # API Endpoints
    BASE_URL = "https://api.binance.com"
    TESTNET_URL = "https://testnet.binance.vision"
    
    WS_BASE_URL = "wss://stream.binance.com:9443/ws"
    WS_TESTNET_URL = "wss://testnet.binance.vision/ws"
    
    def __init__(self):
        """Initialize Binance client with settings from environment."""
        self.settings = get_settings()
        self.api_key = self.settings.BINANCE_API_KEY
        self.api_secret = self.settings.BINANCE_API_SECRET
        self.use_testnet = self.settings.BINANCE_TESTNET
        
        # Select appropriate endpoints
        self.base_url = self.TESTNET_URL if self.use_testnet else self.BASE_URL
        self.ws_url = self.WS_TESTNET_URL if self.use_testnet else self.WS_BASE_URL
        
        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        
        # Rate limiting
        self._request_timestamps: List[float] = []
        self._rate_limit = BINANCE_RATE_LIMITS["requests_per_minute"]
        self._rate_limit_lock = asyncio.Lock()
        
        # Symbol info cache with TTL
        self._symbol_info: Dict[str, Dict] = {}
        self._symbol_info_expiry: Optional[datetime] = None
        self._symbol_info_ttl = timedelta(hours=1)
        
        # Circuit breaker for fault tolerance
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30,
            half_open_requests=2
        )
        
        # Request timeout settings
        self._timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        # Health tracking
        self._last_successful_request: Optional[datetime] = None
        self._consecutive_errors = 0
        
        logger.info(f"BinanceClient initialized - Testnet: {self.use_testnet}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with thread safety."""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    headers={"X-MBX-APIKEY": self.api_key},
                    timeout=self._timeout
                )
            return self._session
    
    async def close(self):
        """Close the HTTP session."""
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
    
    def _generate_signature(self, params: Dict) -> str:
        """Generate HMAC SHA256 signature for authenticated requests."""
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def _check_rate_limit(self):
        """Check and enforce rate limits with thread safety."""
        async with self._rate_limit_lock:
            current_time = time.time()
            # Remove timestamps older than 1 minute
            self._request_timestamps = [
                ts for ts in self._request_timestamps 
                if current_time - ts < 60
            ]
            
            if len(self._request_timestamps) >= self._rate_limit:
                wait_time = 60 - (current_time - self._request_timestamps[0])
                if wait_time > 0:
                    logger.warning(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
            
            self._request_timestamps.append(current_time)
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        signed: bool = False,
        retry: bool = True
    ) -> Dict:
        """
        Make HTTP request to Binance API with circuit breaker and retry logic.
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint
            params: Request parameters
            signed: Whether request requires signature
            retry: Whether to retry on failure
            
        Returns:
            API response as dictionary
            
        Raises:
            Exception: If request fails after all retries
        """
        # Check circuit breaker
        if not self._circuit_breaker.can_execute():
            raise Exception("Circuit breaker is OPEN - service temporarily unavailable")
        
        await self._check_rate_limit()
        
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['recvWindow'] = 5000  # 5 second window for clock sync
            params['signature'] = self._generate_signature(params)
        
        async def make_request():
            async with session.request(
                method,
                url,
                params=params if method == "GET" else None,
                data=params if method != "GET" else None
            ) as response:
                data = await response.json()
                
                if response.status != 200:
                    error_msg = data.get('msg', 'Unknown error')
                    error_code = data.get('code', 'Unknown')
                    
                    # Handle specific error codes
                    if error_code == -1021:  # Timestamp out of sync
                        raise Exception(f"Clock sync error: {error_msg}")
                    elif error_code == -1003:  # Rate limit
                        logger.warning("Rate limit exceeded, backing off...")
                        raise aiohttp.ClientError(f"Rate limit: {error_msg}")
                    elif error_code in [-2010, -2011]:  # Order errors
                        raise Exception(f"Order error: {error_code} - {error_msg}")
                    
                    logger.error(f"Binance API error: {error_code} - {error_msg}")
                    raise Exception(f"Binance API error: {error_code} - {error_msg}")
                
                return data
        
        try:
            if retry:
                result = await retry_with_backoff(
                    make_request,
                    max_retries=3,
                    base_delay=1.0,
                    max_delay=10.0,
                    retryable_exceptions=(aiohttp.ClientError, asyncio.TimeoutError)
                )
            else:
                result = await make_request()
            
            # Record success
            self._circuit_breaker.record_success()
            self._last_successful_request = datetime.utcnow()
            self._consecutive_errors = 0
            
            return result
            
        except Exception as e:
            # Record failure
            self._circuit_breaker.record_failure()
            self._consecutive_errors += 1
            
            logger.error(f"Request failed: {endpoint} - {e}")
            raise
    
    # ===========================================
    # Market Data Methods
    # ===========================================
    
    async def get_exchange_info(self) -> Dict:
        """Get exchange trading rules and symbol information."""
        data = await self._request("GET", "/api/v3/exchangeInfo")
        
        # Cache symbol info
        for symbol_data in data.get('symbols', []):
            self._symbol_info[symbol_data['symbol']] = symbol_data
        
        return data
    
    async def get_symbol_info(self, symbol: str) -> Dict:
        """Get trading rules for a specific symbol."""
        if symbol not in self._symbol_info:
            await self.get_exchange_info()
        return self._symbol_info.get(symbol, {})
    
    async def get_ticker_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        data = await self._request(
            "GET",
            "/api/v3/ticker/price",
            params={"symbol": symbol}
        )
        return float(data['price'])
    
    async def get_all_tickers(self) -> Dict[str, float]:
        """Get current prices for all symbols."""
        data = await self._request("GET", "/api/v3/ticker/price")
        return {item['symbol']: float(item['price']) for item in data}
    
    async def get_ticker_24h(self, symbol: str) -> Dict:
        """Get 24h ticker statistics."""
        return await self._request(
            "GET",
            "/api/v3/ticker/24hr",
            params={"symbol": symbol}
        )
    
    async def get_orderbook(self, symbol: str, limit: int = 100) -> Dict:
        """Get order book depth."""
        return await self._request(
            "GET",
            "/api/v3/depth",
            params={"symbol": symbol, "limit": limit}
        )
    
    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[List]:
        """
        Get candlestick/kline data.
        
        Args:
            symbol: Trading pair symbol
            interval: Kline interval (1m, 5m, 15m, 1h, 4h, 1d, etc.)
            limit: Number of klines to return (max 1000)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            
        Returns:
            List of klines [open_time, open, high, low, close, volume, ...]
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        return await self._request("GET", "/api/v3/klines", params=params)
    
    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get recent trades for a symbol."""
        return await self._request(
            "GET",
            "/api/v3/trades",
            params={"symbol": symbol, "limit": limit}
        )
    
    # ===========================================
    # Account Methods
    # ===========================================
    
    async def get_account(self) -> Dict:
        """Get current account information including balances."""
        return await self._request("GET", "/api/v3/account", signed=True)
    
    async def get_balances(self) -> Dict[str, Dict[str, float]]:
        """
        Get all asset balances.
        
        Returns:
            Dictionary of {asset: {"free": float, "locked": float}}
        """
        account = await self.get_account()
        balances = {}
        
        for balance in account.get('balances', []):
            free = float(balance['free'])
            locked = float(balance['locked'])
            
            if free > 0 or locked > 0:
                balances[balance['asset']] = {
                    "free": free,
                    "locked": locked,
                    "total": free + locked
                }
        
        return balances
    
    async def get_asset_balance(self, asset: str) -> Dict[str, float]:
        """Get balance for a specific asset."""
        balances = await self.get_balances()
        return balances.get(asset, {"free": 0.0, "locked": 0.0, "total": 0.0})
    
    # ===========================================
    # Order Methods
    # ===========================================
    
    def _round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to symbol's step size."""
        if symbol not in self._symbol_info:
            return quantity
        
        info = self._symbol_info[symbol]
        for f in info.get('filters', []):
            if f['filterType'] == 'LOT_SIZE':
                step_size = Decimal(f['stepSize'])
                quantity = Decimal(str(quantity))
                rounded = (quantity // step_size) * step_size
                return float(rounded)
        
        return quantity
    
    def _round_price(self, symbol: str, price: float) -> float:
        """Round price to symbol's tick size."""
        if symbol not in self._symbol_info:
            return price
        
        info = self._symbol_info[symbol]
        for f in info.get('filters', []):
            if f['filterType'] == 'PRICE_FILTER':
                tick_size = Decimal(f['tickSize'])
                price = Decimal(str(price))
                rounded = (price // tick_size) * tick_size
                return float(rounded)
        
        return price
    
    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "MARKET",
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = "GTC"
    ) -> Dict:
        """
        Create a new order.
        
        Args:
            symbol: Trading pair symbol
            side: BUY or SELL
            order_type: MARKET, LIMIT, STOP_LOSS, STOP_LOSS_LIMIT, etc.
            quantity: Order quantity in base asset
            quote_quantity: Order quantity in quote asset (for MARKET orders)
            price: Limit price
            stop_price: Stop price for stop orders
            time_in_force: GTC, IOC, FOK
            
        Returns:
            Order response from Binance
        """
        # Ensure we have symbol info
        await self.get_symbol_info(symbol)
        
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
        }
        
        if quantity:
            params['quantity'] = self._round_quantity(symbol, quantity)
        
        if quote_quantity and order_type == "MARKET":
            params['quoteOrderQty'] = quote_quantity
        
        if price and order_type != "MARKET":
            params['price'] = self._round_price(symbol, price)
            params['timeInForce'] = time_in_force
        
        if stop_price:
            params['stopPrice'] = self._round_price(symbol, stop_price)
        
        logger.info(f"Creating order: {params}")
        
        return await self._request("POST", "/api/v3/order", params=params, signed=True)
    
    async def market_buy(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        quote_quantity: Optional[float] = None
    ) -> Dict:
        """Place a market buy order."""
        return await self.create_order(
            symbol=symbol,
            side="BUY",
            order_type="MARKET",
            quantity=quantity,
            quote_quantity=quote_quantity
        )
    
    async def market_sell(self, symbol: str, quantity: float) -> Dict:
        """Place a market sell order."""
        return await self.create_order(
            symbol=symbol,
            side="SELL",
            order_type="MARKET",
            quantity=quantity
        )
    
    async def limit_buy(
        self,
        symbol: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC"
    ) -> Dict:
        """Place a limit buy order."""
        return await self.create_order(
            symbol=symbol,
            side="BUY",
            order_type="LIMIT",
            quantity=quantity,
            price=price,
            time_in_force=time_in_force
        )
    
    async def limit_sell(
        self,
        symbol: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC"
    ) -> Dict:
        """Place a limit sell order."""
        return await self.create_order(
            symbol=symbol,
            side="SELL",
            order_type="LIMIT",
            quantity=quantity,
            price=price,
            time_in_force=time_in_force
        )
    
    async def cancel_order(self, symbol: str, order_id: int) -> Dict:
        """Cancel an existing order."""
        return await self._request(
            "DELETE",
            "/api/v3/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True
        )
    
    async def cancel_all_orders(self, symbol: str) -> List[Dict]:
        """Cancel all open orders for a symbol."""
        return await self._request(
            "DELETE",
            "/api/v3/openOrders",
            params={"symbol": symbol},
            signed=True
        )
    
    async def get_order(self, symbol: str, order_id: int) -> Dict:
        """Get order status."""
        return await self._request(
            "GET",
            "/api/v3/order",
            params={"symbol": symbol, "orderId": order_id},
            signed=True
        )
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open orders."""
        params = {}
        if symbol:
            params['symbol'] = symbol
        
        return await self._request(
            "GET",
            "/api/v3/openOrders",
            params=params if params else None,
            signed=True
        )
    
    async def get_all_orders(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[Dict]:
        """Get all orders (including filled and cancelled)."""
        return await self._request(
            "GET",
            "/api/v3/allOrders",
            params={"symbol": symbol, "limit": limit},
            signed=True
        )
    
    async def get_my_trades(
        self,
        symbol: str,
        limit: int = 100
    ) -> List[Dict]:
        """Get trades for a specific symbol."""
        return await self._request(
            "GET",
            "/api/v3/myTrades",
            params={"symbol": symbol, "limit": limit},
            signed=True
        )
    
    # ===========================================
    # Utility Methods
    # ===========================================
    
    async def test_connectivity(self) -> bool:
        """Test API connectivity."""
        try:
            await self._request("GET", "/api/v3/ping")
            return True
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            return False
    
    async def get_server_time(self) -> int:
        """Get Binance server time."""
        data = await self._request("GET", "/api/v3/time")
        return data['serverTime']
    
    async def calculate_position_value(
        self,
        symbol: str,
        quantity: float
    ) -> float:
        """Calculate the USDT value of a position."""
        price = await self.get_ticker_price(symbol)
        return quantity * price
    
    async def get_portfolio_value(self) -> float:
        """Calculate total portfolio value in USDT."""
        balances = await self.get_balances()
        prices = await self.get_all_tickers()
        
        total_value = 0.0
        
        for asset, balance in balances.items():
            if asset == 'USDT':
                total_value += balance['total']
            else:
                symbol = f"{asset}USDT"
                if symbol in prices:
                    total_value += balance['total'] * prices[symbol]
        
        return total_value
    
    # ===========================================
    # Convenience Aliases
    # ===========================================
    
    async def get_price(self, symbol: str) -> float:
        """Alias for get_ticker_price."""
        return await self.get_ticker_price(symbol)
    
    async def get_account_info(self) -> Dict:
        """Alias for get_account."""
        return await self.get_account()
    
    async def get_order_book(self, symbol: str, limit: int = 100) -> Dict:
        """Alias for get_orderbook."""
        return await self.get_orderbook(symbol, limit)
    
    async def get_24hr_ticker(self, symbol: str) -> Dict:
        """Alias for get_ticker_24h."""
        return await self.get_ticker_24h(symbol)
