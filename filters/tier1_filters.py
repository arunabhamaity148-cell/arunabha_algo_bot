"""
ARUNABHA ALGO BOT - Tier 1 Filters v5.0
=========================================
FIXES:
ISSUE 5:  OrderBook data type — float conversion + strict "no data" handling
ISSUE 15: Extreme Fear (<=15) block LONG — properly implemented
ISSUE 11: Sentiment ROC used in Tier1 (FALLING_FAST triggers earlier)
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

import config
from core.constants import MarketType, BTCRegime, SessionType
from analysis.technical import TechnicalAnalyzer
from analysis.market_regime import BTCRegimeResult
from analysis.sentiment import SentimentAnalyzer, MarketMood

logger = logging.getLogger(__name__)


class Tier1Filters:

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer()

    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        market_type: MarketType,
        btc_regime: BTCRegimeResult,
        data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:

        results = {}

        # F1: BTC Regime
        p, m = self._check_btc_regime(btc_regime, direction)
        results["btc_regime"] = {"passed": p, "message": m, "weight": "MANDATORY"}

        # F2: Structure
        p, m = self._check_structure(data)
        results["structure"] = {"passed": p, "message": m, "weight": "MANDATORY"}

        # F3: Volume
        p, m = self._check_volume(data)
        results["volume"] = {"passed": p, "message": m, "weight": "MANDATORY"}

        # F4: Liquidity (ISSUE 5 FIXED)
        p, m = self._check_liquidity(data)
        results["liquidity"] = {"passed": p, "message": m, "weight": "MANDATORY"}

        # F5: Session
        p, m = self._check_session()
        results["session"] = {"passed": p, "message": m, "weight": "MANDATORY"}

        # F6: Sentiment (ISSUE 11 + ISSUE 15 FIXED)
        p, m = self._check_sentiment(direction, data)
        results["sentiment"] = {"passed": p, "message": m, "weight": "MANDATORY"}

        all_passed = all(r["passed"] for r in results.values())
        return all_passed, results

    def _check_sentiment(
        self,
        direction: Optional[str],
        data: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        ISSUE 11 FIX: Sentiment ROC used in Tier1
        ISSUE 15 FIX: Extreme Fear (<=15) blocks LONG

        Logic:
        - F&G <= 15 → block LONG (extreme fear, worse than <=20)
        - F&G <= 20 AND falling → block LONG (panic accelerating)
        - F&G >= 80 AND rising → block SHORT (bubble accelerating)
        - FALLING_FAST from any level below 40 → block LONG
        """
        try:
            sentiment_data = data.get("sentiment")
            result = self.sentiment_analyzer.analyze(sentiment_data)
            fg = result.fear_greed_value
            roc = result.rate_of_change
            label = result.fear_greed_label.replace("_", " ")
            change = result.fear_greed_change

            if direction == "LONG":
                # ISSUE 15 FIX: <= 15 is extreme fear — always block
                if fg <= 15:
                    return False, f"🚫 LONG blocked: Extreme Fear ({fg}) — market capitulation"

                # ISSUE 11 FIX: <= 20 falling → panic accelerating
                if fg <= 20 and roc in ("FALLING", "FALLING_FAST"):
                    return False, f"🚫 LONG blocked: Fear {fg} falling ({roc}, Δ{change:+d})"

                # ISSUE 11 FIX: FALLING_FAST below 40 is dangerous for longs
                if roc == "FALLING_FAST" and fg < 40:
                    return False, f"🚫 LONG blocked: Sentiment deteriorating fast ({fg}↓↓ Δ{change:+d})"

                # Standard: is_long_blocked from analyzer (covers >20 stable extreme fear)
                if self.sentiment_analyzer.is_long_blocked(result):
                    return False, f"🚫 LONG blocked: Extreme Fear ({fg})"

            elif direction == "SHORT":
                # ISSUE 11 FIX: rising fast above 75 → block short (parabolic greed)
                if fg >= 75 and roc == "RISING_FAST":
                    return False, f"🚫 SHORT blocked: Extreme Greed rising fast ({fg}↑↑ Δ{change:+d})"

                if self.sentiment_analyzer.is_short_blocked(result):
                    return False, f"🚫 SHORT blocked: Extreme Greed ({fg})"

            # Recovery mood → note it
            mood_note = ""
            if result.market_mood == MarketMood.RECOVERY:
                mood_note = " | 📈 Recovery signal"

            return True, (
                f"Sentiment OK: {label} ({fg} {roc} Δ{change:+d})"
                f", AltSeason={result.alt_season_index}{mood_note}"
            )

        except Exception as e:
            logger.warning(f"Sentiment filter error: {e} — allowing trade")
            return True, "Sentiment check skipped (error)"

    def _check_btc_regime(self, btc_regime: BTCRegimeResult, direction: Optional[str]) -> Tuple[bool, str]:
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
        """
        ISSUE 5 FIX:
        - All bid/ask values cast to float explicitly
        - "No orderbook data" → FAIL (was: allow) for production safety
          EXCEPT when we genuinely have no data at all (paper/dev mode)
        """
        orderbook = data.get("orderbook", {})
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        # No orderbook — in paper/dev allow; in production this should be populated
        if not bids or not asks:
            if config.ENV == "production":
                return False, "No orderbook data — rejecting in production"
            return True, "No orderbook data — allowing (non-production)"

        # ISSUE 5 FIX: explicit float conversion with error handling
        try:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
        except (TypeError, ValueError, IndexError) as e:
            logger.warning(f"Orderbook float conversion failed: {e}")
            return True, "Invalid orderbook format — allowing"

        if best_bid <= 0 or best_ask <= 0:
            return True, "Zero orderbook prices — allowing"

        spread_pct = ((best_ask - best_bid) / best_bid) * 100
        if spread_pct > 0.1:
            return False, f"Spread too wide: {spread_pct:.3f}%"

        # ISSUE 5 FIX: float() on all depth entries
        try:
            bid_depth = sum(float(b[1]) for b in bids[:5] if len(b) > 1)
            ask_depth = sum(float(a[1]) for a in asks[:5] if len(a) > 1)
        except (TypeError, ValueError):
            bid_depth = ask_depth = 0

        if bid_depth < 10_000 or ask_depth < 10_000:
            return False, f"Thin orderbook: Bid ${bid_depth:,.0f} Ask ${ask_depth:,.0f}"

        return True, f"Spread {spread_pct:.3f}%, Depth ${bid_depth+ask_depth:,.0f}"

    def _check_session(self) -> Tuple[bool, str]:
        import pytz
        now = datetime.now(pytz.timezone("Asia/Kolkata"))
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
