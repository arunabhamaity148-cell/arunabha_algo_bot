"""
ARUNABHA ALGO BOT - Backtest Engine
Historical backtesting of strategies
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
    Historical backtesting engine
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
        # Filter date range
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
        
        if len(df) < 50:
            logger.warning("Insufficient data for backtest")
            return self._empty_result()
        
        logger.info(f"Running backtest on {len(df)} candles from {df.index[0]} to {df.index[-1]}")
        
        # Initialize tracking
        trades = []
        equity_curve = [self.initial_capital]
        self.capital = self.initial_capital
        self.peak_capital = self.initial_capital
        
        # Convert to list format for compatibility
        ohlcv_list = self._df_to_ohlcv(df)
        
        # Run through each candle
        for i in range(50, len(ohlcv_list)):  # Start after enough data
            current_data = ohlcv_list[:i+1]
            
            # Generate signal (simplified for backtest)
            signal = self._generate_backtest_signal(symbol, current_data)
            
            if signal:
                # Execute trade
                trade = self._execute_trade(signal, ohlcv_list[i:])
                if trade:
                    trades.append(trade)
                    
                    # Update capital
                    self.capital += trade['pnl_usd']
                    if self.capital > self.peak_capital:
                        self.peak_capital = self.capital
            
            equity_curve.append(self.capital)
        
        # Calculate statistics
        result = self._calculate_statistics(trades, equity_curve)
        
        logger.info(f"Backtest complete: {result.total_trades} trades, {result.win_rate:.1f}% win rate, {result.total_pnl_percent:+.2f}% return")
        
        return result
    
    def _generate_backtest_signal(self, symbol: str, ohlcv: List[List[float]]) -> Optional[Dict]:
        """Generate signal for backtest (simplified)"""
        
        if len(ohlcv) < 50:
            return None
        
        # Simplified structure detection
        structure = self.structure.detect(ohlcv)
        
        # Only trade on clear structure
        if structure.strength == "WEAK":
            return None
        
        # Calculate ATR for levels
        atr = self.analyzer.calculate_atr(ohlcv)
        current_price = ohlcv[-1][4]
        
        # Generate signal
        if structure.direction == "LONG":
            return {
                "direction": "LONG",
                "entry": current_price,
                "stop_loss": current_price - (atr * 1.5),
                "take_profit": current_price + (atr * 3.0),
                "timestamp": ohlcv[-1][0]
            }
        else:
            return {
                "direction": "SHORT",
                "entry": current_price,
                "stop_loss": current_price + (atr * 1.5),
                "take_profit": current_price - (atr * 3.0),
                "timestamp": ohlcv[-1][0]
            }
    
    def _execute_trade(self, signal: Dict, future_data: List[List[float]]) -> Optional[Dict]:
        """Execute a trade on future data"""
        
        if len(future_data) < 5:
            return None
        
        entry = signal['entry']
        sl = signal['stop_loss']
        tp = signal['take_profit']
        direction = signal['direction']
        
        # Check each future candle
        for i, candle in enumerate(future_data):
            high = candle[2]
            low = candle[3]
            close = candle[4]
            
            if direction == "LONG":
                # Check take profit
                if high >= tp:
                    exit_price = tp
                    exit_time = candle[0]
                    pnl_pct = (tp - entry) / entry * 100
                    break
                # Check stop loss
                elif low <= sl:
                    exit_price = sl
                    exit_time = candle[0]
                    pnl_pct = (sl - entry) / entry * 100
                    break
            else:  # SHORT
                # Check take profit
                if low <= tp:
                    exit_price = tp
                    exit_time = candle[0]
                    pnl_pct = (entry - tp) / entry * 100
                    break
                # Check stop loss
                elif high >= sl:
                    exit_price = sl
                    exit_time = candle[0]
                    pnl_pct = (entry - sl) / entry * 100
                    break
        else:
            # Exit at last candle
            exit_price = future_data[-1][4]
            exit_time = future_data[-1][0]
            if direction == "LONG":
                pnl_pct = (exit_price - entry) / entry * 100
            else:
                pnl_pct = (entry - exit_price) / entry * 100
        
        # Calculate P&L in USD
        position_size = self.capital * 0.01  # 1% risk
        pnl_usd = position_size * (pnl_pct / 100)
        
        return {
            "entry_time": signal['timestamp'],
            "exit_time": exit_time,
            "direction": direction,
            "entry": entry,
            "exit": exit_price,
            "pnl_pct": pnl_pct,
            "pnl_usd": pnl_usd,
            "bars_held": i + 1
        }
    
    def _calculate_statistics(
        self,
        trades: List[Dict],
        equity_curve: List[float]
    ) -> BacktestResult:
        """Calculate backtest statistics"""
        
        if not trades:
            return self._empty_result()
        
        # Basic counts
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t['pnl_pct'] > 0])
        losing_trades = len([t for t in trades if t['pnl_pct'] <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # P&L
        total_pnl = sum(t['pnl_usd'] for t in trades)
        total_pnl_percent = (total_pnl / self.initial_capital) * 100
        
        # Drawdown
        max_drawdown = 0
        max_drawdown_percent = 0
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
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit if gross_profit > 0 else 0
        
        # Returns for Sharpe
        returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1] 
                   for i in range(1, len(equity_curve))]
        
        sharpe_ratio = 0
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(365)
        
        # Average trade stats
        avg_rr = np.mean([abs(t['pnl_pct']) for t in trades]) if trades else 0
        avg_win = np.mean([t['pnl_pct'] for t in trades if t['pnl_pct'] > 0]) if winning_trades > 0 else 0
        avg_loss = np.mean([t['pnl_pct'] for t in trades if t['pnl_pct'] < 0]) if losing_trades > 0 else 0
        
        # Best/worst
        best_trade = max(t['pnl_pct'] for t in trades) if trades else 0
        worst_trade = min(t['pnl_pct'] for t in trades) if trades else 0
        
        # Monthly stats
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
        
        monthly = {}
        
        for trade in trades:
            month = datetime.fromtimestamp(trade['exit_time'] / 1000).strftime('%Y-%m')
            
            if month not in monthly:
                monthly[month] = {
                    'trades': 0,
                    'pnl': 0,
                    'wins': 0
                }
            
            monthly[month]['trades'] += 1
            monthly[month]['pnl'] += trade['pnl_usd']
            if trade['pnl_pct'] > 0:
                monthly[month]['wins'] += 1
        
        # Calculate win rates
        for month in monthly:
            monthly[month]['win_rate'] = (monthly[month]['wins'] / monthly[month]['trades'] * 100)
        
        return monthly
    
    def _df_to_ohlcv(self, df: pd.DataFrame) -> List[List[float]]:
        """Convert DataFrame to OHLCV list format"""
        ohlcv = []
        
        for idx, row in df.iterrows():
            ohlcv.append([
                int(idx.timestamp() * 1000),  # timestamp in ms
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
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            total_pnl=0,
            total_pnl_percent=0,
            max_drawdown=0,
            max_drawdown_percent=0,
            profit_factor=0,
            sharpe_ratio=0,
            avg_rr=0,
            avg_win=0,
            avg_loss=0,
            best_trade=0,
            worst_trade=0,
            trades=[],
            equity_curve=[self.initial_capital],
            monthly_stats={}
        )
    
    def print_summary(self, result: BacktestResult):
        """Print backtest summary"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        print(f"Total Trades: {result.total_trades}")
        print(f"Winning Trades: {result.winning_trades}")
        print(f"Losing Trades: {result.losing_trades}")
        print(f"Win Rate: {result.win_rate:.2f}%")
        print(f"\nProfit & Loss:")
        print(f"  Total P&L: ${result.total_pnl:,.2f}")
        print(f"  Total Return: {result.total_pnl_percent:+.2f}%")
        print(f"  Profit Factor: {result.profit_factor:.2f}")
        print(f"  Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"\nRisk Metrics:")
        print(f"  Max Drawdown: ${result.max_drawdown:,.2f}")
        print(f"  Max Drawdown %: {result.max_drawdown_percent:.2f}%")
        print(f"  Avg RR: {result.avg_rr:.2f}")
        print(f"\nTrade Stats:")
        print(f"  Avg Win: {result.avg_win:+.2f}%")
        print(f"  Avg Loss: {result.avg_loss:+.2f}%")
        print(f"  Best Trade: {result.best_trade:+.2f}%")
        print(f"  Worst Trade: {result.worst_trade:+.2f}%")
        print("="*60)
