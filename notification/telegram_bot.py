"""
ARUNABHA ALGO BOT - Telegram Notifier
Sends signals and alerts via Telegram
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

import config
from notification.message_formatter import MessageFormatter
from notification.templates import MessageTemplates

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Handles all Telegram notifications
    """
    
    def __init__(self):
        self.bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.formatter = MessageFormatter()
        self.templates = MessageTemplates()
        
        # Rate limiting
        self.last_message_time = datetime.now()
        self.min_interval = 1.0  # 1 second between messages
        
        # Queue for messages
        self.message_queue = asyncio.Queue()
        self._worker_task = None
        
        logger.info(f"Telegram notifier initialized for chat_id: {self.chat_id}")
    
    async def start(self):
        """Start the notification worker"""
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Telegram notifier worker started")
    
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
        """Background worker to send messages"""
        logger.info("Telegram worker thread started")
        while True:
            try:
                # Get message from queue
                chat_id, text, parse_mode, kwargs = await self.message_queue.get()
                
                # Rate limiting
                now = datetime.now()
                elapsed = (now - self.last_message_time).total_seconds()
                if elapsed < self.min_interval:
                    await asyncio.sleep(self.min_interval - elapsed)
                
                # Send message
                logger.info(f"Sending message to {chat_id}: {text[:50]}...")
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    **kwargs
                )
                
                self.last_message_time = datetime.now()
                logger.info(f"✅ Telegram message sent: {text[:30]}...")
                
            except asyncio.CancelledError:
                logger.info("Telegram worker cancelled")
                break
            except TelegramError as e:
                logger.error(f"Telegram error: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in worker: {e}")
                await asyncio.sleep(5)
    
    async def send_message(
        self,
        text: str,
        parse_mode: str = ParseMode.HTML,
        **kwargs
    ):
        """Send message directly (bypass queue)"""
        logger.info(f"Sending direct message: {text[:50]}...")
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs
            )
            logger.info("✅ Direct message sent successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Direct message failed: {e}")
            return False
    
    async def send_message_queued(
        self,
        text: str,
        parse_mode: str = ParseMode.HTML,
        **kwargs
    ):
        """Queue a message to be sent by worker"""
        logger.info(f"Queueing message: {text[:50]}...")
        await self.message_queue.put((self.chat_id, text, parse_mode, kwargs))
    
    async def send_signal(self, signal: Dict, market_type: str):
        """Send trading signal"""
        text = self.formatter.format_signal(signal, market_type)
        await self.send_message(text, parse_mode=ParseMode.MARKDOWN)
        
        # Also send as separate alert if high confidence
        if signal.get("confidence", 0) >= 80:
            await self.send_message(f"🔥 HIGH CONFIDENCE SIGNAL: {signal['symbol']} {signal['direction']}")
    
    async def send_startup(self):
        """Send startup message"""
        try:
            logger.info("Preparing startup message...")
            text = self.templates.startup_message()
            logger.info(f"Startup message prepared, length: {len(text)} chars")
            
            logger.info(f"Sending startup message to chat_id: {self.chat_id}")
            
            # DIRECT SEND - bypass queue
            result = await self.send_message(text, parse_mode=ParseMode.MARKDOWN)
            
            if result:
                logger.info("✅ Startup message sent successfully to Telegram")
            else:
                logger.error("❌ Startup message failed")
            
            return result
        except Exception as e:
            logger.error(f"❌ Failed to send startup message: {e}")
            logger.exception(e)
            return False
    
    async def send_shutdown(self):
        """Send shutdown message"""
        text = self.templates.shutdown_message()
        await self.send_message(text)
    
    async def send_daily_summary(self, stats: Dict):
        """Send daily trading summary"""
        text = self.formatter.format_daily_summary(stats)
        await self.send_message(text, parse_mode=ParseMode.MARKDOWN)
    
    async def send_weekly_summary(self, stats: Dict):
        """Send weekly trading summary"""
        text = self.formatter.format_weekly_summary(stats)
        await self.send_message(text, parse_mode=ParseMode.MARKDOWN)
    
    async def send_alert(self, message: str, level: str = "INFO"):
        """Send alert message"""
        emoji = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🚨",
            "SUCCESS": "✅"
        }.get(level, "📢")
        
        text = f"{emoji} <b>{level}</b>\n{message}"
        await self.send_message(text, parse_mode=ParseMode.HTML)
    
    async def send_error(self, error: str, traceback: Optional[str] = None):
        """Send error notification"""
        text = f"🚨 <b>ERROR</b>\n{error}"
        if traceback:
            text += f"\n<pre>{traceback[:500]}</pre>"
        await self.send_message(text, parse_mode=ParseMode.HTML)
    
    async def send_health_status(self, status: Dict):
        """Send health status"""
        text = self.formatter.format_health_status(status)
        await self.send_message(text, parse_mode=ParseMode.MARKDOWN)
    
    async def send_test(self):
        """Send test message"""
        await self.send_message("🧪 Test message from ARUNABHA bot")
    
    def get_status(self) -> Dict:
        """Get notifier status"""
        return {
            "queue_size": self.message_queue.qsize(),
            "worker_running": self._worker_task is not None and not self._worker_task.done(),
            "last_message": self.last_message_time.isoformat(),
            "chat_id": str(self.chat_id)[:3] + "..."
        }
