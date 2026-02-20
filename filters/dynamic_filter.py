"""
ARUNABHA ALGO BOT - Dynamic Filter Adjuster
Adjusts filter thresholds based on market conditions and performance
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import config
from core.constants import MarketType

logger = logging.getLogger(__name__)


class DynamicFilter:
    """
    Dynamically adjusts filter thresholds based on:
    - Market conditions
    - Recent performance
    - Time of day
    """
    
    def __init__(self):
        self.performance_history: List[Dict] = []
        self.consecutive_losses = 0
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.last_reset = datetime.now()
        
        # Base thresholds
        self.base_thresholds = {
            "tier2_min_score": config.MIN_TIER2_SCORE,
            "min_signal_score": config.MIN_SIGNAL_SCORE,
            "max_signals": config.MAX_SIGNALS_PER_DAY["default"]
        }
        
        # Current adjusted thresholds
        self.current = self.base_thresholds.copy()
    
    def update(self, market_type: MarketType) -> Dict[str, int]:
        """
        Update thresholds based on current conditions
        """
        self._check_daily_reset()
        
        # Start with base
        thresholds = self.base_thresholds.copy()
        
        # Adjust based on market type
        market_adj = self._get_market_adjustment(market_type)
        for k, v in market_adj.items():
            thresholds[k] += v
        
        # Adjust based on performance
        perf_adj = self._get_performance_adjustment()
        for k, v in perf_adj.items():
            thresholds[k] += v
        
        # Adjust based on time
        time_adj = self._get_time_adjustment()
        for k, v in time_adj.items():
            thresholds[k] += v
        
        # Ensure thresholds stay in reasonable range
        thresholds["tier2_min_score"] = max(40, min(80, thresholds["tier2_min_score"]))
        thresholds["min_signal_score"] = max(50, min(85, thresholds["min_signal_score"]))
        thresholds["max_signals"] = max(1, min(8, thresholds["max_signals"]))
        
        self.current = thresholds
        return thresholds
    
    def _check_daily_reset(self):
        """Reset daily counters if new day"""
        now = datetime.now()
        if now.date() > self.last_reset.date():
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self.last_reset = now
            logger.info("Daily filter counters reset")
    
    def _get_market_adjustment(self, market_type: MarketType) -> Dict[str, int]:
        """Get adjustments based on market type"""
        if market_type == MarketType.TRENDING:
            return {
                "tier2_min_score": -5,  # Easier in trending
                "min_signal_score": -5,
                "max_signals": +1
            }
        elif market_type == MarketType.CHOPPY:
            return {
                "tier2_min_score": +0,  # Normal in choppy
                "min_signal_score": +0,
                "max_signals": -1
            }
        elif market_type == MarketType.HIGH_VOL:
            return {
                "tier2_min_score": +10,  # Stricter in high vol
                "min_signal_score": +10,
                "max_signals": -2
            }
        else:
            return {}
    
    def _get_performance_adjustment(self) -> Dict[str, int]:
        """Get adjustments based on recent performance"""
        adj = {}
        
        # Consecutive losses - get stricter
        if self.consecutive_losses >= 2:
            adj["tier2_min_score"] = +10
            adj["min_signal_score"] = +15
            adj["max_signals"] = -2
        elif self.consecutive_losses == 1:
            adj["tier2_min_score"] = +5
            adj["min_signal_score"] = +5
            adj["max_signals"] = -1
        
        # Daily trades - reduce after reaching target
        if self.daily_trades >= 3:
            adj["tier2_min_score"] = +5
            adj["min_signal_score"] = +5
        
        # Daily profit - stop after target
        if self.daily_pnl >= config.DAILY_PROFIT_TARGET:
            adj["max_signals"] = 0  # No more signals today
        
        return adj
    
    def _get_time_adjustment(self) -> Dict[str, int]:
        """Get adjustments based on time of day"""
        from datetime import datetime
        import pytz
        
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        hour = now.hour
        
        # London/NY overlap (best time) - easier
        if 20 <= hour <= 22:  # 8PM-10PM IST
            return {
                "tier2_min_score": -5,
                "max_signals": +1
            }
        
        # Asia session (low vol) - stricter
        elif 7 <= hour <= 10:  # 7AM-10AM IST
            return {
                "tier2_min_score": +5,
                "max_signals": -1
            }
        
        # Lunch/dead zone - much stricter
        elif 11 <= hour <= 13:  # 11AM-1PM IST
            return {
                "tier2_min_score": +10,
                "max_signals": -2
            }
        
        return {}
    
    def record_trade_result(self, pnl_pct: float):
        """Record trade result for performance tracking"""
        self.daily_trades += 1
        self.daily_pnl += pnl_pct
        
        if pnl_pct < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Store in history
        self.performance_history.append({
            "timestamp": datetime.now().isoformat(),
            "pnl_pct": pnl_pct,
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl
        })
        
        # Keep history manageable
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]
    
    def should_trade(self, market_type: MarketType) -> bool:
        """Check if we should trade at all"""
        # Update thresholds first
        thresholds = self.update(market_type)
        
        # Check max signals
        if self.daily_trades >= thresholds["max_signals"]:
            logger.debug(f"Max signals reached: {self.daily_trades}/{thresholds['max_signals']}")
            return False
        
        # Check daily profit target
        if self.daily_pnl >= config.DAILY_PROFIT_TARGET:
            logger.info(f"Daily profit target reached: ₹{self.daily_pnl:.2f}")
            return False
        
        # Check max consecutive losses
        if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            logger.warning(f"Max consecutive losses reached: {self.consecutive_losses}")
            return False
        
        return True
    
    def get_thresholds(self) -> Dict[str, int]:
        """Get current thresholds"""
        return self.current.copy()
    
    def get_status(self) -> Dict:
        """Get dynamic filter status"""
        return {
            "consecutive_losses": self.consecutive_losses,
            "daily_trades": self.daily_trades,
            "daily_pnl": self.daily_pnl,
            "current_thresholds": self.current,
            "should_trade": self.should_trade(MarketType.UNKNOWN)
        }
