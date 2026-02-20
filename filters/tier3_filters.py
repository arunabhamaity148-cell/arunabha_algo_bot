"""
ARUNABHA ALGO BOT - Tier 3 Filters
Bonus filters that add extra confidence
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
import numpy as np

import config
from analysis.technical import TechnicalAnalyzer
from analysis.liquidity import LiquidityDetector
from analysis.correlation import CorrelationAnalyzer

logger = logging.getLogger(__name__)


class Tier3Filters:
    """
    Tier 3 bonus filters
    Add extra points to signal confidence
    """
    
    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.liquidity = LiquidityDetector()
        self.correlation = CorrelationAnalyzer()
        self.bonus_points = {
            "whale_movement": 5,
            "liquidity_grab": 8,
            "iceberg_detection": 5,
            "news_sentiment": 3,
            "correlation_break": 4,
            "fibonacci_level": 2
        }
    
    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        data: Dict[str, Any]
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Evaluate all Tier 3 filters
        Returns: (total_bonus_points, results_dict)
        """
        results = {}
        total_bonus = 0
        
        # Filter 1: Whale Movement
        whale_bonus, whale_msg = self._check_whale_movement(data)
        results["whale_movement"] = {
            "bonus": whale_bonus,
            "message": whale_msg,
            "max_bonus": self.bonus_points["whale_movement"]
        }
        total_bonus += whale_bonus
        
        # Filter 2: Liquidity Grab
        grab_bonus, grab_msg = self._check_liquidity_grab(data, direction)
        results["liquidity_grab"] = {
            "bonus": grab_bonus,
            "message": grab_msg,
            "max_bonus": self.bonus_points["liquidity_grab"]
        }
        total_bonus += grab_bonus
        
        # Filter 3: Iceberg Detection
        iceberg_bonus, iceberg_msg = self._check_iceberg(data)
        results["iceberg_detection"] = {
            "bonus": iceberg_bonus,
            "message": iceberg_msg,
            "max_bonus": self.bonus_points["iceberg_detection"]
        }
        total_bonus += iceberg_bonus
        
        # Filter 4: News Sentiment
        news_bonus, news_msg = self._check_news_sentiment(symbol)
        results["news_sentiment"] = {
            "bonus": news_bonus,
            "message": news_msg,
            "max_bonus": self.bonus_points["news_sentiment"]
        }
        total_bonus += news_bonus
        
        # Filter 5: Correlation Break
        corr_bonus, corr_msg = self._check_correlation_break(symbol, data, direction)
        results["correlation_break"] = {
            "bonus": corr_bonus,
            "message": corr_msg,
            "max_bonus": self.bonus_points["correlation_break"]
        }
        total_bonus += corr_bonus
        
        # Filter 6: Fibonacci Level
        fib_bonus, fib_msg = self._check_fibonacci_level(data, direction)
        results["fibonacci_level"] = {
            "bonus": fib_bonus,
            "message": fib_msg,
            "max_bonus": self.bonus_points["fibonacci_level"]
        }
        total_bonus += fib_bonus
        
        logger.debug(f"Tier3 bonus points: {total_bonus}")
        
        return total_bonus, results
    
    def _check_whale_movement(
        self,
        data: Dict[str, Any]
    ) -> Tuple[int, str]:
        """
        Detect whale movements from orderbook
        """
        orderbook = data.get("orderbook", {})
        
        if not orderbook:
            return 0, "No orderbook data"
        
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        if not bids or not asks:
            return 0, "Insufficient orderbook data"
        
        # Check for large orders near price
        large_bid_threshold = 50000  # $50k
        large_ask_threshold = 50000
        
        large_bids = [b for b in bids if b[1] > large_bid_threshold]
        large_asks = [a for a in asks if a[1] > large_ask_threshold]
        
        if large_bids and not large_asks:
            return 5, f"Whale accumulation detected ({len(large_bids)} large bids)"
        elif large_asks and not large_bids:
            return 5, f"Whale distribution detected ({len(large_asks)} large asks)"
        elif large_bids and large_asks:
            return 3, "Whale activity on both sides"
        else:
            return 0, "No significant whale movement"
    
    def _check_liquidity_grab(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[int, str]:
        """
        Detect liquidity grab patterns
        """
        ohlcv = data.get("ohlcv", {}).get("5m", [])
        
        if len(ohlcv) < 10:
            return 0, "Insufficient data"
        
        result = self.liquidity.detect(ohlcv, lookback=10)
        
        if direction == "LONG" and result.grab_direction == "LONG":
            return 8, "Liquidity grab detected (bullish)"
        elif direction == "SHORT" and result.grab_direction == "SHORT":
            return 8, "Liquidity grab detected (bearish)"
        elif result.grab_detected:
            return 5, f"Liquidity grab: {result.grab_direction}"
        else:
            return 0, "No liquidity grab"
    
    def _check_iceberg(
        self,
        data: Dict[str, Any]
    ) -> Tuple[int, str]:
        """
        Detect iceberg orders (large hidden orders)
        """
        orderbook = data.get("orderbook", {})
        
        if not orderbook:
            return 0, "No orderbook data"
        
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        # Look for repeating patterns in order sizes
        def detect_iceberg(orders, side):
            if len(orders) < 5:
                return False
            
            sizes = [o[1] for o in orders[:10]]
            
            # Check for similar sized orders
            for i in range(1, len(sizes)):
                if abs(sizes[i] - sizes[0]) / sizes[0] < 0.1:
                    if i > 2:  # Multiple similar sizes
                        return True
            return False
        
        bid_iceberg = detect_iceberg(bids, "bid")
        ask_iceberg = detect_iceberg(asks, "ask")
        
        if bid_iceberg and not ask_iceberg:
            return 5, "Iceberg buy orders detected"
        elif ask_iceberg and not bid_iceberg:
            return 5, "Iceberg sell orders detected"
        elif bid_iceberg and ask_iceberg:
            return 3, "Iceberg orders on both sides"
        else:
            return 0, "No iceberg orders detected"
    
    def _check_news_sentiment(
        self,
        symbol: str
    ) -> Tuple[int, str]:
        """
        Check news sentiment (simplified)
        In production, would integrate with news API
        """
        # Placeholder - in production would fetch real news
        # For now, return 0 with appropriate message
        return 0, "News sentiment check disabled"
    
    def _check_correlation_break(
        self,
        symbol: str,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[int, str]:
        """
        Check if symbol is breaking correlation with BTC
        """
        # Get price data
        prices = {}
        
        # Extract price series
        for pair in ["BTC/USDT", symbol]:
            ohlcv = data.get("ohlcv", {}).get("1h", [])
            if ohlcv:
                prices[pair] = [c[4] for c in ohlcv[-50:]]
        
        if "BTC/USDT" not in prices or symbol not in prices:
            return 0, "Insufficient correlation data"
        
        # Analyze correlation
        result = self.correlation.analyze(symbol, prices, lookback=20)
        
        if result.is_diverging:
            if direction == "LONG" and result.btc_correlation < 0.3:
                return 4, f"Breaking correlation with BTC (r={result.btc_correlation:.2f})"
            elif direction == "SHORT" and result.btc_correlation < 0.3:
                return 4, f"Breaking correlation with BTC (r={result.btc_correlation:.2f})"
            else:
                return 2, "Correlation breaking"
        else:
            return 0, f"Normal correlation (r={result.btc_correlation:.2f})"
    
    def _check_fibonacci_level(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[int, str]:
        """
        Check if price is at Fibonacci level
        """
        ohlcv = data.get("ohlcv", {}).get("4h", [])
        
        if len(ohlcv) < 20:
            return 0, "Insufficient data"
        
        # Find recent swing high/low
        highs = [c[2] for c in ohlcv[-20:]]
        lows = [c[3] for c in ohlcv[-20:]]
        
        swing_high = max(highs)
        swing_low = min(lows)
        current = ohlcv[-1][4]
        
        # Calculate Fibonacci levels
        diff = swing_high - swing_low
        fib_levels = {
            0.236: swing_high - diff * 0.236,
            0.382: swing_high - diff * 0.382,
            0.5: swing_high - diff * 0.5,
            0.618: swing_high - diff * 0.618,
            0.786: swing_high - diff * 0.786
        }
        
        # Check if near any level
        threshold = diff * 0.02  # Within 2% of level
        
        for level, price in fib_levels.items():
            if abs(current - price) < threshold:
                if direction == "LONG" and level >= 0.5:
                    return 2, f"At Fibonacci {level*100:.1f}% support"
                elif direction == "SHORT" and level <= 0.382:
                    return 2, f"At Fibonacci {level*100:.1f}% resistance"
                else:
                    return 1, f"At Fibonacci {level*100:.1f}%"
        
        return 0, "Not at Fibonacci level"
