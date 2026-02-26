"""
ARUNABHA ALGO BOT - Market Regime Detector v4.1

FIXES:
- BUG-13: EMA200 এখন full candle data ব্যবহার করছে (আগে শুধু 30 candle ছিল)
"""

import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import config
from core.constants import MarketType, BTCRegime
from utils.indicators import calculate_adx, calculate_atr, calculate_ema

logger = logging.getLogger(__name__)


@dataclass
class RegimeResult:
    market_type: MarketType
    confidence: int
    adx: float
    atr_pct: float
    reason: str


@dataclass
class BTCRegimeResult:
    regime: BTCRegime
    confidence: int
    direction: str
    strength: str
    can_trade: bool
    trade_mode: str
    reason: Optional[str] = None


class MarketRegimeDetector:
    """Detects market regime (trending/choppy/high_vol)"""

    def __init__(self):
        self.history: List[str] = []
        self.max_history = 10
        self.last_market = MarketType.UNKNOWN

    def detect_market_type(
        self,
        btc_15m: List[List[float]],
        btc_1h: List[List[float]]
    ) -> MarketType:
        if not btc_15m or len(btc_15m) < 30:
            return MarketType.UNKNOWN

        adx = calculate_adx(btc_15m)
        atr_pct = self._calculate_atr_pct(btc_1h)

        if atr_pct > 3.0:
            market = MarketType.HIGH_VOL
        elif adx > 25:
            market = MarketType.TRENDING
        else:
            market = MarketType.CHOPPY

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
        ema_score = self._analyze_ema_structure(btc_15m, btc_1h, btc_4h)
        structure_score = self._analyze_structure(btc_4h)
        momentum_score = self._analyze_momentum(btc_15m)

        adx = calculate_adx(btc_15m)

        total_score = (
            ema_score * 0.4 +
            structure_score * 0.35 +
            momentum_score * 0.25
        )

        regime, confidence = self._classify_regime(total_score, adx)
        can_trade, trade_mode, reason = self._can_trade(regime, confidence, adx)

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
        if len(ohlcv) < 14:
            return 1.0
        atr = calculate_atr(ohlcv)
        current_price = ohlcv[-1][4]
        return (atr / current_price) * 100 if current_price > 0 else 1.0

    def _analyze_ema_structure(self, tf15: List, tf1h: List, tf4h: List) -> float:
        """
        ✅ FIX BUG-13: EMA200 calculation এখন FULL data ব্যবহার করছে
        আগে closes = closes[-30:] ছিল — এতে EMA200 সম্পূর্ণ ভুল হতো
        এখন: সব available candle ব্যবহার করো, minimum 30 require করো
        """
        score = 0.0

        timeframes = [
            (tf15, 0.6),
            (tf1h, 1.0),
            (tf4h, 1.4)
        ]

        for tf, weight in timeframes:
            if len(tf) < 30:
                continue

            # ✅ FIXED: Full candle list use করো, শুধু last 30 না
            closes = [c[4] for c in tf]

            ema9 = calculate_ema(closes, 9)
            ema21 = calculate_ema(closes, 21)

            # EMA200 এর জন্য কমপক্ষে 50 candle দরকার (200 ideal)
            # কম থাকলে EMA50 use করো as proxy
            if len(closes) >= 200:
                ema200 = calculate_ema(closes, 200)
            elif len(closes) >= 50:
                ema200 = calculate_ema(closes, 50)  # proxy
            else:
                ema200 = calculate_ema(closes, len(closes))  # best available

            current = closes[-1]

            if ema9 > ema21 > ema200:
                score += 8 * weight
            elif ema9 < ema21 < ema200:
                score -= 8 * weight
            elif ema9 > ema21:
                score += 3 * weight
            elif ema9 < ema21:
                score -= 3 * weight

        return max(-20, min(20, score))

    def _analyze_structure(self, tf4h: List) -> float:
        if len(tf4h) < 20:
            return 0.0

        highs = [c[2] for c in tf4h[-20:]]
        lows = [c[3] for c in tf4h[-20:]]

        swing_highs = []
        swing_lows = []

        for i in range(2, len(highs) - 2):
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                    highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                swing_highs.append((i, highs[i]))
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                    lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                swing_lows.append((i, lows[i]))

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return 3.0

        recent_hh = [h for _, h in swing_highs[-2:]]
        recent_ll = [l for _, l in swing_lows[-2:]]

        hh = recent_hh[-1] > recent_hh[0] if len(recent_hh) >= 2 else False
        hl = recent_ll[-1] > recent_ll[0] if len(recent_ll) >= 2 else False
        lh = recent_hh[-1] < recent_hh[0] if len(recent_hh) >= 2 else False
        ll = recent_ll[-1] < recent_ll[0] if len(recent_ll) >= 2 else False

        if hh and hl:
            return 15.0
        elif lh and ll:
            return -15.0
        elif hh or hl:
            return 8.0
        elif lh or ll:
            return -8.0
        else:
            return 0.0

    def _analyze_momentum(self, tf15: List) -> float:
        if len(tf15) < 14:
            return 0.0

        from utils.indicators import calculate_rsi
        closes = [c[4] for c in tf15[-14:]]
        rsi = calculate_rsi(closes)

        if rsi > 60:
            score = (rsi - 60) / 40 * 8
        elif rsi < 40:
            score = -(40 - rsi) / 40 * 8
        else:
            score = 0

        volumes = [c[5] for c in tf15[-5:]]
        avg_vol = sum(volumes[:-1]) / (len(volumes) - 1) if len(volumes) > 1 else volumes[0]
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1

        if vol_ratio > 1.2:
            score *= 1.2
        elif vol_ratio < 0.8:
            score *= 0.8

        return max(-10, min(10, score))

    def _classify_regime(self, score: float, adx: float) -> Tuple[BTCRegime, int]:
        if adx > 25:
            adx_conf = min(100, int(adx * 2.5))
        elif adx > 20:
            adx_conf = min(80, int(adx * 2.2))
        else:
            adx_conf = min(60, int(adx * 2))

        if score >= 15:
            return BTCRegime.STRONG_BULL, min(100, adx_conf + 15)
        elif score >= 5:
            return BTCRegime.BULL, adx_conf
        elif score <= -15:
            return BTCRegime.STRONG_BEAR, min(100, adx_conf + 15)
        elif score <= -5:
            return BTCRegime.BEAR, adx_conf
        else:
            return BTCRegime.CHOPPY, min(70, adx_conf)

    def _can_trade(self, regime: BTCRegime, confidence: int, adx: float) -> Tuple[bool, str, Optional[str]]:
        if regime == BTCRegime.UNKNOWN:
            return False, "BLOCK", "Unknown regime"
        if confidence < config.BTC_REGIME_CONFIG["hard_block_confidence"]:
            return False, "BLOCK", f"Confidence {confidence}% too low"
        if regime == BTCRegime.CHOPPY:
            if confidence < config.BTC_REGIME_CONFIG["choppy_min_confidence"]:
                return False, "BLOCK", f"Choppy + low confidence {confidence}%"
            if adx < config.BTC_REGIME_CONFIG["choppy_adx_min"]:
                return False, "BLOCK", f"Choppy + weak ADX {adx:.1f}"
            return True, "RANGE", None
        if regime in [BTCRegime.BULL, BTCRegime.BEAR, BTCRegime.STRONG_BULL, BTCRegime.STRONG_BEAR]:
            if confidence < config.BTC_REGIME_CONFIG["trend_min_confidence"]:
                return False, "BLOCK", f"Trend + low confidence {confidence}%"
            if adx < config.BTC_REGIME_CONFIG["trend_adx_min"]:
                return False, "BLOCK", f"Trend + weak ADX {adx:.1f}"
            return True, "TREND", None
        return False, "BLOCK", f"Unhandled regime: {regime.value}"

    def get_confidence_for_direction(self, direction: str, regime: BTCRegimeResult) -> int:
        if not regime.can_trade:
            return 0
        if (direction == "LONG" and regime.direction == "UP") or \
           (direction == "SHORT" and regime.direction == "DOWN"):
            return regime.confidence
        base_conf = regime.confidence // 2
        if regime.strength == "STRONG":
            base_conf = base_conf // 2
        elif regime.strength == "MODERATE":
            base_conf = int(base_conf * 0.7)
        return base_conf
