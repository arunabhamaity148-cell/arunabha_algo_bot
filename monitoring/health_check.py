"""
ARUNABHA ALGO BOT - Health Check
Monitors bot health and component status
"""

import logging
import psutil
import platform
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)


class HealthChecker:
    """
    Checks health of all bot components
    """
    
    def __init__(self, engine, scheduler):
        self.engine = engine
        self.scheduler = scheduler
        self.start_time = datetime.now()
        self.last_check = datetime.now()
        self.consecutive_failures = 0
        self.status_history = []
        
    async def check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check
        """
        self.last_check = datetime.now()
        
        health = {
            "status": "healthy",
            "timestamp": self.last_check.isoformat(),
            "uptime": str(datetime.now() - self.start_time).split('.')[0],
            "components": {},
            "system": self._get_system_info(),
            "warnings": [],
            "errors": []
        }
        
        # Check engine
        try:
            engine_status = self.engine.get_status()
            health["components"]["engine"] = "ok"
            health["market"] = engine_status
        except Exception as e:
            health["components"]["engine"] = "error"
            health["errors"].append(f"Engine error: {e}")
            self.consecutive_failures += 1
        
        # Check scheduler
        try:
            scheduler_info = self.scheduler.get_session_info()
            health["components"]["scheduler"] = "ok"
            health["session"] = scheduler_info
        except Exception as e:
            health["components"]["scheduler"] = "error"
            health["errors"].append(f"Scheduler error: {e}")
            self.consecutive_failures += 1
        
        # Check WebSocket if available
        if hasattr(self.engine, 'ws_manager'):
            try:
                ws_status = self.engine.ws_manager.get_status()
                health["components"]["websocket"] = "ok" if ws_status.get("connected") else "warning"
                if not ws_status.get("connected"):
                    health["warnings"].append("WebSocket disconnected")
            except Exception as e:
                health["components"]["websocket"] = "error"
                health["errors"].append(f"WebSocket error: {e}")
        
        # Check cache
        if hasattr(self.engine, 'cache'):
            try:
                cache_size = self.engine.cache.size()
                health["components"]["cache"] = "ok"
                health["cache"] = cache_size
            except Exception as e:
                health["components"]["cache"] = "warning"
                health["warnings"].append(f"Cache issue: {e}")
        
        # Check memory
        memory = self._check_memory()
        health["memory"] = memory
        if memory["percent"] > 80:
            health["warnings"].append(f"High memory usage: {memory['percent']}%")
        
        # Determine overall status
        if len(health["errors"]) > 0:
            health["status"] = "degraded"
        if self.consecutive_failures > 5:
            health["status"] = "critical"
        
        # Store in history
        self.status_history.append({
            "timestamp": self.last_check,
            "status": health["status"],
            "errors": len(health["errors"]),
            "warnings": len(health["warnings"])
        })
        
        # Keep history manageable
        if len(self.status_history) > 100:
            self.status_history = self.status_history[-100:]
        
        return health
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        return {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": psutil.cpu_count(),
            "memory_total": round(psutil.virtual_memory().total / (1024**3), 2),  # GB
            "process_id": psutil.Process().pid
        }
    
    def _check_memory(self) -> Dict[str, Any]:
        """Check memory usage"""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            "rss_mb": round(memory_info.rss / (1024**2), 2),
            "vms_mb": round(memory_info.vms / (1024**2), 2),
            "percent": process.memory_percent(),
            "cpu_percent": process.cpu_percent(interval=0.1)
        }
    
    def is_healthy(self) -> bool:
        """Quick health check"""
        try:
            # Check if engine is responding
            self.engine.get_status()
            return True
        except:
            return False
    
    def get_uptime(self) -> str:
        """Get bot uptime"""
        return str(datetime.now() - self.start_time).split('.')[0]
    
    def get_health_summary(self) -> str:
        """Get human-readable health summary"""
        health = asyncio.run(self.check())
        
        lines = [
            f"🤖 Bot Health: {health['status'].upper()}",
            f"⏱️ Uptime: {health['uptime']}",
            f"📊 Components:"
        ]
        
        for comp, status in health['components'].items():
            emoji = "✅" if status == "ok" else "⚠️" if status == "warning" else "❌"
            lines.append(f"  {emoji} {comp}")
        
        if health['warnings']:
            lines.append(f"\n⚠️ Warnings ({len(health['warnings'])}):")
            for w in health['warnings'][:3]:
                lines.append(f"  • {w}")
        
        if health['errors']:
            lines.append(f"\n❌ Errors ({len(health['errors'])}):")
            for e in health['errors'][:3]:
                lines.append(f"  • {e}")
        
        lines.append(f"\n💾 Memory: {health['memory']['rss_mb']}MB ({health['memory']['percent']:.1f}%)")
        
        return "\n".join(lines)
    
    def get_health_history(self, hours: int = 24) -> list:
        """Get health history for last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [h for h in self.status_history if h["timestamp"] > cutoff]
