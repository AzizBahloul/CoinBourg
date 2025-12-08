"""
CoinBourg Helper Utilities
Common utility functions used throughout the application
"""

import hashlib
import hmac
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from decimal import Decimal, ROUND_DOWN
import json

logger = logging.getLogger(__name__)


def generate_timestamp() -> int:
    """Generate current timestamp in milliseconds"""
    return int(time.time() * 1000)


def format_timestamp(timestamp_ms: int) -> str:
    """Format millisecond timestamp to ISO string"""
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.isoformat()


def parse_timestamp(iso_string: str) -> datetime:
    """Parse ISO timestamp string to datetime"""
    return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))


def utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


def create_signature(secret: str, data: str) -> str:
    """
    Create HMAC-SHA256 signature for API authentication
    
    Args:
        secret: API secret key
        data: Data string to sign
        
    Returns:
        Hex-encoded signature
    """
    return hmac.new(
        secret.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def round_price(price: float, tick_size: float = 0.01) -> float:
    """
    Round price to valid tick size
    
    Args:
        price: Price to round
        tick_size: Minimum price increment
        
    Returns:
        Rounded price
    """
    if tick_size <= 0:
        return price
    
    decimal_price = Decimal(str(price))
    decimal_tick = Decimal(str(tick_size))
    
    rounded = (decimal_price / decimal_tick).quantize(
        Decimal('1'), 
        rounding=ROUND_DOWN
    ) * decimal_tick
    
    return float(rounded)


def round_quantity(quantity: float, step_size: float = 0.00001) -> float:
    """
    Round quantity to valid step size
    
    Args:
        quantity: Quantity to round
        step_size: Minimum quantity increment
        
    Returns:
        Rounded quantity
    """
    if step_size <= 0:
        return quantity
    
    decimal_qty = Decimal(str(quantity))
    decimal_step = Decimal(str(step_size))
    
    rounded = (decimal_qty / decimal_step).quantize(
        Decimal('1'), 
        rounding=ROUND_DOWN
    ) * decimal_step
    
    return float(rounded)


def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """
    Calculate percentage change between two values
    
    Args:
        old_value: Original value
        new_value: New value
        
    Returns:
        Percentage change (positive = increase)
    """
    if old_value == 0:
        return 0.0
    return ((new_value - old_value) / old_value) * 100


def format_currency(amount: float, decimals: int = 2) -> str:
    """
    Format amount as currency string
    
    Args:
        amount: Amount to format
        decimals: Number of decimal places
        
    Returns:
        Formatted string like "$1,234.56"
    """
    return f"${amount:,.{decimals}f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Format value as percentage string
    
    Args:
        value: Value to format (0.05 = 5%)
        decimals: Number of decimal places
        
    Returns:
        Formatted string like "5.00%"
    """
    return f"{value * 100:.{decimals}f}%"


def format_quantity(quantity: float, decimals: int = 6) -> str:
    """
    Format quantity with appropriate decimals
    
    Args:
        quantity: Quantity to format
        decimals: Number of decimal places
        
    Returns:
        Formatted string
    """
    return f"{quantity:.{decimals}f}"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero
    
    Args:
        numerator: Top number
        denominator: Bottom number
        default: Value to return if denominator is zero
        
    Returns:
        Result of division or default
    """
    if denominator == 0:
        return default
    return numerator / denominator


def clamp(value: float, min_value: float, max_value: float) -> float:
    """
    Clamp a value between min and max
    
    Args:
        value: Value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Clamped value
    """
    return max(min_value, min(value, max_value))


def moving_average(data: List[float], period: int) -> Optional[float]:
    """
    Calculate simple moving average
    
    Args:
        data: List of values
        period: Number of periods
        
    Returns:
        Moving average or None if insufficient data
    """
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


def exponential_moving_average(
    data: List[float], 
    period: int, 
    smoothing: float = 2.0
) -> Optional[float]:
    """
    Calculate exponential moving average
    
    Args:
        data: List of values
        period: Number of periods
        smoothing: Smoothing factor
        
    Returns:
        EMA or None if insufficient data
    """
    if len(data) < period:
        return None
    
    multiplier = smoothing / (period + 1)
    ema = sum(data[:period]) / period  # Start with SMA
    
    for value in data[period:]:
        ema = (value * multiplier) + (ema * (1 - multiplier))
    
    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index
    
    Args:
        prices: List of closing prices
        period: RSI period (default 14)
        
    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None
    
    # Calculate price changes
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    
    # Separate gains and losses
    gains = [max(0, change) for change in changes]
    losses = [abs(min(0, change)) for change in changes]
    
    # Calculate average gains and losses
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_macd(
    prices: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Optional[Dict[str, float]]:
    """
    Calculate MACD (Moving Average Convergence Divergence)
    
    Args:
        prices: List of closing prices
        fast_period: Fast EMA period
        slow_period: Slow EMA period
        signal_period: Signal line EMA period
        
    Returns:
        Dictionary with macd, signal, and histogram values
    """
    if len(prices) < slow_period + signal_period:
        return None
    
    fast_ema = exponential_moving_average(prices, fast_period)
    slow_ema = exponential_moving_average(prices, slow_period)
    
    if fast_ema is None or slow_ema is None:
        return None
    
    macd_line = fast_ema - slow_ema
    
    # For signal line, we need historical MACD values
    macd_values = []
    for i in range(slow_period, len(prices)):
        fast = exponential_moving_average(prices[:i+1], fast_period)
        slow = exponential_moving_average(prices[:i+1], slow_period)
        if fast and slow:
            macd_values.append(fast - slow)
    
    if len(macd_values) < signal_period:
        return None
    
    signal = exponential_moving_average(macd_values, signal_period)
    
    if signal is None:
        return None
    
    histogram = macd_line - signal
    
    return {
        "macd": macd_line,
        "signal": signal,
        "histogram": histogram
    }


def calculate_bollinger_bands(
    prices: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Optional[Dict[str, float]]:
    """
    Calculate Bollinger Bands
    
    Args:
        prices: List of closing prices
        period: SMA period
        std_dev: Number of standard deviations
        
    Returns:
        Dictionary with upper, middle, lower bands
    """
    if len(prices) < period:
        return None
    
    recent_prices = prices[-period:]
    middle = sum(recent_prices) / period
    
    # Calculate standard deviation
    variance = sum((p - middle) ** 2 for p in recent_prices) / period
    std = variance ** 0.5
    
    return {
        "upper": middle + (std * std_dev),
        "middle": middle,
        "lower": middle - (std * std_dev),
        "bandwidth": (std * std_dev * 2) / middle * 100  # As percentage
    }


def calculate_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Optional[float]:
    """
    Calculate Average True Range
    
    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of closing prices
        period: ATR period
        
    Returns:
        ATR value or None if insufficient data
    """
    if len(highs) < period + 1:
        return None
    
    true_ranges = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],  # High - Low
            abs(highs[i] - closes[i-1]),  # High - Previous Close
            abs(lows[i] - closes[i-1])  # Low - Previous Close
        )
        true_ranges.append(tr)
    
    return sum(true_ranges[-period:]) / period


def json_serialize(obj: Any) -> str:
    """
    Serialize object to JSON with datetime handling
    
    Args:
        obj: Object to serialize
        
    Returns:
        JSON string
    """
    def default_handler(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")
    
    return json.dumps(obj, default=default_handler)


def json_deserialize(json_str: str) -> Any:
    """
    Deserialize JSON string to object
    
    Args:
        json_str: JSON string
        
    Returns:
        Deserialized object
    """
    return json.loads(json_str)


def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for retrying a function with exponential backoff
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch
        
    Returns:
        Function result or raises last exception
    """
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        last_exception = None
        delay = base_delay
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, max_delay)
        
        raise last_exception
    
    return wrapper


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split a list into chunks of specified size
    
    Args:
        lst: List to split
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def deep_merge(dict1: Dict, dict2: Dict) -> Dict:
    """
    Deep merge two dictionaries
    
    Args:
        dict1: Base dictionary
        dict2: Dictionary to merge into dict1
        
    Returns:
        Merged dictionary
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def sanitize_symbol(symbol: str) -> str:
    """
    Sanitize and normalize a trading symbol
    
    Args:
        symbol: Symbol string
        
    Returns:
        Normalized uppercase symbol
    """
    return symbol.upper().strip().replace(" ", "").replace("-", "")
