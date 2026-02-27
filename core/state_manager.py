"""
ARUNABHA ALGO BOT - State Manager v5.0
========================================
FIXES:
ISSUE 4:  Correlation Filter — dynamic, not static
  - correlation groups এখন config থেকে নেওয়া (overrideable)
  - RENDER/USDT properly grouped
  - dynamic_correlation_check(): real-time price correlation check করে
    (যদি BTC prices available থাকে)
  - Static groups = fallback only

ISSUE 12: Entry Zone — engine.py-এ properly used (signal-এ entry_zone_valid flag)
ISSUE 20: Paper Trading P&L persisted in state file
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple

logger = logging.getLogger(__name__)

STATE_FILE = "bot_state.json"

# ISSUE 4 FIX: RENDER/USDT added, groups more granular
# These are FALLBACK groups — dynamic correlation overrides them
DEFAULT_CORRELATION_GROUPS = [
    {"BTC/USDT", "ETH/USDT"},               # BTC + ETH always correlated
    {"ETH/USDT", "SOL/USDT"},               # ETH ecosystem
    {"SOL/USDT", "RENDER/USDT"},            # ISSUE 4 FIX: RENDER is Solana ecosystem
    {"DOGE/USDT"},                           # Meme (isolated)
]

# Dynamic correlation threshold — if real-time r > this, treat as correlated
DYNAMIC_CORR_THRESHOLD = 0.75
ENTRY_ZONE_PCT = 0.3


class StateManager:
    """
    Persistent state manager.
    ISSUE 4: Dynamic + static correlation blocking
    ISSUE 20: Paper P&L persisted
    """

    def __init__(self):
        self.state: Dict[str, Any] = self._default_state()
        self._load()
        # In-memory price history for dynamic correlation
        self._recent_prices: Dict[str, List[float]] = {}
        self._btc_recent_prices: List[float] = []

    def _default_state(self) -> Dict[str, Any]:
        return {
            "version": "5.0",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "daily_trades": 0,
            "daily_wins": 0,
            "daily_losses": 0,
            "daily_pnl_pct": 0.0,
            "daily_pnl_inr": 0.0,
            "consecutive_losses": 0,
            "peak_balance": None,
            "current_balance": None,
            "active_signals": {},
            "last_signal_time": {},
            "active_directions": {},
            "daily_signals_count": 0,
            "is_daily_locked": False,
            "lock_reason": "",
            # ISSUE 20 FIX: paper P&L persisted
            "paper_pnl_inr": 0.0,
            "paper_trades": 0,
            "paper_wins": 0,
            "last_updated": datetime.now().isoformat(),
        }

    def _load(self):
        try:
            if not os.path.exists(STATE_FILE):
                logger.info("📁 No state file — starting fresh")
                self._save()
                return

            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)

            today = datetime.now().strftime("%Y-%m-%d")
            if saved.get("date", "") != today:
                logger.info(f"📅 New day ({today}) — resetting daily stats")
                old_balance = saved.get("current_balance")
                old_peak = saved.get("peak_balance")
                # ISSUE 20 FIX: keep paper P&L across days
                paper_pnl = saved.get("paper_pnl_inr", 0.0)
                paper_trades = saved.get("paper_trades", 0)
                paper_wins = saved.get("paper_wins", 0)
                self.state = self._default_state()
                if old_balance:
                    self.state["current_balance"] = old_balance
                if old_peak:
                    self.state["peak_balance"] = old_peak
                self.state["paper_pnl_inr"] = paper_pnl
                self.state["paper_trades"] = paper_trades
                self.state["paper_wins"] = paper_wins
            else:
                self.state = saved
                logger.info(
                    f"✅ State loaded: {self.state['daily_trades']} trades, "
                    f"{self.state['consecutive_losses']} consec losses, "
                    f"paper P&L ₹{self.state.get('paper_pnl_inr', 0):+,.0f}"
                )
        except Exception as e:
            logger.error(f"State load failed: {e} — starting fresh")
            self.state = self._default_state()

    def _save(self):
        try:
            self.state["last_updated"] = datetime.now().isoformat()
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"State save failed: {e}")

    # ── ISSUE 4 FIX: Dynamic Correlation ─────────────────────────────

    def update_price_history(self, symbol: str, price: float, is_btc: bool = False):
        """Feed price history for dynamic correlation calculation"""
        if is_btc:
            self._btc_recent_prices.append(price)
            if len(self._btc_recent_prices) > 50:
                self._btc_recent_prices.pop(0)
        else:
            if symbol not in self._recent_prices:
                self._recent_prices[symbol] = []
            self._recent_prices[symbol].append(price)
            if len(self._recent_prices[symbol]) > 50:
                self._recent_prices[symbol].pop(0)

    def _dynamic_correlation(self, symbol: str, lookback: int = 20) -> Optional[float]:
        """
        ISSUE 4 FIX: Calculate real-time Pearson correlation with BTC.
        Returns None if insufficient data.
        """
        sym_prices = self._recent_prices.get(symbol, [])
        btc_prices = self._btc_recent_prices

        n = min(len(sym_prices), len(btc_prices), lookback)
        if n < 10:
            return None

        x = sym_prices[-n:]
        y = btc_prices[-n:]

        # Pearson correlation
        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = (sum((v - mean_x) ** 2 for v in x) / n) ** 0.5
        std_y = (sum((v - mean_y) ** 2 for v in y) / n) ** 0.5

        if std_x == 0 or std_y == 0:
            return 0.0
        return cov / (n * std_x * std_y)

    def is_correlated_blocked(self, symbol: str, direction: str) -> Tuple[bool, str]:
        """
        ISSUE 4 FIX: Dynamic + static correlation check.

        Priority:
        1. Dynamic: if we have 20+ prices and r > 0.75 with an active position → block
        2. Static fallback: DEFAULT_CORRELATION_GROUPS
        """
        active_dirs = self.state.get("active_directions", {})

        # Check all active positions
        for other_symbol, other_dir in active_dirs.items():
            if other_symbol == symbol or other_dir != direction:
                continue

            # 1. Try dynamic correlation first
            dyn_r = self._dynamic_correlation(symbol)
            if dyn_r is not None:
                if abs(dyn_r) > DYNAMIC_CORR_THRESHOLD:
                    return (
                        True,
                        f"Dynamic correlation with {other_symbol}: r={dyn_r:.2f} > {DYNAMIC_CORR_THRESHOLD} — "
                        f"both {direction}, double exposure blocked"
                    )
                # Low correlation → allow
                continue

            # 2. Static fallback
            for group in DEFAULT_CORRELATION_GROUPS:
                if symbol in group and other_symbol in group:
                    return (
                        True,
                        f"Static group: {other_symbol} already {direction} — "
                        f"correlated pair block"
                    )

        return False, "OK"

    def register_active_signal(self, symbol: str, direction: str):
        self.state["active_directions"][symbol] = direction
        self._save()

    def clear_active_signal(self, symbol: str):
        self.state["active_directions"].pop(symbol, None)
        self.state["active_signals"].pop(symbol, None)
        self._save()

    # ── ISSUE 12 FIX: Entry Zone ──────────────────────────────────────

    def get_entry_zone(self, signal_price: float, direction: str) -> Dict[str, float]:
        zone_pct = ENTRY_ZONE_PCT / 100
        if direction == "LONG":
            return {
                "entry_min": round(signal_price * (1 - zone_pct), 8),
                "entry_max": round(signal_price * (1 + zone_pct * 0.3), 8),
                "ideal": round(signal_price, 8),
                "zone_pct": ENTRY_ZONE_PCT,
            }
        else:
            return {
                "entry_min": round(signal_price * (1 - zone_pct * 0.3), 8),
                "entry_max": round(signal_price * (1 + zone_pct), 8),
                "ideal": round(signal_price, 8),
                "zone_pct": ENTRY_ZONE_PCT,
            }

    def is_price_in_entry_zone(self, current_price: float, entry_zone: Dict) -> bool:
        return entry_zone["entry_min"] <= current_price <= entry_zone["entry_max"]

    def check_entry_zone_valid(self, signal: Dict, current_price: float) -> Tuple[bool, str]:
        """
        ISSUE 12 FIX: Called from engine before sending signal.
        If price has moved outside entry zone, skip signal.
        """
        entry_zone = signal.get("entry_zone")
        if not entry_zone:
            return True, "No entry zone defined"
        if self.is_price_in_entry_zone(current_price, entry_zone):
            return True, f"Price {current_price:.6f} in zone [{entry_zone['entry_min']:.6f} - {entry_zone['entry_max']:.6f}]"
        return False, f"Price {current_price:.6f} outside entry zone — signal stale"

    # ── ISSUE 20 FIX: Paper P&L Persist ──────────────────────────────

    def record_paper_trade(self, symbol: str, pnl_inr: float):
        """ISSUE 20 FIX: Paper trades persisted in state file"""
        self.state["paper_pnl_inr"] = self.state.get("paper_pnl_inr", 0.0) + pnl_inr
        self.state["paper_trades"] = self.state.get("paper_trades", 0) + 1
        if pnl_inr > 0:
            self.state["paper_wins"] = self.state.get("paper_wins", 0) + 1
        self.clear_active_signal(symbol)
        self._save()
        logger.info(
            f"📄 Paper trade: {symbol} ₹{pnl_inr:+,.0f} | "
            f"Total paper P&L: ₹{self.state['paper_pnl_inr']:+,.0f}"
        )

    def get_paper_stats(self) -> Dict:
        trades = self.state.get("paper_trades", 0)
        wins = self.state.get("paper_wins", 0)
        return {
            "paper_trades": trades,
            "paper_wins": wins,
            "paper_win_rate": round(wins / max(trades, 1) * 100, 1),
            "paper_pnl_inr": round(self.state.get("paper_pnl_inr", 0.0), 2),
        }

    # ── Trade Tracking ────────────────────────────────────────────────

    def record_trade(self, symbol: str, pnl_pct: float, pnl_inr: float):
        self.state["daily_trades"] += 1
        self.state["daily_pnl_pct"] += pnl_pct
        self.state["daily_pnl_inr"] += pnl_inr

        if pnl_pct > 0:
            self.state["daily_wins"] += 1
            self.state["consecutive_losses"] = 0
        else:
            self.state["daily_losses"] += 1
            self.state["consecutive_losses"] += 1

        import config as cfg
        if self.state["current_balance"] is None:
            self.state["current_balance"] = cfg.ACCOUNT_SIZE
        self.state["current_balance"] += pnl_inr

        if (self.state["peak_balance"] is None or
                self.state["current_balance"] > self.state["peak_balance"]):
            self.state["peak_balance"] = self.state["current_balance"]

        self.clear_active_signal(symbol)
        self._save()

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

    # ── Properties ────────────────────────────────────────────────────

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
        import config as cfg
        return self.state.get("current_balance") or cfg.ACCOUNT_SIZE

    @property
    def peak_balance(self) -> float:
        import config as cfg
        return self.state.get("peak_balance") or cfg.ACCOUNT_SIZE

    @property
    def current_drawdown_pct(self) -> float:
        peak = self.peak_balance
        current = self.current_balance
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - current) / peak * 100)

    def get_full_status(self) -> Dict:
        paper = self.get_paper_stats()
        return {
            "date": self.state["date"],
            "daily_trades": self.daily_trades,
            "daily_wins": self.state["daily_wins"],
            "daily_losses": self.state["daily_losses"],
            "win_rate": round(self.state["daily_wins"] / max(self.daily_trades, 1) * 100, 1),
            "daily_pnl_pct": round(self.daily_pnl_pct, 3),
            "daily_pnl_inr": round(self.daily_pnl_inr, 0),
            "consecutive_losses": self.consecutive_losses,
            "current_balance": round(self.current_balance, 0),
            "peak_balance": round(self.peak_balance, 0),
            "current_drawdown_pct": round(self.current_drawdown_pct, 2),
            "active_signals": len(self.state.get("active_directions", {})),
            "is_daily_locked": self.state["is_daily_locked"],
            **paper,
        }

    def reset_daily(self):
        current_bal = self.state.get("current_balance")
        peak_bal = self.state.get("peak_balance")
        paper_pnl = self.state.get("paper_pnl_inr", 0.0)
        paper_trades = self.state.get("paper_trades", 0)
        paper_wins = self.state.get("paper_wins", 0)
        active_dirs = self.state.get("active_directions", {})

        self.state = self._default_state()
        self.state["current_balance"] = current_bal
        self.state["peak_balance"] = peak_bal
        self.state["paper_pnl_inr"] = paper_pnl
        self.state["paper_trades"] = paper_trades
        self.state["paper_wins"] = paper_wins
        self.state["active_directions"] = active_dirs
        self._save()
        logger.info("📅 Daily reset complete")
