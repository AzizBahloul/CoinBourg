"""
Alerting System Configuration
==============================
Configure alerts for critical trading events and system health.
"""

import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from src.utils.error_monitor import ErrorMonitor
from src.utils.prometheus_monitor import get_monitor
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """Alert rule configuration."""
    name: str
    condition: callable
    severity: str  # 'critical', 'warning', 'info'
    cooldown_minutes: int = 15
    last_triggered: Optional[datetime] = None


class AlertingSystem:
    """
    Centralized alerting system for trading events and system health.
    
    Integrates with Telegram, email, and error monitoring.
    """
    
    def __init__(self):
        """Initialize alerting system."""
        self.settings = get_settings()
        self.error_monitor = ErrorMonitor()
        self.prometheus = get_monitor()
        self.alert_rules: List[AlertRule] = []
        
        # Initialize alert rules
        self._setup_alert_rules()
        
        logger.info("Alerting system initialized")
    
    def _setup_alert_rules(self):
        """Configure alert rules."""
        # Trading Alerts
        self.alert_rules.extend([
            AlertRule(
                name="large_profit",
                condition=lambda data: data.get('trade_pnl_percent', 0) > 5.0,
                severity="info",
                cooldown_minutes=5
            ),
            AlertRule(
                name="large_loss",
                condition=lambda data: data.get('trade_pnl_percent', 0) < -3.0,
                severity="warning",
                cooldown_minutes=5
            ),
            AlertRule(
                name="stop_loss_hit",
                condition=lambda data: data.get('exit_reason') == 'stop_loss',
                severity="warning",
                cooldown_minutes=10
            ),
        ])
        
        # Portfolio Alerts
        self.alert_rules.extend([
            AlertRule(
                name="max_drawdown_exceeded",
                condition=lambda data: data.get('current_drawdown', 0) > 10.0,
                severity="critical",
                cooldown_minutes=30
            ),
            AlertRule(
                name="low_balance",
                condition=lambda data: data.get('available_balance', float('inf')) < 100.0,
                severity="warning",
                cooldown_minutes=60
            ),
            AlertRule(
                name="high_var",
                condition=lambda data: data.get('var_95', 0) > data.get('portfolio_value', 0) * 0.15,
                severity="warning",
                cooldown_minutes=60
            ),
        ])
        
        # System Health Alerts
        self.alert_rules.extend([
            AlertRule(
                name="api_high_error_rate",
                condition=lambda data: data.get('api_error_rate', 0) > 0.1,  # 10% error rate
                severity="critical",
                cooldown_minutes=15
            ),
            AlertRule(
                name="circuit_breaker_open",
                condition=lambda data: data.get('circuit_breaker_open', False),
                severity="critical",
                cooldown_minutes=10
            ),
            AlertRule(
                name="low_ai_accuracy",
                condition=lambda data: data.get('ai_accuracy', 1.0) < 0.50,  # Below 50%
                severity="warning",
                cooldown_minutes=120
            ),
        ])
    
    async def check_alerts(self, event_data: Dict):
        """
        Check all alert rules against event data.
        
        Args:
            event_data: Dictionary containing event information
        """
        triggered_alerts = []
        
        for rule in self.alert_rules:
            # Check cooldown
            if rule.last_triggered:
                time_since_last = datetime.utcnow() - rule.last_triggered
                if time_since_last < timedelta(minutes=rule.cooldown_minutes):
                    continue
            
            # Check condition
            try:
                if rule.condition(event_data):
                    triggered_alerts.append(rule)
                    rule.last_triggered = datetime.utcnow()
            except Exception as e:
                logger.error(f"Error checking alert rule {rule.name}: {e}")
        
        # Send alerts
        for rule in triggered_alerts:
            await self._send_alert(rule, event_data)
    
    async def _send_alert(self, rule: AlertRule, data: Dict):
        """Send alert through configured channels."""
        message = self._format_alert_message(rule, data)
        
        try:
            # Send based on severity
            if rule.severity == "critical":
                # Send through all channels
                await self.error_monitor._send_telegram_alert(message)
                await self.error_monitor._send_email_alert("Critical Alert", message)
                logger.critical(f"ALERT: {message}")
            
            elif rule.severity == "warning":
                # Send through telegram
                await self.error_monitor._send_telegram_alert(message)
                logger.warning(f"ALERT: {message}")
            
            else:  # info
                # Log only
                logger.info(f"ALERT: {message}")
        
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def _format_alert_message(self, rule: AlertRule, data: Dict) -> str:
        """Format alert message."""
        emoji_map = {
            'critical': '🚨',
            'warning': '⚠️',
            'info': 'ℹ️'
        }
        
        emoji = emoji_map.get(rule.severity, 'ℹ️')
        
        message = f"{emoji} CoinBourg Alert - {rule.name.replace('_', ' ').title()}\n\n"
        message += f"Severity: {rule.severity.upper()}\n"
        message += f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        
        # Add relevant data
        if 'symbol' in data:
            message += f"Symbol: {data['symbol']}\n"
        
        if 'trade_pnl_percent' in data:
            message += f"P&L: {data['trade_pnl_percent']:+.2f}%\n"
        
        if 'current_drawdown' in data:
            message += f"Drawdown: {data['current_drawdown']:.2f}%\n"
        
        if 'portfolio_value' in data:
            message += f"Portfolio Value: ${data['portfolio_value']:,.2f}\n"
        
        if 'available_balance' in data:
            message += f"Available Balance: ${data['available_balance']:,.2f}\n"
        
        if 'api_error_rate' in data:
            message += f"API Error Rate: {data['api_error_rate']:.1%}\n"
        
        if 'ai_accuracy' in data:
            message += f"AI Accuracy: {data['ai_accuracy']:.1%}\n"
        
        if 'circuit_breaker_open' in data and data['circuit_breaker_open']:
            message += "⚠️ Circuit Breaker: OPEN\n"
        
        return message
    
    async def alert_trade_completed(self, symbol: str, side: str, pnl: float, pnl_percent: float, exit_reason: str):
        """Alert when a trade is completed."""
        await self.check_alerts({
            'event_type': 'trade_completed',
            'symbol': symbol,
            'side': side,
            'trade_pnl': pnl,
            'trade_pnl_percent': pnl_percent,
            'exit_reason': exit_reason
        })
    
    async def alert_portfolio_status(self, portfolio_value: float, available_balance: float, 
                                    current_drawdown: float, var_95: float):
        """Alert on portfolio status."""
        await self.check_alerts({
            'event_type': 'portfolio_status',
            'portfolio_value': portfolio_value,
            'available_balance': available_balance,
            'current_drawdown': current_drawdown,
            'var_95': var_95
        })
    
    async def alert_system_health(self, api_error_rate: float, circuit_breaker_open: bool, ai_accuracy: float):
        """Alert on system health."""
        await self.check_alerts({
            'event_type': 'system_health',
            'api_error_rate': api_error_rate,
            'circuit_breaker_open': circuit_breaker_open,
            'ai_accuracy': ai_accuracy
        })


# Global alerting instance
_alerting_instance = None


def get_alerting_system() -> AlertingSystem:
    """Get or create global alerting system instance."""
    global _alerting_instance
    if _alerting_instance is None:
        _alerting_instance = AlertingSystem()
    return _alerting_instance
