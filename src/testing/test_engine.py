"""
Test Engine - Comprehensive Testing Framework
==============================================
Manages all 10 types of testing for CoinBourg predictions.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import json

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class TestType(str, Enum):
    """Types of tests available."""
    BACKTESTING = "backtesting"
    PAPER_TRADING = "paper_trading"
    FORWARD_TESTING = "forward_testing"
    OUT_OF_SAMPLE = "out_of_sample"
    MONTE_CARLO = "monte_carlo"
    SIGNAL_VALIDATION = "signal_validation"
    PREDICTION_ACCURACY = "prediction_accuracy"
    BENCHMARK_COMPARISON = "benchmark_comparison"
    LIVE_TESTING = "live_testing"
    POST_TRADE_ANALYSIS = "post_trade_analysis"


class TestStatus(str, Enum):
    """Test execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TestConfiguration:
    """Configuration for a test run."""
    test_type: TestType
    symbols: List[str]
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100.0
    risk_level: str = "MODERATE"
    strategies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    

@dataclass
class PredictionRecord:
    """Track individual prediction and its outcome."""
    test_run_id: str
    symbol: str
    prediction_time: datetime
    predicted_action: str  # BUY, SELL, HOLD
    predicted_price: float
    predicted_direction: str  # UP, DOWN, NEUTRAL
    confidence: float
    actual_price: Optional[float] = None
    actual_direction: Optional[str] = None
    outcome: Optional[str] = None  # SUCCESS, FAILURE, PARTIAL
    profit_loss: Optional[float] = None
    profit_loss_pct: Optional[float] = None
    time_to_outcome: Optional[int] = None  # seconds
    ai_reasoning: str = ""
    

@dataclass
class TestResult:
    """Comprehensive test results."""
    test_run_id: str
    test_type: TestType
    status: TestStatus
    symbols: List[str]
    start_date: datetime
    end_date: datetime
    execution_time: float
    
    # Overall performance
    total_predictions: int = 0
    successful_predictions: int = 0
    failed_predictions: int = 0
    accuracy: float = 0.0
    
    # Financial metrics
    initial_capital: float = 100.0
    final_capital: float = 0.0
    total_return: float = 0.0
    total_return_pct: float = 0.0
    
    # Performance metrics
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_profit_per_trade: float = 0.0
    
    # Cryptocurrency-specific results
    symbol_results: Dict[str, Dict] = field(default_factory=dict)
    predictions: List[PredictionRecord] = field(default_factory=list)
    
    # Time series data
    equity_curve: List[Dict] = field(default_factory=list)
    drawdown_series: List[Dict] = field(default_factory=list)
    
    # Detailed breakdown
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    

class TestEngine:
    """
    Main testing engine that orchestrates all test types.
    
    Features:
    - Run all 10 test types
    - Track predictions and outcomes
    - Store results in database
    - Generate comprehensive reports
    """
    
    def __init__(self, db_manager=None):
        """Initialize test engine."""
        self.settings = get_settings()
        self.db_manager = db_manager
        self.active_tests: Dict[str, TestResult] = {}
        
        logger.info("TestEngine initialized")
    
    async def run_test(
        self,
        test_type: TestType,
        config: TestConfiguration
    ) -> TestResult:
        """
        Run a specific test type.
        
        Args:
            test_type: Type of test to run
            config: Test configuration
            
        Returns:
            TestResult with comprehensive results
        """
        import uuid
        test_run_id = str(uuid.uuid4())
        
        logger.info(f"Starting {test_type.value} test - ID: {test_run_id}")
        
        result = TestResult(
            test_run_id=test_run_id,
            test_type=test_type,
            status=TestStatus.RUNNING,
            symbols=config.symbols,
            start_date=config.start_date,
            end_date=config.end_date,
            execution_time=0.0,
            initial_capital=config.initial_capital
        )
        
        self.active_tests[test_run_id] = result
        start_time = datetime.utcnow()
        
        try:
            # Route to appropriate test runner
            if test_type == TestType.BACKTESTING:
                from .backtesting import BacktestRunner
                runner = BacktestRunner()
                result = await runner.run(config, result)
                
            elif test_type == TestType.PAPER_TRADING:
                from .paper_trading import PaperTradingRunner
                runner = PaperTradingRunner()
                result = await runner.run(config, result)
                
            elif test_type == TestType.FORWARD_TESTING:
                from .forward_testing import ForwardTestRunner
                runner = ForwardTestRunner()
                result = await runner.run(config, result)
                
            elif test_type == TestType.OUT_OF_SAMPLE:
                from .out_of_sample import OutOfSampleTester
                runner = OutOfSampleTester()
                result = await runner.run(config, result)
                
            elif test_type == TestType.MONTE_CARLO:
                from .monte_carlo import MonteCarloSimulator
                runner = MonteCarloSimulator()
                result = await runner.run(config, result)
                
            elif test_type == TestType.SIGNAL_VALIDATION:
                from .signal_validator import SignalValidator
                runner = SignalValidator()
                result = await runner.run(config, result)
                
            elif test_type == TestType.PREDICTION_ACCURACY:
                from .prediction_evaluator import PredictionEvaluator
                runner = PredictionEvaluator()
                result = await runner.run(config, result)
                
            elif test_type == TestType.BENCHMARK_COMPARISON:
                from .benchmark_comparator import BenchmarkComparator
                runner = BenchmarkComparator()
                result = await runner.run(config, result)
                
            elif test_type == TestType.LIVE_TESTING:
                from .live_tester import LiveTester
                runner = LiveTester()
                result = await runner.run(config, result)
                
            elif test_type == TestType.POST_TRADE_ANALYSIS:
                from .post_trade_analyzer import PostTradeAnalyzer
                runner = PostTradeAnalyzer()
                result = await runner.run(config, result)
            
            result.status = TestStatus.COMPLETED
            result.completed_at = datetime.utcnow()
            result.execution_time = (result.completed_at - start_time).total_seconds()
            
            # Save to database
            if self.db_manager:
                await self.db_manager.save_test_result(result)
            
            logger.info(f"Test {test_run_id} completed in {result.execution_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Test {test_run_id} failed: {e}", exc_info=True)
            result.status = TestStatus.FAILED
            result.errors.append(str(e))
            result.completed_at = datetime.utcnow()
            
        return result
    
    async def get_test_results(
        self,
        test_run_id: Optional[str] = None,
        test_type: Optional[TestType] = None,
        limit: int = 100
    ) -> List[TestResult]:
        """Get test results from database."""
        if self.db_manager:
            return await self.db_manager.get_test_results(
                test_run_id=test_run_id,
                test_type=test_type,
                limit=limit
            )
        return []
    
    async def get_prediction_tracker(
        self,
        symbol: Optional[str] = None,
        test_run_id: Optional[str] = None
    ) -> List[PredictionRecord]:
        """Get prediction tracking records."""
        if self.db_manager:
            return await self.db_manager.get_predictions(
                symbol=symbol,
                test_run_id=test_run_id
            )
        return []
    
    async def get_best_performing_symbols(
        self,
        test_type: Optional[TestType] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Get cryptocurrencies with best prediction accuracy.
        
        Returns list of symbols with their success rates.
        """
        if self.db_manager:
            return await self.db_manager.get_best_symbols(
                test_type=test_type,
                limit=limit
            )
        return []
