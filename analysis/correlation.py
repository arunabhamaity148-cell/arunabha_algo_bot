"""
ARUNABHA ALGO BOT - Correlation Analyzer
Analyzes correlations between different trading pairs
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CorrelationResult:
    """Correlation analysis result"""
    btc_correlation: float
    eth_correlation: float
    market_correlation: float
    sector_correlation: float
    is_diverging: bool
    strength: str
    reason: str


class CorrelationAnalyzer:
    """
    Analyzes correlations between trading pairs
    """
    
    def __init__(self, history_size: int = 50):
        self.history_size = history_size
        self.correlation_history: Dict[str, deque] = {}
        
    def analyze(
        self,
        symbol: str,
        prices: Dict[str, List[float]],
        lookback: int = 20
    ) -> CorrelationResult:
        """
        Analyze correlation with BTC, ETH, and market
        """
        if not prices or symbol not in prices:
            return CorrelationResult(
                btc_correlation=0.5,
                eth_correlation=0.5,
                market_correlation=0.5,
                sector_correlation=0.5,
                is_diverging=False,
                strength="UNKNOWN",
                reason="Insufficient data"
            )
        
        # Get price series
        symbol_prices = prices.get(symbol, [])
        btc_prices = prices.get("BTC/USDT", [])
        eth_prices = prices.get("ETH/USDT", [])
        
        if len(symbol_prices) < lookback or len(btc_prices) < lookback:
            return CorrelationResult(
                btc_correlation=0.5,
                eth_correlation=0.5,
                market_correlation=0.5,
                sector_correlation=0.5,
                is_diverging=False,
                strength="WEAK",
                reason="Insufficient history"
            )
        
        # Calculate returns
        symbol_returns = self._calculate_returns(symbol_prices[-lookback:])
        btc_returns = self._calculate_returns(btc_prices[-lookback:])
        eth_returns = self._calculate_returns(eth_prices[-lookback:])
        
        # Calculate correlations
        btc_corr = self._calculate_correlation(symbol_returns, btc_returns)
        eth_corr = self._calculate_correlation(symbol_returns, eth_returns)
        
        # Calculate market correlation (average of major pairs)
        market_returns = []
        for pair, p in prices.items():
            if pair in ["BTC/USDT", "ETH/USDT"]:
                continue
            if len(p) >= lookback:
                ret = self._calculate_returns(p[-lookback:])
                market_returns.append(ret)
        
        if market_returns:
            avg_market_returns = np.mean(market_returns, axis=0)
            market_corr = self._calculate_correlation(symbol_returns, avg_market_returns)
        else:
            market_corr = 0.5
        
        # Determine sector (simplified)
        sector = self._get_sector(symbol)
        sector_returns = []
        
        for pair, p in prices.items():
            if self._get_sector(pair) == sector and pair != symbol:
                if len(p) >= lookback:
                    ret = self._calculate_returns(p[-lookback:])
                    sector_returns.append(ret)
        
        if sector_returns:
            avg_sector_returns = np.mean(sector_returns, axis=0)
            sector_corr = self._calculate_correlation(symbol_returns, avg_sector_returns)
        else:
            sector_corr = 0.5
        
        # Check for divergence
        is_diverging = self._check_divergence(
            symbol_prices, btc_prices, lookback
        )
        
        # Determine strength
        if abs(btc_corr) > 0.7:
            strength = "STRONG"
            reason = "High BTC correlation"
        elif abs(btc_corr) > 0.4:
            strength = "MODERATE"
            reason = "Moderate BTC correlation"
        else:
            strength = "WEAK"
            reason = "Low BTC correlation"
        
        # Store history
        if symbol not in self.correlation_history:
            self.correlation_history[symbol] = deque(maxlen=self.history_size)
        
        self.correlation_history[symbol].append({
            "timestamp": len(self.correlation_history[symbol]),
            "btc_correlation": btc_corr,
            "market_correlation": market_corr
        })
        
        return CorrelationResult(
            btc_correlation=round(btc_corr, 3),
            eth_correlation=round(eth_corr, 3),
            market_correlation=round(market_corr, 3),
            sector_correlation=round(sector_corr, 3),
            is_diverging=is_diverging,
            strength=strength,
            reason=reason
        )
    
    def _calculate_returns(self, prices: List[float]) -> List[float]:
        """Calculate percentage returns"""
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                ret = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(ret)
        return returns
    
    def _calculate_correlation(
        self,
        x: List[float],
        y: List[float]
    ) -> float:
        """Calculate Pearson correlation coefficient"""
        if len(x) != len(y) or len(x) < 2:
            return 0.5
        
        n = len(x)
        
        # Calculate means
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        # Calculate covariance and standard deviations
        covariance = 0
        var_x = 0
        var_y = 0
        
        for i in range(n):
            diff_x = x[i] - mean_x
            diff_y = y[i] - mean_y
            covariance += diff_x * diff_y
            var_x += diff_x ** 2
            var_y += diff_y ** 2
        
        if var_x == 0 or var_y == 0:
            return 0.5
        
        correlation = covariance / ((var_x * var_y) ** 0.5)
        
        # Clip to valid range
        return max(-1, min(1, correlation))
    
    def _get_sector(self, symbol: str) -> str:
        """Get sector for a symbol"""
        symbol = symbol.lower()
        
        if "btc" in symbol:
            return "MAJOR"
        elif "eth" in symbol:
            return "MAJOR"
        elif "sol" in symbol:
            return "LAYER1"
        elif "ada" in symbol:
            return "LAYER1"
        elif "doge" in symbol:
            return "MEME"
        elif "shib" in symbol:
            return "MEME"
        elif "link" in symbol:
            return "ORACLE"
        elif "uni" in symbol:
            return "DEFI"
        elif "aave" in symbol:
            return "DEFI"
        else:
            return "OTHER"
    
    def _check_divergence(
        self,
        symbol_prices: List[float],
        btc_prices: List[float],
        lookback: int
    ) -> bool:
        """Check if symbol is diverging from BTC"""
        if len(symbol_prices) < lookback or len(btc_prices) < lookback:
            return False
        
        # Calculate recent performance
        symbol_change = (symbol_prices[-1] - symbol_prices[-lookback]) / symbol_prices[-lookback]
        btc_change = (btc_prices[-1] - btc_prices[-lookback]) / btc_prices[-lookback]
        
        # Check for significant divergence
        diff = abs(symbol_change - btc_change)
        
        return diff > 0.05  # 5% divergence
    
    def get_best_correlated_pairs(
        self,
        symbol: str,
        prices: Dict[str, List[float]],
        top_n: int = 3
    ) -> List[Tuple[str, float]]:
        """Get best correlated pairs for hedging"""
        correlations = []
        
        for other_symbol in prices:
            if other_symbol == symbol:
                continue
            
            result = self.analyze(symbol, {symbol: prices[symbol], other_symbol: prices[other_symbol]}, lookback=20)
            correlations.append((other_symbol, abs(result.btc_correlation)))
        
        # Sort by correlation
        correlations.sort(key=lambda x: x[1], reverse=True)
        
        return correlations[:top_n]
    
    def get_hedge_ratio(
        self,
        symbol1: str,
        symbol2: str,
        prices: Dict[str, List[float]],
        lookback: int = 50
    ) -> float:
        """Calculate hedge ratio for pair trading"""
        if symbol1 not in prices or symbol2 not in prices:
            return 1.0
        
        p1 = prices[symbol1][-lookback:]
        p2 = prices[symbol2][-lookback:]
        
        if len(p1) != len(p2) or len(p1) < 20:
            return 1.0
        
        # Simple linear regression for hedge ratio
        returns1 = self._calculate_returns(p1)
        returns2 = self._calculate_returns(p2)
        
        if len(returns1) != len(returns2):
            return 1.0
        
        # Calculate beta (hedge ratio)
        n = len(returns1)
        mean1 = sum(returns1) / n
        mean2 = sum(returns2) / n
        
        covariance = 0
        variance = 0
        
        for i in range(n):
            covariance += (returns1[i] - mean1) * (returns2[i] - mean2)
            variance += (returns2[i] - mean2) ** 2
        
        if variance == 0:
            return 1.0
        
        beta = covariance / variance
        
        return beta
    
    def is_market_cap_correlated(
        self,
        symbol: str,
        market_cap_data: Optional[List[float]] = None
    ) -> bool:
        """
        Check if symbol correlates with overall market cap
        (Simplified - in production would use actual market cap data)
        """
        # Most alts correlate with market cap
        if symbol in ["BTC/USDT", "ETH/USDT"]:
            return True
        
        # Some stablecoins don't
        if "USDT" in symbol or "USDC" in symbol:
            return False
        
        return True
