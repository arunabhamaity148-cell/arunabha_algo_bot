"""
ARUNABHA ALGO BOT - Tier 3 Filters v6.0
=========================================
NEW:
- liquidity_sweep: EQH/EQL/PDH/PDL sweep + retest confirmation (+6 pts max)
- cvd_absorption: Orderflow absorption pattern (+4 pts)

EXISTING:
- whale_movement: Volume spike whale detection (+5)
- liquidity_grab: Wick-based stop hunt (+5)
- fibonacci_level: Key Fib confluence (+3)
- correlation_break: BTC decorrelation (+4)
- orderbook_imbalance: Bid/ask ratio (+4)
"""

import logging
from typing import Dict, List, Tuple, Optional, Any

import numpy as np

import config
from analysis.technical import TechnicalAnalyzer
from analysis.liquidity import LiquidityDetector
from analysis.liquidity_sweep import LiquiditySweepDetector
from analysis.orderflow import OrderflowAnalyzer
from analysis.correlation import CorrelationAnalyzer

logger = logging.getLogger(__name__)


class Tier3Filters:

    def __init__(self):
        self.analyzer       = TechnicalAnalyzer()
        self.liquidity      = LiquidityDetector()
        self.sweep_detector = LiquiditySweepDetector()
        self.orderflow      = OrderflowAnalyzer()
        self.correlation    = CorrelationAnalyzer()

        self.bonus_points = {
            "whale_movement":     5,
            "liquidity_grab":     5,
            "liquidity_sweep":    6,   # NEW — EQH/EQL/PDH/PDL sweep + retest
            "cvd_absorption":     4,   # NEW — Orderflow absorption
            "fibonacci_level":    3,
            "correlation_break":  4,
            "orderbook_imbalance": 4,
        }

    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        data: Dict[str, Any]
    ) -> Tuple[int, Dict[str, Any]]:

        results = {}
        total_bonus = 0

        def add(name, fn, *args):
            nonlocal total_bonus
            bonus, msg = fn(*args)
            results[name] = {
                "bonus": bonus,
                "max_bonus": self.bonus_points[name],
                "message": msg
            }
            total_bonus += bonus

        add("whale_movement",     self._check_whale_movement,    data)
        add("liquidity_grab",     self._check_liquidity_grab,    data, direction)
        add("liquidity_sweep",    self._check_liquidity_sweep,   data, direction)   # ← NEW
        add("cvd_absorption",     self._check_cvd_absorption,    data, direction)   # ← NEW
        add("fibonacci_level",    self._check_fibonacci,         data, direction)
        add("correlation_break",  self._check_correlation_break, symbol, data, direction)
        add("orderbook_imbalance", self._check_orderbook_imbalance, data, direction)

        return total_bonus, results

    # ──────────────────────────────────────────────────────────────────
    # NEW: Liquidity Sweep (EQH/EQL/PDH/PDL)
    # ──────────────────────────────────────────────────────────────────

    def _check_liquidity_sweep(
        self, data: Dict, direction: Optional[str]
    ) -> Tuple[int, str]:
        """
        ICT-style liquidity sweep detection.

        Scoring:
          Sweep + retest + STRONG → 6 pts (max)
          Sweep + retest + MODERATE → 4 pts
          Sweep detected, no retest yet → 2 pts
          No sweep → 0 pts

        Types detected:
          EQH (Equal Highs)  → SHORT signal
          EQL (Equal Lows)   → LONG signal
          PDH (Previous Day High) → SHORT
          PDL (Previous Day Low)  → LONG
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 15:
            return 0, "Insufficient data for sweep detection"

        try:
            result = self.sweep_detector.analyze(ohlcv, direction=direction)

            if not result.sweep_detected:
                return 0, f"No sweep: {result.reason}"

            if result.sweep_direction != direction:
                return 0, f"Sweep {result.sweep_direction} ≠ direction {direction}"

            # Score by strength + retest
            if result.retest_confirmed and result.strength == "STRONG":
                pts = 6
            elif result.retest_confirmed and result.strength == "MODERATE":
                pts = 4
            elif result.retest_confirmed:
                pts = 3
            else:
                pts = 2  # sweep without retest — possible but less reliable

            eq_count = len(result.equal_levels)
            return pts, (
                f"{'✅✅' if pts >= 5 else '✅'} {result.sweep_type} sweep "
                f"@ {result.sweep_level:.4f} "
                f"({eq_count} levels, {result.strength}) "
                f"{'+ retest confirmed' if result.retest_confirmed else '(awaiting retest)'}"
            )

        except Exception as e:
            logger.warning(f"Liquidity sweep error: {e}")
            return 0, f"Sweep check error: {e}"

    # ──────────────────────────────────────────────────────────────────
    # NEW: CVD Absorption (from Orderflow)
    # ──────────────────────────────────────────────────────────────────

    def _check_cvd_absorption(
        self, data: Dict, direction: Optional[str]
    ) -> Tuple[int, str]:
        """
        Orderflow absorption: big players absorbing opposite side.

        BULL ABSORPTION: price falling, but buy delta increasing
          → Big buyers absorbing sells → LONG likely
          → +4 pts for LONG direction

        BEAR ABSORPTION: price rising, but sell delta increasing
          → Big sellers absorbing buys → SHORT likely
          → +4 pts for SHORT direction

        Also checks CVD divergence as secondary signal (+2 pts).
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 15:
            return 0, "Insufficient data for absorption"

        try:
            result = self.orderflow.analyze(ohlcv, period=20)

            # Primary: absorption match
            if (direction == "LONG" and
                    result.absorption_detected and
                    result.absorption_direction == "BULL_ABSORPTION"):
                strength_pct = int(result.absorption_strength * 100)
                return 4, (
                    f"✅ Bull absorption ({strength_pct}% strength) | "
                    f"Buy pressure: {result.buy_pressure_pct:.0f}%"
                )

            if (direction == "SHORT" and
                    result.absorption_detected and
                    result.absorption_direction == "BEAR_ABSORPTION"):
                strength_pct = int(result.absorption_strength * 100)
                return 4, (
                    f"✅ Bear absorption ({strength_pct}% strength) | "
                    f"Sell pressure: {result.sell_pressure_pct:.0f}%"
                )

            # Secondary: CVD divergence only
            if (direction == "LONG" and
                    result.divergence_type == "BULLISH_DIV"):
                pts = 3 if result.divergence_strength == "STRONG" else 2
                return pts, (
                    f"Bullish CVD divergence ({result.divergence_strength}) | "
                    f"Buy: {result.buy_pressure_pct:.0f}%"
                )

            if (direction == "SHORT" and
                    result.divergence_type == "BEARISH_DIV"):
                pts = 3 if result.divergence_strength == "STRONG" else 2
                return pts, (
                    f"Bearish CVD divergence ({result.divergence_strength}) | "
                    f"Sell: {result.sell_pressure_pct:.0f}%"
                )

            # No special orderflow pattern
            pressure_note = f"Buy:{result.buy_pressure_pct:.0f}% Sell:{result.sell_pressure_pct:.0f}%"
            return 0, f"No absorption/divergence | {pressure_note}"

        except Exception as e:
            logger.warning(f"CVD absorption error: {e}")
            return 0, f"Absorption check error: {e}"

    # ──────────────────────────────────────────────────────────────────
    # Existing filters (unchanged)
    # ──────────────────────────────────────────────────────────────────

    def _check_whale_movement(self, data: Dict) -> Tuple[int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20: return 0, "Insufficient data"
        volumes = [float(c[5]) for c in ohlcv]
        avg_vol = sum(volumes[-20:-1]) / 19
        ratio = volumes[-1] / avg_vol if avg_vol > 0 else 0
        if ratio >= 3.0: return 5, f"🐋 Whale volume: {ratio:.1f}x avg"
        if ratio >= 2.0: return 3, f"Large volume: {ratio:.1f}x avg"
        if ratio >= 1.5: return 1, f"Above avg: {ratio:.1f}x"
        return 0, f"Normal volume: {ratio:.1f}x"

    def _check_liquidity_grab(self, data: Dict, direction: Optional[str]) -> Tuple[int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 10: return 0, "Insufficient data"
        last = ohlcv[-1]
        h, l, c, o = float(last[2]), float(last[3]), float(last[4]), float(last[1])
        rng = h - l
        if rng == 0: return 0, "Zero range candle"
        lower_wick = (min(o, c) - l) / rng
        upper_wick = (h - max(o, c)) / rng
        if direction == "LONG"  and lower_wick > 0.6: return 5, f"Liq grab down (wick={lower_wick:.0%}) ✅"
        if direction == "SHORT" and upper_wick > 0.6: return 5, f"Liq grab up (wick={upper_wick:.0%}) ✅"
        if lower_wick > 0.4 or upper_wick > 0.4:     return 2, "Minor liq grab"
        return 0, "No liquidity grab"

    def _check_fibonacci(self, data: Dict, direction: Optional[str]) -> Tuple[int, str]:
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 30: return 0, "Insufficient data"
        highs = [float(c[2]) for c in ohlcv]; lows = [float(c[3]) for c in ohlcv]
        current = float(ohlcv[-1][4])
        rh = max(highs[-30:]); rl = min(lows[-30:])
        if rh == rl: return 0, "No range"
        swing = rh - rl
        fibs = {"0.236": rh-swing*0.236, "0.382": rh-swing*0.382,
                "0.5": rh-swing*0.5, "0.618": rh-swing*0.618, "0.786": rh-swing*0.786}
        tol = swing * 0.01
        for label, level in fibs.items():
            if abs(current - level) <= tol:
                bonus = 3 if label in ["0.382","0.5","0.618"] else 1
                return bonus, f"Fib {label} ({level:.4f}) ✅"
        return 0, "No Fib confluence"

    def _check_correlation_break(self, symbol: str, data: Dict, direction: Optional[str]) -> Tuple[int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if not ohlcv or len(ohlcv) < 20: return 0, "Insufficient data"
        if symbol == "BTC/USDT": return 0, "BTC self-correlation skipped"
        prices = [float(c[4]) for c in ohlcv]
        btc_ohlcv = data.get("btc_ohlcv", {}).get("15m", [])
        btc_prices = [float(c[4]) for c in btc_ohlcv] if btc_ohlcv else None
        result = self.correlation.analyze(symbol=symbol, prices=prices, btc_prices=btc_prices, lookback=20)
        if result.is_decorrelated:
            if direction == "LONG"  and result.direction == "BREAKING_UP":
                return 4, f"Breaking BTC up (r={result.btc_correlation:.2f}) ✅"
            if direction == "SHORT" and result.direction == "BREAKING_DOWN":
                return 4, f"Breaking BTC down (r={result.btc_correlation:.2f}) ✅"
            return 2, f"Decorrelated from BTC (r={result.btc_correlation:.2f})"
        return 0, f"BTC correlated (r={result.btc_correlation:.2f})"

    def _check_orderbook_imbalance(self, data: Dict, direction: Optional[str]) -> Tuple[int, str]:
        ob = data.get("orderbook", {})
        bids = ob.get("bids", []); asks = ob.get("asks", [])
        if not bids or not asks or len(bids) < 5 or len(asks) < 5:
            return 0, "No orderbook data"
        try:
            bid_vol = sum(float(b[1]) for b in bids[:10])
            ask_vol = sum(float(a[1]) for a in asks[:10])
        except (TypeError, ValueError, IndexError):
            return 0, "Invalid orderbook"
        if bid_vol == 0 or ask_vol == 0: return 0, "Zero orderbook volume"
        imb = bid_vol / ask_vol
        if direction == "LONG":
            if imb >= 2.0: return 4, f"Strong buy pressure bid/ask={imb:.2f} ✅"
            if imb >= 1.5: return 2, f"Moderate buy pressure {imb:.2f}"
            if imb < 0.7:  return 0, f"Sell dominates {imb:.2f} ⚠️"
        elif direction == "SHORT":
            if imb <= 0.5: return 4, f"Strong sell pressure bid/ask={imb:.2f} ✅"
            if imb <= 0.7: return 2, f"Moderate sell pressure {imb:.2f}"
            if imb > 1.5:  return 0, f"Buy dominates {imb:.2f} ⚠️"
        return 1, f"Balanced orderbook bid/ask={imb:.2f}"
