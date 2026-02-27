"""
ARUNABHA ALGO BOT - Risk Manager v5.0
======================================
FIXES:
ISSUE 2: Partial Exit Logic — FIXED
  - PARTIAL_EXIT_AT_R=1.0: actual position_usd কমানো হচ্ছে (50% exit)
  - Trailing stop implementation added
  - Telegram notification for partial exit

ISSUE 7: P&L tracking — FIXED
  - close_trade() এ pnl_inr properly tracked
  - profit_calculator called
  - trade_history-এ INR P&L সঠিকভাবে saved

ISSUE 16: Trailing Stop — FIXED
  - TRAILING_STOP_ATR_MULT = 1.5 config থেকে নেওয়া হচ্ছে
  - trailing SL ATR basis-এ move করছে
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
        if self.daily_lock.is_locked:
            return False, f"Daily lock: {self.daily_lock.reason}"
        if self.drawdown.is_max_drawdown_reached():
            return False, f"Max drawdown: {self.drawdown.current_drawdown:.2f}%"
        if self.loss_tracker.should_stop():
            return False, f"Consecutive losses: {self.loss_tracker.consecutive_losses}"
        if len(self.active_trades) >= config.MAX_CONCURRENT:
            return False, f"Max concurrent: {config.MAX_CONCURRENT}"
        if symbol in self.active_trades:
            return False, f"Active trade exists: {symbol}"
        return True, "OK"

    def calculate_position(
        self,
        account_size: float,
        entry: float,
        stop_loss: float,
        atr_pct: float = 1.0,
        fear_index: int = 50,
        current_drawdown_pct: float = 0.0,
        signal_grade: str = "B"
    ) -> Dict:
        """Calculate position size — delegates to PositionSizer"""
        return self.position_sizer.calculate(
            account_size=account_size,
            entry=entry,
            stop_loss=stop_loss,
            atr_pct=atr_pct,
            fear_index=fear_index,
            current_drawdown_pct=current_drawdown_pct,
            signal_grade=signal_grade
        )

    def approve_trade(
        self,
        symbol: str,
        direction: TradeDirection,
        entry: float,
        stop_loss: float,
        take_profit: float,
        account_size: float,
        atr: float = 0.0,
        atr_pct: float = 1.0,
        fear_index: int = 50,
        market_type: MarketType = MarketType.UNKNOWN
    ) -> Optional[Dict]:
        can_trade, reason = self.can_trade(symbol, market_type)
        if not can_trade:
            logger.debug(f"Trade rejected: {reason}")
            return None

        position = self.position_sizer.calculate(
            account_size=account_size,
            entry=entry,
            stop_loss=stop_loss,
            atr_pct=atr_pct,
            fear_index=fear_index,
            market_type=market_type
        )

        if position.get("blocked", False):
            return None

        trade = {
            "symbol": symbol,
            "direction": direction.value,
            "entry": entry,
            "stop_loss": stop_loss,
            "initial_stop_loss": stop_loss,   # keep original for reference
            "take_profit": take_profit,
            "position_usd": position["position_usd"],
            "initial_position_usd": position["position_usd"],
            "contracts": position.get("contracts", 0),
            "risk_usd": position.get("risk_usd", 0),
            "atr": atr,
            "timestamp": datetime.now(),
            "max_holding_minutes": 60 if market_type == MarketType.CHOPPY else 90,
            "partial_exit_done": False,
            "partial_exit_pct": 0.0,     # % of position already exited
            "be_triggered": False,
            "trailing_sl": stop_loss,    # starts at initial SL
            "trailing_active": False,
            "highest_price": entry if direction.value == "LONG" else entry,
            "lowest_price": entry if direction.value == "SHORT" else entry,
        }
        self.active_trades[symbol] = trade

        logger.info(
            f"Trade approved: {symbol} {direction.value} @ {entry} | "
            f"SL={stop_loss:.6f} TP={take_profit:.6f} | "
            f"Size=₹{position['position_usd']:,.0f} | Risk=₹{position.get('risk_usd',0):,.0f}"
        )
        return trade

    def update_trade(self, symbol: str, current_price: float) -> Optional[Dict]:
        """
        Update active trade: check SL/TP, partial exit, BE, trailing stop

        ISSUE 2 FIX: partial exit actually reduces position_usd
        ISSUE 16 FIX: trailing stop moves with price
        """
        if symbol not in self.active_trades:
            return None

        trade = self.active_trades[symbol]
        direction = TradeDirection(trade["direction"])

        # Calculate current R
        r_distance = abs(trade["entry"] - trade["initial_stop_loss"])
        if r_distance <= 0:
            r_distance = 0.001

        if direction == TradeDirection.LONG:
            current_r = (current_price - trade["entry"]) / r_distance
        else:
            current_r = (trade["entry"] - current_price) / r_distance

        result = {
            "symbol": symbol,
            "current_price": current_price,
            "current_r": round(current_r, 2),
            "action": None,
            "message": "",
            "partial_exit_qty_pct": 0.0,
        }

        # ─── ISSUE 16: Trailing Stop ──────────────────────────────────
        atr = trade.get("atr", 0)
        if atr > 0 and current_r >= 1.0:
            trail_mult = config.TRAILING_STOP_ATR_MULT
            trade["trailing_active"] = True

            if direction == TradeDirection.LONG:
                trade["highest_price"] = max(trade["highest_price"], current_price)
                new_trail_sl = trade["highest_price"] - (atr * trail_mult)
                if new_trail_sl > trade["trailing_sl"]:
                    trade["trailing_sl"] = new_trail_sl
                    trade["stop_loss"] = new_trail_sl
                    logger.debug(f"Trailing SL moved to {new_trail_sl:.6f}")
            else:
                trade["lowest_price"] = min(trade["lowest_price"], current_price)
                new_trail_sl = trade["lowest_price"] + (atr * trail_mult)
                if new_trail_sl < trade["trailing_sl"]:
                    trade["trailing_sl"] = new_trail_sl
                    trade["stop_loss"] = new_trail_sl

        # ─── ISSUE 2: Partial Exit at 1R ──────────────────────────────
        if current_r >= config.PARTIAL_EXIT_AT_R and not trade["partial_exit_done"]:
            trade["partial_exit_done"] = True
            # Actually reduce position size by 50%
            original_size = trade["position_usd"]
            exit_size = original_size * 0.5
            trade["position_usd"] = original_size - exit_size
            trade["partial_exit_pct"] = 50.0
            result["action"] = "PARTIAL_EXIT"
            result["partial_exit_qty_pct"] = 50.0
            result["message"] = (
                f"50% exit at {current_r:.1f}R | "
                f"Exited ₹{exit_size:,.0f} | Remaining ₹{trade['position_usd']:,.0f}"
            )
            logger.info(f"⚡ Partial exit {symbol}: {result['message']}")

        # ─── Break Even at 0.5R ───────────────────────────────────────
        if current_r >= config.BREAK_EVEN_AT_R and not trade["be_triggered"]:
            trade["be_triggered"] = True
            trade["stop_loss"] = trade["entry"]
            trade["trailing_sl"] = trade["entry"]
            result["action"] = result["action"] or "BREAK_EVEN"
            result["message"] = result["message"] or f"SL → entry at {current_r:.1f}R"

        # ─── Stop Loss ────────────────────────────────────────────────
        effective_sl = trade["stop_loss"]
        if direction == TradeDirection.LONG:
            if current_price <= effective_sl:
                result["action"] = "SL_HIT"
                result["message"] = f"SL hit @ {current_price:.6f} (trail={trade['trailing_active']})"
        else:
            if current_price >= effective_sl:
                result["action"] = "SL_HIT"
                result["message"] = f"SL hit @ {current_price:.6f}"

        # ─── Take Profit ──────────────────────────────────────────────
        if direction == TradeDirection.LONG:
            if current_price >= trade["take_profit"]:
                result["action"] = "TP_HIT"
                result["message"] = f"TP hit @ {current_price:.6f}"
        else:
            if current_price <= trade["take_profit"]:
                result["action"] = "TP_HIT"
                result["message"] = f"TP hit @ {current_price:.6f}"

        return result

    def close_trade(
        self,
        symbol: str,
        exit_price: float,
        reason: str
    ) -> Optional[Dict]:
        """
        ISSUE 7 FIX: Close trade with proper INR P&L tracking

        Returns full trade record including pnl_inr
        """
        if symbol not in self.active_trades:
            return None

        trade = self.active_trades.pop(symbol)

        # P&L on remaining position
        if trade["direction"] == "LONG":
            pnl_pct = (exit_price - trade["entry"]) / trade["entry"] * 100
        else:
            pnl_pct = (trade["entry"] - exit_price) / trade["entry"] * 100

        # ─── ISSUE 7 FIX: INR P&L calculation ────────────────────────
        remaining_pct = 1.0 - (trade.get("partial_exit_pct", 0) / 100)
        remaining_usd = trade["initial_position_usd"] * remaining_pct

        # Partial exit P&L (locked in at PARTIAL_EXIT_AT_R)
        partial_pnl_inr = 0.0
        if trade.get("partial_exit_done"):
            partial_usd = trade["initial_position_usd"] * 0.5
            partial_pnl_pct = config.PARTIAL_EXIT_AT_R * (
                abs(trade["entry"] - trade["initial_stop_loss"]) / trade["entry"] * 100
            )
            partial_pnl_inr = partial_usd * (partial_pnl_pct / 100)

        # Remaining position P&L
        remaining_pnl_inr = remaining_usd * (pnl_pct / 100)
        total_pnl_inr = partial_pnl_inr + remaining_pnl_inr

        # Indian tax calculation
        try:
            from config import calculate_indian_profit
            tax_calc = calculate_indian_profit(
                entry=trade["entry"],
                exit=exit_price,
                qty=remaining_usd / trade["entry"] if trade["entry"] > 0 else 0,
                side=trade["direction"]
            )
            net_pnl_inr = tax_calc.get("net_pnl", total_pnl_inr)
        except Exception:
            net_pnl_inr = total_pnl_inr

        trade_record = {
            **trade,
            "exit_price": exit_price,
            "exit_time": datetime.now(),
            "pnl_pct": round(pnl_pct, 4),
            "pnl_inr": round(total_pnl_inr, 2),
            "net_pnl_inr": round(net_pnl_inr, 2),
            "partial_pnl_inr": round(partial_pnl_inr, 2),
            "reason": reason,
            "holding_minutes": (datetime.now() - trade["timestamp"]).total_seconds() / 60,
        }
        self.trade_history.append(trade_record)

        # Update trackers
        self.drawdown.update(pnl_pct)
        self.loss_tracker.update(pnl_pct)
        self.daily_lock.update(pnl_pct)

        emoji = "✅" if pnl_pct > 0 else "❌"
        logger.info(
            f"{emoji} Trade closed: {symbol} | {pnl_pct:+.2f}% | "
            f"₹{total_pnl_inr:+,.0f} (net ₹{net_pnl_inr:+,.0f}) | {reason}"
        )
        return trade_record

    def check_timeouts(self) -> List[str]:
        timed_out = []
        now = datetime.now()
        for symbol, trade in list(self.active_trades.items()):
            mins = (now - trade["timestamp"]).total_seconds() / 60
            if mins > trade["max_holding_minutes"]:
                timed_out.append(symbol)
        return timed_out

    def reset_daily(self):
        self.drawdown.reset()
        self.loss_tracker.reset()
        self.daily_lock.reset()
        logger.info("RiskManager daily reset")

    def get_status(self) -> Dict:
        today_trades = [
            t for t in self.trade_history
            if t["exit_time"].date() == datetime.now().date()
        ]
        today_pnl = sum(t.get("net_pnl_inr", 0) for t in today_trades)
        return {
            "active_trades": len(self.active_trades),
            "active_symbols": list(self.active_trades.keys()),
            "drawdown": self.drawdown.get_status(),
            "consecutive_losses": self.loss_tracker.consecutive_losses,
            "daily_lock": self.daily_lock.get_status(),
            "today_trades": len(today_trades),
            "today_pnl_inr": round(today_pnl, 2),
        }
