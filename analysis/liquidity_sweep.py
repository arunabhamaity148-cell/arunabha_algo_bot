"""
ARUNABHA ALGO BOT - Liquidity Sweep Detector v1.0
==================================================
আগের liquidity.py ছিল shallow — শুধু wick দেখত।
এটা proper ICT/SMC-style sweep detection।

4টা pattern detect করে:

1. EQH SWEEP (Equal Highs Sweep)
   ─────────────────────────────
   একাধিক candle একই high বানায় → retail stops জমে → whale sweep করে → reverse
   Setup: EQH ≥ 2 candles, tolerance ±0.15%
   Signal: Sweep হলে SHORT → Entry: break candle close
   
2. EQL SWEEP (Equal Lows Sweep)  
   ──────────────────────────────
   একাধিক candle একই low → retail stops → sweep → reverse
   Signal: EQL swept → LONG

3. PDH/PDL SWEEP (Previous Day High/Low Sweep)
   ─────────────────────────────────────────────
   Previous day-এর high বা low sweep করে ফিরে আসা।
   Institutional favorite setup।

4. SWEEP + RETEST CONFIRMATION
   ────────────────────────────
   Sweep হওয়াই যথেষ্ট নয় — sweep-এর পরে retest confirm হলে signal valid।
   Retest: price ফিরে sweep level-এ আসে কিন্তু break করে না।
   এই confirmation ছাড়া false signal অনেক বেশি।
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

EQH_EQL_TOLERANCE_PCT = 0.15    # ±0.15% = equal high/low
MIN_EQ_CANDLES = 2               # minimum candles to form EQH/EQL
PDH_PDL_LOOKBACK = 96            # 15m × 96 = 24h for previous day
RETEST_TOLERANCE_PCT = 0.20      # retest within 0.20% of sweep level


@dataclass
class SweepResult:
    sweep_detected: bool
    sweep_type: str        # "EQH" / "EQL" / "PDH" / "PDL" / "NONE"
    sweep_direction: str   # "LONG" (sweep lows → go long) / "SHORT" / "NONE"
    sweep_level: float     # price level that was swept
    sweep_idx: int         # candle index where sweep happened
    retest_confirmed: bool # did price retest the swept level?
    retest_idx: int        # candle index of retest (-1 if none)
    equal_levels: List[float]       # EQH or EQL levels found
    strength: str          # "STRONG" / "MODERATE" / "WEAK"
    reason: str


class LiquiditySweepDetector:
    """
    ICT/SMC Liquidity Sweep Detection.
    
    Use in Tier3 as bonus (+5 pts for confirmed sweep+retest).
    Can also be used in signal_generator to refine entry.
    """

    def analyze(
        self,
        ohlcv: List[List[float]],
        direction: Optional[str] = None,
        lookback: int = 30
    ) -> SweepResult:
        """
        Analyze for liquidity sweeps.
        
        Args:
            ohlcv: OHLCV candles
            direction: "LONG" or "SHORT" — filter for matching sweeps
            lookback: candles to look back for EQH/EQL
        """
        if len(ohlcv) < 10:
            return self._no_sweep("Insufficient data")

        # Check EQH sweep
        eqh_result = self._detect_eqh_sweep(ohlcv, lookback)
        if eqh_result.sweep_detected:
            if direction is None or eqh_result.sweep_direction == direction:
                return eqh_result

        # Check EQL sweep
        eql_result = self._detect_eql_sweep(ohlcv, lookback)
        if eql_result.sweep_detected:
            if direction is None or eql_result.sweep_direction == direction:
                return eql_result

        # Check PDH/PDL sweep
        pdh_result = self._detect_pdh_pdl_sweep(ohlcv)
        if pdh_result.sweep_detected:
            if direction is None or pdh_result.sweep_direction == direction:
                return pdh_result

        return self._no_sweep("No sweep detected")

    # ── EQH: Equal Highs Sweep ────────────────────────────────────────

    def _detect_eqh_sweep(
        self, ohlcv: List[List[float]], lookback: int
    ) -> SweepResult:
        """
        Equal Highs:
        1. Find 2+ candles with highs within ±0.15% of each other
        2. Check if last 5 candles swept above those highs
        3. Verify price closed BACK BELOW the sweep level
        4. Check for retest from below
        """
        n = min(lookback, len(ohlcv))
        recent = ohlcv[-n:]
        highs = [float(c[2]) for c in recent]

        # Find equal highs
        eq_levels = self._find_equal_levels(highs, mode="high")
        if not eq_levels:
            return self._no_sweep("No EQH found")

        # Get highest EQH level (that's where most stops are)
        eqh_level = max(eq_levels)

        # Check sweep: recent candle wicked above EQH but closed below
        sweep_idx = -1
        for i in range(-5, 0):
            idx = len(recent) + i
            if idx < 0:
                continue
            c_high  = float(recent[idx][2])
            c_close = float(recent[idx][4])

            if c_high > eqh_level * (1 + RETEST_TOLERANCE_PCT / 100):
                if c_close < eqh_level * (1 + EQH_EQL_TOLERANCE_PCT / 100):
                    sweep_idx = idx
                    break

        if sweep_idx == -1:
            return self._no_sweep("EQH found but not swept recently")

        # Check retest: after sweep, did price come back to EQH from below?
        retest_confirmed, retest_idx = self._check_retest(
            recent, sweep_idx, eqh_level, mode="resistance"
        )

        strength = self._sweep_strength(eq_levels, eqh_level, retest_confirmed)

        return SweepResult(
            sweep_detected=True,
            sweep_type="EQH",
            sweep_direction="SHORT",   # EQH sweep → go short
            sweep_level=round(eqh_level, 8),
            sweep_idx=len(ohlcv) - n + sweep_idx,
            retest_confirmed=retest_confirmed,
            retest_idx=len(ohlcv) - n + retest_idx if retest_confirmed else -1,
            equal_levels=eq_levels,
            strength=strength,
            reason=(
                f"EQH sweep at {eqh_level:.4f} "
                f"({len(eq_levels)} equal highs) "
                f"{'+ retest ✅' if retest_confirmed else '(no retest yet)'}"
            )
        )

    # ── EQL: Equal Lows Sweep ─────────────────────────────────────────

    def _detect_eql_sweep(
        self, ohlcv: List[List[float]], lookback: int
    ) -> SweepResult:
        """
        Equal Lows:
        1. Find 2+ candles with lows within ±0.15%
        2. Check if recent candle wicked below those lows
        3. Verify price closed BACK ABOVE the sweep level
        4. Retest from above
        """
        n = min(lookback, len(ohlcv))
        recent = ohlcv[-n:]
        lows = [float(c[3]) for c in recent]

        eq_levels = self._find_equal_levels(lows, mode="low")
        if not eq_levels:
            return self._no_sweep("No EQL found")

        eql_level = min(eq_levels)   # lowest EQL level

        # Sweep: wick below EQL, close above
        sweep_idx = -1
        for i in range(-5, 0):
            idx = len(recent) + i
            if idx < 0:
                continue
            c_low   = float(recent[idx][3])
            c_close = float(recent[idx][4])

            if c_low < eql_level * (1 - RETEST_TOLERANCE_PCT / 100):
                if c_close > eql_level * (1 - EQH_EQL_TOLERANCE_PCT / 100):
                    sweep_idx = idx
                    break

        if sweep_idx == -1:
            return self._no_sweep("EQL found but not swept recently")

        retest_confirmed, retest_idx = self._check_retest(
            recent, sweep_idx, eql_level, mode="support"
        )

        strength = self._sweep_strength(eq_levels, eql_level, retest_confirmed)

        return SweepResult(
            sweep_detected=True,
            sweep_type="EQL",
            sweep_direction="LONG",    # EQL sweep → go long
            sweep_level=round(eql_level, 8),
            sweep_idx=len(ohlcv) - n + sweep_idx,
            retest_confirmed=retest_confirmed,
            retest_idx=len(ohlcv) - n + retest_idx if retest_confirmed else -1,
            equal_levels=eq_levels,
            strength=strength,
            reason=(
                f"EQL sweep at {eql_level:.4f} "
                f"({len(eq_levels)} equal lows) "
                f"{'+ retest ✅' if retest_confirmed else '(no retest yet)'}"
            )
        )

    # ── PDH/PDL Sweep ─────────────────────────────────────────────────

    def _detect_pdh_pdl_sweep(self, ohlcv: List[List[float]]) -> SweepResult:
        """
        Previous Day High/Low Sweep.
        
        PDH/PDL: Institutional players love sweeping these levels
        because maximum retail stops sit just above PDH and below PDL.
        
        Method:
        1. Find PDH = highest high of candles 96–192 ago (yesterday)
        2. Find PDL = lowest low of yesterday
        3. Check if today's candle swept PDH/PDL and closed back
        """
        if len(ohlcv) < PDH_PDL_LOOKBACK + 5:
            return self._no_sweep("Insufficient data for PDH/PDL")

        # "Yesterday" = previous 24h = index [-192:-96] for 15m candles
        yesterday_start = len(ohlcv) - PDH_PDL_LOOKBACK * 2
        yesterday_end   = len(ohlcv) - PDH_PDL_LOOKBACK

        if yesterday_start < 0:
            yesterday_start = 0

        yesterday = ohlcv[yesterday_start:yesterday_end]
        if not yesterday:
            return self._no_sweep("No yesterday data")

        pdh = max(float(c[2]) for c in yesterday)
        pdl = min(float(c[3]) for c in yesterday)

        # Today's candles = last PDH_PDL_LOOKBACK
        today = ohlcv[-PDH_PDL_LOOKBACK:]

        # PDH sweep check
        for i, candle in enumerate(today[-5:]):
            c_high  = float(candle[2])
            c_close = float(candle[4])
            if (c_high > pdh * 1.001 and
                    c_close < pdh * (1 + EQH_EQL_TOLERANCE_PCT / 100)):
                retest_ok, retest_i = self._check_retest(
                    today, len(today) - 5 + i, pdh, mode="resistance"
                )
                return SweepResult(
                    sweep_detected=True,
                    sweep_type="PDH",
                    sweep_direction="SHORT",
                    sweep_level=round(pdh, 8),
                    sweep_idx=len(ohlcv) - PDH_PDL_LOOKBACK + len(today) - 5 + i,
                    retest_confirmed=retest_ok,
                    retest_idx=-1,
                    equal_levels=[pdh],
                    strength="STRONG" if retest_ok else "MODERATE",
                    reason=f"PDH {pdh:.4f} swept {'+ retest ✅' if retest_ok else ''}"
                )

        # PDL sweep check
        for i, candle in enumerate(today[-5:]):
            c_low   = float(candle[3])
            c_close = float(candle[4])
            if (c_low < pdl * 0.999 and
                    c_close > pdl * (1 - EQH_EQL_TOLERANCE_PCT / 100)):
                retest_ok, retest_i = self._check_retest(
                    today, len(today) - 5 + i, pdl, mode="support"
                )
                return SweepResult(
                    sweep_detected=True,
                    sweep_type="PDL",
                    sweep_direction="LONG",
                    sweep_level=round(pdl, 8),
                    sweep_idx=len(ohlcv) - PDH_PDL_LOOKBACK + len(today) - 5 + i,
                    retest_confirmed=retest_ok,
                    retest_idx=-1,
                    equal_levels=[pdl],
                    strength="STRONG" if retest_ok else "MODERATE",
                    reason=f"PDL {pdl:.4f} swept {'+ retest ✅' if retest_ok else ''}"
                )

        return self._no_sweep("No PDH/PDL sweep")

    # ── Helpers ───────────────────────────────────────────────────────

    def _find_equal_levels(
        self, values: List[float], mode: str
    ) -> List[float]:
        """
        Find clusters of values within ±tolerance%.
        Returns list of representative levels (cluster average).
        """
        if not values:
            return []

        tolerance = EQH_EQL_TOLERANCE_PCT / 100
        clusters: List[List[float]] = []

        for v in values:
            placed = False
            for cluster in clusters:
                avg = sum(cluster) / len(cluster)
                if abs(v - avg) / avg <= tolerance:
                    cluster.append(v)
                    placed = True
                    break
            if not placed:
                clusters.append([v])

        # Only return clusters with MIN_EQ_CANDLES or more
        result = []
        for cluster in clusters:
            if len(cluster) >= MIN_EQ_CANDLES:
                result.append(round(sum(cluster) / len(cluster), 8))

        return result

    def _check_retest(
        self,
        ohlcv: List[List[float]],
        sweep_idx: int,
        level: float,
        mode: str,   # "support" or "resistance"
        retest_window: int = 10
    ) -> Tuple[bool, int]:
        """
        After sweep, check if price retested the level.
        
        Support retest: price came back DOWN to level but closed above
        Resistance retest: price came back UP to level but closed below
        """
        start = sweep_idx + 1
        end   = min(start + retest_window, len(ohlcv))

        tol = RETEST_TOLERANCE_PCT / 100

        for i in range(start, end):
            if i >= len(ohlcv):
                break
            c_low   = float(ohlcv[i][3])
            c_high  = float(ohlcv[i][2])
            c_close = float(ohlcv[i][4])

            if mode == "support":
                # Price touched level ± tol and closed above
                if (c_low <= level * (1 + tol) and
                        c_close > level * (1 - tol)):
                    return True, i

            elif mode == "resistance":
                # Price touched level ± tol and closed below
                if (c_high >= level * (1 - tol) and
                        c_close < level * (1 + tol)):
                    return True, i

        return False, -1

    def _sweep_strength(
        self, eq_levels: List[float], level: float, retest: bool
    ) -> str:
        n = len(eq_levels)
        if n >= 3 and retest:
            return "STRONG"
        elif n >= 2 and retest:
            return "MODERATE"
        elif retest:
            return "MODERATE"
        else:
            return "WEAK"

    def _no_sweep(self, reason: str) -> SweepResult:
        return SweepResult(
            sweep_detected=False,
            sweep_type="NONE",
            sweep_direction="NONE",
            sweep_level=0.0,
            sweep_idx=-1,
            retest_confirmed=False,
            retest_idx=-1,
            equal_levels=[],
            strength="NONE",
            reason=reason,
        )
