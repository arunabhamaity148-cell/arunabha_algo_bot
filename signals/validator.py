"""
ARUNABHA ALGO BOT - Signal Validator
Validates signals before sending
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

import config
from core.constants import TradeDirection

logger = logging.getLogger(__name__)


class SignalValidator:
    """
    Validates signals for consistency and completeness
    """
    
    def __init__(self):
        self.validation_rules = {
            "price_positive": lambda s: s.get("entry", 0) > 0,
            "stop_loss_different": self._check_sl_different,
            "take_profit_different": self._check_tp_different,
            "rr_reasonable": self._check_rr_reasonable,
            "score_valid": lambda s: 0 <= s.get("score", 0) <= 100,
            "confidence_valid": lambda s: 0 <= s.get("confidence", 0) <= 100,
            "timestamp_recent": self._check_timestamp_recent
        }
    
    def validate(self, signal: Dict) -> Tuple[bool, List[str]]:
        """
        Validate a signal
        Returns: (is_valid, errors)
        """
        errors = []
        
        # Check required fields
        required_fields = ["symbol", "direction", "entry", "stop_loss", "take_profit"]
        for field in required_fields:
            if field not in signal:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return False, errors
        
        # Run validation rules
        for rule_name, rule_func in self.validation_rules.items():
            if not rule_func(signal):
                errors.append(f"Failed validation: {rule_name}")
        
        # Check direction validity
        if signal["direction"] not in ["LONG", "SHORT"]:
            errors.append(f"Invalid direction: {signal['direction']}")
        
        return len(errors) == 0, errors
    
    def _check_sl_different(self, signal: Dict) -> bool:
        """Check if stop loss is different from entry"""
        entry = signal.get("entry", 0)
        sl = signal.get("stop_loss", 0)
        
        if entry == 0 or sl == 0:
            return False
        
        return abs(entry - sl) > 0.01 * entry  # At least 0.01% difference
    
    def _check_tp_different(self, signal: Dict) -> bool:
        """Check if take profit is different from entry"""
        entry = signal.get("entry", 0)
        tp = signal.get("take_profit", 0)
        
        if entry == 0 or tp == 0:
            return False
        
        return abs(entry - tp) > 0.01 * entry  # At least 0.01% difference
    
    def _check_rr_reasonable(self, signal: Dict) -> bool:
        """Check if RR ratio is reasonable"""
        rr = signal.get("rr_ratio", 0)
        return config.MIN_RR_RATIO <= rr <= 10  # Upper bound sanity check
    
    def _check_timestamp_recent(self, signal: Dict) -> bool:
        """Check if timestamp is recent"""
        ts = signal.get("timestamp")
        if not ts:
            return False
        
        try:
            signal_time = datetime.fromisoformat(ts)
            now = datetime.now()
            
            # Signal shouldn't be more than 5 minutes old
            return (now - signal_time).total_seconds() < 300
        except:
            return False
    
    def validate_for_symbol(
        self,
        signal: Dict,
        symbol: str,
        last_signals: Dict[str, datetime]
    ) -> Tuple[bool, str]:
        """Validate symbol-specific rules"""
        
        # Check cooldown
        if symbol in last_signals:
            elapsed = (datetime.now() - last_signals[symbol]).total_seconds() / 60
            if elapsed < config.COOLDOWN_MINUTES:
                return False, f"Cooldown: {elapsed:.1f}/{config.COOLDOWN_MINUTES} minutes"
        
        # Check if same direction as last signal (avoid repeating)
        if symbol in last_signals:
            # Optional: check if same direction within short time
            pass
        
        return True, "OK"
    
    def check_signal_quality(self, signal: Dict) -> Dict[str, Any]:
        """
        Provide detailed quality assessment
        """
        quality = {
            "overall": "GOOD",
            "checks": {},
            "warnings": []
        }
        
        # Check RR
        rr = signal.get("rr_ratio", 0)
        if rr >= 3:
            quality["checks"]["rr"] = "EXCELLENT"
        elif rr >= 2:
            quality["checks"]["rr"] = "GOOD"
        elif rr >= 1.5:
            quality["checks"]["rr"] = "ACCEPTABLE"
        else:
            quality["checks"]["rr"] = "POOR"
            quality["warnings"].append("Low RR ratio")
        
        # Check score
        score = signal.get("score", 0)
        if score >= 80:
            quality["checks"]["score"] = "EXCELLENT"
        elif score >= 70:
            quality["checks"]["score"] = "GOOD"
        elif score >= 60:
            quality["checks"]["score"] = "ACCEPTABLE"
        else:
            quality["checks"]["score"] = "POOR"
            quality["warnings"].append("Low score")
        
        # Check confidence
        confidence = signal.get("confidence", 0)
        if confidence >= 80:
            quality["checks"]["confidence"] = "HIGH"
        elif confidence >= 60:
            quality["checks"]["confidence"] = "MEDIUM"
        else:
            quality["checks"]["confidence"] = "LOW"
            quality["warnings"].append("Low confidence")
        
        # Check structure
        structure = signal.get("structure_strength", "WEAK")
        if structure == "STRONG":
            quality["checks"]["structure"] = "STRONG"
        elif structure == "MODERATE":
            quality["checks"]["structure"] = "MODERATE"
        else:
            quality["checks"]["structure"] = "WEAK"
            quality["warnings"].append("Weak structure")
        
        # Overall assessment
        if len(quality["warnings"]) == 0:
            quality["overall"] = "EXCELLENT"
        elif len(quality["warnings"]) <= 2:
            quality["overall"] = "GOOD"
        else:
            quality["overall"] = "POOR"
        
        return quality
