"""
ARUNABHA ALGO BOT v4.1 - Main Entry Point
Railway-ready, Auto-trade OFF, Manual signals only

FIXES:
- BUG-23: engine.start() এখন startup_event এ call হচ্ছে
- BUG-24: telegram.start() এখন startup_event এ call হচ্ছে
- Config validation explicitly এখানে হচ্ছে
"""

import os
import sys
import asyncio
import logging
import argparse
from typing import Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

# Load environment variables
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
logger.info(f"🚀 ARUNABHA ALGO BOT v4.1 - Starting at {datetime.now().isoformat()}")
logger.info("=" * 80)

# Import core modules
from core.engine import ArunabhaEngine
from core.scheduler import TradingScheduler
from core.orchestrator import Orchestrator
from notification.telegram_bot import TelegramNotifier
from monitoring.health_check import HealthChecker
from monitoring.metrics_collector import MetricsCollector

# Initialize FastAPI
app = FastAPI(title="ARUNABHA ALGO BOT", version="4.1")

# Global instances
engine: Optional[ArunabhaEngine] = None
scheduler: Optional[TradingScheduler] = None
orchestrator: Optional[Orchestrator] = None
telegram: Optional[TelegramNotifier] = None
health_checker: Optional[HealthChecker] = None
metrics: Optional[MetricsCollector] = None


# ==================== FastAPI Routes ====================

@app.get("/")
async def root():
    """Root endpoint - Bot status"""
    if engine:
        status = engine.get_status()
        return {
            "bot": "ARUNABHA ALGO BOT",
            "version": "4.1",
            "status": "running",
            "btc_data_ready": status.get("btc_data_ready", False),
            "btc_candles": status.get("btc_candles", 0),
            "market": status.get("market_type", "unknown"),
            "daily_signals": status.get("daily_signals", 0),
            "auto_trade": False,
            "manual_signals": True
        }
    return {"status": "initializing"}


@app.get("/health")
async def health():
    """Health check endpoint for Railway"""
    if health_checker:
        return await health_checker.check()

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "btc_data_ready": engine._btc_data_ready if engine else False,
        "btc_candles": len(engine.btc_cache.get("15m", [])) if engine else 0
    }


@app.get("/logs")
async def get_logs(lines: int = 50):
    """View recent logs"""
    try:
        with open('bot.log', 'r') as f:
            all_lines = f.readlines()
            return {"logs": all_lines[-lines:]}
    except:
        return {"logs": ["Log file not found"]}


@app.get("/debug")
async def debug_status():
    """Debug endpoint"""
    if engine:
        return {
            "btc_data_ready": engine._btc_data_ready,
            "btc_15m_candles": len(engine.btc_cache.get("15m", [])),
            "btc_1h_candles": len(engine.btc_cache.get("1h", [])),
            "btc_4h_candles": len(engine.btc_cache.get("4h", [])),
            "market_type": str(engine.market_type),
            "daily_signals": engine.daily_signals,
            "last_signal_time": {k: v.isoformat() for k, v in engine.last_signal_time.items()}
        }
    return {"error": "Engine not initialized"}


