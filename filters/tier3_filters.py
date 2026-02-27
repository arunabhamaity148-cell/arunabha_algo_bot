"""
ARUNABHA ALGO BOT - Tier 3 Filters v5.0
========================================
UPGRADE: Tier3 Correlation Fix
- btc_prices now properly passed from data packet
- correlation.analyze() gets real BTC prices → not always 0.5
- Order Book Imbalance filter added (bid/ask volume ratio)
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
    Tier 3 bonus filters — add score on top of Tier2
    Do NOT block signals; only add bonus points.
    """

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.liquidity = LiquidityDetector()
        self.correlation = CorrelationAnalyzer()

        self.bonus_points = {
            "whale_movement": 5,
            "liquidity_grab": 5,
            "fibonacci_level": 3,
            "correlation_break": 4,
            "orderbook_imbalance": 4,    # NEW
            "news_sentiment": 3,
        }

    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        data: Dict[str, Any]
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Evaluate all Tier 3 bonus filters.
        Returns: (total_bonus, results_dict)
        """
        results = {}
        total_bonus = 0

        # 1. Whale Movement
        whale_bonus, whale_msg = self._check_whale_movement(data)
        results["whale_movement"] = {
            "bonus": whale_bonus,
            "max_bonus": self.bonus_points["whale_movement"],
            "message": whale_msg
        }
        total_bonus += whale_bonus

        # 2. Liquidity Grab
        liq_bonus, liq_msg = self._check_liquidity_grab(data, direction)
        results["liquidity_grab"] = {
            "bonus": liq_bonus,
            "max_bonus": self.bonus_points["liquidity_grab"],
            "message": liq_msg
        }
        total_bonus += liq_bonus

        # 3. Fibonacci Level
        fib_bonus, fib_msg = self._check_fibonacci(data, direction)
        results["fibonacci_level"] = {
            "bonus": fib_bonus,
            "max_bonus": self.bonus_points["fibonacci_level"],
            "message": fib_msg
        }
        total_bonus += fib_bonus

        # 4. Correlation Break (FIXED — now passes btc_prices)
        corr_bonus, corr_msg = self._check_correlation_break(symbol, data, direction)
        results["correlation_break"] = {
            "bonus": corr_bonus,
            "max_bonus": self.bonus_points["correlation_break"],
            "message": corr_msg
        }
        total_bonus += corr_bonus

        # 5. Order Book Imbalance (NEW)
        ob_bonus, ob_msg = self._check_orderbook_imbalance(data, direction)
        results["orderbook_imbalance"] = {
            "bonus": ob_bonus,
            "max_bonus": self.bonus_points["orderbook_imbalance"],
            "message": ob_msg
        }
        total_bonus += ob_bonus

        return total_bonus, results

    def _check_whale_movement(self, data: Dict) -> Tuple[int, str]:
        """Check for abnormal volume spikes indicating whale activity"""
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return 0, "Insufficient data"

        volumes = [float(c[5]) for c in ohlcv]
        avg_vol = sum(volumes[-20:-1]) / 19
        current_vol = volumes[-1]

        if avg_vol == 0:
            return 0, "Zero volume"

        ratio = current_vol / avg_vol

        if ratio >= 3.0:
            return 5, f"🐋 Whale volume: {ratio:.1f}x average"
        elif ratio >= 2.0:
            return 3, f"Large volume: {ratio:.1f}x average"
        elif ratio >= 1.5:
            return 1, f"Above avg volume: {ratio:.1f}x"

        return 0, f"Normal volume: {ratio:.1f}x"

    def _check_liquidity_grab(self, data: Dict, direction: Optional[str]) -> Tuple[int, str]:
        """Check for liquidity grab / stop hunt pattern"""
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 10:
            return 0, "Insufficient data"

        last = ohlcv[-1]
        prev = ohlcv[-2]

        high = float(last[2])
        low = float(last[3])
        close = float(last[4])
        open_ = float(last[1])

        candle_range = high - low
        if candle_range == 0:
            return 0, "Zero range candle"

        # Long lower wick = stop hunt below, then reversal up
        lower_wick = min(open_, close) - low
        upper_wick = high - max(open_, close)

        lower_wick_pct = lower_wick / candle_range
        upper_wick_pct = upper_wick / candle_range

        if direction == "LONG" and lower_wick_pct > 0.6:
            return 5, f"Liquidity grab down (wick={lower_wick_pct:.0%}) → reversal ✅"
        if direction == "SHORT" and upper_wick_pct > 0.6:
            return 5, f"Liquidity grab up (wick={upper_wick_pct:.0%}) → reversal ✅"
        if lower_wick_pct > 0.4 or upper_wick_pct > 0.4:
            return 2, "Minor liquidity grab"

        return 0, "No liquidity grab"

    def _check_fibonacci(self, data: Dict, direction: Optional[str]) -> Tuple[int, str]:
        """Check if price is at a key Fibonacci retracement level"""
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 30:
            return 0, "Insufficient data"

        closes = [float(c[4]) for c in ohlcv]
        highs = [float(c[2]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]

        recent_high = max(highs[-30:])
        recent_low = min(lows[-30:])
        current = closes[-1]

        if recent_high == recent_low:
            return 0, "No range"

        swing = recent_high - recent_low
        fib_levels = {
            "0.236": recent_high - swing * 0.236,
            "0.382": recent_high - swing * 0.382,
            "0.5":   recent_high - swing * 0.5,
            "0.618": recent_high - swing * 0.618,
            "0.786": recent_high - swing * 0.786,
        }

        tolerance = swing * 0.01   # 1% of swing

        for label, level in fib_levels.items():
            if abs(current - level) <= tolerance:
                key_fibs = ["0.382", "0.5", "0.618"]
                bonus = 3 if label in key_fibs else 1
                return bonus, f"At Fibonacci {label} ({level:.4f}) ✅"

        return 0, "No Fibonacci confluence"

    def _check_correlation_break(
        self,
        symbol: str,
        data: Dict,
        direction: Optional[str]
    ) -> Tuple[int, str]:
        """
        FIXED: Now properly passes BTC prices from data packet.
        Symbol breaking correlation with BTC = independent move = higher quality.
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if not ohlcv or len(ohlcv) < 20:
            return 0, "Insufficient data"

        if symbol == "BTC/USDT":
            return 0, "BTC/USDT — correlation with itself skipped"

        prices = [float(c[4]) for c in ohlcv]

        # FIXED: get BTC prices from data packet
        btc_ohlcv = data.get("btc_ohlcv", {}).get("15m", [])
        btc_prices = [float(c[4]) for c in btc_ohlcv] if btc_ohlcv else None

        result = self.correlation.analyze(
            symbol=symbol,
            prices=prices,
            btc_prices=btc_prices,
            lookback=20
        )

        if result.is_decorrelated:
            if direction == "LONG" and result.direction == "BREAKING_UP":
                return 4, f"Breaking BTC correlation UPWARD (r={result.btc_correlation:.2f}) ✅"
            elif direction == "SHORT" and result.direction == "BREAKING_DOWN":
                return 4, f"Breaking BTC correlation DOWNWARD (r={result.btc_correlation:.2f}) ✅"
            return 2, f"Decorrelated from BTC (r={result.btc_correlation:.2f})"

        return 0, f"Normal BTC correlation (r={result.btc_correlation:.2f})"

    def _check_orderbook_imbalance(
        self,
        data: Dict,
        direction: Optional[str]
    ) -> Tuple[int, str]:
        """
        NEW: Order book bid/ask volume ratio.
        bid_vol / ask_vol > 1.5 = buy pressure → LONG bonus
        ask_vol / bid_vol > 1.5 = sell pressure → SHORT bonus
        """
        orderbook = data.get("orderbook", {})
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        if not bids or not asks or len(bids) < 5 or len(asks) < 5:
            return 0, "No orderbook data"

        try:
            bid_vol = sum(float(b[1]) for b in bids[:10])
            ask_vol = sum(float(a[1]) for a in asks[:10])
        except (TypeError, ValueError, IndexError):
            return 0, "Invalid orderbook data"

        if bid_vol == 0 or ask_vol == 0:
            return 0, "Zero volume in orderbook"

        imbalance = bid_vol / ask_vol

        if direction == "LONG":
            if imbalance >= 2.0:
                return 4, f"Strong buy pressure: bid/ask={imbalance:.2f} ✅"
            elif imbalance >= 1.5:
                return 2, f"Moderate buy pressure: bid/ask={imbalance:.2f}"
            elif imbalance < 0.7:
                return 0, f"Sell pressure dominates: bid/ask={imbalance:.2f} ⚠️"

        elif direction == "SHORT":
            if imbalance <= 0.5:
                return 4, f"Strong sell pressure: bid/ask={imbalance:.2f} ✅"
            elif imbalance <= 0.7:
                return 2, f"Moderate sell pressure: bid/ask={imbalance:.2f}"
            elif imbalance > 1.5:
                return 0, f"Buy pressure dominates: bid/ask={imbalance:.2f} ⚠️"

        return 1, f"Orderbook balanced: bid/ask={imbalance:.2f}"
