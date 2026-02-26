"""
ARUNABHA ALGO BOT - Backtest Engine v4.2

CRITICAL FIX — LOOKAHEAD BIAS:
    আগের bug:
        i = current candle index
        signal entry = ohlcv_list[i][-1][4]  ← candle[i]-এর close
        execute_trade(ohlcv_list[i:])         ← same candle[i] থেকে check শুরু

        এর মানে: signal দেওয়া হচ্ছে candle[i]-এর close দেখে,
        কিন্তু TP/SL check হচ্ছে সেই একই candle[i]-এর high/low দিয়ে।
        Real trading-এ এটা সম্ভব নয় — close দেখার পরে সেই candle-এর
        high/low আর accessible নয়।

    Fix:
        execute_trade(ohlcv_list[i+1:])  ← NEXT candle থেকে execution শুরু
        entry price = next candle-এর open price (realistic)

ADDITIONAL FIXES:
- Cooldown: একটি signal দেওয়ার পর MIN_COOLDOWN_CANDLES candle skip করো
- avg_rr সঠিকভাবে calculate হচ্ছে (win/loss ratio, absolute pct নয়)
- Sharpe ratio annualization factor: candle timeframe অনুযায়ী
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from filters.filter_orchestrator import FilterOrchestrator

logger = logging.getLogger(__name__)

# Minimum candles to skip after a signal (cooldown)
MIN_COOLDOWN_CANDLES = 4   # 15m * 4 = 1 hour cooldown


@dataclass
class BacktestResult:
    """Backtest results"""
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


class BacktestEngine:
    """
    Historical backtesting engine — FIXED for production use
    """

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
        """
        Run backtest on historical data
        """
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]

        if len(df) < 50:
            logger.warning("Insufficient data for backtest")
            return self._empty_result()

        logger.info(f"Running backtest on {len(df)} candles from {df.index[0]} to {df.index[-1]}")

        trades = []
        equity_curve = [self.initial_capital]
        self.capital = self.initial_capital
        self.peak_capital = self.initial_capital

        ohlcv_list = self._df_to_ohlcv(df)

        # ✅ FIX: Track cooldown — skip N candles after a signal
        last_signal_candle = -MIN_COOLDOWN_CANDLES  # Allow signal from the start

        for i in range(50, len(ohlcv_list) - 1):  # -1 কারণ আমরা i+1 candle access করব
            # Cooldown check
            if i - last_signal_candle < MIN_COOLDOWN_CANDLES:
                equity_curve.append(self.capital)
                continue

            # ✅ FIX: Only use data up to and including candle[i] for signal
            # candle[i] just CLOSED — we can see its close price
            current_data = ohlcv_list[:i + 1]

            signal = self._generate_backtest_signal(symbol, current_data)

            if signal:
                # ✅ CRITICAL FIX: Execute from candle[i+1] onward
                # Entry = candle[i+1] open (next candle open = realistic entry)
                # আগে ছিল: ohlcv_list[i:] — same candle-এ TP/SL check = lookahead bias
                future_data = ohlcv_list[i + 1:]
                trade = self._execute_trade(signal, future_data)

                if trade:
                    trades.append(trade)
                    self.capital += trade['pnl_usd']
                    if self.capital > self.peak_capital:
                        self.peak_capital = self.capital
                    last_signal_candle = i

            equity_curve.append(self.capital)

        result = self._calculate_statistics(trades, equity_curve)
        logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"{result.win_rate:.1f}% win rate, "
            f"{result.total_pnl_percent:+.2f}% return"
        )

        return result

    def _generate_backtest_signal(
        self,
        symbol: str,
        ohlcv: List[List[float]]
    ) -> Optional[Dict]:
        """
        Generate signal for backtest

        NOTE: এটা intentionally simplified version।
        Live bot-এর full filter system (BTC regime, fear/greed, funding rate etc.)
        backtest-এ replicate করা হয়নি কারণ historical data সব সময় available নয়।
        এই backtest শুধু price action logic test করে।
        """
        if len(ohlcv) < 50:
            return None

        structure = self.structure.detect(ohlcv)

        # WEAK structure-এ signal নেই
        if structure.strength == "WEAK":
            return None

        atr = self.analyzer.calculate_atr(ohlcv)
        if atr <= 0:
            return None

        # ✅ Signal entry price = last closed candle close
        # কিন্তু actual execution হবে পরের candle-এর open-এ (execute_trade এ handle করা)
        signal_price = ohlcv[-1][4]
        signal_timestamp = ohlcv[-1][0]

        if structure.direction == "LONG":
            return {
                "direction": "LONG",
                "entry": signal_price,          # Signal price (reference only)
                "stop_loss": signal_price - (atr * 1.5),
                "take_profit": signal_price + (atr * 3.0),
                "timestamp": signal_timestamp,
                "atr": atr,
                "structure_strength": structure.strength
            }
        else:
            return {
                "direction": "SHORT",
                "entry": signal_price,
                "stop_loss": signal_price + (atr * 1.5),
                "take_profit": signal_price - (atr * 3.0),
                "timestamp": signal_timestamp,
                "atr": atr,
                "structure_strength": structure.strength
            }

    def _execute_trade(
        self,
        signal: Dict,
        future_data: List[List[float]]
    ) -> Optional[Dict]:
        """
        ✅ FIXED: Execute trade starting from NEXT candle open

        আগের lookahead bias:
            entry = signal candle-এর close
            execution check শুরু = same candle-এর high/low ← impossible in reality

        এখন:
            entry = future_data[0]-এর open (next candle open)
            SL/TP recalculate করা হচ্ছে new entry থেকে (ATR distance maintain)
            execution check শুরু = future_data[0] (same candle as entry = realistic)
        """
        if len(future_data) < 2:
            return None

        # ✅ Realistic entry = next candle open
        next_candle_open = float(future_data[0][1])  # index 1 = open price
        signal_price = signal["entry"]
        atr = signal.get("atr", 0)
        direction = signal["direction"]

        # Recalculate SL/TP from actual entry price
        if atr > 0:
            if direction == "LONG":
                entry = next_candle_open
                sl = entry - (atr * 1.5)
                tp = entry + (atr * 3.0)
            else:
                entry = next_candle_open
                sl = entry + (atr * 1.5)
                tp = entry - (atr * 3.0)
        else:
            # Fallback: scale SL/TP from signal price to new entry
            if direction == "LONG":
                sl_dist = signal_price - signal["stop_loss"]
                tp_dist = signal["take_profit"] - signal_price
                entry = next_candle_open
                sl = entry - sl_dist
                tp = entry + tp_dist
            else:
                sl_dist = signal["stop_loss"] - signal_price
                tp_dist = signal_price - signal["take_profit"]
                entry = next_candle_open
                sl = entry + sl_dist
                tp = entry - tp_dist

        # Check each future candle for TP/SL hit
        exit_price = None
        exit_time = None
        pnl_pct = None
        bars_held = 0

        for i, candle in enumerate(future_data):
            high = float(candle[2])
            low = float(candle[3])

            if direction == "LONG":
                if high >= tp:
                    exit_price = tp
                    exit_time = candle[0]
                    pnl_pct = (tp - entry) / entry * 100
                    bars_held = i + 1
                    break
                elif low <= sl:
                    exit_price = sl
                    exit_time = candle[0]
                    pnl_pct = (sl - entry) / entry * 100
                    bars_held = i + 1
                    break
            else:  # SHORT
                if low <= tp:
                    exit_price = tp
                    exit_time = candle[0]
                    pnl_pct = (entry - tp) / entry * 100
                    bars_held = i + 1
                    break
                elif high >= sl:
                    exit_price = sl
                    exit_time = candle[0]
                    pnl_pct = (entry - sl) / entry * 100
                    bars_held = i + 1
                    break

        # Max holding: 60 candles (~15 hours on 15m)
        if exit_price is None:
            max_hold = min(60, len(future_data) - 1)
            exit_price = float(future_data[max_hold][4])
            exit_time = future_data[max_hold][0]
            bars_held = max_hold
            if direction == "LONG":
                pnl_pct = (exit_price - entry) / entry * 100
            else:
                pnl_pct = (entry - exit_price) / entry * 100

        if pnl_pct is None:
            return None

        # Position size: 1% risk of current capital
        risk_pct = 1.0
        risk_amount = self.capital * (risk_pct / 100)
        sl_distance_pct = abs(entry - sl) / entry * 100
        if sl_distance_pct > 0:
            position_size = risk_amount / (sl_distance_pct / 100)
        else:
            position_size = self.capital * 0.01

        pnl_usd = position_size * (pnl_pct / 100)

        return {
            "entry_time": signal["timestamp"],
            "exit_time": exit_time,
            "direction": direction,
            "signal_price": signal_price,      # Original signal candle close
            "entry": round(entry, 8),          # Actual entry (next candle open)
            "exit": round(exit_price, 8),
            "sl": round(sl, 8),
            "tp": round(tp, 8),
            "pnl_pct": round(pnl_pct, 4),
            "pnl_usd": round(pnl_usd, 2),
            "bars_held": bars_held,
            "structure_strength": signal.get("structure_strength", "UNKNOWN")
        }

    def _calculate_statistics(
        self,
        trades: List[Dict],
        equity_curve: List[float]
    ) -> BacktestResult:
        """Calculate backtest statistics"""

        if not trades:
            return self._empty_result()

        total_trades = len(trades)
        winning_trades = len([t for t in trades if t['pnl_pct'] > 0])
        losing_trades = len([t for t in trades if t['pnl_pct'] <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        total_pnl = sum(t['pnl_usd'] for t in trades)
        total_pnl_percent = (total_pnl / self.initial_capital) * 100

        # Drawdown
        max_drawdown = 0.0
        max_drawdown_percent = 0.0
        peak = equity_curve[0]

        for value in equity_curve:
            if value > peak:
                peak = value
            dd = peak - value
            dd_percent = (dd / peak) * 100 if peak > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd
                max_drawdown_percent = dd_percent

        # Profit factor
        gross_profit = sum(t['pnl_usd'] for t in trades if t['pnl_usd'] > 0)
        gross_loss = abs(sum(t['pnl_usd'] for t in trades if t['pnl_usd'] < 0))
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = gross_profit
        else:
            profit_factor = 0.0

        # Sharpe ratio (annualized for 15m candles: 365*24*4 = 35040 candles/year)
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] > 0:
                returns.append((equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1])

        sharpe_ratio = 0.0
        if len(returns) > 1 and np.std(returns) > 0:
            annualization = np.sqrt(35040)  # 15m candles per year
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * annualization

        # ✅ FIXED avg_rr: actual win/loss ratio
        wins = [t['pnl_pct'] for t in trades if t['pnl_pct'] > 0]
        losses = [abs(t['pnl_pct']) for t in trades if t['pnl_pct'] < 0]
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        avg_rr = (avg_win / avg_loss) if avg_loss > 0 else avg_win

        best_trade = max(t['pnl_pct'] for t in trades) if trades else 0.0
        worst_trade = min(t['pnl_pct'] for t in trades) if trades else 0.0

        monthly_stats = self._calculate_monthly_stats(trades)

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_drawdown_percent,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            avg_rr=avg_rr,
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade=best_trade,
            worst_trade=worst_trade,
            trades=trades,
            equity_curve=equity_curve,
            monthly_stats=monthly_stats
        )

    def _calculate_monthly_stats(self, trades: List[Dict]) -> Dict:
        """Calculate monthly statistics"""
        monthly: Dict[str, Dict] = {}

        for trade in trades:
            try:
                month = datetime.fromtimestamp(trade['exit_time'] / 1000).strftime('%Y-%m')
            except Exception:
                month = "unknown"

            if month not in monthly:
                monthly[month] = {'trades': 0, 'pnl': 0.0, 'wins': 0}

            monthly[month]['trades'] += 1
            monthly[month]['pnl'] += trade['pnl_usd']
            if trade['pnl_pct'] > 0:
                monthly[month]['wins'] += 1

        for month in monthly:
            t = monthly[month]['trades']
            monthly[month]['win_rate'] = (monthly[month]['wins'] / t * 100) if t > 0 else 0

        return monthly

    def _df_to_ohlcv(self, df: pd.DataFrame) -> List[List[float]]:
        """Convert DataFrame to OHLCV list format"""
        ohlcv = []
        for idx, row in df.iterrows():
            ohlcv.append([
                int(idx.timestamp() * 1000),
                float(row['open']),
                float(row['high']),
                float(row['low']),
                float(row['close']),
                float(row['volume'])
            ])
        return ohlcv

    def _empty_result(self) -> BacktestResult:
        """Return empty result"""
        return BacktestResult(
            total_trades=0, winning_trades=0, losing_trades=0,
            win_rate=0, total_pnl=0, total_pnl_percent=0,
            max_drawdown=0, max_drawdown_percent=0,
            profit_factor=0, sharpe_ratio=0,
            avg_rr=0, avg_win=0, avg_loss=0,
            best_trade=0, worst_trade=0,
            trades=[], equity_curve=[self.initial_capital],
            monthly_stats={}
        )

    def print_summary(self, result: BacktestResult):
        """Print backtest summary"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS (v4.2 — Lookahead Bias Fixed)")
        print("="*60)
        print(f"Total Trades:    {result.total_trades}")
        print(f"Winning Trades:  {result.winning_trades}")
        print(f"Losing Trades:   {result.losing_trades}")
        print(f"Win Rate:        {result.win_rate:.2f}%")
        print(f"\nProfit & Loss:")
        print(f"  Total P&L:       ${result.total_pnl:,.2f}")
        print(f"  Total Return:    {result.total_pnl_percent:+.2f}%")
        print(f"  Profit Factor:   {result.profit_factor:.2f}")
        print(f"  Sharpe Ratio:    {result.sharpe_ratio:.2f}")
        print(f"\nRisk Metrics:")
        print(f"  Max Drawdown:    ${result.max_drawdown:,.2f}")
        print(f"  Max Drawdown %:  {result.max_drawdown_percent:.2f}%")
        print(f"  Avg RR (actual): {result.avg_rr:.2f}")
        print(f"\nTrade Stats:")
        print(f"  Avg Win:         {result.avg_win:+.2f}%")
        print(f"  Avg Loss:        -{result.avg_loss:.2f}%")
        print(f"  Best Trade:      {result.best_trade:+.2f}%")
        print(f"  Worst Trade:     {result.worst_trade:+.2f}%")
        print("="*60)
        print("\n⚠️  NOTE: Backtest uses simplified signal logic.")
        print("   Live bot has additional filters (BTC regime, fear/greed,")
        print("   funding rate etc.) which will reduce signal frequency.")
