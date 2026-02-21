"""
ARUNABHA ALGO BOT - Cache Manager
Handles in-memory caching of market data
"""

import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from collections import deque
from datetime import datetime, timedelta
import asyncio

import config

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages in-memory cache for all market data
    Supports Redis if available, falls back to memory
    """
    
    def __init__(self):
        self._caches: Dict[str, deque] = {}
        self._metadata: Dict[str, Dict] = {}
        self._last_update: Dict[str, datetime] = {}
        
        # Try Redis if configured
        self.redis = None
        if config.USE_REDIS:
            try:
                import aioredis
                self.redis = aioredis.from_url(config.REDIS_URL)
                logger.info("Redis cache enabled")
            except Exception as e:
                logger.warning(f"Redis not available: {e}")
                self.redis = None
    
    def _get_key(self, symbol: str, tf: str, data_type: str = "ohlcv") -> str:
        """Get cache key"""
        return f"{data_type}:{symbol}:{tf}"
    
    def _init_cache(self, key: str):
        """Initialize cache if not exists"""
        if key not in self._caches:
            self._caches[key] = deque(maxlen=config.CACHE_SIZE)
            self._metadata[key] = {
                "created": datetime.now(),
                "hits": 0,
                "misses": 0
            }
            logger.debug(f"🆕 Created new cache for {key}")
    
    # ==================== OHLCV Cache ====================
    
    def set_ohlcv(self, symbol: str, tf: str, candles: List[List[float]]):
        """Set OHLCV data in cache with verification"""
        key = self._get_key(symbol, tf)
        
        logger.info(f"📦 Cache SET: {symbol} {tf} - {len(candles)} candles")
        
        self._init_cache(key)
        
        # Clear and extend
        self._caches[key].clear()
        for candle in candles[-config.CACHE_SIZE:]:
            self._caches[key].append(candle)
        
        self._last_update[key] = datetime.now()
        
        # Verify immediately
        verify = list(self._caches[key])
        if verify:
            logger.info(f"✅ Cache SET verified: {len(verify)} candles for {symbol} {tf} (latest: {verify[-1][4]})")
        else:
            logger.error(f"❌ Cache SET verification failed for {symbol} {tf}")
    
    def get_ohlcv(self, symbol: str, tf: str, limit: Optional[int] = None) -> List[List[float]]:
        """Get OHLCV data from cache with verification"""
        key = self._get_key(symbol, tf)
        
        logger.debug(f"🔍 Cache get: {symbol} {tf}")
        
        if key not in self._caches:
            logger.debug(f"❌ Cache MISS: {key} not found")
            return []
        
        # Update hit count
        self._metadata[key]["hits"] = self._metadata[key].get("hits", 0) + 1
        
        # Get data
        candles = list(self._caches[key])
        
        if not candles:
            logger.debug(f"⚠️ Cache EMPTY: {key} has no candles")
            return []
        
        logger.debug(f"✅ Cache HIT: {key} - {len(candles)} candles (latest: {candles[-1][4]})")
        
        if limit:
            return candles[-limit:]
        
        return candles
    
    def update_ohlcv(self, symbol: str, tf: str, candle: List[float]):
        """Update latest candle or add new one"""
        key = self._get_key(symbol, tf)
        self._init_cache(key)
        
        # Check if this candle exists (update) or is new
        if self._caches[key] and int(candle[0]) == int(self._caches[key][-1][0]):
            # Update last candle
            self._caches[key][-1] = candle
            logger.debug(f"🔄 Updated last candle for {key} @ {candle[4]:.2f}")
        else:
            # Add new candle
            self._caches[key].append(candle)
            logger.debug(f"➕ Added new candle for {key} @ {candle[4]:.2f} (total: {len(self._caches[key])})")
        
        self._last_update[key] = datetime.now()
    
    # ==================== Orderbook Cache ====================
    
    def set_orderbook(self, symbol: str, orderbook: Dict):
        """Set orderbook in cache"""
        key = self._get_key(symbol, "orderbook", "orderbook")
        
        # Store as JSON string
        self._caches[key] = deque([orderbook], maxlen=1)
        self._last_update[key] = datetime.now()
        logger.debug(f"📚 Orderbook cached for {symbol}")
    
    def get_orderbook(self, symbol: str) -> Dict:
        """Get orderbook from cache"""
        key = self._get_key(symbol, "orderbook", "orderbook")
        
        if key not in self._caches or not self._caches[key]:
            logger.debug(f"❌ Orderbook cache miss for {symbol}")
            return {"bids": [], "asks": []}
        
        logger.debug(f"✅ Orderbook cache hit for {symbol}")
        return self._caches[key][0]
    
    # ==================== Ticker Cache ====================
    
    def set_ticker(self, symbol: str, ticker: Dict):
        """Set ticker in cache"""
        key = self._get_key(symbol, "ticker", "ticker")
        self._caches[key] = deque([ticker], maxlen=1)
        self._last_update[key] = datetime.now()
        logger.debug(f"📈 Ticker cached for {symbol}")
    
    def get_ticker(self, symbol: str) -> Dict:
        """Get ticker from cache"""
        key = self._get_key(symbol, "ticker", "ticker")
        
        if key not in self._caches or not self._caches[key]:
            logger.debug(f"❌ Ticker cache miss for {symbol}")
            return {}
        
        logger.debug(f"✅ Ticker cache hit for {symbol}")
        return self._caches[key][0]
    
    # ==================== Metadata ====================
    
    def get_last_update(self, symbol: str, tf: str) -> Optional[datetime]:
        """Get last update time for a symbol/timeframe"""
        key = self._get_key(symbol, tf)
        return self._last_update.get(key)
    
    def is_stale(self, symbol: str, tf: str, max_age_seconds: int = 60) -> bool:
        """Check if cache is stale"""
        last = self.get_last_update(symbol, tf)
        if not last:
            return True
        
        age = (datetime.now() - last).total_seconds()
        return age > max_age_seconds
    
    def clear(self, symbol: Optional[str] = None, tf: Optional[str] = None):
        """Clear cache"""
        if symbol and tf:
            key = self._get_key(symbol, tf)
            if key in self._caches:
                del self._caches[key]
                logger.info(f"Cleared cache for {key}")
        
        elif symbol:
            # Clear all timeframes for symbol
            keys_to_delete = []
            for key in list(self._caches.keys()):
                if key.startswith(f"ohlcv:{symbol}:"):
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del self._caches[key]
            
            logger.info(f"Cleared cache for {symbol} ({len(keys_to_delete)} timeframes)")
        
        else:
            # Clear all
            self._caches.clear()
            self._metadata.clear()
            self._last_update.clear()
            logger.info("Cleared all cache")
    
    def size(self) -> Dict:
        """Get cache size statistics"""
        stats = {
            "total_keys": len(self._caches),
            "total_candles": sum(len(q) for q in self._caches.values()),
            "by_type": {},
            "hits": 0,
            "misses": 0
        }
        
        # Count by type
        for key in self._caches:
            data_type = key.split(":")[0]
            stats["by_type"][data_type] = stats["by_type"].get(data_type, 0) + 1
        
        # Calculate hits/misses
        for meta in self._metadata.values():
            stats["hits"] += meta.get("hits", 0)
            stats["misses"] += meta.get("misses", 0)
        
        if stats["hits"] + stats["misses"] > 0:
            stats["hit_rate"] = stats["hits"] / (stats["hits"] + stats["misses"]) * 100
        else:
            stats["hit_rate"] = 0
        
        return stats
    
    # ==================== Async Redis Methods ====================
    
    async def redis_set(self, key: str, value: Any, expire: int = 300):
        """Set value in Redis"""
        if not self.redis:
            return
        
        try:
            await self.redis.setex(
                key,
                expire,
                json.dumps(value, default=str)
            )
        except Exception as e:
            logger.debug(f"Redis set error: {e}")
    
    async def redis_get(self, key: str) -> Optional[Any]:
        """Get value from Redis"""
        if not self.redis:
            return None
        
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"Redis get error: {e}")
        
        return None