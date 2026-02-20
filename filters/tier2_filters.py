"""
ARUNABHA ALGO BOT - Tier 2 Filters
Quality filters with weighted scoring
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
import numpy as np

import config
from core.constants import MarketType
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from analysis.volume_profile import VolumeProfileAnalyzer

logger = logging.getLogger(__name__)


class Tier2Filters:
    """
    Tier 2 quality filters with weighted scoring
    Need minimum score to pass
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
        """
        Evaluate all Tier 2 filters
        Returns: (passed, score, results_dict)
        """
        results = {}
        total_score = 0
        max_score = sum(self.weights.values())
        
        # Filter 1: MTF Confirmation
        mtf_passed, mtf_score, mtf_msg = self._check_mtf(data, direction)
        results["mtf_confirmation"] = {
            "passed": mtf_passed,
            "score": mtf_score,
            "weight": self.weights.get("mtf_confirmation", 20),
            "message": mtf_msg
        }
        total_score += mtf_score
        
        # Filter 2: Volume Profile
        vp_passed, vp_score, vp_msg = self._check_volume_profile(data)
        results["volume_profile"] = {
            "passed": vp_passed,
            "score": vp_score,
            "weight": self.weights.get("volume_profile", 15),
            "message": vp_msg
        }
        total_score += vp_score
        
        # Filter 3: Funding Rate
        funding_passed, funding_score, funding_msg = self._check_funding_rate(data, direction)
        results["funding_rate"] = {
            "passed": funding_passed,
            "score": funding_score,
            "weight": self.weights.get("funding_rate", 10),
            "message": funding_msg
        }
        total_score += funding_score
        
        # Filter 4: Open Interest
        oi_passed, oi_score, oi_msg = self._check_open_interest(data)
        results["open_interest"] = {
            "passed": oi_passed,
            "score": oi_score,
            "weight": self.weights.get("open_interest", 10),
            "message": oi_msg
        }
        total_score += oi_score
        
        # Filter 5: RSI Divergence
        rsi_passed, rsi_score, rsi_msg = self._check_rsi_divergence(data, direction)
        results["rsi_divergence"] = {
            "passed": rsi_passed,
            "score": rsi_score,
            "weight": self.weights.get("rsi_divergence", 15),
            "message": rsi_msg
        }
        total_score += rsi_score
        
        # Filter 6: EMA Stack
        ema_passed, ema_score, ema_msg = self._check_ema_stack(data, direction)
        results["ema_stack"] = {
            "passed": ema_passed,
            "score": ema_score,
            "weight": self.weights.get("ema_stack", 10),
            "message": ema_msg
        }
        total_score += ema_score
        
        # Filter 7: ATR Percent
        atr_passed, atr_score, atr_msg = self._check_atr_percent(data)
        results["atr_percent"] = {
            "passed": atr_passed,
            "score": atr_score,
            "weight": self.weights.get("atr_percent", 10),
            "message": atr_msg
        }
        total_score += atr_score
        
        # Filter 8: VWAP Position
        vwap_passed, vwap_score, vwap_msg = self._check_vwap_position(data, direction)
        results["vwap_position"] = {
            "passed": vwap_passed,
            "score": vwap_score,
            "weight": self.weights.get("vwap_position", 5),
            "message": vwap_msg
        }
        total_score += vwap_score
        
        # Filter 9: Support/Resistance
        sr_passed, sr_score, sr_msg = self._check_support_resistance(data, direction)
        results["support_resistance"] = {
            "passed": sr_passed,
            "score": sr_score,
            "weight": self.weights.get("support_resistance", 5),
            "message": sr_msg
        }
        total_score += sr_score
        
        # Calculate percentage score
        percentage = (total_score / max_score) * 100 if max_score > 0 else 0
        
        # Check if passed threshold
        threshold = self._get_threshold(market_type)
        passed = percentage >= threshold
        
        if passed:
            logger.debug(f"Tier2 score: {percentage:.1f}% >= {threshold}%")
        else:
            logger.debug(f"Tier2 score: {percentage:.1f}% < {threshold}%")
        
        return passed, percentage, results
    
    def _get_threshold(self, market_type: MarketType) -> int:
        """Get threshold based on market type"""
        thresholds = {
            MarketType.TRENDING: 60,
            MarketType.CHOPPY: 55,
            MarketType.HIGH_VOL: 65,
            MarketType.UNKNOWN: 60
        }
        return thresholds.get(market_type, 60)
    
    def _check_mtf(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """Check multi-timeframe confirmation"""
        
        ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
        ohlcv_1h = data.get("ohlcv", {}).get("1h", [])
        
        if len(ohlcv_15m) < 10 or len(ohlcv_1h) < 10:
            return False, 0, "Insufficient data"
        
        # Get trends
        trend_15m = 1 if ohlcv_15m[-1][4] > ohlcv_15m[-5][4] else -1
        trend_1h = 1 if ohlcv_1h[-1][4] > ohlcv_1h[-5][4] else -1
        
        # Check alignment
        if trend_15m == trend_1h:
            if direction:
                dir_val = 1 if direction == "LONG" else -1
                if trend_15m == dir_val:
                    return True, 20, "All TF aligned with direction"
                else:
                    return True, 15, "TF aligned but opposite direction"
            return True, 20, "All TF aligned"
        else:
            return False, 5, "TF conflict"
    
    def _check_volume_profile(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Check volume profile position"""
        
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"
        
        current_price = ohlcv[-1][4]
        vp_result = self.volume.analyze(ohlcv)
        
        # Check if price is in value area
        in_va = self.volume.is_price_in_value_area(current_price, vp_result)
        
        if in_va:
            return True, 15, f"Price in value area (POC: {vp_result.poc:.2f})"
        else:
            pos = self.volume.get_value_area_position(current_price, vp_result)
            if pos == "BELOW_VA":
                return True, 10, f"Price below VA, near support"
            elif pos == "ABOVE_VA":
                return True, 10, f"Price above VA, near resistance"
            else:
                return False, 5, "Price away from value area"
    
    def _check_funding_rate(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """Check funding rate conditions"""
        
        funding = data.get("funding_rate", 0)
        
        # Convert to percentage
        funding_pct = funding * 100
        
        # Check if extreme
        if abs(funding_pct) > 0.01:  # > 0.01%
            if direction == "LONG" and funding_pct > 0:
                return False, 0, f"High positive funding ({funding_pct:.3f}%)"
            elif direction == "SHORT" and funding_pct < 0:
                return False, 0, f"High negative funding ({funding_pct:.3f}%)"
            else:
                # Opposite direction to funding
                return True, 10, f"Funding supports trade ({funding_pct:.3f}%)"
        
        return True, 10, f"Funding neutral ({funding_pct:.3f}%)"
    
    def _check_open_interest(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Check open interest trend"""
        
        oi = data.get("open_interest", 0)
        
        # In production, would track OI history
        # Simplified for now
        if oi > 0:
            return True, 10, "OI positive"
        else:
            return True, 5, "OI data unavailable"
    
    def _check_rsi_divergence(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """Check RSI divergence"""
        
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"
        
        closes = [c[4] for c in ohlcv]
        
        from analysis.divergence import DivergenceDetector
        detector = DivergenceDetector()
        result = detector.detect_all(ohlcv)
        
        if direction == "LONG" and result.rsi_divergence[1] == "BULLISH":
            return True, 15, "Bullish RSI divergence"
        elif direction == "SHORT" and result.rsi_divergence[1] == "BEARISH":
            return True, 15, "Bearish RSI divergence"
        elif result.rsi_divergence[0]:
            return True, 10, f"RSI divergence: {result.rsi_divergence[1]}"
        else:
            return False, 5, "No RSI divergence"
    
    def _check_ema_stack(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """Check EMA alignment"""
        
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 50:
            return False, 0, "Insufficient data"
        
        closes = [c[4] for c in ohlcv[-50:]]
        
        ema9 = self.analyzer.calculate_ema(closes, 9)
        ema21 = self.analyzer.calculate_ema(closes, 21)
        ema200 = self.analyzer.calculate_ema(closes, 200)
        current = closes[-1]
        
        # Check alignment
        bullish_stack = ema9 > ema21 > ema200
        bearish_stack = ema9 < ema21 < ema200
        
        if direction == "LONG" and bullish_stack:
            return True, 10, "Bullish EMA stack"
        elif direction == "SHORT" and bearish_stack:
            return True, 10, "Bearish EMA stack"
        elif bullish_stack:
            return True, 7, "Bullish stack (opposite direction)"
        elif bearish_stack:
            return True, 7, "Bearish stack (opposite direction)"
        else:
            return False, 3, "No clear EMA stack"
    
    def _check_atr_percent(
        self,
        data: Dict[str, Any]
    ) -> Tuple[bool, int, str]:
        """Check ATR percentage"""
        
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 14:
            return False, 0, "Insufficient data"
        
        atr = self.analyzer.calculate_atr(ohlcv)
        current_price = ohlcv[-1][4]
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
        
        # Check if in acceptable range
        if config.MIN_ATR_PCT <= atr_pct <= config.MAX_ATR_PCT:
            return True, 10, f"ATR {atr_pct:.2f}% in range"
        elif atr_pct < config.MIN_ATR_PCT:
            return False, 5, f"ATR too low: {atr_pct:.2f}%"
        else:
            return False, 5, f"ATR too high: {atr_pct:.2f}%"
    
    def _check_vwap_position(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """Check position relative to VWAP"""
        
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
        else:
            return False, 1, "Price away from VWAP"
    
    def _check_support_resistance(
        self,
        data: Dict[str, Any],
        direction: Optional[str]
    ) -> Tuple[bool, int, str]:
        """Check proximity to support/resistance"""
        
        ohlcv = data.get("ohlcv", {}).get("1h", [])
        if len(ohlcv) < 20:
            return False, 0, "Insufficient data"
        
        from analysis.structure import StructureDetector
        detector = StructureDetector()
        
        levels = detector.get_support_resistance(ohlcv)
        current = ohlcv[-1][4]
        
        nearest_type, nearest_level, distance = detector.get_nearest_level(
            current, levels
        )
        
        if direction == "LONG" and nearest_type == "support":
            return True, 5, f"Near support ({distance:.2f}%)"
        elif direction == "SHORT" and nearest_type == "resistance":
            return True, 5, f"Near resistance ({distance:.2f}%)"
        elif nearest_level:
            return True, 3, f"Near {nearest_type} ({distance:.2f}%)"
        else:
            return False, 1, "No clear S/R levels"
