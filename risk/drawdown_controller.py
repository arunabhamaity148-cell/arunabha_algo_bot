"""
ARUNABHA ALGO BOT - Drawdown Controller v4.1

FIXES:
- BUG-27: current_balance unit mismatch fixed
  আগে: current_balance = 0.0, তারপর += pnl_pct (%) — এটা meaningless ছিল
  এখন: current_balance শুরু হয় account_size (₹) থেকে
        pnl_pct → ₹ amount এ convert করে add করা হচ্ছে
"""

import logging
from typing import Dict, Optional
from datetime import datetime, date

import config

logger = logging.getLogger(__name__)


class DrawdownController:
    """
    Tracks drawdown and stops trading at max drawdown
    """

    def __init__(self):
        # ✅ FIX: account_size দিয়ে initialize করো
        account_size = config.ACCOUNT_SIZE
        self.peak = account_size
        self.current_balance = account_size
        self.current_drawdown = 0.0
        self.max_drawdown_reached = False
        self.daily_drawdown = 0.0
        self.daily_start_balance = account_size
        self.last_update = datetime.now()

    def update(self, pnl_pct: float):
        """
        Update drawdown after trade
        pnl_pct: % gain/loss (e.g. +1.5 or -0.8)
        """
        # ✅ FIX: % → ₹ convert করে balance update করো
        pnl_inr = self.current_balance * (pnl_pct / 100)
        self.current_balance += pnl_inr

        # Update peak
        if self.current_balance > self.peak:
            self.peak = self.current_balance

        # Current drawdown %
        if self.peak > 0:
            self.current_drawdown = ((self.peak - self.current_balance) / self.peak) * 100
        else:
            self.current_drawdown = 0

        # Check if max drawdown reached
        if self.current_drawdown >= abs(config.MAX_DAILY_DRAWDOWN_PCT):
            self.max_drawdown_reached = True
            logger.warning(f"🚨 Max drawdown reached: {self.current_drawdown:.2f}%")

        # Daily drawdown
        if self.daily_start_balance > 0:
            self.daily_drawdown = (
                (self.daily_start_balance - self.current_balance) / self.daily_start_balance
            ) * 100

        self.last_update = datetime.now()

    def is_max_drawdown_reached(self) -> bool:
        return self.max_drawdown_reached

    def reset_daily(self, starting_balance: Optional[float] = None):
        """Reset daily drawdown tracking"""
        self.daily_start_balance = starting_balance or self.current_balance
        self.daily_drawdown = 0.0
        logger.info(f"📅 Daily drawdown reset. Starting balance: ₹{self.daily_start_balance:,.0f}")

    def reset_all(self):
        """Reset all drawdown tracking"""
        account_size = config.ACCOUNT_SIZE
        self.peak = account_size
        self.current_balance = account_size
        self.current_drawdown = 0.0
        self.max_drawdown_reached = False
        self.daily_drawdown = 0.0
        self.daily_start_balance = account_size
        logger.info("🔄 All drawdown tracking reset")

    def get_status(self) -> Dict:
        return {
            "current_drawdown_pct": round(self.current_drawdown, 2),
            "daily_drawdown_pct": round(self.daily_drawdown, 2),
            "max_drawdown_reached": self.max_drawdown_reached,
            "peak_inr": round(self.peak, 0),
            "current_balance_inr": round(self.current_balance, 0),
            "loss_inr": round(self.peak - self.current_balance, 0),
            "max_allowed_pct": abs(config.MAX_DAILY_DRAWDOWN_PCT)
        }

    def get_drawdown_level(self) -> str:
        max_dd = abs(config.MAX_DAILY_DRAWDOWN_PCT)
        if self.current_drawdown >= max_dd:
            return "CRITICAL"
        elif self.current_drawdown >= max_dd * 0.7:
            return "HIGH"
        elif self.current_drawdown >= max_dd * 0.4:
            return "MODERATE"
        elif self.current_drawdown > 0:
            return "LOW"
        else:
            return "NONE"

    def should_reduce_size(self) -> bool:
        level = self.get_drawdown_level()
        return level in ["HIGH", "MODERATE"]

    def get_size_multiplier(self) -> float:
        level = self.get_drawdown_level()
        return {
            "CRITICAL": 0.0,
            "HIGH": 0.3,
            "MODERATE": 0.6,
            "LOW": 0.8,
            "NONE": 1.0
        }.get(level, 1.0)
