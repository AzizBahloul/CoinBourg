"""
CoinBourg Settings Configuration
================================
Centralized configuration management using Pydantic Settings.
All sensitive data is loaded from environment variables.
"""

import os
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ===========================================
    # Application Settings
    # ===========================================
    APP_NAME: str = "CoinBourg AI Trading Bot"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    ENVIRONMENT: str = Field(default="production", description="Environment: development, staging, production")
    
    # ===========================================
    # API Keys
    # ===========================================
    # DeepSeek AI
    DEEPSEEK_API_KEY: str = Field(..., description="DeepSeek API key for AI analysis")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com", description="DeepSeek API base URL")
    DEEPSEEK_MODEL: str = Field(default="deepseek-chat", description="DeepSeek model to use")
    
    # Binance
    BINANCE_API_KEY: str = Field(..., description="Binance API key")
    BINANCE_API_SECRET: str = Field(..., description="Binance API secret")
    BINANCE_TESTNET: bool = Field(default=True, description="Use Binance testnet")
    
 
    DATABASE_URL: str = Field(
        default="postgresql://coinbourg:coinbourg_secure_password@db:5432/coinbourg",
        description="PostgreSQL connection URL"
    )
    REDIS_URL: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL"
    )
    
    # ===========================================
    # Trading Settings
    # ===========================================
    # Risk Management
    RISK_LEVEL: str = Field(default="CONSERVATIVE", description="Risk level: CONSERVATIVE, MODERATE, AGGRESSIVE")
    MAX_POSITION_SIZE_PERCENT: float = Field(default=5.0, description="Max position size as % of portfolio")
    MAX_DAILY_TRADES: int = Field(default=10, description="Maximum trades per day")
    STOP_LOSS_PERCENT: float = Field(default=2.0, description="Default stop loss percentage")
    TAKE_PROFIT_PERCENT: float = Field(default=4.0, description="Default take profit percentage")
    MAX_DRAWDOWN_PERCENT: float = Field(default=10.0, description="Maximum allowed drawdown percentage")
    
    # Trading Pairs
    TRADING_PAIRS: List[str] = Field(
        default=["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"],
        description="List of trading pairs to monitor"
    )
    BASE_CURRENCY: str = Field(default="USDT", description="Base currency for trading")
    
    # Analysis Intervals
    ANALYSIS_INTERVAL_SECONDS: int = Field(default=300, description="AI analysis interval in seconds")
    PRICE_CHECK_INTERVAL_SECONDS: int = Field(default=10, description="Price check interval in seconds")
    
    # ===========================================
    # Notification Settings
    # ===========================================
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, description="Telegram bot token")
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None, description="Telegram chat ID")
    ENABLE_NOTIFICATIONS: bool = Field(default=True, description="Enable notifications")
    
    # ===========================================
    # Web Dashboard Settings
    # ===========================================
    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8000, description="API port")
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production", description="JWT secret key")
    
    # ===========================================
    # Logging Settings
    # ===========================================
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format"
    )
    
    @validator('RISK_LEVEL')
    def validate_risk_level(cls, v):
        allowed = ['CONSERVATIVE', 'MODERATE', 'AGGRESSIVE']
        if v.upper() not in allowed:
            raise ValueError(f'Risk level must be one of: {allowed}')
        return v.upper()
    
    @validator('MAX_POSITION_SIZE_PERCENT')
    def validate_position_size(cls, v):
        if v < 0.1 or v > 100:
            raise ValueError('Position size must be between 0.1% and 100%')
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Risk level presets
RISK_PRESETS = {
    "CONSERVATIVE": {
        "max_position_size_percent": 2.0,
        "stop_loss_percent": 1.5,
        "take_profit_percent": 3.0,
        "max_daily_trades": 5,
        "max_drawdown_percent": 5.0,
        "min_confidence_score": 0.75,
    },
    "MODERATE": {
        "max_position_size_percent": 5.0,
        "stop_loss_percent": 2.5,
        "take_profit_percent": 5.0,
        "max_daily_trades": 10,
        "max_drawdown_percent": 10.0,
        "min_confidence_score": 0.65,
    },
    "AGGRESSIVE": {
        "max_position_size_percent": 10.0,
        "stop_loss_percent": 4.0,
        "take_profit_percent": 8.0,
        "max_daily_trades": 20,
        "max_drawdown_percent": 20.0,
        "min_confidence_score": 0.55,
    },
}
