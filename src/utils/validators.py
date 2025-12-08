"""
CoinBourg Validators
Input validation utilities
"""

import re
from typing import Optional, List, Tuple
from decimal import Decimal, InvalidOperation

from src.config.constants import RiskLevel


class ValidationError(Exception):
    """Custom validation error"""
    
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


def validate_symbol(symbol: str) -> Tuple[bool, str]:
    """
    Validate a trading symbol
    
    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not symbol:
        return False, "Symbol cannot be empty"
    
    if not symbol.isalnum():
        return False, "Symbol must contain only alphanumeric characters"
    
    if len(symbol) < 5 or len(symbol) > 12:
        return False, "Symbol length must be between 5 and 12 characters"
    
    # Must end with common quote currencies
    valid_quotes = ["USDT", "BUSD", "BTC", "ETH", "BNB", "EUR", "GBP"]
    if not any(symbol.upper().endswith(quote) for quote in valid_quotes):
        return False, f"Symbol must end with valid quote currency: {valid_quotes}"
    
    return True, ""


def validate_quantity(
    quantity: float,
    min_qty: float = 0.0,
    max_qty: float = float('inf'),
    step_size: float = 0.00001
) -> Tuple[bool, str]:
    """
    Validate a trading quantity
    
    Args:
        quantity: Order quantity
        min_qty: Minimum allowed quantity
        max_qty: Maximum allowed quantity
        step_size: Minimum quantity increment
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if quantity <= 0:
        return False, "Quantity must be positive"
    
    if quantity < min_qty:
        return False, f"Quantity below minimum: {min_qty}"
    
    if quantity > max_qty:
        return False, f"Quantity above maximum: {max_qty}"
    
    # Check step size using Decimal for precision
    if step_size > 0:
        from decimal import Decimal, ROUND_DOWN
        qty_decimal = Decimal(str(quantity))
        step_decimal = Decimal(str(step_size))
        remainder = qty_decimal % step_decimal
        # Allow very small remainders due to floating point
        if remainder > step_decimal * Decimal('0.001') and remainder < step_decimal * Decimal('0.999'):
            return False, f"Quantity must be multiple of {step_size}"
    
    return True, ""


def validate_price(
    price: float,
    min_price: float = 0.0,
    max_price: float = float('inf'),
    tick_size: float = 0.01
) -> Tuple[bool, str]:
    """
    Validate a trading price
    
    Args:
        price: Order price
        min_price: Minimum allowed price
        max_price: Maximum allowed price
        tick_size: Minimum price increment
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if price <= 0:
        return False, "Price must be positive"
    
    if price < min_price:
        return False, f"Price below minimum: {min_price}"
    
    if price > max_price:
        return False, f"Price above maximum: {max_price}"
    
    # Check tick size using Decimal for precision
    if tick_size > 0:
        price_decimal = Decimal(str(price))
        tick_decimal = Decimal(str(tick_size))
        remainder = price_decimal % tick_decimal
        # Allow very small remainders due to floating point
        if remainder > tick_decimal * Decimal('0.001') and remainder < tick_decimal * Decimal('0.999'):
            return False, f"Price must be multiple of {tick_size}"
    
    return True, ""


def validate_risk_level(level: str) -> Tuple[bool, str]:
    """
    Validate risk level string
    
    Args:
        level: Risk level string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_levels = [e.value for e in RiskLevel]
    
    if level.upper() not in valid_levels:
        return False, f"Invalid risk level. Must be one of: {valid_levels}"
    
    return True, ""


def validate_api_key(key: str, key_type: str = "API") -> Tuple[bool, str]:
    """
    Validate an API key format
    
    Args:
        key: API key string
        key_type: Type of key for error message
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not key:
        return False, f"{key_type} key cannot be empty"
    
    if len(key) < 10:
        return False, f"{key_type} key is too short"
    
    if " " in key:
        return False, f"{key_type} key cannot contain spaces"
    
    return True, ""


def validate_percentage(
    value: float,
    min_val: float = 0.0,
    max_val: float = 100.0,
    field_name: str = "Value"
) -> Tuple[bool, str]:
    """
    Validate a percentage value
    
    Args:
        value: Percentage value
        min_val: Minimum allowed percentage
        max_val: Maximum allowed percentage
        field_name: Name of field for error message
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if value < min_val:
        return False, f"{field_name} cannot be less than {min_val}%"
    
    if value > max_val:
        return False, f"{field_name} cannot be more than {max_val}%"
    
    return True, ""


def validate_confidence(confidence: float) -> Tuple[bool, str]:
    """
    Validate AI confidence score
    
    Args:
        confidence: Confidence value (0-1)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if confidence < 0 or confidence > 1:
        return False, "Confidence must be between 0 and 1"
    
    return True, ""


def validate_order_side(side: str) -> Tuple[bool, str]:
    """
    Validate order side
    
    Args:
        side: Order side string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_sides = ["BUY", "SELL"]
    
    if side.upper() not in valid_sides:
        return False, f"Invalid order side. Must be one of: {valid_sides}"
    
    return True, ""


