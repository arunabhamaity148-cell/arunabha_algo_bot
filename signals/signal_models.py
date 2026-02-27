"""
ARUNABHA ALGO BOT - Signal Models
Dataclasses for Signal and SignalResult used across the bot.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class Signal:
    """Represents a single trading signal"""
    symbol: str
    direction: str                    # "LONG" or "SHORT"
    entry: float
    stop_loss: float
    take_profit: float
    rr_ratio: float
    grade: str                        # "A+", "A", "B+", "B", "C", "D"
    score: float
    confidence: int                   # 0-100
    structure_strength: str           # "STRONG", "MODERATE", "WEAK"
    market_type: str
    key_factors: List[str] = field(default_factory=list)
    levels: Dict[str, float] = field(default_factory=dict)
    position_size: Dict[str, Any] = field(default_factory=dict)
    sentiment: Optional[Dict] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "rr_ratio": self.rr_ratio,
            "grade": self.grade,
            "score": self.score,
            "confidence": self.confidence,
            "structure_strength": self.structure_strength,
            "market_type": self.market_type,
            "key_factors": self.key_factors,
            "levels": self.levels,
            "position_size": self.position_size,
            "sentiment": self.sentiment,
            "timestamp": self.timestamp,
        }


@dataclass
class SignalResult:
    """Result from signal generation attempt"""
    success: bool
    signal: Optional[Signal] = None
    reason: str = ""
    tier1_passed: bool = False
    tier2_score: float = 0.0
    tier3_bonus: float = 0.0
    filter_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "signal": self.signal.to_dict() if self.signal else None,
            "reason": self.reason,
            "tier1_passed": self.tier1_passed,
            "tier2_score": self.tier2_score,
            "tier3_bonus": self.tier3_bonus,
            "filter_details": self.filter_details,
        }
