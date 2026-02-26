"""
ARUNABHA ALGO BOT - Orchestrator v4.1

FIXES:
- BUG-19: Asia session এ hardcoded CHOPPY market_type override সরানো হয়েছে
          আগে প্রতি Asia session শুরুতে engine.market_type = CHOPPY হয়ে যেত
          এখন regime detector নিজে decide করবে
- BUG-20: health_check() এর status logic ঠিক করা হয়েছে
          আগে: any(status["components"].values()) — এটা সবসময় True (wrong!)
          এখন: any(v != "ok" for v in ...) — সঠিক check
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

import config
from core.constants import MarketType, TradeDirection, SignalGrade, SessionType
from core.engine import ArunabhaEngine
from core.scheduler import TradingScheduler
from notification.telegram_bot import TelegramNotifier
from monitoring.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates all bot components and manages workflow"""

    def __init__(
        self,
        engine: ArunabhaEngine,
        scheduler: TradingScheduler,
        telegram: TelegramNotifier
    ):
        self.engine = engine
        self.scheduler = scheduler
        self.telegram = telegram
        self.start_time = datetime.now()

        self.component_status: Dict[str, bool] = {
            "engine": True,
            "scheduler": True,
            "websocket": True,
            "cache": True,
            "risk_manager": True
        }

        self.error_counts: Dict[str, int] = {}
        self.max_errors = 5

        self._register_callbacks()
        logger.info("Orchestrator initialized")

    def _register_callbacks(self):
        self.scheduler.register_session_callback(SessionType.ASIA, self._on_asia_session)
        self.scheduler.register_session_callback(SessionType.LONDON, self._on_london_session)
        self.scheduler.register_session_callback(SessionType.NY, self._on_ny_session)
        self.scheduler.register_session_callback(SessionType.OVERLAP, self._on_overlap_session)

    async def _on_asia_session(self, session: SessionType):
        """
        ✅ FIX BUG-19: Hardcoded market_type = CHOPPY সরানো হয়েছে
        Asia session এ market টা সত্যিই choppy হতে পারে, কিন্তু
        regime detector নিজে এটা বলবে — আমরা force করব না
        """
        logger.info("🌏 Asia session started")

        # ✅ Regime update করো (hardcode না করে)
        try:
            await self.engine._update_regime()
            logger.info("Regime updated for Asia session")
        except Exception as e:
            logger.error(f"Regime update failed: {e}")

        await self.telegram.send_message(
            "🌏 Asia session started\n"
            "📊 Typically low volatility\n"
            "🎯 Range/choppy trades possible"
        )

    async def _on_london_session(self, session: SessionType):
        logger.info("🇬🇧 London session started")
        await self.engine._update_regime()
        await self.telegram.send_message(
            "🇬🇧 London session started\n"
            "📈 High volatility expected\n"
            "🎯 Trend trades preferred"
        )

    async def _on_ny_session(self, session: SessionType):
        logger.info("🗽 NY session started")
        await self.engine._update_regime()
        await self.telegram.send_message(
            "🗽 NY session started\n"
            "⚡ Highest volatility expected\n"
            "⚠️ Tight stops recommended"
        )

    async def _on_overlap_session(self, session: SessionType):
        logger.info("🔄 London+NY Overlap started")
        await self.telegram.send_message(
            "🔄 London+NY Overlap\n"
            "🔥 Extreme volatility expected\n"
            "🎯 Best for breakout trades"
        )

    async def process_webhook(self, data: Dict):
        try:
            webhook_type = data.get("type")
            logger.info(f"Processing webhook: {webhook_type}")

            if webhook_type == "trade_result":
                await self._process_trade_result(data)
            elif webhook_type == "manual_signal":
                await self._process_manual_signal(data)
            elif webhook_type == "config_update":
                await self._process_config_update(data)
            else:
                logger.warning(f"Unknown webhook type: {webhook_type}")

        except Exception as e:
            logger.error(f"Webhook processing error: {e}")

    async def _process_trade_result(self, data: Dict):
        symbol = data.get("symbol")
        pnl_pct = data.get("pnl_pct", 0)
        if not symbol:
            logger.error("Trade result missing symbol")
            return
        await self.engine.on_trade_result(symbol, pnl_pct)
        logger.info(f"Trade result recorded: {symbol} @ {pnl_pct:.2f}%")

    async def _process_manual_signal(self, data: Dict):
        required = ["symbol", "direction", "entry", "stop_loss", "take_profit"]
        if not all(k in data for k in required):
            logger.error("Manual signal missing required fields")
            return
        await self.telegram.send_signal(data, self.engine.market_type.value)
        logger.info(f"Manual signal processed: {data['symbol']}")

    async def _process_config_update(self, data: Dict):
        logger.warning("Config update received - restart may be required")
        await self.telegram.send_message(
            "⚙️ Configuration update received\n"
            "🔄 Bot will restart in 60 seconds"
        )
        asyncio.create_task(self._restart_with_delay(60))

    async def _restart_with_delay(self, delay: int):
        await asyncio.sleep(delay)
        logger.info("Restarting bot...")
        await self.engine.stop()
        await self.scheduler.stop()
        await self.engine.start()
        await self.scheduler.start()
        logger.info("Bot restarted")

    async def health_check(self) -> Dict:
        """
        ✅ FIX BUG-20: Health check status logic সঠিক করা হয়েছে
        আগে: any(status["components"].values()) → সবসময় True → সবসময় "degraded"
        এখন: any(v != "ok" for v in values) → সঠিকভাবে error detect করে
        """
        status = {
            "status": "healthy",
            "components": {},
            "errors": {},
            "timestamp": datetime.now().isoformat(),
            "uptime": str(datetime.now() - self.start_time).split('.')[0]
        }

        # Check engine
        try:
            engine_status = self.engine.get_status()
            status["components"]["engine"] = "ok"
            status["market"] = engine_status
        except Exception as e:
            status["components"]["engine"] = "error"
            status["errors"]["engine"] = str(e)
            self._increment_error("engine")

        # Check scheduler
        try:
            scheduler_info = self.scheduler.get_session_info()
            status["components"]["scheduler"] = "ok"
            status["session"] = scheduler_info
        except Exception as e:
            status["components"]["scheduler"] = "error"
            status["errors"]["scheduler"] = str(e)
            self._increment_error("scheduler")

        # Check cache
        try:
            cache_size = self.engine.cache.size()
            status["components"]["cache"] = "ok"
            status["cache_size"] = cache_size
        except Exception as e:
            status["components"]["cache"] = "error"
            status["errors"]["cache"] = str(e)
            self._increment_error("cache")

        # ✅ FIXED: সঠিক logic দিয়ে overall status নির্ধারণ
        if any(v > self.max_errors for v in self.error_counts.values()):
            status["status"] = "critical"
        elif any(v != "ok" for v in status["components"].values()):
            # কোনো component "ok" না হলেই degraded
            status["status"] = "degraded"
        # else: "healthy" থাকে

        return status

    def _increment_error(self, component: str):
        self.error_counts[component] = self.error_counts.get(component, 0) + 1
        if self.error_counts[component] >= self.max_errors:
            logger.critical(f"Component {component} has {self.error_counts[component]} errors — needs attention!")

    async def emergency_stop(self, reason: str):
        logger.critical(f"EMERGENCY STOP: {reason}")
        await self.telegram.send_message(
            f"🚨 EMERGENCY STOP\n"
            f"Reason: {reason}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.engine.stop()
        await self.scheduler.stop()
        self.component_status = {k: False for k in self.component_status}
        logger.critical("Bot stopped — manual restart required")

    async def resume(self):
        logger.info("Resuming bot operations...")
        await self.engine.start()
        await self.scheduler.start()
        self.component_status = {k: True for k in self.component_status}
        await self.telegram.send_message("✅ Bot resumed normal operations")
        logger.info("Bot resumed")

    def get_stats(self) -> Dict:
        return {
            "component_status": self.component_status,
            "error_counts": self.error_counts,
            "uptime": str(datetime.now() - self.start_time).split('.')[0],
            "engine_status": self.engine.get_status(),
            "session_info": self.scheduler.get_session_info()
        }
