"""
ARUNABHA ALGO BOT - Signal Generator v4.1 (FIXED)

FIXES:
- _calculate_risk_params: SL/TP এখন nearest Support/Resistance use করে
- Direction confirm: RSI + MACD একমত হলে তবেই signal
- Fibonacci levels SL/TP calculation এ use হচ্ছে
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
    """
    Generates final trading signals
    """

    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.scorer = SignalScorer()
        self.confidence = ConfidenceCalculator()
        self.validator = SignalValidator()

        self.last_signals: Dict[str, datetime] = {}

    async def generate(
        self,
        symbol: str,
        data: Dict[str, Any],
        filter_result: Dict[str, Any],
        market_type: MarketType,
        btc_regime: Any
    ) -> Optional[Dict]:
        """
        Generate trading signal with improved SL/TP logic
        """
        try:
            ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
            if not ohlcv_15m:
                logger.warning(f"No 15m data for {symbol}")
                return None

            current_price = ohlcv_15m[-1][4]
            closes = [c[4] for c in ohlcv_15m]

            # ✅ FIX: Direction RSI + MACD + Structure তিনটা মিলিয়ে decide
            structure = self.structure.detect(ohlcv_15m)
            direction = self._confirm_direction(structure, closes, current_price)

            if direction is None:
                logger.info(f"⏸️ {symbol}: Direction not confirmed by indicators")
                return None

            # Calculate technical levels (support/resistance/fib)
            levels = self._calculate_levels(ohlcv_15m, current_price)

            # Score
            score_result = self.scorer.calculate(
                filter_result=filter_result,
                structure=structure,
                market_type=market_type
            )

            # Confidence
            confidence = self.confidence.calculate(
                score=score_result["score"],
                grade=score_result["grade"],
                market_type=market_type,
                btc_regime=btc_regime
            )

            # ✅ FIX: SL/TP now uses Support/Resistance + ATR
            risk_params = self._calculate_risk_params(
                ohlcv_15m=ohlcv_15m,
                direction=direction,
                current_price=current_price,
                market_type=market_type,
                levels=levels
            )

            if not risk_params:
                logger.warning(f"Could not calculate risk params for {symbol}")
                return None

            signal = {
                "symbol": symbol,
                "direction": direction.value,
                "entry": current_price,
                "stop_loss": risk_params["stop_loss"],
                "take_profit": risk_params["take_profit"],
                "rr_ratio": risk_params["rr_ratio"],
                "atr": risk_params["atr"],
                "atr_pct": risk_params["atr_pct"],
                "sl_method": risk_params["sl_method"],   # ✅ NEW: কীভাবে SL calculate হলো
                "score": score_result["score"],
                "grade": score_result["grade"].value,
                "confidence": confidence,
                "market_type": market_type.value,
                "btc_regime": btc_regime.regime.value if btc_regime else "unknown",
                "structure_strength": structure.strength,
                "levels": levels,
                "filters_passed": filter_result.get("score", 0),
                "filter_summary": filter_result.get("reason", ""),
                "timestamp": datetime.now().isoformat(),
                "key_factors": self._get_key_factors(filter_result, structure)
            }

            is_valid, errors = self.validator.validate(signal)

            if not is_valid:
                logger.debug(f"Signal validation failed for {symbol}: {errors}")
                return None

            self.last_signals[symbol] = datetime.now()

            return signal

        except Exception as e:
            logger.error(f"Signal generation error for {symbol}: {e}")
            return None

    def _confirm_direction(
        self,
        structure: Any,
        closes: List[float],
        current_price: float
    ) -> Optional[TradeDirection]:
        """
        ✅ NEW: Structure + RSI + MACD তিনটা মিলে direction confirm করো
        অন্তত ২টা একমত হলে signal দাও
        """
        votes_long = 0
        votes_short = 0

        # Vote 1: Structure
        if structure.direction == "LONG":
            votes_long += 1
        elif structure.direction == "SHORT":
            votes_short += 1

        # Vote 2: RSI
        if len(closes) >= 14:
            rsi = self.analyzer.calculate_rsi(closes)
            if rsi > 50 and rsi < 70:    # Bullish but not overbought
                votes_long += 1
            elif rsi < 50 and rsi > 30:  # Bearish but not oversold
                votes_short += 1
            logger.debug(f"RSI={rsi:.1f} → {'LONG' if rsi > 50 else 'SHORT'}")

        # Vote 3: MACD
        if len(closes) >= 26:
            macd = self.analyzer.calculate_macd(closes)
            macd_hist = macd.get("macd", 0) - macd.get("signal", 0)
            if macd_hist > 0:
                votes_long += 1
            elif macd_hist < 0:
                votes_short += 1
            logger.debug(f"MACD_hist={macd_hist:.6f} → {'LONG' if macd_hist > 0 else 'SHORT'}")

        logger.info(f"Direction votes: LONG={votes_long}, SHORT={votes_short}")

        # ২ out of ৩ agree করলে direction confirm
        if votes_long >= 2:
            return TradeDirection.LONG
        elif votes_short >= 2:
            return TradeDirection.SHORT
        else:
            logger.info("Direction unclear — no majority vote")
            return None

    def _calculate_levels(
        self,
        ohlcv: List[List[float]],
        current_price: float
    ) -> Dict[str, Any]:
        """Calculate key price levels including S/R and Fibonacci"""

        highs = [c[2] for c in ohlcv[-20:]]
        lows = [c[3] for c in ohlcv[-20:]]

        recent_high = max(highs)
        recent_low = min(lows)

        diff = recent_high - recent_low

        fib_levels = {
            "fib_236": round(recent_high - diff * 0.236, 8),
            "fib_382": round(recent_high - diff * 0.382, 8),
            "fib_500": round(recent_high - diff * 0.5, 8),
            "fib_618": round(recent_high - diff * 0.618, 8),
            "fib_786": round(recent_high - diff * 0.786, 8)
        }

        # ✅ Nearest S/R based on last 20 candles
        nearest_resistance = min(
            [h for h in highs if h > current_price],
            default=recent_high
        )
        nearest_support = max(
            [l for l in lows if l < current_price],
            default=recent_low
        )

        return {
            "recent_high": round(recent_high, 8),
            "recent_low": round(recent_low, 8),
            "nearest_resistance": round(nearest_resistance, 8),
            "nearest_support": round(nearest_support, 8),
            **fib_levels
        }

    def _calculate_risk_params(
        self,
        ohlcv_15m: List[List[float]],
        direction: TradeDirection,
        current_price: float,
        market_type: MarketType,
        levels: Dict[str, Any]
    ) -> Optional[Dict]:
        """
        ✅ FIXED: SL/TP calculation
        1. Nearest Support/Resistance try করো
        2. Fibonacci level try করো
        3. ATR fallback use করো
        4. যেটাই use করো, RR >= 1.5 ensure করো
        """

        atr = self.analyzer.calculate_atr(ohlcv_15m)
        if atr <= 0:
            return None

        config_key = market_type.value if market_type.value in config.MARKET_CONFIGS else "trending"
        market_config = config.MARKET_CONFIGS.get(config_key, config.MARKET_CONFIGS["trending"])
        sl_mult = market_config.get("sl_mult", config.ATR_SL_MULT)
        tp_mult = market_config.get("tp_mult", config.ATR_TP_MULT)
        min_rr = market_config.get("min_rr", config.MIN_RR_RATIO)

        sl_method = "ATR"  # Default

        if direction == TradeDirection.LONG:
            # ✅ SL: Nearest support এর নিচে (+ small buffer)
            nearest_support = levels.get("nearest_support")
            atr_sl = current_price - (atr * sl_mult)

            if nearest_support and nearest_support > atr_sl:
                # Support এর 0.3% নিচে SL
                stop_loss = nearest_support * 0.997
                sl_method = "Support"
            else:
                # ATR fallback
                stop_loss = atr_sl
                sl_method = "ATR"

            # TP: Nearest resistance বা ATR TP
            nearest_resistance = levels.get("nearest_resistance")
            atr_tp = current_price + (atr * tp_mult)

            if nearest_resistance and nearest_resistance > current_price:
                # RR check
                sl_dist = current_price - stop_loss
                sr_dist = nearest_resistance - current_price
                if sl_dist > 0 and (sr_dist / sl_dist) >= min_rr:
                    take_profit = nearest_resistance * 0.998  # 0.2% before resistance
                    sl_method += "+SR_TP"
                else:
                    take_profit = atr_tp  # ATR tp better RR
                    sl_method += "+ATR_TP"
            else:
                take_profit = atr_tp

        else:  # SHORT
            # ✅ SL: Nearest resistance এর উপরে
            nearest_resistance = levels.get("nearest_resistance")
            atr_sl = current_price + (atr * sl_mult)

            if nearest_resistance and nearest_resistance < atr_sl:
                stop_loss = nearest_resistance * 1.003  # 0.3% above resistance
                sl_method = "Resistance"
            else:
                stop_loss = atr_sl
                sl_method = "ATR"

            # TP: Nearest support বা ATR TP
            nearest_support = levels.get("nearest_support")
            atr_tp = current_price - (atr * tp_mult)

            if nearest_support and nearest_support < current_price:
                sl_dist = stop_loss - current_price
                sr_dist = current_price - nearest_support
                if sl_dist > 0 and (sr_dist / sl_dist) >= min_rr:
                    take_profit = nearest_support * 1.002
                    sl_method += "+SR_TP"
                else:
                    take_profit = atr_tp
                    sl_method += "+ATR_TP"
            else:
                take_profit = atr_tp

        # Final RR check — minimum enforce
        rr_ratio = abs(take_profit - current_price) / abs(current_price - stop_loss)

        if rr_ratio < min_rr:
            # Force TP to meet minimum RR
            sl_dist = abs(current_price - stop_loss)
            if direction == TradeDirection.LONG:
                take_profit = current_price + (sl_dist * min_rr)
            else:
                take_profit = current_price - (sl_dist * min_rr)
            rr_ratio = min_rr
            sl_method += f"(RR_forced:{min_rr})"

        logger.info(
            f"Risk params: SL={stop_loss:.6f} ({sl_method}) | "
            f"TP={take_profit:.6f} | RR={rr_ratio:.2f}"
        )

        return {
            "stop_loss": round(stop_loss, 8),
            "take_profit": round(take_profit, 8),
            "rr_ratio": round(rr_ratio, 2),
            "atr": round(atr, 8),
            "atr_pct": round((atr / current_price) * 100, 4),
            "sl_method": sl_method
        }

    def _get_key_factors(
        self,
        filter_result: Dict[str, Any],
        structure: Any
    ) -> List[str]:
        """Get key factors that led to signal"""

        factors = []
        factors.append(f"Structure: {structure.strength}")

        if "tier2" in filter_result:
            top_filters = sorted(
                [(k, v) for k, v in filter_result["tier2"].items() if v.get("passed", False)],
                key=lambda x: x[1].get("score", 0),
                reverse=True
            )[:2]

            for f, _ in top_filters:
                factors.append(f.replace("_", " ").title())

        if "tier3" in filter_result:
            bonuses = [k for k, v in filter_result["tier3"].items() if v.get("bonus", 0) > 0]
            if bonuses:
                factors.append(f"+{', '.join(bonuses[:2])}")

        return factors[:4]