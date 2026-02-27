"""
ARUNABHA ALGO BOT - Backtest Engine v4.2
=========================================

Points implemented:
Point 9  — Slippage + Commission model (Binance futures: 0.04% taker + 0.05% slippage)
Point 12 — Expectancy tracking (per trade update)
Point 13 — Monte Carlo simulation (bootstrap resampling, scipy-free)
Point 14 — Regime-specific performance tracking (STRONG vs MODERATE structure)
"""

import logging
import math
import random
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from filters.filter_orchestrator import FilterOrchestrator

logger = logging.getLogger(__name__)

# ✅ Point 9: Realistic cost model
TAKER_FEE_PCT = 0.04      # Binance futures taker fee per side
SLIPPAGE_PCT = 0.05       # Conservative slippage per side
ROUND_TRIP_COST = (TAKER_FEE_PCT + SLIPPAGE_PCT) * 2  # 0.18% total

COOLDOWN_CANDLES = 4
MAX_HOLD_CANDLES = 60
ATR_SL_MULT = 1.5
ATR_TP_MULT = 3.0
MIN_RR = 1.5


@dataclass
class BacktestResult:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_pnl_percent: float
    max_drawdown: float
    max_drawdown_percent: float
    profit_factor: float
    sharpe_ratio: float
    avg_rr: float
    avg_win: float
    avg_loss: float
    best_trade: float
    worst_trade: float
    trades: List[Dict]
    equity_curve: List[float]
    monthly_stats: Dict
    expectancy: float = 0.0           # Point 12
    regime_stats: Dict = field(default_factory=dict)  # Point 14
    total_costs_pct: float = 0.0      # Point 9


