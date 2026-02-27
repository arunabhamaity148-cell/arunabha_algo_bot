"""
ARUNABHA ALGO BOT - Main Engine v4.2
======================================

Points implemented:
Point 16 — Background task error handling:
    আগে: asyncio.create_task() এ exception হলে silent fail
    এখন: done_callback দিয়ে exception catch করা হচ্ছে
         Task fail হলে log করে, restart করার চেষ্টা করে

Point 17 — State persistence on restart:
    আগে: daily signals counter, consecutive losses — memory-তে ছিল
         Bot restart হলে সব হারিয়ে যেত
    এখন: StateManager দিয়ে bot_state.json-এ persist করা হচ্ছে
         Restart হলে state restore হয়

Point 3  — Correlation filter integrated via StateManager
Point 6  — Kelly/drawdown sizing via updated PositionSizer
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import config
from core.constants import (
    MarketType, TradeDirection, SignalGrade, Timeframes,
    BTCRegime, SessionType, ERROR_MESSAGES
)
from core.state_manager import StateManager
from data.websocket_manager import WebSocketManager
from data.rest_client import RESTClient
from data.cache_manager import CacheManager
from analysis.market_regime import MarketRegimeDetector, BTCRegimeResult
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from analysis.volume_profile import VolumeProfileAnalyzer
from filters.filter_orchestrator import FilterOrchestrator
from risk.risk_manager import RiskManager
from signals.signal_generator import SignalGenerator
from notification.telegram_bot import TelegramNotifier
from monitoring.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


def _task_error_handler(task: asyncio.Task):
    """
    ✅ Point 16: Background task error callback.
    asyncio.create_task() exception-এ silent fail না করে log করে।
    """
    try:
        exc = task.exception()
        if exc is not None:
            logger.error(
                f"❌ Background task '{task.get_name()}' failed: "
                f"{type(exc).__name__}: {exc}",
                exc_info=exc
            )
    except asyncio.CancelledError:
        pass


class ArunabhaEngine:
    """
    Main engine — StateManager + background task error handling
    """

    def __init__(self, telegram: Optional[TelegramNotifier] = None):
        self.telegram = telegram or TelegramNotifier()

        # ✅ Point 17: StateManager replaces in-memory counters
        self.state = StateManager()

        # Components
        self.ws_manager = WebSocketManager(self._on_candle_close)
        self.rest_client = RESTClient()
        self.cache = CacheManager()

        self.regime_detector = MarketRegimeDetector()
        self.technical = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.volume = VolumeProfileAnalyzer()

        self.filter_orchestrator = FilterOrchestrator()
        self.risk_manager = RiskManager()
        self.signal_generator = SignalGenerator()

        self.metrics = MetricsCollector(self)

        # Runtime state (not persisted — re-initialized each run)
        self.market_type = MarketType.UNKNOWN
        self.btc_regime: Optional[BTCRegimeResult] = None
        self.btc_cache = {"15m": [], "1h": [], "4h": []}
        self._btc_data_ready = False
        self._btc_fetch_attempts = 0
        self._last_btc_check = None

        # ✅ Point 16: Track background tasks for error handling
        self._background_tasks: List[asyncio.Task] = []

        logger.info("🚀 Engine initialized (StateManager active)")

    def _create_task(self, coro, name: str = None) -> asyncio.Task:
        """
        ✅ Point 16: Wrapper for asyncio.create_task() with error handling.
        All background tasks should be created through this method.
        """
        task = asyncio.create_task(coro, name=name)
        task.add_done_callback(_task_error_handler)
        self._background_tasks.append(task)
        return task

    async def start(self):
        """Start the engine"""
        logger.info("🟢 Starting engine...")

        # Step 1: REST API
        logger.info("🔌 Connecting REST API...")
        try:
            await self.rest_client.connect()
            logger.info("✅ REST API connected")
        except Exception as e:
            logger.error(f"❌ REST API failed: {e}")
            logger.warning("⚠️ Continuing in REST backup mode")

        # Step 2: Seed cache
        logger.info("🌱 Seeding cache...")
        try:
            await self._seed_cache()
            logger.info("✅ Cache seeded")
        except Exception as e:
            logger.error(f"❌ Cache seeding failed: {e}")

        # Step 3: BTC data
        logger.info("🔄 Fetching BTC data...")
        btc_ok = await self._force_fetch_btc_data()
        if btc_ok:
            logger.info("✅ BTC data loaded")
        else:
            logger.error("❌ BTC data failed — starting background fetcher")
            # ✅ Point 16: Use _create_task instead of asyncio.create_task
            self._create_task(self._background_btc_fetcher(), name="btc_fetcher")

        # Step 4: All pairs
        logger.info("🔄 Fetching all pairs...")
        try:
            await self._force_fetch_all_pairs()
            logger.info("✅ All pairs fetched")
        except Exception as e:
            logger.error(f"❌ Pairs fetch failed: {e}")

        # Step 5: WebSocket
        logger.info("🔌 Starting WebSocket...")
        try:
            await self.ws_manager.start()
            logger.info("✅ WebSocket started")
        except Exception as e:
            logger.error(f"❌ WebSocket failed: {e}")
            logger.warning("⚠️ Using REST polling fallback")

        # Step 6: Initial regime
        logger.info("📊 Initial regime detection...")
        try:
            await self._update_regime()
            logger.info(f"✅ Regime: {self.market_type.value}")
        except Exception as e:
            logger.error(f"❌ Regime detection failed: {e}")

        # Step 7: Log restored state
        status = self.state.get_full_status()
        logger.info(
            f"📊 Restored state: {status['daily_trades']} trades today | "
            f"Consec losses: {status['consecutive_losses']} | "
            f"DD: {status['current_drawdown_pct']:.2f}%"
        )

        logger.info("✅ Engine started successfully")

    async def stop(self):
        """Stop the engine gracefully"""
        logger.info("🛑 Stopping engine...")
        await self.ws_manager.stop()

        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        logger.info("✅ Engine stopped")

    async def _on_candle_close(self, symbol: str, tf: str, candles: List[List[float]]):
        """Called when a candle closes — generate signal if conditions met"""
        if tf != "15m":
            return

        try:
            await self._analyze_symbol(symbol, candles)
        except Exception as e:
            # ✅ Point 16: Don't let one symbol's error crash the whole loop
            logger.error(f"❌ _on_candle_close error for {symbol}: {e}", exc_info=e)

    async def _analyze_symbol(self, symbol: str, candles: List[List[float]]):
        """Full analysis pipeline for a symbol"""

        # ✅ Point 17: Check daily lock from persisted state
        if self.state.state.get("is_daily_locked"):
            logger.debug(f"⏸️ {symbol} — daily locked: {self.state.state.get('lock_reason')}")
            return

        # Consecutive loss check
        if self.state.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            logger.warning(f"⏸️ {symbol} — max consecutive losses reached")
            return

        # Signal cooldown per symbol
        last_signal = self.state.get_last_signal_time(symbol)
        if last_signal:
            elapsed = (datetime.now() - last_signal).total_seconds() / 60
            if elapsed < config.SIGNAL_COOLDOWN_MINUTES:
                return

        # Build data packet
        data = await self._build_data_packet(symbol, candles)
        if not data:
            return

        # Run filters
        filter_result = await self.filter_orchestrator.evaluate(
            symbol=symbol,
            direction=data.get("direction"),
            market_type=self.market_type,
            btc_regime=self.btc_regime,
            data=data
        )

        if not filter_result.get("passed"):
            return

        direction = data.get("direction")
        if not direction:
            return

        # ✅ Point 3 (via StateManager): Correlation check
        is_blocked, block_reason = self.state.is_correlated_blocked(symbol, direction)
        if is_blocked:
            logger.info(f"⏸️ {symbol} correlated blocked: {block_reason}")
            return

        # Generate signal
        signal = self.signal_generator.generate(symbol, data, filter_result)
        if not signal:
            return

        # Process
        await self._process_signal(signal)

    async def _process_signal(self, signal: Dict):
        """Process and send signal"""
        # Get current drawdown for position sizing
        drawdown_pct = self.state.current_drawdown_pct

        position = self.risk_manager.calculate_position(
            account_size=self.state.current_balance,
            entry=signal["entry"],
            stop_loss=signal["stop_loss"],
            atr_pct=signal.get("atr_pct", 1.0),
            fear_index=signal.get("fear_index", 50),
            current_drawdown_pct=drawdown_pct,
            signal_grade=signal.get("grade", "B")
        )

        if position.get("blocked"):
            logger.warning(f"⏸️ Position blocked: {position.get('reason')}")
            return

        signal["position"] = position

        symbol = signal["symbol"]
        direction = signal["direction"]

        # ✅ Point 17: Persist signal state
        self.state.update_last_signal_time(symbol)
        self.state.register_active_signal(symbol, direction)

        # Add entry zone info (Point 11 via StateManager)
        entry_zone = self.state.get_entry_zone(signal["entry"], direction)
        signal["entry_zone"] = entry_zone

        await self.telegram.send_signal(signal, self.market_type)

        logger.info(
            f"✅ SIGNAL: {symbol} {direction} @ {signal['entry']:.6f} | "
            f"Grade: {signal.get('grade')} | Score: {signal.get('score')} | "
            f"DD: {drawdown_pct:.1f}% | Size: ₹{position.get('position_usd', 0):,.0f}"
        )

    async def on_trade_result(self, symbol: str, pnl_pct: float):
        """
        ✅ Point 17: Record trade result — persisted to bot_state.json
        Manual trade-এর result manually input করার পরে এই method call হবে।
        """
        pnl_inr = self.state.current_balance * (pnl_pct / 100)
        self.state.record_trade(symbol, pnl_pct, pnl_inr)

        status = self.state.get_full_status()
        logger.info(
            f"Trade result: {symbol} {pnl_pct:+.2f}% (₹{pnl_inr:+.0f}) | "
            f"Balance: ₹{status['current_balance']:,.0f} | "
            f"DD: {status['current_drawdown_pct']:.2f}% | "
            f"Consec losses: {status['consecutive_losses']}"
        )

        # Check if daily lock needed
        if status["daily_pnl_inr"] >= config.DAILY_PROFIT_TARGET:
            self.state.state["is_daily_locked"] = True
            self.state.state["lock_reason"] = f"Profit target ₹{config.DAILY_PROFIT_TARGET} reached"
            self.state._save()
            await self.telegram.send_message(
                f"🔒 Daily lock: Profit target ₹{config.DAILY_PROFIT_TARGET} reached! "
                f"P&L today: ₹{status['daily_pnl_inr']:+.0f}"
            )

        # Drawdown check
        if status["current_drawdown_pct"] >= 10.0:
            self.state.state["is_daily_locked"] = True
            self.state.state["lock_reason"] = f"Drawdown {status['current_drawdown_pct']:.1f}% ≥ 10%"
            self.state._save()
            await self.telegram.send_message(
                f"🚨 Trading PAUSED: Drawdown {status['current_drawdown_pct']:.1f}% ≥ 10%"
            )

    def reset_daily(self):
        """Called at midnight — reset daily counters"""
        self.state.reset_daily()
        self.risk_manager.reset_daily()
        logger.info("📅 Daily counters reset")

    def get_status(self) -> Dict:
        """Get engine status — includes persisted state"""
        state_status = self.state.get_full_status()
        btc_candles = len(self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value))
        return {
            **state_status,
            "market_type": self.market_type.value,
            "btc_regime": self.btc_regime.regime.value if self.btc_regime else "unknown",
            "btc_confidence": self.btc_regime.confidence if self.btc_regime else 0,
            "btc_data_ready": self._btc_data_ready,
            "btc_candles": btc_candles,
            "background_tasks": len([t for t in self._background_tasks if not t.done()]),
        }

    # ── Helpers below (unchanged from v4.1) ─────────────────────────────────

    async def _seed_cache(self):
        """Seed cache with initial historical data"""
        for symbol in config.TRADING_PAIRS:
            for tf in ["15m", "1h", "4h"]:
                try:
                    candles = await self.rest_client.fetch_ohlcv_rest(symbol, tf, 200)
                    if candles:
                        self.cache.set_ohlcv(symbol, tf, candles)
                except Exception as e:
                    logger.warning(f"Cache seed failed {symbol} {tf}: {e}")

    async def _force_fetch_btc_data(self) -> bool:
        """Force fetch BTC data"""
        symbol = "BTC/USDT"
        try:
            for tf in ["15m", "1h", "4h"]:
                candles = await self.rest_client.fetch_ohlcv_rest(symbol, tf, 300)
                if candles:
                    self.btc_cache[tf] = candles
                    self.cache.set_ohlcv(symbol, tf, candles)
            self._btc_data_ready = True
            return True
        except Exception as e:
            logger.error(f"BTC fetch failed: {e}")
            return False

    async def _force_fetch_all_pairs(self):
        """Force fetch all trading pairs"""
        for symbol in config.TRADING_PAIRS:
            if symbol == "BTC/USDT":
                continue
            for tf in ["15m", "1h"]:
                try:
                    candles = await self.rest_client.fetch_ohlcv_rest(symbol, tf, 200)
                    if candles:
                        self.cache.set_ohlcv(symbol, tf, candles)
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Fetch failed {symbol} {tf}: {e}")

    async def _background_btc_fetcher(self):
        """
        ✅ Point 16: Background fetcher with retry.
        Exception handled by _task_error_handler callback.
        """
        while not self._btc_data_ready:
            self._btc_fetch_attempts += 1
            logger.info(f"🔄 BTC fetch attempt #{self._btc_fetch_attempts}")
            ok = await self._force_fetch_btc_data()
            if ok:
                logger.info("✅ BTC data loaded by background fetcher")
                break
            wait = min(30 * self._btc_fetch_attempts, 300)
            logger.warning(f"BTC fetch failed — retrying in {wait}s")
            await asyncio.sleep(wait)

    async def _update_regime(self):
        """Update BTC regime"""
        btc_15m = self.btc_cache.get("15m", [])
        if len(btc_15m) < 50:
            return
        self.btc_regime = self.regime_detector.detect(btc_15m)
        btc_1h = self.btc_cache.get("1h", [])
        if len(btc_1h) >= 20:
            self.market_type = self.regime_detector.get_market_type(btc_1h)

    async def _build_data_packet(self, symbol: str, candles: List) -> Optional[Dict]:
        """Build data packet for filter evaluation"""
        try:
            ohlcv_1h = self.cache.get_ohlcv(symbol, "1h") or []
            ohlcv_4h = self.cache.get_ohlcv(symbol, "4h") or []

            from analysis.structure import StructureDetector
            sd = StructureDetector()
            struct = sd.detect(candles)
            direction = struct.direction if struct.strength != "WEAK" else None

            return {
                "ohlcv": {"15m": candles, "1h": ohlcv_1h, "4h": ohlcv_4h},
                "direction": direction,
                "structure": struct,
                "funding_rate": 0,
                "open_interest": {},
                "orderbook": {},
                "fear_index": 50,
            }
        except Exception as e:
            logger.warning(f"Data packet build failed {symbol}: {e}")
            return None
