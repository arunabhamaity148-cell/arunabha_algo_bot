"""
ARUNABHA ALGO BOT - Daily Lock v4.1

FIXES:
- BUG-28: ₹ vs % unit mismatch fixed
  আগে: daily_pnl (%) >= profit_target (₹500) — এটা কখনো trigger হতো না
  এখন: সব কিছু ₹ amount এ track হচ্ছে
  পাশাপাশি % track ও আলাদা রাখা হয়েছে
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

        # ✅ FIX: আলাদাভাবে ₹ এবং % track করা হচ্ছে
        self.daily_pnl_pct = 0.0        # % পরিবর্তন
        self.daily_pnl_inr = 0.0        # ₹ amount (account_size * pnl_pct / 100)

        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.is_locked = False
        self.lock_reason = None
        self.lock_time = None

        # Targets — consistent units
        self.profit_target_inr = config.DAILY_PROFIT_TARGET      # ₹500
        self.max_loss_pct = abs(config.MAX_DAILY_DRAWDOWN_PCT)   # 2%
        self.max_loss_inr = config.ACCOUNT_SIZE * (self.max_loss_pct / 100)  # ₹2000
        self.max_trades = config.MAX_SIGNALS_PER_DAY["default"]

    def update(self, pnl_pct: float):
        """
        Update daily stats after trade
        pnl_pct: % gain/loss (e.g. +1.5 or -0.8)
        """
        self._check_date()

        # ₹ amount calculate করো
        pnl_inr = config.ACCOUNT_SIZE * (pnl_pct / 100)

        self.daily_pnl_pct += pnl_pct
        self.daily_pnl_inr += pnl_inr
        self.daily_trades += 1

        if pnl_pct > 0:
            self.daily_wins += 1
        else:
            self.daily_losses += 1

        self._check_lock_conditions()

    def _check_date(self):
        """Reset if new day"""
        today = date.today()
        if today > self.current_date:
            logger.info(f"Daily lock reset: {self.current_date} → {today}")
            self.reset()
            self.current_date = today

    def _check_lock_conditions(self):
        """
        ✅ FIX BUG-28: এখন ₹ profit target এবং % loss limit — আলাদা unit এ compare
        """
        # ₹ Profit target reached
        if self.daily_pnl_inr >= self.profit_target_inr:
            self.is_locked = True
            self.lock_reason = f"Profit target reached: ₹{self.daily_pnl_inr:.0f} (target: ₹{self.profit_target_inr})"
            self.lock_time = datetime.now()
            logger.info(f"🔒 Daily lock: {self.lock_reason}")
            return

        # % Loss limit reached
        if self.daily_pnl_pct <= -self.max_loss_pct:
            self.is_locked = True
            self.lock_reason = (
                f"Max loss reached: {self.daily_pnl_pct:.2f}% "
                f"(₹{abs(self.daily_pnl_inr):.0f} loss, limit: {self.max_loss_pct}%)"
            )
            self.lock_time = datetime.now()
            logger.warning(f"🔒 Daily lock: {self.lock_reason}")
            return

        # Max trades reached
        if self.daily_trades >= self.max_trades:
            self.is_locked = True
            self.lock_reason = f"Max trades reached: {self.daily_trades}"
            self.lock_time = datetime.now()
            logger.info(f"🔒 Daily lock: {self.lock_reason}")
            return

    def can_trade(self) -> bool:
        self._check_date()
        return not self.is_locked

    def reset(self):
        self.daily_pnl_pct = 0.0
        self.daily_pnl_inr = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.is_locked = False
        self.lock_reason = None
        self.lock_time = None
        self.max_trades = config.MAX_SIGNALS_PER_DAY["default"]
        # Recalculate INR limits based on current account size
        self.max_loss_inr = config.ACCOUNT_SIZE * (self.max_loss_pct / 100)
        logger.info("📅 Daily lock reset")

    def get_status(self) -> Dict:
        return {
            "date": self.current_date.isoformat(),
            "daily_pnl_pct": round(self.daily_pnl_pct, 2),
            "daily_pnl_inr": round(self.daily_pnl_inr, 0),
            "daily_trades": self.daily_trades,
            "wins": self.daily_wins,
            "losses": self.daily_losses,
            "win_rate": round((self.daily_wins / self.daily_trades * 100), 2) if self.daily_trades > 0 else 0,
            "is_locked": self.is_locked,
            "lock_reason": self.lock_reason,
            "lock_time": self.lock_time.isoformat() if self.lock_time else None,
            "profit_target_inr": self.profit_target_inr,
            "max_loss_pct": self.max_loss_pct,
            "max_loss_inr": self.max_loss_inr,
            "max_trades": self.max_trades
        }

    def get_summary(self) -> str:
        status = self.get_status()
        lines = [
            "📊 Daily Summary:",
            f"   P&L: {status['daily_pnl_pct']:+.2f}% (₹{status['daily_pnl_inr']:+.0f})",
            f"   Trades: {status['daily_trades']} (W:{status['wins']} L:{status['losses']})",
            f"   Win Rate: {status['win_rate']}%"
        ]
        if status['is_locked']:
            lines.append(f"   🔒 LOCKED: {status['lock_reason']}")
        return "\n".join(lines)
