"""
CoinBourg REST API
==================
FastAPI-based REST API for monitoring and controlling the trading bot.
Includes security features, rate limiting, and comprehensive error handling.
"""

import asyncio
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, validator
import os

from src.config.settings import get_settings, RISK_PRESETS
from src.core.trading_engine import TradingEngine
from src.utils.prometheus_monitor import get_monitor
from src.utils.health_check import get_health_check_system

logger = logging.getLogger(__name__)

# Global trading engine instance
trading_engine: Optional[TradingEngine] = None

# Prometheus monitor instance
monitor = get_monitor()

# Health check system
health_checker = get_health_check_system()

# Rate limiting storage
rate_limit_storage: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 100  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds


# ===========================================
# Security & Rate Limiting
# ===========================================

security = HTTPBasic(auto_error=False)


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    # Handle test client or missing client info
    client_ip = "unknown"
    if request.client and hasattr(request.client, 'host'):
        client_ip = request.client.host or "unknown"
    
    current_time = time.time()
    
    # Clean old timestamps
    rate_limit_storage[client_ip] = [
        ts for ts in rate_limit_storage[client_ip]
        if current_time - ts < RATE_LIMIT_WINDOW
    ]
    
    if len(rate_limit_storage[client_ip]) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."}
        )
    
    rate_limit_storage[client_ip].append(current_time)
    return await call_next(request)


def verify_api_key(credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> bool:
    """Verify API key for protected endpoints - DISABLED for open access."""
    # Authentication disabled - allow all requests
    return True


# ===========================================
# Pydantic Models with Validation
# ===========================================

class StatusResponse(BaseModel):
    """Trading bot status response."""
    is_running: bool
    portfolio_value: float
    total_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    open_positions: int
    positions: Dict
    daily_trades: int
    max_daily_trades: int
    risk_level: str


class TradeResponse(BaseModel):
    """Trade information response."""
    id: str
    symbol: str
    side: str
    entry_price: float
    quantity: float
    status: str
    stop_loss: Optional[float]
    take_profit: Optional[float]
    exit_price: Optional[float]
    pnl: Optional[float]
    pnl_percent: Optional[float]
    entry_time: str
    exit_time: Optional[str]
    ai_confidence: float
    ai_reasoning: str


class AnalysisRequest(BaseModel):
    """Market analysis request with validation."""
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)", min_length=5, max_length=12)
    
    @validator('symbol')
    def validate_symbol(cls, v):
        v = v.upper().strip()
        if not v.isalnum():
            raise ValueError('Symbol must contain only alphanumeric characters')
        valid_quotes = ["USDT", "BUSD", "BTC", "ETH", "BNB"]
        if not any(v.endswith(quote) for quote in valid_quotes):
            raise ValueError(f'Symbol must end with valid quote currency: {valid_quotes}')
        return v


class AnalysisResponse(BaseModel):
    """Market analysis response."""
    symbol: str
    sentiment: str
    action: str
    confidence: float
    entry_price: Optional[float]
    stop_loss: float
    take_profit: float
    reasoning: str
    timestamp: str


class RiskSettingsRequest(BaseModel):
    """Risk settings update request with validation."""
    risk_level: str = Field(..., description="CONSERVATIVE, MODERATE, or AGGRESSIVE")
    
    @validator('risk_level')
    def validate_risk_level(cls, v):
        v = v.upper().strip()
        valid_levels = ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]
        if v not in valid_levels:
            raise ValueError(f'Risk level must be one of: {valid_levels}')
        return v


class ManualTradeRequest(BaseModel):
    """Manual trade request with validation."""
    symbol: str = Field(..., min_length=5, max_length=12)
    action: str = Field(..., description="BUY or SELL")
    quantity: Optional[float] = Field(None, description="Trade quantity", gt=0)
    quote_quantity: Optional[float] = Field(None, description="Quote quantity (USDT)", gt=0)
    
    @validator('symbol')
    def validate_symbol(cls, v):
        v = v.upper().strip()
        if not v.isalnum():
            raise ValueError('Symbol must contain only alphanumeric characters')
        return v
    
    @validator('action')
    def validate_action(cls, v):
        v = v.upper().strip()
        if v not in ['BUY', 'SELL']:
            raise ValueError('Action must be BUY or SELL')
        return v


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    binance_connected: bool
    deepseek_connected: bool
    version: str


