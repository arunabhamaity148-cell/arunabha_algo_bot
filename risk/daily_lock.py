"""
ARUNABHA ALGO BOT - Daily Lock
Locks trading after reaching daily limits
"""

import logging
from typing import Dict, Optional
from datetime import datetime, date

import config

logger = logging.getLogger(__name__)


class DailyLock:
    """
    Tracks daily profit/loss and locks trading when limits reached
    """
    
    def __init__(self):
        self.current_date = date.today()
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.is_locked = False
        self.lock_reason = None
        self.lock_time = None
        
        # Targets
        self.profit_target = config.DAILY_PROFIT_TARGET
        self.max_loss = abs(config.MAX_DAILY_DRAWDOWN_PCT)
        self.max_trades = config.MAX_SIGNALS_PER_DAY["default"]
    
    def update(self, pnl_pct: float):
        """
        Update daily stats after trade
        """
        self._check_date()
        
        # Update P&L
        self.daily_pnl += pnl_pct
        self.daily_trades += 1
        
        if pnl_pct > 0:
            self.daily_wins += 1
        else:
            self.daily_losses += 1
        
        # Check lock conditions
        self._check_lock_conditions()
    
    def _check_date(self):
        """Reset if new day"""
        today = date.today()
        if today > self.current_date:
            logger.info(f"Daily lock reset: {self.current_date} -> {today}")
            self.reset()
            self.current_date = today
    
    def _check_lock_conditions(self):
        """Check if trading should be locked"""
        
        # Profit target reached
        if self.daily_pnl >= self.profit_target:
            self.is_locked = True
            self.lock_reason = f"Profit target reached: ₹{self.daily_pnl:.2f}"
            self.lock_time = datetime.now()
            logger.info(f"Daily lock activated: {self.lock_reason}")
            return
        
        # Max loss reached
        if self.daily_pnl <= -self.max_loss:
            self.is_locked = True
            self.lock_reason = f"Max loss reached: {self.daily_pnl:.2f}%"
            self.lock_time = datetime.now()
            logger.warning(f"Daily lock activated: {self.lock_reason}")
            return
        
        # Max trades reached
        if self.daily_trades >= self.max_trades:
            self.is_locked = True
            self.lock_reason = f"Max trades reached: {self.daily_trades}"
            self.lock_time = datetime.now()
            logger.info(f"Daily lock activated: {self.lock_reason}")
            return
    
    def can_trade(self) -> bool:
        """Check if trading is allowed"""
        self._check_date()
        return not self.is_locked
    
    def reset(self):
        """Reset daily counters"""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.is_locked = False
        self.lock_reason = None
        self.lock_time = None
        
        # Update max trades based on config
        self.max_trades = config.MAX_SIGNALS_PER_DAY["default"]
        
        logger.info("Daily lock reset")
    
    def get_status(self) -> Dict:
        """Get daily lock status"""
        return {
            "date": self.current_date.isoformat(),
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_trades": self.daily_trades,
            "wins": self.daily_wins,
            "losses": self.daily_losses,
            "win_rate": round((self.daily_wins / self.daily_trades * 100), 2) if self.daily_trades > 0 else 0,
            "is_locked": self.is_locked,
            "lock_reason": self.lock_reason,
            "lock_time": self.lock_time.isoformat() if self.lock_time else None,
            "profit_target": self.profit_target,
            "max_loss": self.max_loss,
            "max_trades": self.max_trades
        }
    
    def get_summary(self) -> str:
        """Get human-readable summary"""
        status = self.get_status()
        
        lines = [
            f"📊 Daily Summary:",
            f"   P&L: {status['daily_pnl']:+.2f}%",
            f"   Trades: {status['daily_trades']} (W:{status['wins']} L:{status['losses']})",
            f"   Win Rate: {status['win_rate']}%"
        ]
        
        if status['is_locked']:
            lines.append(f"   🔒 LOCKED: {status['lock_reason']}")
        
        return "\n".join(lines)
