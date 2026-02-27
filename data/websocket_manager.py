"""
ARUNABHA ALGO BOT - WebSocket Manager v5.0
==========================================
UPGRADES:
- Heartbeat dead-detection: 30s no data → auto reconnect + Telegram alert
- Exponential backoff with jitter
- Data freshness tracking per stream
- Reconnect counter + health status
- MAX_RETRIES removed → infinite retry (bot must never stop)
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Callable, Any
from collections import deque
from datetime import datetime

import aiohttp
import config

logger = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://fstream.binance.com/stream?streams="
PING_INTERVAL = 20
BASE_RECONNECT = 3
MAX_RECONNECT_WAIT = 120        # cap at 2 minutes
DATA_DEAD_TIMEOUT = 30          # seconds — no data = dead connection
HEARTBEAT_CHECK_INTERVAL = 10   # check every 10s


class BinanceWSFeed:
    """Binance WebSocket feed cache"""

    def __init__(self, on_candle_close: Optional[Callable] = None):
        self.on_candle_close = on_candle_close
        self._cache: Dict[str, deque] = {}
        self._message_count = 0
        self._btc_ready = False
        self._last_message_time: float = time.time()   # ← heartbeat tracking

    def _get_key(self, symbol: str, tf: str) -> str:
        return f"{symbol}_{tf}"

    @property
    def seconds_since_last_message(self) -> float:
        return time.time() - self._last_message_time

    @property
    def is_data_fresh(self) -> bool:
        return self.seconds_since_last_message < DATA_DEAD_TIMEOUT

    def get_ohlcv(self, symbol: str, tf: str) -> List[List[float]]:
        key = self._get_key(symbol, tf)
        if key not in self._cache:
            return []
        return list(self._cache[key])

    def update_cache(self, symbol: str, tf: str, candle: List[float]):
        key = self._get_key(symbol, tf)
        if key not in self._cache:
            self._cache[key] = deque(maxlen=200)
        if self._cache[key] and int(candle[0]) == int(self._cache[key][-1][0]):
            self._cache[key][-1] = candle
        else:
            self._cache[key].append(candle)
            if symbol == "BTC/USDT" and tf == "15m":
                self._btc_ready = True
        # ← update heartbeat
        self._last_message_time = time.time()

    async def seed_from_rest(self, rest_client):
        """Seed cache from REST on startup"""
        logger.info("🌱 Seeding WebSocket cache from REST...")
        symbols = config.TRADING_PAIRS
        timeframes = ["5m", "15m", "1h", "4h"]
        for symbol in symbols:
            for tf in timeframes:
                try:
                    candles = await rest_client.fetch_ohlcv(symbol, tf, limit=200)
                    if candles:
                        key = self._get_key(symbol, tf)
                        self._cache[key] = deque(candles, maxlen=200)
                        logger.info(f"✅ Seeded {symbol} {tf}: {len(candles)} candles")
                except Exception as e:
                    logger.error(f"❌ Seed failed {symbol} {tf}: {e}")
        logger.info("🌱 Seeding complete")


class WebSocketManager:
    """
    WebSocket manager with:
    - Infinite retry (bot must never stop)
    - Heartbeat dead-detection (30s no data → reconnect)
    - Exponential backoff with jitter
    - Telegram alert on reconnect
    """

    def __init__(self, on_candle_close: Optional[Callable] = None):
        self.feed = BinanceWSFeed(on_candle_close)
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._connected = False
        self._retry = 0
        self._total_reconnects = 0
        self._message_count = 0
        self._telegram = None       # injected after init

    def set_telegram(self, telegram):
        """Inject telegram notifier for reconnect alerts"""
        self._telegram = telegram

    async def start(self):
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="ws_main")
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_monitor(), name="ws_heartbeat"
        )
        logger.info("🔌 WebSocket manager started")

    async def stop(self):
        self._stop.set()
        for t in [self._task, self._heartbeat_task]:
            if t:
                t.cancel()
                try:
                    await t
                except Exception:
                    pass
        logger.info("🔌 WebSocket manager stopped")

    async def _run(self):
        """Main loop — infinite retry"""
        while not self._stop.is_set():
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._retry += 1
                self._total_reconnects += 1
                # Exponential backoff with jitter, capped at MAX_RECONNECT_WAIT
                import random
                wait = min(BASE_RECONNECT * (2 ** min(self._retry, 6)), MAX_RECONNECT_WAIT)
                wait += random.uniform(0, 2)  # jitter

                logger.warning(
                    f"⚠️ WS disconnected (retry #{self._retry}): {e}. "
                    f"Reconnecting in {wait:.1f}s..."
                )

                if self._telegram and self._total_reconnects % 5 == 0:
                    try:
                        await self._telegram.send_message(
                            f"⚠️ WebSocket reconnecting (#{self._total_reconnects}). "
                            f"Retry #{self._retry}. Wait: {wait:.0f}s"
                        )
                    except Exception:
                        pass

                await asyncio.sleep(wait)

    async def _connect(self):
        """Connect and listen"""
        streams = [
            f"{s.replace('/','').lower()}@kline_15m"
            for s in config.TRADING_PAIRS
        ] + [
            "btcusdt@kline_5m",
            "btcusdt@kline_1h",
            "btcusdt@kline_4h",
        ]
        # dedupe
        streams = list(dict.fromkeys(streams))

        url = BINANCE_WS_URL + "/".join(streams)
        logger.info(f"🔌 Connecting WS: {len(streams)} streams")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                url,
                heartbeat=PING_INTERVAL,
                receive_timeout=45
            ) as ws:
                logger.info("✅ WebSocket CONNECTED")
                self._connected = True
                self._retry = 0

                async for msg in ws:
                    if self._stop.is_set():
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._process(msg.data)
                        self._message_count += 1
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.warning(f"⚠️ WS closed/error: {msg.type}")
                        break

        self._connected = False
        logger.warning("⚠️ WS disconnected")

    async def _heartbeat_monitor(self):
        """
        Dead-detection: if no data for DATA_DEAD_TIMEOUT seconds,
        force reconnect by cancelling _task and restarting.
        """
        await asyncio.sleep(60)  # grace period on startup
        while not self._stop.is_set():
            await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
            if not self._connected:
                continue
            stale = self.feed.seconds_since_last_message
            if stale > DATA_DEAD_TIMEOUT:
                logger.warning(
                    f"💀 WS dead! No data for {stale:.0f}s — forcing reconnect"
                )
                if self._telegram:
                    try:
                        await self._telegram.send_message(
                            f"💀 WebSocket dead ({stale:.0f}s no data) — reconnecting..."
                        )
                    except Exception:
                        pass
                # Cancel and restart main task
                if self._task and not self._task.done():
                    self._task.cancel()
                self._connected = False
                self._task = asyncio.create_task(self._run(), name="ws_main_restart")

    async def _process(self, raw: str):
        """Process WS message"""
        try:
            data = json.loads(raw)
            payload = data.get("data", {})
            k = payload.get("k", {})
            if not k:
                return

            raw_symbol = payload.get("s", "")
            symbol = raw_symbol.replace("USDT", "/USDT")
            tf = k.get("i")
            is_closed = k.get("x", False)

            candle = [
                k.get("t"),
                float(k.get("o", 0)),
                float(k.get("h", 0)),
                float(k.get("l", 0)),
                float(k.get("c", 0)),
                float(k.get("v", 0)),
            ]

            self.feed.update_cache(symbol, tf, candle)

            if is_closed and self.feed.on_candle_close:
                candles = self.feed.get_ohlcv(symbol, tf)
                if candles:
                    await self.feed.on_candle_close(symbol, tf, candles)

        except json.JSONDecodeError as e:
            logger.error(f"JSON error: {e}")
        except Exception as e:
            logger.error(f"WS process error: {e}")

    def is_connected(self) -> bool:
        return self._connected

    def get_status(self) -> Dict:
        cache_stats = {k: len(v) for k, v in self.feed._cache.items()}
        return {
            "connected": self._connected,
            "retry": self._retry,
            "total_reconnects": self._total_reconnects,
            "message_count": self._message_count,
            "btc_ready": self.feed._btc_ready,
            "last_message_seconds_ago": round(self.feed.seconds_since_last_message, 1),
            "data_fresh": self.feed.is_data_fresh,
            "cache_size": sum(len(q) for q in self.feed._cache.values()),
            "cache_stats": cache_stats,
        }
