"""
ARUNABHA ALGO BOT - State Manager v4.2
=======================================

Points implemented:
Point 3  — Correlation filter: একসাথে correlated pairs এ signal block
Point 7  — Trade state persistence: restart-এ state হারায় না (JSON file)
Point 11 — Partial fill handling: entry zone define করা হচ্ছে
Point 17 — Background task error handling: state save fail হলে log করে

State file: bot_state.json (repo root-এ)
Bot restart হলে এই file থেকে state restore হবে।
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger(__name__)

STATE_FILE = "bot_state.json"

# Correlation groups — এই pairs একসাথে same direction-এ trade করা যাবে না
CORRELATION_GROUPS = [
    {"BTC/USDT", "ETH/USDT"},          # BTC + ETH strongly correlated
    {"ETH/USDT", "SOL/USDT"},          # ETH ecosystem
    {"DOGE/USDT", "SHIB/USDT"},        # Meme coins
    {"SOL/USDT", "AVAX/USDT"},         # Alt L1s
]

# Entry zone tolerance: signal price থেকে এই % এর মধ্যে entry valid
ENTRY_ZONE_PCT = 0.3   # 0.3% zone


class StateManager:
    """
    Persistent state manager — bot restart-এ state হারায় না।

    Manages:
    - Active signals (direction, entry zone, SL, TP)
    - Daily stats (trades, wins, losses, P&L)
    - Consecutive losses
    - Last signal time per symbol
    - Correlation tracking (which pairs are in active positions)
    """

    def __init__(self):
        self.state: Dict[str, Any] = self._default_state()
        self._load()

    # ─────────────────────────────────────────────
    # STATE PERSISTENCE (Point 7)
    # ─────────────────────────────────────────────

    def _default_state(self) -> Dict[str, Any]:
        return {
            "version": "4.2",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "daily_trades": 0,
            "daily_wins": 0,
            "daily_losses": 0,
            "daily_pnl_pct": 0.0,
            "daily_pnl_inr": 0.0,
            "consecutive_losses": 0,
            "peak_balance": None,       # None মানে config.ACCOUNT_SIZE থেকে নেওয়া হবে
            "current_balance": None,
            "active_signals": {},       # symbol → signal dict
            "last_signal_time": {},     # symbol → ISO timestamp
            "active_directions": {},    # symbol → "LONG"/"SHORT" (correlation tracking)
            "daily_signals_count": 0,
            "is_daily_locked": False,
            "lock_reason": "",
            "last_updated": datetime.now().isoformat(),
        }

    def _load(self):
        """Load state from JSON file — restart-safe"""
        try:
            if not os.path.exists(STATE_FILE):
                logger.info("📁 No state file found — starting fresh")
                self._save()
                return

            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)

            # Date check: নতুন দিন হলে daily stats reset করো
            saved_date = saved.get("date", "")
            today = datetime.now().strftime("%Y-%m-%d")

            if saved_date != today:
                logger.info(f"📅 New day ({today}) — resetting daily stats")
                # Balance persist করো, daily stats reset করো
                old_balance = saved.get("current_balance")
                old_peak = saved.get("peak_balance")
                self.state = self._default_state()
                if old_balance:
                    self.state["current_balance"] = old_balance
                if old_peak:
                    self.state["peak_balance"] = old_peak
            else:
                self.state = saved
                logger.info(
                    f"✅ State loaded: {self.state['daily_trades']} trades today, "
                    f"{self.state['consecutive_losses']} consecutive losses"
                )

        except Exception as e:
            logger.error(f"❌ State load failed: {e} — starting fresh")
            self.state = self._default_state()

    def _save(self):
        """Save state to JSON file"""
        try:
            self.state["last_updated"] = datetime.now().isoformat()
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            # Point 17: Error log করো, crash করো না
            logger.error(f"❌ State save failed: {e}")

    # ─────────────────────────────────────────────
    # CORRELATION FILTER (Point 3)
    # ─────────────────────────────────────────────

    def is_correlated_blocked(self, symbol: str, direction: str) -> tuple:
        """
        ✅ Point 3: Correlation filter

        একই correlation group-এ যদি আগে থেকে কোনো pair-এ active signal থাকে,
        same direction-এ নতুন signal block করো।

        Example:
            BTC/USDT LONG active থাকলে → ETH/USDT LONG block
            কারণ: দুটো একই direction-এ নেওয়া মানে double exposure

        Returns: (is_blocked, reason)
        """
        active_dirs = self.state.get("active_directions", {})

        for group in CORRELATION_GROUPS:
            if symbol not in group:
                continue

            # Check other pairs in same group
            for other_symbol in group:
                if other_symbol == symbol:
                    continue

                other_dir = active_dirs.get(other_symbol)
                if other_dir and other_dir == direction:
                    return (
                        True,
                        f"Correlated pair {other_symbol} already {direction} — "
                        f"double exposure blocked"
                    )

        return False, "OK"

    def register_active_signal(self, symbol: str, direction: str):
        """Mark symbol as having active signal in given direction"""
        self.state["active_directions"][symbol] = direction
        self._save()

    def clear_active_signal(self, symbol: str):
        """Clear active signal for symbol (after TP/SL hit)"""
        self.state["active_directions"].pop(symbol, None)
        self.state["active_signals"].pop(symbol, None)
        self._save()

    # ─────────────────────────────────────────────
    # ENTRY ZONE (Point 11)
    # ─────────────────────────────────────────────

    def get_entry_zone(self, signal_price: float, direction: str) -> Dict[str, float]:
        """
        ✅ Point 11: Entry zone calculation

        Signal দেওয়ার পর market কিছুটা move করে।
        Exact price-এ entry না পেলে ±0.3% zone-এর মধ্যে entry valid।

        LONG:  entry_min = signal_price * (1 - 0.003)
               entry_max = signal_price * (1 + 0.001)  ← উপরে বেশি যেতে দিও না

        SHORT: entry_min = signal_price * (1 - 0.001)
               entry_max = signal_price * (1 + 0.003)
        """
        zone_pct = ENTRY_ZONE_PCT / 100

        if direction == "LONG":
            return {
                "entry_min": round(signal_price * (1 - zone_pct), 8),
                "entry_max": round(signal_price * (1 + zone_pct * 0.3), 8),
                "ideal": round(signal_price, 8),
                "zone_pct": ENTRY_ZONE_PCT,
            }
        else:  # SHORT
            return {
                "entry_min": round(signal_price * (1 - zone_pct * 0.3), 8),
                "entry_max": round(signal_price * (1 + zone_pct), 8),
                "ideal": round(signal_price, 8),
                "zone_pct": ENTRY_ZONE_PCT,
            }

    def is_price_in_entry_zone(self, current_price: float, entry_zone: Dict) -> bool:
        """Check if current price is still in valid entry zone"""
        return entry_zone["entry_min"] <= current_price <= entry_zone["entry_max"]

    # ─────────────────────────────────────────────
    # TRADE TRACKING
    # ─────────────────────────────────────────────

    def record_trade(self, symbol: str, pnl_pct: float, pnl_inr: float):
        """Record trade result and update all counters"""
        self.state["daily_trades"] += 1
        self.state["daily_pnl_pct"] += pnl_pct
        self.state["daily_pnl_inr"] += pnl_inr

        if pnl_pct > 0:
            self.state["daily_wins"] += 1
            self.state["consecutive_losses"] = 0
        else:
            self.state["daily_losses"] += 1
            self.state["consecutive_losses"] += 1

        # Update balance
        if self.state["current_balance"] is None:
            import config
            self.state["current_balance"] = config.ACCOUNT_SIZE
        self.state["current_balance"] += pnl_inr

        # Update peak
        if (self.state["peak_balance"] is None or
                self.state["current_balance"] > self.state["peak_balance"]):
            self.state["peak_balance"] = self.state["current_balance"]

        self.clear_active_signal(symbol)
        self._save()

        logger.info(
            f"Trade recorded: {symbol} {pnl_pct:+.2f}% (₹{pnl_inr:+.0f}) | "
            f"Consec losses: {self.state['consecutive_losses']}"
        )

    def update_last_signal_time(self, symbol: str):
        self.state["last_signal_time"][symbol] = datetime.now().isoformat()
        self.state["daily_signals_count"] += 1
        self._save()

    def get_last_signal_time(self, symbol: str) -> Optional[datetime]:
        ts = self.state["last_signal_time"].get(symbol)
        if ts:
            try:
                return datetime.fromisoformat(ts)
            except Exception:
                return None
        return None

    # ─────────────────────────────────────────────
    # GETTERS
    # ─────────────────────────────────────────────

    @property
    def consecutive_losses(self) -> int:
        return self.state.get("consecutive_losses", 0)

    @property
    def daily_trades(self) -> int:
        return self.state.get("daily_trades", 0)

    @property
    def daily_pnl_inr(self) -> float:
        return self.state.get("daily_pnl_inr", 0.0)

    @property
    def daily_pnl_pct(self) -> float:
        return self.state.get("daily_pnl_pct", 0.0)

    @property
    def current_balance(self) -> float:
        import config
        return self.state.get("current_balance") or config.ACCOUNT_SIZE

    @property
    def peak_balance(self) -> float:
        import config
        return self.state.get("peak_balance") or config.ACCOUNT_SIZE

    @property
    def current_drawdown_pct(self) -> float:
        peak = self.peak_balance
        current = self.current_balance
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - current) / peak * 100)

    def get_full_status(self) -> Dict[str, Any]:
        return {
            "date": self.state["date"],
            "daily_trades": self.daily_trades,
            "daily_wins": self.state["daily_wins"],
            "daily_losses": self.state["daily_losses"],
            "win_rate": (self.state["daily_wins"] / max(self.daily_trades, 1)) * 100,
            "daily_pnl_pct": round(self.daily_pnl_pct, 3),
            "daily_pnl_inr": round(self.daily_pnl_inr, 0),
            "consecutive_losses": self.consecutive_losses,
            "current_balance": round(self.current_balance, 0),
            "peak_balance": round(self.peak_balance, 0),
            "current_drawdown_pct": round(self.current_drawdown_pct, 2),
            "active_signals": len(self.state.get("active_directions", {})),
            "is_daily_locked": self.state["is_daily_locked"],
        }

    def reset_daily(self):
        """Called at midnight — reset daily stats only"""
        current_bal = self.state.get("current_balance")
        peak_bal = self.state.get("peak_balance")
        active_dirs = self.state.get("active_directions", {})

        self.state = self._default_state()
        # Persist across days
        self.state["current_balance"] = current_bal
        self.state["peak_balance"] = peak_bal
        self.state["active_directions"] = active_dirs  # keep active positions

        self._save()
        logger.info("📅 Daily state reset complete")
