"""
ARUNABHA ALGO BOT - Market Regime Detector
Identifies trending, choppy, and high volatility regimes
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import config
from core.constants import MarketType, BTCRegime
from utils.indicators import calculate_adx, calculate_atr, calculate_ema

logger = logging.getLogger(__name__)


@dataclass
class RegimeResult:
    """Market regime detection result"""
    market_type: MarketType
    confidence: int
    adx: float
    atr_pct: float
    reason: str


@dataclass
class BTCRegimeResult:
    """BTC regime detection result"""
    regime: BTCRegime
    confidence: int
    direction: str
    strength: str
    can_trade: bool
    trade_mode: str
    reason: Optional[str] = None


class MarketRegimeDetector:
    """
    Detects market regime (trending/choppy/high_vol)
    """
    
    def __init__(self):
        self.history: List[str] = []
        self.max_history = 10
        self.last_market = MarketType.UNKNOWN
    
    def detect_market_type(
        self,
        btc_15m: List[List[float]],
        btc_1h: List[List[float]]
    ) -> MarketType:
        """
        Detect current market type based on BTC
        
        Returns: MarketType (TRENDING, CHOPPY, HIGH_VOL, UNKNOWN)
        """
        if not btc_15m or len(btc_15m) < 30:
            return MarketType.UNKNOWN
        
        # Calculate ADX for trend strength
        adx = calculate_adx(btc_15m)
        
        # Calculate ATR for volatility
        atr_pct = self._calculate_atr_pct(btc_1h)
        
        # Check volatility first
        if atr_pct > 3.0:
            market = MarketType.HIGH_VOL
            logger.debug(f"HIGH_VOL detected: ATR {atr_pct:.1f}%")
        
        # Check trend strength
        elif adx > 25:
            market = MarketType.TRENDING
            logger.debug(f"TRENDING detected: ADX {adx:.1f}")
        
        # Default to choppy
        else:
            market = MarketType.CHOPPY
            logger.debug(f"CHOPPY detected: ADX {adx:.1f}")
        
        # Update history
        self.history.append(market.value)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        self.last_market = market
        return market
    
    def detect_btc_regime(
        self,
        btc_15m: List[List[float]],
        btc_1h: List[List[float]],
        btc_4h: List[List[float]]
    ) -> BTCRegimeResult:
        """
        Detect detailed BTC regime for filtering
        """
        # Get scores from different timeframes
        ema_score = self._analyze_ema_structure(btc_15m, btc_1h, btc_4h)
        structure_score = self._analyze_structure(btc_4h)
        momentum_score = self._analyze_momentum(btc_15m)
        
        # Calculate ADX
        adx = calculate_adx(btc_15m)
        
        # Total score
        total_score = (
            ema_score * 0.4 +
            structure_score * 0.35 +
            momentum_score * 0.25
        )
        
        # Determine regime
        regime, confidence = self._classify_regime(total_score, adx)
        
        # Check if we can trade
        can_trade, trade_mode, reason = self._can_trade(
            regime, confidence, adx
        )
        
        # Determine direction
        if total_score > 3:
            direction = "UP"
            strength = "STRONG" if abs(total_score) > 15 else "MODERATE"
        elif total_score < -3:
            direction = "DOWN"
            strength = "STRONG" if abs(total_score) > 15 else "MODERATE"
        else:
            direction = "SIDEWAYS"
            strength = "WEAK"
        
        return BTCRegimeResult(
            regime=regime,
            confidence=confidence,
            direction=direction,
            strength=strength,
            can_trade=can_trade,
            trade_mode=trade_mode,
            reason=reason
        )
    
    def _calculate_atr_pct(self, ohlcv: List[List[float]]) -> float:
        """Calculate ATR as percentage"""
        if len(ohlcv) < 14:
            return 1.0
        
        atr = calculate_atr(ohlcv)
        current_price = ohlcv[-1][4]
        
        return (atr / current_price) * 100 if current_price > 0 else 1.0
    
    def _analyze_ema_structure(self, tf15: List, tf1h: List, tf4h: List) -> float:
        """Analyze EMA structure across timeframes"""
        score = 0.0
        
        # Check each timeframe
        timeframes = [
            (tf15, 0.6),
            (tf1h, 1.0),
            (tf4h, 1.4)
        ]
        
        for tf, weight in timeframes:
            if len(tf) < 30:
                continue
            
            closes = [c[4] for c in tf[-30:]]
            ema9 = calculate_ema(closes, 9)
            ema21 = calculate_ema(closes, 21)
            ema200 = calculate_ema(closes, 200)
            current = closes[-1]
            
            # Bullish alignment
            if ema9 > ema21 > ema200:
                score += 8 * weight
            # Bearish alignment
            elif ema9 < ema21 < ema200:
                score -= 8 * weight
            # Mixed alignment
            elif ema9 > ema21:
                score += 3 * weight
            elif ema9 < ema21:
                score -= 3 * weight
        
        return max(-20, min(20, score))
    
    def _analyze_structure(self, tf4h: List) -> float:
        """Analyze market structure (HH/HL/LH/LL)"""
        if len(tf4h) < 20:
            return 0.0
        
        highs = [c[2] for c in tf4h[-20:]]
        lows = [c[3] for c in tf4h[-20:]]
        
        # Find swing points
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(highs)-2):
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                swing_highs.append((i, highs[i]))
            
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                swing_lows.append((i, lows[i]))
        
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return 3.0  # Default to slight bullish
        
        # Check HH/HL pattern
        recent_hh = [h for _, h in swing_highs[-2:]]
        recent_ll = [l for _, l in swing_lows[-2:]]
        
        hh = recent_hh[-1] > recent_hh[0] if len(recent_hh) >= 2 else False
        hl = recent_ll[-1] > recent_ll[0] if len(recent_ll) >= 2 else False
        lh = recent_hh[-1] < recent_hh[0] if len(recent_hh) >= 2 else False
        ll = recent_ll[-1] < recent_ll[0] if len(recent_ll) >= 2 else False
        
        # Score based on structure
        if hh and hl:
            return 15.0  # Strong bull
        elif lh and ll:
            return -15.0  # Strong bear
        elif hh or hl:
            return 8.0  # Bullish
        elif lh or ll:
            return -8.0  # Bearish
        else:
            return 0.0  # Choppy
    
    def _analyze_momentum(self, tf15: List) -> float:
        """Analyze momentum using RSI and volume"""
        if len(tf15) < 14:
            return 0.0
        
        from utils.indicators import calculate_rsi
        
        closes = [c[4] for c in tf15[-14:]]
        rsi = calculate_rsi(closes)
        
        # RSI momentum
        if rsi > 60:
            score = (rsi - 60) / 40 * 8
        elif rsi < 40:
            score = -(40 - rsi) / 40 * 8
        else:
            score = 0
        
        # Volume confirmation
        volumes = [c[5] for c in tf15[-5:]]
        avg_vol = sum(volumes[:-1]) / (len(volumes)-1) if len(volumes) > 1 else volumes[0]
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1
        
        if vol_ratio > 1.2:
            score *= 1.2
        elif vol_ratio < 0.8:
            score *= 0.8
        
        return max(-10, min(10, score))
    
    def _classify_regime(self, score: float, adx: float) -> Tuple[BTCRegime, int]:
        """Classify BTC regime based on score and ADX"""
        abs_score = abs(score)
        
        # Calculate confidence based on ADX
        if adx > 25:
            adx_conf = min(100, int(adx * 2.5))
        elif adx > 20:
            adx_conf = min(80, int(adx * 2.2))
        else:
            adx_conf = min(60, int(adx * 2))
        
        # Determine regime
        if score >= 15:
            confidence = min(100, adx_conf + 15)
            return BTCRegime.STRONG_BULL, confidence
        elif score >= 5:
            confidence = adx_conf
            return BTCRegime.BULL, confidence
        elif score <= -15:
            confidence = min(100, adx_conf + 15)
            return BTCRegime.STRONG_BEAR, confidence
        elif score <= -5:
            confidence = adx_conf
            return BTCRegime.BEAR, confidence
        else:
            confidence = min(70, adx_conf)
            return BTCRegime.CHOPPY, confidence
    
    def _can_trade(self, regime: BTCRegime, confidence: int, adx: float) -> Tuple[bool, str, Optional[str]]:
        """Determine if we can trade based on regime"""
        
        # Hard block on unknown
        if regime == BTCRegime.UNKNOWN:
            return False, "BLOCK", "Unknown regime"
        
        # Confidence too low
        if confidence < config.BTC_REGIME_CONFIG["hard_block_confidence"]:
            return False, "BLOCK", f"Confidence {confidence}% too low"
        
        # Choppy regime
        if regime == BTCRegime.CHOPPY:
            if confidence < config.BTC_REGIME_CONFIG["choppy_min_confidence"]:
                return False, "BLOCK", f"Choppy + low confidence {confidence}%"
            if adx < config.BTC_REGIME_CONFIG["choppy_adx_min"]:
                return False, "BLOCK", f"Choppy + weak ADX {adx:.1f}"
            return True, "RANGE", None
        
        # Trend regimes
        if regime in [BTCRegime.BULL, BTCRegime.BEAR, 
                      BTCRegime.STRONG_BULL, BTCRegime.STRONG_BEAR]:
            if confidence < config.BTC_REGIME_CONFIG["trend_min_confidence"]:
                return False, "BLOCK", f"Trend + low confidence {confidence}%"
            if adx < config.BTC_REGIME_CONFIG["trend_adx_min"]:
                return False, "BLOCK", f"Trend + weak ADX {adx:.1f}"
            return True, "TREND", None
        
        return False, "BLOCK", f"Unhandled regime: {regime.value}"
    
    def get_confidence_for_direction(self, direction: str, regime: BTCRegimeResult) -> int:
        """Get confidence score for a specific trade direction"""
        
        if not regime.can_trade:
            return 0
        
        # Same direction as BTC trend
        if (direction == "LONG" and regime.direction == "UP") or \
           (direction == "SHORT" and regime.direction == "DOWN"):
            return regime.confidence
        
        # Opposite direction
        base_conf = regime.confidence // 2
        
        # Adjust based on strength
        if regime.strength == "STRONG":
            base_conf = base_conf // 2
        elif regime.strength == "MODERATE":
            base_conf = int(base_conf * 0.7)
        
        return base_conf
