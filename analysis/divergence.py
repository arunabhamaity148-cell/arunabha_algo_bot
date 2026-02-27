"""
ARUNABHA ALGO BOT - Divergence Detector
RSI/MACD divergence detection — inline helper used by Tier2.
Standalone class kept for analysis/__init__ export compatibility.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DivergenceResult:
    bullish: bool
    bearish: bool
    indicator: str       # "RSI" or "MACD"
    strength: str        # "STRONG" / "WEAK" / "NONE"
    reason: str


class DivergenceDetector:
    """
    Detects RSI and price divergences.
    Tier2 uses this inline; this class is kept for __init__ export.
    """

    def detect_rsi_divergence(
        self,
        closes: List[float],
        rsi_values: List[float],
        lookback: int = 10
    ) -> DivergenceResult:
        """Detect RSI divergence over last N candles"""

        if len(closes) < lookback or len(rsi_values) < lookback:
            return DivergenceResult(
                bullish=False, bearish=False,
                indicator="RSI", strength="NONE",
                reason="Insufficient data"
            )

        recent_closes = closes[-lookback:]
        recent_rsi = rsi_values[-lookback:]

        # Bullish: price makes lower low, RSI makes higher low
        price_lower_low = recent_closes[-1] < min(recent_closes[:-1])
        rsi_higher_low = recent_rsi[-1] > min(recent_rsi[:-1])

        # Bearish: price makes higher high, RSI makes lower high
        price_higher_high = recent_closes[-1] > max(recent_closes[:-1])
        rsi_lower_high = recent_rsi[-1] < max(recent_rsi[:-1])

        if price_lower_low and rsi_higher_low:
            # Measure divergence magnitude
            price_drop = (min(recent_closes[:-1]) - recent_closes[-1]) / min(recent_closes[:-1])
            strength = "STRONG" if price_drop > 0.01 else "WEAK"
            return DivergenceResult(
                bullish=True, bearish=False,
                indicator="RSI", strength=strength,
                reason=f"Bullish RSI divergence ({strength}): price lower low, RSI higher low"
            )

        if price_higher_high and rsi_lower_high:
            price_rise = (recent_closes[-1] - max(recent_closes[:-1])) / max(recent_closes[:-1])
            strength = "STRONG" if price_rise > 0.01 else "WEAK"
            return DivergenceResult(
                bullish=False, bearish=True,
                indicator="RSI", strength=strength,
                reason=f"Bearish RSI divergence ({strength}): price higher high, RSI lower high"
            )

        return DivergenceResult(
            bullish=False, bearish=False,
            indicator="RSI", strength="NONE",
            reason=f"No divergence detected (RSI: {recent_rsi[-1]:.1f})"
        )

    def detect(self, ohlcv: List, rsi_values: Optional[List[float]] = None) -> DivergenceResult:
        """Convenience method — auto-extract closes from OHLCV"""
        closes = [c[4] for c in ohlcv]
        if rsi_values is None:
            # Return neutral if no RSI provided
            return DivergenceResult(
                bullish=False, bearish=False,
                indicator="RSI", strength="NONE",
                reason="No RSI data provided"
            )
        return self.detect_rsi_divergence(closes, rsi_values)
