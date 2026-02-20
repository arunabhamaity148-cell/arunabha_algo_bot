"""
ARUNABHA ALGO BOT - Walk Forward Analysis
Validates strategy robustness through walk-forward testing
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from backtest.backtest_engine import BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


class WalkForwardAnalyzer:
    """
    Performs walk-forward analysis to validate strategy robustness
    """
    
    def __init__(self, engine: BacktestEngine):
        self.engine = engine
        self.results: List[Dict] = []
        
    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        train_window: int = 60,  # days
        test_window: int = 30,    # days
        step_size: int = 30       # days
    ) -> Dict[str, Any]:
        """
        Perform walk-forward analysis
        
        Args:
            df: Historical data
            symbol: Trading symbol
            train_window: Training window in days
            test_window: Testing window in days
            step_size: Step size in days
        
        Returns:
            Walk-forward results
        """
        logger.info(f"Starting walk-forward analysis with train={train_window}d, test={test_window}d, step={step_size}d")
        
        results = []
        dates = df.index
        
        start_idx = 0
        while start_idx + train_window + test_window < len(dates):
            # Define windows
            train_start = dates[start_idx]
            train_end = dates[start_idx + train_window]
            test_start = dates[start_idx + train_window]
            test_end = dates[start_idx + train_window + test_window]
            
            logger.debug(f"Window {len(results)+1}: train {train_start.date()} to {train_end.date()}, test {test_start.date()} to {test_end.date()}")
            
            # Run backtest on training data
            train_result = self.engine.run(
                df,
                symbol,
                start_date=train_start.strftime('%Y-%m-%d'),
                end_date=train_end.strftime('%Y-%m-%d')
            )
            
            # Run backtest on test data (using same parameters)
            test_result = self.engine.run(
                df,
                symbol,
                start_date=test_start.strftime('%Y-%m-%d'),
                end_date=test_end.strftime('%Y-%m-%d')
            )
            
            results.append({
                'window': len(results) + 1,
                'train_start': train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
                'train_trades': train_result.total_trades,
                'train_win_rate': train_result.win_rate,
                'train_return': train_result.total_pnl_percent,
                'train_sharpe': train_result.sharpe_ratio,
                'test_trades': test_result.total_trades,
                'test_win_rate': test_result.win_rate,
                'test_return': test_result.total_pnl_percent,
                'test_sharpe': test_result.sharpe_ratio
            })
            
            # Move to next window
            start_idx += step_size
        
        # Calculate overall statistics
        stats = self._calculate_stats(results)
        
        self.results = results
        return {
            'windows': results,
            'statistics': stats,
            'is_robust': self._is_robust(stats)
        }
    
    def _calculate_stats(self, results: List[Dict]) -> Dict:
        """Calculate overall statistics"""
        
        if not results:
            return {}
        
        train_returns = [r['train_return'] for r in results]
        test_returns = [r['test_return'] for r in results]
        train_sharpes = [r['train_sharpe'] for r in results]
        test_sharpes = [r['test_sharpe'] for r in results]
        
        # Calculate decay
        return_decay = np.mean(test_returns) - np.mean(train_returns)
        sharpe_decay = np.mean(test_sharpes) - np.mean(train_sharpes)
        
        # Calculate consistency
        positive_train = sum(1 for r in train_returns if r > 0)
        positive_test = sum(1 for r in test_returns if r > 0)
        
        return {
            'num_windows': len(results),
            'avg_train_return': np.mean(train_returns),
            'avg_test_return': np.mean(test_returns),
            'avg_train_sharpe': np.mean(train_sharpes),
            'avg_test_sharpe': np.mean(test_sharpes),
            'return_decay': return_decay,
            'sharpe_decay': sharpe_decay,
            'positive_train_ratio': positive_train / len(results) * 100,
            'positive_test_ratio': positive_test / len(results) * 100,
            'max_train_return': max(train_returns),
            'max_test_return': max(test_returns),
            'min_train_return': min(train_returns),
            'min_test_return': min(test_returns)
        }
    
    def _is_robust(self, stats: Dict) -> bool:
        """Determine if strategy is robust"""
        
        if not stats:
            return False
        
        # Criteria for robustness
        criteria = [
            stats.get('avg_test_return', -100) > 0,  # Positive average return
            stats.get('positive_test_ratio', 0) > 60,  # >60% windows profitable
            stats.get('return_decay', 100) > -5,  # Decay not too severe
            stats.get('avg_test_sharpe', -10) > 0.5  # Sharpe > 0.5
        ]
        
        return all(criteria)
    
    def print_summary(self):
        """Print walk-forward summary"""
        if not self.results:
            print("No walk-forward results")
            return
        
        stats = self._calculate_stats(self.results)
        
        print("\n" + "="*60)
        print("WALK-FORWARD ANALYSIS RESULTS")
        print("="*60)
        print(f"Windows Analyzed: {stats['num_windows']}")
        print(f"\nTraining Performance:")
        print(f"  Avg Return: {stats['avg_train_return']:.2f}%")
        print(f"  Avg Sharpe: {stats['avg_train_sharpe']:.2f}")
        print(f"  Profitable Windows: {stats['positive_train_ratio']:.1f}%")
        print(f"\nTesting Performance:")
        print(f"  Avg Return: {stats['avg_test_return']:.2f}%")
        print(f"  Avg Sharpe: {stats['avg_test_sharpe']:.2f}")
        print(f"  Profitable Windows: {stats['positive_test_ratio']:.1f}%")
        print(f"\nRobustness Metrics:")
        print(f"  Return Decay: {stats['return_decay']:+.2f}%")
        print(f"  Sharpe Decay: {stats['sharpe_decay']:+.2f}")
        print(f"\nStrategy Robust: {'✅ YES' if self._is_robust(stats) else '❌ NO'}")
        print("="*60)
