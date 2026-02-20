"""
ARUNABHA ALGO BOT - Filter Orchestrator
Coordinates all filter tiers and produces final decision
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

import config
from core.constants import MarketType, BTCRegime, SignalGrade
from analysis.market_regime import BTCRegimeResult
from filters.tier1_filters import Tier1Filters
from filters.tier2_filters import Tier2Filters
from filters.tier3_filters import Tier3Filters

logger = logging.getLogger(__name__)


class FilterOrchestrator:
    """
    Orchestrates all filter tiers
    """
    
    def __init__(self):
        self.tier1 = Tier1Filters()
        self.tier2 = Tier2Filters()
        self.tier3 = Tier3Filters()
        
        # Statistics
        self.stats = {
            "total_evaluations": 0,
            "tier1_passed": 0,
            "tier2_passed": 0,
            "signals_generated": 0,
            "last_evaluation": None
        }
    
    async def evaluate(
        self,
        symbol: str,
        direction: Optional[str],
        market_type: MarketType,
        btc_regime: BTCRegimeResult,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate all filters
        """
        self.stats["total_evaluations"] += 1
        self.stats["last_evaluation"] = datetime.now().isoformat()
        
        result = {
            "passed": False,
            "tier1": {},
            "tier2": {},
            "tier3": {},
            "score": 0,
            "grade": "D",
            "reason": "",
            "timestamp": datetime.now().isoformat()
        }
        
        # Tier 1 - Mandatory filters
        tier1_passed, tier1_results = self.tier1.evaluate_all(
            symbol, direction, market_type, btc_regime, data
        )
        result["tier1"] = tier1_results
        
        if not tier1_passed:
            result["reason"] = "Tier1 filters failed"
            result["grade"] = "D"
            logger.debug(f"Tier1 failed for {symbol}")
            return result
        
        self.stats["tier1_passed"] += 1
        
        # Tier 2 - Quality filters
        tier2_passed, tier2_score, tier2_results = self.tier2.evaluate_all(
            symbol, direction, market_type, data
        )
        result["tier2"] = tier2_results
        result["score"] = tier2_score
        
        if not tier2_passed:
            result["reason"] = f"Tier2 score too low: {tier2_score}%"
            result["grade"] = "C"
            logger.debug(f"Tier2 failed for {symbol}: {tier2_score}%")
            return result
        
        self.stats["tier2_passed"] += 1
        
        # Tier 3 - Bonus filters
        tier3_bonus, tier3_results = self.tier3.evaluate_all(
            symbol, direction, data
        )
        result["tier3"] = tier3_results
        
        # Calculate final score with bonus
        final_score = min(100, tier2_score + tier3_bonus)
        result["score"] = final_score
        
        # Determine grade
        grade = SignalGrade.from_score(final_score)
        result["grade"] = grade.value
        
        # Final decision
        if grade.can_trade:
            result["passed"] = True
            result["reason"] = f"All filters passed. Score: {final_score}% ({grade.value})"
            self.stats["signals_generated"] += 1
        else:
            result["reason"] = f"Final grade too low: {grade.value}"
        
        return result
    
    def get_summary(self, result: Dict[str, Any]) -> str:
        """
        Get human-readable filter summary
        """
        if not result["passed"]:
            return f"❌ {result['reason']}"
        
        lines = []
        lines.append(f"✅ Score: {result['score']}% | Grade: {result['grade']}")
        
        # Tier1 summary
        tier1_passed = sum(1 for v in result["tier1"].values() if v["passed"])
        lines.append(f"Tier1: {tier1_passed}/5 passed")
        
        # Tier2 top contributors
        if result["tier2"]:
            top_filters = sorted(
                [(k, v) for k, v in result["tier2"].items() if v["passed"]],
                key=lambda x: x[1]["score"],
                reverse=True
            )[:3]
            
            if top_filters:
                filters_str = ", ".join([f.replace("_", " ") for f, _ in top_filters])
                lines.append(f"Key factors: {filters_str}")
        
        # Tier3 bonus
        if result["tier3"]:
            total_bonus = sum(v["bonus"] for v in result["tier3"].values())
            if total_bonus > 0:
                lines.append(f"Bonus: +{total_bonus}")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get filter statistics
        """
        return {
            **self.stats,
            "tier1_success_rate": (self.stats["tier1_passed"] / self.stats["total_evaluations"] * 100) if self.stats["total_evaluations"] > 0 else 0,
            "tier2_success_rate": (self.stats["tier2_passed"] / self.stats["tier1_passed"] * 100) if self.stats["tier1_passed"] > 0 else 0,
            "signal_rate": (self.stats["signals_generated"] / self.stats["total_evaluations"] * 100) if self.stats["total_evaluations"] > 0 else 0
        }