class BacktestEngine:
    """Backtest engine — lookahead bias fixed + realistic costs"""

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.peak_capital = initial_capital
        self.analyzer = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.filters = FilterOrchestrator()

    def run(
        self,
        df: pd.DataFrame,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> BacktestResult:
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]

        if len(df) < 50:
            logger.warning("Insufficient data for backtest")
            return self._empty_result()

        logger.info(f"Backtest: {symbol} | {len(df)} candles | {df.index[0].date()} → {df.index[-1].date()}")

        trades = []
        equity_curve = [self.initial_capital]
        self.capital = self.initial_capital
        self.peak_capital = self.initial_capital
        ohlcv_list = self._df_to_ohlcv(df)
        last_signal_idx = -COOLDOWN_CANDLES

        for i in range(50, len(ohlcv_list) - 1):
            if i - last_signal_idx < COOLDOWN_CANDLES:
                equity_curve.append(self.capital)
                continue

            signal = self._generate_backtest_signal(symbol, ohlcv_list[:i + 1])
            if signal:
                trade = self._execute_trade(signal, ohlcv_list[i + 1:])
                if trade:
                    trades.append(trade)
                    self.capital += trade["pnl_usd"]
                    if self.capital > self.peak_capital:
                        self.peak_capital = self.capital
                    last_signal_idx = i

            equity_curve.append(self.capital)

        result = self._calculate_statistics(trades, equity_curve)
        logger.info(
            f"Done: {result.total_trades} trades | WR={result.win_rate:.1f}% | "
            f"PF={result.profit_factor:.2f} | Return={result.total_pnl_percent:+.2f}% | "
            f"Expectancy={result.expectancy:+.3f}%/trade"
        )
        return result

    def _generate_backtest_signal(self, symbol: str, ohlcv: List) -> Optional[Dict]:
        if len(ohlcv) < 50:
            return None
        structure = self.structure.detect(ohlcv)
        if structure.strength == "WEAK":
            return None
        atr = self.analyzer.calculate_atr(ohlcv)
        if atr <= 0:
            return None
        p = ohlcv[-1][4]
        regime = "STRONG" if structure.choch_detected else "MODERATE"
        if structure.direction == "LONG":
            return {"direction": "LONG", "entry": p, "stop_loss": p - atr * ATR_SL_MULT,
                    "take_profit": p + atr * ATR_TP_MULT, "timestamp": ohlcv[-1][0],
                    "atr": atr, "structure_strength": structure.strength, "regime": regime}
        else:
            return {"direction": "SHORT", "entry": p, "stop_loss": p + atr * ATR_SL_MULT,
                    "take_profit": p - atr * ATR_TP_MULT, "timestamp": ohlcv[-1][0],
                    "atr": atr, "structure_strength": structure.strength, "regime": regime}

    def _execute_trade(self, signal: Dict, future_data: List) -> Optional[Dict]:
        if len(future_data) < 2:
            return None

        atr = signal.get("atr", 0)
        direction = signal["direction"]
        signal_price = signal["entry"]

        # ✅ Point 9: Realistic entry = next candle open + slippage
        raw_entry = float(future_data[0][1])
        if direction == "LONG":
            entry = raw_entry * (1 + SLIPPAGE_PCT / 100)
            sl = entry - atr * ATR_SL_MULT
            tp = entry + atr * ATR_TP_MULT
        else:
            entry = raw_entry * (1 - SLIPPAGE_PCT / 100)
            sl = entry + atr * ATR_SL_MULT
            tp = entry - atr * ATR_TP_MULT

        exit_price = None
        exit_idx = None
        pnl_pct = None

        for i, candle in enumerate(future_data):
            h, l = float(candle[2]), float(candle[3])
            if direction == "LONG":
                if h >= tp:
                    # ✅ Exit slippage on TP (you miss slightly)
                    ep = tp * (1 - SLIPPAGE_PCT / 100)
                    pnl_pct = (ep - entry) / entry * 100
                    exit_price, exit_idx = tp, i; break
                elif l <= sl:
                    ep = sl * (1 - SLIPPAGE_PCT / 100)
                    pnl_pct = (ep - entry) / entry * 100
                    exit_price, exit_idx = sl, i; break
            else:
                if l <= tp:
                    ep = tp * (1 + SLIPPAGE_PCT / 100)
                    pnl_pct = (entry - ep) / entry * 100
                    exit_price, exit_idx = tp, i; break
                elif h >= sl:
                    ep = sl * (1 + SLIPPAGE_PCT / 100)
                    pnl_pct = (entry - ep) / entry * 100
                    exit_price, exit_idx = sl, i; break

        if exit_price is None:
            j = min(MAX_HOLD_CANDLES, len(future_data) - 1)
            exit_price = float(future_data[j][4])
            exit_idx = j
            if direction == "LONG":
                pnl_pct = (exit_price * (1 - SLIPPAGE_PCT/100) - entry) / entry * 100
            else:
                pnl_pct = (entry - exit_price * (1 + SLIPPAGE_PCT/100)) / entry * 100

        # ✅ Point 9: Commission round trip
        pnl_pct -= TAKER_FEE_PCT * 2

        # Position size
        sl_dist = abs(entry - sl) / entry
        if sl_dist <= 0:
            return None
        position_size = (self.capital * 0.01) / sl_dist
        pnl_usd = position_size * (pnl_pct / 100)

        return {
            "entry_time": signal["timestamp"],
            "exit_time": future_data[exit_idx][0] if exit_idx is not None else 0,
            "direction": direction,
            "signal_price": signal_price,
            "entry": round(entry, 8),
            "exit": round(exit_price, 8),
            "sl": round(sl, 8),
            "tp": round(tp, 8),
            "pnl_pct": round(pnl_pct, 4),
            "pnl_usd": round(pnl_usd, 2),
            "commission_pct": round(TAKER_FEE_PCT * 2, 4),
            "bars_held": exit_idx or 0,
            "structure_strength": signal.get("structure_strength", "UNKNOWN"),
            "regime": signal.get("regime", "UNKNOWN"),
        }

    def _calculate_statistics(self, trades: List[Dict], equity_curve: List[float]) -> BacktestResult:
        if not trades:
            return self._empty_result()

        total = len(trades)
        wins = [t for t in trades if t["pnl_pct"] > 0]
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        win_rate = len(wins) / total * 100

        total_pnl = sum(t["pnl_usd"] for t in trades)
        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100

        peak = equity_curve[0]; max_dd = 0.0; max_dd_pct = 0.0
        for v in equity_curve:
            if v > peak: peak = v
            dd = peak - v; dd_pct = dd / peak * 100 if peak > 0 else 0
            if dd > max_dd: max_dd = dd; max_dd_pct = dd_pct

        gp = sum(t["pnl_usd"] for t in wins)
        gl = abs(sum(t["pnl_usd"] for t in losses))
        pf = gp / gl if gl > 0 else (gp if gp > 0 else 0.0)

        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] > 0:
                returns.append((equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1])
        sharpe = 0.0
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * math.sqrt(35040)

        avg_win = float(np.mean([t["pnl_pct"] for t in wins])) if wins else 0.0
        avg_loss = float(np.mean([abs(t["pnl_pct"]) for t in losses])) if losses else 0.0
        avg_rr = avg_win / avg_loss if avg_loss > 0 else avg_win

        # ✅ Point 12: Expectancy
        wr_d = len(wins) / total
        expectancy = (wr_d * avg_win) - ((1 - wr_d) * avg_loss)

        # ✅ Point 14: Regime stats
        regime_stats = {}
        for t in trades:
            r = t.get("regime", "UNKNOWN")
            if r not in regime_stats:
                regime_stats[r] = {"trades": 0, "wins": 0, "pnl": 0.0}
            regime_stats[r]["trades"] += 1
            regime_stats[r]["pnl"] += t["pnl_pct"]
            if t["pnl_pct"] > 0:
                regime_stats[r]["wins"] += 1
        for r in regime_stats:
            n = regime_stats[r]["trades"]
            regime_stats[r]["win_rate"] = round(regime_stats[r]["wins"] / n * 100, 1) if n > 0 else 0
            regime_stats[r]["avg_pnl"] = round(regime_stats[r]["pnl"] / n, 3) if n > 0 else 0

        avg_cost = sum(t.get("commission_pct", 0) for t in trades) / total

        monthly = {}
        for t in trades:
            try:
                month = datetime.fromtimestamp(t["exit_time"] / 1000).strftime("%Y-%m")
            except Exception:
                month = "unknown"
            if month not in monthly:
                monthly[month] = {"trades": 0, "pnl": 0.0, "wins": 0}
            monthly[month]["trades"] += 1
            monthly[month]["pnl"] += t["pnl_usd"]
            if t["pnl_pct"] > 0:
                monthly[month]["wins"] += 1
        for m in monthly:
            n = monthly[m]["trades"]
            monthly[m]["win_rate"] = round(monthly[m]["wins"] / n * 100, 1) if n > 0 else 0

        return BacktestResult(
            total_trades=total, winning_trades=len(wins), losing_trades=len(losses),
            win_rate=win_rate, total_pnl=total_pnl, total_pnl_percent=total_return,
            max_drawdown=max_dd, max_drawdown_percent=max_dd_pct,
            profit_factor=pf, sharpe_ratio=sharpe, avg_rr=avg_rr,
            avg_win=avg_win, avg_loss=avg_loss,
            best_trade=max(t["pnl_pct"] for t in trades),
            worst_trade=min(t["pnl_pct"] for t in trades),
            trades=trades, equity_curve=equity_curve, monthly_stats=monthly,
            expectancy=round(expectancy, 4), regime_stats=regime_stats,
            total_costs_pct=round(avg_cost, 4),
        )

    def _df_to_ohlcv(self, df: pd.DataFrame) -> List:
        return [[int(idx.timestamp() * 1000), float(r["open"]), float(r["high"]),
                 float(r["low"]), float(r["close"]), float(r["volume"])]
                for idx, r in df.iterrows()]

    def _empty_result(self) -> BacktestResult:
        return BacktestResult(
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
            total_pnl=0, total_pnl_percent=0, max_drawdown=0, max_drawdown_percent=0,
            profit_factor=0, sharpe_ratio=0, avg_rr=0, avg_win=0, avg_loss=0,
            best_trade=0, worst_trade=0, trades=[], equity_curve=[self.initial_capital],
            monthly_stats={}, expectancy=0.0, regime_stats={}, total_costs_pct=0.0
        )

    def print_summary(self, result: BacktestResult):
        print("\n" + "═"*65)
        print("  BACKTEST RESULTS v4.2 — Costs + Expectancy + Regime Stats")
        print(f"  Cost model: {TAKER_FEE_PCT*2:.2f}% commission + {SLIPPAGE_PCT*2:.2f}% slippage/round trip")
        print("═"*65)
        rows = [
            ("Total Trades", f"{result.total_trades}"),
            ("Win Rate", f"{result.win_rate:.1f}%"),
            ("Total Return", f"{result.total_pnl_percent:+.2f}%"),
            ("Profit Factor", f"{result.profit_factor:.3f}"),
            ("Sharpe Ratio", f"{result.sharpe_ratio:.3f}"),
            ("Expectancy/trade", f"{result.expectancy:+.3f}%"),
            ("Avg Cost/trade", f"{result.total_costs_pct:.3f}%"),
            ("Max Drawdown", f"{result.max_drawdown_percent:.2f}%"),
            ("Avg Win", f"{result.avg_win:+.3f}%"),
            ("Avg Loss", f"-{result.avg_loss:.3f}%"),
            ("Avg RR (actual)", f"{result.avg_rr:.2f}"),
            ("Best Trade", f"{result.best_trade:+.3f}%"),
            ("Worst Trade", f"{result.worst_trade:+.3f}%"),
        ]
        for label, val in rows:
            print(f"  {label:<30} {val:>30}")

        if result.regime_stats:
            print(f"\n  REGIME BREAKDOWN:")
            for regime, s in result.regime_stats.items():
                print(f"  {regime:<12} trades={s['trades']:>4} | WR={s['win_rate']:>5.1f}% | avg={s['avg_pnl']:>+6.3f}%")

        # Verdict
        pf = result.profit_factor
        if pf >= 1.5 and result.win_rate >= 45 and result.expectancy > 0:
            verdict = "✅ PROMISING — Paper trade করো আগে"
        elif pf >= 1.2:
            verdict = "⚠️  MARGINAL — আরো data দরকার"
        else:
            verdict = "❌ NO EDGE — Real money দিও না"
        print(f"\n  VERDICT: {verdict}")
        print("═"*65)


