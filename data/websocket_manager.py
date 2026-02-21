"""
ARUNABHA ALGO BOT - WebSocket Manager
Handles real-time data streams from Binance
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Callable, Any, Tuple
from collections import deque
from datetime import datetime

import aiohttp
import config
from core.constants import Timeframes

logger = logging.getLogger(__name__)


class BinanceWSFeed:
    """
    WebSocket feed for Binance futures
    """
    
    def __init__(self, on_candle_close: Optional[Callable] = None):
        self.on_candle_close = on_candle_close
        self._cache: Dict[Tuple[str, str], deque] = {}
        self._tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        self._connected = False
        self._reconnect_count = 0
        self._btc_received = False
        
    def _get_cache_key(self, symbol: str, tf: str) -> Tuple[str, str]:
        return (symbol, tf)
    
    def _init_cache(self, symbols: List[str], timeframes: List[str]):
        """Initialize cache for all symbols and timeframes"""
        for symbol in symbols:
            for tf in timeframes:
                key = self._get_cache_key(symbol, tf)
                self._cache[key] = deque(maxlen=config.CACHE_SIZE)
        logger.info(f"✅ Cache initialized for {len(symbols)} symbols x {len(timeframes)} timeframes")
    
    def get_ohlcv(self, symbol: str, tf: str) -> List[List[float]]:
        """Get cached OHLCV data"""
        key = self._get_cache_key(symbol, tf)
        if key in self._cache:
            return list(self._cache[key])
        return []
    
    def update_cache(self, symbol: str, tf: str, candle: List[float]):
        """Update cache with new candle"""
        key = self._get_cache_key(symbol, tf)
        if key not in self._cache:
            self._cache[key] = deque(maxlen=config.CACHE_SIZE)
        
        # Check if this candle exists (update) or is new
        cached = list(self._cache[key])
        if cached and int(candle[0]) == int(cached[-1][0]):
            # Update last candle
            self._cache[key][-1] = candle
            logger.debug(f"🔄 Updated last candle for {symbol} {tf}")
        else:
            # Add new candle
            self._cache[key].append(candle)
            logger.debug(f"➕ New candle for {symbol} {tf} @ {candle[4]:.2f}")
            
            # Track BTC reception
            if symbol == "BTC/USDT" and tf == "15m":
                self._btc_received = True
                logger.info(f"✅ First BTC 15m candle received")
    
    async def seed_from_rest(self, rest_client):
        """Seed cache from REST API"""
        logger.info("🌱 Seeding WebSocket cache from REST...")
        
        symbols = config.TRADING_PAIRS + ["BTC/USDT"]
        self._init_cache(symbols, config.TIMEFRAMES)
        
        # Seed BTC first
        try:
            btc_candles = await rest_client.fetch_ohlcv("BTC/USDT", "15m", limit=config.CACHE_SIZE)
            if btc_candles:
                key = self._get_cache_key("BTC/USDT", "15m")
                self._cache[key].extend(btc_candles)
                logger.info(f"✅ Seeded BTC 15m: {len(btc_candles)} candles")
                self._btc_received = True
        except Exception as e:
            logger.error(f"❌ BTC seed failed: {e}")
        
        # Then other symbols
        for symbol in symbols:
            if symbol == "BTC/USDT":
                continue
            for tf in config.TIMEFRAMES:
                try:
                    candles = await rest_client.fetch_ohlcv(symbol, tf, limit=config.CACHE_SIZE)
                    if candles:
                        key = self._get_cache_key(symbol, tf)
                        self._cache[key].extend(candles)
                        logger.debug(f"✅ Seeded {symbol} {tf}: {len(candles)} candles")
                except Exception as e:
                    logger.warning(f"⚠️ Seed failed {symbol} {tf}: {e}")
        
        logger.info("🌱 Seeding complete")
    
    def _symbol_to_stream(self, symbol: str, tf: str) -> str:
        """Convert symbol to Binance stream name"""
        return symbol.replace("/", "").lower() + f"@kline_{tf}"
    
    def _get_streams(self) -> List[str]:
        """Get all stream names"""
        streams = []
        symbols = config.TRADING_PAIRS + ["BTC/USDT"]
        
        for symbol in symbols:
            for tf in config.TIMEFRAMES:
                streams.append(self._symbol_to_stream(symbol, tf))
        
        logger.info(f"📡 Subscribing to {len(streams)} streams")
        return streams
    
    def _parse_kline(self, data: Dict) -> Optional[Dict]:
        """Parse kline data from Binance"""
        try:
            k = data.get("k", {})
            if not k:
                return None
            
            return {
                "symbol": data.get("s", "").replace("USDT", "/USDT"),
                "timeframe": k.get("i"),
                "candle": [
                    k.get("t"),  # timestamp
                    float(k.get("o", 0)),  # open
                    float(k.get("h", 0)),  # high
                    float(k.get("l", 0)),  # low
                    float(k.get("c", 0)),  # close
                    float(k.get("v", 0)),  # volume
                ],
                "is_closed": k.get("x", False)
            }
        except Exception as e:
            logger.error(f"❌ Kline parse error: {e}")
            return None


class WebSocketManager:
    """
    Manages WebSocket connection and reconnection
    """
    
    def __init__(self, on_candle_close: Optional[Callable] = None):
        self.feed = BinanceWSFeed(on_candle_close)
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._connected = False
        self._reconnect_delay = config.WS_RECONNECT_DELAY
        self._max_retries = config.WS_MAX_RETRIES
        self._retry_count = 0
        
    async def start(self):
        """Start WebSocket connection"""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_forever())
        logger.info("🔌 WebSocket manager started")
    
    async def stop(self):
        """Stop WebSocket connection"""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🔌 WebSocket manager stopped")
    
    async def _run_forever(self):
        """Main loop with reconnection"""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._retry_count += 1
                
                if self._retry_count > self._max_retries:
                    logger.error(f"❌ Max retries ({self._max_retries}) reached")
                    break
                
                wait_time = self._reconnect_delay * (2 ** (self._retry_count - 1))
                logger.warning(
                    f"⚠️ WebSocket error: {e} - "
                    f"Reconnecting in {wait_time}s (attempt {self._retry_count}/{self._max_retries})"
                )
                
                await asyncio.sleep(wait_time)
    
    async def _connect_and_listen(self):
        """Connect and listen to WebSocket streams"""
        streams = self.feed._get_streams()
        stream_names = "/".join(streams)
        url = f"wss://fstream.binance.com/stream?streams={stream_names}"
        
        logger.info(f"🔌 Connecting to WebSocket: {len(streams)} streams")
        
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                url,
                heartbeat=config.WS_PING_INTERVAL,
                receive_timeout=60
            ) as ws:
                logger.info("✅ WebSocket connected")
                self._connected = True
                self._retry_count = 0
                
                async for msg in ws:
                    if self._stop_event.is_set():
                        break
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg.data)
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.warning("⚠️ WebSocket closed/error")
                        break
        
        self._connected = False
    
    async def _handle_message(self, raw: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(raw)
            stream_data = data.get("data", {})
            
            # Parse kline
            parsed = self.feed._parse_kline(stream_data)
            if not parsed:
                return
            
            symbol = parsed["symbol"]
            tf = parsed["timeframe"]
            candle = parsed["candle"]
            is_closed = parsed["is_closed"]
            
            # Update cache
            self.feed.update_cache(symbol, tf, candle)
            
            # Trigger callback on candle close
            if is_closed and self.feed.on_candle_close:
                try:
                    candles = self.feed.get_ohlcv(symbol, tf)
                    await self.feed.on_candle_close(symbol, tf, candles)
                except Exception as e:
                    logger.error(f"❌ Callback error: {e}")
            
        except json.JSONDecodeError:
            logger.debug("⚠️ Invalid JSON received")
        except Exception as e:
            logger.error(f"❌ Message handling error: {e}")
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._connected
    
    def get_status(self) -> Dict:
        """Get WebSocket status"""
        return {
            "connected": self._connected,
            "retry_count": self._retry_count,
            "btc_received": self.feed._btc_received,
            "cache_size": sum(len(q) for q in self.feed._cache.values())
        }