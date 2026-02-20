"""
ARUNABHA ALGO BOT - Alert System
Sends alerts for important events
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class AlertSystem:
    """
    Monitors conditions and sends alerts
    """
    
    def __init__(self, notifier):
        self.notifier = notifier
        self.alert_history = deque(maxlen=100)
        self.suppressed_alerts = {}
        self.alert_counts = {}
        
        # Alert thresholds
        self.thresholds = {
            "consecutive_losses": 2,
            "drawdown": config.MAX_DAILY_DRAWDOWN_PCT,
            "profit_target": config.DAILY_PROFIT_TARGET,
            "high_confidence": 80,
            "low_confidence": 40
        }
    
    async def check_and_alert(self, metrics: Dict[str, Any]):
        """Check metrics and send alerts if needed"""
        
        # Check consecutive losses
        consecutive = metrics.get("summary", {}).get("consecutive_losses", 0)
        if consecutive >= self.thresholds["consecutive_losses"]:
            await self._send_alert(
                "WARNING",
                f"{consecutive} consecutive losses",
                f"Cooling period activated. Take a break."
            )
        
        # Check drawdown
        drawdown = metrics.get("summary", {}).get("max_drawdown", 0)
        if drawdown >= self.thresholds["drawdown"]:
            await self._send_alert(
                "CRITICAL",
                f"Max drawdown reached: {drawdown:.1f}%",
                "Trading stopped for the day."
            )
        
        # Check profit target
        daily_pnl = metrics.get("today", {}).get("pnl", 0)
        if daily_pnl >= self.thresholds["profit_target"]:
            await self._send_alert(
                "SUCCESS",
                f"Daily target achieved! +{daily_pnl:.1f}%",
                "Great work! Consider stopping for the day."
            )
        
        # Check win rate
        win_rate = metrics.get("summary", {}).get("win_rate", 0)
        if win_rate < 40 and metrics.get("summary", {}).get("total_trades", 0) > 10:
            await self._send_alert(
                "WARNING",
                f"Low win rate: {win_rate:.1f}%",
                "Review your strategy or take a break."
            )
    
    async def _send_alert(self, level: str, title: str, message: str):
        """Send alert with rate limiting"""
        
        # Check if suppressed
        alert_key = f"{level}:{title}"
        if alert_key in self.suppressed_alerts:
            last_sent = self.suppressed_alerts[alert_key]
            if datetime.now() - last_sent < timedelta(hours=1):
                return
        
        # Update count
        self.alert_counts[alert_key] = self.alert_counts.get(alert_key, 0) + 1
        
        # Send alert
        alert_text = f"""
{self._get_emoji(level)} <b>{title}</b>

{message}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        
        await self.notifier.send_alert(alert_text, level)
        
        # Record in history
        self.alert_history.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "title": title,
            "message": message
        })
        
        # Suppress for an hour
        self.suppressed_alerts[alert_key] = datetime.now()
    
    def _get_emoji(self, level: str) -> str:
        """Get emoji for alert level"""
        emojis = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
            "SUCCESS": "✅",
            "ERROR": "❌"
        }
        return emojis.get(level, "📢")
    
    async def test_alerts(self):
        """Send test alerts"""
        await self._send_alert("INFO", "Test Alert", "This is a test info alert")
        await asyncio.sleep(2)
        await self._send_alert("WARNING", "Test Warning", "This is a test warning")
        await asyncio.sleep(2)
        await self._send_alert("SUCCESS", "Test Success", "This is a test success alert")
    
    def get_alert_history(self, hours: int = 24) -> List[Dict]:
        """Get recent alert history"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            a for a in self.alert_history
            if datetime.fromisoformat(a["timestamp"]) > cutoff
        ]
    
    def get_alert_stats(self) -> Dict:
        """Get alert statistics"""
        return {
            "total_alerts": len(self.alert_history),
            "by_level": {
                level: len([a for a in self.alert_history if a["level"] == level])
                for level in ["INFO", "WARNING", "CRITICAL", "SUCCESS", "ERROR"]
            },
            "most_frequent": sorted(
                self.alert_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }
