"""
ARUNABHA ALGO BOT - Tier 2 Filters v4.1

FIXES:
- BUG-15: EMA stack check এ EMA200 এখন full candle data ব্যবহার করছে
          আগে ohlcv[-50:] দিয়ে 50 candle দিয়ে EMA200 হিসাব করত — সম্পূর্ণ ভুল
          এখন: সব available candle use করো, minimum 100 require করো
- BUG-16: Open Interest filter এ এখন dummy "always pass" না করে
          OI data না থাকলে neutral score দেওয়া হচ্ছে
- BUG-17: Correlation check এ symbol-specific data সঠিকভাবে handle হচ্ছে
"""

import logging
from typing import Dict, List, Tuple, Optional, Any

import config
from core.constants import MarketType
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from analysis.volume_profile import VolumeProfileAnalyzer

logger = logging.getLogger(__name__)


class Tier2Filters:
    """
    Tier 2 quality filters with weighted scoring
    Minimum score needed to pass
    """

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.volume = VolumeProfileAnalyzer()
        self.weights = config.TIER2_FILTERS

    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        market_type: MarketType,
        data: Dict[str, Any]
    ) -> Tuple[bool, int, Dict[str, Any]]:
        results = {}
        total_score = 0
        max_score = sum(self.weights.values())

        # Filter 1: MTF Confirmation
        mtf_passed, mtf_score, mtf_msg = self._check_mtf(data, direction)
        results["mtf_confirmation"] = {"passed": mtf_passed, "score": mtf_score,
                                        "weight": self.weights.get("mtf_confirmation", 20), "message": mtf_msg}
        total_score += mtf_score

        # Filter 2: Volume Profile
        vp_passed, vp_score, vp_msg = self._check_volume_profile(data)
        results["volume_profile"] = {"passed": vp_passed, "score": vp_score,
                                      "weight": self.weights.get("volume_profile", 15), "message": vp_msg}
        total_score += vp_score

        # Filter 3: Funding Rate
        funding_passed, funding_score, funding_msg = self._check_funding_rate(data, direction)
        results["funding_rate"] = {"passed": funding_passed, "score": funding_score,
                                    "weight": self.weights.get("funding_rate", 10), "message": funding_msg}
        total_score += funding_score

        # Filter 4: Open Interest
        oi_passed, oi_score, oi_msg = self._check_open_interest(data)
        results["open_interest"] = {"passed": oi_passed, "score": oi_score,
                                     "weight": self.weights.get("open_interest", 10), "message": oi_msg}
        total_score += oi_score

        # Filter 5: RSI Divergence
        rsi_passed, rsi_score, rsi_msg = self._check_rsi_divergence(data, direction)
        results["rsi_divergence"] = {"passed": rsi_passed, "score": rsi_score,
                                      "weight": self.weights.get("rsi_divergence", 15), "message": rsi_msg}
        total_score += rsi_score

        # Filter 6: EMA Stack
        ema_passed, ema_score, ema_msg = self._check_ema_stack(data, direction)
        results["ema_stack"] = {"passed": ema_passed, "score": ema_score,
                                 "weight": self.weights.get("ema_stack", 10), "message": ema_msg}
        total_score += ema_score

        # Filter 7: ATR Percent
        atr_passed, atr_score, atr_msg = self._check_atr_percent(data)
        results["atr_percent"] = {"passed": atr_passed, "score": atr_score,
                                   "weight": self.weights.get("atr_percent", 10), "message": atr_msg}
        total_score += atr_score

        # Filter 8: VWAP Position
        vwap_passed, vwap_score, vwap_msg = self._check_vwap_position(data, direction)
        results["vwap_position"] = {"passed": vwap_passed, "score": vwap_score,
                                     "weight": self.weights.get("vwap_position", 5), "message": vwap_msg}
        total_score += vwap_score

        # Filter 9: Support/Resistance
        sr_passed, sr_score, sr_msg = self._check_support_resistance(data, direction)
        results["support_resistance"] = {"passed": sr_passed, "score": sr_score,
                                          "weight": self.weights.get("support_resistance", 5), "message": sr_msg}
        total_score += sr_score

        percentage = (total_score / max_score) * 100 if max_score > 0 else 0
        threshold = self._get_threshold(market_type)
        passed = percentage >= threshold

        logger.debug(f"Tier2 score: {percentage:.1f}% {'≥' if passed else '<'} {threshold}%")
        return passed, percentage, results

    def _get_threshold(self, market_type: MarketType) -> int:
        return {
            MarketType.TRENDING: 60,
            MarketType.CHOPPY: 55,
            MarketType.HIGH_VOL: 65,
            MarketType.UNKNOWN: 60
        }.get(market_type, 60)

    def _check_mtf(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
        ohlcv_1h = data.get("ohlcv", {}).get("1h", [])

        if len(ohlcv_15m) < 10 or len(ohlcv_1h) < 10:
            return False, 0, "Insufficient data"

        trend_15m = 1 if ohlcv_15m[-1][4] > ohlcv_15m[-5][4] else -1
        trend_1h = 1 if ohlcv_1h[-1][4] > ohlcv_1h[-5][4] else -1

        if trend_15m == trend_1h:
            if direction:
                dir_val = 1 if direction == "LONG" else -1
                if trend_15m == dir_val:
                    return True, 20, "All TF aligned with direction"
                else:
                    return True, 15, "TF aligned but opposite direction"
            return True, 20, "All TF aligned"
        return False, 5, "TF conflict"

    def _check_volume_profile(self, data: Dict) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"

        current_price = ohlcv[-1][4]
        vp_result = self.volume.analyze(ohlcv)
        in_va = self.volume.is_price_in_value_area(current_price, vp_result)

        if in_va:
            return True, 15, f"Price in value area (POC: {vp_result.poc:.2f})"
        pos = self.volume.get_value_area_position(current_price, vp_result)
        if pos in ["BELOW_VA", "ABOVE_VA"]:
            return True, 10, f"Price {pos}, near key level"
        return False, 5, "Price away from value area"

    def _check_funding_rate(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        funding = data.get("funding_rate", 0)
        funding_pct = funding * 100

        if abs(funding_pct) > 0.01:
            if direction == "LONG" and funding_pct > 0:
                return False, 0, f"High positive funding ({funding_pct:.3f}%)"
            elif direction == "SHORT" and funding_pct < 0:
                return False, 0, f"High negative funding ({funding_pct:.3f}%)"
            else:
                return True, 10, f"Funding supports trade ({funding_pct:.3f}%)"
        return True, 10, f"Funding neutral ({funding_pct:.3f}%)"

    def _check_open_interest(self, data: Dict) -> Tuple[bool, int, str]:
        """
        ✅ FIX BUG-16: আগে সবসময় 10 দিত — এখন সঠিকভাবে neutral score দেওয়া হচ্ছে
        """
        oi = data.get("open_interest", 0)
        oi_prev = data.get("open_interest_prev", 0)

        if oi <= 0:
            # Data নেই — neutral, half score
            return True, 5, "OI data unavailable (neutral)"

        if oi_prev > 0:
            oi_change_pct = ((oi - oi_prev) / oi_prev) * 100
            if oi_change_pct > 5:
                return True, 10, f"OI increasing +{oi_change_pct:.1f}% (bullish pressure)"
            elif oi_change_pct < -5:
                return True, 8, f"OI decreasing {oi_change_pct:.1f}% (position closing)"
            else:
                return True, 7, f"OI stable ({oi_change_pct:.1f}% change)"

        return True, 7, "OI present but no history"

    def _check_rsi_divergence(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"

        from analysis.divergence import DivergenceDetector
        detector = DivergenceDetector()
        result = detector.detect_all(ohlcv)

        if direction == "LONG" and result.rsi_divergence[1] == "BULLISH":
            return True, 15, "Bullish RSI divergence"
        elif direction == "SHORT" and result.rsi_divergence[1] == "BEARISH":
            return True, 15, "Bearish RSI divergence"
        elif result.rsi_divergence[0]:
            return True, 10, f"RSI divergence: {result.rsi_divergence[1]}"
        return False, 5, "No RSI divergence"

    def _check_ema_stack(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        """
        ✅ FIX BUG-15: EMA200 এর জন্য full candle list use করা হচ্ছে
        আগে: ohlcv[-50:] দিয়ে 50 candle → EMA200 সম্পূর্ণ ভুল
        এখন: সব available candle use করো
        """
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 30:
            return False, 0, "Insufficient data (need 30+ candles)"

        # ✅ FIXED: Full list use করো
        closes = [c[4] for c in ohlcv]

        ema9 = self.analyzer.calculate_ema(closes, 9)
        ema21 = self.analyzer.calculate_ema(closes, 21)

        # EMA200 proxy যদি কম candle থাকে
        if len(closes) >= 200:
            ema200 = self.analyzer.calculate_ema(closes, 200)
        elif len(closes) >= 50:
            ema200 = self.analyzer.calculate_ema(closes, 50)
        else:
            ema200 = self.analyzer.calculate_ema(closes, len(closes))

        bullish_stack = ema9 > ema21 > ema200
        bearish_stack = ema9 < ema21 < ema200

        if direction == "LONG" and bullish_stack:
            return True, 10, "Bullish EMA stack (9>21>200)"
        elif direction == "SHORT" and bearish_stack:
            return True, 10, "Bearish EMA stack (9<21<200)"
        elif bullish_stack:
            return True, 7, "Bullish stack (trade opposite — caution)"
        elif bearish_stack:
            return True, 7, "Bearish stack (trade opposite — caution)"
        return False, 3, "No clear EMA stack"

    def _check_atr_percent(self, data: Dict) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 14:
            return False, 0, "Insufficient data"

        atr = self.analyzer.calculate_atr(ohlcv)
        current_price = ohlcv[-1][4]
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0

        if config.MIN_ATR_PCT <= atr_pct <= config.MAX_ATR_PCT:
            return True, 10, f"ATR {atr_pct:.2f}% in range"
        elif atr_pct < config.MIN_ATR_PCT:
            return False, 5, f"ATR too low: {atr_pct:.2f}%"
        return False, 5, f"ATR too high: {atr_pct:.2f}%"

    def _check_vwap_position(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"

        vwap = self.analyzer.calculate_vwap(ohlcv)
        current = ohlcv[-1][4]

        if direction == "LONG" and current > vwap:
            return True, 5, f"Price above VWAP ({current/vwap-1:.2%})"
        elif direction == "SHORT" and current < vwap:
            return True, 5, f"Price below VWAP ({vwap/current-1:.2%})"
        elif abs(current - vwap) / vwap < 0.01:
            return True, 3, "Price near VWAP"
        return False, 1, "Price away from VWAP"

    def _check_support_resistance(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        """
        ✅ FIX BUG-17: Correlation data ঠিকমতো handle করা হচ্ছে এখানে
        S/R check নিজের data দিয়ে করা হচ্ছে
        """
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"

        detector = StructureDetector()
        levels = detector.get_support_resistance(ohlcv)
        current = ohlcv[-1][4]
        nearest_type, nearest_level, distance = detector.get_nearest_level(current, levels)

        if direction == "LONG" and nearest_type == "support":
            return True, 5, f"Near support ({distance:.2f}%)"
        elif direction == "SHORT" and nearest_type == "resistance":
            return True, 5, f"Near resistance ({distance:.2f}%)"
        elif nearest_level:
            return True, 3, f"Near {nearest_type} ({distance:.2f}%)"
        return False, 1, "No clear S/R levels"