def validate_order_type(order_type: str) -> Tuple[bool, str]:
    """
    Validate order type
    
    Args:
        order_type: Order type string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_types = ["MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"]
    
    if order_type.upper() not in valid_types:
        return False, f"Invalid order type. Must be one of: {valid_types}"
    
    return True, ""


def validate_timeframe(timeframe: str) -> Tuple[bool, str]:
    """
    Validate candlestick timeframe
    
    Args:
        timeframe: Timeframe string (e.g., 1m, 5m, 1h, 1d)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_timeframes = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
    
    if timeframe not in valid_timeframes:
        return False, f"Invalid timeframe. Must be one of: {valid_timeframes}"
    
    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email address format
    
    Args:
        email: Email address string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(pattern, email):
        return False, "Invalid email address format"
    
    return True, ""


def validate_url(url: str) -> Tuple[bool, str]:
    """
    Validate URL format
    
    Args:
        url: URL string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    
    if not re.match(pattern, url, re.IGNORECASE):
        return False, "Invalid URL format"
    
    return True, ""


def validate_positive_integer(value: int, field_name: str = "Value") -> Tuple[bool, str]:
    """
    Validate positive integer
    
    Args:
        value: Integer value
        field_name: Name of field for error message
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(value, int):
        return False, f"{field_name} must be an integer"
    
    if value <= 0:
        return False, f"{field_name} must be positive"
    
    return True, ""


def validate_trading_pair_list(pairs: List[str]) -> Tuple[bool, str]:
    """
    Validate a list of trading pairs
    
    Args:
        pairs: List of trading pair symbols
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not pairs:
        return False, "Trading pair list cannot be empty"
    
    if len(pairs) > 20:
        return False, "Cannot monitor more than 20 trading pairs"
    
    for pair in pairs:
        is_valid, error = validate_symbol(pair)
        if not is_valid:
            return False, f"Invalid symbol '{pair}': {error}"
    
    return True, ""


def validate_decimal_string(value: str, field_name: str = "Value") -> Tuple[bool, str]:
    """
    Validate that a string represents a valid decimal number
    
    Args:
        value: String to validate
        field_name: Name of field for error message
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        Decimal(value)
        return True, ""
    except InvalidOperation:
        return False, f"{field_name} must be a valid number"


class TradeValidator:
    """Validate complete trade parameters"""
    
    @staticmethod
    def validate_new_trade(
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> List[str]:
        """
        Validate all parameters for a new trade
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Validate symbol
        is_valid, error = validate_symbol(symbol)
        if not is_valid:
            errors.append(f"Symbol: {error}")
        
        # Validate side
        is_valid, error = validate_order_side(side)
        if not is_valid:
            errors.append(f"Side: {error}")
        
        # Validate quantity
        is_valid, error = validate_quantity(quantity)
        if not is_valid:
            errors.append(f"Quantity: {error}")
        
        # Validate price if provided
        if price is not None:
            is_valid, error = validate_price(price)
            if not is_valid:
                errors.append(f"Price: {error}")
        
        # Validate stop loss if provided
        if stop_loss is not None:
            is_valid, error = validate_price(stop_loss)
            if not is_valid:
                errors.append(f"Stop Loss: {error}")
            
            # Check stop loss logic
            if price is not None and side.upper() == "BUY" and stop_loss >= price:
                errors.append("Stop Loss: Must be below entry price for buy orders")
            elif price is not None and side.upper() == "SELL" and stop_loss <= price:
                errors.append("Stop Loss: Must be above entry price for sell orders")
        
        # Validate take profit if provided
        if take_profit is not None:
            is_valid, error = validate_price(take_profit)
            if not is_valid:
                errors.append(f"Take Profit: {error}")
            
            # Check take profit logic
            if price is not None and side.upper() == "BUY" and take_profit <= price:
                errors.append("Take Profit: Must be above entry price for buy orders")
            elif price is not None and side.upper() == "SELL" and take_profit >= price:
                errors.append("Take Profit: Must be below entry price for sell orders")
        
        return errors


class ConfigValidator:
    """Validate configuration settings"""
    
    @staticmethod
    def validate_risk_settings(
        risk_level: str,
        max_position_size: float,
        stop_loss_percent: float,
        take_profit_percent: float,
        max_daily_trades: int,
        max_drawdown: float
    ) -> List[str]:
        """
        Validate risk configuration settings
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Validate risk level
        is_valid, error = validate_risk_level(risk_level)
        if not is_valid:
            errors.append(error)
        
        # Validate position size
        is_valid, error = validate_percentage(
            max_position_size, 0.1, 50.0, "Max position size"
        )
        if not is_valid:
            errors.append(error)
        
        # Validate stop loss
        is_valid, error = validate_percentage(
            stop_loss_percent, 0.1, 20.0, "Stop loss"
        )
        if not is_valid:
            errors.append(error)
        
        # Validate take profit
        is_valid, error = validate_percentage(
            take_profit_percent, 0.1, 50.0, "Take profit"
        )
        if not is_valid:
            errors.append(error)
        
        # Validate max daily trades
        is_valid, error = validate_positive_integer(
            max_daily_trades, "Max daily trades"
        )
        if not is_valid:
            errors.append(error)
        
        # Validate max drawdown
        is_valid, error = validate_percentage(
            max_drawdown, 1.0, 50.0, "Max drawdown"
        )
        if not is_valid:
            errors.append(error)
        
        # Business logic validation
        if take_profit_percent <= stop_loss_percent:
            errors.append("Take profit percentage should be greater than stop loss")
        
        return errors
