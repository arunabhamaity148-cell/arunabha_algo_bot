"""
ARUNABHA ALGO BOT - Tier 2 Filters v5.0
=========================================
FIXES:
ISSUE 9:  MTF Confirmation — price action + structure properly integrated
          Higher timeframe structure direction overrides EMA when strong
ISSUE 10: Volume on BOS/CHoCH — properly identifies BOS candle index,
          checks volume on THAT specific candle (not just last candle)
ISSUE 11: Sentiment ROC used in Tier2 scoring
          RECOVERY mood → bonus for LONG
          FALLING_FAST → penalty
"""

import logging
from typing import Dict, List, Tuple, Optional, Any

import config
from core.constants import MarketType
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from analysis.volume_profile import VolumeProfileAnalyzer
from analysis.sentiment import SentimentAnalyzer, MarketMood

logger = logging.getLogger(__name__)


class Tier2Filters:

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
    ) -> Tuple[bool, float, Dict[str, Any]]:

        results = {}
        total_score = 0
        max_score = sum(self.weights.values())

        def add(name, fn, *args):
            nonlocal total_score
            p, s, m = fn(*args)
            results[name] = {
                "passed": p, "score": s,
                "weight": self.weights.get(name, 0), "message": m
            }
            total_score += s

        add("mtf_confirmation",    self._check_mtf,                 data, direction)
        add("volume_profile",      self._check_volume_profile,      data)
        add("funding_rate",        self._check_funding_rate,        data, direction)
        add("open_interest",       self._check_open_interest,       data)
        add("rsi_divergence",      self._check_rsi_divergence,      data, direction)
        add("ema_stack",           self._check_ema_stack,           data, direction)
        add("atr_percent",         self._check_atr_percent,         data)
        add("vwap_position",       self._check_vwap_position,       data, direction)
        add("support_resistance",  self._check_support_resistance,  data, direction)
        add("volume_on_structure", self._check_volume_on_structure, data, direction)
        add("sentiment",           self._check_sentiment_score,     data, direction)

        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        threshold = self._get_threshold(market_type)
        passed = percentage >= threshold

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
        ISSUE 9 FIX: Real MTF with price action integration

        Logic per timeframe:
        1. Get market structure (BOS/CHoCH) — most reliable
        2. If structure is WEAK, fall back to EMA9/21 direction
        3. Also check: is price above/below EMA200 (major trend)
        All 3 TF same direction → 20pts. 2 → 12pts. 1 → 4pts. 0 → 0pts.
        """
        ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
        ohlcv_1h  = data.get("ohlcv", {}).get("1h", [])
        ohlcv_4h  = data.get("ohlcv", {}).get("4h", [])

        if len(ohlcv_15m) < 21:
            return False, 0, "Insufficient 15m data"

        aligned = 0
        details = []

        for tf_name, ohlcv in [("15m", ohlcv_15m), ("1h", ohlcv_1h), ("4h", ohlcv_4h)]:
            if len(ohlcv) < 21:
                details.append(f"{tf_name}:N/A")
                continue

            closes = [float(c[4]) for c in ohlcv]
            current = closes[-1]

            # ISSUE 9 FIX: Structure-first direction
            tf_dir = "NEUTRAL"
            if len(ohlcv) >= 30:
                struct = self.structure.detect(ohlcv)
                if struct.strength in ("STRONG", "MODERATE"):
                    tf_dir = struct.direction
                    # Price action confirmation: price must be above key level for LONG
                    # (structure direction AND price position agree)
                    if tf_dir == "LONG" and len(closes) >= 10:
                        recent_pivot_low = min(closes[-10:])
                        if current < recent_pivot_low * 0.99:
                            tf_dir = "NEUTRAL"  # structure says LONG but price broke down
                    elif tf_dir == "SHORT" and len(closes) >= 10:
                        recent_pivot_high = max(closes[-10:])
                        if current > recent_pivot_high * 1.01:
                            tf_dir = "NEUTRAL"

            # Fallback: EMA9/EMA21 alignment
            if tf_dir == "NEUTRAL" and len(closes) >= 21:
                ema9  = self.analyzer.calculate_ema(closes, 9)
                ema21 = self.analyzer.calculate_ema(closes, 21)
                if ema9 > ema21 * 1.001:
                    tf_dir = "LONG"
                elif ema9 < ema21 * 0.999:
                    tf_dir = "SHORT"

            # Bonus: EMA200 major trend filter
            major_trend = "NEUTRAL"
            if len(closes) >= 50:
                ema200 = self.analyzer.calculate_ema(closes, min(200, len(closes)))
                if current > ema200 * 1.005:
                    major_trend = "LONG"
                elif current < ema200 * 0.995:
                    major_trend = "SHORT"

            details.append(f"{tf_name}:{tf_dir}(major:{major_trend})")

            if direction and tf_dir == direction:
                aligned += 1

        detail_str = " | ".join(details)

        if aligned >= 3:
            return True, 20, f"All 3 TF aligned ✅ {detail_str}"
        elif aligned == 2:
            return True, 12, f"2/3 TF aligned {detail_str}"
        elif aligned == 1:
            return False, 4, f"1/3 TF aligned {detail_str}"
        return False, 0, f"No TF aligned {detail_str}"

    def _check_volume_on_structure(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        """
        ISSUE 10 FIX: Find the actual BOS/CHoCH candle and check ITS volume

        Method:
        1. Detect structure
        2. Find the candle where BOS happened (swing high/low break)
        3. Check if THAT candle's volume > 1.5x 20-period average
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 25:
            return True, 5, "Insufficient data — neutral"

        struct = self.structure.detect(ohlcv)
        if not struct.bos_detected and not struct.choch_detected:
            return True, 5, "No BOS/CHoCH — check skipped"

        volumes = [float(c[5]) for c in ohlcv]
        closes  = [float(c[4]) for c in ohlcv]
        highs   = [float(c[2]) for c in ohlcv]
        lows    = [float(c[3]) for c in ohlcv]

        avg_vol = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else sum(volumes[:-1]) / max(len(volumes)-1, 1)

        # ISSUE 10 FIX: Find BOS candle — look back 5 candles for the swing break
        bos_candle_idx = -1
        lookback = min(5, len(ohlcv) - 1)

        if direction == "LONG" or struct.direction == "LONG":
            # BOS up: candle that broke above recent swing high
            swing_high = max(highs[-20:-lookback]) if len(highs) >= 20 else max(highs[:-lookback])
            for i in range(-lookback, 0):
                if closes[i] > swing_high and volumes[i] == max(volumes[-lookback:]):
                    bos_candle_idx = i
                    break
        else:
            # BOS down
            swing_low = min(lows[-20:-lookback]) if len(lows) >= 20 else min(lows[:-lookback])
            for i in range(-lookback, 0):
                if closes[i] < swing_low and volumes[i] == max(volumes[-lookback:]):
                    bos_candle_idx = i
                    break

        # Use BOS candle volume if found, else last candle
        bos_vol = volumes[bos_candle_idx] if bos_candle_idx != -1 else volumes[-1]
        vol_ratio = bos_vol / avg_vol if avg_vol > 0 else 1.0

        structure_type = "CHoCH" if struct.choch_detected else "BOS"
        candle_info = f"candle[{bos_candle_idx}]" if bos_candle_idx != -1 else "last"

        if vol_ratio >= 1.5:
            return True, 10, f"{structure_type} confirmed: {candle_info} vol {vol_ratio:.1f}x avg ✅"
        elif vol_ratio >= 1.0:
            return True, 6,  f"{structure_type} weak vol: {candle_info} {vol_ratio:.1f}x — caution"
        else:
            return False, 0, f"{structure_type} NO volume: {candle_info} {vol_ratio:.1f}x — false break ❌"

    def _check_sentiment_score(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        """
        ISSUE 11 FIX: ROC used in scoring
        RECOVERY + LONG → bonus points
        FALLING_FAST → penalty even if neutral
        """
        try:
            result = self.sentiment_analyzer.analyze(data.get("sentiment"))
            base = self.sentiment_analyzer.get_sentiment_score(result, direction)
            fg = result.fear_greed_value
            roc = result.rate_of_change
            label = result.fear_greed_label.replace("_", " ")
            change = result.fear_greed_change

            # ISSUE 11 FIX: ROC adjustments
            if roc == "FALLING_FAST" and base > 0:
                base = max(0, base - 4)  # penalty
            elif roc == "RISING_FAST" and direction == "LONG":
                base = min(15, base + 2)  # momentum bonus

            # RECOVERY mood bonus
            if result.market_mood == MarketMood.RECOVERY and direction == "LONG":
                base = min(15, base + 2)

            # Structure alignment bonus
            ohlcv = data.get("ohlcv", {}).get("15m", [])
            if len(ohlcv) >= 30 and base >= 8:
                struct = self.structure.detect(ohlcv)
                if struct.strength != "WEAK" and struct.direction == direction:
                    base = min(15, base + 3)

            mood_str = result.market_mood.value
            roc_str = f" {roc}(Δ{change:+d})" if roc != "STABLE" else ""

            if base >= 8:
                return True, base, f"✅ {mood_str}: {label}({fg}){roc_str}, Alt={result.alt_season_index}"
            elif base > 0:
                return True, base, f"{mood_str}: {label}({fg}){roc_str}"
            return False, 0, f"❌ Sentiment vs {direction}: {label}({fg}){roc_str}"

        except Exception as e:
            logger.warning(f"Tier2 sentiment error: {e}")
            return True, 5, "Sentiment skipped"

    def _check_volume_profile(self, data: Dict) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"
        current_price = float(ohlcv[-1][4])
        vp = self.volume.analyze(ohlcv)
        if self.volume.is_price_in_value_area(current_price, vp):
            return True, 15, f"In value area (POC: {vp.poc:.4f})"
        pos = self.volume.get_value_area_position(current_price, vp)
        return True, 10, f"{pos}, near key level"

    def _check_funding_rate(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        funding_pct = data.get("funding_rate", 0) * 100
        if abs(funding_pct) > 0.01:
            if direction == "LONG" and funding_pct > 0:
                return False, 0, f"High positive funding ({funding_pct:.3f}%)"
            if direction == "SHORT" and funding_pct < 0:
                return False, 0, f"High negative funding ({funding_pct:.3f}%)"
            return True, 10, f"Funding supports trade ({funding_pct:.3f}%)"
        return True, 10, f"Funding neutral ({funding_pct:.3f}%)"

    def _check_open_interest(self, data: Dict) -> Tuple[bool, int, str]:
        oi = data.get("open_interest", {})
        if not oi:
            return True, 5, "OI unavailable"
        oi_change = oi.get("change_pct", 0)
        if oi_change > 5:
            return True, 10, f"OI rising {oi_change:+.1f}%"
        elif oi_change < -5:
            return True, 6, f"OI falling {oi_change:+.1f}%"
        return True, 8, f"OI stable {oi_change:+.1f}%"

    def _check_rsi_divergence(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 30:
            return False, 0, "Insufficient data"
        closes = [float(c[4]) for c in ohlcv]
        rsi_series = []
        for i in range(15, len(closes)):
            rsi_series.append(self.analyzer.calculate_rsi(closes[:i+1]))
        if len(rsi_series) < 5:
            return False, 0, "Insufficient RSI"
        recent_c = closes[-10:]
        recent_r = rsi_series[-10:]
        bull_div = recent_c[-1] < min(recent_c[:-1]) and recent_r[-1] > min(recent_r[:-1])
        bear_div = recent_c[-1] > max(recent_c[:-1]) and recent_r[-1] < max(recent_r[:-1])
        cur_rsi  = recent_r[-1]
        if bull_div and direction == "LONG":
            return True, 15, f"Bullish RSI divergence ✅ (RSI:{cur_rsi:.1f})"
        if bear_div and direction == "SHORT":
            return True, 15, f"Bearish RSI divergence ✅ (RSI:{cur_rsi:.1f})"
        if bull_div or bear_div:
            return True, 8, f"RSI divergence (opposite dir) (RSI:{cur_rsi:.1f})"
        if direction == "LONG" and 50 < cur_rsi < 70:
            return True, 8, f"RSI bullish momentum ({cur_rsi:.1f})"
        if direction == "SHORT" and 30 < cur_rsi < 50:
            return True, 8, f"RSI bearish momentum ({cur_rsi:.1f})"
        return False, 3, f"No RSI divergence (RSI:{cur_rsi:.1f})"

    def _check_ema_stack(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 30:
            return False, 0, "Insufficient 1h data"
        closes = [float(c[4]) for c in ohlcv]
        ema9  = self.analyzer.calculate_ema(closes, 9)
        ema21 = self.analyzer.calculate_ema(closes, 21)
        ema200 = self.analyzer.calculate_ema(closes, min(200, len(closes)))
        bull = ema9 > ema21 > ema200
        bear = ema9 < ema21 < ema200
        if direction == "LONG" and bull:
            return True, 10, "Bullish EMA stack 9>21>200 ✅"
        if direction == "SHORT" and bear:
            return True, 10, "Bearish EMA stack 9<21<200 ✅"
        if bull or bear:
            return True, 5, "EMA stack opposite direction"
        return False, 2, "No EMA stack"

    def _check_atr_percent(self, data: Dict) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 14:
            return False, 0, "Insufficient data"
        atr = self.analyzer.calculate_atr(ohlcv)
        price = float(ohlcv[-1][4])
        atr_pct = (atr / price * 100) if price > 0 else 0
        if config.MIN_ATR_PCT <= atr_pct <= config.MAX_ATR_PCT:
            return True, 10, f"ATR {atr_pct:.2f}% in range"
        if atr_pct < config.MIN_ATR_PCT:
            return False, 5, f"ATR too low: {atr_pct:.2f}%"
        return False, 5, f"ATR too high: {atr_pct:.2f}%"

    def _check_vwap_position(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 10:
            return False, 0, "Insufficient data"
        vwap = self.analyzer.calculate_vwap(ohlcv)
        price = float(ohlcv[-1][4])
        if direction == "LONG" and price > vwap:
            return True, 5, f"Above VWAP {vwap:.4f} ✅"
        if direction == "SHORT" and price < vwap:
            return True, 5, f"Below VWAP {vwap:.4f} ✅"
        if abs(price - vwap) / vwap < 0.002:
            return True, 3, f"At VWAP {vwap:.4f}"
        return False, 1, f"Wrong side of VWAP {vwap:.4f}"

    def _check_support_resistance(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 30:
            return False, 0, "Insufficient data"
        price = float(ohlcv[-1][4])
        levels = self.structure.get_support_resistance(ohlcv, num_levels=5)
        supports    = [s for s in levels.get("support", []) if s < price]
        resistances = [r for r in levels.get("resistance", []) if r > price]
        if direction == "LONG" and supports:
            ns = max(supports)
            dist = (price - ns) / price * 100
            return True, (5 if dist < 1.0 else 3), f"Support {ns:.4f} ({dist:.2f}% away)"
        if direction == "SHORT" and resistances:
            nr = min(resistances)
            dist = (nr - price) / price * 100
            return True, (5 if dist < 1.0 else 3), f"Resistance {nr:.4f} ({dist:.2f}% away)"
        return False, 1, "No nearby S/R"
