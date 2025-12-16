"""
Live Tester
===========
Test with small real capital.
"""

import logging
from .test_engine import TestConfiguration, TestResult

logger = logging.getLogger(__name__)


class LiveTester:
    """Live testing with small capital."""
    
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """Run live test."""
        logger.info("Running live test")
        result.details['test_type'] = 'live_testing'
        return result
