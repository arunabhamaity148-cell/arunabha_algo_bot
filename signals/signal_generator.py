"""
ARUNABHA ALGO BOT - Signal Generator
Generates final trading signals from all inputs
"""

import logging
from typing import Dict, List, Optional, Any
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
        Generate trading signal
        """
        try:
            # Extract data
            ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
            if not ohlcv_15m:
                logger.warning(f"No 15m data for {symbol}")
                return None
            
            current_price = ohlcv_15m[-1][4]
            
            # Determine direction from structure
            structure = self.structure.detect(ohlcv_15m)
            direction = TradeDirection(structure.direction)
            
            # Calculate technical levels
            levels = self._calculate_levels(ohlcv_15m, current_price)
            
            # Calculate score and grade
            score_result = self.scorer.calculate(
                filter_result=filter_result,
                structure=structure,
                market_type=market_type
            )
            
            # Calculate confidence
            confidence = self.confidence.calculate(
                score=score_result["score"],
                grade=score_result["grade"],
                market_type=market_type,
                btc_regime=btc_regime
            )
            
            # Calculate risk parameters
            risk_params = self._calculate_risk_params(
                ohlcv_15m=ohlcv_15m,
                direction=direction,
                current_price=current_price,
                market_type=market_type
            )
            
            if not risk_params:
                logger.warning(f"Could not calculate risk params for {symbol}")
                return None
            
            # Build signal
            signal = {
                "symbol": symbol,
                "direction": direction.value,
                "entry": current_price,
                "stop_loss": risk_params["stop_loss"],
                "take_profit": risk_params["take_profit"],
                "rr_ratio": risk_params["rr_ratio"],
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
            
            # Validate signal
            is_valid, errors = self.validator.validate(signal)
            
            if not is_valid:
                logger.debug(f"Signal validation failed for {symbol}: {errors}")
                return None
            
            # Update last signal time
            self.last_signals[symbol] = datetime.now()
            
            return signal
            
        except Exception as e:
            logger.error(f"Signal generation error for {symbol}: {e}")
            return None
    
    def _calculate_levels(
        self,
        ohlcv: List[List[float]],
        current_price: float
    ) -> Dict[str, float]:
        """Calculate key price levels"""
        
        # Find recent swing points
        highs = [c[2] for c in ohlcv[-20:]]
        lows = [c[3] for c in ohlcv[-20:]]
        
        recent_high = max(highs)
        recent_low = min(lows)
        
        # Calculate Fibonacci levels
        diff = recent_high - recent_low
        fib_levels = {
            "fib_236": recent_high - diff * 0.236,
            "fib_382": recent_high - diff * 0.382,
            "fib_500": recent_high - diff * 0.5,
            "fib_618": recent_high - diff * 0.618,
            "fib_786": recent_high - diff * 0.786
        }
        
        # Find nearest levels
        nearest_resistance = min([h for h in highs if h > current_price], default=None)
        nearest_support = max([l for l in lows if l < current_price], default=None)
        
        return {
            "recent_high": recent_high,
            "recent_low": recent_low,
            "nearest_resistance": nearest_resistance,
            "nearest_support": nearest_support,
            **fib_levels
        }
    
    def _calculate_risk_params(
        self,
        ohlcv_15m: List[List[float]],
        direction: TradeDirection,
        current_price: float,
        market_type: MarketType
    ) -> Optional[Dict]:
        """Calculate stop loss and take profit levels"""
        
        # Calculate ATR
        atr = self.analyzer.calculate_atr(ohlcv_15m)
        
        if atr <= 0:
            return None
        
        # Get multipliers from config
        config_key = market_type.value if market_type.value in config.MARKET_CONFIGS else "trending"
        market_config = config.MARKET_CONFIGS.get(config_key, config.MARKET_CONFIGS["trending"])
        
        sl_mult = market_config.get("sl_mult", config.ATR_SL_MULT)
        tp_mult = market_config.get("tp_mult", config.ATR_TP_MULT)
        
        # Calculate SL and TP
        if direction == TradeDirection.LONG:
            stop_loss = current_price - (atr * sl_mult)
            take_profit = current_price + (atr * tp_mult)
        else:
            stop_loss = current_price + (atr * sl_mult)
            take_profit = current_price - (atr * tp_mult)
        
        # Calculate RR ratio
        rr_ratio = abs(take_profit - current_price) / abs(current_price - stop_loss)
        
        return {
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "rr_ratio": round(rr_ratio, 2),
            "atr": round(atr, 2),
            "atr_pct": round((atr / current_price) * 100, 2)
        }
    
    def _get_key_factors(
        self,
        filter_result: Dict[str, Any],
        structure: Any
    ) -> List[str]:
        """Get key factors that led to signal"""
        
        factors = []
        
        # Add structure
        factors.append(f"Structure: {structure.strength}")
        
        # Add top tier2 filters
        if "tier2" in filter_result:
            top_filters = sorted(
                [(k, v) for k, v in filter_result["tier2"].items() if v.get("passed", False)],
                key=lambda x: x[1].get("score", 0),
                reverse=True
            )[:2]
            
            for f, _ in top_filters:
                factors.append(f.replace("_", " ").title())
        
        # Add tier3 bonuses
        if "tier3" in filter_result:
            bonuses = [k for k, v in filter_result["tier3"].items() if v.get("bonus", 0) > 0]
            if bonuses:
                factors.append(f"+{', '.join(bonuses[:2])}")
        
        return factors[:4]  # Max 4 factors
