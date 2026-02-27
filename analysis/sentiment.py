"""
ARUNABHA ALGO BOT - Sentiment Analysis v2.0
============================================
UPGRADES:
- F&G Rate of Change → smarter blocking
  FALLING_FAST → block even if value not extreme
  RISING from FEAR → recovery signal → LONG ok
- Adaptive scoring based on ROC direction
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from data.sentiment_fetcher import fetch_all_sentiment, get_sentiment_sync

logger = logging.getLogger(__name__)


class MarketMood(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"
    RECOVERY = "RECOVERY"     # Fear but rising → early long opportunity


@dataclass
class SentimentResult:
    fear_greed_value: int
    fear_greed_label: str
    fear_greed_change: int          # today - yesterday
    rate_of_change: str             # RISING_FAST / RISING / STABLE / FALLING / FALLING_FAST
    alt_season_index: int
    btc_dominance: float
    market_mood: MarketMood
    mood_reason: str
    raw: Dict


class SentimentAnalyzer:

    def analyze(self, sentiment_data: Optional[Dict] = None) -> SentimentResult:
        if sentiment_data is None:
            sentiment_data = get_sentiment_sync()

        fg = sentiment_data.get("fear_greed", {})
        alt = sentiment_data.get("alt_season", {})

        fg_value = fg.get("value", 50)
        fg_label = fg.get("classification", "NEUTRAL")
        fg_change = fg.get("change", 0)
        roc = fg.get("rate_of_change", "STABLE")
        alt_index = alt.get("alt_season_index", 50)
        btc_dom = alt.get("btc_dominance", 50.0)

        mood, reason = self._calculate_mood(fg_value, fg_label, fg_change, roc, alt_index)

        return SentimentResult(
            fear_greed_value=fg_value,
            fear_greed_label=fg_label,
            fear_greed_change=fg_change,
            rate_of_change=roc,
            alt_season_index=alt_index,
            btc_dominance=btc_dom,
            market_mood=mood,
            mood_reason=reason,
            raw=sentiment_data
        )

    def _calculate_mood(
        self,
        fg_value: int,
        fg_label: str,
        fg_change: int,
        roc: str,
        alt_index: int
    ) -> Tuple[MarketMood, str]:
        """
        Smart mood calc using both VALUE and RATE OF CHANGE

        Key insight:
          F&G=25 stable → moderate caution
          F&G=25 falling fast → panic, block longs
          F&G=25 rising → recovery begins, longs ok
        """
        # 1. EXTREME FEAR falling → pure RISK_OFF (panic)
        if fg_value <= 20 and roc in ("FALLING", "FALLING_FAST"):
            return MarketMood.RISK_OFF, f"Panic: F&G={fg_value} and falling ({roc})"

        # 2. EXTREME GREED rising → bubble risk, RISK_OFF for longs
        if fg_value >= 80 and roc in ("RISING", "RISING_FAST"):
            return MarketMood.RISK_OFF, f"Bubble: F&G={fg_value} and rising ({roc})"

        # 3. EXTREME FEAR but recovering → RECOVERY (early long opportunity)
        if fg_value <= 25 and roc in ("RISING", "RISING_FAST"):
            return MarketMood.RECOVERY, f"Recovery: F&G={fg_value} rising from fear ({fg_change:+d})"

        # 4. Plain EXTREME FEAR (stable) → block longs
        if fg_value <= 20:
            return MarketMood.RISK_OFF, f"Extreme Fear: F&G={fg_value} (stable)"

        # 5. Plain EXTREME GREED (stable) → block shorts
        if fg_value >= 80:
            return MarketMood.RISK_OFF, f"Extreme Greed: F&G={fg_value} (stable)"

        # 6. Falling fast from neutral → caution
        if roc == "FALLING_FAST" and fg_value < 50:
            return MarketMood.NEUTRAL, f"Sentiment deteriorating: F&G={fg_value} falling fast"

        # 7. Greed + Alt season → RISK_ON
        if fg_value >= 60 and alt_index >= 60:
            return MarketMood.RISK_ON, f"Bull run: Greed ({fg_value}) + AltSeason ({alt_index})"

        return MarketMood.NEUTRAL, f"F&G={fg_value} ({roc}), AltSeason={alt_index}"

    def is_long_blocked(self, result: SentimentResult) -> bool:
        """Block LONG: extreme fear falling, or plain extreme fear"""
        if result.market_mood == MarketMood.RISK_OFF:
            # RISK_OFF from extreme fear → block long
            if result.fear_greed_value <= 25:
                return True
        return False

    def is_short_blocked(self, result: SentimentResult) -> bool:
        """Block SHORT: extreme greed"""
        if result.market_mood == MarketMood.RISK_OFF:
            if result.fear_greed_value >= 75:
                return True
        return False

    def get_sentiment_score(self, result: SentimentResult, direction: Optional[str] = None) -> int:
        """
        Sentiment score for Tier2 (0-15)
        RECOVERY + LONG = high score (contrarian opportunity)
        RISK_ON + LONG = high score
        RISK_OFF = 0
        """
        if direction == "LONG":
            if result.market_mood == MarketMood.RISK_ON:
                return 15
            elif result.market_mood == MarketMood.RECOVERY:
                return 13   # contrarian long in recovery
            elif result.market_mood == MarketMood.NEUTRAL:
                return 8
            else:
                return 0
        elif direction == "SHORT":
            if result.market_mood == MarketMood.RISK_OFF and result.fear_greed_value <= 25:
                return 15   # shorting into panic
            elif result.market_mood == MarketMood.NEUTRAL:
                return 8
            elif result.market_mood == MarketMood.RISK_ON:
                return 2    # shorting into greed = risky
            else:
                return 5
        return 8

    def format_for_signal(self, result: SentimentResult) -> str:
        roc_arrows = {
            "RISING_FAST": "⬆️⬆️", "RISING": "⬆️",
            "STABLE": "➡️",
            "FALLING": "⬇️", "FALLING_FAST": "⬇️⬇️"
        }
        arrow = roc_arrows.get(result.rate_of_change, "")
        return (
            f"{self._fg_emoji(result.fear_greed_value)} "
            f"{result.fear_greed_label.replace('_', ' ')} "
            f"({result.fear_greed_value}{arrow} Δ{result.fear_greed_change:+d}) "
            f"| Alt Season: {result.alt_season_index}"
        )

    def _fg_emoji(self, value: int) -> str:
        if value <= 20: return "😱"
        elif value <= 40: return "😨"
        elif value <= 60: return "😐"
        elif value <= 80: return "😄"
        else: return "🤑"
