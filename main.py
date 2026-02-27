"""
ARUNABHA ALGO BOT v4.1 - Main Entry Point

FIXES in this version:
- BUG-23: engine.start() এখন startup_event এ call হচ্ছে
- BUG-24: telegram.start() এখন startup_event এ call হচ্ছে
- BUG-26: Backtest এখন CLI থেকে run করা যাবে
          python main.py --mode backtest --symbol ETH/USDT --days 30
          python main.py --mode backtest --all-pairs --days 60
"""

import os
import sys
import asyncio
import logging
import argparse
from typing import Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv

load_dotenv()

# ==================== LOGGING SETUP ====================
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('ccxt').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

logger = logging.getLogger("main")
logger.info("=" * 80)
logger.info(f"🚀 ARUNABHA ALGO BOT v4.1 — Starting at {datetime.now().isoformat()}")
logger.info("=" * 80)

# Import core modules
from core.engine import ArunabhaEngine
from core.scheduler import TradingScheduler
from core.orchestrator import Orchestrator
from notification.telegram_bot import TelegramNotifier
from monitoring.health_check import HealthChecker
from monitoring.metrics_collector import MetricsCollector

# FastAPI app
app = FastAPI(title="ARUNABHA ALGO BOT", version="4.1")

# Global instances
engine: Optional[ArunabhaEngine] = None
scheduler: Optional[TradingScheduler] = None
orchestrator: Optional[Orchestrator] = None
telegram: Optional[TelegramNotifier] = None
health_checker: Optional[HealthChecker] = None
metrics: Optional[MetricsCollector] = None


# ==================== API Routes ====================

@app.get("/")
async def root():
    if engine:
        status = engine.get_status()
        return {
            "bot": "ARUNABHA ALGO BOT",
            "version": "4.1",
            "status": "running",
            **status,
            "auto_trade": False,
            "manual_signals": True
        }
    return {"status": "initializing"}


@app.get("/health")
async def health():
    if health_checker:
        return await health_checker.check()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "btc_data_ready": engine._btc_data_ready if engine else False
    }


@app.get("/logs")
async def get_logs(lines: int = 50):
    try:
        with open('bot.log', 'r') as f:
            return {"logs": f.readlines()[-lines:]}
    except:
        return {"logs": ["Log file not found"]}


@app.get("/debug")
async def debug_status():
    if not engine:
        return {"error": "Engine not initialized"}
    return {
        "btc_data_ready": engine._btc_data_ready,
        "btc_15m_candles": len(engine.btc_cache.get("15m", [])),
        "btc_1h_candles": len(engine.btc_cache.get("1h", [])),
        "btc_4h_candles": len(engine.btc_cache.get("4h", [])),
        "market_type": str(engine.market_type),
        "daily_signals": engine.daily_signals,
        "paper_trading": engine.paper_trading,
        "paper_pnl": engine._paper_pnl if engine.paper_trading else None,
        "adaptive_threshold": engine._adaptive_threshold,
        "ws_status": engine.ws_manager.get_status(),
        "last_signal_time": {k: v.isoformat() for k, v in engine.last_signal_time.items()}
    }


