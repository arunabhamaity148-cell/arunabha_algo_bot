"""
ARUNABHA ALGO BOT - Performance Dashboard
Real-time performance monitoring dashboard
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class PerformanceDashboard:
    """
    Real-time performance dashboard
    """
    
    def __init__(self, metrics_collector, trade_logger):
        self.metrics = metrics_collector
        self.trade_logger = trade_logger
        self.last_update = datetime.now()
        self.cached_data = {}
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get all dashboard data"""
        
        metrics = self.metrics.get_all_metrics()
        trades_today = self.trade_logger.get_trades_today() if self.trade_logger else []
        
        return {
            "summary": metrics.get("summary", {}),
            "today": metrics.get("today", {}),
            "week": metrics.get("week", {}),
            "trades_today": trades_today[-10:],  # Last 10 trades
            "best_trade": metrics.get("best_trade", {}),
            "worst_trade": metrics.get("worst_trade", {}),
            "uptime": metrics.get("uptime", ""),
            "last_update": datetime.now().isoformat()
        }
    
    def get_html_dashboard(self) -> str:
        """Generate HTML dashboard"""
        data = self.get_dashboard_data()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>ARUNABHA Trading Dashboard</title>
            <meta http-equiv="refresh" content="60">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }}
                .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                .card h3 {{ margin-top: 0; color: #2c3e50; }}
                .value {{ font-size: 24px; font-weight: bold; color: #27ae60; }}
                .negative {{ color: #e74c3c; }}
                .table {{ width: 100%; border-collapse: collapse; }}
                .table th, .table td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                .table th {{ background: #34495e; color: white; }}
                .win {{ color: #27ae60; }}
                .loss {{ color: #e74c3c; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 ARUNABHA Trading Dashboard</h1>
                    <p>Last Update: {data['last_update']} | Uptime: {data['uptime']}</p>
                </div>
                
                <div class="stats-grid">
                    <div class="card">
                        <h3>📈 Overall Performance</h3>
                        <p>Total Trades: {data['summary'].get('total_trades', 0)}</p>
                        <p>Win Rate: <span class="value">{data['summary'].get('win_rate', 0):.1f}%</span></p>
                        <p>Total P&L: <span class="{'value' if data['summary'].get('total_pnl', 0) >= 0 else 'negative'}">{data['summary'].get('total_pnl', 0):+.2f}%</span></p>
                        <p>Profit Factor: {data['summary'].get('profit_factor', 0):.2f}</p>
                        <p>Sharpe Ratio: {data['summary'].get('sharpe_ratio', 0):.2f}</p>
                    </div>
                    
                    <div class="card">
                        <h3>📅 Today</h3>
                        <p>Trades: {data['today'].get('trades', 0)}</p>
                        <p>Win Rate: {data['today'].get('win_rate', 0):.1f}%</p>
                        <p>P&L: <span class="{'value' if data['today'].get('pnl', 0) >= 0 else 'negative'}">{data['today'].get('pnl', 0):+.2f}%</span></p>
                    </div>
                    
                    <div class="card">
                        <h3>📅 This Week</h3>
                        <p>Trades: {data['week'].get('trades', 0)}</p>
                        <p>Win Rate: {data['week'].get('win_rate', 0):.1f}%</p>
                        <p>P&L: <span class="{'value' if data['week'].get('pnl', 0) >= 0 else 'negative'}">{data['week'].get('pnl', 0):+.2f}%</span></p>
                    </div>
                    
                    <div class="card">
                        <h3>🏆 Best/Worst</h3>
                        <p>Best: {data['best_trade'].get('pnl_pct', 0):+.2f}% ({data['best_trade'].get('symbol', 'N/A')})</p>
                        <p>Worst: {data['worst_trade'].get('pnl_pct', 0):+.2f}% ({data['worst_trade'].get('symbol', 'N/A')})</p>
                        <p>Avg RR: {data['summary'].get('avg_rr', 0):.2f}</p>
                    </div>
                </div>
                
                <div class="card">
                    <h3>📋 Recent Trades</h3>
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Symbol</th>
                                <th>Direction</th>
                                <th>Entry</th>
                                <th>Exit</th>
                                <th>P&L</th>
                                <th>RR</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        # Add recent trades
        for trade in data['trades_today']:
            pnl = trade.get('pnl_pct', 0)
            pnl_class = "win" if pnl > 0 else "loss"
            
            html += f"""
                            <tr>
                                <td>{trade.get('timestamp', '')[:16]}</td>
                                <td>{trade.get('symbol', '')}</td>
                                <td>{trade.get('direction', '')}</td>
                                <td>{trade.get('entry', 0):.2f}</td>
                                <td>{trade.get('exit', 0):.2f}</td>
                                <td class="{pnl_class}">{pnl:+.2f}%</td>
                                <td>{trade.get('rr_ratio', 0):.2f}</td>
                            </tr>
            """
        
        html += """
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def save_dashboard(self, filename: str = "dashboard.html"):
        """Save dashboard to file"""
        html = self.get_html_dashboard()
        
        with open(filename, 'w') as f:
            f.write(html)
        
        logger.info(f"Dashboard saved to {filename}")
    
    def get_json_dashboard(self) -> str:
        """Get dashboard as JSON"""
        return json.dumps(self.get_dashboard_data(), indent=2, default=str)
    
    def get_text_summary(self) -> str:
        """Get text summary for Telegram"""
        data = self.get_dashboard_data()
        summary = data['summary']
        today = data['today']
        
        lines = [
            "📊 <b>Performance Summary</b>",
            "",
            f"<b>Overall</b>",
            f"Trades: {summary.get('total_trades', 0)}",
            f"Win Rate: {summary.get('win_rate', 0):.1f}%",
            f"Total P&L: {summary.get('total_pnl', 0):+.2f}%",
            f"Profit Factor: {summary.get('profit_factor', 0):.2f}",
            f"Sharpe: {summary.get('sharpe_ratio', 0):.2f}",
            "",
            f"<b>Today</b>",
            f"Trades: {today.get('trades', 0)}",
            f"Win Rate: {today.get('win_rate', 0):.1f}%",
            f"P&L: {today.get('pnl', 0):+.2f}%",
            "",
            f"<b>Best Trade</b>: {data['best_trade'].get('pnl_pct', 0):+.2f}%",
            f"<b>Worst Trade</b>: {data['worst_trade'].get('pnl_pct', 0):+.2f}%",
            f"<b>Uptime</b>: {data['uptime']}"
        ]
        
        return "\n".join(lines)
