"""
ARUNABHA ALGO BOT - WebSocket Manager v5.1
===========================================
FIXES:
ISSUE 3:  Memory leak — explicit session.close() on every exit path
          aiohttp.ClientSession created fresh on each reconnect (not reused)
          _current_session tracked and forcibly closed on heartbeat restart
ISSUE 17: 1h/4h cache synced from 15m data (candle aggregation)
          Every 4 closed 15m candles → update 1h candle in cache
          Every 16 → update 4h candle

Other fixes retained from v5.0:
- Heartbeat dead-detection (30s)
- Infinite retry with exponential backoff + jitter
- Telegram alert on reconnect
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Callable
from collections import deque
from datetime import datetime

import aiohttp
import config

logger = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://fstream.binance.com/stream?streams="
PING_INTERVAL = 20
BASE_RECONNECT = 3
MAX_RECONNECT_WAIT = 120
DATA_DEAD_TIMEOUT = 30
HEARTBEAT_CHECK_INTERVAL = 10
CACHE_MAXLEN = 200


class BinanceWSFeed:

    def __init__(self, on_candle_close: Optional[Callable] = None):
        self.on_candle_close = on_candle_close
        self._cache: Dict[str, deque] = {}
        self._message_count = 0
        self._btc_ready = False
        self._last_message_time: float = time.time()
        # ISSUE 17: 15m candle counters for 1h/4h aggregation
        self._candle_counts: Dict[str, int] = {}

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
        return list(self._cache.get(key, []))

    def update_cache(self, symbol: str, tf: str, candle: List[float], is_closed: bool = False):
        key = self._get_key(symbol, tf)
        if key not in self._cache:
            self._cache[key] = deque(maxlen=CACHE_MAXLEN)

        if self._cache[key] and int(candle[0]) == int(self._cache[key][-1][0]):
            self._cache[key][-1] = candle
        else:
            self._cache[key].append(candle)
            if symbol == "BTC/USDT" and tf == "15m":
                self._btc_ready = True

        self._last_message_time = time.time()

        # ISSUE 17 FIX: Aggregate 15m → 1h and 4h on close
        if is_closed and tf == "15m":
            self._aggregate_higher_tf(symbol, candle)

    def _aggregate_higher_tf(self, symbol: str, closed_15m: List[float]):
        """
        ISSUE 17 FIX: Build 1h/4h candles from 15m closes.
        4 × 15m = 1h candle
        16 × 15m = 4h candle
        """
        count_key = symbol
        self._candle_counts[count_key] = self._candle_counts.get(count_key, 0) + 1
        count = self._candle_counts[count_key]

        # ── 1h aggregation (every 4 × 15m) ──────────────────────────
        if count % 4 == 0:
            candles_15m = list(self._cache.get(self._get_key(symbol, "15m"), []))
            if len(candles_15m) >= 4:
                last4 = candles_15m[-4:]
                h1_candle = self._aggregate_candles(last4)
                if h1_candle:
                    key_1h = self._get_key(symbol, "1h")
                    if key_1h not in self._cache:
                        self._cache[key_1h] = deque(maxlen=CACHE_MAXLEN)
                    if self._cache[key_1h] and int(h1_candle[0]) == int(self._cache[key_1h][-1][0]):
                        self._cache[key_1h][-1] = h1_candle
                    else:
                        self._cache[key_1h].append(h1_candle)
                    logger.debug(f"1h candle updated: {symbol} @ {h1_candle[4]:.4f}")

        # ── 4h aggregation (every 16 × 15m) ─────────────────────────
        if count % 16 == 0:
            candles_15m = list(self._cache.get(self._get_key(symbol, "15m"), []))
            if len(candles_15m) >= 16:
                last16 = candles_15m[-16:]
                h4_candle = self._aggregate_candles(last16)
                if h4_candle:
                    key_4h = self._get_key(symbol, "4h")
                    if key_4h not in self._cache:
                        self._cache[key_4h] = deque(maxlen=CACHE_MAXLEN)
                    if self._cache[key_4h] and int(h4_candle[0]) == int(self._cache[key_4h][-1][0]):
                        self._cache[key_4h][-1] = h4_candle
                    else:
                        self._cache[key_4h].append(h4_candle)
                    logger.debug(f"4h candle updated: {symbol} @ {h4_candle[4]:.4f}")

    def _aggregate_candles(self, candles: List[List]) -> Optional[List]:
        """Merge N candles into one OHLCV candle"""
        if not candles:
            return None
        try:
            timestamp = candles[0][0]
            open_  = float(candles[0][1])
            high   = max(float(c[2]) for c in candles)
            low    = min(float(c[3]) for c in candles)
            close  = float(candles[-1][4])
            volume = sum(float(c[5]) for c in candles)
            return [timestamp, open_, high, low, close, volume]
        except Exception as e:
            logger.warning(f"Candle aggregation failed: {e}")
            return None

    async def seed_from_rest(self, rest_client):
        logger.info("🌱 Seeding WS cache from REST...")
        for symbol in config.TRADING_PAIRS:
            for tf in ["5m", "15m", "1h", "4h"]:
                try:
                    candles = await rest_client.fetch_ohlcv(symbol, tf, limit=200)
                    if candles:
                        key = self._get_key(symbol, tf)
                        self._cache[key] = deque(candles, maxlen=CACHE_MAXLEN)
                except Exception as e:
                    logger.error(f"Seed failed {symbol} {tf}: {e}")
        logger.info("🌱 Seeding done")


class WebSocketManager:
    """
    ISSUE 3 FIX: Explicit session close on every exit path.
    _current_session tracked; forcibly closed by heartbeat restart.
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
        self._telegram = None
        # ISSUE 3 FIX: track current session for explicit close
        self._current_session: Optional[aiohttp.ClientSession] = None

    def set_telegram(self, telegram):
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
        await self._close_current_session()
        for t in [self._task, self._heartbeat_task]:
            if t:
                t.cancel()
                try:
                    await t
                except Exception:
                    pass
        logger.info("🔌 WebSocket stopped")

    async def _close_current_session(self):
        """ISSUE 3 FIX: Explicitly close aiohttp session"""
        if self._current_session and not self._current_session.closed:
            try:
                await self._current_session.close()
                logger.debug("WS session closed explicitly")
            except Exception as e:
                logger.debug(f"Session close error: {e}")
            finally:
                self._current_session = None

    async def _run(self):
        while not self._stop.is_set():
            try:
                await self._connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._retry += 1
                self._total_reconnects += 1
                import random
                wait = min(BASE_RECONNECT * (2 ** min(self._retry, 6)), MAX_RECONNECT_WAIT)
                wait += random.uniform(0, 2)
                logger.warning(f"⚠️ WS error (retry #{self._retry}): {e} — reconnect in {wait:.1f}s")
                if self._telegram and self._total_reconnects % 5 == 0:
                    try:
                        await self._telegram.send_message(
                            f"⚠️ WS reconnecting #{self._total_reconnects} — wait {wait:.0f}s"
                        )
                    except Exception:
                        pass
                await asyncio.sleep(wait)

    async def _connect(self):
        """ISSUE 3 FIX: Session created fresh, always closed in finally"""
        streams = list(dict.fromkeys(
            [f"{s.replace('/','').lower()}@kline_15m" for s in config.TRADING_PAIRS]
            + ["btcusdt@kline_5m", "btcusdt@kline_1h", "btcusdt@kline_4h"]
        ))
        url = BINANCE_WS_URL + "/".join(streams)
        logger.info(f"🔌 Connecting WS ({len(streams)} streams)...")

        # ISSUE 3 FIX: Close old session before creating new one
        await self._close_current_session()

        # ISSUE 3 FIX: New session each connect cycle
        session = aiohttp.ClientSession()
        self._current_session = session

        try:
            async with session.ws_connect(
                url,
                heartbeat=PING_INTERVAL,
                receive_timeout=45
            ) as ws:
                logger.info("✅ WS CONNECTED")
                self._connected = True
                self._retry = 0

                async for msg in ws:
                    if self._stop.is_set():
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._process(msg.data)
                        self._message_count += 1
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.warning(f"⚠️ WS {msg.type}")
                        break
        finally:
            # ISSUE 3 FIX: Always close session
            self._connected = False
            await self._close_current_session()
            logger.debug("WS _connect() session cleaned up")

    async def _heartbeat_monitor(self):
        await asyncio.sleep(60)
        while not self._stop.is_set():
            await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
            if not self._connected:
                continue
            stale = self.feed.seconds_since_last_message
            if stale > DATA_DEAD_TIMEOUT:
                logger.warning(f"💀 WS dead ({stale:.0f}s) — forcing reconnect")
                if self._telegram:
                    try:
                        await self._telegram.send_message(
                            f"💀 WS dead {stale:.0f}s — reconnecting..."
                        )
                    except Exception:
                        pass
                # ISSUE 3 FIX: Close session before restarting task
                await self._close_current_session()
                self._connected = False
                if self._task and not self._task.done():
                    self._task.cancel()
                self._task = asyncio.create_task(self._run(), name="ws_restart")

    async def _process(self, raw: str):
        try:
            data = json.loads(raw)
            payload = data.get("data", {})
            k = payload.get("k", {})
            if not k:
                return
            symbol = payload.get("s", "").replace("USDT", "/USDT")
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
            # ISSUE 17 FIX: pass is_closed for aggregation
            self.feed.update_cache(symbol, tf, candle, is_closed=is_closed)
            if is_closed and self.feed.on_candle_close:
                candles = self.feed.get_ohlcv(symbol, tf)
                if candles:
                    await self.feed.on_candle_close(symbol, tf, candles)
        except Exception as e:
            logger.error(f"WS process error: {e}")

    def is_connected(self) -> bool:
        return self._connected

    def get_status(self) -> Dict:
        return {
            "connected": self._connected,
            "retry": self._retry,
            "total_reconnects": self._total_reconnects,
            "message_count": self._message_count,
            "btc_ready": self.feed._btc_ready,
            "last_message_ago": round(self.feed.seconds_since_last_message, 1),
            "data_fresh": self.feed.is_data_fresh,
            "session_open": self._current_session is not None and not self._current_session.closed,
            "cache_keys": len(self.feed._cache),
        }
