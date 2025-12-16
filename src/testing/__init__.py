"""
CoinBourg Testing Framework
============================
Comprehensive testing and validation system for trading predictions.
"""

from .test_engine import TestEngine, TestType, TestStatus
from .backtesting import BacktestRunner
from .paper_trading import PaperTradingRunner
from .forward_testing import ForwardTestRunner
from .monte_carlo import MonteCarloSimulator
from .signal_validator import SignalValidator
from .prediction_evaluator import PredictionEvaluator
from .benchmark_comparator import BenchmarkComparator

__all__ = [
    'TestEngine',
    'TestType',
    'TestStatus',
    'BacktestRunner',
    'PaperTradingRunner',
    'ForwardTestRunner',
    'MonteCarloSimulator',
    'SignalValidator',
    'PredictionEvaluator',
    'BenchmarkComparator',
]
