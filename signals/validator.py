"""
ARUNABHA ALGO BOT - Signal Validator v4.2

FIXES:
- SL minimum distance check: entry থেকে SL অন্তত 0.3% দূরে থাকতে হবে
- TP minimum distance check: entry থেকে TP অন্তত 0.5% দূরে থাকতে হবে
- SL direction check: LONG-এ SL অবশ্যই entry-র নিচে, SHORT-এ উপরে
- TP direction check: LONG-এ TP অবশ্যই entry-র উপরে, SHORT-এ নিচে
- RR ratio upper bound: 15 থেকে 8-এ নামানো হয়েছে (15 unrealistic)
- Grade D signal block করা হয়েছে
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta

import config
from core.constants import TradeDirection, SignalGrade

logger = logging.getLogger(__name__)


class SignalValidator:
    """
    Validates signals for consistency, safety and completeness
    """

    def __init__(self):
        # Minimum distances as percentage of entry price
        self.min_sl_distance_pct = 0.3   # SL অন্তত 0.3% দূরে
        self.min_tp_distance_pct = 0.5   # TP অন্তত 0.5% দূরে
        self.max_rr_ratio = 8.0          # RR > 8 মানে TP unrealistic

    def validate(self, signal: Dict) -> Tuple[bool, List[str]]:
        """
        Validate a signal — সব checks pass করলেই signal forward হবে
        Returns: (is_valid, list_of_errors)
        """
        errors = []

        # --- 1. Required fields ---
        required_fields = ["symbol", "direction", "entry", "stop_loss", "take_profit", "score", "grade"]
        for field in required_fields:
            if field not in signal or signal[field] is None:
                errors.append(f"Missing required field: {field}")

        if errors:
            return False, errors

        entry = float(signal["entry"])
        sl = float(signal["stop_loss"])
        tp = float(signal["take_profit"])
        direction = signal["direction"]
        score = float(signal.get("score", 0))
        grade = signal.get("grade", "D")

        # --- 2. Price sanity ---
        if entry <= 0:
            errors.append(f"Invalid entry price: {entry}")
        if sl <= 0:
            errors.append(f"Invalid stop loss: {sl}")
        if tp <= 0:
            errors.append(f"Invalid take profit: {tp}")

        if errors:
            return False, errors

        # --- 3. Direction validity ---
        if direction not in ["LONG", "SHORT"]:
            errors.append(f"Invalid direction: {direction}")
            return False, errors

        # --- 4. SL direction check ---
        # LONG trade: SL অবশ্যই entry-র নিচে
        # SHORT trade: SL অবশ্যই entry-র উপরে
        if direction == "LONG":
            if sl >= entry:
                errors.append(
                    f"LONG signal: SL ({sl:.6f}) must be BELOW entry ({entry:.6f})"
                )
        else:  # SHORT
            if sl <= entry:
                errors.append(
                    f"SHORT signal: SL ({sl:.6f}) must be ABOVE entry ({entry:.6f})"
                )

        # --- 5. TP direction check ---
        if direction == "LONG":
            if tp <= entry:
                errors.append(
                    f"LONG signal: TP ({tp:.6f}) must be ABOVE entry ({entry:.6f})"
                )
        else:  # SHORT
            if tp >= entry:
                errors.append(
                    f"SHORT signal: TP ({tp:.6f}) must be BELOW entry ({entry:.6f})"
                )

        # --- 6. Minimum SL distance ---
        sl_distance_pct = abs(entry - sl) / entry * 100
        if sl_distance_pct < self.min_sl_distance_pct:
            errors.append(
                f"SL too tight: {sl_distance_pct:.3f}% < {self.min_sl_distance_pct}% minimum"
            )

        # --- 7. Minimum TP distance ---
        tp_distance_pct = abs(tp - entry) / entry * 100
        if tp_distance_pct < self.min_tp_distance_pct:
            errors.append(
                f"TP too close: {tp_distance_pct:.3f}% < {self.min_tp_distance_pct}% minimum"
            )

        # --- 8. RR ratio checks ---
        rr = signal.get("rr_ratio", 0)
        if rr < config.MIN_RR_RATIO:
            errors.append(f"RR too low: {rr:.2f} < {config.MIN_RR_RATIO} minimum")
        if rr > self.max_rr_ratio:
            errors.append(f"RR unrealistic: {rr:.2f} > {self.max_rr_ratio} maximum")

        # --- 9. Score check ---
        if score < config.MIN_SIGNAL_SCORE:
            errors.append(f"Score too low: {score:.1f} < {config.MIN_SIGNAL_SCORE} minimum")

        # --- 10. Grade D block ---
        if grade == "D":
            errors.append("Grade D signals are blocked — not tradeable")

        # --- 11. Confidence check ---
        confidence = signal.get("confidence", 0)
        if confidence < 30:
            errors.append(f"Confidence too low: {confidence} < 30 minimum")

        # --- 12. Timestamp check ---
        ts = signal.get("timestamp")
        if ts:
            try:
                signal_time = datetime.fromisoformat(ts)
                age_seconds = (datetime.now() - signal_time).total_seconds()
                if age_seconds > 300:
                    errors.append(f"Signal too old: {age_seconds:.0f}s > 300s")
            except Exception:
                errors.append("Invalid timestamp format")
        else:
            errors.append("Missing timestamp")

        is_valid = len(errors) == 0

        if not is_valid:
            logger.debug(f"Signal validation failed: {errors}")

        return is_valid, errors

    def validate_for_symbol(
        self,
        signal: Dict,
        symbol: str,
        last_signals: Dict[str, datetime]
    ) -> Tuple[bool, str]:
        """Validate symbol-specific cooldown rules"""

        if symbol in last_signals:
            elapsed = (datetime.now() - last_signals[symbol]).total_seconds() / 60
            if elapsed < config.COOLDOWN_MINUTES:
                return False, f"Cooldown: {elapsed:.1f}/{config.COOLDOWN_MINUTES} minutes"

        return True, "OK"

    def check_signal_quality(self, signal: Dict) -> Dict[str, Any]:
        """
        Detailed quality assessment — Telegram message-এ দেখানো হবে
        """
        quality = {
            "overall": "GOOD",
            "checks": {},
            "warnings": []
        }

        # RR check
        rr = signal.get("rr_ratio", 0)
        if rr >= 3:
            quality["checks"]["rr"] = "EXCELLENT"
        elif rr >= 2:
            quality["checks"]["rr"] = "GOOD"
        elif rr >= 1.5:
            quality["checks"]["rr"] = "ACCEPTABLE"
        else:
            quality["checks"]["rr"] = "POOR"
            quality["warnings"].append(f"Low RR: {rr:.2f}")

        # Score check
        score = signal.get("score", 0)
        if score >= 80:
            quality["checks"]["score"] = "EXCELLENT"
        elif score >= 70:
            quality["checks"]["score"] = "GOOD"
        elif score >= 60:
            quality["checks"]["score"] = "ACCEPTABLE"
        else:
            quality["checks"]["score"] = "POOR"
            quality["warnings"].append(f"Low score: {score:.1f}")

        # Confidence check
        confidence = signal.get("confidence", 0)
        if confidence >= 80:
            quality["checks"]["confidence"] = "HIGH"
        elif confidence >= 60:
            quality["checks"]["confidence"] = "MEDIUM"
        else:
            quality["checks"]["confidence"] = "LOW"
            quality["warnings"].append(f"Low confidence: {confidence}")

        # Structure check
        structure = signal.get("structure_strength", "WEAK")
        if structure == "STRONG":
            quality["checks"]["structure"] = "STRONG"
        elif structure == "MODERATE":
            quality["checks"]["structure"] = "MODERATE"
        else:
            quality["checks"]["structure"] = "WEAK"
            quality["warnings"].append("Weak structure")

        # SL distance check
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        if entry > 0 and sl > 0:
            sl_pct = abs(entry - sl) / entry * 100
            if sl_pct < 0.5:
                quality["warnings"].append(f"Very tight SL: {sl_pct:.2f}%")

        # Overall
        if len(quality["warnings"]) == 0:
            quality["overall"] = "EXCELLENT"
        elif len(quality["warnings"]) == 1:
            quality["overall"] = "GOOD"
        elif len(quality["warnings"]) == 2:
            quality["overall"] = "ACCEPTABLE"
        else:
            quality["overall"] = "POOR"

        return quality