# ===========================================
# Application Lifecycle
# ===========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global trading_engine
    
    logger.info("Starting CoinBourg API...")
    
    # Initialize trading engine
    trading_engine = TradingEngine()
    
    try:
        await trading_engine.initialize()
        logger.info("Trading engine initialized")
    except Exception as e:
        logger.error(f"Failed to initialize trading engine: {e}")
    
    yield
    
    # Cleanup
    if trading_engine:
        await trading_engine.shutdown()
    
    logger.info("CoinBourg API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    # Determine allowed origins based on environment
    if settings.ENVIRONMENT == "production":
        allowed_origins = [
            f"http://{settings.API_HOST}",
            f"https://{settings.API_HOST}",
        ]
    else:
        allowed_origins = ["*"]
    
    app = FastAPI(
        title="CoinBourg AI Trading Bot API",
        description="REST API for monitoring and controlling the AI-powered crypto trading bot",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,  # Disable docs in production
        redoc_url="/redoc" if settings.DEBUG else None,
    )
    
    # Add CORS middleware with security
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
        max_age=86400,  # Cache preflight for 24 hours
    )
    
    # Add rate limiting (as middleware)
    @app.middleware("http")
    async def rate_limiter(request: Request, call_next):
        return await rate_limit_middleware(request, call_next)
    
    return app


# Create app instance
app = create_app()


# ===========================================
# Dependency Injection
# ===========================================

async def get_engine() -> TradingEngine:
    """Dependency to get trading engine instance."""
    if trading_engine is None:
        raise HTTPException(status_code=503, detail="Trading engine not initialized")
    return trading_engine


# ===========================================
# API Endpoints
# ===========================================

@app.get("/", tags=["General"])
async def root():
    """Serve the dashboard UI."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    index_file = os.path.join(static_dir, "index.html")
    
    if os.path.exists(index_file):
        return FileResponse(index_file)
    else:
        # Fallback to JSON response if HTML not found
        return {
            "name": "CoinBourg AI Trading Bot",
            "version": get_settings().APP_VERSION,
            "status": "running"
        }


@app.get("/testing", tags=["General"])
async def testing_dashboard():
    """Serve the testing dashboard UI."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    testing_file = os.path.join(static_dir, "testing.html")
    
    if os.path.exists(testing_file):
        return FileResponse(testing_file)
    else:
        raise HTTPException(status_code=404, detail="Testing dashboard not found")


@app.get("/api/info", tags=["General"])
async def api_info():
    """API information endpoint."""
    return {
        "name": "CoinBourg AI Trading Bot",
        "version": get_settings().APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    monitor.update_uptime()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "uptime_seconds": monitor.system_uptime._value.get()
    }


