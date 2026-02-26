"""
ARUNABHA ALGO BOT - Core Constants v4.1

FIXES:
- BUG-22: NY session hours আগে (18, 22) ছিল
  কিন্তু tier1_filters.py এ: elif 17 <= hour < 22 → NY active দেখাত
  এর মানে hour=17 তে filter pass করত কিন্তু session বলত "dead"
  Fix: NY session এখন (17, 22) — scheduler ও 17:00 তে fire করবে
"""

from enum import Enum
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
        return [tf.value for tf in cls]

    @classmethod
    def primary(cls) -> str:
        return cls.M15.value

    @classmethod
    def secondary(cls) -> List[str]:
        return [cls.M5.value, cls.H1.value]

    @classmethod
    def tertiary(cls) -> List[str]:
        return [cls.H4.value]

    @classmethod
    def from_string(cls, tf_str: str) -> "Timeframes":
        for tf in cls:
            if tf.value == tf_str:
                return tf
        return cls.M15


class MarketType(str, Enum):
    """Market regime types"""
    TRENDING = "trending"
    CHOPPY = "choppy"
    HIGH_VOL = "high_vol"
    UNKNOWN = "unknown"

    @property
    def emoji(self) -> str:
        return {
            "trending": "📈",
            "choppy": "〰️",
            "high_vol": "⚡",
            "unknown": "❓"
        }[self.value]

    @classmethod
    def list(cls) -> List[str]:
        return [mt.value for mt in cls]


class TradeDirection(str, Enum):
    """Trade direction"""
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def emoji(self) -> str:
        return "🟢" if self == TradeDirection.LONG else "🔴"

    @property
    def opposite(self) -> "TradeDirection":
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
    def from_score(cls, score: float) -> "SignalGrade":
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
        return {
            "A+": "🏆",
            "A":  "🌟",
            "B+": "⭐",
            "B":  "✨",
            "C":  "⚠️",
            "D":  "❌"
        }[self.value]

    @property
    def can_trade(self) -> bool:
        return self.value in ["A+", "A", "B+", "B"]

    @property
    def min_score(self) -> int:
        return {
            "A+": 90,
            "A":  80,
            "B+": 70,
            "B":  60,
            "C":  50,
            "D":  0
        }[self.value]


class SessionType(str, Enum):
    """
    Trading sessions (IST = UTC+5:30)

    ✅ FIX BUG-22: NY session hours ঠিক করা হয়েছে
    আগে: "ny": (18, 22) → কিন্তু tier1_filters.py 17:00 থেকে NY allow করত
    এখন: "ny": (17, 22) → সব জায়গায় consistent
    """
    ASIA    = "asia"
    LONDON  = "london"
    NY      = "ny"
    OVERLAP = "overlap"
    DEAD    = "dead"

    @property
    def hours(self) -> Tuple[int, int]:
        """Get session hours in IST (start, end)"""
        return {
            "asia":    (7,  11),
            "london":  (13, 17),
            "ny":      (17, 22),   # ✅ FIXED: was (18, 22)
            "overlap": (22, 24),
            "dead":    (0,   7),
        }[self.value]

    @property
    def is_active(self) -> bool:
        """Check if session is currently active"""
        from datetime import datetime
        import pytz
        hour = datetime.now(pytz.timezone('Asia/Kolkata')).hour
        start, end = self.hours
        return start <= hour < end

    @property
    def emoji(self) -> str:
        return {
            "asia":    "🌏",
            "london":  "🇬🇧",
            "ny":      "🗽",
            "overlap": "🔄",
            "dead":    "💤"
        }[self.value]

    @property
    def description(self) -> str:
        start, end = self.hours
        return f"{self.value.upper()} ({start:02d}:00–{end:02d}:00 IST)"

    @classmethod
    def current(cls) -> "SessionType":
        """Get current active session"""
        from datetime import datetime
        import pytz
        hour = datetime.now(pytz.timezone('Asia/Kolkata')).hour
        for session in cls:
            start, end = session.hours
            if start <= hour < end:
                return session
        return cls.DEAD


class BTCRegime(str, Enum):
    """Bitcoin market regime types"""
    STRONG_BULL = "strong_bull"
    BULL        = "bull"
    CHOPPY      = "choppy"
    BEAR        = "bear"
    STRONG_BEAR = "strong_bear"
    UNKNOWN     = "unknown"

    @property
    def trend_direction(self) -> str:
        if self in [BTCRegime.STRONG_BULL, BTCRegime.BULL]:
            return "UP"
        elif self in [BTCRegime.STRONG_BEAR, BTCRegime.BEAR]:
            return "DOWN"
        return "SIDEWAYS"

    @property
    def can_trade(self) -> bool:
        return self != BTCRegime.UNKNOWN

    @property
    def emoji(self) -> str:
        return {
            "strong_bull": "🚀",
            "bull":        "📈",
            "choppy":      "〰️",
            "bear":        "📉",
            "strong_bear": "💥",
            "unknown":     "❓"
        }[self.value]


# ==================== Trading pair categories ====================

PAIR_CATEGORIES = {
    "major": ["BTC/USDT", "ETH/USDT"],
    "mid":   ["DOGE/USDT", "SOL/USDT"],
    "alt":   ["RENDER/USDT", "ZRO/USDT", "MORPHO/USDT", "ETC/USDT"]
}

# ==================== Minimum data requirements ====================

MIN_CANDLES = {
    "5m":  50,
    "15m": 50,
    "1h":  30,
    "4h":  20
}

# ==================== Default fallback values ====================

DEFAULT_VALUES = {
    "fear_index":    50,
    "funding_rate":  0.0,
    "open_interest": 0.0,
    "volume":        0.0
}

# ==================== Error messages ====================

ERROR_MESSAGES = {
    "no_data":        "Insufficient data for analysis",
    "btc_block":      "BTC regime blocking trade",
    "structure_block":"Structure not confirmed",
    "risk_block":     "Risk manager blocked trade",
    "filter_block":   "Filters not passed",
    "session_block":  "Not in active session"
}

# ==================== Signal thresholds ====================

SIGNAL_THRESHOLDS = {
    "min_score":        60,
    "strong_score":     75,
    "min_rr":           1.5,
    "min_volume_ratio": 0.7,
    "max_spread":       0.1
}

# ==================== Time in milliseconds ====================

MS_IN_SECOND = 1_000
MS_IN_MINUTE = 60   * MS_IN_SECOND
MS_IN_HOUR   = 60   * MS_IN_MINUTE
MS_IN_DAY    = 24   * MS_IN_HOUR
