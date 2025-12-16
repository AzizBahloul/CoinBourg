"""
System Health Monitoring
========================
Comprehensive health checks for all system components.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Component health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component."""
    name: str
    status: HealthStatus
    last_check: datetime
    response_time_ms: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'status': self.status.value,
            'last_check': self.last_check.isoformat(),
            'response_time_ms': round(self.response_time_ms, 2),
            'error_message': self.error_message,
            'metadata': self.metadata
        }


class HealthCheckSystem:
    """
    Centralized health monitoring for all system components.
    
    Monitors:
    - Binance API connectivity
    - DeepSeek AI availability
    - Database connection
    - Redis cache
    - Internal services
    """
    
    def __init__(self):
        """Initialize health check system."""
        self.component_health: Dict[str, ComponentHealth] = {}
        self.check_interval_seconds = 30
        self.retry_attempts = 3
        self.retry_delay_seconds = 2
        
        logger.info("Health check system initialized")
    
    async def check_binance_health(self, binance_client) -> ComponentHealth:
        """Check Binance API health."""
        start_time = datetime.utcnow()
        
        try:
            # Test connectivity
            result = await binance_client.test_connectivity()
            
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Test if we can fetch a ticker (more comprehensive)
            await binance_client.get_ticker_price("BTCUSDT")
            
            return ComponentHealth(
                name="binance_api",
                status=HealthStatus.HEALTHY,
                last_check=datetime.utcnow(),
                response_time_ms=response_time,
                metadata={
                    'base_url': binance_client.base_url,
                    'testnet': binance_client.testnet
                }
            )
        
        except Exception as e:
            logger.error(f"Binance health check failed: {e}")
            return ComponentHealth(
                name="binance_api",
                status=HealthStatus.UNHEALTHY,
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
    
    async def check_deepseek_health(self, deepseek_client) -> ComponentHealth:
        """Check DeepSeek AI health."""
        start_time = datetime.utcnow()
        
        try:
            # Simple health check
            is_healthy = await deepseek_client.test_connection()
            
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if is_healthy:
                return ComponentHealth(
                    name="deepseek_ai",
                    status=HealthStatus.HEALTHY,
                    last_check=datetime.utcnow(),
                    response_time_ms=response_time,
                    metadata={
                        'api_url': deepseek_client.api_url
                    }
                )
            else:
                return ComponentHealth(
                    name="deepseek_ai",
                    status=HealthStatus.DEGRADED,
                    last_check=datetime.utcnow(),
                    error_message="Health check returned false"
                )
        
        except Exception as e:
            logger.error(f"DeepSeek health check failed: {e}")
            return ComponentHealth(
                name="deepseek_ai",
                status=HealthStatus.UNHEALTHY,
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
    
    async def check_database_health(self, state_manager) -> ComponentHealth:
        """Check database health."""
        start_time = datetime.utcnow()
        
        try:
            # Simple query to test connection
            await state_manager.test_connection()
            
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                last_check=datetime.utcnow(),
                response_time_ms=response_time,
                metadata={
                    'database_url': state_manager.database_url.split('@')[0] + '@***'  # Hide credentials
                }
            )
        
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
    
    async def check_redis_health(self, redis_url: str) -> ComponentHealth:
        """Check Redis cache health."""
        start_time = datetime.utcnow()
        
        try:
            import aioredis
            
            redis = await aioredis.from_url(redis_url)
            
            # Ping test
            await redis.ping()
            
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            await redis.close()
            
            return ComponentHealth(
                name="redis_cache",
                status=HealthStatus.HEALTHY,
                last_check=datetime.utcnow(),
                response_time_ms=response_time
            )
        
        except ImportError:
            return ComponentHealth(
                name="redis_cache",
                status=HealthStatus.UNKNOWN,
                last_check=datetime.utcnow(),
                error_message="Redis client not installed"
            )
        
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return ComponentHealth(
                name="redis_cache",
                status=HealthStatus.DEGRADED,  # Not critical
                last_check=datetime.utcnow(),
                error_message=str(e)
            )
    
    async def check_component_with_retry(
        self,
        check_func,
        component_name: str,
        *args
    ) -> ComponentHealth:
        """Check component health with retry logic."""
        last_error = None
        
        for attempt in range(self.retry_attempts):
            try:
                result = await check_func(*args)
                
                if result.status != HealthStatus.UNHEALTHY:
                    return result
                
                last_error = result.error_message
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"{component_name} health check attempt {attempt + 1} failed: {e}")
            
            if attempt < self.retry_attempts - 1:
                await asyncio.sleep(self.retry_delay_seconds)
        
        # All attempts failed
        return ComponentHealth(
            name=component_name,
            status=HealthStatus.UNHEALTHY,
            last_check=datetime.utcnow(),
            error_message=f"Failed after {self.retry_attempts} attempts: {last_error}"
        )
    
    async def check_all_components(
        self,
        binance_client=None,
        deepseek_client=None,
        state_manager=None,
        redis_url: Optional[str] = None
    ) -> Dict[str, ComponentHealth]:
        """
        Check all system components.
        
        Returns:
            Dictionary of component health statuses
        """
        checks = []
        
        # Run all checks in parallel
        if binance_client:
            checks.append(
                self.check_component_with_retry(
                    self.check_binance_health,
                    "binance_api",
                    binance_client
                )
            )
        
        if deepseek_client:
            checks.append(
                self.check_component_with_retry(
                    self.check_deepseek_health,
                    "deepseek_ai",
                    deepseek_client
                )
            )
        
        if state_manager:
            checks.append(
                self.check_component_with_retry(
                    self.check_database_health,
                    "database",
                    state_manager
                )
            )
        
        if redis_url:
            checks.append(
                self.check_redis_health(redis_url)
            )
        
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Update stored health status
        for result in results:
            if isinstance(result, ComponentHealth):
                self.component_health[result.name] = result
        
        return self.component_health
    
    def get_overall_health(self) -> Dict[str, Any]:
        """
        Get overall system health.
        
        Returns:
            Dictionary with overall status and component details
        """
        if not self.component_health:
            return {
                'overall_status': 'unknown',
                'components': {},
                'last_check': None
            }
        
        # Determine overall status
        statuses = [comp.status for comp in self.component_health.values()]
        
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = 'unhealthy'
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = 'degraded'
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            overall = 'healthy'
        else:
            overall = 'unknown'
        
        return {
            'overall_status': overall,
            'components': {
                name: health.to_dict()
                for name, health in self.component_health.items()
            },
            'last_check': max(
                comp.last_check for comp in self.component_health.values()
            ).isoformat() if self.component_health else None,
            'healthy_components': sum(
                1 for comp in self.component_health.values()
                if comp.status == HealthStatus.HEALTHY
            ),
            'total_components': len(self.component_health)
        }
    
    def get_component_history(self, component_name: str, hours: int = 24) -> List[Dict]:
        """
        Get health history for a component.
        
        Note: This is a placeholder. In production, you'd store history in database.
        """
        # TODO: Implement history storage
        if component_name in self.component_health:
            return [self.component_health[component_name].to_dict()]
        return []


# Global health check instance
_health_check_instance = None


def get_health_check_system() -> HealthCheckSystem:
    """Get or create global health check system instance."""
    global _health_check_instance
    if _health_check_instance is None:
        _health_check_instance = HealthCheckSystem()
    return _health_check_instance
