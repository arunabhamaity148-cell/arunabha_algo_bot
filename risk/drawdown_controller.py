"""
ARUNABHA ALGO BOT - Drawdown Controller
Monitors and controls drawdown levels
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
        self.peak = 0.0
        self.current_drawdown = 0.0
        self.max_drawdown_reached = False
        self.daily_drawdown = 0.0
        self.daily_start_balance = 0.0
        self.current_balance = 0.0
        self.last_update = datetime.now()
    
    def update(self, pnl_pct: float):
        """
        Update drawdown after trade
        """
        # Update current balance
        self.current_balance += pnl_pct
        
        # Update peak
        if self.current_balance > self.peak:
            self.peak = self.current_balance
        
        # Calculate current drawdown
        if self.peak > 0:
            self.current_drawdown = ((self.peak - self.current_balance) / self.peak) * 100
        else:
            self.current_drawdown = 0
        
        # Check if max drawdown reached
        if self.current_drawdown >= abs(config.MAX_DAILY_DRAWDOWN_PCT):
            self.max_drawdown_reached = True
            logger.warning(f"Max drawdown reached: {self.current_drawdown:.2f}%")
        
        # Update daily drawdown
        if self.daily_start_balance > 0:
            self.daily_drawdown = ((self.daily_start_balance - self.current_balance) / self.daily_start_balance) * 100
        
        self.last_update = datetime.now()
    
    def is_max_drawdown_reached(self) -> bool:
        """Check if max drawdown reached"""
        return self.max_drawdown_reached
    
    def reset_daily(self, starting_balance: float):
        """
        Reset daily drawdown tracking
        """
        self.daily_start_balance = starting_balance
        self.daily_drawdown = 0.0
        logger.info(f"Daily drawdown reset. Starting balance: {starting_balance:.2f}%")
    
    def reset_all(self):
        """
        Reset all drawdown tracking
        """
        self.peak = 0.0
        self.current_drawdown = 0.0
        self.max_drawdown_reached = False
        self.daily_drawdown = 0.0
        self.current_balance = 0.0
        logger.info("All drawdown tracking reset")
    
    def get_status(self) -> Dict:
        """Get drawdown status"""
        return {
            "current_drawdown": round(self.current_drawdown, 2),
            "daily_drawdown": round(self.daily_drawdown, 2),
            "max_drawdown_reached": self.max_drawdown_reached,
            "peak": round(self.peak, 2),
            "current_balance": round(self.current_balance, 2),
            "max_allowed": abs(config.MAX_DAILY_DRAWDOWN_PCT)
        }
    
    def get_drawdown_level(self) -> str:
        """Get drawdown severity level"""
        if self.current_drawdown >= abs(config.MAX_DAILY_DRAWDOWN_PCT):
            return "CRITICAL"
        elif self.current_drawdown >= abs(config.MAX_DAILY_DRAWDOWN_PCT) * 0.7:
            return "HIGH"
        elif self.current_drawdown >= abs(config.MAX_DAILY_DRAWDOWN_PCT) * 0.4:
            return "MODERATE"
        elif self.current_drawdown > 0:
            return "LOW"
        else:
            return "NONE"
    
    def should_reduce_size(self) -> bool:
        """Check if position size should be reduced"""
        level = self.get_drawdown_level()
        
        if level == "HIGH":
            return True
        elif level == "MODERATE":
            return True
        else:
            return False
    
    def get_size_multiplier(self) -> float:
        """Get position size multiplier based on drawdown"""
        level = self.get_drawdown_level()
        
        multipliers = {
            "CRITICAL": 0.0,  # No trading
            "HIGH": 0.3,       # 30% size
            "MODERATE": 0.6,   # 60% size
            "LOW": 0.8,        # 80% size
            "NONE": 1.0        # Full size
        }
        
        return multipliers.get(level, 1.0)
