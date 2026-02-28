"""
ARUNABHA ALGO BOT - Backtest Runner v5.0
=========================================
CRITICAL FIX:
  আগে: limit = min(days * 96, 1000) → 90 দিনের backtest-এও শুধু 1000 candles (10 দিন)!
  এখন: fetch_historical_data() with pagination → সত্যিকারের 90 দিন data

  90 days × 96 candles/day = 8640 candles দরকার।
  Binance max 1000/request → 9টা paginated request করে সব আনো।

ALSO FIXED:
  - Walk-forward minimum: 1000 candles (was 5760 — impossible to meet)
  - async ccxt close() added (Unclosed client session warning fix)
  - Trade count normalized by actual days (not candle count)
"""

import asyncio
import logging
import pandas as pd
from typing import Optional, List
from datetime import datetime, timedelta

import config

logger = logging.getLogger(__name__)


class BacktestRunner:

    def __init__(self):
        from data.rest_client import RESTClient
        from backtest.backtest_engine import BacktestEngine
        from backtest.report_generator import ReportGenerator

        self.rest_client = RESTClient()
        self.engine      = BacktestEngine(initial_capital=config.ACCOUNT_SIZE)
        self.reporter    = ReportGenerator()

    async def run(
        self,
        symbol: str,
        timeframe: str = "15m",
        days: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        report_format: str = "all"
    ) -> dict:

        logger.info("=" * 60)
        logger.info("ARUNABHA ALGO BOT — BACKTEST MODE")
        logger.info("=" * 60)
        logger.info(f"Backtest starting: {symbol} {timeframe} | {days} days")

        # ── Step 1: Connect ──────────────────────────────────────────
        try:
            await self.rest_client.connect()
        except Exception as e:
            logger.error(f"REST connection failed: {e}")
            return {"error": f"REST connection failed: {e}"}

        # ── Step 2: Fetch historical data (PAGINATED) ────────────────
        logger.info(f"Fetching historical data for {symbol}...")
        candles = []
        try:
            # FIXED: use fetch_historical_data() for paginated fetch
            # This gets the actual days requested, not just 1000 candles
            candles = await self.rest_client.fetch_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                days=days,
            )

            if not candles or len(candles) < 60:
                msg = (
                    f"Insufficient data: got {len(candles) if candles else 0} candles. "
                    f"Need at least 60."
                )
                logger.error(msg)
                await self._close_exchange()
                return {"error": msg}

            logger.info(f"Fetched {len(candles)} candles for {symbol}")

        except Exception as e:
            logger.error(f"Data fetch failed: {e}")
            await self._close_exchange()
            return {"error": f"Data fetch failed: {e}"}

        # ── Step 3: Convert to DataFrame ─────────────────────────────
        try:
            df = pd.DataFrame(
                candles,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            df = df[~df.index.duplicated(keep="last")]
            df.sort_index(inplace=True)

            logger.info(
                f"Data range: {df.index[0]} to {df.index[-1]} "
                f"({len(df)} candles)"
            )

        except Exception as e:
            logger.error(f"DataFrame conversion failed: {e}")
            await self._close_exchange()
            return {"error": f"DataFrame error: {e}"}

        # ── Step 4: Run backtest ─────────────────────────────────────
        logger.info("Running backtest engine...")
        try:
            result = self.engine.run(df, symbol, start_date, end_date)
        except Exception as e:
            logger.error(f"Backtest engine failed: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            await self._close_exchange()
            return {"error": f"Backtest failed: {e}"}

        # ── Step 5: Print summary ─────────────────────────────────────
        self.engine.print_summary(result)

        # ── Step 6: Save reports ──────────────────────────────────────
        file_paths = {}
        try:
            file_paths = self.reporter.save_all(result, symbol, timeframe)
            logger.info(f"Reports saved: {list(file_paths.values())}")
        except Exception as e:
            logger.warning(f"Report save failed: {e}")

        # ── Step 7: Walk-forward validation ──────────────────────────
        logger.info("Running walk-forward validation...")
        wf_result = {}
        try:
            from backtest.walk_forward import WalkForwardValidator
            wf = WalkForwardValidator()
            wf_result = wf.validate(candles, symbol, timeframe)
            logger.info(
                f"Walk-forward: {wf_result.get('windows', 0)} windows | "
                f"Train={wf_result.get('avg_train_pf', 0):.2f} | "
                f"Test={wf_result.get('avg_test_pf', 0):.2f} | "
                f"Verdict={wf_result.get('verdict', 'N/A')}"
            )
        except Exception as e:
            logger.warning(f"Walk-forward failed: {e}")
            wf_result = {"verdict": "ERROR", "error": str(e)}

        # ── Step 8: Close exchange (fixes "Unclosed client session") ──
        await self._close_exchange()

        return {
            "symbol":        symbol,
            "timeframe":     timeframe,
            "days":          days,
            "candles":       len(candles),
            "total_trades":  result.total_trades,
            "win_rate":      result.win_rate,
            "total_return":  result.total_pnl_percent,
            "profit_factor": result.profit_factor,
            "sharpe_ratio":  result.sharpe_ratio,
            "max_drawdown":  result.max_drawdown_percent,
            "expectancy":    result.expectancy,
            "signals_blocked": result.signals_blocked,
            "walk_forward":  wf_result,
            "reports":       file_paths,
        }

    async def _close_exchange(self):
        """Properly close ccxt exchange to avoid 'Unclosed client session'"""
        try:
            if hasattr(self.rest_client, "exchange") and self.rest_client.exchange:
                await self.rest_client.exchange.close()
        except Exception:
            pass


def run_backtest_cli():
    """Entry point for CLI: python main.py --mode backtest"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol",    default="BTC/USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--days",      type=int, default=30)
    args, _ = parser.parse_known_args()

    async def _run():
        runner = BacktestRunner()
        result = await runner.run(
            symbol=args.symbol,
            timeframe=args.timeframe,
            days=args.days,
        )

        print("\n" + "=" * 50)
        if "error" in result:
            print(f"BACKTEST FAILED: {result['error']}")
        else:
            print(f"BACKTEST COMPLETE: {result['symbol']}")
            print(f"   Trades:          {result['total_trades']}")
            print(f"   Signals Blocked: {result.get('signals_blocked', 0)}")
            print(f"   Win Rate:        {result['win_rate']:.1f}%")
            print(f"   Total Return:    {result['total_return']:+.2f}%")
            print(f"   Profit Factor:   {result['profit_factor']:.2f}")
            print(f"   Sharpe Ratio:    {result['sharpe_ratio']:.2f}")
            print(f"   Max Drawdown:    {result['max_drawdown']:.2f}%")
            if result.get("reports"):
                print(f"   Reports saved:")
                for fmt, path in result["reports"].items():
                    print(f"      {fmt}: {path}")
        print("=" * 50)

    asyncio.run(_run())
