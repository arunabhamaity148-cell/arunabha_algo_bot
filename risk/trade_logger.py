"""
ARUNABHA ALGO BOT - Trade Logger
Logs all trades for analysis and reporting
"""

import logging
import json
import csv
from typing import Dict, List, Optional
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeLogger:
    """
    Logs all trades to file for later analysis
    """
    
    def __init__(self, log_dir: str = "trade_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        self.trades: List[Dict] = []
        self.current_file = self.log_dir / f"trades_{date.today().isoformat()}.csv"
        
        # Initialize CSV file
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers"""
        if not self.current_file.exists():
            headers = [
                "timestamp", "symbol", "direction", "entry", "exit",
                "stop_loss", "take_profit", "position_usd", "pnl_pct",
                "pnl_usd", "rr_ratio", "market_type", "grade",
                "filters_passed", "score", "reason"
            ]
            
            with open(self.current_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
    
    def log_trade(self, trade_data: Dict):
        """
        Log a trade
        """
        # Add timestamp
        if "timestamp" not in trade_data:
            trade_data["timestamp"] = datetime.now().isoformat()
        
        # Store in memory
        self.trades.append(trade_data)
        
        # Write to CSV
        self._write_to_csv(trade_data)
        
        # Also write to JSON log
        self._write_to_json(trade_data)
        
        logger.debug(f"Trade logged: {trade_data.get('symbol')} @ {trade_data.get('pnl_pct', 0):.2f}%")
    
    def _write_to_csv(self, trade: Dict):
        """Write trade to CSV file"""
        try:
            with open(self.current_file, 'a', newline='') as f:
                writer = csv.writer(f)
                
                row = [
                    trade.get("timestamp", ""),
                    trade.get("symbol", ""),
                    trade.get("direction", ""),
                    trade.get("entry", ""),
                    trade.get("exit", ""),
                    trade.get("stop_loss", ""),
                    trade.get("take_profit", ""),
                    trade.get("position_usd", ""),
                    trade.get("pnl_pct", ""),
                    trade.get("pnl_usd", ""),
                    trade.get("rr_ratio", ""),
                    trade.get("market_type", ""),
                    trade.get("grade", ""),
                    trade.get("filters_passed", ""),
                    trade.get("score", ""),
                    trade.get("reason", "")
                ]
                
                writer.writerow(row)
                
        except Exception as e:
            logger.error(f"Failed to write trade to CSV: {e}")
    
    def _write_to_json(self, trade: Dict):
        """Write trade to JSON log file"""
        try:
            json_file = self.log_dir / f"trades_{date.today().isoformat()}.json"
            
            # Read existing data
            existing = []
            if json_file.exists():
                with open(json_file, 'r') as f:
                    try:
                        existing = json.load(f)
                    except:
                        existing = []
            
            # Append new trade
            existing.append(trade)
            
            # Write back
            with open(json_file, 'w') as f:
                json.dump(existing, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to write trade to JSON: {e}")
    
    def get_trades_today(self) -> List[Dict]:
        """Get today's trades"""
        today = date.today().isoformat()
        return [t for t in self.trades if t.get("timestamp", "").startswith(today)]
    
    def get_stats_today(self) -> Dict:
        """Get today's trading statistics"""
        trades = self.get_trades_today()
        
        if not trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "total_pnl": 0.0,
                "avg_rr": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0
            }
        
        wins = [t for t in trades if t.get("pnl_pct", 0) > 0]
        losses = [t for t in trades if t.get("pnl_pct", 0) <= 0]
        
        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(trades)) * 100 if trades else 0,
            "total_pnl": sum(t.get("pnl_pct", 0) for t in trades),
            "avg_rr": sum(t.get("rr_ratio", 0) for t in trades) / len(trades) if trades else 0,
            "best_trade": max((t.get("pnl_pct", 0) for t in trades), default=0),
            "worst_trade": min((t.get("pnl_pct", 0) for t in trades), default=0)
        }
    
    def get_all_stats(self) -> Dict:
        """Get all-time statistics"""
        if not self.trades:
            return {
                "total_trades": 0,
                "total_days": 0,
                "avg_trades_per_day": 0,
                "win_rate": 0,
                "total_pnl": 0.0,
                "profit_factor": 0.0
            }
        
        # Group by date
        trades_by_date = {}
        for trade in self.trades:
            date_str = trade.get("timestamp", "")[:10]
            if date_str:
                if date_str not in trades_by_date:
                    trades_by_date[date_str] = []
                trades_by_date[date_str].append(trade)
        
        wins = [t for t in self.trades if t.get("pnl_pct", 0) > 0]
        losses = [t for t in self.trades if t.get("pnl_pct", 0) <= 0]
        
        total_profit = sum(t.get("pnl_pct", 0) for t in wins)
        total_loss = abs(sum(t.get("pnl_pct", 0) for t in losses))
        
        return {
            "total_trades": len(self.trades),
            "total_days": len(trades_by_date),
            "avg_trades_per_day": len(self.trades) / len(trades_by_date) if trades_by_date else 0,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(self.trades)) * 100 if self.trades else 0,
            "total_pnl": sum(t.get("pnl_pct", 0) for t in self.trades),
            "profit_factor": total_profit / total_loss if total_loss > 0 else total_profit if total_profit > 0 else 0,
            "avg_rr": sum(t.get("rr_ratio", 0) for t in self.trades) / len(self.trades) if self.trades else 0
        }
    
    def export_to_dataframe(self):
        """Export trades to pandas DataFrame (optional)"""
        try:
            import pandas as pd
            return pd.DataFrame(self.trades)
        except ImportError:
            logger.warning("pandas not installed")
            return None
