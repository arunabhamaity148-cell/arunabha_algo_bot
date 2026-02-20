"""
ARUNABHA ALGO BOT - Profit Calculator
Calculates profit after TDS, GST, and fees for Indian exchanges
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import config

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    symbol: str
    direction: str
    entry: float
    exit: float
    quantity: float
    gross_pnl: float
    tds: float
    gst: float
    brokerage: float
    net_pnl: float
    pnl_percent: float


class ProfitCalculator:
    def __init__(self, exchange: str = "CoinDCX"):
        self.exchange = exchange
        self.brokerage_rate = 0.1  # 0.1% for CoinDCX
        self.trades: List[TradeResult] = []
        self.daily_pnl = 0.0
    
    def calculate(self, entry: float, exit: float, qty: float, side: str, symbol: str) -> TradeResult:
        """Calculate profit after all deductions"""
        
        # Gross P&L
        if side == "LONG":
            gross_pnl = (exit - entry) * qty
            pnl_percent = ((exit - entry) / entry) * 100
        else:
            gross_pnl = (entry - exit) * qty
            pnl_percent = ((entry - exit) / entry) * 100
        
        # Brokerage (0.1% of trade value)
        trade_value = entry * qty
        brokerage = trade_value * (self.brokerage_rate / 100)
        
        # TDS (1% on profit)
        tds = gross_pnl * (config.TDS_RATE / 100) if gross_pnl > 0 else 0
        
        # GST (18% on brokerage)
        gst = brokerage * (config.GST_RATE / 100)
        
        # Net P&L
        net_pnl = gross_pnl - brokerage - tds - gst
        
        result = TradeResult(
            symbol=symbol,
            direction=side,
            entry=entry,
            exit=exit,
            quantity=qty,
            gross_pnl=round(gross_pnl, 2),
            tds=round(tds, 2),
            gst=round(gst, 2),
            brokerage=round(brokerage, 2),
            net_pnl=round(net_pnl, 2),
            pnl_percent=round(pnl_percent, 2)
        )
        
        self.trades.append(result)
        self.daily_pnl += net_pnl
        
        logger.info(f"[PROFIT] {symbol} {side} | Gross: ₹{gross_pnl:.2f} | Net: ₹{net_pnl:.2f}")
        
        return result
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """Get daily profit summary"""
        if not self.trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "gross_pnl": 0,
                "net_pnl": 0,
                "total_tds": 0,
                "total_gst": 0,
                "total_brokerage": 0,
                "target_achieved": False
            }
        
        total_gross = sum(t.gross_pnl for t in self.trades)
        total_net = sum(t.net_pnl for t in self.trades)
        total_tds = sum(t.tds for t in self.trades)
        total_gst = sum(t.gst for t in self.trades)
        total_brokerage = sum(t.brokerage for t in self.trades)
        
        wins = len([t for t in self.trades if t.net_pnl > 0])
        losses = len([t for t in self.trades if t.net_pnl < 0])
        
        return {
            "total_trades": len(self.trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins/len(self.trades)*100, 2) if self.trades else 0,
            "gross_pnl": round(total_gross, 2),
            "net_pnl": round(total_net, 2),
            "total_tds": round(total_tds, 2),
            "total_gst": round(total_gst, 2),
            "total_brokerage": round(total_brokerage, 2),
            "target_achieved": total_net >= config.DAILY_PROFIT_TARGET
        }
    
    def reset_daily(self):
        """Reset for new day"""
        self.trades.clear()
        self.daily_pnl = 0.0


profit_calculator = ProfitCalculator()
