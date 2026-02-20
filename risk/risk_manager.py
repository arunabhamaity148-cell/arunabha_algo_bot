"""
ARUNABHA ALGO BOT - Risk Manager
Central risk management and trade approval
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

import config
from core.constants import TradeDirection, MarketType
from risk.position_sizing import PositionSizer
from risk.drawdown_controller import DrawdownController
from risk.daily_lock import DailyLock
from risk.consecutive_loss import ConsecutiveLossTracker

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Central risk management for all trades
    """
    
    def __init__(self):
        self.position_sizer = PositionSizer()
        self.drawdown = DrawdownController()
        self.daily_lock = DailyLock()
        self.loss_tracker = ConsecutiveLossTracker()
        
        self.active_trades: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []
        
        logger.info("RiskManager initialized")
    
    def can_trade(
        self,
        symbol: str,
        market_type: MarketType = MarketType.UNKNOWN
    ) -> Tuple[bool, str]:
        """
        Check if we can take a new trade
        """
        # Check daily lock
        if self.daily_lock.is_locked:
            return False, f"Daily lock active: {self.daily_lock.reason}"
        
        # Check drawdown
        if self.drawdown.is_max_drawdown_reached():
            return False, f"Max drawdown reached: {self.drawdown.current_drawdown:.2f}%"
        
        # Check max consecutive losses
        if self.loss_tracker.should_stop():
            return False, f"Max consecutive losses: {self.loss_tracker.consecutive_losses}"
        
        # Check max concurrent trades
        if len(self.active_trades) >= config.MAX_CONCURRENT:
            return False, f"Max concurrent trades: {config.MAX_CONCURRENT}"
        
        # Check if symbol already has active trade
        if symbol in self.active_trades:
            return False, f"Active trade exists for {symbol}"
        
        return True, "OK"
    
    def approve_trade(
        self,
        symbol: str,
        direction: TradeDirection,
        entry: float,
        stop_loss: float,
        take_profit: float,
        account_size: float,
        atr_pct: float = 1.0,
        fear_index: int = 50,
        market_type: MarketType = MarketType.UNKNOWN
    ) -> Optional[Dict]:
        """
        Approve trade and calculate position size
        """
        # Check if we can trade
        can_trade, reason = self.can_trade(symbol, market_type)
        if not can_trade:
            logger.debug(f"Trade rejected: {reason}")
            return None
        
        # Calculate position size
        position = self.position_sizer.calculate(
            account_size=account_size,
            entry=entry,
            stop_loss=stop_loss,
            atr_pct=atr_pct,
            fear_index=fear_index,
            market_type=market_type
        )
        
        if position.get("blocked", False):
            logger.debug(f"Position sizing blocked: {position.get('reason')}")
            return None
        
        # Create trade record
        trade = {
            "symbol": symbol,
            "direction": direction.value,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_usd": position["position_usd"],
            "contracts": position["contracts"],
            "risk_usd": position["risk_usd"],
            "timestamp": datetime.now(),
            "max_holding_minutes": 60 if market_type == MarketType.CHOPPY else 90,
            "partial_exit_done": False,
            "be_triggered": False
        }
        
        # Add to active trades
        self.active_trades[symbol] = trade
        
        logger.info(
            f"Trade approved: {symbol} {direction.value} @ {entry} | "
            f"Size: ${position['position_usd']:.2f} | Risk: ${position['risk_usd']:.2f}"
        )
        
        return trade
    
    def update_trade(
        self,
        symbol: str,
        current_price: float
    ) -> Optional[Dict]:
        """
        Update active trade (check SL/TP, partial exits, BE)
        """
        if symbol not in self.active_trades:
            return None
        
        trade = self.active_trades[symbol]
        direction = TradeDirection(trade["direction"])
        
        # Calculate current R multiple
        if direction == TradeDirection.LONG:
            r_distance = trade["entry"] - trade["stop_loss"]
            if r_distance > 0:
                current_r = (current_price - trade["entry"]) / r_distance
            else:
                current_r = 0
        else:
            r_distance = trade["stop_loss"] - trade["entry"]
            if r_distance > 0:
                current_r = (trade["entry"] - current_price) / r_distance
            else:
                current_r = 0
        
        result = {
            "symbol": symbol,
            "current_price": current_price,
            "current_r": current_r,
            "action": None,
            "message": ""
        }
        
        # Check for partial exit (1R)
        if current_r >= config.PARTIAL_EXIT_AT_R and not trade["partial_exit_done"]:
            trade["partial_exit_done"] = True
            result["action"] = "PARTIAL_EXIT"
            result["message"] = f"Partial exit at {current_r:.2f}R"
        
        # Check for break-even (0.5R)
        if current_r >= config.BREAK_EVEN_AT_R and not trade["be_triggered"]:
            trade["be_triggered"] = True
            trade["stop_loss"] = trade["entry"]  # Move SL to entry
            result["action"] = "BREAK_EVEN"
            result["message"] = f"SL moved to entry at {current_r:.2f}R"
        
        # Check stop loss
        if direction == TradeDirection.LONG:
            if current_price <= trade["stop_loss"]:
                result["action"] = "SL_HIT"
                result["message"] = f"Stop loss hit at {current_price}"
        else:
            if current_price >= trade["stop_loss"]:
                result["action"] = "SL_HIT"
                result["message"] = f"Stop loss hit at {current_price}"
        
        # Check take profit
        if direction == TradeDirection.LONG:
            if current_price >= trade["take_profit"]:
                result["action"] = "TP_HIT"
                result["message"] = f"Take profit hit at {current_price}"
        else:
            if current_price <= trade["take_profit"]:
                result["action"] = "TP_HIT"
                result["message"] = f"Take profit hit at {current_price}"
        
        return result
    
    def close_trade(
        self,
        symbol: str,
        exit_price: float,
        reason: str
    ) -> Optional[float]:
        """
        Close a trade and calculate P&L
        """
        if symbol not in self.active_trades:
            return None
        
        trade = self.active_trades.pop(symbol)
        
        # Calculate P&L
        if trade["direction"] == "LONG":
            pnl_pct = (exit_price - trade["entry"]) / trade["entry"] * 100
        else:
            pnl_pct = (trade["entry"] - exit_price) / trade["entry"] * 100
        
        # Add to history
        trade_record = {
            **trade,
            "exit_price": exit_price,
            "exit_time": datetime.now(),
            "pnl_pct": pnl_pct,
            "pnl_usd": trade["position_usd"] * (pnl_pct / 100),
            "reason": reason
        }
        self.trade_history.append(trade_record)
        
        # Update trackers
        self.drawdown.update(pnl_pct)
        self.loss_tracker.update(pnl_pct)
        self.daily_lock.update(pnl_pct)
        
        # Log result
        if pnl_pct > 0:
            logger.info(f"✅ Trade closed: {symbol} @ {pnl_pct:.2f}% | Reason: {reason}")
        else:
            logger.warning(f"❌ Trade closed: {symbol} @ {pnl_pct:.2f}% | Reason: {reason}")
        
        return pnl_pct
    
    def check_timeouts(self) -> List[str]:
        """
        Check for timed out trades
        """
        timed_out = []
        now = datetime.now()
        
        for symbol, trade in list(self.active_trades.items()):
            holding_minutes = (now - trade["timestamp"]).total_seconds() / 60
            
            if holding_minutes > trade["max_holding_minutes"]:
                timed_out.append(symbol)
        
        return timed_out
    
    def reset_daily(self):
        """Reset daily counters"""
        self.drawdown.reset()
        self.loss_tracker.reset()
        self.daily_lock.reset()
        logger.info("RiskManager daily reset")
    
    def get_status(self) -> Dict:
        """Get risk manager status"""
        return {
            "active_trades": len(self.active_trades),
            "active_symbols": list(self.active_trades.keys()),
            "drawdown": self.drawdown.get_status(),
            "consecutive_losses": self.loss_tracker.consecutive_losses,
            "daily_lock": self.daily_lock.get_status(),
            "total_trades_today": len([t for t in self.trade_history if t["exit_time"].date() == datetime.now().date()])
        }
