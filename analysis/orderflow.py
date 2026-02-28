"""
ARUNABHA ALGO BOT - Orderflow / CVD Analyzer v1.0
==================================================
Real Orderflow analysis — শুধু candle direction দিয়ে নয়,
প্রতিটা candle-এর ভেতরে buying vs selling pressure কতটা ছিল।

3টা component:

1. CVD (Cumulative Volume Delta)
   ─────────────────────────────
   প্রতিটা candle-এ: কতটা volume "buy" আর কতটা "sell"
   
   Calculation (OHLCV-based, no tick data):
     Bullish candle → buy_vol = volume × (close - low) / (high - low)
                       sell_vol = volume × (high - close) / (high - low)
     Bearish candle → বিপরীত
   
   CVD = Σ(buy_vol - sell_vol) rolling N candles
   
   Divergence:
     Price rising + CVD falling → Bearish divergence (sellers absorbing)
     Price falling + CVD rising → Bullish divergence (buyers absorbing)

2. DELTA PER CANDLE
   ─────────────────
   Individual candle delta: buy_vol - sell_vol
   Large positive delta = aggressive buying
   Large negative delta = aggressive selling

3. ABSORPTION DETECTION
   ─────────────────────
   Price moves in one direction কিন্তু volume delta বিপরীত।
   মানে: বড় player opposite side-এ absorb করছে।
   → High probability reversal setup।

Signal use:
  Tier2: CVD divergence filter (replaces weak momentum check)
  Tier3: Absorption bonus (+4 pts)
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderflowResult:
    # CVD
    cvd_series: List[float]          # rolling CVD for last N candles
    cvd_current: float               # latest CVD value
    cvd_direction: str               # "RISING" / "FALLING" / "FLAT"
    cvd_slope: float                 # linear slope of CVD (normalized)

    # Delta
    delta_series: List[float]        # per-candle delta
    delta_current: float             # last candle delta
    cumulative_delta_pct: float      # CVD as % of total volume

    # Divergence
    divergence_type: str             # "BULLISH_DIV" / "BEARISH_DIV" / "NONE"
    divergence_strength: str         # "STRONG" / "MODERATE" / "NONE"

    # Absorption
    absorption_detected: bool
    absorption_direction: str        # "BULL_ABSORPTION" / "BEAR_ABSORPTION" / "NONE"
    absorption_strength: float       # 0.0–1.0

    # Buy/Sell pressure
    buy_pressure_pct: float          # % of volume that was buying
    sell_pressure_pct: float         # % of volume that was selling
    pressure_bias: str               # "BUY" / "SELL" / "NEUTRAL"


class OrderflowAnalyzer:
    """
    OHLCV-based orderflow analysis.
    
    Note: Real tick-level data সবচেয়ে accurate।
    কিন্তু OHLCV থেকেও দারুণ approximation পাওয়া যায়
    (Kaplan-Meier volume distribution method)।
    """

    def __init__(self, cvd_period: int = 20):
        self.cvd_period = cvd_period

    def analyze(
        self,
        ohlcv: List[List[float]],
        period: int = 20
    ) -> OrderflowResult:
        """
        Full orderflow analysis on OHLCV data.
        
        Args:
            ohlcv: OHLCV candles [timestamp, open, high, low, close, volume]
            period: lookback for CVD and divergence
        """
        if len(ohlcv) < 5:
            return self._empty_result()

        n = min(period, len(ohlcv))
        recent = ohlcv[-n:]

        # ── 1. Calculate delta for each candle ─────────────────────────
        deltas = []
        buy_vols = []
        sell_vols = []

        for candle in recent:
            o = float(candle[1])
            h = float(candle[2])
            l = float(candle[3])
            c = float(candle[4])
            vol = float(candle[5])

            rng = h - l
            if rng == 0:
                # Doji → 50/50
                buy_v = sell_v = vol / 2
            else:
                # Volume distribution based on wick anatomy
                # Bullish candle: more volume near close (buying)
                if c >= o:
                    buy_v  = vol * (c - l) / rng
                    sell_v = vol * (h - c) / rng
                else:
                    sell_v = vol * (h - c) / rng
                    buy_v  = vol * (c - l) / rng

            delta = buy_v - sell_v
            deltas.append(delta)
            buy_vols.append(buy_v)
            sell_vols.append(sell_v)

        # ── 2. CVD (cumulative sum of deltas) ─────────────────────────
        cvd_series = []
        running = 0.0
        for d in deltas:
            running += d
            cvd_series.append(running)

        cvd_current = cvd_series[-1] if cvd_series else 0.0

        # CVD direction (compare first half vs second half)
        mid = len(cvd_series) // 2
        cvd_early = sum(cvd_series[:mid]) / max(mid, 1)
        cvd_late  = sum(cvd_series[mid:]) / max(len(cvd_series) - mid, 1)

        if cvd_late > cvd_early * 1.05:
            cvd_direction = "RISING"
        elif cvd_late < cvd_early * 0.95:
            cvd_direction = "FALLING"
        else:
            cvd_direction = "FLAT"

        # CVD slope (simple linear regression slope normalized)
        cvd_slope = self._linear_slope(cvd_series)

        # ── 3. Divergence detection ───────────────────────────────────
        closes = [float(c[4]) for c in recent]
        div_type, div_strength = self._detect_divergence(closes, cvd_series)

        # ── 4. Absorption detection ───────────────────────────────────
        abs_detected, abs_dir, abs_strength = self._detect_absorption(
            recent, deltas
        )

        # ── 5. Buy/Sell pressure ──────────────────────────────────────
        total_buy  = sum(buy_vols)
        total_sell = sum(sell_vols)
        total_vol  = total_buy + total_sell

        buy_pct  = (total_buy  / total_vol * 100) if total_vol > 0 else 50.0
        sell_pct = (total_sell / total_vol * 100) if total_vol > 0 else 50.0

        if buy_pct >= 55:
            pressure_bias = "BUY"
        elif sell_pct >= 55:
            pressure_bias = "SELL"
        else:
            pressure_bias = "NEUTRAL"

        # CVD as % of total volume
        total_abs_vol = sum(abs(d) for d in deltas)
        cvd_pct = (cvd_current / total_abs_vol * 100) if total_abs_vol > 0 else 0.0

        logger.debug(
            f"Orderflow | CVD={cvd_current:.0f}({cvd_direction}) "
            f"Buy={buy_pct:.1f}% Sell={sell_pct:.1f}% "
            f"Div={div_type}({div_strength}) Absorption={abs_dir}"
        )

        return OrderflowResult(
            cvd_series=cvd_series,
            cvd_current=cvd_current,
            cvd_direction=cvd_direction,
            cvd_slope=cvd_slope,
            delta_series=deltas,
            delta_current=deltas[-1] if deltas else 0.0,
            cumulative_delta_pct=round(cvd_pct, 2),
            divergence_type=div_type,
            divergence_strength=div_strength,
            absorption_detected=abs_detected,
            absorption_direction=abs_dir,
            absorption_strength=abs_strength,
            buy_pressure_pct=round(buy_pct, 2),
            sell_pressure_pct=round(sell_pct, 2),
            pressure_bias=pressure_bias,
        )

    def _detect_divergence(
        self,
        closes: List[float],
        cvd: List[float],
        lookback: int = 10
    ) -> Tuple[str, str]:
        """
        CVD divergence with price:
        
        BULLISH DIVERGENCE:
          Price: lower low  →  CVD: higher low
          Meaning: sellers exhausted, buyers absorbing
          → LONG setup
        
        BEARISH DIVERGENCE:
          Price: higher high  →  CVD: lower high
          Meaning: buyers exhausted, sellers absorbing
          → SHORT setup
        """
        if len(closes) < lookback or len(cvd) < lookback:
            return "NONE", "NONE"

        p = closes[-lookback:]
        c = cvd[-lookback:]

        p_first_half  = p[:lookback // 2]
        p_second_half = p[lookback // 2:]
        c_first_half  = c[:lookback // 2]
        c_second_half = c[lookback // 2:]

        p_min_1 = min(p_first_half)
        p_min_2 = min(p_second_half)
        c_min_1 = min(c_first_half)
        c_min_2 = min(c_second_half)

        p_max_1 = max(p_first_half)
        p_max_2 = max(p_second_half)
        c_max_1 = max(c_first_half)
        c_max_2 = max(c_second_half)

        # Bullish: price lower low but CVD higher low
        price_lower_low = p_min_2 < p_min_1 * 0.999
        cvd_higher_low  = c_min_2 > c_min_1 * 1.001  # CVD improved

        # Bearish: price higher high but CVD lower high
        price_higher_high = p_max_2 > p_max_1 * 1.001
        cvd_lower_high    = c_max_2 < c_max_1 * 0.999  # CVD weakened

        if price_lower_low and cvd_higher_low:
            # Strength based on magnitude
            price_drop = (p_min_1 - p_min_2) / max(p_min_1, 0.001) * 100
            cvd_recovery = (c_min_2 - c_min_1) / max(abs(c_min_1), 1) * 100
            strength = "STRONG" if price_drop > 0.5 and cvd_recovery > 0 else "MODERATE"
            return "BULLISH_DIV", strength

        if price_higher_high and cvd_lower_high:
            price_rise  = (p_max_2 - p_max_1) / max(p_max_1, 0.001) * 100
            cvd_decline = (c_max_1 - c_max_2) / max(abs(c_max_1), 1) * 100
            strength = "STRONG" if price_rise > 0.5 and cvd_decline > 0 else "MODERATE"
            return "BEARISH_DIV", strength

        return "NONE", "NONE"

    def _detect_absorption(
        self,
        ohlcv: List[List[float]],
        deltas: List[float],
        lookback: int = 5
    ) -> Tuple[bool, str, float]:
        """
        Absorption: price moves one direction but delta moves other direction.
        
        BULL ABSORPTION (বড় players buy করছে):
          Price falling / flat, but delta turning positive
          → Sellers hitting bids but price not dropping = buyers absorbing
        
        BEAR ABSORPTION (বড় players sell করছে):
          Price rising / flat, but delta turning negative
          → Buyers hitting asks but price not rising = sellers absorbing
        """
        if len(ohlcv) < lookback or len(deltas) < lookback:
            return False, "NONE", 0.0

        recent_candles = ohlcv[-lookback:]
        recent_deltas  = deltas[-lookback:]

        # Price direction
        price_start = float(recent_candles[0][4])
        price_end   = float(recent_candles[-1][4])
        price_change_pct = (price_end - price_start) / price_start * 100

        # Delta direction
        delta_sum = sum(recent_deltas)
        avg_delta = delta_sum / lookback

        # Total volume for normalization
        total_vol = sum(float(c[5]) for c in recent_candles)
        delta_pct = (avg_delta / (total_vol / lookback) * 100) if total_vol > 0 else 0

        # Bullish absorption: price falling but delta positive
        if price_change_pct < -0.2 and delta_pct > 10:
            strength = min(1.0, abs(delta_pct) / 30)
            return True, "BULL_ABSORPTION", round(strength, 2)

        # Bearish absorption: price rising but delta negative
        if price_change_pct > 0.2 and delta_pct < -10:
            strength = min(1.0, abs(delta_pct) / 30)
            return True, "BEAR_ABSORPTION", round(strength, 2)

        return False, "NONE", 0.0

    def get_signal_bias(self, result: OrderflowResult, direction: str) -> Tuple[int, str]:
        """
        Return (score, message) for use in filter scoring.
        
        Max contribution: 10 points
          - CVD aligned:     +3
          - Pressure aligned: +2
          - No divergence:   +0 (divergence: -0 but used for bonus)
          - Divergence match: +3
          - Absorption match: +2
        """
        score = 0
        notes = []

        # CVD direction alignment
        if direction == "LONG" and result.cvd_direction == "RISING":
            score += 3
            notes.append(f"CVD rising ✅")
        elif direction == "SHORT" and result.cvd_direction == "FALLING":
            score += 3
            notes.append(f"CVD falling ✅")
        elif result.cvd_direction == "FLAT":
            score += 1
            notes.append("CVD flat")
        else:
            notes.append(f"CVD against ({result.cvd_direction})")

        # Buy/sell pressure
        if direction == "LONG" and result.pressure_bias == "BUY":
            score += 2
            notes.append(f"Buy pressure {result.buy_pressure_pct:.0f}% ✅")
        elif direction == "SHORT" and result.pressure_bias == "SELL":
            score += 2
            notes.append(f"Sell pressure {result.sell_pressure_pct:.0f}% ✅")

        # Divergence confirmation
        if direction == "LONG" and result.divergence_type == "BULLISH_DIV":
            bonus = 3 if result.divergence_strength == "STRONG" else 2
            score += bonus
            notes.append(f"Bullish CVD divergence ({result.divergence_strength}) ✅")
        elif direction == "SHORT" and result.divergence_type == "BEARISH_DIV":
            bonus = 3 if result.divergence_strength == "STRONG" else 2
            score += bonus
            notes.append(f"Bearish CVD divergence ({result.divergence_strength}) ✅")

        # Absorption
        if direction == "LONG" and result.absorption_direction == "BULL_ABSORPTION":
            score += 2
            notes.append(f"Bull absorption detected ✅")
        elif direction == "SHORT" and result.absorption_direction == "BEAR_ABSORPTION":
            score += 2
            notes.append(f"Bear absorption detected ✅")

        return min(score, 10), " | ".join(notes)

    # ── Helpers ───────────────────────────────────────────────────────

    def _linear_slope(self, series: List[float]) -> float:
        """Normalized linear regression slope"""
        n = len(series)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2
        y_mean = sum(series) / n
        num = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0.0
        # Normalize by mean price range
        rng = max(series) - min(series)
        return slope / rng if rng != 0 else 0.0

    def _empty_result(self) -> OrderflowResult:
        return OrderflowResult(
            cvd_series=[], cvd_current=0.0, cvd_direction="FLAT", cvd_slope=0.0,
            delta_series=[], delta_current=0.0, cumulative_delta_pct=0.0,
            divergence_type="NONE", divergence_strength="NONE",
            absorption_detected=False, absorption_direction="NONE", absorption_strength=0.0,
            buy_pressure_pct=50.0, sell_pressure_pct=50.0, pressure_bias="NEUTRAL",
        )
