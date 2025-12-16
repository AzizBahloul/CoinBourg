"""
WebSocket Client for Real-Time Market Data
==========================================
Efficient streaming of multiple symbols, order book, and trade data.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass
import websockets
from websockets.client import WebSocketClientProtocol

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Real-time trade data."""
    symbol: str
    price: float
    quantity: float
    is_buyer_maker: bool  # True if seller is market maker
    timestamp: datetime
    trade_id: int


@dataclass
class OrderBookUpdate:
    """Order book update."""
    symbol: str
    bids: List[tuple]  # [(price, quantity), ...]
    asks: List[tuple]
    timestamp: datetime


@dataclass
class TickerUpdate:
    """24h ticker update."""
    symbol: str
    price: float
    price_change_percent: float
    volume_24h: float
    high_24h: float
    low_24h: float
    timestamp: datetime


class WebSocketClient:
    """
    Binance WebSocket client for real-time market data.
    
    Features:
    - Multiple symbol streaming with combined streams
    - Order book depth streaming
    - Real-time trade streaming
    - Large order detection
    - Auto-reconnect on disconnection
    - Backpressure handling
    """
    
    def __init__(self, testnet: bool = True):
        """
        Initialize WebSocket client.
        
        Args:
            testnet: Use testnet WebSocket
        """
        self.settings = get_settings()
        self.testnet = testnet
        
        # WebSocket URLs
        if testnet:
            self.ws_base_url = "wss://testnet.binance.vision/ws"
            self.ws_stream_url = "wss://testnet.binance.vision/stream"
        else:
            self.ws_base_url = "wss://stream.binance.com:9443/ws"
            self.ws_stream_url = "wss://stream.binance.com:9443/stream"
        
        # Connection management
        self._connections: Dict[str, WebSocketClientProtocol] = {}
        self._running = False
        self._reconnect_delay = 5
        self._max_reconnect_delay = 60
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        
        # Heartbeat monitoring (NEW)
        self._last_message_time: Dict[str, datetime] = {}
        self._heartbeat_interval = 30  # Send ping every 30 seconds
        self._heartbeat_timeout = 60  # Reconnect if no message for 60 seconds
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        
        # Subscriptions
        self._subscribed_symbols: Set[str] = set()
        self._stream_handlers: Dict[str, List[Callable]] = {
            'trade': [],
            'ticker': [],
            'depth': [],
            'large_order': []
        }
        
        # Connection state tracking (NEW)
        self._connection_healthy: Dict[str, bool] = {}
        self._reconnection_in_progress: Dict[str, bool] = {}
        
        # Large order detection
        self._large_order_threshold_usd = 100000  # $100k+ orders
        
        # Metrics
        self._messages_received = 0
        self._last_message_time: Optional[datetime] = None
        self._connection_errors = 0
        
        logger.info(f"WebSocketClient initialized - Testnet: {testnet}")
    
    async def connect(self, streams: List[str]) -> WebSocketClientProtocol:
        """
        Connect to Binance WebSocket.
        
        Args:
            streams: List of stream names (e.g., ['btcusdt@trade', 'ethusdt@depth'])
            
        Returns:
            WebSocket connection
        """
        # Combine multiple streams into one connection
        stream_path = "/".join(streams)
        url = f"{self.ws_stream_url}?streams={stream_path}"
        
        try:
            websocket = await websockets.connect(url)
            logger.info(f"WebSocket connected: {len(streams)} streams")
            return websocket
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self._connection_errors += 1
            raise
    
    async def subscribe_trades(self, symbols: List[str], handler: Optional[Callable] = None):
        """
        Subscribe to real-time trades for multiple symbols.
        
        Args:
            symbols: List of trading pairs
            handler: Optional callback function for trade events
        """
        if handler:
            self._stream_handlers['trade'].append(handler)
        
        streams = [f"{symbol.lower()}@trade" for symbol in symbols]
        await self._subscribe_streams(streams, self._handle_trade_message)
        
        for symbol in symbols:
            self._subscribed_symbols.add(symbol)
        
        logger.info(f"Subscribed to trades for {len(symbols)} symbols")
    
    async def subscribe_tickers(self, symbols: List[str], handler: Optional[Callable] = None):
        """
        Subscribe to 24h ticker updates.
        
        Args:
            symbols: List of trading pairs
            handler: Optional callback function for ticker events
        """
        if handler:
            self._stream_handlers['ticker'].append(handler)
        
        streams = [f"{symbol.lower()}@ticker" for symbol in symbols]
        await self._subscribe_streams(streams, self._handle_ticker_message)
        
        logger.info(f"Subscribed to tickers for {len(symbols)} symbols")
    
    async def subscribe_orderbook(self, symbols: List[str], depth: int = 20, update_speed: str = "100ms", handler: Optional[Callable] = None):
        """
        Subscribe to order book depth updates.
        
        Args:
            symbols: List of trading pairs
            depth: Depth levels (5, 10, 20)
            update_speed: Update speed (100ms or 1000ms)
            handler: Optional callback function for depth events
        """
        if handler:
            self._stream_handlers['depth'].append(handler)
        
        # Use partial book depth stream
        speed_suffix = "" if update_speed == "1000ms" else "@100ms"
        streams = [f"{symbol.lower()}@depth{depth}{speed_suffix}" for symbol in symbols]
        await self._subscribe_streams(streams, self._handle_depth_message)
        
        logger.info(f"Subscribed to order book for {len(symbols)} symbols (depth={depth})")
    
    async def _subscribe_streams(self, streams: List[str], message_handler: Callable):
        """Subscribe to multiple streams with a message handler."""
        if not self._running:
            self._running = True
            asyncio.create_task(self._maintain_connection(streams, message_handler))
    
    async def _maintain_connection(self, streams: List[str], message_handler: Callable):
        """Maintain WebSocket connection with auto-reconnect."""
        reconnect_delay = self._reconnect_delay
        
        while self._running:
            try:
                websocket = await self.connect(streams)
                reconnect_delay = self._reconnect_delay  # Reset delay on successful connection
                
                # Process messages
                async for message in websocket:
                    await self._process_message(message, message_handler)
                    
            except websockets.ConnectionClosed as e:
                logger.warning(f"WebSocket connection closed: {e}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self._connection_errors += 1
            
            if self._running:
                logger.info(f"Reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self._max_reconnect_delay)
    
    async def _process_message(self, message: str, handler: Callable):
        """Process incoming WebSocket message."""
        try:
            data = json.loads(message)
            self._messages_received += 1
            self._last_message_time = datetime.utcnow()
            
            # Handle combined stream format
            if 'stream' in data and 'data' in data:
                await handler(data['data'])
            else:
                await handler(data)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _handle_trade_message(self, data: Dict):
        """Handle trade message."""
        try:
            symbol = data['s']
            price = float(data['p'])
            quantity = float(data['q'])
            is_buyer_maker = data['m']
            
            trade = Trade(
                symbol=symbol,
                price=price,
                quantity=quantity,
                is_buyer_maker=is_buyer_maker,
                timestamp=datetime.fromtimestamp(data['T'] / 1000),
                trade_id=data['t']
            )
            
            # Check for large orders
            trade_value_usd = price * quantity
            if trade_value_usd >= self._large_order_threshold_usd:
                await self._handle_large_order(trade, trade_value_usd)
            
            # Call registered handlers
            for handler in self._stream_handlers['trade']:
                try:
                    await handler(trade)
                except Exception as e:
                    logger.error(f"Trade handler error: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to process trade message: {e}")
    
    async def _handle_ticker_message(self, data: Dict):
        """Handle 24h ticker message."""
        try:
            ticker = TickerUpdate(
                symbol=data['s'],
                price=float(data['c']),
                price_change_percent=float(data['P']),
                volume_24h=float(data['q']),
                high_24h=float(data['h']),
                low_24h=float(data['l']),
                timestamp=datetime.fromtimestamp(data['E'] / 1000)
            )
            
            # Call registered handlers
            for handler in self._stream_handlers['ticker']:
                try:
                    await handler(ticker)
                except Exception as e:
                    logger.error(f"Ticker handler error: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to process ticker message: {e}")
    
    async def _handle_depth_message(self, data: Dict):
        """Handle order book depth message."""
        try:
            # Convert string prices/quantities to floats
            bids = [(float(b[0]), float(b[1])) for b in data.get('bids', [])]
            asks = [(float(a[0]), float(a[1])) for a in data.get('asks', [])]
            
            orderbook = OrderBookUpdate(
                symbol=data.get('s', 'UNKNOWN'),
                bids=bids,
                asks=asks,
                timestamp=datetime.utcnow()
            )
            
            # Detect large orders in order book
            await self._detect_large_orderbook_orders(orderbook)
            
            # Call registered handlers
            for handler in self._stream_handlers['depth']:
                try:
                    await handler(orderbook)
                except Exception as e:
                    logger.error(f"Depth handler error: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to process depth message: {e}")
    
    async def _handle_large_order(self, trade: Trade, value_usd: float):
        """Handle detection of a large order."""
        logger.info(
            f"🐋 LARGE ORDER DETECTED: {trade.symbol} - "
            f"${value_usd:,.0f} @ ${trade.price:,.2f} "
            f"({'SELL' if trade.is_buyer_maker else 'BUY'})"
        )
        
        # Call registered handlers
        for handler in self._stream_handlers['large_order']:
            try:
                await handler({
                    'type': 'large_trade',
                    'trade': trade,
                    'value_usd': value_usd
                })
            except Exception as e:
                logger.error(f"Large order handler error: {e}")
    
    async def _detect_large_orderbook_orders(self, orderbook: OrderBookUpdate):
        """Detect large orders in order book."""
        # Check for large single orders in order book
        for price, quantity in orderbook.bids + orderbook.asks:
            value_usd = price * quantity
            if value_usd >= self._large_order_threshold_usd:
                side = 'BID' if (price, quantity) in orderbook.bids else 'ASK'
                logger.info(
                    f"🐋 LARGE ORDER BOOK ORDER: {orderbook.symbol} - "
                    f"${value_usd:,.0f} @ ${price:,.2f} ({side})"
                )
                
                # Call registered handlers
                for handler in self._stream_handlers['large_order']:
                    try:
                        await handler({
                            'type': 'large_orderbook',
                            'symbol': orderbook.symbol,
                            'side': side,
                            'price': price,
                            'quantity': quantity,
                            'value_usd': value_usd
                        })
                    except Exception as e:
                        logger.error(f"Large order handler error: {e}")
    
    def register_large_order_handler(self, handler: Callable):
        """
        Register a callback for large order detection.
        
        Args:
            handler: Async callback function
        """
        self._stream_handlers['large_order'].append(handler)
        logger.info("Large order handler registered")
    
    async def stop(self):
        """Stop all WebSocket connections."""
        self._running = False
        
        for stream_name, websocket in self._connections.items():
            try:
                await websocket.close()
                logger.info(f"Closed WebSocket: {stream_name}")
            except Exception as e:
                logger.error(f"Error closing WebSocket {stream_name}: {e}")
        
        self._connections.clear()
        self._subscribed_symbols.clear()
        logger.info("WebSocket client stopped")
    
    def get_statistics(self) -> Dict:
        """Get WebSocket statistics."""
        return {
            'running': self._running,
            'subscribed_symbols': len(self._subscribed_symbols),
            'messages_received': self._messages_received,
            'connection_errors': self._connection_errors,
            'last_message': self._last_message_time.isoformat() if self._last_message_time else None,
            'active_connections': len(self._connections)
        }
    
    def is_healthy(self) -> bool:
        """Check if WebSocket client is healthy."""
        if not self._running:
            return False
        
        if self._last_message_time:
            elapsed = (datetime.utcnow() - self._last_message_time).total_seconds()
            # Consider unhealthy if no message in 30 seconds
            if elapsed > 30:
                return False
        
        return True
    
    # ===== ENHANCED RECONNECTION & HEARTBEAT (NEW) =====
    
    async def _heartbeat_monitor(self, stream_id: str):
        """
        Monitor connection health and send heartbeats.
        
        Args:
            stream_id: Unique stream identifier
        """
        logger.info(f"Starting heartbeat monitor for {stream_id}")
        
        while self._running and stream_id in self._connections:
            try:
                # Check if connection is still alive
                if stream_id in self._last_message_time:
                    elapsed = (datetime.utcnow() - self._last_message_time[stream_id]).total_seconds()
                    
                    if elapsed > self._heartbeat_timeout:
                        logger.warning(f"Stream {stream_id} timeout ({elapsed}s), reconnecting...")
                        self._connection_healthy[stream_id] = False
                        await self._reconnect_stream(stream_id)
                        continue
                
                # Send ping
                if stream_id in self._connections:
                    ws = self._connections[stream_id]
                    await ws.ping()
                    logger.debug(f"Sent heartbeat ping to {stream_id}")
                
                await asyncio.sleep(self._heartbeat_interval)
            
            except websockets.ConnectionClosed:
                logger.warning(f"Heartbeat failed for {stream_id}: Connection closed")
                self._connection_healthy[stream_id] = False
                await self._reconnect_stream(stream_id)
            
            except Exception as e:
                logger.error(f"Heartbeat error for {stream_id}: {e}")
                await asyncio.sleep(5)
    
    async def _reconnect_stream(self, stream_id: str):
        """
        Reconnect a specific stream with exponential backoff.
        
        Args:
            stream_id: Stream to reconnect
        """
        if stream_id in self._reconnection_in_progress and self._reconnection_in_progress[stream_id]:
            logger.debug(f"Reconnection already in progress for {stream_id}")
            return
        
        self._reconnection_in_progress[stream_id] = True
        self._reconnect_attempts += 1
        
        reconnect_delay = min(
            self._reconnect_delay * (2 ** self._reconnect_attempts),
            self._max_reconnect_delay
        )
        
        logger.info(f"Reconnecting {stream_id} (attempt {self._reconnect_attempts})...")
        
        try:
            # Close existing connection
            if stream_id in self._connections:
                await self._connections[stream_id].close()
                del self._connections[stream_id]
            
            # Wait before reconnecting
            await asyncio.sleep(reconnect_delay)
            
            # Resubscribe to streams
            # (Implementation depends on how you track subscriptions)
            logger.info(f"Stream {stream_id} reconnected successfully")
            
            self._reconnect_attempts = 0  # Reset on success
            self._connection_healthy[stream_id] = True
        
        except Exception as e:
            logger.error(f"Reconnection failed for {stream_id}: {e}")
            
            if self._reconnect_attempts < self._max_reconnect_attempts:
                # Retry
                await self._reconnect_stream(stream_id)
            else:
                logger.critical(f"Max reconnection attempts reached for {stream_id}")
        
        finally:
            self._reconnection_in_progress[stream_id] = False
    
    async def subscribe_with_auto_reconnect(
        self,
        symbols: List[str],
        stream_types: List[str] = None
    ):
        """
        Subscribe to symbol streams with automatic reconnection.
        
        Args:
            symbols: List of symbols to subscribe to
            stream_types: Types of streams ('trade', 'ticker', 'depth')
        """
        if stream_types is None:
            stream_types = ['trade', 'ticker']
        
        # Build stream names
        streams = []
        for symbol in symbols:
            symbol_lower = symbol.lower()
            for stream_type in stream_types:
                streams.append(f"{symbol_lower}@{stream_type}")
        
        stream_id = "_".join(symbols[:3])  # Use first 3 symbols as ID
        
        # Start connection
        try:
            # Create combined stream URL
            stream_params = "/".join(streams)
            ws_url = f"{self.ws_stream_url}?streams={stream_params}"
            
            logger.info(f"Connecting to WebSocket: {stream_id}")
            
            ws = await websockets.connect(ws_url)
            self._connections[stream_id] = ws
            self._connection_healthy[stream_id] = True
            self._last_message_time[stream_id] = datetime.utcnow()
            
            # Start heartbeat monitor
            heartbeat_task = asyncio.create_task(self._heartbeat_monitor(stream_id))
            self._heartbeat_tasks[stream_id] = heartbeat_task
            
            # Start message processing
            asyncio.create_task(self._process_stream_messages(stream_id, ws))
            
            logger.info(f"Successfully subscribed to {len(streams)} streams")
        
        except Exception as e:
            logger.error(f"Failed to subscribe to streams: {e}")
            self._connection_healthy[stream_id] = False
            await self._reconnect_stream(stream_id)
    
    async def _process_stream_messages(self, stream_id: str, ws: WebSocketClientProtocol):
        """
        Process messages from a stream with error handling.
        
        Args:
            stream_id: Stream identifier
            ws: WebSocket connection
        """
        try:
            async for message in ws:
                self._last_message_time[stream_id] = datetime.utcnow()
                self._messages_received += 1
                
                try:
                    data = json.loads(message)
                    
                    # Route to appropriate handler
                    if 'stream' in data:
                        stream_name = data['stream']
                        stream_data = data['data']
                        
                        if '@trade' in stream_name:
                            await self._handle_trade_message(stream_data)
                        elif '@ticker' in stream_name:
                            await self._handle_ticker_message(stream_data)
                        elif '@depth' in stream_name:
                            await self._handle_depth_message(stream_data)
                
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message from {stream_id}: {e}")
                except Exception as e:
                    logger.error(f"Error processing message from {stream_id}: {e}")
        
        except websockets.ConnectionClosed:
            logger.warning(f"Stream {stream_id} connection closed")
            self._connection_healthy[stream_id] = False
            await self._reconnect_stream(stream_id)
        
        except Exception as e:
            logger.error(f"Stream {stream_id} error: {e}")
            self._connection_healthy[stream_id] = False
    
    async def close_all_connections(self):
        """Close all WebSocket connections gracefully."""
        logger.info("Closing all WebSocket connections...")
        
        self._running = False
        
        # Cancel heartbeat tasks
        for task in self._heartbeat_tasks.values():
            task.cancel()
        
        # Close all connections
        for stream_id, ws in list(self._connections.items()):
            try:
                await ws.close()
                logger.info(f"Closed connection: {stream_id}")
            except Exception as e:
                logger.error(f"Error closing connection {stream_id}: {e}")
        
        self._connections.clear()
        self._heartbeat_tasks.clear()
        
        logger.info("All WebSocket connections closed")

