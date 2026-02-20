"""
ARUNABHA ALGO BOT - Trading Scheduler
Manages timing and session-based operations
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, time, timedelta  # 🔴 'timedelta' যোগ করুন
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
    
    # ... rest of the code remains the same ...
