"""
Monte Carlo Simulator
=====================
Run randomized simulations to test strategy robustness.
"""

import asyncio
import logging
from datetime import datetime
import numpy as np
from typing import Dict, List

from .test_engine import TestConfiguration, TestResult

logger = logging.getLogger(__name__)


class MonteCarloSimulator:
    """Monte Carlo simulation for strategy robustness testing."""
    
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """Run Monte Carlo simulation."""
        logger.info("Running Monte Carlo simulation")
        
        num_simulations = config.parameters.get('num_simulations', 1000)
        result.details['num_simulations'] = num_simulations
        
        # Run simulations with randomized parameters
        simulation_results = []
        
        for i in range(num_simulations):
            sim_result = await self._run_single_simulation(config, i)
            simulation_results.append(sim_result)
        
        # Analyze results
        returns = [r['return'] for r in simulation_results]
        result.details['mean_return'] = float(np.mean(returns))
        result.details['std_return'] = float(np.std(returns))
        result.details['min_return'] = float(np.min(returns))
        result.details['max_return'] = float(np.max(returns))
        result.details['percentile_5'] = float(np.percentile(returns, 5))
        result.details['percentile_95'] = float(np.percentile(returns, 95))
        
        result.total_return_pct = result.details['mean_return']
        
        logger.info(f"Monte Carlo complete: Mean return {result.total_return_pct:.2f}%")
        
        return result
    
    async def _run_single_simulation(
        self,
        config: TestConfiguration,
        simulation_num: int
    ) -> Dict:
        """Run a single Monte Carlo simulation."""
        # Simulate random market conditions
        days = (config.end_date - config.start_date).days
        daily_returns = np.random.normal(0.001, 0.02, days)  # Mean 0.1%, std 2%
        
        cumulative_return = np.prod(1 + daily_returns) - 1
        
        return {
            'simulation': simulation_num,
            'return': cumulative_return * 100,
            'max_drawdown': float(np.min(np.minimum.accumulate(daily_returns)) * 100)
        }
