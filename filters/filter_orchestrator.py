"""
ARUNABHA ALGO BOT - Filter Orchestrator v5.0
=============================================
UPGRADE:
- tier2_threshold_override param for Adaptive Threshold support
  engine passes self._adaptive_threshold → overrides config.MIN_TIER2_SCORE
- evaluate() is now sync (was async but had no awaits)
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

    def __init__(self):
        self.tier1 = Tier1Filters()
        self.tier2 = Tier2Filters()
        self.tier3 = Tier3Filters()
        self.stats = {
            "total_evaluations": 0,
            "tier1_passed": 0,
            "tier2_passed": 0,
            "signals_generated": 0,
            "last_evaluation": None,
        }

    def evaluate(
        self,
        symbol: str,
        direction: Optional[str],
        market_type: MarketType,
        btc_regime: BTCRegimeResult,
        data: Dict[str, Any],
        tier2_threshold_override: Optional[float] = None,   # ← NEW: adaptive threshold
    ) -> Dict[str, Any]:
        """
        Evaluate all filter tiers.
        tier2_threshold_override: if provided, overrides config.MIN_TIER2_SCORE
        """
        self.stats["total_evaluations"] += 1
        self.stats["last_evaluation"] = datetime.now().isoformat()

        tier2_min = tier2_threshold_override if tier2_threshold_override is not None else config.MIN_TIER2_SCORE

        logger.info(f"🔍 FILTER: {symbol} | threshold={tier2_min:.0f}%")

        result = {
            "passed": False,
            "tier1": {},
            "tier2": {},
            "tier3": {},
            "score": 0,
            "grade": "D",
            "reason": "",
            "tier2_threshold_used": tier2_min,
            "timestamp": datetime.now().isoformat(),
        }

        # ── TIER 1 ───────────────────────────────────────────────
        tier1_passed, tier1_results = self.tier1.evaluate_all(
            symbol, direction, market_type, btc_regime, data
        )
        result["tier1"] = tier1_results

        for fn, fr in tier1_results.items():
            status = "✅" if fr["passed"] else "❌"
            logger.info(f"   {status} T1/{fn}: {fr['message']}")

        if not tier1_passed:
            failed = [k for k, v in tier1_results.items() if not v["passed"]]
            result["reason"] = f"Tier1 failed: {', '.join(failed)}"
            logger.info(f"❌ T1 FAIL: {', '.join(failed)}")
            return result

        logger.info("✅ T1 PASS")
        self.stats["tier1_passed"] += 1

        # ── TIER 2 ───────────────────────────────────────────────
        tier2_passed, tier2_score, tier2_results = self.tier2.evaluate_all(
            symbol, direction, market_type, data
        )
        result["tier2"] = tier2_results
        result["score"] = tier2_score

        logger.info(f"   T2 score: {tier2_score:.1f}% (need {tier2_min:.0f}%)")

        # Use adaptive threshold
        tier2_ok = tier2_score >= tier2_min
        if not tier2_ok:
            result["reason"] = (
                f"Tier2 score {tier2_score:.1f}% < threshold {tier2_min:.0f}% "
                f"{'(adaptive)' if tier2_threshold_override else ''}"
            )
            result["grade"] = "C"
            logger.info(f"❌ T2 FAIL: {tier2_score:.1f}%")
            return result

        logger.info(f"✅ T2 PASS: {tier2_score:.1f}%")
        self.stats["tier2_passed"] += 1

        # ── TIER 3 ───────────────────────────────────────────────
        tier3_bonus, tier3_results = self.tier3.evaluate_all(
            symbol, direction, data
        )
        result["tier3"] = tier3_results

        if tier3_bonus > 0:
            logger.info(f"   T3 bonus: +{tier3_bonus}")

        final_score = min(100, tier2_score + tier3_bonus)
        result["score"] = final_score

        grade = SignalGrade.from_score(final_score)
        result["grade"] = grade.value

        if grade.can_trade:
            result["passed"] = True
            result["reason"] = f"Score: {final_score:.0f}% ({grade.value})"
            logger.info(f"✅✅ APPROVED: {symbol} Grade={grade.value} Score={final_score:.0f}%")
            self.stats["signals_generated"] += 1
        else:
            result["reason"] = f"Grade {grade.value} below minimum"
            logger.info(f"❌ GRADE TOO LOW: {grade.value}")

        return result

    def get_summary(self, result: Dict[str, Any]) -> str:
        if not result["passed"]:
            return f"❌ {result['reason']}"
        lines = [f"✅ Score: {result['score']:.0f}% | Grade: {result['grade']}"]
        tier1_passed = sum(1 for v in result["tier1"].values() if v["passed"])
        lines.append(f"Tier1: {tier1_passed}/{len(result['tier1'])} passed")
        if result["tier2"]:
            top = sorted(
                [(k, v) for k, v in result["tier2"].items() if v["passed"]],
                key=lambda x: x[1]["score"], reverse=True
            )[:3]
            if top:
                lines.append(f"Key: {', '.join(f.replace('_',' ') for f, _ in top)}")
        if result["tier3"]:
            bonus = sum(v["bonus"] for v in result["tier3"].values())
            if bonus > 0:
                lines.append(f"Bonus: +{bonus}")
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        t = self.stats["total_evaluations"]
        t1 = self.stats["tier1_passed"]
        return {
            **self.stats,
            "tier1_success_rate": (t1 / t * 100) if t > 0 else 0,
            "tier2_success_rate": (self.stats["tier2_passed"] / t1 * 100) if t1 > 0 else 0,
            "signal_rate": (self.stats["signals_generated"] / t * 100) if t > 0 else 0,
        }
