"""
ARUNABHA ALGO BOT - Monte Carlo Simulation
Simulates thousands of possible outcomes
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from scipy import stats

logger = logging.getLogger(__name__)


class MonteCarloSimulator:
    """
    Performs Monte Carlo simulations to assess risk
    """
    
    def __init__(self):
        self.simulations: List[Dict] = []
        
    def simulate(
        self,
        trades: List[Dict],
        num_simulations: int = 1000,
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation
        
        Args:
            trades: List of historical trades
            num_simulations: Number of simulations to run
            confidence_level: Confidence level for VaR
        
        Returns:
            Simulation results
        """
        if len(trades) < 10:
            logger.warning("Insufficient trades for Monte Carlo simulation")
            return {}
        
        # Extract returns
        returns = [t['pnl_pct'] for t in trades if 'pnl_pct' in t]
        
        if not returns:
            return {}
        
        # Fit distribution
        mean = np.mean(returns)
        std = np.std(returns)
        
        # Run simulations
        simulation_results = []
        
        for i in range(num_simulations):
            # Generate random sequence
            sim_returns = np.random.normal(mean, std, len(returns))
            
            # Calculate cumulative return
            cumulative = np.cumprod(1 + np.array(sim_returns) / 100) - 1
            final_return = cumulative[-1] * 100
            
            # Calculate max drawdown
            peak = np.maximum.accumulate(cumulative)
            drawdown = (peak - cumulative) / (1 + peak) * 100
            max_dd = np.max(drawdown)
            
            simulation_results.append({
                'final_return': final_return,
                'max_drawdown': max_dd,
                'sharpe': np.mean(sim_returns) / np.std(sim_returns) * np.sqrt(252) if np.std(sim_returns) > 0 else 0
            })
        
        # Calculate statistics
        final_returns = [r['final_return'] for r in simulation_results]
        max_drawdowns = [r['max_drawdown'] for r in simulation_results]
        sharpes = [r['sharpe'] for r in simulation_results]
        
        # Calculate VaR
        var_index = int((1 - confidence_level) * num_simulations)
        sorted_returns = sorted(final_returns)
        var = sorted_returns[var_index] if var_index < len(sorted_returns) else sorted_returns[-1]
        
        # Calculate CVaR
        cvar = np.mean([r for r in sorted_returns if r <= var])
        
        self.simulations = simulation_results
        
        return {
            'num_simulations': num_simulations,
            'confidence_level': confidence_level,
            'mean_return': np.mean(final_returns),
            'median_return': np.median(final_returns),
            'std_return': np.std(final_returns),
            'max_return': max(final_returns),
            'min_return': min(final_returns),
            'var': var,
            'cvar': cvar,
            'prob_profit': sum(1 for r in final_returns if r > 0) / num_simulations * 100,
            'prob_loss': sum(1 for r in final_returns if r < 0) / num_simulations * 100,
            'mean_drawdown': np.mean(max_drawdowns),
            'max_drawdown_95': np.percentile(max_drawdowns, 95),
            'mean_sharpe': np.mean(sharpes),
            'sharpe_95': np.percentile(sharpes, 95)
        }
    
    def simulate_with_resampling(
        self,
        trades: List[Dict],
        num_simulations: int = 1000,
        sample_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo with bootstrap resampling
        """
        if len(trades) < 10:
            return {}
        
        returns = [t['pnl_pct'] for t in trades if 'pnl_pct' in t]
        
        if not returns:
            return {}
        
        if not sample_size:
            sample_size = len(returns)
        
        simulation_results = []
        
        for i in range(num_simulations):
            # Resample with replacement
            sample = np.random.choice(returns, sample_size, replace=True)
            
            # Calculate metrics
            final_return = np.sum(sample)
            max_drawdown = self._calculate_max_drawdown_from_returns(sample)
            sharpe = np.mean(sample) / np.std(sample) * np.sqrt(252) if np.std(sample) > 0 else 0
            
            simulation_results.append({
                'final_return': final_return,
                'max_drawdown': max_drawdown,
                'sharpe': sharpe
            })
        
        # Calculate percentiles
        final_returns = [r['final_return'] for r in simulation_results]
        
        return {
            'num_simulations': num_simulations,
            'mean_return': np.mean(final_returns),
            'median_return': np.median(final_returns),
            'std_return': np.std(final_returns),
            'percentile_5': np.percentile(final_returns, 5),
            'percentile_25': np.percentile(final_returns, 25),
            'percentile_75': np.percentile(final_returns, 75),
            'percentile_95': np.percentile(final_returns, 95),
            'prob_profit': sum(1 for r in final_returns if r > 0) / num_simulations * 100
        }
    
    def _calculate_max_drawdown_from_returns(self, returns: List[float]) -> float:
        """Calculate max drawdown from return series"""
        cumulative = np.cumprod(1 + np.array(returns) / 100)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (peak - cumulative) / peak * 100
        return np.max(drawdown)
    
    def print_summary(self, results: Dict[str, Any]):
        """Print Monte Carlo summary"""
        print("\n" + "="*60)
        print("MONTE CARLO SIMULATION RESULTS")
        print("="*60)
        print(f"Simulations: {results.get('num_simulations', 0)}")
        print(f"Confidence Level: {results.get('confidence_level', 0.95)*100:.0f}%")
        print(f"\nReturn Distribution:")
        print(f"  Mean: {results.get('mean_return', 0):+.2f}%")
        print(f"  Median: {results.get('median_return', 0):+.2f}%")
        print(f"  Std Dev: {results.get('std_return', 0):.2f}%")
        print(f"  Best: {results.get('max_return', 0):+.2f}%")
        print(f"  Worst: {results.get('min_return', 0):+.2f}%")
        print(f"\nRisk Metrics:")
        print(f"  VaR ({results.get('confidence_level', 0.95)*100:.0f}%): {results.get('var', 0):+.2f}%")
        print(f"  CVaR: {results.get('cvar', 0):+.2f}%")
        print(f"  Prob Profit: {results.get('prob_profit', 0):.1f}%")
        print(f"  Prob Loss: {results.get('prob_loss', 0):.1f}%")
        print(f"\nDrawdown:")
        print(f"  Mean Max DD: {results.get('mean_drawdown', 0):.2f}%")
        print(f"  95% Max DD: {results.get('max_drawdown_95', 0):.2f}%")
        print("="*60)