@app.get("/health/detailed")
async def detailed_health_check(engine: TradingEngine = Depends(get_engine)):
    """
    Comprehensive health check with component status.
    
    Checks:
    - Binance API connectivity
    - DeepSeek AI availability
    - Database connection
    - Redis cache (if configured)
    """
    from src.config.settings import get_settings
    settings = get_settings()
    
    # Check all components
    health_status = await health_checker.check_all_components(
        binance_client=engine.binance if engine else None,
        deepseek_client=engine.deepseek if engine else None,
        state_manager=engine.state_manager if engine else None,
        redis_url=settings.REDIS_URL if hasattr(settings, 'REDIS_URL') else None
    )
    
    overall_health = health_checker.get_overall_health()
    
    return overall_health


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text format for scraping.
    """
    return Response(
        content=monitor.generate_metrics(),
        media_type="text/plain; version=0.0.4"
    )


@app.get("/status", response_model=StatusResponse, tags=["Trading"])
async def get_status(engine: TradingEngine = Depends(get_engine)):
    """Get current trading bot status."""
    return engine.get_status()


@app.get("/trades", response_model=List[TradeResponse], tags=["Trading"])
async def get_trades(
    limit: int = 50,
    engine: TradingEngine = Depends(get_engine)
):
    """Get recent trades."""
    trades = engine.trades[-limit:]
    
    return [
        TradeResponse(
            id=t.id,
            symbol=t.symbol,
            side=t.side,
            entry_price=t.entry_price,
            quantity=t.quantity,
            status=t.status.value,
            stop_loss=t.stop_loss,
            take_profit=t.take_profit,
            exit_price=t.exit_price,
            pnl=t.pnl,
            pnl_percent=t.pnl_percent,
            entry_time=t.entry_time.isoformat(),
            exit_time=t.exit_time.isoformat() if t.exit_time else None,
            ai_confidence=t.ai_confidence,
            ai_reasoning=t.ai_reasoning
        )
        for t in reversed(trades)
    ]


@app.get("/positions", tags=["Trading"])
async def get_positions(engine: TradingEngine = Depends(get_engine)):
    """Get current open positions."""
    positions = {}
    
    for symbol, pos in engine.positions.items():
        positions[symbol] = {
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "current_price": pos.current_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "unrealized_pnl_percent": pos.unrealized_pnl_percent,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit
        }
    
    return positions


@app.post("/analyze", response_model=AnalysisResponse, tags=["Analysis"])
async def analyze_symbol(
    request: AnalysisRequest,
    engine: TradingEngine = Depends(get_engine)
):
    """Perform AI analysis on a symbol."""
    try:
        decision = await engine.analyze_and_decide(request.symbol)
        
        return AnalysisResponse(
            symbol=request.symbol,
            sentiment=decision.get('sentiment', 'NEUTRAL'),
            action=decision.get('action', 'HOLD'),
            confidence=decision.get('confidence', 0),
            entry_price=decision.get('entry_price'),
            stop_loss=decision.get('stop_loss', 0),
            take_profit=decision.get('take_profit', 0),
            reasoning=decision.get('reasoning', ''),
            timestamp=decision.get('timestamp', datetime.utcnow().isoformat())
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market/{symbol}", tags=["Market Data"])
async def get_market_data(
    symbol: str,
    engine: TradingEngine = Depends(get_engine)
):
    """Get market data for a symbol."""
    try:
        data = await engine.get_market_data(symbol)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/balance", tags=["Account"])
async def get_balance(engine: TradingEngine = Depends(get_engine)):
    """Get account balances."""
    try:
        balances = await engine.binance.get_balances()
        portfolio_value = await engine.binance.get_portfolio_value()
        
        return {
            "balances": balances,
            "portfolio_value": portfolio_value
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trade", tags=["Trading"])
async def manual_trade(
    request: ManualTradeRequest,
    engine: TradingEngine = Depends(get_engine)
):
    """Execute a manual trade."""
    if request.action.upper() not in ['BUY', 'SELL']:
        raise HTTPException(status_code=400, detail="Action must be BUY or SELL")
    
    try:
        if request.action.upper() == 'BUY':
            if request.quote_quantity:
                order = await engine.binance.market_buy(
                    request.symbol,
                    quote_quantity=request.quote_quantity
                )
            elif request.quantity:
                order = await engine.binance.market_buy(
                    request.symbol,
                    quantity=request.quantity
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Either quantity or quote_quantity must be provided"
                )
        else:
            if not request.quantity:
                raise HTTPException(
                    status_code=400,
                    detail="Quantity must be provided for sell orders"
                )
            order = await engine.binance.market_sell(request.symbol, request.quantity)
        
        return order
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/start", tags=["Control"])
async def start_trading(
    background_tasks: BackgroundTasks,
    engine: TradingEngine = Depends(get_engine)
):
    """Start the automated trading loop."""
    if engine.is_running:
        return {"status": "already_running"}
    
    background_tasks.add_task(engine.run)
    
    return {"status": "started"}


@app.post("/stop", tags=["Control"])
async def stop_trading(engine: TradingEngine = Depends(get_engine)):
    """Stop the automated trading loop."""
    engine.is_running = False
    return {"status": "stopped"}


@app.get("/risk-settings", tags=["Settings"])
async def get_risk_settings(engine: TradingEngine = Depends(get_engine)):
    """Get current risk settings."""
    return {
        "risk_level": engine.settings.RISK_LEVEL,
        "max_position_size_percent": engine.max_position_size_percent,
        "stop_loss_percent": engine.stop_loss_percent,
        "take_profit_percent": engine.take_profit_percent,
        "max_daily_trades": engine.max_daily_trades,
        "max_drawdown_percent": engine.max_drawdown_percent,
        "min_confidence_score": engine.min_confidence_score,
        "available_presets": list(RISK_PRESETS.keys())
    }


@app.post("/risk-settings", tags=["Settings"])
async def update_risk_settings(
    request: RiskSettingsRequest,
    engine: TradingEngine = Depends(get_engine)
):
    """Update risk settings."""
    if request.risk_level.upper() not in RISK_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid risk level. Must be one of: {list(RISK_PRESETS.keys())}"
        )
    
    preset = RISK_PRESETS[request.risk_level.upper()]
    
    # Update engine attributes
    engine.max_position_size_percent = preset["max_position_size_percent"]
    engine.stop_loss_percent = preset["stop_loss_percent"]
    engine.take_profit_percent = preset["take_profit_percent"]
    engine.max_daily_trades = preset["max_daily_trades"]
    engine.max_drawdown_percent = preset["max_drawdown_percent"]
    engine.min_confidence_score = preset["min_confidence_score"]
    
    # Update settings object so status endpoint reflects the change
    engine.settings.RISK_LEVEL = request.risk_level.upper()
    
    return {
        "status": "updated",
        "risk_level": request.risk_level.upper(),
        "settings": preset
    }


@app.get("/metrics", tags=["Metrics"])
async def get_metrics(engine: TradingEngine = Depends(get_engine)):
    """Get trading metrics."""
    total_trades = engine.metrics['total_trades']
    winning = engine.metrics['winning_trades']
    losing = engine.metrics['losing_trades']
    
    return {
        "total_trades": total_trades,
        "winning_trades": winning,
        "losing_trades": losing,
        "win_rate": (winning / total_trades * 100) if total_trades > 0 else 0,
        "total_pnl": engine.metrics['total_pnl'],
        "portfolio_value": engine.metrics['current_value'],
        "peak_value": engine.metrics['peak_value'],
        "max_drawdown": (
            (engine.metrics['peak_value'] - engine.metrics['current_value']) /
            engine.metrics['peak_value'] * 100
            if engine.metrics['peak_value'] > 0 else 0
        )
    }


@app.get("/api/v1/ai/thoughts", tags=["AI"])
async def get_ai_thoughts(
    limit: int = 20,
    engine: TradingEngine = Depends(get_engine),
    authenticated: bool = Depends(verify_api_key)
):
    """Get recent AI thoughts and analysis."""
    return engine.ai_thoughts[:limit]


# ===========================================
# Testing & Validation Endpoints
# ===========================================

from src.testing.test_engine import TestEngine, TestType, TestConfiguration
from src.testing.test_tracker import TestDatabaseManager

test_engine_instance = None
test_db_manager = None

async def get_test_engine():
    """Get or create test engine instance."""
    global test_engine_instance, test_db_manager
    if test_engine_instance is None:
        test_db_manager = TestDatabaseManager()
        await test_db_manager.connect()
        test_engine_instance = TestEngine(test_db_manager)
    return test_engine_instance


class TestRunRequest(BaseModel):
    """Request to run a test."""
    test_type: str = Field(..., description="Type of test to run")
    symbols: List[str] = Field(..., description="Trading pairs to test")
    start_date: str = Field(..., description="Start date ISO format")
    end_date: str = Field(..., description="End date ISO format")
    initial_capital: float = Field(default=10000.0, gt=0)
    risk_level: str = Field(default="MODERATE")
    parameters: Dict = Field(default_factory=dict)


@app.post("/api/tests/run", tags=["Testing"])
async def run_test(
    request: TestRunRequest,
    background_tasks: BackgroundTasks,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Run a comprehensive test.
    
    Available test types:
    - backtesting: Test on historical data
    - paper_trading: Real-time simulation
    - forward_testing: Test on new data
    - out_of_sample: Validate on separate dataset
    - monte_carlo: Randomized simulations
    - signal_validation: Validate buy/sell signals
    - prediction_accuracy: Measure prediction accuracy
    - benchmark_comparison: Compare vs buy-and-hold
    - live_testing: Small capital real testing
    - post_trade_analysis: Review completed trades
    """
    try:
        engine = await get_test_engine()
        
        # Parse test type
        test_type = TestType(request.test_type.lower())
        
        # Create configuration
        config = TestConfiguration(
            test_type=test_type,
            symbols=request.symbols,
            start_date=datetime.fromisoformat(request.start_date),
            end_date=datetime.fromisoformat(request.end_date),
            initial_capital=request.initial_capital,
            risk_level=request.risk_level,
            parameters=request.parameters
        )
        
        # Run test in background
        background_tasks.add_task(engine.run_test, test_type, config)
        
        return {
            "status": "Test started",
            "test_type": test_type.value,
            "symbols": request.symbols,
            "message": "Test is running in background. Use GET /api/tests/results to check progress."
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid test type: {str(e)}")
    except Exception as e:
        logger.error(f"Error starting test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tests/results", tags=["Testing"])
async def get_test_results(
    test_run_id: Optional[str] = None,
    test_type: Optional[str] = None,
    limit: int = 100,
    authenticated: bool = Depends(verify_api_key)
):
    """Get test results."""
    try:
        engine = await get_test_engine()
        
        test_type_enum = TestType(test_type.lower()) if test_type else None
        
        results = await engine.get_test_results(
            test_run_id=test_run_id,
            test_type=test_type_enum,
            limit=limit
        )
        
        return {
            "total": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error getting test results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tests/{test_run_id}/predictions", tags=["Testing"])
async def get_test_predictions(
    test_run_id: str,
    symbol: Optional[str] = None,
    authenticated: bool = Depends(verify_api_key)
):
    """Get predictions for a specific test run."""
    try:
        engine = await get_test_engine()
        
        predictions = await engine.get_prediction_tracker(
            symbol=symbol,
            test_run_id=test_run_id
        )
        
        return {
            "test_run_id": test_run_id,
            "total_predictions": len(predictions),
            "predictions": predictions
        }
        
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tests/best-symbols", tags=["Testing"])
async def get_best_performing_symbols(
    test_type: Optional[str] = None,
    limit: int = 10,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Get cryptocurrencies with best prediction accuracy.
    
    Shows which coins the model predicts most successfully.
    """
    try:
        engine = await get_test_engine()
        
        test_type_enum = TestType(test_type.lower()) if test_type else None
        
        best_symbols = await engine.get_best_performing_symbols(
            test_type=test_type_enum,
            limit=limit
        )
        
        return {
            "best_performing_symbols": best_symbols
        }
        
    except Exception as e:
        logger.error(f"Error getting best symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tests/types", tags=["Testing"])
async def get_available_test_types():
    """Get all available test types and their descriptions."""
    return {
        "test_types": [
            {
                "name": "backtesting",
                "description": "Test strategy on historical market data"
            },
            {
                "name": "paper_trading",
                "description": "Real-time predictions without real money"
            },
            {
                "name": "forward_testing",
                "description": "Test on new, unseen data after backtesting"
            },
            {
                "name": "out_of_sample",
                "description": "Validate on separate dataset not used in training"
            },
            {
                "name": "monte_carlo",
                "description": "Randomized simulations to test robustness"
            },
            {
                "name": "signal_validation",
                "description": "Check if buy/sell signals lead to profit"
            },
            {
                "name": "prediction_accuracy",
                "description": "Measure how often predictions are correct"
            },
            {
                "name": "benchmark_comparison",
                "description": "Compare vs buy-and-hold strategy"
            },
            {
                "name": "live_testing",
                "description": "Small capital real market testing"
            },
            {
                "name": "post_trade_analysis",
                "description": "Review and analyze completed trades"
            }
        ]
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )


# WebSocket endpoint for real-time updates
@app.websocket("/ws/trading")
async def websocket_trading_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time trading data streaming.
    
    Streams:
    - Portfolio value updates
    - Position changes
    - Trade executions
    - AI predictions
    - System health
    """
    await websocket.accept()
    logger.info(f"WebSocket client connected from {websocket.client}")
    
    try:
        # Get trading engine
        engine = await get_engine()
        
        if not engine:
            await websocket.send_json({"error": "Trading engine not initialized"})
            await websocket.close()
            return
        
        # Send initial status
        await websocket.send_json({
            "type": "initial_status",
            "data": engine.get_status()
        })
        
        # Stream updates
        while True:
            try:
                # Send portfolio update every 5 seconds
                status = engine.get_status()
                
                await websocket.send_json({
                    "type": "portfolio_update",
                    "data": {
                        "portfolio_value": status.get('portfolio_value'),
                        "available_balance": status.get('available_balance'),
                        "open_positions": status.get('open_positions'),
                        "total_pnl": status.get('total_pnl'),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                })
                
                # Send positions update
                if engine.positions:
                    await websocket.send_json({
                        "type": "positions_update",
                        "data": [
                            {
                                "symbol": pos.symbol,
                                "quantity": pos.quantity,
                                "entry_price": pos.entry_price,
                                "current_price": pos.current_price,
                                "unrealized_pnl": pos.unrealized_pnl,
                                "unrealized_pnl_percent": pos.unrealized_pnl_percent
                            }
                            for pos in engine.positions.values()
                        ]
                    })
                
                # Send recent trade if any
                if engine.trades and len(engine.trades) > 0:
                    latest_trade = engine.trades[-1]
                    await websocket.send_json({
                        "type": "latest_trade",
                        "data": {
                            "symbol": latest_trade.symbol,
                            "side": latest_trade.side,
                            "entry_price": latest_trade.entry_price,
                            "quantity": latest_trade.quantity,
                            "pnl": latest_trade.pnl if hasattr(latest_trade, 'pnl') else None,
                            "timestamp": latest_trade.entry_time.isoformat()
                        }
                    })
                
                await asyncio.sleep(5)
            
            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected")
                break
            
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_json({"error": str(e)})
                await asyncio.sleep(5)
    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    
    finally:
        try:
            await websocket.close()
        except:
            pass


@app.websocket("/ws/prices/{symbol}")
async def websocket_price_stream(websocket: WebSocket, symbol: str):
    """
    WebSocket endpoint for real-time price streaming of a specific symbol.
    
    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT)
    """
    await websocket.accept()
    logger.info(f"Price stream WebSocket connected for {symbol}")
    
    try:
        engine = await get_engine()
        
        if not engine or not engine.websocket_client:
            await websocket.send_json({"error": "WebSocket client not available"})
            await websocket.close()
            return
        
        # Stream price updates
        while True:
            try:
                # Get current price
                price = await engine.binance.get_ticker_price(symbol)
                ticker_data = await engine.binance.get_ticker_24h(symbol)
                
                await websocket.send_json({
                    "symbol": symbol,
                    "price": price,
                    "price_change_24h": float(ticker_data.get('priceChangePercent', 0)),
                    "volume_24h": float(ticker_data.get('volume', 0)),
                    "high_24h": float(ticker_data.get('highPrice', 0)),
                    "low_24h": float(ticker_data.get('lowPrice', 0)),
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                await asyncio.sleep(1)  # Update every second
            
            except WebSocketDisconnect:
                break
            
            except Exception as e:
                logger.error(f"Price stream error for {symbol}: {e}")
                await asyncio.sleep(5)
    
    except WebSocketDisconnect:
        logger.info(f"Price stream disconnected for {symbol}")
    
    finally:
        try:
            await websocket.close()
        except:
            pass

