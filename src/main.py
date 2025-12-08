

import asyncio
import logging
import sys
import signal
from datetime import datetime

import uvicorn

from src.config.settings import get_settings
from src.core.trading_engine import TradingEngine
from src.api.main import app


def setup_logging():
    """Configure application logging."""
    settings = get_settings()
    
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format=settings.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"logs/coinbourg_{datetime.now().strftime('%Y%m%d')}.log")
        ]
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


async def run_bot():
    """Run the trading bot in standalone mode."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("CoinBourg AI Trading Bot")
    logger.info("=" * 60)
    
    settings = get_settings()
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Risk Level: {settings.RISK_LEVEL}")
    logger.info(f"Trading Pairs: {settings.TRADING_PAIRS}")
    logger.info(f"Testnet Mode: {settings.BINANCE_TESTNET}")
    
    engine = TradingEngine()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received...")
        engine.is_running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await engine.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await engine.shutdown()


def run_api():
    """Run the FastAPI server."""
    setup_logging()
    
    settings = get_settings()
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="CoinBourg AI Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["bot", "api", "both"],
        default="api",
        help="Run mode: bot (trading only), api (REST API only), both"
    )
    
    args = parser.parse_args()
    
    # Create logs directory
    import os
    os.makedirs("logs", exist_ok=True)
    
    if args.mode == "bot":
        asyncio.run(run_bot())
    elif args.mode == "api":
        run_api()
    else:
        # Run both API and bot
        # The API will handle starting/stopping the bot
        run_api()


if __name__ == "__main__":
    main()
