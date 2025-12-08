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

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, validator
import os

from src.config.settings import get_settings, RISK_PRESETS
from src.core.trading_engine import TradingEngine

logger = logging.getLogger(__name__)

# Global trading engine instance
trading_engine: Optional[TradingEngine] = None

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
    """Verify API key for protected endpoints."""
    settings = get_settings()
    
    # Allow unauthenticated in development
    if settings.DEBUG and settings.ENVIRONMENT == "development":
        return True
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    # Compare against configured secret
    correct_password = secrets.compare_digest(
        credentials.password,
        settings.SECRET_KEY
    )
    
    if not correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
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


@app.get("/api/info", tags=["General"])
async def api_info():
    """API information endpoint."""
    return {
        "name": "CoinBourg AI Trading Bot",
        "version": get_settings().APP_VERSION,
        "status": "running"
    }


@app.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check(engine: TradingEngine = Depends(get_engine)):
    """Health check endpoint."""
    binance_ok = await engine.binance.test_connectivity()
    deepseek_ok = await engine.deepseek.test_connection()
    
    return HealthResponse(
        status="healthy" if binance_ok and deepseek_ok else "degraded",
        timestamp=datetime.utcnow().isoformat(),
        binance_connected=binance_ok,
        deepseek_connected=deepseek_ok,
        version=get_settings().APP_VERSION
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
    
    engine.max_position_size_percent = preset["max_position_size_percent"]
    engine.stop_loss_percent = preset["stop_loss_percent"]
    engine.take_profit_percent = preset["take_profit_percent"]
    engine.max_daily_trades = preset["max_daily_trades"]
    engine.max_drawdown_percent = preset["max_drawdown_percent"]
    engine.min_confidence_score = preset["min_confidence_score"]
    
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


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )
