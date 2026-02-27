"""
ARUNABHA ALGO BOT - Backtest Report Generator
Generates backtest reports in txt, csv, json, html formats.
Saves to backtest_reports/ folder.
"""

import os
import json
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

REPORT_DIR = "backtest_reports"


class ReportGenerator:
    """
    Generates backtest reports from BacktestResult objects.
    Supports: txt, csv, json, html, or all.
    """

    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)

    def generate_report(
        self,
        result,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        format: str = "all"
    ) -> Dict[str, str]:
        """
        Generate report files.
        Returns dict: {format: filepath}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_symbol = symbol.replace("/", "")
        base_name = f"{REPORT_DIR}/{safe_symbol}_{timeframe}_{timestamp}"

        files = {}
        formats = ["txt", "csv", "json", "html"] if format == "all" else [format]

        for fmt in formats:
            try:
                if fmt == "txt":
                    path = base_name + ".txt"
                    self._write_txt(result, symbol, timeframe, start_date, end_date, path)
                    files["txt"] = path

                elif fmt == "json":
                    path = base_name + ".json"
                    self._write_json(result, symbol, timeframe, start_date, end_date, path)
                    files["json"] = path

                elif fmt == "csv":
                    path = base_name + "_trades.csv"
                    self._write_csv(result, path)
                    files["csv"] = path

                elif fmt == "html":
                    path = base_name + ".html"
                    self._write_html(result, symbol, timeframe, start_date, end_date, path)
                    files["html"] = path

            except Exception as e:
                logger.warning(f"Report format {fmt} failed: {e}")

        logger.info(f"📁 Reports saved: {list(files.values())}")
        return files

    def _write_txt(self, result, symbol, timeframe, start, end, path):
        with open(path, "w") as f:
            f.write("=" * 60 + "\n")
            f.write(f"ARUNABHA ALGO BOT — BACKTEST REPORT\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Symbol:    {symbol}\n")
            f.write(f"Timeframe: {timeframe}\n")
            f.write(f"Period:    {start} → {end}\n\n")
            f.write("-" * 40 + "\n")
            f.write("PERFORMANCE SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Trades:    {result.total_trades}\n")
            f.write(f"Win Rate:        {result.win_rate:.1f}%\n")
            f.write(f"Total Return:    {result.total_pnl_percent:+.2f}%\n")
            f.write(f"Profit Factor:   {result.profit_factor:.2f}\n")
            f.write(f"Sharpe Ratio:    {result.sharpe_ratio:.2f}\n")
            f.write(f"Max Drawdown:    {result.max_drawdown_percent:.2f}%\n")
            f.write(f"Avg R:R:         {result.avg_rr:.2f}\n")
            f.write(f"Best Trade:      {result.best_trade:+.2f}%\n")
            f.write(f"Worst Trade:     {result.worst_trade:+.2f}%\n")
            f.write("\n" + "=" * 60 + "\n")

    def _write_json(self, result, symbol, timeframe, start, end, path):
        data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start,
            "end_date": end,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_trades": result.total_trades,
                "win_rate": round(result.win_rate, 2),
                "total_return_pct": round(result.total_pnl_percent, 2),
                "profit_factor": round(result.profit_factor, 2),
                "sharpe_ratio": round(result.sharpe_ratio, 2),
                "max_drawdown_pct": round(result.max_drawdown_percent, 2),
                "avg_rr": round(result.avg_rr, 2),
                "best_trade_pct": round(result.best_trade, 2),
                "worst_trade_pct": round(result.worst_trade, 2),
            },
            "trades": [t.__dict__ if hasattr(t, '__dict__') else t for t in (result.trades or [])]
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _write_csv(self, result, path):
        trades = result.trades or []
        if not trades:
            with open(path, "w") as f:
                f.write("No trades recorded\n")
            return

        with open(path, "w") as f:
            # Write header from first trade's keys
            first = trades[0]
            if hasattr(first, '__dict__'):
                keys = list(first.__dict__.keys())
            elif isinstance(first, dict):
                keys = list(first.keys())
            else:
                keys = ["trade"]

            f.write(",".join(keys) + "\n")
            for trade in trades:
                if hasattr(trade, '__dict__'):
                    row = trade.__dict__
                elif isinstance(trade, dict):
                    row = trade
                else:
                    row = {"trade": str(trade)}
                f.write(",".join(str(row.get(k, "")) for k in keys) + "\n")

    def _write_html(self, result, symbol, timeframe, start, end, path):
        html = f"""<!DOCTYPE html>
<html>
<head>
<title>Backtest Report — {symbol}</title>
<style>
body {{ font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
h1 {{ color: #58a6ff; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #30363d; padding: 8px 12px; text-align: left; }}
th {{ background: #161b22; color: #58a6ff; }}
.pos {{ color: #3fb950; }}
.neg {{ color: #f85149; }}
</style>
</head>
<body>
<h1>📊 ARUNABHA ALGO BOT — Backtest Report</h1>
<p><b>Symbol:</b> {symbol} | <b>TF:</b> {timeframe} | <b>Period:</b> {start} → {end}</p>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Trades</td><td>{result.total_trades}</td></tr>
<tr><td>Win Rate</td><td>{result.win_rate:.1f}%</td></tr>
<tr><td>Total Return</td><td class="{'pos' if result.total_pnl_percent >= 0 else 'neg'}">{result.total_pnl_percent:+.2f}%</td></tr>
<tr><td>Profit Factor</td><td>{result.profit_factor:.2f}</td></tr>
<tr><td>Sharpe Ratio</td><td>{result.sharpe_ratio:.2f}</td></tr>
<tr><td>Max Drawdown</td><td class="neg">{result.max_drawdown_percent:.2f}%</td></tr>
<tr><td>Avg R:R</td><td>{result.avg_rr:.2f}</td></tr>
<tr><td>Best Trade</td><td class="pos">{result.best_trade:+.2f}%</td></tr>
<tr><td>Worst Trade</td><td class="neg">{result.worst_trade:+.2f}%</td></tr>
</table>
<p style="color:#8b949e; font-size:0.85em;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</body>
</html>"""
        with open(path, "w") as f:
            f.write(html)
