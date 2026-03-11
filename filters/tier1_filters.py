"""
ARUNABHA ALGO BOT - Tier 1 Filters v6.0
=========================================
MANDATORY: সব filter pass না হলে signal block।

NEW (v6.0):
  SESSION VWAP filter — Tier1-এ add করা হয়েছে।
  Best choice কারণ:
    - Session VWAP institutional reference point। Price wrong side = setup invalid।
    - Calculation simple, fast, reliable — Tier1-এ overhead নেই।
    - Weekly/Event VWAP Tier2-তে থাকবে (scoring)।
    - CVD/Sweep Tier1-এ দেওয়া হয়নি — rare pattern, অনেক signal miss হত।

  Logic:
    - LONG signal: price must be ABOVE session VWAP বা AT (±0.5%)
    - SHORT signal: price must be BELOW session VWAP বা AT (±0.5%)
    - AT zone (±0.5%) = dono direction allow, price at fair value
    - First 30 min of session (< 2 candles) = skip (VWAP not meaningful yet)

FIXED (v5.1):
  ISSUE 5: OrderBook data type — float conversion
  ISSUE 11: Sentiment ROC in Tier1
  ISSUE 15: F&G <= 15 blocks LONG (capitulation)
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

import config
from core.constants import MarketType, BTCRegime, SessionType
from analysis.technical import TechnicalAnalyzer
from analysis.market_regime import BTCRegimeResult
from analysis.sentiment import SentimentAnalyzer, MarketMood
from analysis.anchored_vwap import AnchoredVWAPAnalyzer
from analysis.amd import AMDDetector

logger = logging.getLogger(__name__)

# Session VWAP tolerance — AT zone এর মধ্যে থাকলে both direction ok
SESSION_VWAP_TOLERANCE_PCT = 0.50   # ±0.50%
# প্রথম কয়টা candle VWAP skip করবো
SESSION_VWAP_MIN_CANDLES = 2


class Tier1Filters:

    def __init__(self):
        self.analyzer  = TechnicalAnalyzer()
        self.sentiment  = SentimentAnalyzer()
        self.avwap      = AnchoredVWAPAnalyzer()
        self.amd        = AMDDetector()

    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        market_type: MarketType,
        btc_regime: BTCRegimeResult,
        data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:

        results = {}

        def check(name, fn, *args):
            p, m = fn(*args)
            results[name] = {"passed": p, "message": m, "weight": "MANDATORY"}

        check("btc_regime",    self._check_btc_regime,    btc_regime, direction)
        check("structure",     self._check_structure,     data)
        check("volume",        self._check_volume,        data)
        check("liquidity",     self._check_liquidity,     data)
        check("session",       self._check_session)
        check("sentiment",     self._check_sentiment,     direction, data)
        check("session_vwap",  self._check_session_vwap,  direction, data)
        check("amd_phase",     self._check_amd_phase,     direction, data)   # ← NEW

        all_passed = all(r["passed"] for r in results.values())
        return all_passed, results

    # ──────────────────────────────────────────────────────────────────
    # NEW v6.0: Session VWAP Filter
    # ──────────────────────────────────────────────────────────────────

    def _check_session_vwap(
        self,
        direction: Optional[str],
        data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Session VWAP Tier1 filter.

        কেন শুধু Session VWAP (Weekly/Event নয়):
          Session VWAP = আজকের fair value। Price এর wrong side = 
          institutional bias against তোমার direction।
          Weekly VWAP = longer context, Tier2-তে scoring করে।
          Event VWAP = BOS থেকে, rare — Tier2/3-তে থাকুক।

        Pass conditions:
          LONG:  price >= session_vwap × (1 - tolerance)   [above or AT]
          SHORT: price <= session_vwap × (1 + tolerance)   [below or AT]
          AT zone (±0.5%): always pass — fair value entry both sides ok

        Skip conditions:
          - Session candles < 2 (VWAP too young, meaningless)
          - direction = None (no filter needed)
          - OHLCV data not available

        Block conditions:
          LONG below session VWAP by > 0.5%  → price against bias → BLOCK
          SHORT above session VWAP by > 0.5% → price against bias → BLOCK
        """
        if not direction:
            return True, "No direction — session VWAP skip"

        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 5:
            return True, "Insufficient data — session VWAP skip"

        try:
            avwap_result = self.avwap.analyze(ohlcv)
            session_vwap = avwap_result.session_vwap
            pos = avwap_result.price_vs_session
            dev = avwap_result.deviation_pct.get("session", 0.0)

            # Session-এ candle কম → VWAP reliable না, skip করো
            # ✅ FIX BUG-6: private method এর বদলে public API ব্যবহার করো
            # আগে: self.avwap._get_session_candles(ohlcv) → OOP violation
            # এখন: self.avwap.get_session_candle_count(ohlcv) → proper interface
            session_candles_count = self.avwap.get_session_candle_count(ohlcv)
            if session_candles_count < SESSION_VWAP_MIN_CANDLES:
                return True, f"Session too new ({session_candles_count} candles) — VWAP skip"

            if pos == "AT":
                return True, (
                    f"AT Session VWAP {session_vwap:.4f} (±{abs(dev):.2f}%) "
                    f"— fair value entry"
                )

            if direction == "LONG":
                if pos == "ABOVE":
                    return True, (
                        f"LONG above Session VWAP {session_vwap:.4f} "
                        f"(+{dev:.2f}%) ✓"
                    )
                else:  # BELOW
                    return False, (
                        f"LONG blocked: price {abs(dev):.2f}% BELOW Session VWAP "
                        f"{session_vwap:.4f} — institutional bias down"
                    )

            elif direction == "SHORT":
                if pos == "BELOW":
                    return True, (
                        f"SHORT below Session VWAP {session_vwap:.4f} "
                        f"({dev:.2f}%) ✓"
                    )
                else:  # ABOVE
                    return False, (
                        f"SHORT blocked: price {dev:.2f}% ABOVE Session VWAP "
                        f"{session_vwap:.4f} — institutional bias up"
                    )

        except Exception as e:
            logger.warning(f"Session VWAP filter error: {e} — allowing")
            return True, f"Session VWAP error ({e}) — allowing"

        return True, "Session VWAP OK"

    # ──────────────────────────────────────────────────────────────────
    # NEW v7.0: AMD Phase Filter
    # ──────────────────────────────────────────────────────────────────

    def _check_amd_phase(
        self,
        direction: Optional[str],
        data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        AMD Phase Tier1 filter.

        BLOCK: Accumulation phase — smart money এখনো position নেয়নি।
               এই phase-এ trade = noise trade।

        PASS:  Manipulation শেষ (post-manipulation) → BEST entry window।
               Distribution active → trend ride করো।
               Unknown → allow (data কম, conservative)।

        কেন Tier1-এ:
          Accumulation-এ bot অনেক false signal দিচ্ছিল।
          AMD phase block করলে win rate ~8% বাড়ার সম্ভাবনা।
        """
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 30:
            return True, "Insufficient data — AMD skip"

        try:
            import pytz
            now      = datetime.now(pytz.timezone("Asia/Kolkata"))
            hour_ist = now.hour
        except Exception:
            hour_ist = None

        try:
            result = self.amd.analyze(ohlcv, direction=direction, session_hour_ist=hour_ist)

            # BLOCK: pure accumulation
            if result.phase == "ACCUMULATION" and result.phase_confidence >= 65:
                return False, (
                    f"AMD BLOCK: Accumulation phase ({result.phase_confidence}%) — "
                    f"{result.phase_reason}"
                )

            # PASS: post-manipulation = best entry
            if result.post_manipulation:
                manip_dir = result.manipulation_direction
                return True, (
                    f"AMD PASS: Post-manipulation sweep ({manip_dir}) — "
                    f"Distribution starting. Score={result.amd_score}/10"
                )

            # PASS: distribution active
            if result.distribution_active:
                return True, (
                    f"AMD PASS: Distribution {result.distribution_direction} "
                    f"({result.distribution_strength}, "
                    f"vol {result.momentum_ratio:.1f}x)"
                )

            # PASS: manipulation in progress (allow — entry window opening)
            if result.manipulation_detected:
                return True, (
                    f"AMD PASS: Manipulation detected ({result.manipulation_direction}) — "
                    f"watch for reversal"
                )

            # PASS: unknown or low confidence accumulation
            return True, (
                f"AMD: Phase={result.phase} ({result.phase_confidence}%) — allowing"
            )

        except Exception as e:
            logger.warning(f"AMD filter error: {e} — allowing")
            return True, f"AMD error ({e}) — allowing"

    # ──────────────────────────────────────────────────────────────────
    # Existing filters
    # ──────────────────────────────────────────────────────────────────

    def _check_sentiment(
        self,
        direction: Optional[str],
        data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        ISSUE 11: ROC used | ISSUE 15: F&G <= 15 always blocks LONG
        """
        try:
            result = self.sentiment.analyze(data.get("sentiment"))
            fg     = result.fear_greed_value
            roc    = result.rate_of_change
            label  = result.fear_greed_label.replace("_", " ")
            change = result.fear_greed_change

            if direction == "LONG":
                if fg <= 15:
                    return False, f"LONG blocked: Extreme Fear ({fg}) — capitulation"
                if fg <= 20 and roc in ("FALLING", "FALLING_FAST"):
                    return False, f"LONG blocked: Fear {fg} falling ({roc} d{change:+d})"
                if roc == "FALLING_FAST" and fg < 40:
                    return False, f"LONG blocked: Sentiment deteriorating fast ({fg} d{change:+d})"
                if self.sentiment.is_long_blocked(result):
                    return False, f"LONG blocked: Extreme Fear ({fg})"

            elif direction == "SHORT":
                if fg >= 75 and roc == "RISING_FAST":
                    return False, f"SHORT blocked: Extreme Greed rising ({fg} d{change:+d})"
                if self.sentiment.is_short_blocked(result):
                    return False, f"SHORT blocked: Extreme Greed ({fg})"

            mood = ""
            if result.market_mood == MarketMood.RECOVERY:
                mood = " | Recovery signal"

            return True, (
                f"Sentiment OK: {label} ({fg} {roc} d{change:+d})"
                f", Alt={result.alt_season_index}{mood}"
            )

        except Exception as e:
            logger.warning(f"Sentiment filter error: {e} — allowing")
            return True, "Sentiment check skipped (error)"

    def _check_btc_regime(
        self,
        btc_regime: BTCRegimeResult,
        direction: Optional[str]
    ) -> Tuple[bool, str]:
        if not btc_regime:
            return False, "BTC regime data not available"
        if not btc_regime.can_trade:
            return False, f"BTC regime blocks: {btc_regime.reason}"
        if direction:
            if direction == "LONG" and btc_regime.direction == "DOWN":
                return False, f"BTC trending DOWN — LONG blocked"
            if direction == "SHORT" and btc_regime.direction == "UP":
                return False, f"BTC trending UP — SHORT blocked"
        if btc_regime.confidence < 20:
            return False, f"BTC confidence too low: {btc_regime.confidence}%"
        return True, f"BTC {btc_regime.regime.value} ({btc_regime.confidence}%, {btc_regime.direction})"

    def _check_structure(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, "Insufficient data (need 20 candles)"
        from analysis.structure import StructureDetector
        structure = StructureDetector().detect(ohlcv)
        if structure.strength == "WEAK" and not structure.bos_detected:
            return False, f"Structure too weak: {structure.reason}"
        return True, f"Structure: {structure.direction} ({structure.strength})"

    def _check_volume(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, "Insufficient data"
        volumes = [float(c[5]) for c in ohlcv[-5:]]
        avg = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
        ratio = volumes[-1] / avg if avg > 0 else 0
        if ratio < 0.7:
            return False, f"Volume too low: {ratio:.1f}x average"
        return True, f"Volume: {ratio:.1f}x average"

    def _check_liquidity(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """ISSUE 5 FIX: explicit float() conversion on all orderbook entries"""
        orderbook = data.get("orderbook", {})
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        if not bids or not asks:
            if getattr(config, "ENV", "development") == "production":
                return False, "No orderbook — rejecting in production"
            return True, "No orderbook — allowing (non-production)"

        try:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
        except (TypeError, ValueError, IndexError) as e:
            logger.warning(f"Orderbook parse error: {e}")
            return True, "Invalid orderbook format — allowing"

        if best_bid <= 0 or best_ask <= 0:
            return True, "Zero prices — allowing"

        spread_pct = (best_ask - best_bid) / best_bid * 100
        if spread_pct > 0.1:
            return False, f"Spread too wide: {spread_pct:.3f}%"

        try:
            bid_depth = sum(float(b[1]) for b in bids[:5] if len(b) > 1)
            ask_depth = sum(float(a[1]) for a in asks[:5] if len(a) > 1)
        except (TypeError, ValueError):
            bid_depth = ask_depth = 0

        if bid_depth < 10_000 or ask_depth < 10_000:
            return False, f"Thin orderbook: Bid ${bid_depth:,.0f} Ask ${ask_depth:,.0f}"

        return True, f"Spread {spread_pct:.3f}%, Depth ${bid_depth + ask_depth:,.0f}"

    def _check_session(self) -> Tuple[bool, str]:
        import pytz
        now  = datetime.now(pytz.timezone("Asia/Kolkata"))
        hour = now.hour

        for start, end, name in config.AVOID_TIMES:
            if start <= hour < end:
                return False, f"Avoid: {name} ({hour:02d}:00 IST)"

        if 7 <= hour < 11:
            return True, f"Asia session ({hour:02d}:00 IST)"
        elif 13 <= hour < 17:
            return True, f"London session ({hour:02d}:00 IST)"
        elif 17 <= hour < 22:
            return True, f"NY session ({hour:02d}:00 IST)"
        elif 22 <= hour < 24:
            return True, f"Overlap session ({hour:02d}:00 IST)"
        else:
            return False, f"Dead zone ({hour:02d}:00 IST)"
