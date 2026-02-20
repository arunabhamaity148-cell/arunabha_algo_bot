"""
ARUNABHA ALGO BOT - Notification Scheduler
Schedules periodic notifications
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
import pytz

import config

logger = logging.getLogger(__name__)


class NotificationScheduler:
    """
    Schedules periodic notifications
    """
    
    def __init__(self, notifier):
        self.notifier = notifier
        self.tasks: List[asyncio.Task] = []
        self.running = False
        self.timezone = pytz.timezone('Asia/Kolkata')
        
        # Scheduled notifications
        self.schedule = [
            {"time": "09:30", "callback": self._morning_update, "name": "morning_update"},
            {"time": "13:00", "callback": self._london_open, "name": "london_open"},
            {"time": "18:00", "callback": self._ny_open, "name": "ny_open"},
            {"time": "20:00", "callback": self._overlap_start, "name": "overlap_start"},
            {"time": "23:55", "callback": self._daily_summary, "name": "daily_summary"},
            {"time": "00:05", "callback": self._midnight_reset, "name": "midnight_reset"}
        ]
        
        # Weekly schedule
        self.weekly_schedule = [
            {"day": 4, "time": "20:00", "callback": self._weekly_summary, "name": "weekly_summary"}  # Friday
        ]
    
    async def start(self):
        """Start the scheduler"""
        self.running = True
        
        # Start daily scheduled tasks
        for item in self.schedule:
            self.tasks.append(asyncio.create_task(
                self._run_daily(item["time"], item["callback"], item["name"])
            ))
        
        # Start weekly scheduled tasks
        for item in self.weekly_schedule:
            self.tasks.append(asyncio.create_task(
                self._run_weekly(item["day"], item["time"], item["callback"], item["name"])
            ))
        
        logger.info(f"Notification scheduler started with {len(self.tasks)} tasks")
    
    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        
        for task in self.tasks:
            task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Notification scheduler stopped")
    
    async def _run_daily(self, time_str: str, callback: Callable, name: str):
        """Run a task daily at specified time"""
        while self.running:
            try:
                now = datetime.now(self.timezone)
                target = datetime.strptime(time_str, "%H:%M").time()
                target_dt = datetime.combine(now.date(), target)
                target_dt = self.timezone.localize(target_dt)
                
                # If target time passed, schedule for tomorrow
                if now > target_dt:
                    target_dt += timedelta(days=1)
                
                # Wait until target time
                wait_seconds = (target_dt - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # Execute callback
                logger.info(f"Running scheduled notification: {name}")
                await callback()
                
                # Wait a minute to avoid double execution
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in daily task {name}: {e}")
                await asyncio.sleep(60)
    
    async def _run_weekly(self, day: int, time_str: str, callback: Callable, name: str):
        """Run a task weekly on specified day and time"""
        while self.running:
            try:
                now = datetime.now(self.timezone)
                target_time = datetime.strptime(time_str, "%H:%M").time()
                
                # Calculate next occurrence
                days_ahead = day - now.weekday()
                if days_ahead < 0 or (days_ahead == 0 and now.time() > target_time):
                    days_ahead += 7
                
                target_dt = datetime.combine(now.date() + timedelta(days=days_ahead), target_time)
                target_dt = self.timezone.localize(target_dt)
                
                # Wait until target time
                wait_seconds = (target_dt - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # Execute callback
                logger.info(f"Running weekly notification: {name}")
                await callback()
                
                # Wait a day to avoid multiple executions
                await asyncio.sleep(86400)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in weekly task {name}: {e}")
                await asyncio.sleep(3600)
    
    async def _morning_update(self):
        """Send morning market update"""
        now = datetime.now(self.timezone)
        
        message = f"""
🌅 <b>Good Morning!</b>
📅 {now.strftime('%A, %d %B %Y')}

Today's trading sessions:
• Asia: 7:00-11:00 IST
• London: 13:30-17:30 IST
• NY: 18:00-22:00 IST
• Overlap: 22:00-00:30 IST

🎯 Daily target: ₹{config.DAILY_PROFIT_TARGET}
⚡ Risk per trade: {config.RISK_PER_TRADE}%

<i>Trade smart, protect capital!</i>
"""
        
        await self.notifier.send_message(message, parse_mode="HTML")
    
    async def _london_open(self):
        """Send London open notification"""
        message = """
🇬🇧 <b>London Session Open</b>

📈 High volatility expected
🎯 Best for trend trades
⚡ Tight stops recommended

<i>Watch for breakouts!</i>
"""
        
        await self.notifier.send_message(message, parse_mode="HTML")
    
    async def _ny_open(self):
        """Send NY open notification"""
        message = """
🗽 <b>NY Session Open</b>

🔥 Highest volatility of the day
🎯 Best for momentum trades
⚠️ Be careful with entries

<i>Let the market come to you!</i>
"""
        
        await self.notifier.send_message(message, parse_mode="HTML")
    
    async def _overlap_start(self):
        """Send overlap session notification"""
        message = """
🔄 <b>London + NY Overlap</b>

⚡ Maximum volatility
🎯 Best for breakout trades
💰 Highest profit potential

<i>This is the prime time!</i>
"""
        
        await self.notifier.send_message(message, parse_mode="HTML")
    
    async def _daily_summary(self):
        """Send daily summary"""
        # This would get stats from trade logger
        # Placeholder for now
        message = """
📊 <b>Daily Summary Placeholder</b>

Trades: 0
P&L: ₹0
Win Rate: 0%

<i>Check back tomorrow!</i>
"""
        
        await self.notifier.send_message(message, parse_mode="HTML")
    
    async def _midnight_reset(self):
        """Send midnight reset notification"""
        message = """
🌙 <b>Day Reset</b>

Daily counters reset
Ready for new trading day

<i>Good night, see you tomorrow!</i>
"""
        
        await self.notifier.send_message(message, parse_mode="HTML")
    
    async def _weekly_summary(self):
        """Send weekly summary"""
        message = """
📈 <b>Weekly Summary Placeholder</b>

Total Trades: 0
Win Rate: 0%
Total P&L: ₹0

<i>Have a great weekend!</i>
"""
        
        await self.notifier.send_message(message, parse_mode="HTML")
    
    async def send_test_notifications(self):
        """Send test notifications for all types"""
        await self.notifier.send_test()
        await asyncio.sleep(2)
        await self._morning_update()
        await asyncio.sleep(2)
        await self._london_open()
        await asyncio.sleep(2)
        await self._ny_open()
        await asyncio.sleep(2)
        await self._overlap_start()
