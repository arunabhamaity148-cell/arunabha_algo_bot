"""
ARUNABHA ALGO BOT - Telegram Notifier v4.1

FIXES:
- BUG-25: Token missing এ bot crash করত
  আগে: __init__ এ Bot(token=...) সরাসরি call → token না থাকলে crash
  এখন:
    1. __init__ এ token validate করা হয় — invalid হলে warning, crash নয়
    2. Bot object lazy initialize করা হয় (প্রথম use এ তৈরি হয়)
    3. সব send method এ try-except আছে — Telegram fail হলে bot চলতে থাকে
    4. _get_bot() method দিয়ে safe access
"""

import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime

import config
from notification.message_formatter import MessageFormatter
from notification.templates import MessageTemplates

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Handles all Telegram notifications — gracefully handles missing token
    """

    def __init__(self):
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.formatter = MessageFormatter()
        self.templates = MessageTemplates()

        # Rate limiting
        self.last_message_time = datetime.now()
        self.min_interval = 1.0

        # Message queue
        self.message_queue = asyncio.Queue()
        self._worker_task = None

        # ✅ FIX BUG-25: Lazy initialization — __init__ এ crash না করে
        # Bot object পরে তৈরি হবে, এখন শুধু token validate করো
        self._bot = None
        self._bot_ready = False
        self._token = config.TELEGRAM_BOT_TOKEN

        if not self._token:
            logger.error(
                "❌ TELEGRAM_BOT_TOKEN is empty!\n"
                "   Bot will run but NO notifications will be sent.\n"
                "   Set TELEGRAM_BOT_TOKEN in .env to fix this."
            )
        elif not self.chat_id:
            logger.error(
                "❌ TELEGRAM_CHAT_ID is empty!\n"
                "   Bot will run but NO notifications will be sent.\n"
                "   Set TELEGRAM_CHAT_ID in .env to fix this."
            )
        else:
            logger.info(f"📱 Telegram configured for chat_id: {str(self.chat_id)[:5]}...")

    def _get_bot(self):
        """
        ✅ FIX BUG-25: Lazy bot initialization
        প্রথমবার call হলে Bot object তৈরি করে, না পারলে None return করে
        """
        if self._bot is not None:
            return self._bot

        if not self._token:
            return None

        try:
            from telegram import Bot
            self._bot = Bot(token=self._token)
            self._bot_ready = True
            logger.info("✅ Telegram Bot object created successfully")
            return self._bot
        except Exception as e:
            logger.error(f"❌ Failed to create Telegram Bot: {e}")
            self._bot_ready = False
            return None

    async def start(self):
        """Start the notification worker"""
        # ✅ Lazy init — bot তৈরি করার চেষ্টা করো
        bot = self._get_bot()
        if bot:
            logger.info("✅ Telegram Bot ready")
        else:
            logger.warning("⚠️ Telegram Bot not available — notifications disabled")

        self._worker_task = asyncio.create_task(self._worker())
        logger.info("📮 Telegram notification worker started")

    async def stop(self):
        """Stop the notification worker"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram notifier stopped")

    async def _worker(self):
        """Background worker to send queued messages"""
        while True:
            try:
                chat_id, text, parse_mode, kwargs = await self.message_queue.get()

                # Rate limiting
                elapsed = (datetime.now() - self.last_message_time).total_seconds()
                if elapsed < self.min_interval:
                    await asyncio.sleep(self.min_interval - elapsed)

                await self._send_raw(chat_id, text, parse_mode, **kwargs)
                self.message_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram worker error: {e}")
                await asyncio.sleep(5)

    async def _send_raw(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        **kwargs
    ) -> bool:
        """
        ✅ FIX BUG-25: Low-level send — bot না থাকলে gracefully fail করে
        """
        bot = self._get_bot()
        if not bot:
            logger.warning(f"⚠️ Telegram not available, message skipped: {text[:50]}...")
            return False

        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs
            )
            self.last_message_time = datetime.now()
            return True
        except Exception as e:
            logger.error(f"❌ Telegram send error: {e}")
            return False

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        **kwargs
    ) -> bool:
        """Send a message directly (bypass queue)"""
        if not self.chat_id:
            logger.warning("⚠️ No chat_id set — cannot send message")
            return False

        logger.debug(f"📤 Sending: {text[:60]}...")
        result = await self._send_raw(self.chat_id, text, parse_mode, **kwargs)
        if result:
            logger.info(f"✅ Message sent: {text[:40]}...")
        return result

    async def send_message_queued(
        self,
        text: str,
        parse_mode: str = "HTML",
        **kwargs
    ):
        """Queue a message to be sent by background worker"""
        await self.message_queue.put((self.chat_id, text, parse_mode, kwargs))

    async def send_signal(self, signal: Dict, market_type) -> bool:
        """Send trading signal to Telegram"""
        try:
            market_str = market_type.value if hasattr(market_type, 'value') else str(market_type)
            text = self.formatter.format_signal(signal, market_str)
            result = await self.send_message(text, parse_mode="Markdown")

            # Extra alert for high confidence signals
            if signal.get("confidence", 0) >= 80:
                grade = signal.get("grade", "")
                await self.send_message(
                    f"🔥 <b>HIGH CONFIDENCE</b>: {signal['symbol']} "
                    f"{signal['direction']} | Grade: {grade}"
                )
            return result
        except Exception as e:
            logger.error(f"❌ send_signal error: {e}")
            return False

    async def send_startup(self) -> bool:
        """Send startup notification"""
        try:
            text = self.templates.startup_message()
            result = await self.send_message(text, parse_mode="Markdown")
            if result:
                logger.info("✅ Startup message sent to Telegram")
            else:
                logger.warning("⚠️ Startup message could not be sent (Telegram unavailable)")
            return result
        except Exception as e:
            logger.error(f"❌ send_startup error: {e}")
            return False

    async def send_shutdown(self) -> bool:
        """Send shutdown notification"""
        try:
            text = self.templates.shutdown_message()
            return await self.send_message(text)
        except Exception as e:
            logger.error(f"❌ send_shutdown error: {e}")
            return False

    async def send_daily_summary(self, stats: Dict) -> bool:
        """Send daily trading summary"""
        try:
            text = self.formatter.format_daily_summary(stats)
            return await self.send_message(text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ send_daily_summary error: {e}")
            return False

    async def send_alert(self, message: str, level: str = "INFO") -> bool:
        """Send an alert message"""
        emoji = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "🚨", "SUCCESS": "✅"}.get(level, "📢")
        text = f"{emoji} <b>{level}</b>\n{message}"
        try:
            return await self.send_message(text)
        except Exception as e:
            logger.error(f"❌ send_alert error: {e}")
            return False

    async def send_error(self, error: str, traceback_str: Optional[str] = None) -> bool:
        """Send error notification"""
        text = f"🚨 <b>ERROR</b>\n{error}"
        if traceback_str:
            # Truncate to avoid Telegram message limit
            text += f"\n<pre>{traceback_str[:800]}</pre>"
        try:
            return await self.send_message(text)
        except Exception as e:
            logger.error(f"❌ send_error failed: {e}")
            return False

    async def send_health_status(self, status: Dict) -> bool:
        """Send health status"""
        try:
            text = self.formatter.format_health_status(status)
            return await self.send_message(text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"❌ send_health_status error: {e}")
            return False

    async def send_test(self) -> bool:
        """Send a test message to verify Telegram is working"""
        return await self.send_message(
            "🧪 <b>ARUNABHA ALGO BOT</b>\nTest message — Telegram is working!"
        )

    def is_available(self) -> bool:
        """Check if Telegram notifications are available"""
        return bool(self._token and self.chat_id)

    def get_status(self) -> Dict:
        """Get notifier status"""
        return {
            "available": self.is_available(),
            "bot_ready": self._bot_ready,
            "queue_size": self.message_queue.qsize(),
            "worker_running": (
                self._worker_task is not None
                and not self._worker_task.done()
            ),
            "last_message": self.last_message_time.isoformat(),
            "chat_id_set": bool(self.chat_id),
            "token_set": bool(self._token)
        }
