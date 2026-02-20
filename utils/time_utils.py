"""
ARUNABHA ALGO BOT - Time Utilities
IST timezone, sleep detection, formatting
"""

from datetime import datetime, timedelta, timezone
from typing import Optional


# Timezones
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc


def utcnow() -> datetime:
    """Current UTC time"""
    return datetime.now(UTC)


def ist_now() -> datetime:
    """Current IST time"""
    return datetime.now(IST)


def is_sleep_time() -> bool:
    """
    Check if sleep hours (IST 1 AM - 7 AM)
    No trading during this time
    """
    now = ist_now()
    return 1 <= now.hour < 7


def today_ist_str() -> str:
    """Today date in IST (YYYY-MM-DD)"""
    return ist_now().strftime("%Y-%m-%d")


def ts_label() -> str:
    """Human readable timestamp for Telegram"""
    return ist_now().strftime("%d %b %Y, %H:%M IST")


def format_duration(minutes: int) -> str:
    """Format minutes to readable string"""
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


def get_session_name() -> Optional[str]:
    """
    Get current trading session name
    Returns: asia, london, ny, or None
    """
    hour = ist_now().hour
    
    if 6 <= hour < 12:
        return "asia"
    elif 13 <= hour < 17:
        return "london"
    elif 17 <= hour < 22:
        return "ny"
    
    return None


def is_major_session() -> bool:
    """Check if London or NY is active"""
    session = get_session_name()
    return session in ["london", "ny"]


def next_session_start() -> Optional[str]:
    """Get next major session start time"""
    hour = ist_now().hour
    
    if hour < 13:
        return "13:30 IST (London)"
    elif hour < 17:
        return "18:00 IST (NY)"
    
    return "Tomorrow 13:30 IST"
