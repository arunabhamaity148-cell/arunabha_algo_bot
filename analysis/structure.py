"""
ARUNABHA ALGO BOT - Market Structure Detector
Detects BOS, CHoCH, and other structure patterns
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StructureResult:
    """Market structure detection result"""
    direction: str  # "LONG" or "SHORT"
    strength: str  # "STRONG", "MODERATE", "WEAK"
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
        min_swing_size: float = 0.5  # Minimum % for swing point
    ) -> StructureResult:
        """
        Detect current market structure
        """
        if len(ohlcv) < 20:
            return StructureResult(
                direction="LONG",
                strength="WEAK",
                bos_detected=False,
                choch_detected=False,
                swing_high=ohlcv[-1][2] if ohlcv else 0,
                swing_low=ohlcv[-1][3] if ohlcv else 0,
                reason="Insufficient data"
            )
        
        # Find swing points
        swings = self._find_swing_points(ohlcv)
        
        if not swings["highs"] or not swings["lows"]:
            return StructureResult(
                direction="LONG",
                strength="WEAK",
                bos_detected=False,
                choch_detected=False,
                swing_high=ohlcv[-1][2],
                swing_low=ohlcv[-1][3],
                reason="No swing points found"
            )
        
        # Detect BOS (Break of Structure)
        bos_detected, bos_direction = self._detect_bos(ohlcv, swings)
        
        # Detect CHoCH (Change of Character)
        choch_detected, choch_direction = self._detect_choch(swings)
        
        # Determine current structure
        if choch_detected:
            direction = choch_direction
            strength = "STRONG"
            reason = f"CHoCH to {choch_direction}"
        elif bos_detected:
            direction = bos_direction
            strength = "MODERATE"
            reason = f"BOS to {bos_direction}"
        else:
            # Determine based on recent price action
            recent_closes = [c[4] for c in ohlcv[-5:]]
            if recent_closes[-1] > recent_closes[0]:
                direction = "LONG"
                strength = "WEAK"
                reason = "Gradual uptrend"
            else:
                direction = "SHORT"
                strength = "WEAK"
                reason = "Gradual downtrend"
        
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
        """
        Find swing highs and lows
        """
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        
        swing_highs = []
        swing_lows = []
        
        for i in range(left_bars, len(ohlcv) - right_bars):
            # Check swing high
            is_high = True
            for j in range(1, left_bars + 1):
                if highs[i] <= highs[i - j]:
                    is_high = False
                    break
            for j in range(1, right_bars + 1):
                if highs[i] <= highs[i + j]:
                    is_high = False
                    break
            
            if is_high:
                swing_highs.append(highs[i])
            
            # Check swing low
            is_low = True
            for j in range(1, left_bars + 1):
                if lows[i] >= lows[i - j]:
                    is_low = False
                    break
            for j in range(1, right_bars + 1):
                if lows[i] >= lows[i + j]:
                    is_low = False
                    break
            
            if is_low:
                swing_lows.append(lows[i])
        
        return {
            "highs": swing_highs,
            "lows": swing_lows
        }
    
    def _detect_bos(
        self,
        ohlcv: List[List[float]],
        swings: Dict[str, List[float]]
    ) -> Tuple[bool, str]:
        """
        Detect Break of Structure
        """
        if len(swings["highs"]) < 2 or len(swings["lows"]) < 2:
            return False, "NONE"
        
        current_price = ohlcv[-1][4]
        prev_close = ohlcv[-2][4]
        
        last_high = swings["highs"][-1]
        last_low = swings["lows"][-1]
        
        # Bullish BOS: price breaks above last swing high
        bullish_bos = (
            current_price > last_high and
            prev_close <= last_high
        )
        
        # Bearish BOS: price breaks below last swing low
        bearish_bos = (
            current_price < last_low and
            prev_close >= last_low
        )
        
        if bullish_bos:
            return True, "LONG"
        elif bearish_bos:
            return True, "SHORT"
        
        return False, "NONE"
    
    def _detect_choch(
        self,
        swings: Dict[str, List[float]]
    ) -> Tuple[bool, str]:
        """
        Detect Change of Character
        """
        if len(swings["highs"]) < 3 or len(swings["lows"]) < 3:
            return False, "NONE"
        
        # Get last few swings
        h1, h2, h3 = swings["highs"][-3:]
        l1, l2, l3 = swings["lows"][-3:]
        
        # Bullish CHoCH: Lower Highs -> Higher High
        lower_highs = h1 > h2 > h3
        if lower_highs and h3 < h2 and h2 < h1:
            # Check for break of structure
            return True, "LONG"
        
        # Bearish CHoCH: Higher Lows -> Lower Low
        higher_lows = l1 < l2 < l3
        if higher_lows and l3 > l2 > l1:
            return True, "SHORT"
        
        return False, "NONE"
    
    def get_support_resistance(
        self,
        ohlcv: List[List[float]],
        num_levels: int = 3
    ) -> Dict[str, List[float]]:
        """
        Find support and resistance levels
        """
        if len(ohlcv) < 20:
            return {"support": [], "resistance": []}
        
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        
        # Find local maxima and minima
        resistance_levels = []
        support_levels = []
        
        for i in range(2, len(ohlcv) - 2):
            # Resistance (local high)
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                resistance_levels.append(highs[i])
            
            # Support (local low)
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                support_levels.append(lows[i])
        
        # Sort and take strongest
        resistance_levels.sort(reverse=True)
        support_levels.sort()
        
        return {
            "resistance": resistance_levels[:num_levels],
            "support": support_levels[:num_levels]
        }
    
    def is_near_level(
        self,
        price: float,
        level: float,
        threshold_pct: float = 0.5
    ) -> bool:
        """
        Check if price is near a level
        """
        if level == 0:
            return False
        
        distance_pct = abs(price - level) / level * 100
        return distance_pct <= threshold_pct
    
    def get_nearest_level(
        self,
        price: float,
        levels: Dict[str, List[float]]
    ) -> Tuple[Optional[str], Optional[float], float]:
        """
        Get nearest support/resistance level
        """
        nearest_type = None
        nearest_level = None
        min_distance = float('inf')
        
        # Check resistance above
        for r in levels.get("resistance", []):
            if r > price:
                distance = r - price
                if distance < min_distance:
                    min_distance = distance
                    nearest_level = r
                    nearest_type = "resistance"
        
        # Check support below
        for s in levels.get("support", []):
            if s < price:
                distance = price - s
                if distance < min_distance:
                    min_distance = distance
                    nearest_level = s
                    nearest_type = "support"
        
        if nearest_level:
            distance_pct = (min_distance / price) * 100
            return nearest_type, nearest_level, distance_pct
        
        return None, None, 0
