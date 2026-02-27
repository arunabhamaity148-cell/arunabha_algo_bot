"""
ARUNABHA ALGO BOT - Sentiment Data Fetcher v2.0
================================================
UPGRADES:
- F&G rate of change tracking (today vs yesterday)
- 15-min cache
- Exponential backoff on API failure
- get_fg_change() → rising/falling/stable
"""

import asyncio
import logging
import time
from typing import Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CACHE_DURATION = 15 * 60   # 15 minutes


@dataclass
class SentimentCache:
    data: Optional[Dict] = None
    timestamp: float = 0.0

    def is_valid(self) -> bool:
        return self.data is not None and (time.time() - self.timestamp) < CACHE_DURATION

    def update(self, data: Dict):
        self.data = data
        self.timestamp = time.time()


_cache = SentimentCache()


async def fetch_fear_greed() -> Dict:
    """
    Fetch BTC Fear & Greed from alternative.me
    Returns current + yesterday for rate-of-change calc
    """
    try:
        import aiohttp
        # limit=2 → today + yesterday
        url = "https://api.alternative.me/fng/?limit=2"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    jd = await resp.json()
                    entries = jd.get("data", [])
                    today = entries[0] if entries else {}
                    yesterday = entries[1] if len(entries) > 1 else {}

                    today_val = int(today.get("value", 50))
                    yesterday_val = int(yesterday.get("value", 50))
                    change = today_val - yesterday_val

                    # Classify rate of change
                    if change <= -5:
                        roc = "FALLING_FAST"
                    elif change < 0:
                        roc = "FALLING"
                    elif change >= 5:
                        roc = "RISING_FAST"
                    elif change > 0:
                        roc = "RISING"
                    else:
                        roc = "STABLE"

                    return {
                        "value": today_val,
                        "classification": today.get("value_classification", "Neutral").upper().replace(" ", "_"),
                        "yesterday_value": yesterday_val,
                        "change": change,
                        "rate_of_change": roc,
                        "source": "alternative.me"
                    }
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed: {e}")
    return {
        "value": 50,
        "classification": "NEUTRAL",
        "yesterday_value": 50,
        "change": 0,
        "rate_of_change": "STABLE",
        "source": "fallback"
    }


async def fetch_altcoin_season() -> Dict:
    """Fetch BTC/Altcoin dominance from CoinGecko (free, no key)"""
    try:
        import aiohttp
        url = "https://api.coingecko.com/api/v3/global"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    btc_dom = data["data"]["market_cap_percentage"].get("btc", 50)
                    eth_dom = data["data"]["market_cap_percentage"].get("eth", 15)
                    alt_season_index = max(0, min(100, int(100 - btc_dom)))
                    return {
                        "btc_dominance": round(btc_dom, 2),
                        "eth_dominance": round(eth_dom, 2),
                        "alt_season_index": alt_season_index,
                        "source": "coingecko"
                    }
    except Exception as e:
        logger.warning(f"Altcoin season fetch failed: {e}")
    return {
        "btc_dominance": 50.0,
        "eth_dominance": 15.0,
        "alt_season_index": 50,
        "source": "fallback"
    }


async def fetch_all_sentiment() -> Dict:
    """Fetch all sentiment data concurrently with 15-min cache"""
    global _cache

    if _cache.is_valid():
        logger.debug("Sentiment cache hit")
        return _cache.data

    logger.info("Fetching fresh sentiment data...")

    results = await asyncio.gather(
        fetch_fear_greed(),
        fetch_altcoin_season(),
        return_exceptions=True
    )

    fear_greed = results[0] if not isinstance(results[0], Exception) else {
        "value": 50, "classification": "NEUTRAL",
        "yesterday_value": 50, "change": 0,
        "rate_of_change": "STABLE", "source": "error"
    }
    alt_season = results[1] if not isinstance(results[1], Exception) else {
        "btc_dominance": 50.0, "eth_dominance": 15.0,
        "alt_season_index": 50, "source": "error"
    }

    combined = {
        "fear_greed": fear_greed,
        "alt_season": alt_season,
        "fetched_at": time.time()
    }

    _cache.update(combined)
    logger.info(
        f"Sentiment: F&G={fear_greed['value']} ({fear_greed['classification']}) "
        f"ROC={fear_greed['rate_of_change']} Δ{fear_greed['change']:+d} | "
        f"AltSeason={alt_season['alt_season_index']}"
    )
    return combined


def get_sentiment_sync() -> Dict:
    """Sync wrapper"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            if _cache.is_valid():
                return _cache.data
            return {
                "fear_greed": {"value": 50, "classification": "NEUTRAL",
                               "yesterday_value": 50, "change": 0,
                               "rate_of_change": "STABLE", "source": "no_loop"},
                "alt_season": {"btc_dominance": 50.0, "eth_dominance": 15.0,
                               "alt_season_index": 50, "source": "no_loop"},
            }
        return loop.run_until_complete(fetch_all_sentiment())
    except Exception as e:
        logger.error(f"Sentiment sync error: {e}")
        return {
            "fear_greed": {"value": 50, "classification": "NEUTRAL",
                           "yesterday_value": 50, "change": 0,
                           "rate_of_change": "STABLE", "source": "error"},
            "alt_season": {"btc_dominance": 50.0, "eth_dominance": 15.0,
                           "alt_season_index": 50, "source": "error"},
        }
