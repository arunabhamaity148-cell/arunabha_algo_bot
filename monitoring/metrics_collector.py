"""
ARUNABHA ALGO BOT - Metrics Collector
Collects and tracks performance metrics
"""

import logging
import statistics
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and analyzes bot performance metrics
    """
    
    def __init__(self, engine):
        self.engine = engine
        self.start_time = datetime.now()
        
        # Metrics storage
        self.signals_generated: List[Dict] = []
        self.trades_completed: List[Dict] = []
        self.errors: List[Dict] = []
        self.performance_snapshots: deque = deque(maxlen=100)
        
        # Running totals
        self.total_signals = 0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.total_volume = 0.0
        
    async def record_signal(self, signal: Dict):
        """Record a generated signal"""
        self.signals_generated.append({
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.get("symbol"),
            "direction": signal.get("direction"),
            "score": signal.get("score"),
            "grade": signal.get("grade"),
            "confidence": signal.get("confidence")
        })
        
        self.total_signals += 1
        
        # Trim if too many
        if len(self.signals_generated) > 1000:
            self.signals_generated = self.signals_generated[-1000:]
    
    async def record_trade(self, trade_result: Dict):
        """Record a completed trade"""
        pnl = trade_result.get("pnl_pct", 0)
        
        self.trades_completed.append({
            "timestamp": datetime.now().isoformat(),
            "symbol": trade_result.get("symbol"),
            "direction": trade_result.get("direction"),
            "entry": trade_result.get("entry"),
            "exit": trade_result.get("exit"),
            "pnl_pct": pnl,
            "pnl_usd": trade_result.get("pnl_usd", 0),
            "rr_ratio": trade_result.get("rr_ratio", 0),
            "reason": trade_result.get("reason")
        })
        
        self.total_trades += 1
        self.total_pnl += pnl
        
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        # Trim if too many
        if len(self.trades_completed) > 1000:
            self.trades_completed = self.trades_completed[-1000:]
    
    async def record_error(self, error_type: str, message: str):
        """Record an error"""
        self.errors.append({
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "message": message
        })
        
        # Trim if too many
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
    
    def take_snapshot(self):
        """Take a performance snapshot"""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "total_signals": self.total_signals,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "total_pnl": self.total_pnl,
            "win_rate": self.get_win_rate(),
            "avg_rr": self.get_avg_rr(),
            "profit_factor": self.get_profit_factor()
        }
        
        self.performance_snapshots.append(snapshot)
    
    def get_win_rate(self, period: Optional[str] = None) -> float:
        """Calculate win rate"""
        trades = self._get_trades_by_period(period) if period else self.trades_completed
        
        if not trades:
            return 0.0
        
        wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
        return (wins / len(trades)) * 100
    
    def get_avg_rr(self, period: Optional[str] = None) -> float:
        """Calculate average RR ratio"""
        trades = self._get_trades_by_period(period) if period else self.trades_completed
        
        if not trades:
            return 0.0
        
        rr_sum = sum(t.get("rr_ratio", 0) for t in trades)
        return rr_sum / len(trades)
    
    def get_profit_factor(self, period: Optional[str] = None) -> float:
        """Calculate profit factor"""
        trades = self._get_trades_by_period(period) if period else self.trades_completed
        
        if not trades:
            return 0.0
        
        gross_profit = sum(t.get("pnl_pct", 0) for t in trades if t.get("pnl_pct", 0) > 0)
        gross_loss = abs(sum(t.get("pnl_pct", 0) for t in trades if t.get("pnl_pct", 0) < 0))
        
        return gross_profit / gross_loss if gross_loss > 0 else gross_profit if gross_profit > 0 else 0
    
    def get_sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio"""
        if len(self.trades_completed) < 2:
            return 0.0
        
        returns = [t.get("pnl_pct", 0) for t in self.trades_completed]
        
        if not returns:
            return 0.0
        
        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 1
        
        if std_return == 0:
            return 0.0
        
        # Annualized Sharpe (assuming 252 trading days, ~3 trades per day)
        trades_per_year = 3 * 252
        sharpe = (avg_return / std_return) * (trades_per_year ** 0.5)
        
        return sharpe
    
    def get_max_drawdown(self) -> float:
        """Calculate maximum drawdown"""
        if not self.trades_completed:
            return 0.0
        
        cumulative = 0
        peak = 0
        max_dd = 0
        
        for trade in self.trades_completed:
            cumulative += trade.get("pnl_pct", 0)
            
            if cumulative > peak:
                peak = cumulative
            
            dd = (peak - cumulative) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return max_dd * 100
    
    def get_best_trade(self) -> Dict:
        """Get best trade"""
        if not self.trades_completed:
            return {}
        
        return max(self.trades_completed, key=lambda x: x.get("pnl_pct", 0))
    
    def get_worst_trade(self) -> Dict:
        """Get worst trade"""
        if not self.trades_completed:
            return {}
        
        return min(self.trades_completed, key=lambda x: x.get("pnl_pct", 0))
    
    def _get_trades_by_period(self, period: str) -> List[Dict]:
        """Get trades for specific period"""
        now = datetime.now()
        
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            return self.trades_completed
        
        return [
            t for t in self.trades_completed
            if datetime.fromisoformat(t["timestamp"]) >= start
        ]
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics"""
        return {
            "summary": {
                "total_signals": self.total_signals,
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "total_pnl": round(self.total_pnl, 2),
                "win_rate": round(self.get_win_rate(), 2),
                "avg_rr": round(self.get_avg_rr(), 2),
                "profit_factor": round(self.get_profit_factor(), 2),
                "sharpe_ratio": round(self.get_sharpe_ratio(), 2),
                "max_drawdown": round(self.get_max_drawdown(), 2)
            },
            "today": {
                "trades": len(self._get_trades_by_period("today")),
                "win_rate": round(self.get_win_rate("today"), 2),
                "pnl": round(sum(t.get("pnl_pct", 0) for t in self._get_trades_by_period("today")), 2)
            },
            "week": {
                "trades": len(self._get_trades_by_period("week")),
                "win_rate": round(self.get_win_rate("week"), 2),
                "pnl": round(sum(t.get("pnl_pct", 0) for t in self._get_trades_by_period("week")), 2)
            },
            "best_trade": self.get_best_trade(),
            "worst_trade": self.get_worst_trade(),
            "uptime": str(datetime.now() - self.start_time).split('.')[0]
        }
