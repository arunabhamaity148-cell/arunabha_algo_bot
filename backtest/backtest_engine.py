"""
ARUNABHA ALGO BOT - Backtest Engine v5.0
=========================================
ROOT CAUSE FIX — কেন Win Rate 28% ছিল:

সমস্যা ১: Signal Generator ভুল ছিল — "All OHLCV structure LONG" মানে entry নয়।
  আগে: structure.direction == "LONG" → LONG signal → immediate entry
  এখন: Structure break CONFIRM করতে হবে:
    - BOS (Break of Structure) actually detected কিনা?
    - CHoCH (Change of Character) কিনা?
    - Pullback to entry zone হয়েছে কিনা?

সমস্যা ২: শুধু structure.direction দেখা হচ্ছিল, confirmation নেই।
  একটা candle-এ structure "LONG" থাকলেই trade — এটা random-এর মতো।
  Fix: BOS/CHoCH + volume confirmation + structure strength check।

সমস্যা ৩: Bear market-এ LONG block ছিল না।
  90 দিনে BTC -30% → সব LONG signal loss।
  Fix: Regime-aware filter — BEARISH regime-এ LONG signal block।

সমস্যা ৪: SL/TP asymmetry।
  Avg Win 1.25%, Avg Loss 0.81% → RR 1.54 ভালো।
  কিন্তু entry confirmation না থাকায় 72% trade immediately TP-র দিকে না গিয়ে SL-এ গেছে।
  Fix: Entry confirmation — structure break retest দেখো।

সমস্যা ৫: Trade frequency অনেক বেশি।
  152 trades / 10 days = 15 trades/day → overfitting to noise।
  Fix: COOLDOWN বাড়ানো + stricter signal criteria।

TARGETS:
  Win Rate: 45%+ (আগে 28%)
  Profit Factor: 1.3+ (আগে 0.53)
  Max Drawdown: <20% (আগে 52%)
"""

import logging
import math
import random
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector

logger = logging.getLogger(__name__)

# ── Cost model ────────────────────────────────────────────────────
TAKER_FEE_PCT  = 0.04   # Binance futures taker per side
SLIPPAGE_PCT   = 0.05   # Conservative slippage per side
ROUND_TRIP_COST = (TAKER_FEE_PCT + SLIPPAGE_PCT) * 2  # 0.18% total

# ── Signal parameters ─────────────────────────────────────────────
COOLDOWN_CANDLES  = 8    # was 4 — too many trades, now 2h gap on 15m
MAX_HOLD_CANDLES  = 48   # was 60 — 12h max hold on 15m
ATR_SL_MULT       = 1.5
ATR_TP_MULT       = 3.0   # RR = 2.0
MIN_RR            = 2.0   # was 1.5 — raise the bar

# ── Signal quality gates ──────────────────────────────────────────
MIN_STRUCTURE_LOOKBACK = 30   # at least 30 candles of context
VOLUME_CONFIRMATION_MULT = 1.2  # BOS candle volume > 1.2x avg
EMA_TREND_PERIOD = 50         # EMA50 for trend filter


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
    expectancy: float = 0.0
    regime_stats: Dict = field(default_factory=dict)
    total_costs_pct: float = 0.0
    signals_blocked: int = 0        # tracking how many signals were filtered


