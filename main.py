"""
ARUNABHA ALGO BOT v4.0 - Main Entry Point
Railway-ready, Auto-trade OFF, Manual signals only
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

# ==================== FORCE LOGGING SETUP ====================
# Clear any existing handlers
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Configure logging to show EVERYTHING
logging.basicConfig(
    level=logging.DEBUG,  # DEBUG level to see everything
    format='%(asctime)s.%(msecs)03d | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Print to console
        logging.FileHandler('bot.log')      # Save to file
    ]
)

# Set specific log levels
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('ccxt').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)

logger = logging.getLogger("main")
logger.info("=" * 80)
logger.info(f"🚀 ARUNABHA ALGO BOT v4.0 - Starting at {datetime.now().isoformat()}")
logger.info("=" * 80)

# Import core modules
from core.engine import ArunabhaEngine
from core.scheduler import TradingScheduler
from core.orchestrator import Orchestrator
from notification.telegram_bot import TelegramNotifier
from monitoring.health_check import HealthChecker
from monitoring.metrics_collector import MetricsCollector

# Initialize FastAPI
app = FastAPI(title="ARUNABHA ALGO BOT", version="4.0")

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
            "version": "4.0",
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
    
    # Simple health response
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
            recent = all_lines[-lines:]
            return {"logs": recent}
    except:
        return {"logs": ["Log file not found"]}

@app.get("/debug")
async def debug_status():
    """Debug endpoint to see all status"""
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
    
    # Process webhook data
    if orchestrator:
        await orchestrator.process_webhook(data)
    
    return {"status": "received"}

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    global engine, scheduler, orchestrator, telegram, health_checker, metrics
    
    logger.info("=" * 60)
    logger.info("🟢 ARUNABHA ALGO BOT v4.0 - Starting up...")
    logger.info("=" * 60)
    
    try:
        # Initialize components
        logger.info("📱 Initializing Telegram notifier...")
        telegram = TelegramNotifier()
        
        logger.info("⚙️ Initializing Engine...")
        engine = ArunabhaEngine(telegram)
        
        logger.info("⏰ Initializing Scheduler...")
        scheduler = TradingScheduler(engine)
        
        logger.info("🔄 Initializing Orchestrator...")
        orchestrator = Orchestrator(engine, scheduler, telegram)
        
        logger.info("🏥 Initializing Health Checker...")
        health_checker = HealthChecker(engine, scheduler)
        
        logger.info("📊 Initializing Metrics Collector...")
        metrics = MetricsCollector(engine)
        
        # Send startup notification
        logger.info("📱 Attempting to send startup message to Telegram...")
        try:
            await telegram.send_startup()
            logger.info("✅ Startup message sent successfully to Telegram")
        except Exception as e:
            logger.error(f"❌ Failed to send startup message: {e}")
        
        # Start scheduler in background
        logger.info("⏰ Starting scheduler...")
        asyncio.create_task(scheduler.start())
        
        # Start BTC monitor
        logger.info("📡 Starting BTC data monitor...")
        asyncio.create_task(monitor_btc_data())
        
        logger.info("✅ Bot initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        logger.exception(e)
        raise

async def monitor_btc_data():
    """Monitor BTC data status periodically"""
    while True:
        await asyncio.sleep(60)  # Check every minute
        
        if engine:
            btc_ready = engine._btc_data_ready
            btc_count = len(engine.btc_cache.get("15m", []))
            
            logger.info(f"📊 BTC Status: Ready={btc_ready}, Candles={btc_count}")
            
            if not btc_ready and btc_count < 50:
                logger.warning(f"⚠️ Still waiting for BTC data: {btc_count}/50 candles")
                
                # Force fetch if needed
                if btc_count < 30:
                    logger.info("🔄 Force fetching BTC data...")
                    asyncio.create_task(engine._force_fetch_btc_data())

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🔴 Bot shutting down...")
    
    if scheduler:
        await scheduler.stop()
    
    if telegram:
        await telegram.send_message("🛑 Bot shutting down...")
    
    logger.info("✅ Bot shutdown complete")

# ==================== CLI Mode ====================

async def run_worker():
    """Run in worker mode (background tasks only)"""
    global engine, scheduler, orchestrator, telegram
    
    logger.info("Starting in WORKER mode...")
    
    telegram = TelegramNotifier()
    engine = ArunabhaEngine(telegram)
    scheduler = TradingScheduler(engine)
    orchestrator = Orchestrator(engine, scheduler, telegram)
    
    await telegram.send_startup()
    await scheduler.start()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
            # Log status every minute
            if engine:
                status = engine.get_status()
                logger.info(f"📊 Status: BTC={status.get('btc_data_ready')}, Market={status.get('market_type')}, Signals={status.get('daily_signals')}")
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    finally:
        await scheduler.stop()
        await telegram.send_message("🛑 Worker stopped")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="ARUNABHA ALGO BOT")
    parser.add_argument("--mode", choices=["web", "worker"], default="web",
                       help="Run mode: web (default) or worker")
    
    args = parser.parse_args()
    
    if args.mode == "worker":
        asyncio.run(run_worker())
    else:
        # Web mode - run FastAPI
        port = int(os.getenv("PORT", "8080"))
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level="debug"  # Set to debug
        )

if __name__ == "__main__":
    main()