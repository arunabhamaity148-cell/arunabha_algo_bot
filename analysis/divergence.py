"""
ARUNABHA ALGO BOT - Divergence Detector
Detects bullish/bearish divergences across indicators
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from analysis.technical import TechnicalAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class DivergenceResult:
    """Divergence detection result"""
    rsi_divergence: Tuple[bool, str]  # (detected, direction)
    macd_divergence: Tuple[bool, str]
    volume_divergence: Tuple[bool, str]
    hidden_divergence: Tuple[bool, str]
    strength: str  # "STRONG", "MODERATE", "WEAK"
    reason: str


class DivergenceDetector:
    """
    Detects divergences between price and indicators
    """
    
    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
    
    def detect_all(
        self,
        ohlcv: List[List[float]],
        lookback: int = 20
    ) -> DivergenceResult:
        """
        Detect all types of divergences
        """
        if len(ohlcv) < lookback + 5:
            return DivergenceResult(
                rsi_divergence=(False, "NONE"),
                macd_divergence=(False, "NONE"),
                volume_divergence=(False, "NONE"),
                hidden_divergence=(False, "NONE"),
                strength="WEAK",
                reason="Insufficient data"
            )
        
        closes = [c[4] for c in ohlcv]
        
        # Calculate indicators
        rsi_values = self._calculate_rsi_series(closes)
        macd_values = self._calculate_macd_series(closes)
        volume_values = [c[5] for c in ohlcv]
        
        # Detect divergences
        rsi_div = self._detect_rsi_divergence(closes, rsi_values, lookback)
        macd_div = self._detect_macd_divergence(closes, macd_values, lookback)
        vol_div = self._detect_volume_divergence(closes, volume_values, lookback)
        hidden_div = self._detect_hidden_divergence(closes, rsi_values, lookback)
        
        # Calculate overall strength
        strengths = []
        if rsi_div[0]:
            strengths.append(1)
        if macd_div[0]:
            strengths.append(1)
        if vol_div[0]:
            strengths.append(0.5)
        if hidden_div[0]:
            strengths.append(0.7)
        
        if sum(strengths) >= 2:
            strength = "STRONG"
            reason = "Multiple divergences detected"
        elif sum(strengths) >= 1:
            strength = "MODERATE"
            reason = "Single divergence detected"
        else:
            strength = "WEAK"
            reason = "No divergence detected"
        
        return DivergenceResult(
            rsi_divergence=rsi_div,
            macd_divergence=macd_div,
            volume_divergence=vol_div,
            hidden_divergence=hidden_div,
            strength=strength,
            reason=reason
        )
    
    def _calculate_rsi_series(
        self,
        closes: List[float],
        period: int = 14
    ) -> List[float]:
        """Calculate RSI series"""
        rsi_values = []
        
        for i in range(period, len(closes)):
            rsi = self.analyzer.calculate_rsi(closes[:i+1], period)
            rsi_values.append(rsi)
        
        return rsi_values
    
    def _calculate_macd_series(
        self,
        closes: List[float]
    ) -> List[float]:
        """Calculate MACD histogram series"""
        macd_values = []
        
        for i in range(26, len(closes)):
            macd = self.analyzer.calculate_macd(closes[:i+1])
            macd_values.append(macd["histogram"])
        
        return macd_values
    
    def _detect_rsi_divergence(
        self,
        closes: List[float],
        rsi_values: List[float],
        lookback: int
    ) -> Tuple[bool, str]:
        """
        Detect RSI divergence
        """
        if len(closes) < lookback or len(rsi_values) < lookback:
            return False, "NONE"
        
        recent_closes = closes[-lookback:]
        recent_rsi = rsi_values[-lookback:]
        
        # Find lows and highs
        price_low_idx = recent_closes.index(min(recent_closes))
        price_high_idx = recent_closes.index(max(recent_closes))
        
        rsi_low_idx = recent_rsi.index(min(recent_rsi))
        rsi_high_idx = recent_rsi.index(max(recent_rsi))
        
        # Bullish divergence: price makes lower low, RSI makes higher low
        if (price_low_idx == len(recent_closes) - 1 and
            rsi_low_idx < len(recent_rsi) - 1 and
            recent_closes[price_low_idx] < recent_closes[0] and
            recent_rsi[rsi_low_idx] > recent_rsi[0]):
            return True, "BULLISH"
        
        # Bearish divergence: price makes higher high, RSI makes lower high
        if (price_high_idx == len(recent_closes) - 1 and
            rsi_high_idx < len(recent_rsi) - 1 and
            recent_closes[price_high_idx] > recent_closes[0] and
            recent_rsi[rsi_high_idx] < recent_rsi[0]):
            return True, "BEARISH"
        
        return False, "NONE"
    
    def _detect_macd_divergence(
        self,
        closes: List[float],
        macd_values: List[float],
        lookback: int
    ) -> Tuple[bool, str]:
        """
        Detect MACD divergence
        """
        if len(closes) < lookback or len(macd_values) < lookback:
            return False, "NONE"
        
        recent_closes = closes[-lookback:]
        recent_macd = macd_values[-lookback:]
        
        # Find lows and highs
        price_low_idx = recent_closes.index(min(recent_closes))
        price_high_idx = recent_closes.index(max(recent_closes))
        
        macd_low_idx = recent_macd.index(min(recent_macd))
        macd_high_idx = recent_macd.index(max(recent_macd))
        
        # Bullish divergence: price lower low, MACD higher low
        if (price_low_idx == len(recent_closes) - 1 and
            macd_low_idx < len(recent_macd) - 1 and
            recent_closes[price_low_idx] < recent_closes[0] and
            recent_macd[macd_low_idx] > recent_macd[0]):
            return True, "BULLISH"
        
        # Bearish divergence: price higher high, MACD lower high
        if (price_high_idx == len(recent_closes) - 1 and
            macd_high_idx < len(recent_macd) - 1 and
            recent_closes[price_high_idx] > recent_closes[0] and
            recent_macd[macd_high_idx] < recent_macd[0]):
            return True, "BEARISH"
        
        return False, "NONE"
    
    def _detect_volume_divergence(
        self,
        closes: List[float],
        volumes: List[float],
        lookback: int
    ) -> Tuple[bool, str]:
        """
        Detect volume divergence
        """
        if len(closes) < lookback or len(volumes) < lookback:
            return False, "NONE"
        
        recent_closes = closes[-lookback:]
        recent_volumes = volumes[-lookback:]
        
        # Calculate price change
        price_change = recent_closes[-1] - recent_closes[0]
        
        # Calculate volume trend
        vol_ma = sum(recent_volumes[:-1]) / (len(recent_volumes) - 1)
        current_vol = recent_volumes[-1]
        
        # Bullish divergence: price down, volume up
        if price_change < 0 and current_vol > vol_ma * 1.2:
            return True, "BULLISH"
        
        # Bearish divergence: price up, volume down
        if price_change > 0 and current_vol < vol_ma * 0.8:
            return True, "BEARISH"
        
        return False, "NONE"
    
    def _detect_hidden_divergence(
        self,
        closes: List[float],
        rsi_values: List[float],
        lookback: int
    ) -> Tuple[bool, str]:
        """
        Detect hidden divergence (continuation signals)
        """
        if len(closes) < lookback or len(rsi_values) < lookback:
            return False, "NONE"
        
        recent_closes = closes[-lookback:]
        recent_rsi = rsi_values[-lookback:]
        
        # Find lows and highs
        price_low_idx = recent_closes.index(min(recent_closes))
        price_high_idx = recent_closes.index(max(recent_closes))
        
        rsi_low_idx = recent_rsi.index(min(recent_rsi))
        rsi_high_idx = recent_rsi.index(max(recent_rsi))
        
        # Bullish hidden: price higher low, RSI lower low
        if (price_low_idx < len(recent_closes) - 1 and
            recent_closes[price_low_idx] > recent_closes[0] and
            recent_rsi[rsi_low_idx] < recent_rsi[0]):
            return True, "BULLISH_HIDDEN"
        
        # Bearish hidden: price lower high, RSI higher high
        if (price_high_idx < len(recent_closes) - 1 and
            recent_closes[price_high_idx] < recent_closes[0] and
            recent_rsi[rsi_high_idx] > recent_rsi[0]):
            return True, "BEARISH_HIDDEN"
        
        return False, "NONE"
    
    def get_divergence_strength(
        self,
        result: DivergenceResult
    ) -> int:
        """
        Get numerical strength score
        """
        score = 0
        
        if result.rsi_divergence[0]:
            score += 30
        if result.macd_divergence[0]:
            score += 25
        if result.volume_divergence[0]:
            score += 15
        if result.hidden_divergence[0]:
            score += 20
        
        return score
