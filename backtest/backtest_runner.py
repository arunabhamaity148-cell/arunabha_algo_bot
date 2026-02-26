"""
ARUNABHA ALGO BOT - Backtest Runner v4.1

FIX BUG-26: Backtest এখন main.py এর সাথে connected
- CLI: python main.py --mode backtest --symbol ETH/USDT --days 30
- API: POST /backtest (web mode এ)
- Binance REST থেকে historical data নিয়ে backtest run করে
- Report: backtest_reports/ folder এ save হয়
"""

import asyncio
import logging
import argparse
from typing import Optional, List
from datetime import datetime, timedelta

import config

logger = logging.getLogger(__name__)


class BacktestRunner:
    """
    Connects backtest engine to live REST client for historical data
    """

    def __init__(self):
        from data.rest_client import RESTClient
        from backtest.backtest_engine import BacktestEngine
        from backtest.report_generator import ReportGenerator

        self.rest_client = RESTClient()
        self.engine = BacktestEngine(initial_capital=config.ACCOUNT_SIZE)
        self.reporter = ReportGenerator()

    async def run(
        self,
        symbol: str,
        timeframe: str = "15m",
        days: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        report_format: str = "all"
    ) -> dict:
        """
        Run a backtest for a symbol

        Args:
            symbol:      Trading pair, e.g. "ETH/USDT"
            timeframe:   Candle timeframe, e.g. "15m"
            days:        How many days of history to fetch (if no start_date)
            start_date:  Optional start date string "YYYY-MM-DD"
            end_date:    Optional end date string "YYYY-MM-DD"
            report_format: "txt", "csv", "json", "html", or "all"

        Returns:
            dict with result summary and file paths
        """
        logger.info(f"🔄 Backtest starting: {symbol} {timeframe} | {days} days")

        # Step 1: Connect REST API
        try:
            await self.rest_client.connect()
        except Exception as e:
            logger.error(f"❌ REST connection failed: {e}")
            return {"error": f"REST connection failed: {e}"}

        # Step 2: Fetch historical data
        logger.info(f"📡 Fetching historical data for {symbol}...")
        try:
            # Calculate number of candles needed
            candles_per_day = {
                "1m": 1440, "5m": 288, "15m": 96,
                "30m": 48,  "1h": 24,  "4h": 6, "1d": 1
            }
            per_day = candles_per_day.get(timeframe, 96)
            limit = min(days * per_day, 1000)  # Binance max 1000 per request

            candles = await self.rest_client.fetch_ohlcv_rest(symbol, timeframe, limit)

            if not candles or len(candles) < 50:
                msg = f"Insufficient data: got {len(candles) if candles else 0} candles, need 50+"
                logger.error(f"❌ {msg}")
                return {"error": msg}

            logger.info(f"✅ Fetched {len(candles)} candles for {symbol}")

        except Exception as e:
            logger.error(f"❌ Data fetch failed: {e}")
            return {"error": f"Data fetch failed: {e}"}

        # Step 3: Convert to DataFrame
        try:
            import pandas as pd
            df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)

            logger.info(f"📊 Data range: {df.index[0]} → {df.index[-1]}")

        except Exception as e:
            logger.error(f"❌ DataFrame conversion failed: {e}")
            return {"error": f"DataFrame conversion failed: {e}"}

        # Step 4: Run backtest
        logger.info("⚙️ Running backtest engine...")
        try:
            result = self.engine.run(
                df=df,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
        except Exception as e:
            logger.error(f"❌ Backtest engine error: {e}")
            return {"error": f"Backtest engine error: {e}"}

        # Step 5: Generate report
        end_str = end_date or datetime.now().strftime("%Y-%m-%d")
        start_str = start_date or (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            files = self.reporter.generate_report(
                result=result,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_str,
                end_date=end_str,
                format=report_format
            )
        except Exception as e:
            logger.warning(f"⚠️ Report generation failed: {e}")
            files = {}

        # Step 6: Print summary
        self.engine.print_summary(result)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start_str,
            "end": end_str,
            "candles": len(candles),
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
            "report_files": files
        }

    async def run_all_pairs(
        self,
        timeframe: str = "15m",
        days: int = 30
    ) -> dict:
        """Run backtest for all configured trading pairs"""
        all_results = {}

        for symbol in config.TRADING_PAIRS:
            logger.info(f"\n{'='*50}")
            logger.info(f"🔄 Running backtest for {symbol}")
            logger.info(f"{'='*50}")

            result = await self.run(
                symbol=symbol,
                timeframe=timeframe,
                days=days
            )
            all_results[symbol] = result
            await asyncio.sleep(1)  # rate limit

        # Print comparison table
        logger.info("\n" + "="*70)
        logger.info("BACKTEST COMPARISON — ALL PAIRS")
        logger.info("="*70)
        logger.info(f"{'Symbol':<15} {'Trades':>7} {'WinRate':>9} {'Return%':>9} {'PF':>6} {'MaxDD%':>8}")
        logger.info("-"*70)

        for symbol, res in all_results.items():
            if "error" in res:
                logger.info(f"{symbol:<15} {'ERROR':>7} {res['error'][:30]}")
                continue
            s = res["summary"]
            logger.info(
                f"{symbol:<15} {s['total_trades']:>7} "
                f"{s['win_rate']:>8.1f}% {s['total_return_pct']:>+8.2f}% "
                f"{s['profit_factor']:>6.2f} {s['max_drawdown_pct']:>7.2f}%"
            )

        logger.info("="*70)
        return all_results


async def run_backtest_cli(args):
    """Entry point for CLI backtest mode"""
    logger.info("=" * 60)
    logger.info("📊 ARUNABHA ALGO BOT — BACKTEST MODE")
    logger.info("=" * 60)

    runner = BacktestRunner()

    if args.all_pairs:
        results = await runner.run_all_pairs(
            timeframe=args.timeframe,
            days=args.days
        )
        return results
    else:
        result = await runner.run(
            symbol=args.symbol,
            timeframe=args.timeframe,
            days=args.days,
            start_date=args.start_date,
            end_date=args.end_date,
            report_format=args.report_format
        )
        return result
