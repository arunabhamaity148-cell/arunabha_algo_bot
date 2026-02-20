"""
ARUNABHA ALGO BOT - Orchestrator
Coordinates all components and manages workflow
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
    """
    Orchestrates all bot components and manages workflow
    """
    
    def __init__(
        self,
        engine: ArunabhaEngine,
        scheduler: TradingScheduler,
        telegram: TelegramNotifier
    ):
        self.engine = engine
        self.scheduler = scheduler
        self.telegram = telegram
        
        # Component status
        self.component_status: Dict[str, bool] = {
            "engine": True,
            "scheduler": True,
            "websocket": True,
            "cache": True,
            "risk_manager": True
        }
        
        # Error counts
        self.error_counts: Dict[str, int] = {}
        self.max_errors = 5
        
        # Register session callbacks
        self._register_callbacks()
        
        logger.info("Orchestrator initialized")
    
    def _register_callbacks(self):
        """Register session callbacks"""
        self.scheduler.register_session_callback(
            SessionType.ASIA, self._on_asia_session
        )
        self.scheduler.register_session_callback(
            SessionType.LONDON, self._on_london_session
        )
        self.scheduler.register_session_callback(
            SessionType.NY, self._on_ny_session
        )
        self.scheduler.register_session_callback(
            SessionType.OVERLAP, self._on_overlap_session
        )
    
    async def _on_asia_session(self, session: SessionType):
        """Handle Asia session start"""
        logger.info("Asia session started - low volatility expected")
        
        # Adjust parameters for Asia session
        self.engine.market_type = MarketType.CHOPPY
        
        # Send notification
        await self.telegram.send_message(
            "🌏 Asia session started\n"
            "📊 Low volatility expected\n"
            "🎯 Range trades preferred"
        )
    
    async def _on_london_session(self, session: SessionType):
        """Handle London session start"""
        logger.info("London session started - high volatility expected")
        
        # Adjust parameters for London session
        await self.engine._update_regime()
        
        # Send notification
        await self.telegram.send_message(
            "🇬🇧 London session started\n"
            "📈 High volatility expected\n"
            "🎯 Trend trades preferred"
        )
    
    async def _on_ny_session(self, session: SessionType):
        """Handle NY session start"""
        logger.info("NY session started - highest volatility expected")
        
        # Send notification
        await self.telegram.send_message(
            "🗽 NY session started\n"
            "⚡ Highest volatility expected\n"
            "⚠️ Tight stops recommended"
        )
    
    async def _on_overlap_session(self, session: SessionType):
        """Handle overlap session (London+NY)"""
        logger.info("Overlap session started - extreme volatility expected")
        
        # Send notification
        await self.telegram.send_message(
            "🔄 London+NY Overlap\n"
            "🔥 Extreme volatility expected\n"
            "🎯 Best for breakout trades"
        )
    
    async def process_webhook(self, data: Dict):
        """Process incoming webhook data"""
        try:
            logger.info(f"Processing webhook: {data.get('type', 'unknown')}")
            
            webhook_type = data.get("type")
            
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
        """Process trade result from manual trading"""
        symbol = data.get("symbol")
        pnl_pct = data.get("pnl_pct", 0)
        
        if not symbol:
            logger.error("Trade result missing symbol")
            return
        
        # Update engine
        await self.engine.on_trade_result(symbol, pnl_pct)
        
        # Log trade
        logger.info(f"Trade result recorded: {symbol} @ {pnl_pct:.2f}%")
    
    async def _process_manual_signal(self, data: Dict):
        """Process manually entered signal"""
        # Validate signal
        required = ["symbol", "direction", "entry", "stop_loss", "take_profit"]
        if not all(k in data for k in required):
            logger.error("Manual signal missing required fields")
            return
        
        # Forward to telegram
        await self.telegram.send_signal(data, self.engine.market_type.value)
        
        logger.info(f"Manual signal processed: {data['symbol']}")
    
    async def _process_config_update(self, data: Dict):
        """Process configuration update"""
        # Update config (requires restart)
        logger.warning("Config update received - restart may be required")
        
        # Notify
        await self.telegram.send_message(
            "⚙️ Configuration update received\n"
            "🔄 Bot will restart in 60 seconds"
        )
        
        # Schedule restart
        asyncio.create_task(self._restart_with_delay(60))
    
    async def _restart_with_delay(self, delay: int):
        """Restart bot after delay"""
        await asyncio.sleep(delay)
        
        logger.info("Restarting bot...")
        
        # Stop components
        await self.engine.stop()
        await self.scheduler.stop()
        
        # Start again
        await self.engine.start()
        await self.scheduler.start()
        
        logger.info("Bot restarted")
    
    async def health_check(self) -> Dict:
        """Perform health check on all components"""
        status = {
            "status": "healthy",
            "components": {},
            "errors": {},
            "timestamp": datetime.now().isoformat()
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
        
        # Determine overall status
        if any(v > self.max_errors for v in self.error_counts.values()):
            status["status"] = "critical"
        elif any(status["components"].values()):
            status["status"] = "degraded"
        
        return status
    
    def _increment_error(self, component: str):
        """Increment error count for component"""
        self.error_counts[component] = self.error_counts.get(component, 0) + 1
        
        if self.error_counts[component] >= self.max_errors:
            logger.critical(f"Component {component} has {self.error_counts[component]} errors")
    
    async def emergency_stop(self, reason: str):
        """Emergency stop all operations"""
        logger.critical(f"EMERGENCY STOP: {reason}")
        
        # Notify
        await self.telegram.send_message(
            f"🚨 EMERGENCY STOP\n"
            f"Reason: {reason}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # Stop components
        await self.engine.stop()
        await self.scheduler.stop()
        
        # Update status
        self.component_status = {k: False for k in self.component_status}
        
        logger.critical("Bot stopped - manual restart required")
    
    async def resume(self):
        """Resume bot operations"""
        logger.info("Resuming bot operations...")
        
        # Start components
        await self.engine.start()
        await self.scheduler.start()
        
        # Update status
        self.component_status = {k: True for k in self.component_status}
        
        # Notify
        await self.telegram.send_message(
            "✅ Bot resumed normal operations"
        )
        
        logger.info("Bot resumed")
    
    def get_stats(self) -> Dict:
        """Get orchestrator statistics"""
        return {
            "component_status": self.component_status,
            "error_counts": self.error_counts,
            "uptime": self._get_uptime(),
            "engine_status": self.engine.get_status(),
            "session_info": self.scheduler.get_session_info()
        }
    
    def _get_uptime(self) -> str:
        """Get bot uptime"""
        # This would need a start time tracking
        return "N/A"
