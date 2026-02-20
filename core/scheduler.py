"""
ARUNABHA ALGO BOT - Trading Scheduler
Manages timing and session-based operations
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, time
import pytz

import config
from core.constants import SessionType

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Scheduler for trading operations based on time and sessions
    """
    
    def __init__(self, engine):
        self.engine = engine
        self.tasks: List[asyncio.Task] = []
        self.running = False
        self.timezone = pytz.timezone('Asia/Kolkata')
        
        # Session callbacks
        self.session_callbacks: Dict[SessionType, List[Callable]] = {
            session: [] for session in SessionType
        }
        
        # Scheduled tasks
        self.scheduled_tasks = [
            {"time": "00:00", "callback": self._daily_reset, "name": "daily_reset"},
            {"time": "01:00", "callback": self._update_regime, "name": "regime_update"},
            {"time": "07:00", "callback": self._session_start, "name": "asia_start", "session": SessionType.ASIA},
            {"time": "13:00", "callback": self._session_start, "name": "london_start", "session": SessionType.LONDON},
            {"time": "18:00", "callback": self._session_start, "name": "ny_start", "session": SessionType.NY},
            {"time": "22:00", "callback": self._session_start, "name": "overlap_start", "session": SessionType.OVERLAP}
        ]
    
    async def start(self):
        """Start the scheduler"""
        self.running = True
        logger.info("Scheduler started")
        
        # Start main loop
        self.tasks.append(asyncio.create_task(self._main_loop()))
        
        # Start scheduled tasks
        for task_config in self.scheduled_tasks:
            self.tasks.append(asyncio.create_task(
                self._run_scheduled(task_config)
            ))
    
    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        
        for task in self.tasks:
            task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Scheduler stopped")
    
    async def _main_loop(self):
        """Main scheduler loop - runs every minute"""
        while self.running:
            try:
                now = datetime.now(self.timezone)
                
                # Check sessions
                current_session = self._get_current_session()
                
                # Log every hour
                if now.minute == 0:
                    logger.info(f"Scheduler: {now.strftime('%H:%M')} | Session: {current_session}")
                
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def _run_scheduled(self, task_config: Dict):
        """Run a scheduled task at specific time"""
        target_time = datetime.strptime(task_config["time"], "%H:%M").time()
        
        while self.running:
            try:
                now = datetime.now(self.timezone)
                target = datetime.combine(now.date(), target_time)
                target = self.timezone.localize(target)
                
                # If target time passed, schedule for tomorrow
                if now > target:
                    target = target + timedelta(days=1)
                
                # Wait until target time
                wait_seconds = (target - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # Execute callback
                logger.info(f"Executing scheduled task: {task_config['name']}")
                
                if "session" in task_config:
                    await task_config["callback"](task_config["session"])
                else:
                    await task_config["callback"]()
                
                # Wait a minute to avoid double execution
                await asynleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduled task {task_config['name']} error: {e}")
                await asyncio.sleep(60)
    
    def _get_current_session(self) -> Optional[SessionType]:
        """Get current trading session"""
        hour = datetime.now(self.timezone).hour
        
        for session in SessionType:
            start, end = session.hours
            if start <= hour < end:
                return session
        
        return None
    
    async def _daily_reset(self):
        """Reset daily counters"""
        logger.info("Daily reset triggered")
        self.engine.reset_daily()
    
    async def _update_regime(self):
        """Update market regime"""
        logger.info("Regime update triggered")
        await self.engine._update_regime()
    
    async def _session_start(self, session: SessionType):
        """Handle session start"""
        logger.info(f"Session started: {session.value}")
        
        # Notify via Telegram
        if self.engine.telegram:
            await self.engine.telegram.send_message(
                f"🕐 {session.value.upper()} session started\n"
                f"🎯 Best time for trading: {session.hours[0]}:00-{session.hours[1]}:00 IST"
            )
        
        # Execute session callbacks
        for callback in self.session_callbacks.get(session, []):
            try:
                await callback(session)
            except Exception as e:
                logger.error(f"Session callback error: {e}")
    
    def register_session_callback(self, session: SessionType, callback: Callable):
        """Register callback for session start"""
        self.session_callbacks[session].append(callback)
        logger.debug(f"Callback registered for {session.value}")
    
    def is_trading_time(self) -> bool:
        """Check if current time is suitable for trading"""
        session = self._get_current_session()
        
        if not session:
            return False
        
        # Avoid dead zone
        if session == SessionType.DEAD:
            return False
        
        # Check if in avoid times
        hour = datetime.now(self.timezone).hour
        for start, end, _ in config.AVOID_TIMES:
            if start <= hour < end:
                return False
        
        return True
    
    def get_session_info(self) -> Dict:
        """Get current session information"""
        session = self._get_current_session()
        hour = datetime.now(self.timezone).hour
        
        return {
            "current_session": session.value if session else None,
            "hour": hour,
            "is_trading_time": self.is_trading_time(),
            "next_session": self._get_next_session(),
            "time_ist": datetime.now(self.timezone).strftime("%H:%M")
        }
    
    def _get_next_session(self) -> Optional[Dict]:
        """Get next trading session"""
        current_hour = datetime.now(self.timezone).hour
        
        sessions = []
        for session in SessionType:
            start, end = session.hours
            sessions.append({
                "name": session.value,
                "start": start,
                "end": end
            })
        
        # Find next session
        sessions.sort(key=lambda x: x["start"])
        
        for session in sessions:
            if session["start"] > current_hour:
                return {
                    "name": session["name"],
                    "start": f"{session['start']}:00",
                    "end": f"{session['end']}:00",
                    "in": session["start"] - current_hour
                }
        
        # If no session today, return first session tomorrow
        tomorrow = sessions[0]
        return {
            "name": tomorrow["name"],
            "start": f"{tomorrow['start']}:00",
            "end": f"{tomorrow['end']}:00",
            "in": (24 - current_hour) + tomorrow["start"]
        }
