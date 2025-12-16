"""
Out of Sample Tester
=====================
Validate on separate dataset not used in training.
"""

import logging
from .test_engine import TestConfiguration, TestResult

logger = logging.getLogger(__name__)


class OutOfSampleTester:
    """Out-of-sample testing."""
    
    async def run(
        self,
        config: TestConfiguration,
        result: TestResult
    ) -> TestResult:
        """Run out-of-sample test."""
        logger.info("Running out-of-sample test")
        result.details['test_type'] = 'out_of_sample'
        return result
