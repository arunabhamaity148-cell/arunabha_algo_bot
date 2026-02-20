"""
ARUNABHA ALGO BOT - Liquidity Detector
Identifies liquidity grabs, sweeps, and order blocks
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LiquidityResult:
    """Liquidity detection result"""
    sweep_detected: bool
    sweep_direction: str
    grab_detected: bool
    grab_direction: str
    order_block: Optional[Dict]
    liquidity_levels: List[float]
    reason: str


class LiquidityDetector:
    """
    Detects liquidity patterns in the market
    """
    
    def __init__(self):
        self.last_sweep = None
    
    def detect(
        self,
        ohlcv: List[List[float]],
        lookback: int = 20
    ) -> LiquidityResult:
        """
        Detect liquidity patterns
        """
        if len(ohlcv) < lookback:
            return LiquidityResult(
                sweep_detected=False,
                sweep_direction="NONE",
                grab_detected=False,
                grab_direction="NONE",
                order_block=None,
                liquidity_levels=[],
                reason="Insufficient data"
            )
        
        recent = ohlcv[-lookback:]
        
        # Find liquidity levels
        liquidity_levels = self._find_liquidity_levels(recent)
        
        # Detect liquidity sweep
        sweep_detected, sweep_dir = self._detect_liquidity_sweep(recent, liquidity_levels)
        
        # Detect liquidity grab
        grab_detected, grab_dir = self._detect_liquidity_grab(recent)
        
        # Find order block
        order_block = self._find_order_block(recent)
        
        reason = []
        if sweep_detected:
            reason.append(f"{sweep_dir} sweep")
        if grab_detected:
            reason.append(f"{grab_dir} grab")
        if order_block:
            reason.append("Order block")
        
        return LiquidityResult(
            sweep_detected=sweep_detected,
            sweep_direction=sweep_dir,
            grab_detected=grab_detected,
            grab_direction=grab_dir,
            order_block=order_block,
            liquidity_levels=liquidity_levels,
            reason=", ".join(reason) if reason else "No liquidity patterns"
        )
    
    def _find_liquidity_levels(
        self,
        ohlcv: List[List[float]]
    ) -> List[float]:
        """
        Find potential liquidity levels
        (Previous highs/lows where stops might be)
        """
        levels = []
        
        # Look for swing highs and lows
        for i in range(2, len(ohlcv) - 2):
            # Swing high
            if (ohlcv[i][2] > ohlcv[i-1][2] and
                ohlcv[i][2] > ohlcv[i-2][2] and
                ohlcv[i][2] > ohlcv[i+1][2] and
                ohlcv[i][2] > ohlcv[i+2][2]):
                levels.append(ohlcv[i][2])
            
            # Swing low
            if (ohlcv[i][3] < ohlcv[i-1][3] and
                ohlcv[i][3] < ohlcv[i-2][3] and
                ohlcv[i][3] < ohlcv[i+1][3] and
                ohlcv[i][3] < ohlcv[i+2][3]):
                levels.append(ohlcv[i][3])
        
        # Remove duplicates and sort
        levels = sorted(list(set(levels)))
        
        return levels
    
    def _detect_liquidity_sweep(
        self,
        ohlcv: List[List[float]],
        levels: List[float],
        threshold_pct: float = 0.2
    ) -> Tuple[bool, str]:
        """
        Detect liquidity sweep (price moves beyond level then reverses)
        """
        if len(ohlcv) < 3 or not levels:
            return False, "NONE"
        
        current = ohlcv[-1]
        prev = ohlcv[-2]
        prev_prev = ohlcv[-3]
        
        current_high = current[2]
        current_low = current[3]
        current_close = current[4]
        
        # Check for sweep above resistance
        for level in levels:
            if level > current_close:  # Resistance above
                # Price moved above resistance then closed below
                if (current_high > level and
                    current_close < level and
                    prev_prev[4] < level):  # Was below before
                    return True, "SHORT"  # Sweep longs, go short
        
        # Check for sweep below support
        for level in levels:
            if level < current_close:  # Support below
                # Price moved below support then closed above
                if (current_low < level and
                    current_close > level and
                    prev_prev[4] > level):  # Was above before
                    return True, "LONG"  # Sweep shorts, go long
        
        return False, "NONE"
    
    def _detect_liquidity_grab(
        self,
        ohlcv: List[List[float]],
        lookback: int = 5
    ) -> Tuple[bool, str]:
        """
        Detect liquidity grab (wicks grabbing stops)
        """
        if len(ohlcv) < lookback + 1:
            return False, "NONE"
        
        current = ohlcv[-1]
        previous = ohlcv[-2:-lookback-1:-1]
        
        current_open = current[1]
        current_high = current[2]
        current_low = current[3]
        current_close = current[4]
        
        # Calculate average candle size
        avg_size = sum(c[2] - c[3] for c in previous) / len(previous)
        
        # Check for long wick grab
        upper_wick = current_high - max(current_open, current_close)
        if upper_wick > avg_size * 0.5:  # Significant upper wick
            if current_close < current_open:  # Bearish close
                return True, "SHORT"  # Grabbed longs
        
        # Check for lower wick grab
        lower_wick = min(current_open, current_close) - current_low
        if lower_wick > avg_size * 0.5:  # Significant lower wick
            if current_close > current_open:  # Bullish close
                return True, "LONG"  # Grabbed shorts
        
        return False, "NONE"
    
    def _find_order_block(
        self,
        ohlcv: List[List[float]],
        lookback: int = 10
    ) -> Optional[Dict]:
        """
        Find order block (last candle before strong move)
        """
        if len(ohlcv) < lookback + 2:
            return None
        
        for i in range(len(ohlcv) - 2, len(ohlcv) - lookback - 1, -1):
            current = ohlcv[i]
            next_candle = ohlcv[i + 1]
            
            # Check for strong move
            move_size = abs(next_candle[4] - current[4])
            avg_move = self._calculate_avg_move(ohlcv, i)
            
            if move_size > avg_move * 1.5:  # Strong move
                # This candle could be order block
                return {
                    "price": current[4],
                    "high": current[2],
                    "low": current[3],
                    "type": "BULLISH" if next_candle[4] > current[4] else "BEARISH",
                    "strength": move_size / avg_move if avg_move > 0 else 1
                }
        
        return None
    
    def _calculate_avg_move(
        self,
        ohlcv: List[List[float]],
        exclude_idx: int,
        period: int = 10
    ) -> float:
        """
        Calculate average move size
        """
        start = max(0, exclude_idx - period)
        moves = []
        
        for i in range(start, exclude_idx):
            if i > 0:
                move = abs(ohlcv[i][4] - ohlcv[i-1][4])
                moves.append(move)
        
        return sum(moves) / len(moves) if moves else 0
    
    def is_liquidity_sweep_setup(
        self,
        ohlcv: List[List[float]],
        direction: str
    ) -> bool:
        """
        Check if market is setting up for liquidity sweep
        """
        if len(ohlcv) < 10:
            return False
        
        recent = ohlcv[-10:]
        
        if direction == "LONG":
            # Looking for sweep of lows
            lows = [c[3] for c in recent]
            current_low = lows[-1]
            
            # Price making new lows but showing reversal signs
            if current_low == min(lows):
                # Check for reversal candle
                last = recent[-1]
                if last[4] > last[1]:  # Bullish close
                    return True
        
        else:  # SHORT
            # Looking for sweep of highs
            highs = [c[2] for c in recent]
            current_high = highs[-1]
            
            # Price making new highs but showing reversal signs
            if current_high == max(highs):
                # Check for reversal candle
                last = recent[-1]
                if last[4] < last[1]:  # Bearish close
                    return True
        
        return False
