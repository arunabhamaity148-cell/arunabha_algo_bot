"""
ARUNABHA ALGO BOT - Filter Orchestrator
Coordinates all filter tiers and produces final decision
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

import config
from core.constants import MarketType, SignalGrade
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
        Evaluate all filters with detailed logging
        """
        self.stats["total_evaluations"] += 1
        self.stats["last_evaluation"] = datetime.now().isoformat()
        
        logger.info(f"🔍 ===== FILTER EVALUATION START: {symbol} =====")
        
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
        
        # ========== TIER 1 - MANDATORY FILTERS ==========
        logger.info("📊 TIER 1: Mandatory filters")
        tier1_passed, tier1_results = self.tier1.evaluate_all(
            symbol, direction, market_type, btc_regime, data
        )
        result["tier1"] = tier1_results
        
        # Log each Tier1 result
        for filter_name, filter_result in tier1_results.items():
            status = "✅" if filter_result["passed"] else "❌"
            logger.info(f"   {status} {filter_name}: {filter_result['message']}")
        
        if not tier1_passed:
            failed = [k for k, v in tier1_results.items() if not v["passed"]]
            result["reason"] = f"Tier1 filters failed: {', '.join(failed)}"
            result["grade"] = "D"
            logger.info(f"❌ TIER 1 FAILED: {', '.join(failed)}")
            logger.info(f"🔍 ===== FILTER EVALUATION END: {symbol} - NO SIGNAL =====\n")
            return result
        
        logger.info("✅ TIER 1 PASSED - All mandatory filters OK")
        self.stats["tier1_passed"] += 1
        
        # ========== TIER 2 - QUALITY FILTERS ==========
        logger.info("📊 TIER 2: Quality filters (weighted scoring)")
        tier2_passed, tier2_score, tier2_results = self.tier2.evaluate_all(
            symbol, direction, market_type, data
        )
        result["tier2"] = tier2_results
        result["score"] = tier2_score
        
        # Log top Tier2 filters
        passed_tier2 = [(k, v) for k, v in tier2_results.items() if v["passed"]]
        if passed_tier2:
            logger.info(f"   ✅ Passed: {len(passed_tier2)}/{len(tier2_results)} filters")
            for name, res in passed_tier2[:3]:  # Show top 3
                logger.info(f"      ✓ {name}: {res['message']} (+{res['score']} pts)")
        
        if not tier2_passed:
            result["reason"] = f"Tier2 score too low: {tier2_score}% (need {config.MIN_TIER2_SCORE}%)"
            result["grade"] = "C"
            logger.info(f"❌ TIER 2 FAILED: Score {tier2_score}% < {config.MIN_TIER2_SCORE}%")
            logger.info(f"🔍 ===== FILTER EVALUATION END: {symbol} - NO SIGNAL =====\n")
            return result
        
        logger.info(f"✅ TIER 2 PASSED: Score {tier2_score}%")
        self.stats["tier2_passed"] += 1
        
        # ========== TIER 3 - BONUS FILTERS ==========
        logger.info("📊 TIER 3: Bonus filters")
        tier3_bonus, tier3_results = self.tier3.evaluate_all(
            symbol, direction, data
        )
        result["tier3"] = tier3_results
        
        if tier3_bonus > 0:
            logger.info(f"   ✅ Bonus points: +{tier3_bonus}")
            for name, res in tier3_results.items():
                if res["bonus"] > 0:
                    logger.info(f"      ✓ {name}: +{res['bonus']} ({res['message']})")
        else:
            logger.info("   ⏸️ No bonus filters triggered")
        
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
            logger.info(f"✅✅ SIGNAL APPROVED: {symbol} - Grade {grade.value}, Score {final_score}%")
            self.stats["signals_generated"] += 1
        else:
            result["reason"] = f"Final grade too low: {grade.value} (need B or better)"
            logger.info(f"❌ FINAL REJECTED: Grade {grade.value} < B")
        
        logger.info(f"🔍 ===== FILTER EVALUATION END: {symbol} - {'APPROVED' if result['passed'] else 'REJECTED'} =====\n")
        
        return result
    
    def get_summary(self, result: Dict[str, Any]) -> str:
        """Get human-readable filter summary"""
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
        """Get filter statistics"""
        return {
            **self.stats,
            "tier1_success_rate": (self.stats["tier1_passed"] / self.stats["total_evaluations"] * 100) if self.stats["total_evaluations"] > 0 else 0,
            "tier2_success_rate": (self.stats["tier2_passed"] / self.stats["tier1_passed"] * 100) if self.stats["tier1_passed"] > 0 else 0,
            "signal_rate": (self.stats["signals_generated"] / self.stats["total_evaluations"] * 100) if self.stats["total_evaluations"] > 0 else 0
        }