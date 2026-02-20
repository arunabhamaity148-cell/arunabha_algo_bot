"""
ARUNABHA ALGO BOT - Overfitting Detector
Detects strategy overfitting using various methods
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from scipy import stats

logger = logging.getLogger(__name__)


class OverfittingDetector:
    """
    Detects overfitting in trading strategies
    """
    
    def __init__(self):
        self.results: Dict = {}
        
    def detect(
        self,
        train_results: Dict,
        test_results: Dict,
        method: str = 'all'
    ) -> Dict[str, Any]:
        """
        Detect overfitting using various methods
        
        Args:
            train_results: Results on training data
            test_results: Results on test data
            method: Detection method ('decay', 'sharpe', 'correlation', 'all')
        
        Returns:
            Overfitting assessment
        """
        
        assessment = {
            'is_overfitting': False,
            'confidence': 0,
            'methods': {},
            'details': {}
        }
        
        if method in ['decay', 'all']:
            decay_result = self._check_performance_decay(train_results, test_results)
            assessment['methods']['decay'] = decay_result
            if decay_result['overfitting']:
                assessment['confidence'] += decay_result['severity'] * 0.4
        
        if method in ['sharpe', 'all']:
            sharpe_result = self._check_sharpe_degradation(train_results, test_results)
            assessment['methods']['sharpe'] = sharpe_result
            if sharpe_result['overfitting']:
                assessment['confidence'] += sharpe_result['severity'] * 0.3
        
        if method in ['correlation', 'all']:
            corr_result = self._check_train_test_correlation(train_results, test_results)
            assessment['methods']['correlation'] = corr_result
            if corr_result['overfitting']:
                assessment['confidence'] += corr_result['severity'] * 0.3
        
        # Overall assessment
        assessment['is_overfitting'] = assessment['confidence'] > 50
        assessment['confidence'] = min(100, assessment['confidence'])
        
        self.results = assessment
        return assessment
    
    def _check_performance_decay(self, train: Dict, test: Dict) -> Dict:
        """Check performance decay between train and test"""
        
        train_return = train.get('total_pnl_percent', 0)
        test_return = test.get('total_pnl_percent', 0)
        
        train_win_rate = train.get('win_rate', 0)
        test_win_rate = test.get('win_rate', 0)
        
        # Calculate decay
        return_decay = ((train_return - test_return) / abs(train_return) * 100 
                       if train_return != 0 else 0)
        win_rate_decay = train_win_rate - test_win_rate
        
        # Determine severity
        if return_decay > 50 or win_rate_decay > 20:
            severity = 80
            overfitting = True
        elif return_decay > 30 or win_rate_decay > 10:
            severity = 50
            overfitting = True
        elif return_decay > 10 or win_rate_decay > 5:
            severity = 20
            overfitting = False
        else:
            severity = 0
            overfitting = False
        
        return {
            'overfitting': overfitting,
            'severity': severity,
            'return_decay': return_decay,
            'win_rate_decay': win_rate_decay,
            'train_return': train_return,
            'test_return': test_return,
            'train_win_rate': train_win_rate,
            'test_win_rate': test_win_rate
        }
    
    def _check_sharpe_degradation(self, train: Dict, test: Dict) -> Dict:
        """Check Sharpe ratio degradation"""
        
        train_sharpe = train.get('sharpe_ratio', 0)
        test_sharpe = test.get('sharpe_ratio', 0)
        
        if train_sharpe <= 0:
            return {'overfitting': False, 'severity': 0, 'message': 'Train Sharpe not positive'}
        
        sharpe_ratio = test_sharpe / train_sharpe if train_sharpe > 0 else 0
        
        if sharpe_ratio < 0.3:
            severity = 90
            overfitting = True
        elif sharpe_ratio < 0.5:
            severity = 60
            overfitting = True
        elif sharpe_ratio < 0.7:
            severity = 30
            overfitting = False
        else:
            severity = 0
            overfitting = False
        
        return {
            'overfitting': overfitting,
            'severity': severity,
            'sharpe_ratio': sharpe_ratio,
            'train_sharpe': train_sharpe,
            'test_sharpe': test_sharpe
        }
    
    def _check_train_test_correlation(self, train: Dict, test: Dict) -> Dict:
        """Check correlation between train and test performance"""
        
        # This is a simplified version - in practice, would use more sophisticated methods
        train_trades = train.get('trades', [])
        test_trades = test.get('trades', [])
        
        if len(train_trades) < 5 or len(test_trades) < 5:
            return {'overfitting': False, 'severity': 0, 'message': 'Insufficient trades'}
        
        train_returns = [t['pnl_pct'] for t in train_trades]
        test_returns = [t['pnl_pct'] for t in test_trades]
        
        # Compare distributions
        ks_statistic, p_value = stats.ks_2samp(train_returns, test_returns)
        
        # If distributions are too different, might be overfitting
        if p_value < 0.05:
            severity = 70
            overfitting = True
        elif p_value < 0.1:
            severity = 40
            overfitting = True
        else:
            severity = 0
            overfitting = False
        
        return {
            'overfitting': overfitting,
            'severity': severity,
            'ks_statistic': ks_statistic,
            'p_value': p_value,
            'train_mean': np.mean(train_returns),
            'test_mean': np.mean(test_returns)
        }
    
    def deflate_sharpe(self, sharpe: float, num_trials: int, num_tests: int) -> float:
        """
        Apply Deflated Sharpe Ratio to account for multiple tests
        
        Args:
            sharpe: Original Sharpe ratio
            num_trials: Number of strategy variations tested
            num_tests: Number of tests performed
        
        Returns:
            Deflated Sharpe ratio
        """
        if num_trials <= 1:
            return sharpe
        
        # Marc Lopeza de Prado's deflated Sharpe ratio
        from scipy.stats import norm
        
        # Estimate expected maximum Sharpe under null
        expected_max = norm.ppf(1 - 1/num_trials)
        
        # Adjust for number of tests
        adjusted_sharpe = sharpe - expected_max * np.sqrt(1/num_tests)
        
        return max(0, adjusted_sharpe)
    
    def print_summary(self, results: Dict[str, Any]):
        """Print overfitting assessment"""
        print("\n" + "="*60)
        print("OVERFITTING DETECTION RESULTS")
        print("="*60)
        print(f"Overfitting Detected: {'✅ YES' if results.get('is_overfitting') else '❌ NO'}")
        print(f"Confidence: {results.get('confidence', 0):.1f}%")
        
        print("\nMethod Results:")
        for method, method_result in results.get('methods', {}).items():
            print(f"\n  {method.upper()}:")
            if method == 'decay':
                print(f"    Return Decay: {method_result.get('return_decay', 0):.1f}%")
                print(f"    Win Rate Decay: {method_result.get('win_rate_decay', 0):.1f}%")
            elif method == 'sharpe':
                print(f"    Sharpe Ratio: {method_result.get('sharpe_ratio', 0):.2f}")
            elif method == 'correlation':
                print(f"    KS Statistic: {method_result.get('ks_statistic', 0):.3f}")
                print(f"    P-Value: {method_result.get('p_value', 0):.3f}")
            
            verdict = "⚠️ OVERFITTING" if method_result.get('overfitting') else "✅ OK"
            print(f"    Verdict: {verdict}")
        
        print("="*60)
