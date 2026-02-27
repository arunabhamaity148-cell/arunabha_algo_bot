"""
ARUNABHA ALGO BOT - Orchestrator
Coordinates Engine + Scheduler + Telegram for webhook and manual triggers
"""

import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrates communication between Engine, Scheduler, and Telegram.
    Handles incoming webhooks and manual commands.
    """

    def __init__(self, engine, scheduler, telegram):
        self.engine = engine
        self.scheduler = scheduler
        self.telegram = telegram
        logger.info("✅ Orchestrator initialized")

    async def process_webhook(self, data: Dict[str, Any]) -> Dict:
        """
        Handle incoming webhook data.
        Supported types: 'scan', 'force_signal', 'status', 'reset'
        """
        event_type = data.get("type", "unknown")
        logger.info(f"📡 Orchestrator processing webhook: {event_type}")

        try:
            if event_type == "scan":
                symbol = data.get("symbol")
                if symbol:
                    await self.engine._force_fetch_all_pairs()
                    return {"status": "scan_triggered", "symbol": symbol}
                else:
                    await self.engine._force_fetch_all_pairs()
                    return {"status": "full_scan_triggered"}

            elif event_type == "force_signal":
                symbol = data.get("symbol", "BTC/USDT")
                direction = data.get("direction")
                logger.info(f"🔔 Force signal: {symbol} {direction}")
                return {"status": "force_signal_acknowledged", "symbol": symbol}

            elif event_type == "status":
                status = self.engine.get_status()
                return {"status": "ok", "engine": status}

            elif event_type == "reset_daily":
                self.engine.reset_daily()
                logger.info("🔄 Daily reset triggered via webhook")
                return {"status": "daily_reset_done"}

            elif event_type == "regime_update":
                await self.engine._update_regime()
                return {"status": "regime_updated"}

            else:
                logger.warning(f"Unknown webhook type: {event_type}")
                return {"status": "unknown_event", "type": event_type}

        except Exception as e:
            logger.error(f"❌ Webhook processing error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def handle_command(self, command: str, args: Dict = None) -> str:
        """Handle Telegram bot commands"""
        args = args or {}

        if command == "/status":
            s = self.engine.get_status()
            return (
                f"📊 Bot Status\n"
                f"BTC Ready: {s.get('btc_data_ready')}\n"
                f"Market: {s.get('market_type')}\n"
                f"Signals Today: {s.get('daily_signals')}\n"
                f"Consecutive Losses: {s.get('consecutive_losses', 0)}"
            )

        elif command == "/scan":
            await self.engine._force_fetch_all_pairs()
            return "🔍 Full scan triggered"

        elif command == "/reset":
            self.engine.reset_daily()
            return "🔄 Daily counters reset"

        else:
            return f"❓ Unknown command: {command}"
