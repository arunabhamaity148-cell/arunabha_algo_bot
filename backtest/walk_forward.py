"""
ARUNABHA ALGO BOT - Walk Forward Analysis v4.2
===============================================

Point 10 — Walk-forward validation:
    60% data train, 40% test — overfitting ধরা যাবে
    Out-of-sample result না দেখলে backtest misleading

Point 8  — Market hours filter integrated in backtest logic
Point 16 — Regime-aware window analysis (STRONG vs MODERATE separately tracked)
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime

from backtest.backtest_engine import BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


class WalkForwardAnalyzer:
    """
    Walk-forward analysis — validates strategy robustness.

    Method:
    - Split data into rolling windows
    - Train on first N days, test on next M days
    - Move forward by step_size days
    - Compare train vs test performance

    If test performance closely tracks train → strategy is robust (not overfit)
    If test performance drops sharply → strategy is overfit to train data
    """

    def __init__(self, engine: BacktestEngine):
        self.engine = engine
        self.results: List[Dict] = []

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str,
        train_pct: float = 0.6,   # 60% train, 40% test
        min_window_days: int = 30, # minimum data per window
        step_size: int = 15        # roll forward every 15 days
    ) -> Dict[str, Any]:
        """
        ✅ Point 10: Walk-forward with percentage split

        train_pct=0.6 মানে প্রতিটা window-এ:
          - প্রথম 60% candles = train
          - বাকি 40% candles = out-of-sample test

        Rolling forward by step_size → multiple windows → aggregate stats
        """
        if len(df) < min_window_days * 2 * 96:  # ~2 months of 15m data
            logger.warning("Insufficient data for walk-forward — need at least 2 months")
            return self._insufficient_data_result()

        logger.info(
            f"Walk-forward: {symbol} | {len(df)} candles | "
            f"train={train_pct*100:.0f}% test={(1-train_pct)*100:.0f}% | "
            f"step={step_size}d"
        )

        # Candles per day (15m = 96/day)
        cpd = 96
        step_candles = step_size * cpd
        window_candles = min_window_days * cpd
        total_candles = len(df)

        results = []
        start_idx = 0

        while start_idx + window_candles * 2 <= total_candles:
            end_idx = min(start_idx + window_candles * 3, total_candles)
            window_df = df.iloc[start_idx:end_idx]

            split_idx = int(len(window_df) * train_pct)
            if split_idx < 50 or (len(window_df) - split_idx) < 50:
                start_idx += step_candles
                continue

            train_df = window_df.iloc[:split_idx]
            test_df  = window_df.iloc[split_idx:]

            train_start = train_df.index[0].strftime("%Y-%m-%d")
            train_end   = train_df.index[-1].strftime("%Y-%m-%d")
            test_start  = test_df.index[0].strftime("%Y-%m-%d")
            test_end    = test_df.index[-1].strftime("%Y-%m-%d")

            logger.debug(
                f"Window {len(results)+1}: "
                f"train {train_start}→{train_end} | test {test_start}→{test_end}"
            )

            try:
                train_r = self.engine.run(train_df, symbol)
                test_r  = self.engine.run(test_df, symbol)

                results.append({
                    "window": len(results) + 1,
                    "train_start": train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                    "train_trades": train_r.total_trades,
                    "train_win_rate": train_r.win_rate,
                    "train_return": train_r.total_pnl_percent,
                    "train_pf": train_r.profit_factor,
                    "train_sharpe": train_r.sharpe_ratio,
                    "train_expectancy": train_r.expectancy,
                    "test_trades": test_r.total_trades,
                    "test_win_rate": test_r.win_rate,
                    "test_return": test_r.total_pnl_percent,
                    "test_pf": test_r.profit_factor,
                    "test_sharpe": test_r.sharpe_ratio,
                    "test_expectancy": test_r.expectancy,
                    # Point 16: regime stats from test window
                    "test_regime_stats": test_r.regime_stats,
                })
            except Exception as e:
                logger.warning(f"Walk-forward window {len(results)+1} failed: {e}")

            start_idx += step_candles

        if not results:
            return self._insufficient_data_result()

        self.results = results
        stats = self._calculate_stats(results)
        robust = self._is_robust(stats)

        return {
            "windows": results,
            "statistics": stats,
            "is_robust": robust,
            "verdict": self._get_verdict(stats, robust),
        }

    def _calculate_stats(self, results: List[Dict]) -> Dict:
        train_returns  = [r["train_return"] for r in results]
        test_returns   = [r["test_return"] for r in results]
        train_pfs      = [r["train_pf"] for r in results]
        test_pfs       = [r["test_pf"] for r in results]
        train_sharpes  = [r["train_sharpe"] for r in results]
        test_sharpes   = [r["test_sharpe"] for r in results]
        train_exp      = [r["train_expectancy"] for r in results]
        test_exp       = [r["test_expectancy"] for r in results]

        return {
            "num_windows": len(results),
            "avg_train_return":    round(float(np.mean(train_returns)), 2),
            "avg_test_return":     round(float(np.mean(test_returns)), 2),
            "avg_train_pf":        round(float(np.mean(train_pfs)), 3),
            "avg_test_pf":         round(float(np.mean(test_pfs)), 3),
            "avg_train_sharpe":    round(float(np.mean(train_sharpes)), 3),
            "avg_test_sharpe":     round(float(np.mean(test_sharpes)), 3),
            "avg_train_expectancy":round(float(np.mean(train_exp)), 4),
            "avg_test_expectancy": round(float(np.mean(test_exp)), 4),
            "return_decay":        round(float(np.mean(test_returns)) - float(np.mean(train_returns)), 2),
            "pf_decay":            round(float(np.mean(test_pfs)) - float(np.mean(train_pfs)), 3),
            "positive_train_ratio":round(sum(1 for r in train_returns if r > 0) / len(results) * 100, 1),
            "positive_test_ratio": round(sum(1 for r in test_returns if r > 0) / len(results) * 100, 1),
            "best_test_return":    round(max(test_returns), 2),
            "worst_test_return":   round(min(test_returns), 2),
        }

    def _is_robust(self, stats: Dict) -> bool:
        """
        Strategy robust হলে:
        1. Test windows-এ average return > 0
        2. Test windows-এ 60%+ profitable
        3. Return decay খুব বেশি না (< 10%)
        4. Test PF > 1.0
        5. Test expectancy > 0
        """
        return all([
            stats.get("avg_test_return", -100) > 0,
            stats.get("positive_test_ratio", 0) >= 60,
            stats.get("return_decay", -100) > -10,
            stats.get("avg_test_pf", 0) > 1.0,
            stats.get("avg_test_expectancy", -1) > 0,
        ])

    def _get_verdict(self, stats: Dict, robust: bool) -> str:
        if robust:
            return (
                f"✅ ROBUST — Test windows avg return: {stats['avg_test_return']:+.2f}% | "
                f"PF: {stats['avg_test_pf']:.2f} | "
                f"Profitable windows: {stats['positive_test_ratio']:.0f}%"
            )
        elif stats.get("avg_test_return", -100) > 0:
            return (
                f"⚠️  MARGINAL — Return decays {stats['return_decay']:+.2f}% train→test | "
                f"Need more windows"
            )
        else:
            return (
                f"❌ NOT ROBUST — Test avg: {stats['avg_test_return']:+.2f}% | "
                f"Likely overfit to train data"
            )

    def _insufficient_data_result(self) -> Dict:
        return {
            "windows": [],
            "statistics": {},
            "is_robust": False,
            "verdict": "❌ Insufficient data — need at least 2 months of 15m data (≈5760 candles)"
        }

    def print_summary(self):
        if not self.results:
            print("No walk-forward results")
            return

        stats = self._calculate_stats(self.results)
        robust = self._is_robust(stats)

        print("\n" + "═"*65)
        print("  WALK-FORWARD ANALYSIS v4.2")
        print("  60% Train | 40% Test (Out-of-Sample)")
        print("═"*65)
        print(f"  Windows analyzed:    {stats['num_windows']}")
        print()
        print(f"  {'Metric':<25} {'TRAIN':>15} {'TEST':>15}")
        print("  " + "─"*55)
        rows = [
            ("Avg Return", f"{stats['avg_train_return']:>+14.2f}%", f"{stats['avg_test_return']:>+14.2f}%"),
            ("Avg Profit Factor", f"{stats['avg_train_pf']:>15.3f}", f"{stats['avg_test_pf']:>15.3f}"),
            ("Avg Sharpe", f"{stats['avg_train_sharpe']:>15.3f}", f"{stats['avg_test_sharpe']:>15.3f}"),
            ("Avg Expectancy", f"{stats['avg_train_expectancy']:>+14.4f}%", f"{stats['avg_test_expectancy']:>+14.4f}%"),
            ("Profitable Windows", f"{stats['positive_train_ratio']:>14.1f}%", f"{stats['positive_test_ratio']:>14.1f}%"),
        ]
        for label, train_val, test_val in rows:
            print(f"  {label:<25} {train_val:>15} {test_val:>15}")

        print()
        print(f"  Return decay (train→test): {stats['return_decay']:+.2f}%")
        print(f"  PF decay (train→test):     {stats['pf_decay']:+.3f}")
        print()
        print(f"  Strategy robust: {'✅ YES' if robust else '❌ NO'}")
        print(f"  Verdict: {self._get_verdict(stats, robust)}")
        print("═"*65)

        # Per-window table
        print(f"\n  {'Win':<5} {'Train Ret':>10} {'Test Ret':>10} {'Train PF':>9} {'Test PF':>9}")
        print("  " + "─"*47)
        for r in self.results:
            icon = "✅" if r["test_return"] > 0 else "❌"
            print(
                f"  {icon} {r['window']:<4} "
                f"{r['train_return']:>+9.2f}% {r['test_return']:>+9.2f}% "
                f"{r['train_pf']:>9.2f} {r['test_pf']:>9.2f}"
            )
        print()