# ══════════════════════════════════════════════════════
# ✅ Point 13: Monte Carlo Simulation (scipy-free)
# ══════════════════════════════════════════════════════

class MonteCarloSimulator:
    """Bootstrap resampling — 1000 random sequences → worst-case drawdown"""

    def simulate(
        self,
        trades: List[Dict],
        num_simulations: int = 1000,
        confidence_level: float = 0.95
    ) -> Dict:
        if len(trades) < 10:
            return {"error": "Need at least 10 trades for Monte Carlo"}

        returns = [t["pnl_pct"] for t in trades if "pnl_pct" in t]
        if not returns:
            return {"error": "No returns found"}

        final_returns = []
        max_dds = []
        n = len(returns)

        for _ in range(num_simulations):
            sample = [random.choice(returns) for _ in range(n)]
            equity = [1.0]
            for r in sample:
                equity.append(equity[-1] * (1 + r / 100))
            final_returns.append((equity[-1] - 1) * 100)

            peak = equity[0]
            max_dd = 0.0
            for v in equity:
                if v > peak: peak = v
                dd = (peak - v) / peak * 100 if peak > 0 else 0
                if dd > max_dd: max_dd = dd
            max_dds.append(max_dd)

        final_returns.sort()
        var_idx = int((1 - confidence_level) * num_simulations)
        var = final_returns[var_idx]
        cvar_vals = [r for r in final_returns if r <= var]
        cvar = sum(cvar_vals) / len(cvar_vals) if cvar_vals else var

        return {
            "num_simulations": num_simulations,
            "mean_return": round(sum(final_returns) / len(final_returns), 2),
            "median_return": round(final_returns[len(final_returns)//2], 2),
            "var_95": round(var, 2),
            "cvar_95": round(cvar, 2),
            "prob_profit": round(sum(1 for r in final_returns if r > 0) / num_simulations * 100, 1),
            "worst_case": round(min(final_returns), 2),
            "best_case": round(max(final_returns), 2),
            "mean_max_drawdown": round(sum(max_dds) / len(max_dds), 2),
            "dd_95th_pct": round(sorted(max_dds)[int(0.95 * len(max_dds))], 2),
        }

    def print_summary(self, results: Dict):
        if "error" in results:
            print(f"Monte Carlo error: {results['error']}")
            return
        print("\n" + "═"*50)
        print("  MONTE CARLO RESULTS (1000 simulations)")
        print("═"*50)
        print(f"  Mean Return:           {results['mean_return']:>+9.2f}%")
        print(f"  VaR (95%):             {results['var_95']:>+9.2f}%")
        print(f"  CVaR (worst 5%):       {results['cvar_95']:>+9.2f}%")
        print(f"  Prob Profit:           {results['prob_profit']:>8.1f}%")
        print(f"  Mean Max Drawdown:     {results['mean_max_drawdown']:>8.2f}%")
        print(f"  95th DD percentile:    {results['dd_95th_pct']:>8.2f}%")
        print(f"  Worst case:            {results['worst_case']:>+9.2f}%")
        print("═"*50)
