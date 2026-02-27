"""
ARUNABHA ALGO BOT - Main Engine v5.0
======================================
UPGRADES v5.0:
- Paper Trading Mode: PAPER_TRADING=true → signals generated, NO real orders
  P&L simulated in memory, all sent to Telegram with [PAPER] tag
- Adaptive Thresholds: last 20 signals win rate → auto-tune Tier2 threshold
  win rate < 40% → threshold +10%, win rate > 65% → threshold -5%
- Session-Aware Position Sizing: Asia=0.7x, London/NY overlap=1.2x, high_vol=0.8x
- BTC prices properly passed to Tier3 for correlation fix
- WebSocket telegram injection for reconnect alerts

Previous points retained:
Point 16 — Background task error handling
Point 17 — State persistence on restart
Point 3  — Correlation filter integrated via StateManager
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Any, Tuple, Deque
from datetime import datetime
from collections import deque

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

# Paper trading mode — set PAPER_TRADING=true in .env
PAPER_TRADING = os.getenv("PAPER_TRADING", "false").lower() == "true"

# Adaptive threshold config
ADAPTIVE_WINDOW = 20          # last N signals
ADAPTIVE_MIN_THRESHOLD = 50   # never go below this
ADAPTIVE_MAX_THRESHOLD = 80   # never go above this


def _task_error_handler(task: asyncio.Task):
    """Point 16: Background task error callback"""
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
    Main engine v5.0
    Paper trading + Adaptive thresholds + Session sizing + Correlation fix
    """

    def __init__(self, telegram: Optional[TelegramNotifier] = None):
        self.telegram = telegram or TelegramNotifier()

        # State manager
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

        # Runtime state
        self.market_type = MarketType.UNKNOWN
        self.btc_regime: Optional[BTCRegimeResult] = None
        self.btc_cache = {"15m": [], "1h": [], "4h": []}
        self._btc_data_ready = False
        self._btc_fetch_attempts = 0
        self._last_btc_check = None
        self._background_tasks: List[asyncio.Task] = []

        # Paper trading state
        self.paper_trading = PAPER_TRADING
        self._paper_pnl: float = 0.0
        self._paper_trades: int = 0
        if self.paper_trading:
            logger.info("📄 PAPER TRADING MODE ACTIVE — no real orders will be placed")

        # Adaptive threshold tracking
        self._signal_history: Deque[Dict] = deque(maxlen=ADAPTIVE_WINDOW)
        self._adaptive_threshold: float = config.MIN_TIER2_SCORE

        # Last signal time per symbol
        self.last_signal_time: Dict[str, datetime] = {}
        self.daily_signals: int = self.state.state.get("daily_signals_count", 0)

    def _create_task(self, coro, name: str = None) -> asyncio.Task:
        """ISSUE 13 FIX: add_done_callback properly registered"""
        task = asyncio.create_task(coro, name=name)
        task.add_done_callback(_task_error_handler)   # ← was missing before
        self._background_tasks.append(task)
        return task

    async def start(self):
        """Start engine — REST + Cache + BTC + WebSocket"""
        logger.info("⚙️ Engine starting...")

        # Inject telegram into WS manager for reconnect alerts
        self.ws_manager.set_telegram(self.telegram)

        try:
            await self.rest_client.connect()
            logger.info("✅ REST client connected")
        except Exception as e:
            logger.error(f"❌ REST connection failed: {e}")

        # Seed cache
        await self._seed_cache()

        # Force BTC fetch
        ok = await self._force_fetch_btc_data()
        if not ok:
            logger.warning("⚠️ BTC data not ready — will retry in background")
            self._create_task(self._background_btc_fetcher(), "btc_fetcher")

        # Start WebSocket
        await self.ws_manager.start()

        # Background tasks
        self._create_task(self._update_regime(), "regime_update")

        if self.paper_trading:
            await self.telegram.send_message(
                "📄 <b>PAPER TRADING MODE</b>\n"
                "Signals will be generated but NO real orders placed.\n"
                f"Simulating with ₹{config.ACCOUNT_SIZE:,.0f}"
            )

        logger.info(f"✅ Engine started (paper_trading={self.paper_trading})")

    async def stop(self):
        """Stop engine"""
        await self.ws_manager.stop()
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        try:
            await self.rest_client.close()
        except Exception:
            pass
        logger.info("✅ Engine stopped")

    async def _on_candle_close(self, symbol: str, tf: str, candles: List[List[float]]):
        """Called on every closed candle"""
        if tf != "15m":
            return

        # Update BTC cache
        if symbol == "BTC/USDT":
            self.btc_cache["15m"] = candles
            if not self._btc_data_ready and len(candles) >= 50:
                self._btc_data_ready = True
            self._create_task(self._update_regime(), "regime")
            return

        await self._analyze_symbol(symbol, candles)

    async def _analyze_symbol(self, symbol: str, candles: List[List[float]]):
        """Full analysis pipeline for a symbol"""
        if not self._btc_data_ready:
            logger.debug(f"BTC not ready — skipping {symbol}")
            return

        # Check daily limits
        if self.state.state.get("is_daily_locked"):
            return

        max_signals = config.MAX_SIGNALS_PER_DAY.get(
            self.market_type.value, config.MAX_SIGNALS_PER_DAY["default"]
        )
        if self.daily_signals >= max_signals:
            return

        # Cooldown check
        last = self.last_signal_time.get(symbol)
        if last:
            elapsed = (datetime.now() - last).total_seconds() / 60
            if elapsed < config.COOLDOWN_MINUTES:
                return
