"""
Prometheus Monitoring for CoinBourg
====================================
Metrics collection and monitoring endpoints for production observability.
"""

import logging
from datetime import datetime
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, Summary, Info, generate_latest, REGISTRY
from prometheus_client import CollectorRegistry
import time

logger = logging.getLogger(__name__)


class PrometheusMonitor:
    """
    Prometheus metrics collector for trading system.
    
    Tracks:
    - Trade executions and outcomes
    - API latencies and errors
    - Portfolio value and positions
    - AI decision metrics
    - System health
    """
    
    def __init__(self):
        """Initialize Prometheus metrics."""
        # Trade Metrics
        self.trades_total = Counter(
            'coinbourg_trades_total',
            'Total number of trades executed',
            ['symbol', 'side', 'outcome']
        )
        
        self.trade_pnl = Summary(
            'coinbourg_trade_pnl_usd',
            'Trade profit/loss in USD',
            ['symbol']
        )
        
        self.trade_duration = Histogram(
            'coinbourg_trade_duration_seconds',
            'Time from entry to exit',
            ['symbol'],
            buckets=[60, 300, 900, 1800, 3600, 7200, 14400, 28800, 86400]  # 1min to 24h
        )
        
        # Portfolio Metrics
        self.portfolio_value = Gauge(
            'coinbourg_portfolio_value_usd',
            'Current total portfolio value in USD'
        )
        
        self.available_balance = Gauge(
            'coinbourg_available_balance_usd',
            'Available trading balance in USD'
        )
        
        self.open_positions = Gauge(
            'coinbourg_open_positions',
            'Number of open positions'
        )
        
        self.position_value = Gauge(
            'coinbourg_position_value_usd',
            'Value of individual positions',
            ['symbol']
        )
        
        self.unrealized_pnl = Gauge(
            'coinbourg_unrealized_pnl_usd',
            'Unrealized profit/loss',
            ['symbol']
        )
        
        # API Performance Metrics
        self.api_requests_total = Counter(
            'coinbourg_api_requests_total',
            'Total API requests',
            ['service', 'endpoint', 'status']
        )
        
        self.api_latency = Histogram(
            'coinbourg_api_latency_seconds',
            'API request latency',
            ['service', 'endpoint'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        )
        
        self.api_errors = Counter(
            'coinbourg_api_errors_total',
            'Total API errors',
            ['service', 'error_type']
        )
        
        # AI Decision Metrics
        self.ai_predictions = Counter(
            'coinbourg_ai_predictions_total',
            'Total AI predictions',
            ['action', 'confidence_range']
        )
        
        self.ai_accuracy = Gauge(
            'coinbourg_ai_accuracy_percent',
            'AI prediction accuracy',
            ['action', 'timeframe']
        )
        
        self.ai_latency = Histogram(
            'coinbourg_ai_latency_seconds',
            'AI analysis latency',
            ['provider'],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
        )
        
        # Risk Metrics
        self.drawdown_current = Gauge(
            'coinbourg_drawdown_current_percent',
            'Current drawdown percentage'
        )
        
        self.drawdown_max = Gauge(
            'coinbourg_drawdown_max_percent',
            'Maximum drawdown percentage'
        )
        
        self.var_95 = Gauge(
            'coinbourg_var_95_usd',
            'Value at Risk (95% confidence)'
        )
        
        self.sharpe_ratio = Gauge(
            'coinbourg_sharpe_ratio',
            'Current Sharpe ratio'
        )
        
        # System Health Metrics
        self.system_uptime = Gauge(
            'coinbourg_system_uptime_seconds',
            'System uptime in seconds'
        )
        
        self.circuit_breaker_state = Gauge(
            'coinbourg_circuit_breaker_open',
            'Circuit breaker state (1=open, 0=closed)',
            ['service']
        )
        
        self.memory_usage = Gauge(
            'coinbourg_memory_usage_bytes',
            'Memory usage in bytes',
            ['type']
        )
        
        # Market Data Metrics
        self.market_scans = Counter(
            'coinbourg_market_scans_total',
            'Total market scans performed'
        )
        
        self.coins_analyzed = Counter(
            'coinbourg_coins_analyzed_total',
            'Total coins analyzed'
        )
        
        # System Info
        self.system_info = Info(
            'coinbourg_system',
            'System information'
        )
        
        self.start_time = time.time()
        
        logger.info("Prometheus monitoring initialized")
    
    # Trade Tracking Methods
    def record_trade(self, symbol: str, side: str, outcome: str, pnl: float = None, duration_seconds: float = None):
        """Record a completed trade."""
        self.trades_total.labels(symbol=symbol, side=side, outcome=outcome).inc()
        
        if pnl is not None:
            self.trade_pnl.labels(symbol=symbol).observe(pnl)
        
        if duration_seconds is not None:
            self.trade_duration.labels(symbol=symbol).observe(duration_seconds)
        
        logger.debug(f"Recorded trade: {symbol} {side} {outcome}")
    
    def update_portfolio(self, total_value: float, available_balance: float, positions_count: int):
        """Update portfolio metrics."""
        self.portfolio_value.set(total_value)
        self.available_balance.set(available_balance)
        self.open_positions.set(positions_count)
    
    def update_position(self, symbol: str, value: float, unrealized_pnl: float):
        """Update individual position metrics."""
        self.position_value.labels(symbol=symbol).set(value)
        self.unrealized_pnl.labels(symbol=symbol).set(unrealized_pnl)
    
    def clear_position(self, symbol: str):
        """Clear position metrics when closed."""
        try:
            self.position_value.remove(symbol)
            self.unrealized_pnl.remove(symbol)
        except KeyError:
            pass
    
    # API Tracking Methods
    def record_api_request(self, service: str, endpoint: str, status: str, latency: float):
        """Record API request."""
        self.api_requests_total.labels(service=service, endpoint=endpoint, status=status).inc()
        self.api_latency.labels(service=service, endpoint=endpoint).observe(latency)
    
    def record_api_error(self, service: str, error_type: str):
        """Record API error."""
        self.api_errors.labels(service=service, error_type=error_type).inc()
    
    # AI Tracking Methods
    def record_ai_prediction(self, action: str, confidence: float, latency: float, provider: str = "unknown"):
        """Record AI prediction."""
        # Categorize confidence
        if confidence < 0.6:
            confidence_range = "low"
        elif confidence < 0.75:
            confidence_range = "medium"
        else:
            confidence_range = "high"
        
        self.ai_predictions.labels(action=action, confidence_range=confidence_range).inc()
        self.ai_latency.labels(provider=provider).observe(latency)
    
    def update_ai_accuracy(self, action: str, timeframe: str, accuracy: float):
        """Update AI accuracy metrics."""
        self.ai_accuracy.labels(action=action, timeframe=timeframe).set(accuracy * 100)
    
    # Risk Tracking Methods
    def update_risk_metrics(self, current_drawdown: float, max_drawdown: float, 
                           var_95: float, sharpe_ratio: float):
        """Update risk management metrics."""
        self.drawdown_current.set(current_drawdown)
        self.drawdown_max.set(max_drawdown)
        self.var_95.set(var_95)
        self.sharpe_ratio.set(sharpe_ratio)
    
    # System Health Methods
    def update_uptime(self):
        """Update system uptime."""
        uptime = time.time() - self.start_time
        self.system_uptime.set(uptime)
    
    def set_circuit_breaker(self, service: str, is_open: bool):
        """Set circuit breaker state."""
        self.circuit_breaker_state.labels(service=service).set(1 if is_open else 0)
    
    def update_memory_usage(self, rss: int, vms: int):
        """Update memory usage metrics."""
        self.memory_usage.labels(type='rss').set(rss)
        self.memory_usage.labels(type='vms').set(vms)
    
    # Market Activity Methods
    def record_market_scan(self, coins_found: int):
        """Record market scan."""
        self.market_scans.inc()
        self.coins_analyzed.inc(coins_found)
    
    def set_system_info(self, version: str, environment: str, risk_level: str):
        """Set system information."""
        self.system_info.info({
            'version': version,
            'environment': environment,
            'risk_level': risk_level,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat()
        })
    
    def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics in text format."""
        return generate_latest(REGISTRY)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics as dictionary."""
        self.update_uptime()
        
        return {
            'portfolio': {
                'total_value': self.portfolio_value._value.get(),
                'available_balance': self.available_balance._value.get(),
                'open_positions': self.open_positions._value.get(),
            },
            'risk': {
                'current_drawdown': self.drawdown_current._value.get(),
                'max_drawdown': self.drawdown_max._value.get(),
                'var_95': self.var_95._value.get(),
                'sharpe_ratio': self.sharpe_ratio._value.get(),
            },
            'system': {
                'uptime_seconds': self.system_uptime._value.get(),
            }
        }


# Global monitor instance
_monitor_instance = None


def get_monitor() -> PrometheusMonitor:
    """Get or create global monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = PrometheusMonitor()
    return _monitor_instance
