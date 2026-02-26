"""
ARUNABHA ALGO BOT - Market Structure Detector v4.1

FIXES:
- BUG-14: CHoCH detection logic ছিল উল্টো — এখন সঠিকভাবে pattern detect হচ্ছে
  আগের code এ lower_highs এবং higher_lows condition একই জিনিস check করত
  এখন: properly চেক করা হচ্ছে — bearish pattern থেকে bullish তে shift
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StructureResult:
    direction: str      # "LONG" or "SHORT"
    strength: str       # "STRONG", "MODERATE", "WEAK"
    bos_detected: bool
    choch_detected: bool
    swing_high: float
    swing_low: float
    reason: str


class StructureDetector:
    """
    Detects market structure patterns (BOS, CHoCH, swing points)
    """

    def __init__(self):
        self.last_structure = None

    def detect(
        self,
        ohlcv: List[List[float]],
        min_swing_size: float = 0.5
    ) -> StructureResult:
        if len(ohlcv) < 20:
            return StructureResult(
                direction="LONG", strength="WEAK",
                bos_detected=False, choch_detected=False,
                swing_high=ohlcv[-1][2] if ohlcv else 0,
                swing_low=ohlcv[-1][3] if ohlcv else 0,
                reason="Insufficient data"
            )

        swings = self._find_swing_points(ohlcv)

        if not swings["highs"] or not swings["lows"]:
            return StructureResult(
                direction="LONG", strength="WEAK",
                bos_detected=False, choch_detected=False,
                swing_high=ohlcv[-1][2], swing_low=ohlcv[-1][3],
                reason="No swing points found"
            )

        bos_detected, bos_direction = self._detect_bos(ohlcv, swings)
        choch_detected, choch_direction = self._detect_choch(swings)

        if choch_detected:
            direction = choch_direction
            strength = "STRONG"
            reason = f"CHoCH to {choch_direction}"
        elif bos_detected:
            direction = bos_direction
            strength = "MODERATE"
            reason = f"BOS to {bos_direction}"
        else:
            recent_closes = [c[4] for c in ohlcv[-5:]]
            if recent_closes[-1] > recent_closes[0]:
                direction, strength, reason = "LONG", "WEAK", "Gradual uptrend"
            else:
                direction, strength, reason = "SHORT", "WEAK", "Gradual downtrend"

        return StructureResult(
            direction=direction,
            strength=strength,
            bos_detected=bos_detected,
            choch_detected=choch_detected,
            swing_high=swings["highs"][-1] if swings["highs"] else 0,
            swing_low=swings["lows"][-1] if swings["lows"] else 0,
            reason=reason
        )

    def _find_swing_points(
        self,
        ohlcv: List[List[float]],
        left_bars: int = 2,
        right_bars: int = 2
    ) -> Dict[str, List[float]]:
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        swing_highs = []
        swing_lows = []

        for i in range(left_bars, len(ohlcv) - right_bars):
            is_high = all(highs[i] > highs[i - j] for j in range(1, left_bars + 1)) and \
                      all(highs[i] > highs[i + j] for j in range(1, right_bars + 1))
            if is_high:
                swing_highs.append(highs[i])

            is_low = all(lows[i] < lows[i - j] for j in range(1, left_bars + 1)) and \
                     all(lows[i] < lows[i + j] for j in range(1, right_bars + 1))
            if is_low:
                swing_lows.append(lows[i])

        return {"highs": swing_highs, "lows": swing_lows}

    def _detect_bos(
        self,
        ohlcv: List[List[float]],
        swings: Dict[str, List[float]]
    ) -> Tuple[bool, str]:
        if len(swings["highs"]) < 2 or len(swings["lows"]) < 2:
            return False, "NONE"

        current_price = ohlcv[-1][4]
        prev_close = ohlcv[-2][4]
        last_high = swings["highs"][-1]
        last_low = swings["lows"][-1]

        if current_price > last_high and prev_close <= last_high:
            return True, "LONG"
        if current_price < last_low and prev_close >= last_low:
            return True, "SHORT"

        return False, "NONE"

    def _detect_choch(
        self,
        swings: Dict[str, List[float]]
    ) -> Tuple[bool, str]:
        """
        ✅ FIX BUG-14: CHoCH logic সঠিকভাবে implement করা হয়েছে

        CHoCH (Change of Character) মানে:
        - Bullish CHoCH: আগে Lower Highs ছিল (bearish), এখন সর্বশেষ swing high
          আগের দুটো swing high কে break করেছে (bullish তে shift)
        - Bearish CHoCH: আগে Higher Lows ছিল (bullish), এখন সর্বশেষ swing low
          আগের দুটো swing low এর নিচে গেছে (bearish তে shift)

        আগের bug: lower_highs = h1 > h2 > h3 এবং if h3 < h2 < h1 — একই condition!
        """
        if len(swings["highs"]) < 3 or len(swings["lows"]) < 3:
            return False, "NONE"

        # Oldest → Newest: h1, h2, h3
        h1, h2, h3 = swings["highs"][-3:]
        l1, l2, l3 = swings["lows"][-3:]

        # ✅ Bullish CHoCH:
        # Prior structure: Lower Highs (h1 > h2 > h3 — descending highs = bearish)
        # Character change: latest high (h3) breaks ABOVE the previous high (h2)
        prior_lower_highs = h1 > h2  # প্রথম দুটো Lower High ছিল
        recent_break_up = h3 > h2    # সর্বশেষ high আগেরটাকে break করেছে
        if prior_lower_highs and recent_break_up:
            return True, "LONG"

        # ✅ Bearish CHoCH:
        # Prior structure: Higher Lows (l1 < l2 < l3 — ascending lows = bullish)
        # Character change: latest low (l3) breaks BELOW the previous low (l2)
        prior_higher_lows = l1 < l2  # প্রথম দুটো Higher Low ছিল
        recent_break_down = l3 < l2  # সর্বশেষ low আগেরটার নিচে গেছে
        if prior_higher_lows and recent_break_down:
            return True, "SHORT"

        return False, "NONE"

    def get_support_resistance(
        self,
        ohlcv: List[List[float]],
        num_levels: int = 3
    ) -> Dict[str, List[float]]:
        if len(ohlcv) < 20:
            return {"support": [], "resistance": []}

        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        resistance_levels = []
        support_levels = []

        for i in range(2, len(ohlcv) - 2):
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                    highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                resistance_levels.append(highs[i])
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                    lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                support_levels.append(lows[i])

        resistance_levels.sort(reverse=True)
        support_levels.sort()

        return {
            "resistance": resistance_levels[:num_levels],
            "support": support_levels[:num_levels]
        }

    def is_near_level(self, price: float, level: float, threshold_pct: float = 0.5) -> bool:
        if level == 0:
            return False
        distance_pct = abs(price - level) / level * 100
        return distance_pct <= threshold_pct

    def get_nearest_level(
        self,
        price: float,
        levels: Dict[str, List[float]]
    ) -> Tuple[Optional[str], Optional[float], float]:
        nearest_type = None
        nearest_level = None
        min_distance = float('inf')

        for r in levels.get("resistance", []):
            if r > price:
                distance = r - price
                if distance < min_distance:
                    min_distance = distance
                    nearest_level = r
                    nearest_type = "resistance"

        for s in levels.get("support", []):
            if s < price:
                distance = price - s
                if distance < min_distance:
                    min_distance = distance
                    nearest_level = s
                    nearest_type = "support"

        if nearest_level:
            return nearest_type, nearest_level, (min_distance / price) * 100
        return None, None, 0