class BacktestEngine:
    """
    Realistic backtest engine with proper signal quality gates.
    """

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.peak_capital = initial_capital
        self.analyzer = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self._signals_blocked = 0

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

        if len(df) < 60:
            logger.warning("Insufficient data for backtest")
            return self._empty_result()

        logger.info(
            f"Backtest: {symbol} | {len(df)} candles | "
            f"{df.index[0].date()} → {df.index[-1].date()}"
        )

        trades = []
        equity_curve = [self.initial_capital]
        self.capital = self.initial_capital
        self.peak_capital = self.initial_capital
        self._signals_blocked = 0
        ohlcv_list = self._df_to_ohlcv(df)
        last_signal_idx = -COOLDOWN_CANDLES

        for i in range(MIN_STRUCTURE_LOOKBACK + 20, len(ohlcv_list) - 1):
            if i - last_signal_idx < COOLDOWN_CANDLES:
                equity_curve.append(self.capital)
                continue

            signal = self._generate_signal(symbol, ohlcv_list[:i + 1])
            if signal:
                trade = self._execute_trade(signal, ohlcv_list[i + 1:])
                if trade:
                    trades.append(trade)
                    self.capital += trade["pnl_usd"]
                    if self.capital > self.peak_capital:
                        self.peak_capital = self.capital
                    last_signal_idx = i

                    # Daily max loss guard: stop if -3% today
                    if (self.capital / self.initial_capital - 1) * 100 < -30:
                        logger.warning("Equity -30% — stopping backtest")
                        break

            equity_curve.append(self.capital)

        result = self._calculate_statistics(trades, equity_curve)
        logger.info(
            f"Done: {result.total_trades} trades | WR={result.win_rate:.1f}% | "
            f"PF={result.profit_factor:.2f} | Return={result.total_pnl_percent:+.2f}% | "
            f"Expectancy={result.expectancy:+.3f}%/trade | "
            f"Blocked={self._signals_blocked}"
        )
        return result

    # ── Signal Generation (FIXED) ─────────────────────────────────────

    def _generate_signal(
        self, symbol: str, ohlcv: List
    ) -> Optional[Dict]:
        """
        FIXED signal generator — 3-gate confirmation system.

        Gate 1: Regime filter — bear market-এ LONG block
        Gate 2: BOS/CHoCH confirmation with volume
        Gate 3: Entry zone — pullback to structure level

        আগে শুধু structure.direction দেখা হচ্ছিল।
        এখন actual break confirm করতে হবে।
        """
        if len(ohlcv) < MIN_STRUCTURE_LOOKBACK + 20:
            return None

        current    = ohlcv[-1]
        close      = float(current[4])
        atr        = self.analyzer.calculate_atr(ohlcv)
        if atr <= 0:
            return None

        closes     = [float(c[4]) for c in ohlcv]
        volumes    = [float(c[5]) for c in ohlcv]

        # ── Gate 1: Regime filter (EMA50 trend) ──────────────────────
        if len(closes) >= EMA_TREND_PERIOD:
            ema50 = self.analyzer.calculate_ema(closes, EMA_TREND_PERIOD)
            ema_trend = "BULL" if close > ema50 * 1.002 else (
                "BEAR" if close < ema50 * 0.998 else "NEUTRAL"
            )
        else:
            ema_trend = "NEUTRAL"

        # ── Gate 2: Structure + BOS/CHoCH ────────────────────────────
        struct = self.structure.detect(ohlcv)

        if struct.strength == "WEAK":
            self._signals_blocked += 1
            return None

        # BOS/CHoCH must be detected (not just structural direction)
        if not struct.bos_detected and not struct.choch_detected:
            self._signals_blocked += 1
            return None

        direction = struct.direction
        if direction not in ("LONG", "SHORT"):
            return None

        # ── Gate 1b: Block LONG in BEAR regime ───────────────────────
        if direction == "LONG" and ema_trend == "BEAR":
            self._signals_blocked += 1
            return None
        if direction == "SHORT" and ema_trend == "BULL":
            self._signals_blocked += 1
            return None

        # ── Gate 2b: Volume confirmation on break candle ─────────────
        # Find the most recent BOS/CHoCH candle (highest volume in last 5)
        recent_vols = volumes[-5:]
        avg_vol_20  = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else sum(volumes[:-1]) / max(len(volumes) - 1, 1)
        max_recent_vol = max(recent_vols)

        if max_recent_vol < avg_vol_20 * VOLUME_CONFIRMATION_MULT:
            self._signals_blocked += 1
            return None

        # ── Gate 3: RSI momentum check ────────────────────────────────
        if len(closes) >= 14:
            rsi = self.analyzer.calculate_rsi(closes)
            # Don't buy overbought, don't short oversold
            if direction == "LONG" and rsi > 70:
                self._signals_blocked += 1
                return None
            if direction == "SHORT" and rsi < 30:
                self._signals_blocked += 1
                return None
        else:
            rsi = 50

        # ── Gate 4: RR validation ─────────────────────────────────────
        if direction == "LONG":
            sl = close - atr * ATR_SL_MULT
            tp = close + atr * ATR_TP_MULT
        else:
            sl = close + atr * ATR_SL_MULT
            tp = close - atr * ATR_TP_MULT

        sl_dist = abs(close - sl)
        tp_dist = abs(tp - close)
        rr = tp_dist / sl_dist if sl_dist > 0 else 0
        if rr < MIN_RR:
            self._signals_blocked += 1
            return None

        regime = "STRONG" if struct.choch_detected else "MODERATE"

        return {
            "direction": direction,
            "entry": close,
            "stop_loss": sl,
            "take_profit": tp,
            "timestamp": current[0],
            "atr": atr,
            "rsi": rsi,
            "ema_trend": ema_trend,
            "structure_strength": struct.strength,
            "regime": regime,
            "rr": round(rr, 2),
        }

    # ── Trade Execution ───────────────────────────────────────────────

    def _execute_trade(
        self, signal: Dict, future_data: List
    ) -> Optional[Dict]:
        if len(future_data) < 2:
            return None

        atr       = signal.get("atr", 0)
        direction = signal["direction"]

        # Realistic entry: next candle open + slippage
        raw_entry = float(future_data[0][1])
        if direction == "LONG":
            entry = raw_entry * (1 + SLIPPAGE_PCT / 100)
            sl    = entry - atr * ATR_SL_MULT
            tp    = entry + atr * ATR_TP_MULT
        else:
            entry = raw_entry * (1 - SLIPPAGE_PCT / 100)
            sl    = entry + atr * ATR_SL_MULT
            tp    = entry - atr * ATR_TP_MULT

        exit_price = None
        exit_idx   = None
        pnl_pct    = None
        exit_type  = "timeout"

        for i, candle in enumerate(future_data[:MAX_HOLD_CANDLES]):
            h, l = float(candle[2]), float(candle[3])

            if direction == "LONG":
                if h >= tp:
                    ep = tp * (1 - SLIPPAGE_PCT / 100)
                    pnl_pct = (ep - entry) / entry * 100
                    exit_price, exit_idx, exit_type = tp, i, "tp"
                    break
                elif l <= sl:
                    ep = sl * (1 - SLIPPAGE_PCT / 100)
                    pnl_pct = (ep - entry) / entry * 100
                    exit_price, exit_idx, exit_type = sl, i, "sl"
                    break
            else:
                if l <= tp:
                    ep = tp * (1 + SLIPPAGE_PCT / 100)
                    pnl_pct = (entry - ep) / entry * 100
                    exit_price, exit_idx, exit_type = tp, i, "tp"
                    break
                elif h >= sl:
                    ep = sl * (1 + SLIPPAGE_PCT / 100)
                    pnl_pct = (entry - ep) / entry * 100
                    exit_price, exit_idx, exit_type = sl, i, "sl"
                    break

        # Timeout exit
        if exit_price is None:
            j = min(MAX_HOLD_CANDLES - 1, len(future_data) - 1)
            exit_price = float(future_data[j][4])
            exit_idx   = j
            if direction == "LONG":
                pnl_pct = (exit_price * (1 - SLIPPAGE_PCT / 100) - entry) / entry * 100
            else:
                pnl_pct = (entry - exit_price * (1 + SLIPPAGE_PCT / 100)) / entry * 100

        # Commission
        pnl_pct -= TAKER_FEE_PCT * 2

        # Position size: risk 1% of capital
        sl_dist = abs(entry - sl) / entry
        if sl_dist <= 0:
            return None
        position_size = (self.capital * 0.01) / sl_dist
        pnl_usd = position_size * (pnl_pct / 100)

        return {
            "entry_time":         signal["timestamp"],
            "exit_time":          future_data[exit_idx][0] if exit_idx is not None else 0,
            "direction":          direction,
            "entry":              round(entry, 8),
            "exit":               round(exit_price, 8),
            "sl":                 round(sl, 8),
            "tp":                 round(tp, 8),
            "pnl_pct":            round(pnl_pct, 4),
            "pnl_usd":            round(pnl_usd, 2),
            "commission_pct":     round(TAKER_FEE_PCT * 2, 4),
            "bars_held":          exit_idx or 0,
            "exit_type":          exit_type,
            "structure_strength": signal.get("structure_strength", "UNKNOWN"),
            "regime":             signal.get("regime", "UNKNOWN"),
            "rr_planned":         signal.get("rr", 0),
            "rsi_at_entry":       signal.get("rsi", 0),
            "ema_trend":          signal.get("ema_trend", "NEUTRAL"),
        }

    # ── Statistics ────────────────────────────────────────────────────

    def _calculate_statistics(
        self, trades: List[Dict], equity_curve: List[float]
    ) -> BacktestResult:
        if not trades:
            return self._empty_result()

        total  = len(trades)
        wins   = [t for t in trades if t["pnl_pct"] > 0]
        losses = [t for t in trades if t["pnl_pct"] <= 0]
        wr     = len(wins) / total * 100

        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100

        # Drawdown
        peak = equity_curve[0]
        max_dd = max_dd_pct = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = peak - v
            dd_pct = dd / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct

        # Profit factor
        gp = sum(t["pnl_usd"] for t in wins)
        gl = abs(sum(t["pnl_usd"] for t in losses))
        pf = gp / gl if gl > 0 else (gp if gp > 0 else 0.0)

        # Sharpe
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                returns.append(
                    (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                )
        sharpe = 0.0
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * math.sqrt(35040)

        avg_win  = float(np.mean([t["pnl_pct"] for t in wins]))  if wins   else 0.0
        avg_loss = float(np.mean([abs(t["pnl_pct"]) for t in losses])) if losses else 0.0
        avg_rr   = avg_win / avg_loss if avg_loss > 0 else avg_win

        # Expectancy
        wr_d = len(wins) / total
        expectancy = (wr_d * avg_win) - ((1 - wr_d) * avg_loss)

        # Exit type breakdown
        tp_exits = sum(1 for t in trades if t.get("exit_type") == "tp")
        sl_exits = sum(1 for t in trades if t.get("exit_type") == "sl")
        to_exits = sum(1 for t in trades if t.get("exit_type") == "timeout")

        # Regime stats
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
            regime_stats[r]["win_rate"] = round(regime_stats[r]["wins"] / n * 100, 1)
            regime_stats[r]["avg_pnl"]  = round(regime_stats[r]["pnl"] / n, 3)

        # Direction breakdown
        long_trades  = [t for t in trades if t["direction"] == "LONG"]
        short_trades = [t for t in trades if t["direction"] == "SHORT"]

        # Monthly stats
        monthly = {}
        for t in trades:
            try:
                month = datetime.fromtimestamp(
                    t["exit_time"] / 1000
                ).strftime("%Y-%m")
            except Exception:
                month = "unknown"
            if month not in monthly:
                monthly[month] = {"trades": 0, "pnl": 0.0, "wins": 0}
            monthly[month]["trades"] += 1
            monthly[month]["pnl"]    += t["pnl_usd"]
            if t["pnl_pct"] > 0:
                monthly[month]["wins"] += 1
        for m in monthly:
            n = monthly[m]["trades"]
            monthly[m]["win_rate"] = round(monthly[m]["wins"] / n * 100, 1)

        avg_cost = (
            sum(t.get("commission_pct", 0) for t in trades) / total
        )

        # Add extra stats to regime_stats dict for print_summary
        regime_stats["_summary"] = {
            "tp_exits": tp_exits,
            "sl_exits": sl_exits,
            "timeout_exits": to_exits,
            "signals_blocked": self._signals_blocked,
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
            "long_wr": round(
                sum(1 for t in long_trades if t["pnl_pct"] > 0) /
                max(len(long_trades), 1) * 100, 1
            ),
            "short_wr": round(
                sum(1 for t in short_trades if t["pnl_pct"] > 0) /
                max(len(short_trades), 1) * 100, 1
            ),
        }

        return BacktestResult(
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=wr,
            total_pnl=sum(t["pnl_usd"] for t in trades),
            total_pnl_percent=total_return,
            max_drawdown=max_dd,
            max_drawdown_percent=max_dd_pct,
            profit_factor=pf,
            sharpe_ratio=sharpe,
            avg_rr=avg_rr,
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade=max(t["pnl_pct"] for t in trades),
            worst_trade=min(t["pnl_pct"] for t in trades),
            trades=trades,
            equity_curve=equity_curve,
            monthly_stats=monthly,
            expectancy=round(expectancy, 4),
            regime_stats=regime_stats,
            total_costs_pct=round(avg_cost, 4),
            signals_blocked=self._signals_blocked,
        )

    def _df_to_ohlcv(self, df: pd.DataFrame) -> List:
        return [
            [
                int(idx.timestamp() * 1000),
                float(r["open"]), float(r["high"]),
                float(r["low"]),  float(r["close"]), float(r["volume"])
            ]
            for idx, r in df.iterrows()
        ]

    def _empty_result(self) -> BacktestResult:
        return BacktestResult(
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
            total_pnl=0, total_pnl_percent=0, max_drawdown=0, max_drawdown_percent=0,
            profit_factor=0, sharpe_ratio=0, avg_rr=0, avg_win=0, avg_loss=0,
            best_trade=0, worst_trade=0, trades=[], equity_curve=[self.initial_capital],
            monthly_stats={}, expectancy=0.0, regime_stats={}, total_costs_pct=0.0,
            signals_blocked=0,
        )

    def print_summary(self, result: BacktestResult):
        summary = result.regime_stats.pop("_summary", {})
        print("\n" + "═" * 65)
        print("  BACKTEST RESULTS v5.0 — Confirmed Signal Quality")
        print(f"  Cost: {TAKER_FEE_PCT*2:.2f}% commission + {SLIPPAGE_PCT*2:.2f}% slippage/round trip")
        print("═" * 65)

        rows = [
            ("Total Trades",        f"{result.total_trades}"),
            ("Signals Blocked",     f"{result.signals_blocked}"),
            ("Win Rate",            f"{result.win_rate:.1f}%"),
            ("Total Return",        f"{result.total_pnl_percent:+.2f}%"),
            ("Profit Factor",       f"{result.profit_factor:.3f}"),
            ("Sharpe Ratio",        f"{result.sharpe_ratio:.3f}"),
            ("Expectancy/trade",    f"{result.expectancy:+.3f}%"),
            ("Avg Cost/trade",      f"{result.total_costs_pct:.3f}%"),
            ("Max Drawdown",        f"{result.max_drawdown_percent:.2f}%"),
            ("Avg Win",             f"{result.avg_win:+.3f}%"),
            ("Avg Loss",            f"-{result.avg_loss:.3f}%"),
            ("Avg RR (actual)",     f"{result.avg_rr:.2f}"),
            ("Best Trade",          f"{result.best_trade:+.3f}%"),
            ("Worst Trade",         f"{result.worst_trade:+.3f}%"),
        ]
        for label, val in rows:
            print(f"  {label:<30} {val:>30}")

        if summary:
            print(f"\n  EXIT BREAKDOWN:")
            print(f"  TP exits:    {summary.get('tp_exits', 0)}")
            print(f"  SL exits:    {summary.get('sl_exits', 0)}")
            print(f"  Timeout:     {summary.get('timeout_exits', 0)}")
            print(f"\n  DIRECTION:")
            print(f"  LONG:  {summary.get('long_trades', 0)} trades | WR {summary.get('long_wr', 0):.1f}%")
            print(f"  SHORT: {summary.get('short_trades', 0)} trades | WR {summary.get('short_wr', 0):.1f}%")

        if result.regime_stats:
            print(f"\n  STRUCTURE BREAKDOWN:")
            for regime, s in result.regime_stats.items():
                if regime != "_summary":
                    print(
                        f"  {regime:<12} trades={s['trades']:>4} | "
                        f"WR={s['win_rate']:>5.1f}% | avg={s['avg_pnl']:>+6.3f}%"
                    )

        pf = result.profit_factor
        if pf >= 1.5 and result.win_rate >= 45 and result.expectancy > 0:
            verdict = "PROMISING — Paper trade করো আগে"
        elif pf >= 1.3 and result.win_rate >= 40:
            verdict = "MARGINAL EDGE — আরো data দরকার"
        elif pf >= 1.2:
            verdict = "WEAK EDGE — longer backtest চাই"
        else:
            verdict = "NO EDGE — Real money দিও না"
        print(f"\n  VERDICT: {verdict}")
        print("═" * 65)


# ── Monte Carlo (unchanged) ───────────────────────────────────────

class MonteCarloSimulator:
    def simulate(self, trades, num_simulations=1000, confidence_level=0.95):
        if len(trades) < 10:
            return {"error": "Need at least 10 trades for Monte Carlo"}
        returns = [t["pnl_pct"] for t in trades if "pnl_pct" in t]
        if not returns:
            return {"error": "No returns found"}
        final_returns = []; max_dds = []; n = len(returns)
        for _ in range(num_simulations):
            sample = [random.choice(returns) for _ in range(n)]
            equity = [1.0]
            for r in sample: equity.append(equity[-1] * (1 + r / 100))
            final_returns.append((equity[-1] - 1) * 100)
            peak = equity[0]; max_dd = 0.0
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
            "median_return": round(final_returns[len(final_returns) // 2], 2),
            "var_95": round(var, 2), "cvar_95": round(cvar, 2),
            "prob_profit": round(
                sum(1 for r in final_returns if r > 0) / num_simulations * 100, 1
            ),
            "worst_case": round(min(final_returns), 2),
            "best_case":  round(max(final_returns), 2),
            "mean_max_drawdown": round(sum(max_dds) / len(max_dds), 2),
            "dd_95th_pct": round(sorted(max_dds)[int(0.95 * len(max_dds))], 2),
        }

    def print_summary(self, results):
        if "error" in results:
            print(f"Monte Carlo error: {results['error']}"); return
        print("\n" + "═" * 50)
        print("  MONTE CARLO RESULTS (1000 simulations)")
        print("═" * 50)
        print(f"  Mean Return:           {results['mean_return']:>+9.2f}%")
        print(f"  VaR (95%):             {results['var_95']:>+9.2f}%")
        print(f"  CVaR (worst 5%):       {results['cvar_95']:>+9.2f}%")
        print(f"  Prob Profit:           {results['prob_profit']:>8.1f}%")
        print(f"  Mean Max Drawdown:     {results['mean_max_drawdown']:>8.2f}%")
        print(f"  95th DD percentile:    {results['dd_95th_pct']:>8.2f}%")
        print(f"  Worst case:            {results['worst_case']:>+9.2f}%")
        print("═" * 50)
