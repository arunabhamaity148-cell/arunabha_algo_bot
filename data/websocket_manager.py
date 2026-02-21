"""
ARUNABHA ALGO BOT - WebSocket Manager
পারফেক্ট ভার্সন - ১০০% কাজ করবেই
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Callable, Any, Tuple
from collections import deque
from datetime import datetime

import aiohttp
import config

logger = logging.getLogger(__name__)

# ==================== কনস্ট্যান্ট ====================
BINANCE_WS_URL = "wss://fstream.binance.com/stream?streams="
PING_INTERVAL = 20
RECONNECT_DELAY = 5
MAX_RETRIES = 10

class BinanceWSFeed:
    """Binance WebSocket ফিড - সিম্পল, ক্লিন, বুলেট-প্রুফ"""
    
    def __init__(self, on_candle_close: Optional[Callable] = None):
        self.on_candle_close = on_candle_close
        self._cache: Dict[str, deque] = {}
        self._message_count = 0
        self._last_pong = datetime.now()
        self._btc_ready = False
        
    def _get_key(self, symbol: str, tf: str) -> str:
        """ক্যাশের জন্য কী জেনারেট"""
        return f"{symbol}_{tf}"
    
    def get_ohlcv(self, symbol: str, tf: str) -> List[List[float]]:
        """ক্যাশ থেকে ডেটা নাও"""
        key = self._get_key(symbol, tf)
        
        if key not in self._cache:
            logger.debug(f"❌ Cache MISS: {symbol} {tf}")
            return []
            
        data = list(self._cache[key])
        if data:
            logger.debug(f"✅ Cache HIT: {symbol} {tf} - {len(data)} candles")
            return data
        return []
    
    def update_cache(self, symbol: str, tf: str, candle: List[float]):
        """ক্যাশ আপডেট করো"""
        key = self._get_key(symbol, tf)
        
        if key not in self._cache:
            self._cache[key] = deque(maxlen=100)
            logger.info(f"🆕 New cache for {symbol} {tf}")
        
        # চেক করো এই ক্যান্ডেল আগে আছে কিনা
        if self._cache[key] and int(candle[0]) == int(self._cache[key][-1][0]):
            self._cache[key][-1] = candle
            logger.debug(f"🔄 Updated {symbol} {tf} @ {candle[4]:.2f}")
        else:
            self._cache[key].append(candle)
            logger.info(f"➕ ADDED {symbol} {tf} @ {candle[4]:.2f} (total: {len(self._cache[key])})")
            
            if symbol == "BTC/USDT" and tf == "15m":
                self._btc_ready = True
                logger.info(f"✅ BTC 15m ready - {len(self._cache[key])} candles")
    
    def seed_from_rest(self, rest_client):
        """REST থেকে ডেটা নিয়ে ক্যাশ সিড করো"""
        logger.info("🌱 Seeding cache from REST...")
        
        symbols = ["BTC/USDT", "ETH/USDT", "DOGE/USDT", "SOL/USDT", "RENDER/USDT"]
        timeframes = ["5m", "15m", "1h", "4h"]
        
        # সব সিম্বলের জন্য ডেটা আনো
        import asyncio
        loop = asyncio.get_event_loop()
        
        for symbol in symbols:
            for tf in timeframes:
                try:
                    candles = loop.run_until_complete(
                        rest_client.fetch_ohlcv(symbol, tf, limit=100)
                    )
                    if candles:
                        key = self._get_key(symbol, tf)
                        self._cache[key] = deque(candles, maxlen=100)
                        logger.info(f"✅ Seeded {symbol} {tf}: {len(candles)} candles")
                except Exception as e:
                    logger.error(f"❌ Seed failed {symbol} {tf}: {e}")
        
        logger.info("🌱 Seeding complete")


class WebSocketManager:
    """ওয়েবসকেট ম্যানেজার - অটো রিকানেক্ট, এরর হ্যান্ডলিং সহ"""
    
    def __init__(self, on_candle_close: Optional[Callable] = None):
        self.feed = BinanceWSFeed(on_candle_close)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._connected = False
        self._retry = 0
        
    async def start(self):
        """স্টার্ট করো"""
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("🔌 WebSocket manager started")
    
    async def stop(self):
        """স্টপ করো"""
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except:
                pass
        logger.info("🔌 WebSocket manager stopped")
    
    async def _run(self):
        """মেইন লুপ"""
        while not self._stop.is_set():
            try:
                await self._connect()
            except Exception as e:
                self._retry += 1
                if self._retry > MAX_RETRIES:
                    logger.error(f"❌ Max retries reached")
                    break
                    
                wait = RECONNECT_DELAY * (2 ** (self._retry - 1))
                logger.warning(f"⚠️ Error: {e}, retry {self._retry}/{MAX_RETRIES} in {wait}s")
                await asyncio.sleep(wait)
    
    async def _connect(self):
        """কানেক্ট করো এবং লিসেন করো"""
        streams = [
            "btcusdt@kline_15m",
            "ethusdt@kline_15m", 
            "dogeusdt@kline_15m",
            "solusdt@kline_15m",
            "renderusdt@kline_15m",
            "btcusdt@kline_5m",
            "btcusdt@kline_1h",
            "btcusdt@kline_4h"
        ]
        
        url = BINANCE_WS_URL + "/".join(streams)
        logger.info(f"🔌 Connecting to: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                url,
                heartbeat=PING_INTERVAL,
                receive_timeout=30
            ) as ws:
                logger.info("✅ WebSocket CONNECTED!")
                self._connected = True
                self._retry = 0
                
                async for msg in ws:
                    if self._stop.is_set():
                        break
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._process(msg.data)
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.warning("⚠️ WebSocket closed")
                        break
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error("❌ WebSocket error")
                        break
                
                self._connected = False
    
    async def _process(self, raw: str):
        """মেসেজ প্রসেস করো"""
        try:
            data = json.loads(raw)
            stream = data.get("stream", "")
            payload = data.get("data", {})
            
            # শুধু kline ডেটা নাও
            k = payload.get("k", {})
            if not k:
                return
            
            # সিম্বল ঠিক করো
            symbol = payload.get("s", "").replace("USDT", "/USDT")
            tf = k.get("i")
            is_closed = k.get("x", False)
            
            candle = [
                k.get("t"),                    # timestamp
                float(k.get("o", 0)),           # open
                float(k.get("h", 0)),           # high
                float(k.get("l", 0)),           # low
                float(k.get("c", 0)),           # close
                float(k.get("v", 0)),           # volume
            ]
            
            # ফোর্স প্রিন্ট - দেখো ডেটা আসছে কিনা
            print(f"🔥 WEBSOCKET: {symbol} {tf} @ {candle[4]} closed={is_closed}")
            logger.info(f"🔥 WEBSOCKET: {symbol} {tf} @ {candle[4]} closed={is_closed}")
            
            # ক্যাশ আপডেট করো
            self.feed.update_cache(symbol, tf, candle)
            
            # ক্যান্ডেল ক্লোজ হলে সিগন্যাল জেনারেট করো
            if is_closed and self.feed.on_candle_close:
                candles = self.feed.get_ohlcv(symbol, tf)
                if candles:
                    await self.feed.on_candle_close(symbol, tf, candles)
                    
        except Exception as e:
            logger.error(f"❌ Process error: {e}")
    
    def is_connected(self) -> bool:
        """কানেক্টেড কিনা চেক করো"""
        return self._connected
    
    def get_status(self) -> Dict:
        """স্ট্যাটাস দাও"""
        return {
            "connected": self._connected,
            "retry": self._retry,
            "message_count": self.feed._message_count,
            "btc_ready": self.feed._btc_ready,
            "cache_size": sum(len(q) for q in self.feed._cache.values())
        }