@app.post("/reload")
async def hot_reload_config():
    """
    Hot reload config without restarting bot.
    POST /reload → reloads config.py values at runtime.
    """
    try:
        import importlib
        import config as cfg_module
        importlib.reload(cfg_module)
        logger.info("🔄 Config hot-reloaded")
        return {
            "status": "reloaded",
            "timestamp": datetime.now().isoformat(),
            "key_values": {
                "RISK_PER_TRADE": cfg_module.RISK_PER_TRADE,
                "MAX_SIGNALS_PER_DAY": cfg_module.MAX_SIGNALS_PER_DAY,
                "MIN_TIER2_SCORE": cfg_module.MIN_TIER2_SCORE,
                "PAPER_TRADING": cfg_module.PAPER_TRADING,
            }
        }
    except Exception as e:
        logger.error(f"Config reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != os.getenv("WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    data = await request.json()
    logger.info(f"📡 Webhook: {data.get('type', 'unknown')}")
    if orchestrator:
        await orchestrator.process_webhook(data)
    return {"status": "received"}


# ✅ FIX BUG-26: Web mode এ backtest endpoint
@app.post("/backtest")
async def run_backtest(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Run a backtest via API

    Body (JSON):
    {
        "symbol": "ETH/USDT",
        "timeframe": "15m",
        "days": 30,
        "all_pairs": false
    }
    """
    data = await request.json()
    symbol = data.get("symbol", "BTC/USDT")
    timeframe = data.get("timeframe", "15m")
    days = int(data.get("days", 30))
    all_pairs = data.get("all_pairs", False)

    # Run in background to avoid timeout
    async def _run():
        from backtest.backtest_runner import BacktestRunner
        runner = BacktestRunner()
        if all_pairs:
            result = await runner.run_all_pairs(timeframe=timeframe, days=days)
        else:
            result = await runner.run(symbol=symbol, timeframe=timeframe, days=days)
        logger.info(f"✅ Backtest complete: {result.get('summary', {})}")

    background_tasks.add_task(_run)
    return {
        "status": "backtest_started",
        "symbol": symbol if not all_pairs else "all_pairs",
        "timeframe": timeframe,
        "days": days,
        "note": "Results will be logged and saved to backtest_reports/"
    }


@app.on_event("startup")
async def startup_event():
    global engine, scheduler, orchestrator, telegram, health_checker, metrics

    logger.info("=" * 60)
    logger.info("🟢 ARUNABHA ALGO BOT v4.1 — Starting up...")
    logger.info("=" * 60)

    try:
        # Config validation
        from config import ConfigValidator
        try:
            ConfigValidator.validate_all()
            logger.info("✅ Config validation passed")
        except ValueError as e:
            logger.error(f"❌ Config validation failed: {e}")
            raise

        # Telegram — token missing হলেও crash করবে না (BUG-25 fixed)
        logger.info("📱 Initializing Telegram...")
        telegram = TelegramNotifier()
        await telegram.start()
        logger.info(
            f"✅ Telegram started (available={telegram.is_available()})"
        )

        # Engine
        logger.info("⚙️ Initializing Engine...")
        engine = ArunabhaEngine(telegram)

        # Scheduler
        logger.info("⏰ Initializing Scheduler...")
        scheduler = TradingScheduler(engine)

        # Orchestrator
        logger.info("🔄 Initializing Orchestrator...")
        orchestrator = Orchestrator(engine, scheduler, telegram)

        # Monitoring
        health_checker = HealthChecker(engine, scheduler)
        metrics = MetricsCollector(engine)

        # Send startup message (non-blocking)
        try:
            await telegram.send_startup()
        except Exception as e:
            logger.warning(f"⚠️ Startup message failed (non-fatal): {e}")

        # ✅ FIX BUG-23: engine.start() — REST + Cache + BTC fetch + WebSocket
        logger.info("🚀 Starting Engine...")
        await engine.start()

        # Scheduler in background
        asyncio.create_task(scheduler.start())

        # BTC monitor
        asyncio.create_task(monitor_btc_data())

        logger.info("=" * 60)
        logger.info("✅ All systems running!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        logger.exception(e)
        raise


async def monitor_btc_data():
    """Periodically check and refresh BTC data"""
    while True:
        await asyncio.sleep(60)
        if engine:
            ready = engine._btc_data_ready
            count = len(engine.btc_cache.get("15m", []))
            logger.info(f"📊 BTC: ready={ready}, candles={count}")
            if not ready and count < 30:
                logger.info("🔄 Retrying BTC data fetch...")
                asyncio.create_task(engine._force_fetch_btc_data())


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🔴 Bot shutting down...")
    if engine:
        await engine.stop()
    if scheduler:
        await scheduler.stop()
    if telegram:
        await telegram.send_message("🛑 Bot shutting down...")
        await telegram.stop()
    logger.info("✅ Shutdown complete")


# ==================== CLI Modes ====================

async def run_worker():
    """Worker mode — no HTTP server, background tasks only"""
    global engine, scheduler, orchestrator, telegram

    logger.info("Starting in WORKER mode...")

    from config import ConfigValidator
    ConfigValidator.validate_all()

    telegram = TelegramNotifier()
    await telegram.start()

    engine = ArunabhaEngine(telegram)
    scheduler = TradingScheduler(engine)
    orchestrator = Orchestrator(engine, scheduler, telegram)

    await telegram.send_startup()
    await engine.start()
    await scheduler.start()

    try:
        while True:
            await asyncio.sleep(60)
            if engine:
                s = engine.get_status()
                logger.info(
                    f"📊 BTC={s['btc_data_ready']} "
                    f"Market={s['market_type']} "
                    f"Signals={s['daily_signals']}"
                )
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    finally:
        await engine.stop()
        await scheduler.stop()
        await telegram.send_message("🛑 Worker stopped")
        await telegram.stop()


# ✅ FIX BUG-26: Backtest mode — CLI থেকে run করা যাবে
async def run_backtest(args):
    """Backtest mode — fetch historical data and run strategy"""
    from backtest.backtest_runner import run_backtest_cli

    logger.info("=" * 60)
    logger.info("📊 BACKTEST MODE")
    logger.info("=" * 60)

    result = await run_backtest_cli(args)

    if "error" in result:
        logger.error(f"❌ Backtest failed: {result['error']}")
    elif isinstance(result, dict) and "summary" in result:
        s = result["summary"]
        logger.info(f"\n{'='*50}")
        logger.info(f"✅ BACKTEST COMPLETE: {result['symbol']}")
        logger.info(f"   Trades:        {s['total_trades']}")
        logger.info(f"   Win Rate:      {s['win_rate']:.1f}%")
        logger.info(f"   Total Return:  {s['total_return_pct']:+.2f}%")
        logger.info(f"   Profit Factor: {s['profit_factor']:.2f}")
        logger.info(f"   Sharpe Ratio:  {s['sharpe_ratio']:.2f}")
        logger.info(f"   Max Drawdown:  {s['max_drawdown_pct']:.2f}%")
        logger.info(f"{'='*50}")
        if result.get("report_files"):
            logger.info(f"📁 Reports saved:")
            for fmt, path in result["report_files"].items():
                logger.info(f"   {fmt}: {path}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="ARUNABHA ALGO BOT v4.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                  # Web server (default)
  python main.py --mode worker                    # Background worker
  python main.py --mode backtest --symbol ETH/USDT --days 30
  python main.py --mode backtest --all-pairs --days 60 --timeframe 1h
        """
    )

    parser.add_argument(
        "--mode",
        choices=["web", "worker", "backtest"],
        default="web",
        help="Run mode (default: web)"
    )

    # ✅ FIX BUG-26: Backtest CLI arguments
    backtest_group = parser.add_argument_group("Backtest options")
    backtest_group.add_argument(
        "--symbol",
        default="BTC/USDT",
        help="Symbol to backtest (default: BTC/USDT)"
    )
    backtest_group.add_argument(
        "--timeframe",
        default="15m",
        choices=["5m", "15m", "1h", "4h"],
        help="Candle timeframe (default: 15m)"
    )
    backtest_group.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backtest (default: 30)"
    )
    backtest_group.add_argument(
        "--all-pairs",
        action="store_true",
        help="Backtest all configured trading pairs"
    )
    backtest_group.add_argument(
        "--start-date",
        default=None,
        help="Start date YYYY-MM-DD (optional)"
    )
    backtest_group.add_argument(
        "--end-date",
        default=None,
        help="End date YYYY-MM-DD (optional)"
    )
    backtest_group.add_argument(
        "--report-format",
        default="all",
        choices=["txt", "csv", "json", "html", "all"],
        help="Report output format (default: all)"
    )

    args = parser.parse_args()

    if args.mode == "worker":
        asyncio.run(run_worker())

    elif args.mode == "backtest":
        asyncio.run(run_backtest(args))

    else:
        # Web server mode
        port = int(os.getenv("PORT", "8080"))
        logger.info(f"🌐 Starting web server on port {port}")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level="info"
        )


if __name__ == "__main__":
    main()
