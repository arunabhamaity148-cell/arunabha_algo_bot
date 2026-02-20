"""
ARUNABHA ALGO BOT - Report Generator
Generates comprehensive backtest reports
"""

import logging
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from backtest.backtest_engine import BacktestResult

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates detailed backtest reports in multiple formats
    """
    
    def __init__(self, output_dir: str = "backtest_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    def generate_report(
        self,
        result: BacktestResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        format: str = 'all'
    ) -> Dict[str, str]:
        """
        Generate comprehensive backtest report
        
        Args:
            result: Backtest result object
            symbol: Trading symbol
            timeframe: Timeframe used
            start_date: Start date
            end_date: End date
            format: Output format ('txt', 'csv', 'json', 'html', 'all')
        
        Returns:
            Dictionary with paths to generated files
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"{symbol}_{timeframe}_{start_date}_to_{end_date}_{timestamp}"
        
        generated_files = {}
        
        if format in ['txt', 'all']:
            txt_file = self.output_dir / f"{base_filename}.txt"
            self._generate_txt_report(result, symbol, timeframe, start_date, end_date, txt_file)
            generated_files['txt'] = str(txt_file)
        
        if format in ['csv', 'all']:
            csv_file = self.output_dir / f"{base_filename}.csv"
            self._generate_csv_report(result, csv_file)
            generated_files['csv'] = str(csv_file)
        
        if format in ['json', 'all']:
            json_file = self.output_dir / f"{base_filename}.json"
            self._generate_json_report(result, symbol, timeframe, start_date, end_date, json_file)
            generated_files['json'] = str(json_file)
        
        if format in ['html', 'all']:
            html_file = self.output_dir / f"{base_filename}.html"
            self._generate_html_report(result, symbol, timeframe, start_date, end_date, html_file)
            generated_files['html'] = str(html_file)
        
        logger.info(f"Reports generated: {', '.join(generated_files.values())}")
        
        return generated_files
    
    def _generate_txt_report(
        self,
        result: BacktestResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        filepath: Path
    ):
        """Generate text report"""
        
        with open(filepath, 'w') as f:
            f.write("="*80 + "\n")
            f.write("ARUNABHA BACKTEST REPORT\n")
            f.write("="*80 + "\n\n")
            
            f.write(f"Symbol: {symbol}\n")
            f.write(f"Timeframe: {timeframe}\n")
            f.write(f"Period: {start_date} to {end_date}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("-"*80 + "\n")
            f.write("TRADE STATISTICS\n")
            f.write("-"*80 + "\n")
            f.write(f"Total Trades: {result.total_trades}\n")
            f.write(f"Winning Trades: {result.winning_trades}\n")
            f.write(f"Losing Trades: {result.losing_trades}\n")
            f.write(f"Win Rate: {result.win_rate:.2f}%\n")
            f.write(f"Avg RR: {result.avg_rr:.2f}\n")
            f.write(f"Avg Win: {result.avg_win:+.2f}%\n")
            f.write(f"Avg Loss: {result.avg_loss:+.2f}%\n")
            f.write(f"Best Trade: {result.best_trade:+.2f}%\n")
            f.write(f"Worst Trade: {result.worst_trade:+.2f}%\n\n")
            
            f.write("-"*80 + "\n")
            f.write("PERFORMANCE METRICS\n")
            f.write("-"*80 + "\n")
            f.write(f"Total P&L: ${result.total_pnl:,.2f}\n")
            f.write(f"Total Return: {result.total_pnl_percent:+.2f}%\n")
            f.write(f"Profit Factor: {result.profit_factor:.2f}\n")
            f.write(f"Sharpe Ratio: {result.sharpe_ratio:.2f}\n")
            f.write(f"Max Drawdown: ${result.max_drawdown:,.2f}\n")
            f.write(f"Max Drawdown %: {result.max_drawdown_percent:.2f}%\n\n")
            
            if result.monthly_stats:
                f.write("-"*80 + "\n")
                f.write("MONTHLY PERFORMANCE\n")
                f.write("-"*80 + "\n")
                f.write(f"{'Month':<10} {'Trades':<8} {'Wins':<8} {'Win Rate':<10} {'P&L':<12}\n")
                f.write("-"*60 + "\n")
                
                for month, stats in sorted(result.monthly_stats.items()):
                    f.write(f"{month:<10} {stats['trades']:<8} {stats['wins']:<8} "
                           f"{stats['win_rate']:<10.1f} ${stats['pnl']:<12,.2f}\n")
            
            f.write("\n" + "="*80 + "\n")
    
    def _generate_csv_report(self, result: BacktestResult, filepath: Path):
        """Generate CSV report of individual trades"""
        
        if not result.trades:
            return
        
        # Convert trades to DataFrame
        df = pd.DataFrame(result.trades)
        
        # Format columns
        if 'entry_time' in df.columns:
            df['entry_time'] = pd.to_datetime(df['entry_time'], unit='ms')
        if 'exit_time' in df.columns:
            df['exit_time'] = pd.to_datetime(df['exit_time'], unit='ms')
        
        # Save to CSV
        df.to_csv(filepath, index=False)
    
    def _generate_json_report(
        self,
        result: BacktestResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        filepath: Path
    ):
        """Generate JSON report"""
        
        report = {
            'metadata': {
                'symbol': symbol,
                'timeframe': timeframe,
                'start_date': start_date,
                'end_date': end_date,
                'generated': datetime.now().isoformat()
            },
            'summary': {
                'total_trades': result.total_trades,
                'winning_trades': result.winning_trades,
                'losing_trades': result.losing_trades,
                'win_rate': result.win_rate,
                'total_pnl': result.total_pnl,
                'total_pnl_percent': result.total_pnl_percent,
                'profit_factor': result.profit_factor,
                'sharpe_ratio': result.sharpe_ratio,
                'max_drawdown': result.max_drawdown,
                'max_drawdown_percent': result.max_drawdown_percent,
                'avg_rr': result.avg_rr,
                'avg_win': result.avg_win,
                'avg_loss': result.avg_loss,
                'best_trade': result.best_trade,
                'worst_trade': result.worst_trade
            },
            'trades': result.trades,
            'equity_curve': result.equity_curve,
            'monthly_stats': result.monthly_stats
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
    
    def _generate_html_report(
        self,
        result: BacktestResult,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        filepath: Path
    ):
        """Generate HTML report with charts"""
        
        # Create equity curve data for chart
        equity_data = []
        for i, value in enumerate(result.equity_curve):
            equity_data.append({'x': i, 'y': value})
        
        # Create monthly stats table
        monthly_rows = ""
        if result.monthly_stats:
            for month, stats in sorted(result.monthly_stats.items()):
                monthly_rows += f"""
                <tr>
                    <td>{month}</td>
                    <td>{stats['trades']}</td>
                    <td>{stats['wins']}</td>
                    <td>{stats['win_rate']:.1f}%</td>
                    <td class="{'positive' if stats['pnl'] >= 0 else 'negative'}">${stats['pnl']:,.2f}</td>
                </tr>
                """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>ARUNABHA Backtest Report - {symbol}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 30px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 20px; }}
                .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                .card h3 {{ margin-top: 0; color: #2c3e50; }}
                .value {{ font-size: 24px; font-weight: bold; color: #27ae60; }}
                .negative {{ color: #e74c3c; }}
                .positive {{ color: #27ae60; }}
                .table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .table th, .table td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                .table th {{ background: #34495e; color: white; }}
                .chart-container {{ height: 400px; margin: 20px 0; }}
            </style>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 ARUNABHA Backtest Report</h1>
                    <p>Symbol: {symbol} | Timeframe: {timeframe}</p>
                    <p>Period: {start_date} to {end_date}</p>
                    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                
                <div class="stats-grid">
                    <div class="card">
                        <h3>📈 Trade Statistics</h3>
                        <p>Total Trades: {result.total_trades}</p>
                        <p>Winning Trades: {result.winning_trades}</p>
                        <p>Losing Trades: {result.losing_trades}</p>
                        <p>Win Rate: <span class="value">{result.win_rate:.1f}%</span></p>
                        <p>Avg RR: {result.avg_rr:.2f}</p>
                    </div>
                    
                    <div class="card">
                        <h3>💰 Performance</h3>
                        <p>Total P&L: <span class="{'value' if result.total_pnl >= 0 else 'negative'}">${result.total_pnl:,.2f}</span></p>
                        <p>Total Return: <span class="{'value' if result.total_pnl_percent >= 0 else 'negative'}">{result.total_pnl_percent:+.2f}%</span></p>
                        <p>Profit Factor: {result.profit_factor:.2f}</p>
                        <p>Sharpe Ratio: {result.sharpe_ratio:.2f}</p>
                    </div>
                    
                    <div class="card">
                        <h3>📉 Risk Metrics</h3>
                        <p>Max Drawdown: <span class="negative">${result.max_drawdown:,.2f}</span></p>
                        <p>Max Drawdown %: <span class="negative">{result.max_drawdown_percent:.2f}%</span></p>
                        <p>Best Trade: <span class="positive">{result.best_trade:+.2f}%</span></p>
                        <p>Worst Trade: <span class="negative">{result.worst_trade:+.2f}%</span></p>
                    </div>
                    
                    <div class="card">
                        <h3>📊 Averages</h3>
                        <p>Avg Win: <span class="positive">{result.avg_win:+.2f}%</span></p>
                        <p>Avg Loss: <span class="negative">{result.avg_loss:+.2f}%</span></p>
                        <p>Win/Loss Ratio: {abs(result.avg_win / result.avg_loss) if result.avg_loss != 0 else 0:.2f}</p>
                    </div>
                </div>
                
                <div class="card">
                    <h3>📈 Equity Curve</h3>
                    <div class="chart-container">
                        <canvas id="equityChart"></canvas>
                    </div>
                </div>
                
                <div class="card">
                    <h3>📅 Monthly Performance</h3>
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Month</th>
                                <th>Trades</th>
                                <th>Wins</th>
                                <th>Win Rate</th>
                                <th>P&L</th>
                            </tr>
                        </thead>
                        <tbody>
                            {monthly_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <script>
                const ctx = document.getElementById('equityChart').getContext('2d');
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: {list(range(len(result.equity_curve)))},
                        datasets: [{{
                            label: 'Equity Curve',
                            data: {result.equity_curve},
                            borderColor: '#27ae60',
                            backgroundColor: 'rgba(39, 174, 96, 0.1)',
                            fill: true
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{
                                display: false
                            }}
                        }}
                    }}
                }});
            </script>
        </body>
        </html>
        """
        
        with open(filepath, 'w') as f:
            f.write(html)
    
    def compare_strategies(
        self,
        results: Dict[str, BacktestResult],
        output_file: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Compare multiple strategy backtest results
        
        Args:
            results: Dictionary mapping strategy names to results
            output_file: Optional file to save comparison
        
        Returns:
            DataFrame with comparison metrics
        """
        comparison = []
        
        for name, result in results.items():
            comparison.append({
                'Strategy': name,
                'Total Trades': result.total_trades,
                'Win Rate': f"{result.win_rate:.1f}%",
                'Total Return': f"{result.total_pnl_percent:+.2f}%",
                'Profit Factor': f"{result.profit_factor:.2f}",
                'Sharpe': f"{result.sharpe_ratio:.2f}",
                'Max DD': f"{result.max_drawdown_percent:.2f}%",
                'Avg RR': f"{result.avg_rr:.2f}",
                'Best Trade': f"{result.best_trade:+.2f}%",
                'Worst Trade': f"{result.worst_trade:+.2f}%"
            })
        
        df = pd.DataFrame(comparison)
        
        if output_file:
            df.to_csv(output_file, index=False)
            logger.info(f"Comparison saved to {output_file}")
        
        return df
