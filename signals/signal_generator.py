"""
ARUNABHA ALGO BOT - Signal Generator v5.0
==========================================
FIXES:
ISSUE 1: SL/TP Calculation Bug — FIXED
  - Support-based SL নিলে ATR distance check করা হচ্ছে
  - TP recalculated based on ACTUAL SL distance (not ATR TP independently)
  - RR enforce করলে TP সঠিকভাবে adjust হচ্ছে
  - Max SL = 2x ATR (too wide SL block)

ISSUE 11: Sentiment ROC properly used in signal scoring
ISSUE 12: Entry zone checked before signal sent
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import config
from core.constants import TradeDirection, SignalGrade, MarketType
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from signals.scorer import SignalScorer
from signals.confidence_calculator import ConfidenceCalculator
from signals.validator import SignalValidator

logger = logging.getLogger(__name__)


class SignalGenerator:

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.scorer = SignalScorer()
        self.confidence_calc = ConfidenceCalculator()
        self.validator = SignalValidator()

    def generate(
        self,
        symbol: str,
        data: Dict[str, Any],
        filter_result: Dict[str, Any]
    ) -> Optional[Dict]:
        """Generate signal from filter result"""
        try:
            ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
            if len(ohlcv_15m) < 30:
                return None

            current_price = float(ohlcv_15m[-1][4])
            direction_str = data.get("direction")
            if not direction_str:
                return None

            try:
                direction = TradeDirection(direction_str)
            except ValueError:
                direction = TradeDirection.LONG if direction_str == "LONG" else TradeDirection.SHORT

            market_type = data.get("market_type", MarketType.UNKNOWN)
            if isinstance(market_type, str):
                try:
                    market_type = MarketType(market_type)
                except ValueError:
                    market_type = MarketType.UNKNOWN

            # Get key levels
            levels = self._get_levels(ohlcv_15m, current_price)

            # ─── ISSUE 1 FIX: Proper SL/TP calculation ─────────────────
            risk_params = self._calculate_risk_params(
                ohlcv_15m, direction, current_price, market_type, levels
            )
            if not risk_params:
                logger.debug(f"Risk params failed for {symbol}")
                return None

            # Score
            score_result = self.scorer.calculate(
                filter_result=filter_result,
                structure=data.get("structure"),
                market_type=market_type,
                rr_ratio=risk_params["rr_ratio"]
            )

            # Grade check
            grade = SignalGrade.from_score(score_result.score)
            if not grade.can_trade:
                logger.debug(f"Grade {grade.value} too low for {symbol}")
                return None

            # Confidence
            btc_regime = data.get("btc_regime")
            confidence = self.confidence_calc.calculate(
                score=score_result.score,
                market_type=market_type,
                btc_regime=btc_regime,
                filter_result=filter_result
            )

            if confidence < config.CONFIDENCE["MIN_CONFIDENCE_ALLOW"]:
                return None

            # Key factors
            key_factors = self._get_key_factors(filter_result, data)

            # ─── ISSUE 11 FIX: Sentiment in signal output ──────────────
            sentiment_info = None
            sentiment_data = data.get("sentiment")
            if sentiment_data:
                fg = sentiment_data.get("fear_greed", {})
                alt = sentiment_data.get("alt_season", {})
                sentiment_info = {
                    "fear_greed_value": fg.get("value", 50),
                    "fear_greed_label": fg.get("classification", "NEUTRAL"),
                    "fear_greed_change": fg.get("change", 0),
                    "rate_of_change": fg.get("rate_of_change", "STABLE"),
                    "alt_season_index": alt.get("alt_season_index", 50),
                }

            signal = {
                "symbol": symbol,
                "direction": direction.value,
                "entry": round(current_price, 8),
                "stop_loss": risk_params["stop_loss"],
                "take_profit": risk_params["take_profit"],
                "rr_ratio": risk_params["rr_ratio"],
                "atr": risk_params["atr"],
                "atr_pct": risk_params["atr_pct"],
                "sl_method": risk_params["sl_method"],
                "score": round(score_result.score, 1),
                "grade": grade.value,
                "confidence": confidence,
                "market_type": market_type.value,
                "structure_strength": getattr(data.get("structure"), "strength", "UNKNOWN"),
                "key_factors": key_factors,
                "levels": levels,
                "sentiment": sentiment_info,
                "timestamp": datetime.now().isoformat(),
                "fear_index": sentiment_info["fear_greed_value"] if sentiment_info else 50,
            }

            # Validate
            errors = self.validator.validate(signal)
            if errors:
                logger.debug(f"Signal validation failed {symbol}: {errors}")
                return None

            logger.info(
                f"✅ Signal: {symbol} {direction.value} @ {current_price:.4f} | "
                f"SL={risk_params['stop_loss']:.4f} ({risk_params['sl_method']}) | "
                f"TP={risk_params['take_profit']:.4f} | RR={risk_params['rr_ratio']:.2f} | "
                f"Grade={grade.value} Score={score_result.score:.1f}"
            )
            return signal

        except Exception as e:
            logger.error(f"Signal generation error {symbol}: {e}", exc_info=True)
            return None

    def _calculate_risk_params(
        self,
        ohlcv_15m: List,
        direction: TradeDirection,
        current_price: float,
        market_type: MarketType,
        levels: Dict
    ) -> Optional[Dict]:
        """
        ISSUE 1 FIX: Proper SL/TP calculation

        Rules:
        1. Try support/resistance based SL first
        2. ATR fallback
        3. SL min = 0.5 ATR, max = 2.0 ATR (too wide = bad trade)
        4. TP = based on ACTUAL sl_distance * tp_mult (not independent ATR calc)
           This ensures RR is always consistent
        5. RR enforce করলে TP adjust হচ্ছে, SL নয়
        """
        atr = self.analyzer.calculate_atr(ohlcv_15m)
        if atr <= 0:
            return None

        config_key = market_type.value if market_type.value in config.MARKET_CONFIGS else "trending"
        market_config = config.MARKET_CONFIGS.get(config_key, config.MARKET_CONFIGS["trending"])
        sl_mult = market_config.get("sl_mult", config.ATR_SL_MULT)
        tp_mult = market_config.get("tp_mult", config.ATR_TP_MULT)
        min_rr = market_config.get("min_rr", config.MIN_RR_RATIO)

        # Bounds
        min_sl_dist = atr * 0.5
        max_sl_dist = atr * 2.0   # ← ISSUE 1 FIX: max SL added

        sl_method = "ATR"

        if direction == TradeDirection.LONG:
            nearest_support = levels.get("nearest_support")
            atr_sl = current_price - (atr * sl_mult)

            # Support-based SL
            if (nearest_support
                    and atr_sl <= nearest_support < current_price):
                candidate_sl = nearest_support * 0.997
                candidate_dist = current_price - candidate_sl

                # ← ISSUE 1 FIX: ATR distance check for support-based SL
                if min_sl_dist <= candidate_dist <= max_sl_dist:
                    stop_loss = candidate_sl
                    sl_method = "Support"
                else:
                    stop_loss = atr_sl
                    sl_method = "ATR(SR_rejected)"
            else:
                stop_loss = atr_sl

            # Enforce min/max SL distance
            sl_dist = current_price - stop_loss
            if sl_dist < min_sl_dist:
                stop_loss = current_price - min_sl_dist
                sl_method += "(min)"
            elif sl_dist > max_sl_dist:
                stop_loss = current_price - max_sl_dist
                sl_method += "(max_capped)"

            # ← ISSUE 1 FIX: TP based on ACTUAL sl_distance, not independent ATR
            actual_sl_dist = current_price - stop_loss
            tp_from_rr = current_price + (actual_sl_dist * tp_mult)

            # Try SR-based TP
            nearest_resistance = levels.get("nearest_resistance")
            if nearest_resistance and nearest_resistance > current_price:
                sr_dist = nearest_resistance - current_price
                sr_rr = sr_dist / actual_sl_dist if actual_sl_dist > 0 else 0
                if sr_rr >= min_rr:
                    take_profit = nearest_resistance * 0.998
                    sl_method += "+SR_TP"
                else:
                    take_profit = tp_from_rr
                    sl_method += "+ATR_TP"
            else:
                take_profit = tp_from_rr

        else:  # SHORT
            nearest_resistance = levels.get("nearest_resistance")
            atr_sl = current_price + (atr * sl_mult)

            if (nearest_resistance
                    and current_price < nearest_resistance <= atr_sl):
                candidate_sl = nearest_resistance * 1.003
                candidate_dist = candidate_sl - current_price

                if min_sl_dist <= candidate_dist <= max_sl_dist:
                    stop_loss = candidate_sl
                    sl_method = "Resistance"
                else:
                    stop_loss = atr_sl
                    sl_method = "ATR(SR_rejected)"
            else:
                stop_loss = atr_sl

            sl_dist = stop_loss - current_price
            if sl_dist < min_sl_dist:
                stop_loss = current_price + min_sl_dist
                sl_method += "(min)"
            elif sl_dist > max_sl_dist:
                stop_loss = current_price + max_sl_dist
                sl_method += "(max_capped)"

            actual_sl_dist = stop_loss - current_price
            tp_from_rr = current_price - (actual_sl_dist * tp_mult)

            nearest_support = levels.get("nearest_support")
            if nearest_support and nearest_support < current_price:
                sr_dist = current_price - nearest_support
                sr_rr = sr_dist / actual_sl_dist if actual_sl_dist > 0 else 0
                if sr_rr >= min_rr:
                    take_profit = nearest_support * 1.002
                    sl_method += "+SR_TP"
                else:
                    take_profit = tp_from_rr
                    sl_method += "+ATR_TP"
            else:
                take_profit = tp_from_rr

        # Final RR
        sl_distance = abs(current_price - stop_loss)
        tp_distance = abs(take_profit - current_price)

        if sl_distance <= 0:
            logger.warning(f"SL distance zero — aborting")
            return None

        rr_ratio = tp_distance / sl_distance

        # ← ISSUE 1 FIX: if RR low, extend TP only (don't touch SL)
        if rr_ratio < min_rr:
            if direction == TradeDirection.LONG:
                take_profit = current_price + (sl_distance * min_rr)
            else:
                take_profit = current_price - (sl_distance * min_rr)
            rr_ratio = min_rr
            sl_method += f"(RR_TP_forced:{min_rr})"

        return {
            "stop_loss": round(stop_loss, 8),
            "take_profit": round(take_profit, 8),
            "rr_ratio": round(rr_ratio, 2),
            "atr": round(atr, 8),
            "atr_pct": round((atr / current_price) * 100, 4),
            "sl_method": sl_method,
        }

    def _get_levels(self, ohlcv: List, current_price: float) -> Dict:
        try:
            levels = self.structure.get_support_resistance(ohlcv, num_levels=5)
            supports = [s for s in levels.get("support", []) if s < current_price]
            resistances = [r for r in levels.get("resistance", []) if r > current_price]
            return {
                "nearest_support": max(supports) if supports else None,
                "nearest_resistance": min(resistances) if resistances else None,
                "all_supports": supports,
                "all_resistances": resistances,
            }
        except Exception:
            return {"nearest_support": None, "nearest_resistance": None}

    def _get_key_factors(self, filter_result: Dict, data: Dict) -> List[str]:
        factors = []
        tier2 = filter_result.get("tier2", {})
        top = sorted(
            [(k, v) for k, v in tier2.items() if v.get("passed") and v.get("score", 0) >= 8],
            key=lambda x: x[1].get("score", 0), reverse=True
        )[:4]
        for name, res in top:
            msg = res.get("message", "")
            factors.append(f"{name.replace('_',' ').title()}: {msg[:50]}")

        # Add sentiment ROC if relevant
        sentiment = data.get("sentiment", {})
        if sentiment:
            fg = sentiment.get("fear_greed", {})
            roc = fg.get("rate_of_change", "")
            if roc in ("RISING_FAST", "FALLING_FAST"):
                factors.append(f"Sentiment: F&G {roc} ({fg.get('change',0):+d})")

        return factors[:4]
