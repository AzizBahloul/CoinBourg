"""
Parameter Optimizer
===================
Grid search and random search for strategy parameter optimization.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np
import pandas as pd
from itertools import product
import json

logger = logging.getLogger(__name__)


@dataclass
class ParameterSet:
    """Parameter combination for optimization."""
    params: Dict[str, Any]
    score: float
    sharpe_ratio: float
    max_drawdown: float
    total_return_pct: float
    win_rate: float
    total_trades: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'params': self.params,
            'score': self.score,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'total_return_pct': self.total_return_pct,
            'win_rate': self.win_rate,
            'total_trades': self.total_trades
        }


@dataclass
class OptimizationResult:
    """Results from parameter optimization."""
    best_params: Dict[str, Any]
    best_score: float
    all_results: List[ParameterSet]
    parameter_sensitivity: Dict[str, Dict[str, float]]
    market_regime_performance: Dict[str, ParameterSet]
    optimization_time: float


class ParameterOptimizer:
    """
    Parameter optimization with grid search and random search.
    
    Features:
    - Grid search over parameter space
    - Random search for large parameter spaces
    - Market regime analysis (bull/bear/sideways)
    - Parameter sensitivity analysis
    - Cross-validation support
    - Robust scoring with drawdown penalty
    """
    
    def __init__(
        self,
        backtest_engine,
        scoring_method: str = "sharpe_drawdown"
    ):
        """
        Initialize optimizer.
        
        Args:
            backtest_engine: BacktestEngine instance
            scoring_method: Scoring method (sharpe_drawdown, sharpe, return, calmar)
        """
        self.backtest_engine = backtest_engine
        self.scoring_method = scoring_method
        
        logger.info(f"ParameterOptimizer initialized - Scoring: {scoring_method}")
    
    async def grid_search(
        self,
        strategy_class,
        symbol: str,
        data: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        n_splits: int = 3
    ) -> OptimizationResult:
        """
        Grid search over parameter space with cross-validation.
        
        Args:
            strategy_class: Strategy class to instantiate
            symbol: Trading symbol
            data: Historical data
            param_grid: Parameter grid, e.g., {'stop_loss': [2, 3, 5], 'take_profit': [5, 10, 15]}
            n_splits: Number of cross-validation splits
            
        Returns:
            OptimizationResult with best parameters
        """
        start_time = datetime.now()
        
        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        param_combinations = list(product(*param_values))
        
        total_combinations = len(param_combinations)
        logger.info(f"Grid search: {total_combinations} combinations across {n_splits} splits")
        
        results = []
        
        # Test each combination
        for i, combo in enumerate(param_combinations, 1):
            params = dict(zip(param_names, combo))
            
            try:
                # Cross-validation
                cv_scores = await self._cross_validate(
                    strategy_class,
                    symbol,
                    data,
                    params,
                    n_splits
                )
                
                # Average metrics
                avg_score = np.mean([s.score for s in cv_scores])
                avg_sharpe = np.mean([s.sharpe_ratio for s in cv_scores])
                avg_drawdown = np.mean([s.max_drawdown for s in cv_scores])
                avg_return = np.mean([s.total_return_pct for s in cv_scores])
                avg_win_rate = np.mean([s.win_rate for s in cv_scores])
                total_trades = sum([s.total_trades for s in cv_scores])
                
                param_set = ParameterSet(
                    params=params,
                    score=avg_score,
                    sharpe_ratio=avg_sharpe,
                    max_drawdown=avg_drawdown,
                    total_return_pct=avg_return,
                    win_rate=avg_win_rate,
                    total_trades=total_trades
                )
                results.append(param_set)
                
                logger.info(f"[{i}/{total_combinations}] {params} -> Score: {avg_score:.4f}, "
                          f"Sharpe: {avg_sharpe:.2f}, Drawdown: {avg_drawdown:.2f}%")
                
            except Exception as e:
                logger.error(f"Error testing {params}: {e}")
        
        if not results:
            raise ValueError("No valid results from grid search")
        
        # Find best parameters
        best_result = max(results, key=lambda x: x.score)
        
        # Parameter sensitivity analysis
        sensitivity = self._analyze_parameter_sensitivity(results, param_names)
        
        # Market regime analysis
        regime_performance = await self._analyze_market_regimes(
            strategy_class,
            symbol,
            data,
            best_result.params
        )
        
        optimization_time = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"Grid search complete - Best score: {best_result.score:.4f}, "
                   f"Best params: {best_result.params}")
        
        return OptimizationResult(
            best_params=best_result.params,
            best_score=best_result.score,
            all_results=sorted(results, key=lambda x: x.score, reverse=True),
            parameter_sensitivity=sensitivity,
            market_regime_performance=regime_performance,
            optimization_time=optimization_time
        )
    
    async def random_search(
        self,
        strategy_class,
        symbol: str,
        data: pd.DataFrame,
        param_distributions: Dict[str, Tuple[Any, Any]],
        n_iterations: int = 100,
        n_splits: int = 3
    ) -> OptimizationResult:
        """
        Random search over parameter space.
        
        Args:
            strategy_class: Strategy class to instantiate
            symbol: Trading symbol
            data: Historical data
            param_distributions: Parameter ranges, e.g., {'stop_loss': (1, 10), 'take_profit': (5, 20)}
            n_iterations: Number of random samples
            n_splits: Number of cross-validation splits
            
        Returns:
            OptimizationResult with best parameters
        """
        start_time = datetime.now()
        
        logger.info(f"Random search: {n_iterations} iterations across {n_splits} splits")
        
        results = []
        
        for i in range(n_iterations):
            # Sample random parameters
            params = {}
            for param_name, (min_val, max_val) in param_distributions.items():
                if isinstance(min_val, int):
                    params[param_name] = np.random.randint(min_val, max_val + 1)
                else:
                    params[param_name] = np.random.uniform(min_val, max_val)
            
            try:
                # Cross-validation
                cv_scores = await self._cross_validate(
                    strategy_class,
                    symbol,
                    data,
                    params,
                    n_splits
                )
                
                # Average metrics
                avg_score = np.mean([s.score for s in cv_scores])
                avg_sharpe = np.mean([s.sharpe_ratio for s in cv_scores])
                avg_drawdown = np.mean([s.max_drawdown for s in cv_scores])
                avg_return = np.mean([s.total_return_pct for s in cv_scores])
                avg_win_rate = np.mean([s.win_rate for s in cv_scores])
                total_trades = sum([s.total_trades for s in cv_scores])
                
                param_set = ParameterSet(
                    params=params,
                    score=avg_score,
                    sharpe_ratio=avg_sharpe,
                    max_drawdown=avg_drawdown,
                    total_return_pct=avg_return,
                    win_rate=avg_win_rate,
                    total_trades=total_trades
                )
                results.append(param_set)
                
                logger.info(f"[{i+1}/{n_iterations}] {params} -> Score: {avg_score:.4f}")
                
            except Exception as e:
                logger.error(f"Error testing {params}: {e}")
        
        if not results:
            raise ValueError("No valid results from random search")
        
        # Find best parameters
        best_result = max(results, key=lambda x: x.score)
        
        # Parameter sensitivity analysis
        param_names = list(param_distributions.keys())
        sensitivity = self._analyze_parameter_sensitivity(results, param_names)
        
        # Market regime analysis
        regime_performance = await self._analyze_market_regimes(
            strategy_class,
            symbol,
            data,
            best_result.params
        )
        
        optimization_time = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"Random search complete - Best score: {best_result.score:.4f}, "
                   f"Best params: {best_result.params}")
        
        return OptimizationResult(
            best_params=best_result.params,
            best_score=best_result.score,
            all_results=sorted(results, key=lambda x: x.score, reverse=True),
            parameter_sensitivity=sensitivity,
            market_regime_performance=regime_performance,
            optimization_time=optimization_time
        )
    
    async def _cross_validate(
        self,
        strategy_class,
        symbol: str,
        data: pd.DataFrame,
        params: Dict[str, Any],
        n_splits: int
    ) -> List[ParameterSet]:
        """
        Cross-validate parameters.
        
        Args:
            strategy_class: Strategy class
            symbol: Trading symbol
            data: Historical data
            params: Parameters to test
            n_splits: Number of splits
            
        Returns:
            List of ParameterSet for each split
        """
        split_size = len(data) // n_splits
        results = []
        
        for i in range(n_splits):
            start_idx = i * split_size
            end_idx = start_idx + split_size if i < n_splits - 1 else len(data)
            
            split_data = data.iloc[start_idx:end_idx]
            
            # Create strategy with parameters
            strategy = strategy_class(**params)
            
            # Run backtest
            backtest_result = await self.backtest_engine.run_backtest(
                strategy=strategy,
                symbol=symbol,
                data=split_data
            )
            
            # Calculate score
            score = self._calculate_score(backtest_result)
            
            param_set = ParameterSet(
                params=params,
                score=score,
                sharpe_ratio=backtest_result.sharpe_ratio,
                max_drawdown=backtest_result.max_drawdown,
                total_return_pct=backtest_result.total_return_pct,
                win_rate=backtest_result.win_rate,
                total_trades=backtest_result.total_trades
            )
            results.append(param_set)
        
        return results
    
    def _calculate_score(self, result) -> float:
        """
        Calculate optimization score.
        
        Args:
            result: BacktestResult
            
        Returns:
            Score (higher is better)
        """
        if self.scoring_method == "sharpe_drawdown":
            # Penalize drawdown
            drawdown_penalty = 1 - (abs(result.max_drawdown) / 100)
            score = result.sharpe_ratio * drawdown_penalty
            
        elif self.scoring_method == "sharpe":
            score = result.sharpe_ratio
            
        elif self.scoring_method == "return":
            score = result.total_return_pct
            
        elif self.scoring_method == "calmar":
            score = result.calmar_ratio
            
        else:
            raise ValueError(f"Unknown scoring method: {self.scoring_method}")
        
        # Penalize low trade count
        if result.total_trades < 10:
            score *= 0.5
        
        return score
    
    def _analyze_parameter_sensitivity(
        self,
        results: List[ParameterSet],
        param_names: List[str]
    ) -> Dict[str, Dict[str, float]]:
        """
        Analyze parameter sensitivity.
        
        Args:
            results: List of optimization results
            param_names: Parameter names
            
        Returns:
            Sensitivity analysis for each parameter
        """
        sensitivity = {}
        
        for param_name in param_names:
            # Group by parameter value
            param_groups = {}
            for result in results:
                param_value = result.params[param_name]
                if param_value not in param_groups:
                    param_groups[param_value] = []
                param_groups[param_value].append(result.score)
            
            # Calculate statistics
            param_stats = {}
            for value, scores in param_groups.items():
                param_stats[str(value)] = {
                    'mean_score': np.mean(scores),
                    'std_score': np.std(scores),
                    'count': len(scores)
                }
            
            sensitivity[param_name] = param_stats
        
        return sensitivity
    
    async def _analyze_market_regimes(
        self,
        strategy_class,
        symbol: str,
        data: pd.DataFrame,
        params: Dict[str, Any]
    ) -> Dict[str, ParameterSet]:
        """
        Test parameters across different market regimes.
        
        Args:
            strategy_class: Strategy class
            symbol: Trading symbol
            data: Historical data
            params: Parameters to test
            
        Returns:
            Performance in bull/bear/sideways markets
        """
        # Calculate market trends
        returns = data['close'].pct_change()
        
        # Split data into regimes based on rolling trend
        window = 60
        rolling_return = returns.rolling(window).mean()
        
        # Define regimes
        bull_mask = rolling_return > 0.005  # >0.5% average daily return
        bear_mask = rolling_return < -0.005  # <-0.5% average daily return
        sideways_mask = ~(bull_mask | bear_mask)
        
        regime_performance = {}
        
        # Test each regime
        for regime_name, mask in [("bull", bull_mask), ("bear", bear_mask), ("sideways", sideways_mask)]:
            regime_data = data[mask]
            
            if len(regime_data) < 100:
                logger.warning(f"Insufficient data for {regime_name} regime ({len(regime_data)} bars)")
                continue
            
            try:
                strategy = strategy_class(**params)
                result = await self.backtest_engine.run_backtest(
                    strategy=strategy,
                    symbol=symbol,
                    data=regime_data
                )
                
                score = self._calculate_score(result)
                
                regime_performance[regime_name] = ParameterSet(
                    params=params,
                    score=score,
                    sharpe_ratio=result.sharpe_ratio,
                    max_drawdown=result.max_drawdown,
                    total_return_pct=result.total_return_pct,
                    win_rate=result.win_rate,
                    total_trades=result.total_trades
                )
                
                logger.info(f"{regime_name.upper()} regime: Score {score:.4f}, "
                          f"Return {result.total_return_pct:.2f}%, "
                          f"Trades {result.total_trades}")
                
            except Exception as e:
                logger.error(f"Error testing {regime_name} regime: {e}")
        
        return regime_performance
    
    def export_results(self, result: OptimizationResult, filename: str):
        """Export optimization results to JSON."""
        export_data = {
            'best_params': result.best_params,
            'best_score': result.best_score,
            'optimization_time': result.optimization_time,
            'top_10_results': [r.to_dict() for r in result.all_results[:10]],
            'parameter_sensitivity': result.parameter_sensitivity,
            'market_regime_performance': {
                regime: perf.to_dict() 
                for regime, perf in result.market_regime_performance.items()
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        logger.info(f"Optimization results exported to {filename}")
    
    def print_summary(self, result: OptimizationResult):
        """Print optimization summary."""
        print("\n" + "="*80)
        print("PARAMETER OPTIMIZATION RESULTS")
        print("="*80)
        
        print(f"\nBest Parameters (Score: {result.best_score:.4f}):")
        for param, value in result.best_params.items():
            print(f"  {param}: {value}")
        
        print(f"\nTop 5 Parameter Sets:")
        for i, param_set in enumerate(result.all_results[:5], 1):
            print(f"\n{i}. Score: {param_set.score:.4f}")
            print(f"   Params: {param_set.params}")
            print(f"   Sharpe: {param_set.sharpe_ratio:.2f}, "
                  f"Return: {param_set.total_return_pct:.2f}%, "
                  f"Drawdown: {param_set.max_drawdown:.2f}%")
        
        print(f"\nMarket Regime Performance:")
        for regime, perf in result.market_regime_performance.items():
            print(f"  {regime.upper()}: "
                  f"Score {perf.score:.4f}, "
                  f"Return {perf.total_return_pct:.2f}%, "
                  f"Sharpe {perf.sharpe_ratio:.2f}")
        
        print(f"\nOptimization completed in {result.optimization_time:.1f} seconds")
        print("="*80 + "\n")


class WalkForwardOptimizer:
    """
    Walk-forward optimization to prevent overfitting.
    
    Splits data into in-sample (training) and out-of-sample (testing) periods.
    """
    
    def __init__(self, optimizer: ParameterOptimizer):
        """
        Initialize walk-forward optimizer.
        
        Args:
            optimizer: ParameterOptimizer instance
        """
        self.optimizer = optimizer
    
    async def optimize(
        self,
        strategy_class,
        symbol: str,
        data: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        in_sample_pct: float = 0.7,
        n_windows: int = 5
    ) -> Dict[str, Any]:
        """
        Perform walk-forward optimization.
        
        Args:
            strategy_class: Strategy class
            symbol: Trading symbol
            data: Historical data
            param_grid: Parameter grid
            in_sample_pct: Percentage of data for training
            n_windows: Number of walk-forward windows
            
        Returns:
            Walk-forward optimization results
        """
        window_size = len(data) // n_windows
        in_sample_size = int(window_size * in_sample_pct)
        out_sample_size = window_size - in_sample_size
        
        logger.info(f"Walk-forward optimization: {n_windows} windows, "
                   f"{in_sample_pct*100:.0f}% in-sample")
        
        results = []
        
        for i in range(n_windows):
            window_start = i * window_size
            in_sample_end = window_start + in_sample_size
            out_sample_end = min(window_start + window_size, len(data))
            
            in_sample_data = data.iloc[window_start:in_sample_end]
            out_sample_data = data.iloc[in_sample_end:out_sample_end]
            
            logger.info(f"\nWindow {i+1}/{n_windows}: "
                       f"In-sample: {len(in_sample_data)} bars, "
                       f"Out-sample: {len(out_sample_data)} bars")
            
            # Optimize on in-sample data
            opt_result = await self.optimizer.grid_search(
                strategy_class=strategy_class,
                symbol=symbol,
                data=in_sample_data,
                param_grid=param_grid,
                n_splits=3
            )
            
            # Test on out-of-sample data
            strategy = strategy_class(**opt_result.best_params)
            out_sample_result = await self.optimizer.backtest_engine.run_backtest(
                strategy=strategy,
                symbol=symbol,
                data=out_sample_data
            )
            
            results.append({
                'window': i + 1,
                'in_sample_params': opt_result.best_params,
                'in_sample_score': opt_result.best_score,
                'out_sample_return': out_sample_result.total_return_pct,
                'out_sample_sharpe': out_sample_result.sharpe_ratio,
                'out_sample_drawdown': out_sample_result.max_drawdown
            })
            
            logger.info(f"Out-of-sample: Return {out_sample_result.total_return_pct:.2f}%, "
                       f"Sharpe {out_sample_result.sharpe_ratio:.2f}")
        
        # Calculate aggregate statistics
        avg_out_sample_return = np.mean([r['out_sample_return'] for r in results])
        avg_out_sample_sharpe = np.mean([r['out_sample_sharpe'] for r in results])
        
        logger.info(f"\nWalk-forward complete - Avg out-of-sample return: {avg_out_sample_return:.2f}%, "
                   f"Avg Sharpe: {avg_out_sample_sharpe:.2f}")
        
        return {
            'results': results,
            'avg_out_sample_return': avg_out_sample_return,
            'avg_out_sample_sharpe': avg_out_sample_sharpe
        }
