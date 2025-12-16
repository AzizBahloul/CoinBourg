"""
Error Monitoring & Alerting System
===================================
Comprehensive error tracking with Sentry integration and alert notifications.
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, List
from datetime import datetime
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

# Optional Sentry import
try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    HAS_SENTRY = True
except ImportError:
    HAS_SENTRY = False
    logger.warning("sentry-sdk not installed - error tracking disabled")


class ErrorMonitor:
    """
    Production error monitoring and alerting system.
    
    Features:
    - Sentry integration for error tracking
    - Telegram notifications for critical errors
    - Email alerts
    - Error rate limiting to prevent spam
    - Context enrichment for better debugging
    """
    
    def __init__(
        self,
        sentry_dsn: Optional[str] = None,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        email_from: Optional[str] = None,
        email_to: Optional[str] = None,
        smtp_server: Optional[str] = None,
        smtp_port: int = 587,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None
    ):
        """Initialize error monitoring."""
        
        # Sentry configuration
        self.sentry_dsn = sentry_dsn or os.getenv('SENTRY_DSN')
        if HAS_SENTRY and self.sentry_dsn:
            try:
                sentry_sdk.init(
                    dsn=self.sentry_dsn,
                    traces_sample_rate=1.0,
                    profiles_sample_rate=1.0,
                    integrations=[
                        LoggingIntegration(
                            level=logging.INFO,
                            event_level=logging.ERROR
                        )
                    ],
                    environment=os.getenv('ENVIRONMENT', 'production'),
                    release=os.getenv('RELEASE_VERSION', '1.0.0')
                )
                logger.info("✓ Sentry error tracking initialized")
            except Exception as e:
                logger.warning(f"Sentry initialization failed: {e}")
        
        # Telegram configuration
        self.telegram_token = telegram_bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = telegram_chat_id or os.getenv('TELEGRAM_CHAT_ID')
        
        # Email configuration
        self.email_from = email_from or os.getenv('ALERT_EMAIL_FROM')
        self.email_to = email_to or os.getenv('ALERT_EMAIL_TO')
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER')
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username or os.getenv('SMTP_USERNAME')
        self.smtp_password = smtp_password or os.getenv('SMTP_PASSWORD')
        
        # Error rate limiting
        self.error_counts: Dict[str, int] = {}
        self.last_alert_times: Dict[str, datetime] = {}
        self.alert_cooldown_seconds = 300  # 5 minutes between same error alerts
    
    async def capture_exception(
        self,
        error: Exception,
        context: Optional[Dict] = None,
        level: str = "error"
    ):
        """
        Capture and report an exception.
        
        Args:
            error: The exception to capture
            context: Additional context (user, request, etc.)
            level: Severity level (error, warning, fatal)
        """
        error_key = f"{type(error).__name__}:{str(error)[:100]}"
        
        # Update error count
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # Log the error
        if level == "fatal":
            logger.critical(f"FATAL ERROR: {error}", exc_info=True)
        else:
            logger.error(f"ERROR: {error}", exc_info=True, extra=context or {})
        
        # Send to Sentry
        if HAS_SENTRY and self.sentry_dsn:
            with sentry_sdk.push_scope() as scope:
                # Add context
                if context:
                    for key, value in context.items():
                        scope.set_context(key, value)
                
                # Add tags
                scope.set_tag("error_count", self.error_counts[error_key])
                
                # Capture exception
                if level == "warning":
                    sentry_sdk.capture_message(str(error), level="warning")
                else:
                    sentry_sdk.capture_exception(error)
        
        # Send alerts for critical/fatal errors
        if level in ["error", "fatal"]:
            await self._send_alerts(error, context, level)
    
    async def _send_alerts(
        self,
        error: Exception,
        context: Optional[Dict],
        level: str
    ):
        """Send alerts via configured channels."""
        error_key = f"{type(error).__name__}:{str(error)[:100]}"
        
        # Rate limiting - don't spam same error
        last_alert = self.last_alert_times.get(error_key)
        if last_alert:
            seconds_since = (datetime.utcnow() - last_alert).total_seconds()
            if seconds_since < self.alert_cooldown_seconds:
                logger.debug(f"Skipping alert for {error_key} (cooldown)")
                return
        
        # Update last alert time
        self.last_alert_times[error_key] = datetime.utcnow()
        
        # Prepare message
        message = self._format_error_message(error, context, level)
        
        # Send to all configured channels
        await asyncio.gather(
            self._send_telegram_alert(message),
            self._send_email_alert(message, error, level),
            return_exceptions=True
        )
    
    def _format_error_message(
        self,
        error: Exception,
        context: Optional[Dict],
        level: str
    ) -> str:
        """Format error message for alerts."""
        error_key = f"{type(error).__name__}:{str(error)[:100]}"
        error_count = self.error_counts.get(error_key, 1)
        
        emoji = "🔴" if level == "fatal" else "⚠️"
        
        message = f"{emoji} **CoinBourg Alert - {level.upper()}**\n\n"
        message += f"**Error Type:** {type(error).__name__}\n"
        message += f"**Message:** {str(error)}\n"
        message += f"**Occurrences:** {error_count}\n"
        message += f"**Time:** {datetime.utcnow().isoformat()}\n"
        
        if context:
            message += "\n**Context:**\n"
            for key, value in context.items():
                message += f"- {key}: {value}\n"
        
        return message
    
    async def _send_telegram_alert(self, message: str):
        """Send alert via Telegram."""
        if not self.telegram_token or not self.telegram_chat_id:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info("✓ Telegram alert sent")
                    else:
                        logger.warning(f"Telegram alert failed: {response.status}")
        
        except Exception as e:
            logger.warning(f"Failed to send Telegram alert: {e}")
    
    async def _send_email_alert(
        self,
        message: str,
        error: Exception,
        level: str
    ):
        """Send alert via email."""
        if not all([self.email_from, self.email_to, self.smtp_server]):
            return
        
        try:
            # Create email
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = self.email_to
            msg['Subject'] = f"CoinBourg Alert: {level.upper()} - {type(error).__name__}"
            
            # Add body
            body = message.replace('**', '').replace('*', '')  # Remove markdown
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info("✓ Email alert sent")
        
        except Exception as e:
            logger.warning(f"Failed to send email alert: {e}")
    
    def capture_message(
        self,
        message: str,
        level: str = "info",
        context: Optional[Dict] = None
    ):
        """Capture a message (not an exception)."""
        if HAS_SENTRY and self.sentry_dsn:
            with sentry_sdk.push_scope() as scope:
                if context:
                    for key, value in context.items():
                        scope.set_context(key, value)
                
                sentry_sdk.capture_message(message, level=level)
    
    def set_user_context(
        self,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        email: Optional[str] = None
    ):
        """Set user context for error tracking."""
        if HAS_SENTRY and self.sentry_dsn:
            sentry_sdk.set_user({
                "id": user_id,
                "username": username,
                "email": email
            })
    
    def set_context(self, key: str, value: Dict):
        """Set custom context."""
        if HAS_SENTRY and self.sentry_dsn:
            sentry_sdk.set_context(key, value)
    
    async def log_trade_error(
        self,
        symbol: str,
        action: str,
        error: Exception,
        context: Optional[Dict] = None
    ):
        """Specialized logging for trade errors."""
        enriched_context = {
            "symbol": symbol,
            "action": action,
            "error_type": type(error).__name__,
            **(context or {})
        }
        
        await self.capture_exception(
            error,
            context=enriched_context,
            level="error"
        )
    
    def get_error_stats(self) -> Dict:
        """Get error statistics."""
        return {
            "total_unique_errors": len(self.error_counts),
            "total_error_count": sum(self.error_counts.values()),
            "top_errors": sorted(
                self.error_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }


# Global error monitor instance
_error_monitor: Optional[ErrorMonitor] = None


def get_error_monitor() -> ErrorMonitor:
    """Get global error monitor instance."""
    global _error_monitor
    if _error_monitor is None:
        _error_monitor = ErrorMonitor()
    return _error_monitor


async def alert_on_error(
    error: Exception,
    context: Optional[Dict] = None,
    level: str = "error"
):
    """Convenience function to alert on errors."""
    monitor = get_error_monitor()
    await monitor.capture_exception(error, context, level)
