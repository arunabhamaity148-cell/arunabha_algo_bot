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
        """Get cache key for symbol and timeframe"""
        return (symbol, tf)
    
    def _init_cache(self, symbols: List[str], timeframes: List[str]):
        """Initialize cache for all symbols and timeframes"""
        for symbol in symbols:
            for tf in timeframes:
                key = self._get_cache_key(symbol, tf)
                self._cache[key] = deque(maxlen=config.CACHE_SIZE)
        logger.info(f"✅ Cache initialized for {len(symbols)} symbols x {len(timeframes)} timeframes")
        logger.debug(f"   Cache keys: {list(self._cache.keys())}")
    
    def get_ohlcv(self, symbol: str, tf: str) -> List[List[float]]:
        """
        Get cached OHLCV data with verification
        Returns list of candles or empty list if not found
        """
        key = self._get_cache_key(symbol, tf)
        
        # Log the request
        logger.debug(f"🔍 Cache request: {symbol} {tf}")
        
        if key in self._cache:
            data = list(self._cache[key])
            if data:
                logger.debug(f"✅ Cache HIT: {symbol} {tf} - {len(data)} candles (latest: {data[-1][4]})")
                return data
            else:
                logger.debug(f"⚠️ Cache EMPTY: {symbol} {tf} - key exists but no data")
                return []
        else:
            logger.debug(f"❌ Cache MISS: {symbol} {tf} - key not found")
            
            # List available keys for debugging (first 5)
            available = [f"{k[0]} {k[1]}" for k in list(self._cache.keys())[:5]]
            logger.debug(f"   Available keys (first 5): {available}")
            return []
    
    def update_cache(self, symbol: str, tf: str, candle: List[float]):
        """Update cache with new candle"""
        key = self._get_cache_key(symbol, tf)
        if key not in self._cache:
            logger.debug(f"🆕 Creating new cache for {symbol} {tf}")
            self._cache[key] = deque(maxlen=config.CACHE_SIZE)
        
        # Check if this candle exists (update) or is new
        cached = list(self._cache[key])
        if cached and int(candle[0]) == int(cached[-1][0]):
            # Update last candle
            self._cache[key][-1] = candle
            logger.debug(f"🔄 Updated last candle for {symbol} {tf} @ {candle[4]:.2f}")
        else:
            # Add new candle
            self._cache[key].append(candle)
            logger.debug(f"➕ New candle for {symbol} {tf} @ {candle[4]:.2f} (total: {len(self._cache[key])})")
            
            # Track BTC reception
            if symbol == "BTC/USDT" and tf == "15m":
                self._btc_received = True
                logger.info(f"✅ BTC 15m candle received - total: {len(self._cache[key])}")
    
    async def seed_from_rest(self, rest_client):
        """Seed cache from REST API and ensure it's accessible"""
        logger.info("🌱 Seeding WebSocket cache from REST...")
        
        symbols = config.TRADING_PAIRS + ["BTC/USDT"]
        self._init_cache(symbols, config.TIMEFRAMES)
        
        # Seed BTC first - with explicit logging and verification
        try:
            logger.info("📡 Fetching BTC data for cache...")
            
            # Fetch all BTC timeframes
            btc_15m = await rest_client.fetch_ohlcv("BTC/USDT", "15m", limit=config.CACHE_SIZE)
            if btc_15m and len(btc_15m) > 0:
                key_15m = self._get_cache_key("BTC/USDT", "15m")
                self._cache[key_15m].clear()  # Clear existing
                self._cache[key_15m].extend(btc_15m)
                logger.info(f"✅ Cached BTC 15m: {len(btc_15m)} candles (latest: {btc_15m[-1][4]})")
                
                # Verify cache immediately
                verify = self.get_ohlcv("BTC/USDT", "15m")
                if verify:
                    logger.info(f"🔍 VERIFICATION PASSED - Cache now has {len(verify)} candles for BTC 15m")
                else:
                    logger.error(f"❌ VERIFICATION FAILED - BTC 15m not in cache!")
                
                self._btc_received = True
            else:
                logger.warning("⚠️ No BTC 15m data received")
            
            # Seed BTC 1h
            btc_1h = await rest_client.fetch_ohlcv("BTC/USDT", "1h", limit=50)
            if btc_1h:
                key_1h = self._get_cache_key("BTC/USDT", "1h")
                self._cache[key_1h].clear()
                self._cache[key_1h].extend(btc_1h)
                logger.info(f"✅ Cached BTC 1h: {len(btc_1h)} candles")
                
                # Verify
                verify = self.get_ohlcv("BTC/USDT", "1h")
                if verify:
                    logger.info(f"🔍 BTC 1h verified: {len(verify)} candles")
            
            # Seed BTC 4h
            btc_4h = await rest_client.fetch_ohlcv("BTC/USDT", "4h", limit=50)
            if btc_4h:
                key_4h = self._get_cache_key("BTC/USDT", "4h")
                self._cache[key_4h].clear()
                self._cache[key_4h].extend(btc_4h)
                logger.info(f"✅ Cached BTC 4h: {len(btc_4h)} candles")
                
                # Verify
                verify = self.get_ohlcv("BTC/USDT", "4h")
                if verify:
                    logger.info(f"🔍 BTC 4h verified: {len(verify)} candles")
                    
        except Exception as e:
            logger.error(f"❌ BTC cache seed failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Seed other symbols
        for symbol in symbols:
            if symbol == "BTC/USDT":
                continue
            for tf in config.TIMEFRAMES:
                try:
                    candles = await rest_client.fetch_ohlcv(symbol, tf, limit=config.CACHE_SIZE)
                    if candles:
                        key = self._get_cache_key(symbol, tf)
                        self._cache[key].clear()
                        self._cache[key].extend(candles)
                        logger.info(f"✅ Cached {symbol} {tf}: {len(candles)} candles")
                        
                        # Verify
                        verify = self.get_ohlcv(symbol, tf)
                        if verify:
                            logger.debug(f"🔍 Verified {symbol} {tf}: {len(verify)} candles")
                except Exception as e:
                    logger.warning(f"⚠️ Seed failed {symbol} {tf}: {e}")
        
        # Final cache stats
        total = sum(len(q) for q in self._cache.values())
        logger.info(f"🌱 Seeding complete - TOTAL CANDLES IN CACHE: {total}")
        
        # Print detailed cache summary
        logger.info("📊 CACHE SUMMARY:")
        cache_summary = {}
        for (sym, tf), queue in self._cache.items():
            if len(queue) > 0:
                cache_summary[f"{sym} {tf}"] = len(queue)
                logger.info(f"   ✅ {sym} {tf}: {len(queue)} candles")
        
        # Double-check BTC specifically
        btc_check = self.get_ohlcv("BTC/USDT", "15m")
        if btc_check:
            logger.info(f"🔍 FINAL BTC VERIFICATION: {len(btc_check)} candles available")
        else:
            logger.error("❌ FINAL BTC VERIFICATION FAILED - BTC not in cache!")
    
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
            
            symbol = data.get("s", "").replace("USDT", "/USDT")
            timeframe = k.get("i")
            is_closed = k.get("x", False)
            
            candle = [
                k.get("t"),  # timestamp
                float(k.get("o", 0)),  # open
                float(k.get("h", 0)),  # high
                float(k.get("l", 0)),  # low
                float(k.get("c", 0)),  # close
                float(k.get("v", 0)),  # volume
            ]
            
            if is_closed:
                logger.debug(f"🔔 Candle closed: {symbol} {timeframe} @ {candle[4]:.2f}")
            
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "candle": candle,
                "is_closed": is_closed
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
                    if candles:
                        await self.feed.on_candle_close(symbol, tf, candles)
                    else:
                        logger.warning(f"⚠️ No candles for {symbol} {tf} in callback")
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
        # Count candles per symbol
        cache_stats = {}
        total = 0
        for (symbol, tf), queue in self.feed._cache.items():
            if symbol not in cache_stats:
                cache_stats[symbol] = {}
            cache_stats[symbol][tf] = len(queue)
            total += len(queue)
        
        # Specifically check BTC
        btc_candles = len(self.feed._cache.get(("BTC/USDT", "15m"), []))
        
        return {
            "connected": self._connected,
            "retry_count": self._retry_count,
            "btc_received": self.feed._btc_received,
            "btc_15m_candles": btc_candles,
            "total_candles": total,
            "cache_stats": cache_stats
        }