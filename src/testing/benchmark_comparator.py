"""
Benchmark Comparator
====================
Compare strategy performance against benchmarks.
"""

import logging
from datetime import datetime
from typing import Dict

from .test_engine import TestConfiguration, TestResult

logger = logging.getLogger(__name__)


class BenchmarkComparator:
    """Compare strategy against buy-and-hold and market indices."""
    
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """Compare against benchmarks."""
        logger.info("Running benchmark comparison")
        
        result.details['comparison_type'] = 'benchmark'
        
        return result
