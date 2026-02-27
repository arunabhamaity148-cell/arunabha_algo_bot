"""
ARUNABHA ALGO BOT - Tier 2 Filters v4.2

IMPROVEMENTS (17-point plan):
Point 1 — MTF real confirmation:
    আগে: শুধু close price compare (5 candle ago)
    এখন: EMA9/21 alignment + structure direction check on 15m AND 1h AND 4h
          তিনটা TF same direction → full score
          দুটো → partial score
          একটা → fail

Point 2 — Volume on BOS/CHoCH:
    আগে: শুধু average volume ratio check
    এখন: structure detector থেকে BOS/CHoCH আছে কিনা জানা হচ্ছে
          BOS/CHoCH candle-এ volume > 1.5x average হলেই VALID
          ভলিউম spike ছাড়া BOS = false breakout → block

Point 15 — Duplicate indicator elimination:
    EMA calculation এখন analysis.technical থেকেই আসছে (utils.indicators নয়)
"""

import logging
from typing import Dict, List, Tuple, Optional, Any

import config
from core.constants import MarketType
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from analysis.volume_profile import VolumeProfileAnalyzer
from analysis.sentiment import SentimentAnalyzer

logger = logging.getLogger(__name__)


class Tier2Filters:
    """
    Tier 2 quality filters with weighted scoring
    """

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.volume = VolumeProfileAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer()
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

        # Filter 1: MTF Confirmation (IMPROVED — Point 1)
        mtf_passed, mtf_score, mtf_msg = self._check_mtf(data, direction)
        results["mtf_confirmation"] = {
            "passed": mtf_passed, "score": mtf_score,
            "weight": self.weights.get("mtf_confirmation", 20), "message": mtf_msg
        }
        total_score += mtf_score

        # Filter 2: Volume Profile
        vp_passed, vp_score, vp_msg = self._check_volume_profile(data)
        results["volume_profile"] = {
            "passed": vp_passed, "score": vp_score,
            "weight": self.weights.get("volume_profile", 15), "message": vp_msg
        }
        total_score += vp_score

        # Filter 3: Funding Rate
        funding_passed, funding_score, funding_msg = self._check_funding_rate(data, direction)
        results["funding_rate"] = {
            "passed": funding_passed, "score": funding_score,
            "weight": self.weights.get("funding_rate", 10), "message": funding_msg
        }
        total_score += funding_score

        # Filter 4: Open Interest
        oi_passed, oi_score, oi_msg = self._check_open_interest(data)
        results["open_interest"] = {
            "passed": oi_passed, "score": oi_score,
            "weight": self.weights.get("open_interest", 10), "message": oi_msg
        }
        total_score += oi_score

        # Filter 5: RSI Divergence
        rsi_passed, rsi_score, rsi_msg = self._check_rsi_divergence(data, direction)
        results["rsi_divergence"] = {
            "passed": rsi_passed, "score": rsi_score,
            "weight": self.weights.get("rsi_divergence", 15), "message": rsi_msg
        }
        total_score += rsi_score

        # Filter 6: EMA Stack (IMPROVED — Point 15)
        ema_passed, ema_score, ema_msg = self._check_ema_stack(data, direction)
        results["ema_stack"] = {
            "passed": ema_passed, "score": ema_score,
            "weight": self.weights.get("ema_stack", 10), "message": ema_msg
        }
        total_score += ema_score

        # Filter 7: ATR Percent
        atr_passed, atr_score, atr_msg = self._check_atr_percent(data)
        results["atr_percent"] = {
            "passed": atr_passed, "score": atr_score,
            "weight": self.weights.get("atr_percent", 10), "message": atr_msg
        }
        total_score += atr_score

        # Filter 8: VWAP Position
        vwap_passed, vwap_score, vwap_msg = self._check_vwap_position(data, direction)
        results["vwap_position"] = {
            "passed": vwap_passed, "score": vwap_score,
            "weight": self.weights.get("vwap_position", 5), "message": vwap_msg
        }
        total_score += vwap_score

        # Filter 9: Support/Resistance
        sr_passed, sr_score, sr_msg = self._check_support_resistance(data, direction)
        results["support_resistance"] = {
            "passed": sr_passed, "score": sr_score,
            "weight": self.weights.get("support_resistance", 5), "message": sr_msg
        }
        total_score += sr_score

        # Filter 10: Volume on BOS/CHoCH (NEW — Point 2)
        bos_vol_passed, bos_vol_score, bos_vol_msg = self._check_volume_on_structure(data)
        results["volume_on_structure"] = {
            "passed": bos_vol_passed, "score": bos_vol_score,
            "weight": self.weights.get("volume_on_structure", 10), "message": bos_vol_msg
        }
        total_score += bos_vol_score

        # Filter 11: Sentiment Score (Structure + Sentiment confirm → bonus)
        sent_passed, sent_score, sent_msg = self._check_sentiment_score(data, direction)
        results["sentiment"] = {
            "passed": sent_passed, "score": sent_score,
            "weight": self.weights.get("sentiment", 15), "message": sent_msg
        }
        total_score += sent_score

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
        """
        ✅ IMPROVED Point 1: Real MTF confirmation

        আগের সমস্যা:
            trend_15m = 1 if close[-1] > close[-5] else -1  ← 5 candle ago compare
            এটা choppy market-এ completely random

        এখন:
            প্রতিটা timeframe-এ EMA9 vs EMA21 check করা হচ্ছে
            Structure direction (BOS/CHoCH) check করা হচ্ছে
            15m + 1h + 4h তিনটাই same direction → full score (20)
            যেকোনো দুটো → partial score (12)
            একটাও না → fail (0)
        """
        ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
        ohlcv_1h = data.get("ohlcv", {}).get("1h", [])
        ohlcv_4h = data.get("ohlcv", {}).get("4h", [])

        if len(ohlcv_15m) < 21:
            return False, 0, "Insufficient 15m data for MTF"

        aligned_count = 0
        tf_details = []

        # Check each timeframe
        for tf_name, ohlcv in [("15m", ohlcv_15m), ("1h", ohlcv_1h), ("4h", ohlcv_4h)]:
            if len(ohlcv) < 21:
                tf_details.append(f"{tf_name}:N/A")
                continue

            closes = [c[4] for c in ohlcv]
            ema9 = self.analyzer.calculate_ema(closes, 9)
            ema21 = self.analyzer.calculate_ema(closes, 21)

            # EMA direction
            if ema9 > ema21:
                tf_dir = "LONG"
            elif ema9 < ema21:
                tf_dir = "SHORT"
            else:
                tf_dir = "NEUTRAL"

            # Structure direction (more reliable than EMA alone)
            if len(ohlcv) >= 30:
                struct = self.structure.detect(ohlcv)
                if struct.strength != "WEAK":
                    tf_dir = struct.direction

            tf_details.append(f"{tf_name}:{tf_dir}")

            if direction and tf_dir == direction:
                aligned_count += 1
            elif not direction and tf_dir in ["LONG", "SHORT"]:
                aligned_count += 1

        detail_str = " | ".join(tf_details)

        if aligned_count >= 3:
            return True, 20, f"All 3 TF aligned: {detail_str}"
        elif aligned_count == 2:
            return True, 12, f"2/3 TF aligned: {detail_str}"
        elif aligned_count == 1:
            return False, 4, f"Only 1 TF aligned: {detail_str}"
        else:
            return False, 0, f"No TF aligned: {detail_str}"

    def _check_volume_on_structure(self, data: Dict) -> Tuple[bool, int, str]:
        """
        ✅ NEW Point 2: Volume confirmation on BOS/CHoCH

        Volume spike ছাড়া BOS = false breakout।
        BOS/CHoCH candle-এ volume > 1.5x average হলে valid।
        এটা Tier2-তে extra filter হিসেবে কাজ করছে।
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 25:
            return True, 5, "Insufficient data — neutral"

        struct = self.structure.detect(ohlcv)

        # No BOS/CHoCH → neutral
        if not struct.bos_detected and not struct.choch_detected:
            return True, 5, "No BOS/CHoCH — volume check skipped"

        # Get last 5 candle volumes to find breakout candle
        volumes = [float(c[5]) for c in ohlcv]
        avg_vol = sum(volumes[-20:-1]) / 19 if len(volumes) >= 20 else sum(volumes[:-1]) / max(len(volumes) - 1, 1)
        last_vol = volumes[-1]

        vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0

        structure_type = "CHoCH" if struct.choch_detected else "BOS"

        if vol_ratio >= 1.5:
            return True, 10, f"{structure_type} confirmed with volume {vol_ratio:.1f}x ✅"
        elif vol_ratio >= 1.0:
            return True, 6, f"{structure_type} weak volume {vol_ratio:.1f}x — caution"
        else:
            return False, 0, f"{structure_type} without volume {vol_ratio:.1f}x — likely false break ❌"

    def _check_volume_profile(self, data: Dict) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"

        current_price = ohlcv[-1][4]
        vp_result = self.volume.analyze(ohlcv)
        in_va = self.volume.is_price_in_value_area(current_price, vp_result)

        if in_va:
            return True, 15, f"Price in value area (POC: {vp_result.poc:.4f})"
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
        oi = data.get("open_interest", {})
        if not oi:
            return True, 5, "OI data unavailable — neutral score"

        oi_change = oi.get("change_pct", 0)

        if abs(oi_change) < 1:
            return True, 8, f"OI stable ({oi_change:+.1f}%)"
        elif oi_change > 5:
            return True, 10, f"OI increasing strongly ({oi_change:+.1f}%) — trend continuation likely"
        elif oi_change < -5:
            return True, 6, f"OI decreasing ({oi_change:+.1f}%) — possible reversal"
        else:
            return True, 7, f"OI changing ({oi_change:+.1f}%)"

    def _check_rsi_divergence(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 30:
            return False, 0, "Insufficient data"

        closes = [c[4] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        highs = [c[2] for c in ohlcv]

        # Calculate RSI series for last 15 candles
        rsi_values = []
        for i in range(15, len(closes)):
            rsi = self.analyzer.calculate_rsi(closes[:i+1])
            rsi_values.append(rsi)

        if len(rsi_values) < 5:
            return False, 0, "Insufficient RSI data"

        # Check divergence in last 10 candles
        recent_closes = closes[-10:]
        recent_rsi = rsi_values[-10:]
        recent_lows = lows[-10:]
        recent_highs = highs[-10:]

        # Bullish divergence: price lower low, RSI higher low
        price_lower_low = recent_closes[-1] < min(recent_closes[:-1])
        rsi_higher_low = recent_rsi[-1] > min(recent_rsi[:-1])

        # Bearish divergence: price higher high, RSI lower high
        price_higher_high = recent_closes[-1] > max(recent_closes[:-1])
        rsi_lower_high = recent_rsi[-1] < max(recent_rsi[:-1])

        if price_lower_low and rsi_higher_low:
            if direction == "LONG":
                return True, 15, f"Bullish RSI divergence ✅ (RSI: {recent_rsi[-1]:.1f})"
            return True, 8, f"Bullish RSI divergence (not matching direction)"

        if price_higher_high and rsi_lower_high:
            if direction == "SHORT":
                return True, 15, f"Bearish RSI divergence ✅ (RSI: {recent_rsi[-1]:.1f})"
            return True, 8, f"Bearish RSI divergence (not matching direction)"

        # No divergence — check momentum
        current_rsi = recent_rsi[-1]
        if direction == "LONG" and 50 < current_rsi < 70:
            return True, 8, f"RSI bullish momentum ({current_rsi:.1f})"
        elif direction == "SHORT" and 30 < current_rsi < 50:
            return True, 8, f"RSI bearish momentum ({current_rsi:.1f})"

        return False, 3, f"No RSI divergence (RSI: {current_rsi:.1f})"

    def _check_ema_stack(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        """
        ✅ KEPT from v4.1 fix — uses full candle list for EMA200
        Point 15: Only uses analysis.technical (no utils.indicators duplicate)
        """
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 30:
            return False, 0, "Insufficient 1h data (need 30+)"

        closes = [c[4] for c in ohlcv]

        ema9 = self.analyzer.calculate_ema(closes, 9)
        ema21 = self.analyzer.calculate_ema(closes, 21)

        if len(closes) >= 200:
            ema200 = self.analyzer.calculate_ema(closes, 200)
        elif len(closes) >= 50:
            ema200 = self.analyzer.calculate_ema(closes, 50)
        else:
            ema200 = self.analyzer.calculate_ema(closes, len(closes))

        bullish_stack = ema9 > ema21 > ema200
        bearish_stack = ema9 < ema21 < ema200

        if direction == "LONG" and bullish_stack:
            return True, 10, f"✅ Bullish EMA stack (9>21>200)"
        elif direction == "SHORT" and bearish_stack:
            return True, 10, f"✅ Bearish EMA stack (9<21<200)"
        elif bullish_stack or bearish_stack:
            return True, 5, "EMA stack exists but opposite direction"
        return False, 2, "No clear EMA stack"

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
        if len(ohlcv) < 10:
            return False, 0, "Insufficient data"

        closes = [c[4] for c in ohlcv]
        vwap = self.analyzer.calculate_vwap(ohlcv)
        current_price = closes[-1]

        if direction == "LONG" and current_price > vwap:
            return True, 5, f"Price above VWAP ({vwap:.4f}) ✅"
        elif direction == "SHORT" and current_price < vwap:
            return True, 5, f"Price below VWAP ({vwap:.4f}) ✅"
        elif abs(current_price - vwap) / vwap < 0.002:
            return True, 3, f"Price at VWAP ({vwap:.4f}) — neutral"
        return False, 1, f"Price {'below' if current_price < vwap else 'above'} VWAP (opposite direction)"

    def _check_support_resistance(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 30:
            return False, 0, "Insufficient data"

        current_price = ohlcv[-1][4]
        levels = self.structure.get_support_resistance(ohlcv, num_levels=5)

        supports = [s for s in levels.get("support", []) if s < current_price]
        resistances = [r for r in levels.get("resistance", []) if r > current_price]

        if direction == "LONG" and supports:
            nearest_support = max(supports)
            dist_pct = (current_price - nearest_support) / current_price * 100
            if dist_pct < 1.0:
                return True, 5, f"Near support {nearest_support:.4f} ({dist_pct:.2f}% away)"
            return True, 3, f"Support exists at {nearest_support:.4f}"

        if direction == "SHORT" and resistances:
            nearest_resistance = min(resistances)
            dist_pct = (nearest_resistance - current_price) / current_price * 100
            if dist_pct < 1.0:
                return True, 5, f"Near resistance {nearest_resistance:.4f} ({dist_pct:.2f}% away)"
            return True, 3, f"Resistance exists at {nearest_resistance:.4f}"

        return False, 1, "No nearby S/R levels"

    def _check_sentiment_score(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        """
        Tier2 Sentiment Score:
        Structure + Sentiment একসাথে confirm করলে বেশি score।
        RISK_ON + LONG structure → full 15 points
        RISK_OFF + SHORT structure → full 15 points
        Mismatch → reduced score
        """
        try:
            sentiment_data = data.get("sentiment", None)
            result = self.sentiment_analyzer.analyze(sentiment_data)

            base_score = self.sentiment_analyzer.get_sentiment_score(result, direction)
            fg = result.fear_greed_value
            label = result.fear_greed_label.replace("_", " ")
            alt = result.alt_season_index

            # Check structure alignment for bonus
            ohlcv = data.get("ohlcv", {}).get("15m", [])
            if len(ohlcv) >= 30 and base_score >= 8:
                from analysis.structure import StructureDetector
                struct = StructureDetector().detect(ohlcv)
                if struct.strength != "WEAK" and struct.direction == direction:
                    # Structure + Sentiment confirm → max score
                    return True, min(15, base_score + 3), (
                        f"✅ Structure+Sentiment aligned: {label} ({fg}), AltSeason={alt}"
                    )

            if base_score >= 8:
                return True, base_score, f"Sentiment OK: {label} ({fg}), AltSeason={alt}"
            elif base_score > 0:
                return True, base_score, f"Sentiment weak for {direction}: {label} ({fg})"
            else:
                return False, 0, f"❌ Sentiment blocks {direction}: {label} ({fg})"

        except Exception as e:
            logger.warning(f"Tier2 sentiment score error: {e}")
            return True, 5, "Sentiment score skipped (error)"
