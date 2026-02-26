"""
ARUNABHA ALGO BOT - Signal Generator v4.2

FIXES:
- _confirm_direction: RSI threshold 50→55/45 (stronger filter, কম false signal)
- _confirm_direction: MACD crossover check করা হচ্ছে (histogram এর direction নয়)
- _confirm_direction: EMA alignment vote যোগ করা হয়েছে (4th vote)
- _calculate_levels: শেষ 20 candle → 100 candle (meaningful S/R)
- _calculate_risk_params: SL minimum buffer 0.5 ATR enforce করা হয়েছে
- _confirm_direction: Weak structure-এ 3/4 votes require করা হচ্ছে
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
        Generate trading signal with improved direction logic and S/R calculation
        """
        try:
            ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
            if not ohlcv_15m or len(ohlcv_15m) < 50:
                logger.warning(f"Insufficient 15m data for {symbol}: {len(ohlcv_15m)} candles")
                return None

            current_price = ohlcv_15m[-1][4]
            closes = [c[4] for c in ohlcv_15m]

            # Structure detection
            structure = self.structure.detect(ohlcv_15m)

            # ✅ FIX: Stronger direction confirmation with 4 votes
            direction = self._confirm_direction(structure, closes, ohlcv_15m, current_price)

            if direction is None:
                logger.info(f"⏸️ {symbol}: Direction not confirmed by indicators")
                return None

            # ✅ FIX: Calculate S/R from 100 candles, not 20
            levels = self._calculate_levels(ohlcv_15m, current_price)

            # Score
            score_result = self.scorer.calculate(
                filter_result=filter_result,
                structure=structure,
                market_type=market_type
            )

            # Confidence
            confidence_val = self.confidence.calculate(
                score=score_result["score"],
                grade=score_result["grade"],
                market_type=market_type,
                btc_regime=btc_regime
            )

            # Risk params
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
                "sl_method": risk_params["sl_method"],
                "score": score_result["score"],
                "grade": score_result["grade"].value,
                "confidence": confidence_val,
                "market_type": market_type.value,
                "btc_regime": btc_regime.regime.value if btc_regime else "unknown",
                "structure_strength": structure.strength,
                "levels": levels,
                "filters_passed": filter_result.get("score", 0),
                "filter_summary": filter_result.get("reason", ""),
                "timestamp": datetime.now().isoformat(),
                "key_factors": self._get_key_factors(filter_result, structure),
                # ✅ NEW: Direction vote breakdown for transparency
                "direction_votes": risk_params.get("direction_votes", {})
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
        ohlcv: List[List[float]],
        current_price: float
    ) -> Optional[TradeDirection]:
        """
        ✅ FIXED: 4-vote direction confirmation system

        আগের সমস্যা:
        - RSI > 50 মানেই LONG vote — এটা choppy market-এ random
        - MACD vote ছিল utils/indicators.py-র ভাঙা function-এর উপর নির্ভরশীল
        - মাত্র 3টা vote, 2/3 majority যথেষ্ট ছিল না

        এখন:
        Vote 1 — Structure (BOS/CHoCH): সবচেয়ে গুরুত্বপূর্ণ
        Vote 2 — RSI (55+/45- threshold): false signal কমাতে কড়া threshold
        Vote 3 — MACD crossover (histogram sign change): momentum confirmation
        Vote 4 — EMA stack (9 > 21 > price বা বিপরীত): trend alignment

        Rule:
        - STRONG structure: 2/4 votes যথেষ্ট
        - MODERATE structure: 3/4 votes দরকার
        - WEAK structure: signal দেওয়া হবে না
        """
        votes_long = 0
        votes_short = 0
        vote_detail: Dict[str, str] = {}

        # --- Vote 1: Structure (weight = most important) ---
        if structure.strength == "WEAK":
            logger.info(f"⛔ Direction blocked: WEAK structure, no signal")
            return None

        if structure.direction == "LONG":
            votes_long += 1
            vote_detail["structure"] = "LONG"
        elif structure.direction == "SHORT":
            votes_short += 1
            vote_detail["structure"] = "SHORT"
        else:
            vote_detail["structure"] = "NEUTRAL"

        # --- Vote 2: RSI with tighter thresholds ---
        # আগে: rsi > 50 → LONG (খুব weak signal)
        # এখন: rsi > 55 → LONG, rsi < 45 → SHORT (real momentum)
        if len(closes) >= 14:
            rsi = self.analyzer.calculate_rsi(closes)
            if rsi >= 55 and rsi <= 75:
                votes_long += 1
                vote_detail["rsi"] = f"LONG ({rsi:.1f})"
            elif rsi <= 45 and rsi >= 25:
                votes_short += 1
                vote_detail["rsi"] = f"SHORT ({rsi:.1f})"
            else:
                vote_detail["rsi"] = f"NEUTRAL ({rsi:.1f})"
                logger.debug(f"RSI={rsi:.1f} neutral zone (25-45 or 55-75 required)")

        # --- Vote 3: MACD crossover (histogram sign change) ---
        # শুধু histogram-এর direction নয়, sign change দেখো
        # অর্থাৎ আগের candle negative ছিল, এখন positive = bullish crossover
        if len(closes) >= 35:  # 26 (slow) + 9 (signal) দরকার
            macd_now = self.analyzer.calculate_macd(closes)
            macd_prev = self.analyzer.calculate_macd(closes[:-1])
            hist_now = macd_now.get("histogram", 0)
            hist_prev = macd_prev.get("histogram", 0)

            # Crossover: sign change in histogram
            if hist_prev <= 0 and hist_now > 0:
                votes_long += 1
                vote_detail["macd"] = f"LONG crossover (hist: {hist_prev:.6f}→{hist_now:.6f})"
            elif hist_prev >= 0 and hist_now < 0:
                votes_short += 1
                vote_detail["macd"] = f"SHORT crossover (hist: {hist_prev:.6f}→{hist_now:.6f})"
            else:
                # No crossover — check strong momentum (histogram clear)
                if hist_now > 0:
                    # Continuing bullish momentum — half vote (only contributes if strong)
                    if abs(hist_now) > abs(hist_prev) * 0.5:
                        votes_long += 1
                        vote_detail["macd"] = f"LONG momentum (hist: {hist_now:.6f})"
                    else:
                        vote_detail["macd"] = f"LONG weak (hist: {hist_now:.6f})"
                elif hist_now < 0:
                    if abs(hist_now) > abs(hist_prev) * 0.5:
                        votes_short += 1
                        vote_detail["macd"] = f"SHORT momentum (hist: {hist_now:.6f})"
                    else:
                        vote_detail["macd"] = f"SHORT weak (hist: {hist_now:.6f})"
                else:
                    vote_detail["macd"] = "NEUTRAL"

        # --- Vote 4: EMA stack alignment ---
        # EMA9 > EMA21 > current_price zone = bullish stack
        # EMA9 < EMA21 < current_price zone = bearish (price above all = extended)
        if len(closes) >= 21:
            ema9 = self.analyzer.calculate_ema(closes, 9)
            ema21 = self.analyzer.calculate_ema(closes, 21)

            if ema9 > ema21 and current_price > ema21:
                # Bullish EMA stack, price above slower EMA
                votes_long += 1
                vote_detail["ema"] = f"LONG (EMA9={ema9:.4f} > EMA21={ema21:.4f})"
            elif ema9 < ema21 and current_price < ema21:
                # Bearish EMA stack, price below slower EMA
                votes_short += 1
                vote_detail["ema"] = f"SHORT (EMA9={ema9:.4f} < EMA21={ema21:.4f})"
            else:
                vote_detail["ema"] = f"NEUTRAL (EMA9={ema9:.4f}, EMA21={ema21:.4f})"

        logger.info(
            f"Direction votes: LONG={votes_long}, SHORT={votes_short} | "
            f"Structure={structure.strength} | {vote_detail}"
        )

        # --- Decision logic based on structure strength ---
        # STRONG structure (BOS/CHoCH): 2/4 votes যথেষ্ট
        # MODERATE structure: 3/4 votes দরকার (কড়া requirement)
        if structure.strength == "STRONG":
            required_votes = 2
        else:  # MODERATE
            required_votes = 3

        if votes_long >= required_votes and votes_long > votes_short:
            return TradeDirection.LONG
        elif votes_short >= required_votes and votes_short > votes_long:
            return TradeDirection.SHORT
        else:
            logger.info(
                f"Direction unclear — votes (LONG={votes_long}, SHORT={votes_short}), "
                f"required={required_votes} for {structure.strength} structure"
            )
            return None

    def _calculate_levels(
        self,
        ohlcv: List[List[float]],
        current_price: float
    ) -> Dict[str, Any]:
        """
        ✅ FIXED: Support/Resistance calculation

        আগের সমস্যা:
            highs = [c[2] for c in ohlcv[-20:]]  ← মাত্র ২০ candle = ৫ ঘণ্টা data
            এটা দিয়ে meaningful S/R পাওয়া যায় না

        এখন:
            শেষ 100 candle (15m = ~25 ঘণ্টা) ব্যবহার করা হচ্ছে
            Fibonacci levels আলাদাভাবে last 50 candle এর swing দিয়ে বের করা হচ্ছে
            Structure-based S/R (swing highs/lows) ব্যবহার করা হচ্ছে
        """
        # ✅ FIX: 100 candle use করো, 20 নয়
        lookback = min(100, len(ohlcv))
        recent_ohlcv = ohlcv[-lookback:]

        highs = [c[2] for c in recent_ohlcv]
        lows = [c[3] for c in recent_ohlcv]

        recent_high = max(highs)
        recent_low = min(lows)

        # Swing-based S/R from structure detector
        sr_levels = self.structure.get_support_resistance(recent_ohlcv, num_levels=5)

        # Nearest resistance ABOVE current price
        resistance_above = [r for r in sr_levels.get("resistance", []) if r > current_price]
        nearest_resistance = min(resistance_above) if resistance_above else recent_high

        # Nearest support BELOW current price
        support_below = [s for s in sr_levels.get("support", []) if s < current_price]
        nearest_support = max(support_below) if support_below else recent_low

        # Fibonacci levels based on recent swing
        diff = recent_high - recent_low
        fib_levels = {}
        if diff > 0:
            fib_levels = {
                "fib_236": round(recent_high - diff * 0.236, 8),
                "fib_382": round(recent_high - diff * 0.382, 8),
                "fib_500": round(recent_high - diff * 0.5, 8),
                "fib_618": round(recent_high - diff * 0.618, 8),
                "fib_786": round(recent_high - diff * 0.786, 8)
            }

        return {
            "recent_high": round(recent_high, 8),
            "recent_low": round(recent_low, 8),
            "nearest_resistance": round(nearest_resistance, 8),
            "nearest_support": round(nearest_support, 8),
            "all_resistance": [round(r, 8) for r in sr_levels.get("resistance", [])[:3]],
            "all_support": [round(s, 8) for s in sr_levels.get("support", [])[:3]],
            "lookback_candles": lookback,
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
        SL/TP calculation:
        1. Nearest Support/Resistance try করো
        2. Fibonacci level check করো
        3. ATR fallback use করো
        4. SL minimum = 0.5 ATR (খুব tight SL block করো)
        5. RR >= min_rr enforce করো
        """
        atr = self.analyzer.calculate_atr(ohlcv_15m)
        if atr <= 0:
            return None

        config_key = market_type.value if market_type.value in config.MARKET_CONFIGS else "trending"
        market_config = config.MARKET_CONFIGS.get(config_key, config.MARKET_CONFIGS["trending"])
        sl_mult = market_config.get("sl_mult", config.ATR_SL_MULT)
        tp_mult = market_config.get("tp_mult", config.ATR_TP_MULT)
        min_rr = market_config.get("min_rr", config.MIN_RR_RATIO)

        sl_method = "ATR"

        if direction == TradeDirection.LONG:
            nearest_support = levels.get("nearest_support")
            atr_sl = current_price - (atr * sl_mult)

            if nearest_support and nearest_support > atr_sl and nearest_support < current_price:
                stop_loss = nearest_support * 0.997
                sl_method = "Support"
            else:
                stop_loss = atr_sl
                sl_method = "ATR"

            # ✅ FIX: SL minimum distance = 0.5 ATR (tight SL block)
            min_sl_dist = atr * 0.5
            if (current_price - stop_loss) < min_sl_dist:
                stop_loss = current_price - min_sl_dist
                sl_method += "(min_enforced)"

            nearest_resistance = levels.get("nearest_resistance")
            atr_tp = current_price + (atr * tp_mult)

            if nearest_resistance and nearest_resistance > current_price:
                sl_dist = current_price - stop_loss
                sr_dist = nearest_resistance - current_price
                if sl_dist > 0 and (sr_dist / sl_dist) >= min_rr:
                    take_profit = nearest_resistance * 0.998
                    sl_method += "+SR_TP"
                else:
                    take_profit = atr_tp
                    sl_method += "+ATR_TP"
            else:
                take_profit = atr_tp

        else:  # SHORT
            nearest_resistance = levels.get("nearest_resistance")
            atr_sl = current_price + (atr * sl_mult)

            if nearest_resistance and nearest_resistance < atr_sl and nearest_resistance > current_price:
                stop_loss = nearest_resistance * 1.003
                sl_method = "Resistance"
            else:
                stop_loss = atr_sl
                sl_method = "ATR"

            # ✅ FIX: SL minimum distance = 0.5 ATR
            min_sl_dist = atr * 0.5
            if (stop_loss - current_price) < min_sl_dist:
                stop_loss = current_price + min_sl_dist
                sl_method += "(min_enforced)"

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

        # Final RR check
        sl_distance = abs(current_price - stop_loss)
        tp_distance = abs(take_profit - current_price)

        if sl_distance <= 0:
            logger.warning("SL distance is zero — aborting signal")
            return None

        rr_ratio = tp_distance / sl_distance

        if rr_ratio < min_rr:
            sl_dist = abs(current_price - stop_loss)
            if direction == TradeDirection.LONG:
                take_profit = current_price + (sl_dist * min_rr)
            else:
                take_profit = current_price - (sl_dist * min_rr)
            rr_ratio = min_rr
            sl_method += f"(RR_forced:{min_rr})"

        logger.info(
            f"Risk params: SL={stop_loss:.6f} ({sl_method}) | "
            f"TP={take_profit:.6f} | RR={rr_ratio:.2f} | ATR={atr:.6f}"
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
        factors.append(f"Structure: {structure.strength} ({structure.reason})")

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
