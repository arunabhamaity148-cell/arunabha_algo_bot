"""
ARUNABHA ALGO BOT - Expectancy Tracker v4.2
============================================

Point 12 — Expectancy tracking (live):
    প্রতিটা trade শেষে expectancy update হবে।
    20+ trade হলে edge আছে কিনা Telegram-এ report যাবে।

    Expectancy formula:
    E = (Win Rate × Avg Win%) - (Loss Rate × Avg Loss%)

    E > 0  → strategy has edge
    E < 0  → strategy loses money on average
    E ≈ 0  → break even

    একটা ভালো strategy-তে Expectancy > 0.3% per trade হওয়া উচিত।
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

EXPECTANCY_FILE = "expectancy_log.json"
MIN_TRADES_FOR_VALID = 20   # কমপক্ষে এতগুলো trade না হলে expectancy reliable নয়


class ExpectancyTracker:
    """
    Live expectancy tracker — manual trade results input করলে
    এই class edge আছে কিনা track করে।

    Usage (manual trade করার পরে):
        tracker.add_trade(symbol="BTCUSDT", direction="LONG", pnl_pct=1.5)
        tracker.add_trade(symbol="ETHUSDT", direction="SHORT", pnl_pct=-0.8)
        print(tracker.get_summary())
    """

    def __init__(self):
        self.trades: List[Dict] = []
        self._load()

    def _load(self):
        """Load existing trade history"""
        try:
            if os.path.exists(EXPECTANCY_FILE):
                with open(EXPECTANCY_FILE, "r") as f:
                    data = json.load(f)
                    self.trades = data.get("trades", [])
                logger.info(f"📊 Expectancy tracker loaded: {len(self.trades)} trades")
        except Exception as e:
            logger.warning(f"Expectancy load failed: {e}")
            self.trades = []

    def _save(self):
        """Save trade history to file"""
        try:
            with open(EXPECTANCY_FILE, "w") as f:
                json.dump({
                    "trades": self.trades,
                    "last_updated": datetime.now().isoformat(),
                    "summary": self.get_stats()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Expectancy save failed: {e}")

    def add_trade(
        self,
        symbol: str,
        direction: str,
        pnl_pct: float,
        grade: str = "B",
        structure: str = "UNKNOWN"
    ):
        """
        Add a completed trade result.

        Args:
            symbol:    e.g. "BTCUSDT"
            direction: "LONG" or "SHORT"
            pnl_pct:   Actual P&L % (e.g. +1.5 or -0.8)
            grade:     Signal grade ("A+", "A", "B+", "B", "C")
            structure: "STRONG" or "MODERATE"
        """
        self.trades.append({
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "direction": direction,
            "pnl_pct": round(pnl_pct, 4),
            "grade": grade,
            "structure": structure,
            "is_win": pnl_pct > 0,
        })
        self._save()

        # Alert if meaningful sample
        n = len(self.trades)
        if n % 10 == 0 and n >= MIN_TRADES_FOR_VALID:
            stats = self.get_stats()
            logger.info(
                f"📊 Expectancy update ({n} trades): "
                f"E={stats['expectancy']:+.3f}% | "
                f"WR={stats['win_rate']:.1f}% | "
                f"PF={stats['profit_factor']:.2f}"
            )

    def get_stats(self) -> Dict:
        """Calculate current expectancy and related stats"""
        if not self.trades:
            return self._empty_stats()

        wins = [t for t in self.trades if t["is_win"]]
        losses = [t for t in self.trades if not t["is_win"]]
        n = len(self.trades)
        nw = len(wins)
        nl = len(losses)

        win_rate = nw / n * 100
        avg_win = sum(t["pnl_pct"] for t in wins) / nw if wins else 0.0
        avg_loss = abs(sum(t["pnl_pct"] for t in losses) / nl) if losses else 0.0

        # E = (WR × avg_win) - (LR × avg_loss)
        wr_d = nw / n
        expectancy = (wr_d * avg_win) - ((1 - wr_d) * avg_loss)

        # Profit factor
        gross_profit = sum(t["pnl_pct"] for t in wins) if wins else 0.0
        gross_loss = abs(sum(t["pnl_pct"] for t in losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit

        # Grade breakdown
        grade_stats = {}
        for grade in ["A+", "A", "B+", "B"]:
            g_trades = [t for t in self.trades if t.get("grade") == grade]
            if g_trades:
                g_wins = [t for t in g_trades if t["is_win"]]
                grade_stats[grade] = {
                    "trades": len(g_trades),
                    "win_rate": round(len(g_wins) / len(g_trades) * 100, 1),
                    "expectancy": round(
                        (len(g_wins)/len(g_trades)) *
                        (sum(t["pnl_pct"] for t in g_wins) / max(len(g_wins), 1)) -
                        (1 - len(g_wins)/len(g_trades)) *
                        abs(sum(t["pnl_pct"] for t in g_trades if not t["is_win"]) / max(len(g_trades)-len(g_wins), 1)),
                        3
                    )
                }

        # Valid flag
        is_valid = n >= MIN_TRADES_FOR_VALID
        edge_verdict = "NO DATA"
        if is_valid:
            if expectancy > 0.3 and profit_factor >= 1.3:
                edge_verdict = "✅ EDGE EXISTS"
            elif expectancy > 0:
                edge_verdict = "⚠️  MARGINAL EDGE"
            else:
                edge_verdict = "❌ NO EDGE"

        return {
            "total_trades": n,
            "wins": nw,
            "losses": nl,
            "win_rate": round(win_rate, 2),
            "avg_win_pct": round(avg_win, 3),
            "avg_loss_pct": round(avg_loss, 3),
            "avg_rr": round(avg_win / avg_loss, 2) if avg_loss > 0 else avg_win,
            "expectancy": round(expectancy, 4),
            "profit_factor": round(profit_factor, 3),
            "is_valid_sample": is_valid,
            "min_trades_needed": MIN_TRADES_FOR_VALID,
            "edge_verdict": edge_verdict,
            "grade_stats": grade_stats,
        }

    def get_summary(self) -> str:
        """Telegram-ready summary"""
        stats = self.get_stats()
        n = stats["total_trades"]
        if n == 0:
            return "📊 No trades recorded yet."

        validity = "✅ Valid sample" if stats["is_valid_sample"] else f"⚠️  Need {stats['min_trades_needed'] - n} more trades for valid data"

        lines = [
            f"📊 <b>Expectancy Report</b>",
            f"Trades: {n} ({stats['wins']}W / {stats['losses']}L)",
            f"Win Rate: {stats['win_rate']:.1f}%",
            f"Avg Win: +{stats['avg_win_pct']:.3f}% | Avg Loss: -{stats['avg_loss_pct']:.3f}%",
            f"RR (actual): {stats['avg_rr']:.2f}",
            f"<b>Expectancy: {stats['expectancy']:+.3f}%/trade</b>",
            f"Profit Factor: {stats['profit_factor']:.3f}",
            f"{validity}",
            f"<b>Verdict: {stats['edge_verdict']}</b>",
        ]

        if stats["grade_stats"]:
            lines.append("\nBy Grade:")
            for grade, gs in stats["grade_stats"].items():
                lines.append(
                    f"  {grade}: {gs['trades']} trades | "
                    f"WR={gs['win_rate']:.1f}% | E={gs['expectancy']:+.3f}%"
                )

        return "\n".join(lines)

    def should_stop_trading(self) -> tuple:
        """
        Returns (should_stop: bool, reason: str)
        After 20+ trades, if expectancy < -0.5% consistently → stop signal
        """
        stats = self.get_stats()
        if not stats["is_valid_sample"]:
            return False, "insufficient data"
        if stats["expectancy"] < -0.5 and stats["profit_factor"] < 0.8:
            return True, f"Expectancy {stats['expectancy']:+.3f}% < -0.5% over {stats['total_trades']} trades"
        return False, "OK"

    def _empty_stats(self) -> Dict:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "avg_rr": 0.0, "expectancy": 0.0, "profit_factor": 0.0,
            "is_valid_sample": False, "min_trades_needed": MIN_TRADES_FOR_VALID,
            "edge_verdict": "NO DATA", "grade_stats": {}
        }

    def reset(self):
        """Clear all trade history"""
        self.trades = []
        self._save()
        logger.info("📊 Expectancy tracker reset")
