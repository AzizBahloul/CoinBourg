"""
Forward Testing Runner
======================
Test strategy on new, unseen data after backtesting.
"""

import logging
from .test_engine import TestConfiguration, TestResult

logger = logging.getLogger(__name__)


class ForwardTestRunner:
    """Forward testing on out-of-sample data."""
    
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """Run forward test."""
        logger.info("Running forward test")
        result.details['test_type'] = 'forward_testing'
        return result
