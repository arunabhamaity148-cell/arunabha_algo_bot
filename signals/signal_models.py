"""
ARUNABHA ALGO BOT - Signal Models
Data models for signals
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class Signal:
    """Core signal data model"""
    
    # Required fields
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry: float
    stop_loss: float
    take_profit: float
    
    # Optional fields with defaults
    rr_ratio: float = 0.0
    score: int = 0
    grade: str = "D"
    confidence: int = 0
    market_type: str = "unknown"
    btc_regime: str = "unknown"
    structure_strength: str = "WEAK"
    filters_passed: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Extended data
    levels: Dict[str, float] = field(default_factory=dict)
    key_factors: List[str] = field(default_factory=list)
    position_size: Dict[str, Any] = field(default_factory=dict)
    filter_summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "rr_ratio": self.rr_ratio,
            "score": self.score,
            "grade": self.grade,
            "confidence": self.confidence,
            "market_type": self.market_type,
            "btc_regime": self.btc_regime,
            "structure_strength": self.structure_strength,
            "filters_passed": self.filters_passed,
            "timestamp": self.timestamp,
            "levels": self.levels,
            "key_factors": self.key_factors,
            "position_size": self.position_size,
            "filter_summary": self.filter_summary
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Signal":
        """Create from dictionary"""
        return cls(
            symbol=data.get("symbol", ""),
            direction=data.get("direction", ""),
            entry=data.get("entry", 0.0),
            stop_loss=data.get("stop_loss", 0.0),
            take_profit=data.get("take_profit", 0.0),
            rr_ratio=data.get("rr_ratio", 0.0),
            score=data.get("score", 0),
            grade=data.get("grade", "D"),
            confidence=data.get("confidence", 0),
            market_type=data.get("market_type", "unknown"),
            btc_regime=data.get("btc_regime", "unknown"),
            structure_strength=data.get("structure_strength", "WEAK"),
            filters_passed=data.get("filters_passed", 0),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            levels=data.get("levels", {}),
            key_factors=data.get("key_factors", []),
            position_size=data.get("position_size", {}),
            filter_summary=data.get("filter_summary", "")
        )


@dataclass
class SignalResult:
    """Result of signal processing"""
    
    signal: Optional[Signal]
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    quality: Dict[str, Any]
    processing_time_ms: float
    
    @classmethod
    def success(cls, signal: Signal, quality: Dict, time_ms: float) -> "SignalResult":
        """Create successful result"""
        return cls(
            signal=signal,
            is_valid=True,
            errors=[],
            warnings=quality.get("warnings", []),
            quality=quality,
            processing_time_ms=time_ms
        )
    
    @classmethod
    def failure(cls, errors: List[str], time_ms: float) -> "SignalResult":
        """Create failure result"""
        return cls(
            signal=None,
            is_valid=False,
            errors=errors,
            warnings=[],
            quality={},
            processing_time_ms=time_ms
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "quality": self.quality,
            "processing_time_ms": self.processing_time_ms,
            "signal": self.signal.to_dict() if self.signal else None
        }
