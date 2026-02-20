"""
ARUNABHA ALGO BOT - Confidence Calculator
Calculates confidence levels for signals
"""

import logging
from typing import Dict, Any, Tuple

import config
from core.constants import SignalGrade, MarketType

logger = logging.getLogger(__name__)


class ConfidenceCalculator:
    """
    Calculates confidence level for signals
    """
    
    def __init__(self):
        self.base_confidence = {
            SignalGrade.APLUS: 95,
            SignalGrade.A: 85,
            SignalGrade.BPLUS: 75,
            SignalGrade.B: 65,
            SignalGrade.C: 50,
            SignalGrade.D: 30
        }
    
    def calculate(
        self,
        score: int,
        grade: SignalGrade,
        market_type: MarketType,
        btc_regime: Any
    ) -> int:
        """
        Calculate final confidence percentage
        """
        # Start with base confidence for grade
        confidence = self.base_confidence.get(grade, 50)
        
        # Adjust based on market type
        confidence = self._adjust_for_market(confidence, market_type)
        
        # Adjust based on BTC regime
        confidence = self._adjust_for_btc(confidence, btc_regime)
        
        # Adjust based on score (if score higher than grade typical)
        grade_typical = self._get_typical_score(grade)
        if score > grade_typical:
            confidence += min(10, (score - grade_typical) // 2)
        
        # Ensure within bounds
        return max(0, min(100, confidence))
    
    def _adjust_for_market(self, confidence: int, market_type: MarketType) -> int:
        """Adjust confidence based on market type"""
        
        adjustments = {
            MarketType.TRENDING: +5,
            MarketType.CHOPPY: -10,
            MarketType.HIGH_VOL: -15,
            MarketType.UNKNOWN: -5
        }
        
        adj = adjustments.get(market_type, 0)
        return confidence + adj
    
    def _adjust_for_btc(self, confidence: int, btc_regime: Any) -> int:
        """Adjust confidence based on BTC regime"""
        
        if not btc_regime:
            return confidence - 10
        
        # Strong trend alignment
        if btc_regime.strength == "STRONG" and btc_regime.can_trade:
            return confidence + 10
        elif btc_regime.strength == "MODERATE":
            return confidence + 5
        elif not btc_regime.can_trade:
            return confidence - 20
        else:
            return confidence - 5
    
    def _get_typical_score(self, grade: SignalGrade) -> int:
        """Get typical score for a grade"""
        
        typical = {
            SignalGrade.APLUS: 95,
            SignalGrade.A: 85,
            SignalGrade.BPLUS: 75,
            SignalGrade.B: 65,
            SignalGrade.C: 55,
            SignalGrade.D: 45
        }
        
        return typical.get(grade, 50)
    
    def get_confidence_level(self, confidence: int) -> str:
        """Get confidence level description"""
        
        if confidence >= 90:
            return "EXTREME_HIGH"
        elif confidence >= 80:
            return "VERY_HIGH"
        elif confidence >= 70:
            return "HIGH"
        elif confidence >= 60:
            return "MODERATE"
        elif confidence >= 50:
            return "LOW"
        else:
            return "VERY_LOW"
    
    def get_position_size_multiplier(self, confidence: int) -> float:
        """Get position size multiplier based on confidence"""
        
        if confidence >= 90:
            return 1.0
        elif confidence >= 80:
            return 0.9
        elif confidence >= 70:
            return 0.8
        elif confidence >= 60:
            return 0.6
        elif confidence >= 50:
            return 0.4
        else:
            return 0.2
    
    def should_alert(self, confidence: int, grade: SignalGrade) -> bool:
        """Determine if signal should trigger alert"""
        
        # Always alert for high grades
        if grade in [SignalGrade.APLUS, SignalGrade.A]:
            return True
        
        # Alert for B+ with good confidence
        if grade == SignalGrade.BPLUS and confidence >= 70:
            return True
        
        # Alert for B only with very high confidence
        if grade == SignalGrade.B and confidence >= 80:
            return True
        
        return False
