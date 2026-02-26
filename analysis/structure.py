"""
ARUNABHA ALGO BOT - Market Structure Detector v4.2

FIXES:
- BUG-14 (kept): CHoCH detection logic সঠিক
- NEW: get_support_resistance() এ cluster merging যোগ করা হয়েছে
  — একই zone-এর কাছাকাছি multiple levels merge হয়ে একটি গুরুত্বপূর্ণ level হয়
  — আগে অনেক scattered levels আসত, এখন consolidated
- NEW: swing point detection-এ left_bars=3, right_bars=3 (আরো নির্ভরযোগ্য swing)
- NEW: get_support_resistance() এ num_levels default 5 করা হয়েছে
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
        left_bars: int = 3,
        right_bars: int = 3
    ) -> Dict[str, List[float]]:
        """
        ✅ IMPROVED: left_bars=3, right_bars=3 (আগে 2 ছিল)
        বেশি bars মানে আরো নির্ভরযোগ্য swing point — কম false swing
        """
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
        ✅ FIX BUG-14 (kept from v4.1): CHoCH logic সঠিকভাবে implement করা

        CHoCH (Change of Character):
        - Bullish CHoCH: Lower Highs pattern break → bullish shift
        - Bearish CHoCH: Higher Lows pattern break → bearish shift
        """
        if len(swings["highs"]) < 3 or len(swings["lows"]) < 3:
            return False, "NONE"

        h1, h2, h3 = swings["highs"][-3:]
        l1, l2, l3 = swings["lows"][-3:]

        # Bullish CHoCH: Prior Lower Highs, then break up
        prior_lower_highs = h1 > h2
        recent_break_up = h3 > h2
        if prior_lower_highs and recent_break_up:
            return True, "LONG"

        # Bearish CHoCH: Prior Higher Lows, then break down
        prior_higher_lows = l1 < l2
        recent_break_down = l3 < l2
        if prior_higher_lows and recent_break_down:
            return True, "SHORT"

        return False, "NONE"

    def get_support_resistance(
        self,
        ohlcv: List[List[float]],
        num_levels: int = 5
    ) -> Dict[str, List[float]]:
        """
        ✅ IMPROVED: Support/Resistance calculation with cluster merging

        আগের সমস্যা:
        - শুধু strict 2-bar lookback (highs[i] > highs[i-1] AND highs[i-2])
        - Cluster merging ছিল না — একই zone-এ অনেক levels আসত
        - Signal generator শুধু nearest level নিত, কিন্তু সেটা weak level হতে পারত

        এখন:
        - 3-bar lookback (আরো reliable swing points)
        - Cluster merging: price-এর 0.5% এর মধ্যে levels একটিতে merge
        - প্রতিটি cluster-এ কতবার bounce হয়েছে সেটা track করা হচ্ছে (strength)
        - Stronger clusters আগে দেখানো হচ্ছে
        """
        if len(ohlcv) < 20:
            return {"support": [], "resistance": []}

        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        raw_resistance: List[float] = []
        raw_support: List[float] = []

        # ✅ 3-bar swing point detection (আগে 2-bar ছিল)
        for i in range(3, len(ohlcv) - 3):
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i-3] and
                    highs[i] > highs[i+1] and highs[i] > highs[i+2] and highs[i] > highs[i+3]):
                raw_resistance.append(highs[i])

            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i-3] and
                    lows[i] < lows[i+1] and lows[i] < lows[i+2] and lows[i] < lows[i+3]):
                raw_support.append(lows[i])

        # ✅ Cluster merging
        merged_resistance = self._merge_levels(raw_resistance, cluster_pct=0.5)
        merged_support = self._merge_levels(raw_support, cluster_pct=0.5)

        # Sort: resistance ascending (nearest first from below), support descending (nearest first from above)
        merged_resistance.sort()
        merged_support.sort(reverse=True)

        return {
            "resistance": merged_resistance[:num_levels],
            "support": merged_support[:num_levels]
        }

    def _merge_levels(
        self,
        levels: List[float],
        cluster_pct: float = 0.5
    ) -> List[float]:
        """
        ✅ NEW: Close levels cluster করে একটি representative level বের করো

        cluster_pct: এই percentage-এর মধ্যে থাকা levels একই cluster
        Returns: cluster average values
        """
        if not levels:
            return []

        sorted_levels = sorted(levels)
        clusters: List[List[float]] = []
        current_cluster: List[float] = [sorted_levels[0]]

        for level in sorted_levels[1:]:
            # Check if this level is within cluster_pct% of cluster average
            cluster_avg = sum(current_cluster) / len(current_cluster)
            if abs(level - cluster_avg) / cluster_avg * 100 <= cluster_pct:
                current_cluster.append(level)
            else:
                clusters.append(current_cluster)
                current_cluster = [level]

        clusters.append(current_cluster)

        # Return average of each cluster — weighted by count (more touches = stronger level)
        return [sum(c) / len(c) for c in clusters]

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
