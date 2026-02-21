"""
ARUNABHA ALGO BOT - Core Constants
Enum definitions and fixed values
"""

from enum import Enum, auto
from typing import Dict, List, Tuple


class Timeframes(str, Enum):
    """Timeframe constants"""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    
    @classmethod
    def list(cls) -> List[str]:
        """Get all timeframe values as strings"""
        return [tf.value for tf in cls]
    
    @classmethod
    def primary(cls) -> str:
        """Get primary timeframe (15m)"""
        return cls.M15.value
    
    @classmethod
    def secondary(cls) -> List[str]:
        """Get secondary timeframes (5m, 1h)"""
        return [cls.M5.value, cls.H1.value]
    
    @classmethod
    def tertiary(cls) -> List[str]:
        """Get tertiary timeframes (4h)"""
        return [cls.H4.value]
    
    @classmethod
    def from_string(cls, tf_str: str) -> "Timeframes":
        """Convert string to Timeframes enum"""
        for tf in cls:
            if tf.value == tf_str:
                return tf
        return cls.M15  # default


class MarketType(str, Enum):
    """Market regime types"""
    TRENDING = "trending"
    CHOPPY = "choppy"
    HIGH_VOL = "high_vol"
    UNKNOWN = "unknown"
    
    @property
    def emoji(self) -> str:
        """Get emoji for market type"""
        return {
            "trending": "📈",
            "choppy": "〰️",
            "high_vol": "⚡",
            "unknown": "❓"
        }[self.value]
    
    @classmethod
    def list(cls) -> List[str]:
        """Get all market types"""
        return [mt.value for mt in cls]


class TradeDirection(str, Enum):
    """Trade direction"""
    LONG = "LONG"
    SHORT = "SHORT"
    
    @property
    def emoji(self) -> str:
        """Get emoji for direction"""
        return "🟢" if self == TradeDirection.LONG else "🔴"
    
    @property
    def opposite(self) -> "TradeDirection":
        """Get opposite direction"""
        return TradeDirection.SHORT if self == TradeDirection.LONG else TradeDirection.LONG


class SignalGrade(str, Enum):
    """Signal quality grades"""
    APLUS = "A+"
    A = "A"
    BPLUS = "B+"
    B = "B"
    C = "C"
    D = "D"
    
    @classmethod
    def from_score(cls, score: int) -> "SignalGrade":
        """Convert score to grade"""
        if score >= 90:
            return cls.APLUS
        elif score >= 80:
            return cls.A
        elif score >= 70:
            return cls.BPLUS
        elif score >= 60:
            return cls.B
        elif score >= 50:
            return cls.C
        else:
            return cls.D
    
    @property
    def emoji(self) -> str:
        """Get emoji for grade"""
        return {
            "A+": "🏆",
            "A": "🌟",
            "B+": "⭐",
            "B": "✨",
            "C": "⚠️",
            "D": "❌"
        }[self.value]
    
    @property
    def can_trade(self) -> bool:
        """Check if grade is tradeable"""
        return self.value in ["A+", "A", "B+", "B"]
    
    @property
    def min_score(self) -> int:
        """Get minimum score for this grade"""
        return {
            "A+": 90,
            "A": 80,
            "B+": 70,
            "B": 60,
            "C": 50,
            "D": 0
        }[self.value]


class SessionType(str, Enum):
    """Trading sessions"""
    ASIA = "asia"
    LONDON = "london"
    NY = "ny"
    OVERLAP = "overlap"
    DEAD = "dead"
    
    @property
    def hours(self) -> Tuple[int, int]:
        """Get session hours (IST)"""
        return {
            "asia": (7, 11),
            "london": (13, 17),
            "ny": (18, 22),
            "overlap": (22, 24),
            "dead": (0, 6)
        }[self.value]
    
    @property
    def is_active(self) -> bool:
        """Check if session is currently active"""
        from datetime import datetime
        import pytz
        
        now = datetime.now(pytz.timezone('Asia/Kolkata')).hour
        start, end = self.hours
        return start <= now < end
    
    @property
    def emoji(self) -> str:
        """Get emoji for session"""
        return {
            "asia": "🌏",
            "london": "🇬🇧",
            "ny": "🗽",
            "overlap": "🔄",
            "dead": "💤"
        }[self.value]
    
    @classmethod
    def current(cls) -> "SessionType":
        """Get current session"""
        from datetime import datetime
        import pytz
        
        hour = datetime.now(pytz.timezone('Asia/Kolkata')).hour
        
        for session in cls:
            start, end = session.hours
            if start <= hour < end:
                return session
        return cls.DEAD


class BTCRegime(str, Enum):
    """Bitcoin regime types"""
    STRONG_BULL = "strong_bull"
    BULL = "bull"
    CHOPPY = "choppy"
    BEAR = "bear"
    STRONG_BEAR = "strong_bear"
    UNKNOWN = "unknown"
    
    @property
    def trend_direction(self) -> str:
        """Get trend direction"""
        if self in [BTCRegime.STRONG_BULL, BTCRegime.BULL]:
            return "UP"
        elif self in [BTCRegime.STRONG_BEAR, BTCRegime.BEAR]:
            return "DOWN"
        else:
            return "SIDEWAYS"
    
    @property
    def can_trade(self) -> bool:
        """Check if regime is tradeable"""
        return self != BTCRegime.UNKNOWN
    
    @property
    def emoji(self) -> str:
        """Get emoji for regime"""
        return {
            "strong_bull": "🚀",
            "bull": "📈",
            "choppy": "〰️",
            "bear": "📉",
            "strong_bear": "💥",
            "unknown": "❓"
        }[self.value]


# Trading pair categories
PAIR_CATEGORIES = {
    "major": ["BTC/USDT", "ETH/USDT"],
    "mid": ["DOGE/USDT", "SOL/USDT"],
    "alt": ["RENDER/USDT", "ZRO/USDT", "MORPHO/USDT", "ETC/USDT"]
}

# Minimum data requirements
MIN_CANDLES = {
    "5m": 50,
    "15m": 50,
    "1h": 30,
    "4h": 20
}

# Default values
DEFAULT_VALUES = {
    "fear_index": 50,
    "funding_rate": 0.0,
    "open_interest": 0.0,
    "volume": 0.0
}

# Error messages
ERROR_MESSAGES = {
    "no_data": "Insufficient data for analysis",
    "btc_block": "BTC regime blocking trade",
    "structure_block": "Structure not confirmed",
    "risk_block": "Risk manager blocked trade",
    "filter_block": "Filters not passed",
    "session_block": "Not in active session"
}

# Signal thresholds
SIGNAL_THRESHOLDS = {
    "min_score": 60,
    "strong_score": 75,
    "min_rr": 1.5,
    "min_volume_ratio": 0.7,
    "max_spread": 0.1
}

# Time in milliseconds
MS_IN_SECOND = 1000
MS_IN_MINUTE = 60 * MS_IN_SECOND
MS_IN_HOUR = 60 * MS_IN_MINUTE
MS_IN_DAY = 24 * MS_IN_HOUR