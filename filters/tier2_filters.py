"""
ARUNABHA ALGO BOT - Tier 2 Filters v6.0
=========================================
NEW FILTERS:
- anchored_vwap: Session + Weekly + Event VWAP confluence (replaces weak vwap_position)
- orderflow_cvd: CVD divergence + absorption detection (replaces nothing — new slot)

EXISTING FIXED:
- MTF: structure-first, price action confirmed
- volume_on_structure: BOS candle volume check
- sentiment ROC used in scoring
"""

import logging
from typing import Dict, List, Tuple, Optional, Any

import config
from core.constants import MarketType
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from analysis.volume_profile import VolumeProfileAnalyzer
from analysis.sentiment import SentimentAnalyzer, MarketMood
from analysis.anchored_vwap import AnchoredVWAPAnalyzer
from analysis.orderflow import OrderflowAnalyzer
from analysis.amd import AMDDetector

logger = logging.getLogger(__name__)


class Tier2Filters:

    def __init__(self):
        self.analyzer  = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.volume    = VolumeProfileAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer()
        self.avwap     = AnchoredVWAPAnalyzer()
        self.orderflow = OrderflowAnalyzer()
        self.amd       = AMDDetector()
        self.weights   = config.TIER2_FILTERS

    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        market_type: MarketType,
        data: Dict[str, Any],
        threshold_override: Optional[float] = None,   # ✅ FIX BUG-7: adaptive threshold
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

        add("mtf_confirmation",    self._check_mtf,                    data, direction)
        add("volume_profile",      self._check_volume_profile,         data)
        add("funding_rate",        self._check_funding_rate,           data, direction)
        add("open_interest",       self._check_open_interest,          data)
        add("rsi_divergence",      self._check_rsi_divergence,         data, direction)
        add("ema_stack",           self._check_ema_stack,              data, direction)
        add("atr_percent",         self._check_atr_percent,            data)
        add("anchored_vwap",       self._check_anchored_vwap,          data, direction)
        add("support_resistance",  self._check_support_resistance,     data, direction)
        add("volume_on_structure", self._check_volume_on_structure,    data, direction)
        add("sentiment",           self._check_sentiment_score,        data, direction)
        add("orderflow_cvd",       self._check_orderflow_cvd,          data, direction)
        add("amd_phase",           self._check_amd_score,              data, direction)  # ← NEW v7.0

        percentage = (total_score / max_score * 100) if max_score > 0 else 0

        # ✅ FIX BUG-7: threshold_override (adaptive) actually ব্যবহার করো
        # আগে engine থেকে tier2_threshold_override pass হত filter_orchestrator-এ
        # কিন্তু tier2.evaluate_all() সেটা নিত না — সবসময় _get_threshold() ডাকত
        # এখন: threshold_override থাকলে সেটাই ব্যবহার হবে, না থাকলে market_type default
        if threshold_override is not None:
            threshold = float(threshold_override)
        else:
            threshold = self._get_threshold(market_type)

        passed = percentage >= threshold

        return passed, percentage, results

    def _get_threshold(self, market_type: MarketType) -> int:
        return {
            MarketType.TRENDING:  60,
            MarketType.CHOPPY:    55,
            MarketType.HIGH_VOL:  65,
            MarketType.UNKNOWN:   60
        }.get(market_type, 60)

    # ──────────────────────────────────────────────────────────────────
    # NEW: Anchored VWAP (replaces simple vwap_position)
    # ──────────────────────────────────────────────────────────────────

    def _check_anchored_vwap(
        self, data: Dict, direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """
        3-layer VWAP confluence: Session + Weekly + Event (BOS-anchored)

        Score:
          3 VWAPs agree with direction → 10 pts (max)
          2 VWAPs agree               → 7 pts
          1 VWAP agrees               → 4 pts
          AT session VWAP (±0.3%)     → 5 pts (best entry zone)
          All VWAP against            → 0 pts
        """
        ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv_15m) < 20:
            return False, 0, "Insufficient data for AVWAP"

        try:
            # BOS index from structure if available
            bos_idx = None
            struct = self.structure.detect(ohlcv_15m)
            if struct.bos_detected and hasattr(struct, "bos_candle_idx"):
                bos_idx = struct.bos_candle_idx

            result = self.avwap.analyze(ohlcv_15m, bos_idx=bos_idx)
            current_price = float(ohlcv_15m[-1][4])

            # AT session VWAP = best entry (institution sitting there)
            if result.price_vs_session == "AT":
                return True, 5, (
                    f"AT Session VWAP {result.session_vwap:.4f} "
                    f"(±{abs(result.deviation_pct['session']):.2f}%) ✅"
                )

            # Confluence score
            vwap_score = result.confluence_score  # 0–3
            vwap_dir   = result.confluence_direction

            if direction and vwap_dir == direction:
                score = {3: 10, 2: 7, 1: 4, 0: 0}.get(vwap_score, 0)
                ev_note = (
                    f" | Event VWAP={result.event_vwap:.4f}"
                    if result.event_vwap else ""
                )
                return (score >= 4), score, (
                    f"{vwap_score}/3 VWAPs aligned {direction} "
                    f"(S={result.session_vwap:.4f} W={result.weekly_vwap:.4f}"
                    f"{ev_note}) {'✅' if score >= 7 else ''}"
                )
            elif vwap_dir == "MIXED":
                return True, 3, (
                    f"VWAP mixed (S={result.price_vs_session} "
                    f"W={result.price_vs_weekly})"
                )
            else:
                return False, 0, (
                    f"All VWAPs against {direction}: "
                    f"S={result.price_vs_session} W={result.price_vs_weekly}"
                )

        except Exception as e:
            logger.warning(f"Anchored VWAP error: {e}")
            # Fallback: basic VWAP
            ohlcv = data.get("ohlcv", {}).get("15m", [])
            if len(ohlcv) < 10:
                return False, 0, "AVWAP failed + no fallback"
            vwap = self.analyzer.calculate_vwap(ohlcv)
            price = float(ohlcv[-1][4])
            if direction == "LONG" and price > vwap:
                return True, 4, f"Fallback VWAP: above {vwap:.4f}"
            if direction == "SHORT" and price < vwap:
                return True, 4, f"Fallback VWAP: below {vwap:.4f}"
            return False, 1, f"Fallback VWAP: wrong side {vwap:.4f}"

    # ──────────────────────────────────────────────────────────────────
    # NEW: Orderflow / CVD
    # ──────────────────────────────────────────────────────────────────

    def _check_orderflow_cvd(
        self, data: Dict, direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """
        CVD (Cumulative Volume Delta) analysis.

        Scoring (max 12 pts):
          CVD rising + LONG direction   → +3
          CVD falling + SHORT direction → +3
          Bullish/Bearish divergence    → +3 (STRONG) or +2 (MODERATE)
          Absorption detected           → +2
          Buy/Sell pressure aligned     → +2
          CVD against direction         → 0

        Why this matters:
          If price is rising but CVD falling → sellers absorbing →
          likely reversal → avoid LONG signal
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 15:
            return True, 5, "Insufficient data for CVD — neutral"

        try:
            result = self.orderflow.analyze(ohlcv, period=20)
            score, msg = self.orderflow.get_signal_bias(result, direction or "LONG")

            # Penalize opposite CVD (weak signal)
            if direction == "LONG" and result.cvd_direction == "FALLING":
                score = max(0, score - 2)
                msg = f"⚠️ CVD falling vs LONG | {msg}"
            elif direction == "SHORT" and result.cvd_direction == "RISING":
                score = max(0, score - 2)
                msg = f"⚠️ CVD rising vs SHORT | {msg}"

            passed = score >= 3
            return passed, min(score, 12), msg

        except Exception as e:
            logger.warning(f"Orderflow CVD error: {e}")
            return True, 4, "CVD check failed — neutral"

    # ──────────────────────────────────────────────────────────────────
    # Existing filters (unchanged from v5.0)
    # ──────────────────────────────────────────────────────────────────

    def _check_mtf(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
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

            closes  = [float(c[4]) for c in ohlcv]
            current = closes[-1]
            tf_dir  = "NEUTRAL"

            if len(ohlcv) >= 30:
                struct = self.structure.detect(ohlcv)
                if struct.strength in ("STRONG", "MODERATE"):
                    tf_dir = struct.direction
                    if tf_dir == "LONG" and len(closes) >= 10:
                        if current < min(closes[-10:]) * 0.99:
                            tf_dir = "NEUTRAL"
                    elif tf_dir == "SHORT" and len(closes) >= 10:
                        if current > max(closes[-10:]) * 1.01:
                            tf_dir = "NEUTRAL"

            if tf_dir == "NEUTRAL" and len(closes) >= 21:
                ema9  = self.analyzer.calculate_ema(closes, 9)
                ema21 = self.analyzer.calculate_ema(closes, 21)
                if ema9 > ema21 * 1.001:
                    tf_dir = "LONG"
                elif ema9 < ema21 * 0.999:
                    tf_dir = "SHORT"

            major_trend = "NEUTRAL"
            if len(closes) >= 50:
                ema200 = self.analyzer.calculate_ema(closes, min(200, len(closes)))
                if current > ema200 * 1.005:
                    major_trend = "LONG"
                elif current < ema200 * 0.995:
                    major_trend = "SHORT"

            details.append(f"{tf_name}:{tf_dir}(M:{major_trend})")
            if direction and tf_dir == direction:
                aligned += 1

        detail_str = " | ".join(details)
        if aligned >= 3:
            return True, 20, f"All 3 TF aligned ✅ {detail_str}"
        elif aligned == 2:
            return True, 12, f"2/3 TF {detail_str}"
        elif aligned == 1:
            return False, 4, f"1/3 TF {detail_str}"
        return False, 0, f"No TF aligned {detail_str}"

    def _check_volume_on_structure(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
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
        avg_vol = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else sum(volumes[:-1]) / max(len(volumes)-1,1)
        lookback = min(5, len(ohlcv)-1)
        bos_candle_idx = -1
        if direction == "LONG" or struct.direction == "LONG":
            swing_high = max(highs[-20:-lookback]) if len(highs) >= 20 else max(highs[:-lookback])
            for i in range(-lookback, 0):
                if closes[i] > swing_high and volumes[i] == max(volumes[-lookback:]):
                    bos_candle_idx = i; break
        else:
            swing_low = min(lows[-20:-lookback]) if len(lows) >= 20 else min(lows[:-lookback])
            for i in range(-lookback, 0):
                if closes[i] < swing_low and volumes[i] == max(volumes[-lookback:]):
                    bos_candle_idx = i; break
        bos_vol   = volumes[bos_candle_idx] if bos_candle_idx != -1 else volumes[-1]
        vol_ratio = bos_vol / avg_vol if avg_vol > 0 else 1.0
        stype = "CHoCH" if struct.choch_detected else "BOS"
        if vol_ratio >= 1.5:
            return True, 10, f"{stype} confirmed {vol_ratio:.1f}x avg ✅"
        elif vol_ratio >= 1.0:
            return True, 6,  f"{stype} weak vol {vol_ratio:.1f}x"
        return False, 0, f"{stype} NO volume {vol_ratio:.1f}x ❌"

    def _check_sentiment_score(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        try:
            result = self.sentiment_analyzer.analyze(data.get("sentiment"))
            base = self.sentiment_analyzer.get_sentiment_score(result, direction)
            roc = result.rate_of_change; change = result.fear_greed_change
            fg  = result.fear_greed_value; label = result.fear_greed_label.replace("_"," ")
            if roc == "FALLING_FAST" and base > 0:
                base = max(0, base - 4)
            elif roc == "RISING_FAST" and direction == "LONG":
                base = min(15, base + 2)
            if result.market_mood == MarketMood.RECOVERY and direction == "LONG":
                base = min(15, base + 2)
            ohlcv = data.get("ohlcv",{}).get("15m",[])
            if len(ohlcv) >= 30 and base >= 8:
                struct = self.structure.detect(ohlcv)
                if struct.strength != "WEAK" and struct.direction == direction:
                    base = min(15, base + 3)
            roc_str = f" {roc}(Δ{change:+d})" if roc != "STABLE" else ""
            if base >= 8:
                return True, base, f"✅ {result.market_mood.value}: {label}({fg}){roc_str}"
            elif base > 0:
                return True, base, f"{result.market_mood.value}: {label}({fg}){roc_str}"
            return False, 0, f"❌ Sentiment vs {direction}: {label}({fg}){roc_str}"
        except Exception as e:
            logger.warning(f"Tier2 sentiment error: {e}")
            return True, 5, "Sentiment skipped"

    def _check_volume_profile(self, data: Dict) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv",{}).get("15m",[])
        if len(ohlcv) < 20: return False, 0, "Insufficient data"
        price = float(ohlcv[-1][4])
        vp = self.volume.analyze(ohlcv)
        if self.volume.is_price_in_value_area(price, vp):
            return True, 15, f"In value area (POC:{vp.poc:.4f})"
        pos = self.volume.get_value_area_position(price, vp)
        return True, 10, f"{pos}, near key level"

    def _check_funding_rate(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        fp = data.get("funding_rate", 0) * 100
        if abs(fp) > 0.01:
            if direction == "LONG" and fp > 0: return False, 0, f"High positive funding ({fp:.3f}%)"
            if direction == "SHORT" and fp < 0: return False, 0, f"High negative funding ({fp:.3f}%)"
            return True, 10, f"Funding supports trade ({fp:.3f}%)"
        return True, 10, f"Funding neutral ({fp:.3f}%)"

    def _check_open_interest(self, data: Dict) -> Tuple[bool, int, str]:
        oi = data.get("open_interest", {})
        if not oi: return True, 5, "OI unavailable"
        oc = oi.get("change_pct", 0)
        if oc > 5:  return True, 10, f"OI rising {oc:+.1f}%"
        if oc < -5: return True, 6, f"OI falling {oc:+.1f}%"
        return True, 8, f"OI stable {oc:+.1f}%"

    def _check_rsi_divergence(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv",{}).get("15m",[])
        if len(ohlcv) < 30: return False, 0, "Insufficient data"
        closes = [float(c[4]) for c in ohlcv]
        rsi_series = [self.analyzer.calculate_rsi(closes[:i+1]) for i in range(15, len(closes))]
        if len(rsi_series) < 5: return False, 0, "Insufficient RSI"
        rc = closes[-10:]; rr = rsi_series[-10:]
        bull_div = rc[-1] < min(rc[:-1]) and rr[-1] > min(rr[:-1])
        bear_div = rc[-1] > max(rc[:-1]) and rr[-1] < max(rr[:-1])
        cur_rsi  = rr[-1]
        if bull_div and direction == "LONG":  return True, 15, f"Bullish RSI div ✅ ({cur_rsi:.1f})"
        if bear_div and direction == "SHORT": return True, 15, f"Bearish RSI div ✅ ({cur_rsi:.1f})"
        if bull_div or bear_div:              return True, 8, f"RSI div (opposite) ({cur_rsi:.1f})"
        if direction == "LONG" and 50 < cur_rsi < 70:  return True, 8, f"RSI bull momentum ({cur_rsi:.1f})"
        if direction == "SHORT" and 30 < cur_rsi < 50: return True, 8, f"RSI bear momentum ({cur_rsi:.1f})"
        return False, 3, f"No RSI div ({cur_rsi:.1f})"

    def _check_ema_stack(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv",{}).get("1h",[])
        if len(ohlcv) < 30: return False, 0, "Insufficient 1h data"
        closes = [float(c[4]) for c in ohlcv]
        ema9   = self.analyzer.calculate_ema(closes, 9)
        ema21  = self.analyzer.calculate_ema(closes, 21)
        ema200 = self.analyzer.calculate_ema(closes, min(200, len(closes)))
        bull = ema9 > ema21 > ema200; bear = ema9 < ema21 < ema200
        if direction == "LONG"  and bull: return True, 10, "Bullish EMA stack 9>21>200 ✅"
        if direction == "SHORT" and bear: return True, 10, "Bearish EMA stack 9<21<200 ✅"
        if bull or bear:                  return True, 5, "EMA stack opposite"
        return False, 2, "No EMA stack"

    def _check_atr_percent(self, data: Dict) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv",{}).get("15m",[])
        if len(ohlcv) < 14: return False, 0, "Insufficient data"
        atr = self.analyzer.calculate_atr(ohlcv)
        price = float(ohlcv[-1][4])
        atr_pct = (atr / price * 100) if price > 0 else 0
        if config.MIN_ATR_PCT <= atr_pct <= config.MAX_ATR_PCT:
            return True, 10, f"ATR {atr_pct:.2f}% in range"
        if atr_pct < config.MIN_ATR_PCT: return False, 5, f"ATR too low: {atr_pct:.2f}%"
        return False, 5, f"ATR too high: {atr_pct:.2f}%"

    def _check_support_resistance(self, data: Dict, direction: Optional[str]) -> Tuple[bool, int, str]:
        ohlcv = data.get("ohlcv",{}).get("15m",[])
        if len(ohlcv) < 30: return False, 0, "Insufficient data"
        price  = float(ohlcv[-1][4])
        levels = self.structure.get_support_resistance(ohlcv, num_levels=5)
        supports    = [s for s in levels.get("support",[]) if s < price]
        resistances = [r for r in levels.get("resistance",[]) if r > price]
        if direction == "LONG" and supports:
            ns = max(supports); dist = (price-ns)/price*100
            return True, (5 if dist < 1.0 else 3), f"Support {ns:.4f} ({dist:.2f}% away)"
        if direction == "SHORT" and resistances:
            nr = min(resistances); dist = (nr-price)/price*100
            return True, (5 if dist < 1.0 else 3), f"Resistance {nr:.4f} ({dist:.2f}% away)"
        return False, 1, "No nearby S/R"

    # ──────────────────────────────────────────────────────────────────
    # NEW v7.0: AMD Phase Score
    # ──────────────────────────────────────────────────────────────────

    def _check_amd_score(
        self, data: Dict, direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """
        AMD phase scoring for Tier2.

        Post-manipulation + direction match → highest score (15)
        Distribution active + direction match → good score (10-12)
        Manipulation detected → moderate (8)
        Unknown/no signal → neutral (5)
        Accumulation (shouldn't reach here, blocked in Tier1) → 0
        Session AMD valid adds +2 bonus

        Max: 15 points
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 30:
            return True, 5, "Insufficient data — AMD neutral"

        try:
            from datetime import datetime
            import pytz
            now      = datetime.now(pytz.timezone("Asia/Kolkata"))
            hour_ist = now.hour
        except Exception:
            hour_ist = None

        try:
            result = self.amd.analyze(ohlcv, direction=direction, session_hour_ist=hour_ist)
            score  = 0
            msg    = ""

            # Accumulation = bad (Tier1 should have blocked, but score 0 here too)
            if result.phase == "ACCUMULATION":
                return False, 0, f"AMD: Accumulation phase — no edge"

            # Post-manipulation = best setup
            if result.post_manipulation:
                dir_match = (
                    (direction == "LONG"  and result.manipulation_direction == "BEAR_SWEEP") or
                    (direction == "SHORT" and result.manipulation_direction == "BULL_SWEEP") or
                    direction is None
                )
                score = 15 if dir_match else 6
                msg   = (
                    f"Post-manipulation {result.manipulation_direction} "
                    f"({'direction match' if dir_match else 'direction mismatch'})"
                )

            # Distribution active
            elif result.distribution_active:
                dir_match = (
                    direction is None or
                    result.distribution_direction == direction
                )
                if result.distribution_strength == "STRONG" and dir_match:
                    score = 12
                elif dir_match:
                    score = 10
                else:
                    score = 4
                msg = (
                    f"Distribution {result.distribution_direction} "
                    f"({result.distribution_strength}, vol {result.momentum_ratio:.1f}x)"
                )

            # Manipulation in progress
            elif result.manipulation_detected:
                score = 8
                msg   = f"Manipulation detected ({result.manipulation_direction})"

            # AMD score from signal
            else:
                score = min(result.amd_score, 7)
                msg   = f"AMD phase={result.phase} score={result.amd_score}/10"

            # Session bonus
            if result.session_amd_valid:
                score = min(15, score + 2)
                msg  += f" | Session={result.session_phase} ✓"

            # FVG near price adds confidence
            if result.nearest_fvg and not result.nearest_fvg.filled:
                fvg = result.nearest_fvg
                msg += f" | FVG {fvg.direction} {fvg.gap_pct:.2f}%"
                score = min(15, score + 1)

            return score >= 5, score, msg

        except Exception as e:
            logger.warning(f"AMD score error: {e}")
            return True, 5, f"AMD error — neutral (5)"
