"""
ARUNABHA ALGO BOT - Signal Scorer
Calculates signal scores and grades
"""

import logging
from typing import Dict, Any, Tuple

import config
from core.constants import SignalGrade, MarketType
from analysis.structure import StructureResult

logger = logging.getLogger(__name__)


class SignalScorer:
    """
    Calculates signal scores and assigns grades
    """
    
    def __init__(self):
        self.weights = {
            "tier2_score": 0.7,
            "structure_strength": 0.2,
            "bonus_points": 0.1
        }
    
    def calculate(
        self,
        filter_result: Dict[str, Any],
        structure: StructureResult,
        market_type: MarketType
    ) -> Dict[str, Any]:
        """
        Calculate final signal score and grade
        """
        
        # Get base score from tier2 filters
        tier2_score = filter_result.get("score", 0)
        
        # Get bonus from tier3
        tier3_bonus = 0
        if "tier3" in filter_result:
            tier3_bonus = sum(v.get("bonus", 0) for v in filter_result["tier3"].values())
        
        # Structure strength score
        structure_score = self._score_structure(structure)
        
        # Calculate weighted score
        weighted_score = (
            tier2_score * self.weights["tier2_score"] +
            structure_score * self.weights["structure_strength"] +
            tier3_bonus * self.weights["bonus_points"]
        )
        
        # Apply market type modifier
        final_score = self._apply_market_modifier(weighted_score, market_type)
        
        # Determine grade
        grade = SignalGrade.from_score(final_score)
        
        return {
            "score": round(final_score, 1),
            "grade": grade,
            "components": {
                "tier2_score": round(tier2_score, 1),
                "structure_score": round(structure_score, 1),
                "bonus_points": tier3_bonus
            },
            "weighted_score": round(weighted_score, 1)
        }
    
    def _score_structure(self, structure: StructureResult) -> float:
        """Convert structure strength to score"""
        
        strength_scores = {
            "STRONG": 90,
            "MODERATE": 70,
            "WEAK": 50
        }
        
        base_score = strength_scores.get(structure.strength, 50)
        
        # Bonus for BOS/CHoCH
        if structure.bos_detected:
            base_score += 10
        if structure.choch_detected:
            base_score += 15
        
        return min(100, base_score)
    
    def _apply_market_modifier(self, score: float, market_type: MarketType) -> float:
        """Apply market type modifier to score"""
        
        modifiers = {
            MarketType.TRENDING: 1.0,    # No modifier
            MarketType.CHOPPY: 0.9,      # Slight penalty
            MarketType.HIGH_VOL: 0.8,     # Larger penalty
            MarketType.UNKNOWN: 0.85
        }
        
        modifier = modifiers.get(market_type, 0.9)
        return score * modifier
    
    def get_grade_requirements(self, grade: SignalGrade) -> Dict[str, Any]:
        """Get requirements for a specific grade"""
        
        requirements = {
            SignalGrade.APLUS: {
                "min_score": 90,
                "min_rr": 2.5,
                "structure_required": "STRONG",
                "description": "Exceptional signal - must trade"
            },
            SignalGrade.A: {
                "min_score": 80,
                "min_rr": 2.0,
                "structure_required": "STRONG",
                "description": "Strong signal - should trade"
            },
            SignalGrade.BPLUS: {
                "min_score": 70,
                "min_rr": 1.8,
                "structure_required": "MODERATE",
                "description": "Good signal - consider trading"
            },
            SignalGrade.B: {
                "min_score": 60,
                "min_rr": 1.5,
                "structure_required": "MODERATE",
                "description": "Decent signal - could trade"
            },
            SignalGrade.C: {
                "min_score": 50,
                "min_rr": 1.2,
                "structure_required": "WEAK",
                "description": "Weak signal - avoid"
            },
            SignalGrade.D: {
                "min_score": 0,
                "min_rr": 1.0,
                "structure_required": "WEAK",
                "description": "Poor signal - do not trade"
            }
        }
        
        return requirements.get(grade, requirements[SignalGrade.D])
    
    def is_tradeable(self, score: float, rr_ratio: float, structure: StructureResult) -> Tuple[bool, str]:
        """Determine if signal is tradeable"""
        
        grade = SignalGrade.from_score(score)
        reqs = self.get_grade_requirements(grade)
        
        # Check score
        if score < config.MIN_SIGNAL_SCORE:
            return False, f"Score too low: {score} < {config.MIN_SIGNAL_SCORE}"
        
        # Check RR
        if rr_ratio < reqs["min_rr"]:
            return False, f"RR too low: {rr_ratio} < {reqs['min_rr']}"
        
        # Check structure strength
        strength_scores = {"STRONG": 3, "MODERATE": 2, "WEAK": 1}
        req_strength = strength_scores.get(reqs["structure_required"], 1)
        act_strength = strength_scores.get(structure.strength, 1)
        
        if act_strength < req_strength:
            return False, f"Structure too weak: {structure.strength} < {reqs['structure_required']}"
        
        return True, f"Tradeable: {grade.value}"
