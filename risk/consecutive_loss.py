"""
ARUNABHA ALGO BOT - Consecutive Loss Tracker
Tracks consecutive losses and enforces cooling periods
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

import config

logger = logging.getLogger(__name__)


class ConsecutiveLossTracker:
    """
    Tracks consecutive losses and implements cooling periods
    """
    
    def __init__(self):
        self.consecutive_losses = 0
        self.max_consecutive = config.MAX_CONSECUTIVE_LOSSES
        self.last_loss_time = None
        self.cooling_until = None
        self.cooling_minutes = config.COOLDOWN_MINUTES
        self.loss_streak_start = None
        
        # History
        self.recent_results = []
    
    def update(self, pnl_pct: float):
        """
        Update with trade result
        """
        now = datetime.now()
        
        # Add to history
        self.recent_results.append({
            "pnl_pct": pnl_pct,
            "timestamp": now
        })
        
        # Keep history manageable
        if len(self.recent_results) > 20:
            self.recent_results = self.recent_results[-20:]
        
        if pnl_pct < 0:  # Loss
            self.consecutive_losses += 1
            self.last_loss_time = now
            
            if self.consecutive_losses == 1:
                self.loss_streak_start = now
            
            logger.warning(f"Consecutive loss #{self.consecutive_losses}")
            
            # Check if cooling needed
            if self.consecutive_losses >= self.max_consecutive:
                self._activate_cooling()
        
        else:  # Win
            if self.consecutive_losses > 0:
                logger.info(f"Loss streak ended after {self.consecutive_losses} losses")
            
            self.consecutive_losses = 0
            self.loss_streak_start = None
    
    def _activate_cooling(self):
        """Activate cooling period"""
        self.cooling_until = datetime.now() + timedelta(minutes=self.cooling_minutes)
        logger.warning(f"Cooling activated until {self.cooling_until.strftime('%H:%M')}")
    
    def should_stop(self) -> bool:
        """Check if trading should stop"""
        # Check cooling period
        if self.cooling_until and datetime.now() < self.cooling_until:
            remaining = (self.cooling_until - datetime.now()).total_seconds() / 60
            logger.debug(f"Cooling: {remaining:.1f} minutes remaining")
            return True
        
        # Check max consecutive losses
        if self.consecutive_losses >= self.max_consecutive:
            return True
        
        return False
    
    def get_size_multiplier(self) -> float:
        """Get position size multiplier based on loss streak"""
        if self.consecutive_losses == 0:
            return 1.0
        elif self.consecutive_losses == 1:
            return 0.7  # 30% reduction
        elif self.consecutive_losses >= 2:
            return 0.0  # No trading
        else:
            return 1.0
    
    def get_status(self) -> Dict:
        """Get loss tracker status"""
        now = datetime.now()
        
        cooling_remaining = 0
        if self.cooling_until and now < self.cooling_until:
            cooling_remaining = (self.cooling_until - now).total_seconds() / 60
        
        return {
            "consecutive_losses": self.consecutive_losses,
            "max_allowed": self.max_consecutive,
            "in_cooling": cooling_remaining > 0,
            "cooling_remaining_minutes": round(cooling_remaining, 1),
            "should_stop": self.should_stop(),
            "size_multiplier": self.get_size_multiplier(),
            "loss_streak_start": self.loss_streak_start.isoformat() if self.loss_streak_start else None,
            "recent_results": self.recent_results[-5:]  # Last 5 results
        }
    
    def reset(self):
        """Reset loss tracking"""
        self.consecutive_losses = 0
        self.last_loss_time = None
        self.cooling_until = None
        self.loss_streak_start = None
        logger.info("Consecutive loss tracker reset")