# Cooldown check
        last = self.last_signal_time.get(symbol)
        if last:
            elapsed = (datetime.now() - last).total_seconds() / 60
            if elapsed < config.COOLDOWN_MINUTES:
                return

        # Risk check
        can_trade, reason = self.risk_manager.can_trade(symbol, self.market_type)
        if not can_trade:
            logger.debug(f"Risk blocked {symbol}: {reason}")
            return

        # Build data packet
        data = await self._build_data_packet(symbol, candles)
        if not data:
            return

        direction = data.get("direction")
        if not direction:
            return

        # Correlation check via StateManager
        is_blocked, block_reason = self.state.is_correlated_blocked(symbol, direction)
        if is_blocked:
            logger.info(f"⏸️ Correlated block {symbol}: {block_reason}")
            return

        # Filter evaluation with adaptive threshold
        filter_result = self.filter_orchestrator.evaluate(
            symbol=symbol,
            direction=direction,
            market_type=self.market_type,
            btc_regime=self.btc_regime,
            data=data,
            tier2_threshold_override=self._adaptive_threshold
        )

        if not filter_result.get("passed"):
            logger.debug(f"Filters failed {symbol}: {filter_result.get('reason')}")
            return

        # Generate signal
        signal = self.signal_generator.generate(symbol, data, filter_result)
        if not signal:
            return

        await self._process_signal(signal)

    async def _process_signal(self, signal: Dict):
        """Process signal — paper trading aware, session-aware sizing"""
        drawdown_pct = self.state.current_drawdown_pct

        # Session-aware position sizing multiplier
        session_mult = self._get_session_multiplier()

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
            return

        # Apply session multiplier to position size
        if session_mult != 1.0:
            pos_usd = position.get("position_usd", 0)
            position["position_usd"] = round(pos_usd * session_mult, 0)
            position["session_multiplier"] = session_mult
            logger.info(f"Session sizing: {session_mult}x → ₹{position['position_usd']:,.0f}")

        signal["position"] = position
        symbol = signal["symbol"]
        direction = signal["direction"]

        # Paper trading tag
        if self.paper_trading:
            signal["paper_trade"] = True
            self._paper_trades += 1

        # Persist state
        self.state.update_last_signal_time(symbol)
        self.state.register_active_signal(symbol, direction)
        self.daily_signals += 1
        self.last_signal_time[symbol] = datetime.now()

        # Entry zone (calculate before sending)
        entry_zone = self.state.get_entry_zone(signal["entry"], direction)
        signal["entry_zone"] = entry_zone

        # ISSUE 12 FIX: Validate current price is still in entry zone
        # (price may have moved since signal was generated)
        try:
            ohlcv_now = self.cache.get_ohlcv(symbol, "15m")
            if ohlcv_now:
                current_price = float(ohlcv_now[-1][4])
                zone_ok, zone_msg = self.state.check_entry_zone_valid(signal, current_price)
                if not zone_ok:
                    logger.info(f"⏸️ Entry zone stale {symbol}: {zone_msg} — skipping signal")
                    self.state.clear_active_signal(symbol)
                    self.daily_signals -= 1
                    return
        except Exception as e:
            logger.debug(f"Entry zone check error {symbol}: {e}")

        # Adaptive threshold: record signal for future win rate tracking
        self._signal_history.append({
            "symbol": symbol,
            "direction": direction,
            "timestamp": datetime.now().isoformat(),
            "grade": signal.get("grade"),
            "score": signal.get("score"),
            "result": None  # filled in by on_trade_result
        })

        # Send
        await self.telegram.send_signal(signal, self.market_type)

        prefix = "📄 [PAPER] " if self.paper_trading else ""
        logger.info(
            f"{prefix}✅ SIGNAL: {symbol} {direction} @ {signal['entry']:.6f} | "
            f"Grade: {signal.get('grade')} | Score: {signal.get('score')} | "
            f"Session: {session_mult}x | DD: {drawdown_pct:.1f}%"
        )

        # Update adaptive threshold after enough data
        self._update_adaptive_threshold()

    def _get_session_multiplier(self) -> float:
        """
        ISSUE 19 FIX: Session multipliers from config (not hardcoded)
        config.SESSION_SIZE_MULTIPLIERS can be hot-reloaded via /reload
        """
        import pytz
        mults = config.SESSION_SIZE_MULTIPLIERS
        now = datetime.now(pytz.timezone("Asia/Kolkata"))
        hour = now.hour

        if self.market_type == MarketType.HIGH_VOL:
            return mults.get("high_vol", 0.8)
        if 13 <= hour <= 15:
            return mults.get("london_open", 1.2)
        if 18 <= hour <= 20:
            return mults.get("ny_open", 1.2)
        if 7 <= hour <= 11:
            return mults.get("asia", 0.7)
        return mults.get("default", 1.0)

    def _update_adaptive_threshold(self):
        """
        Adaptive Tier2 threshold based on recent signal win rate.
        win_rate < 40% → raise threshold (be more selective)
        win_rate > 65% → lower slightly (allow more signals)
        """
        completed = [s for s in self._signal_history if s.get("result") is not None]
        if len(completed) < 10:
            return   # not enough data yet

        wins = sum(1 for s in completed if s["result"] == "WIN")
        win_rate = wins / len(completed)

        old = self._adaptive_threshold

        if win_rate < 0.40:
            # performing poorly → be more selective
            self._adaptive_threshold = min(
                self._adaptive_threshold + 5.0,
                ADAPTIVE_MAX_THRESHOLD
            )
        elif win_rate > 0.65:
            # performing well → allow slightly more signals
            self._adaptive_threshold = max(
                self._adaptive_threshold - 3.0,
                ADAPTIVE_MIN_THRESHOLD
            )

        if self._adaptive_threshold != old:
            logger.info(
                f"🎯 Adaptive threshold: {old:.0f}% → {self._adaptive_threshold:.0f}% "
                f"(win_rate={win_rate:.0%} over {len(completed)} trades)"
            )

    async def on_trade_result(self, symbol: str, pnl_pct: float):
        """Record trade result — updates adaptive threshold"""
        pnl_inr = self.state.current_balance * (pnl_pct / 100)

        if self.paper_trading:
            pnl_inr = self.state.current_balance * (pnl_pct / 100)
            # ISSUE 20 FIX: persisted via state_manager (survives restart)
            self.state.record_paper_trade(symbol, pnl_inr)
            self._paper_pnl = self.state.state.get("paper_pnl_inr", 0.0)
            logger.info(
                f"📄 Paper trade: {symbol} {pnl_pct:+.2f}% "
                f"(sim ₹{pnl_inr:+.0f}) | Total: ₹{self._paper_pnl:+,.0f}"
            )
        else:
            pnl_inr = self.state.current_balance * (pnl_pct / 100)
            self.state.record_trade(symbol, pnl_pct, pnl_inr)

        # Update signal history for adaptive threshold
        for s in reversed(self._signal_history):
            if s["symbol"] == symbol and s["result"] is None:
                s["result"] = "WIN" if pnl_pct > 0 else "LOSS"
                break

        self._update_adaptive_threshold()

        status = self.state.get_full_status()
        if status["daily_pnl_inr"] >= config.DAILY_PROFIT_TARGET:
            self.state.state["is_daily_locked"] = True
            self.state.state["lock_reason"] = f"Profit target ₹{config.DAILY_PROFIT_TARGET} reached"
            self.state._save()
            await self.telegram.send_message(
                f"🔒 Daily lock: Target reached! P&L: ₹{status['daily_pnl_inr']:+.0f}"
            )

        if status["current_drawdown_pct"] >= 10.0:
            self.state.state["is_daily_locked"] = True
            self.state.state["lock_reason"] = f"Drawdown {status['current_drawdown_pct']:.1f}%"
            self.state._save()
            await self.telegram.send_message(
                f"🚨 Trading PAUSED: Drawdown {status['current_drawdown_pct']:.1f}% ≥ 10%"
            )

    def reset_daily(self):
        self.state.reset_daily()
        self.risk_manager.reset_daily()
        self.daily_signals = 0
        logger.info("📅 Daily counters reset")

    def get_status(self) -> Dict:
        state_status = self.state.get_full_status()
        btc_candles = len(self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value))
        ws_status = self.ws_manager.get_status()
        return {
            **state_status,
            "market_type": self.market_type.value,
            "btc_regime": self.btc_regime.regime.value if self.btc_regime else "unknown",
            "btc_confidence": self.btc_regime.confidence if self.btc_regime else 0,
            "btc_data_ready": self._btc_data_ready,
            "btc_candles": btc_candles,
            "paper_trading": self.paper_trading,
            "paper_pnl": round(self._paper_pnl, 2) if self.paper_trading else None,
            "adaptive_threshold": round(self._adaptive_threshold, 1),
            "ws_connected": ws_status.get("connected"),
            "ws_last_message_ago": ws_status.get("last_message_seconds_ago"),
            "ws_reconnects": ws_status.get("total_reconnects"),
            "background_tasks": len([t for t in self._background_tasks if not t.done()]),
        }

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _seed_cache(self):
        for symbol in config.TRADING_PAIRS:
            for tf in ["15m", "1h", "4h"]:
                try:
                    candles = await self.rest_client.fetch_ohlcv_rest(symbol, tf, 200)
                    if candles:
                        self.cache.set_ohlcv(symbol, tf, candles)
                except Exception as e:
                    logger.warning(f"Cache seed failed {symbol} {tf}: {e}")

    async def _force_fetch_btc_data(self) -> bool:
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
        while not self._btc_data_ready:
            self._btc_fetch_attempts += 1
            ok = await self._force_fetch_btc_data()
            if ok:
                break
            wait = min(30 * self._btc_fetch_attempts, 300)
            await asyncio.sleep(wait)

    async def _update_regime(self):
        btc_15m = self.btc_cache.get("15m", [])
        if len(btc_15m) < 50:
            return
        self.btc_regime = self.regime_detector.detect(btc_15m)
        btc_1h = self.btc_cache.get("1h", [])
        if len(btc_1h) >= 20:
            self.market_type = self.regime_detector.get_market_type(btc_1h)

    async def _build_data_packet(self, symbol: str, candles: List) -> Optional[Dict]:
        """Build full data packet — includes btc_ohlcv for Tier3 correlation fix"""
        try:
            ohlcv_1h = self.cache.get_ohlcv(symbol, "1h") or []
            ohlcv_4h = self.cache.get_ohlcv(symbol, "4h") or []

            sd = StructureDetector()
            struct = sd.detect(candles)
            direction = struct.direction if struct.strength != "WEAK" else None

            # Fetch sentiment data async
            try:
                from data.sentiment_fetcher import fetch_all_sentiment
                sentiment_data = await fetch_all_sentiment()
            except Exception:
                sentiment_data = None

            return {
                "ohlcv": {"15m": candles, "1h": ohlcv_1h, "4h": ohlcv_4h},
                "btc_ohlcv": {          # ← FIXED: passed to Tier3 correlation
                    "15m": self.btc_cache.get("15m", []),
                    "1h": self.btc_cache.get("1h", []),
                },
                "direction": direction,
                "structure": struct,
                "funding_rate": 0,
                "open_interest": {},
                "orderbook": {},
                "fear_index": 50,
                "sentiment": sentiment_data,   # ← passed to Tier1/Tier2 sentiment
            }
        except Exception as e:
            logger.warning(f"Data packet build failed {symbol}: {e}")
            return None