@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    """Webhook endpoint for external signals"""
    if secret != os.getenv("WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    logger.info(f"📡 Webhook received: {data}")

    if orchestrator:
        await orchestrator.process_webhook(data)

    return {"status": "received"}


@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    global engine, scheduler, orchestrator, telegram, health_checker, metrics

    logger.info("=" * 60)
    logger.info("🟢 ARUNABHA ALGO BOT v4.1 - Starting up...")
    logger.info("=" * 60)

    try:
        # ✅ FIX BUG-04: Config validation এখানে explicitly করা হচ্ছে
        from config import ConfigValidator
        try:
            ConfigValidator.validate_all()
            logger.info("✅ Config validation passed")
        except ValueError as e:
            logger.error(f"❌ Config validation failed: {e}")
            raise

        # Initialize Telegram
        logger.info("📱 Initializing Telegram notifier...")
        telegram = TelegramNotifier()

        # ✅ FIX BUG-24: telegram.start() call করা হচ্ছে
        await telegram.start()
        logger.info("✅ Telegram notifier started")

        # Initialize Engine
        logger.info("⚙️ Initializing Engine...")
        engine = ArunabhaEngine(telegram)

        # Initialize Scheduler
        logger.info("⏰ Initializing Scheduler...")
        scheduler = TradingScheduler(engine)

        # Initialize Orchestrator
        logger.info("🔄 Initializing Orchestrator...")
        orchestrator = Orchestrator(engine, scheduler, telegram)

        # Initialize Health Checker
        logger.info("🏥 Initializing Health Checker...")
        health_checker = HealthChecker(engine, scheduler)

        # Initialize Metrics
        logger.info("📊 Initializing Metrics Collector...")
        metrics = MetricsCollector(engine)

        # Send startup notification
        try:
            await telegram.send_startup()
            logger.info("✅ Startup message sent to Telegram")
        except Exception as e:
            logger.error(f"❌ Failed to send startup message: {e}")

        # ✅ FIX BUG-23: engine.start() এখন explicitly call হচ্ছে
        # এটা ছাড়া: REST connect হয় না, cache seed হয় না, WebSocket চালু হয় না
        logger.info("🚀 Starting Engine (REST + WebSocket + Cache)...")
        await engine.start()
        logger.info("✅ Engine started successfully")

        # Start scheduler in background
        logger.info("⏰ Starting scheduler...")
        asyncio.create_task(scheduler.start())

        # Start BTC monitor
        logger.info("📡 Starting BTC data monitor...")
        asyncio.create_task(monitor_btc_data())

        logger.info("=" * 60)
        logger.info("✅ ARUNABHA ALGO BOT v4.1 - All systems running!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        logger.exception(e)
        raise


async def monitor_btc_data():
    """Monitor BTC data status periodically"""
    while True:
        await asyncio.sleep(60)

        if engine:
            btc_ready = engine._btc_data_ready
            btc_count = len(engine.btc_cache.get("15m", []))

            logger.info(f"📊 BTC Status: Ready={btc_ready}, Candles={btc_count}")

            if not btc_ready and btc_count < 50:
                logger.warning(f"⚠️ Still waiting for BTC data: {btc_count}/50 candles")
                if btc_count < 30:
                    logger.info("🔄 Force fetching BTC data...")
                    asyncio.create_task(engine._force_fetch_btc_data())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🔴 Bot shutting down...")

    if engine:
        await engine.stop()

    if scheduler:
        await scheduler.stop()

    if telegram:
        await telegram.send_message("🛑 Bot shutting down...")
        await telegram.stop()

    logger.info("✅ Bot shutdown complete")


# ==================== CLI Mode ====================

async def run_worker():
    """Run in worker mode"""
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

    # ✅ engine.start() worker mode এও call করা হচ্ছে
    await engine.start()
    await scheduler.start()

    try:
        while True:
            await asyncio.sleep(60)
            if engine:
                status = engine.get_status()
                logger.info(
                    f"📊 Status: BTC={status.get('btc_data_ready')}, "
                    f"Market={status.get('market_type')}, "
                    f"Signals={status.get('daily_signals')}"
                )
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    finally:
        await engine.stop()
        await scheduler.stop()
        await telegram.send_message("🛑 Worker stopped")
        await telegram.stop()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="ARUNABHA ALGO BOT")
    parser.add_argument("--mode", choices=["web", "worker"], default="web",
                        help="Run mode: web (default) or worker")

    args = parser.parse_args()

    if args.mode == "worker":
        asyncio.run(run_worker())
    else:
        port = int(os.getenv("PORT", "8080"))
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level="info"
        )


if __name__ == "__main__":
    main()
