"""
ARUNABHA ALGO BOT - Cache Manager v5.2
=======================================
WINDOWS FIX (Issue 2):
- aioredis সম্পূর্ণ বাদ। Python 3.11 + Windows-এ aioredis কাজ করে না।
- USE_REDIS=false থাকলে Redis-এর কোনো code চলবেই না (আগে চলত)
- Memory-only cache — production-এ Redis লাগবে না, bot ঠিকঠাক চলবে
- Redis শুধু explicitly USE_REDIS=true AND REDIS_URL set থাকলে try হবে
  তখনও redis-py (sync) দিয়ে করা হবে, aioredis না

ISSUE 6 (preserved): Redis reconnect with backoff
ISSUE 14 (preserved): maxlen=200, LRU via deque
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional, Any
from collections import deque
from datetime import datetime

import config

logger = logging.getLogger(__name__)

CACHE_MAXLEN = 200


class CacheManager:
    """
    Pure memory cache.
    Redis বন্ধ by default — USE_REDIS=true + REDIS_URL set থাকলে optional।
    Windows/Python 3.11-এ aioredis নেই — redis-py async wrapper use করা হয়।
    """

    def __init__(self):
        self._caches: Dict[str, deque] = {}
        self._last_update: Dict[str, datetime] = {}
        self._hits = 0
        self._misses = 0

        # Redis — সম্পূর্ণ optional, default বন্ধ
        self.redis = None
        self._redis_enabled = (
            getattr(config, "USE_REDIS", False)
            and bool(getattr(config, "REDIS_URL", ""))
        )
        self._redis_connecting = False

        # USE_REDIS=true হলেই try করো
        if self._redis_enabled:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._connect_redis())
                else:
                    loop.run_until_complete(self._connect_redis())
            except RuntimeError:
                # No event loop yet — will connect lazily
                pass

    async def _connect_redis(self):
        """
        Redis connect — aioredis নয়, redis-py async wrapper।
        USE_REDIS=false থাকলে এই function কখনো call হয় না।
        """
        if self._redis_connecting or not self._redis_enabled:
            return
        self._redis_connecting = True

        for attempt in range(5):
            try:
                # redis-py 4.2+ এ asyncio support আছে
                import redis.asyncio as aioredis
                self.redis = aioredis.from_url(
                    config.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                await self.redis.ping()
                logger.info("Redis connected (redis-py async)")
                self._redis_connecting = False
                return
            except ImportError:
                logger.warning(
                    "redis package not installed — Redis disabled. "
                    "Install: pip install redis"
                )
                self._redis_enabled = False
                self._redis_connecting = False
                return
            except Exception as e:
                wait = 5 * (attempt + 1)
                logger.warning(
                    f"Redis connect failed (attempt {attempt + 1}/5): {e} "
                    f"— retry in {wait}s"
                )
                await asyncio.sleep(wait)

        logger.warning("Redis unavailable after 5 attempts — memory cache only")
        self.redis = None
        self._redis_enabled = False
        self._redis_connecting = False

    # ── Key helpers ──────────────────────────────────────────────────

    def _get_key(self, symbol: str, tf: str, dtype: str = "ohlcv") -> str:
        return f"{dtype}:{symbol}:{tf}"

    def _ensure_cache(self, key: str):
        if key not in self._caches:
            self._caches[key] = deque(maxlen=CACHE_MAXLEN)

    # ── OHLCV ────────────────────────────────────────────────────────

    def set_ohlcv(self, symbol: str, tf: str, candles: List[List[float]]):
        key = self._get_key(symbol, tf)
        self._ensure_cache(key)
        self._caches[key].clear()
        for c in candles[-CACHE_MAXLEN:]:
            self._caches[key].append(c)
        self._last_update[key] = datetime.now()
        logger.debug(f"Cache SET {symbol} {tf}: {len(self._caches[key])} candles")

    def get_ohlcv(
        self, symbol: str, tf: str, limit: Optional[int] = None
    ) -> List[List[float]]:
        key = self._get_key(symbol, tf)
        if key not in self._caches or not self._caches[key]:
            self._misses += 1
            return []
        self._hits += 1
        data = list(self._caches[key])
        return data[-limit:] if limit else data

    def update_ohlcv(self, symbol: str, tf: str, candle: List[float]):
        key = self._get_key(symbol, tf)
        self._ensure_cache(key)
        if (self._caches[key] and
                int(candle[0]) == int(self._caches[key][-1][0])):
            self._caches[key][-1] = candle
        else:
            self._caches[key].append(candle)
        self._last_update[key] = datetime.now()

    # ── Orderbook ─────────────────────────────────────────────────────

    def set_orderbook(self, symbol: str, orderbook: Dict):
        key = self._get_key(symbol, "ob", "ob")
        self._caches[key] = deque([orderbook], maxlen=1)
        self._last_update[key] = datetime.now()

    def get_orderbook(self, symbol: str) -> Dict:
        key = self._get_key(symbol, "ob", "ob")
        if key not in self._caches or not self._caches[key]:
            return {"bids": [], "asks": []}
        return self._caches[key][0]

    # ── Ticker ────────────────────────────────────────────────────────

    def set_ticker(self, symbol: str, ticker: Dict):
        key = self._get_key(symbol, "tick", "tick")
        self._caches[key] = deque([ticker], maxlen=1)
        self._last_update[key] = datetime.now()

    def get_ticker(self, symbol: str) -> Dict:
        key = self._get_key(symbol, "tick", "tick")
        if key not in self._caches or not self._caches[key]:
            return {}
        return self._caches[key][0]

    # ── Staleness ─────────────────────────────────────────────────────

    def get_last_update(self, symbol: str, tf: str) -> Optional[datetime]:
        return self._last_update.get(self._get_key(symbol, tf))

    def is_stale(self, symbol: str, tf: str, max_age_seconds: int = 60) -> bool:
        last = self.get_last_update(symbol, tf)
        if not last:
            return True
        return (datetime.now() - last).total_seconds() > max_age_seconds

    # ── Redis helpers (only if enabled) ──────────────────────────────

    async def redis_set(self, key: str, value: Any, expire: int = 300):
        if not self.redis or not self._redis_enabled:
            return
        try:
            await self.redis.setex(key, expire, json.dumps(value, default=str))
        except Exception as e:
            logger.debug(f"Redis set error: {e} — reconnecting")
            asyncio.create_task(self._connect_redis())

    async def redis_get(self, key: str) -> Optional[Any]:
        if not self.redis or not self._redis_enabled:
            return None
        try:
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.debug(f"Redis get error: {e} — reconnecting")
            asyncio.create_task(self._connect_redis())
            return None

    # ── Stats ─────────────────────────────────────────────────────────

    def size(self) -> Dict:
        total = sum(len(q) for q in self._caches.values())
        rate = self._hits / max(self._hits + self._misses, 1) * 100
        return {
            "total_keys": len(self._caches),
            "total_candles": total,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(rate, 1),
            "redis_connected": self.redis is not None,
            "redis_enabled": self._redis_enabled,
        }

    def clear(
        self,
        symbol: Optional[str] = None,
        tf: Optional[str] = None
    ):
        if symbol and tf:
            self._caches.pop(self._get_key(symbol, tf), None)
        elif symbol:
            to_del = [k for k in self._caches if f":{symbol}:" in k]
            for k in to_del:
                del self._caches[k]
        else:
            self._caches.clear()
            self._last_update.clear()
            self._hits = self._misses = 0
