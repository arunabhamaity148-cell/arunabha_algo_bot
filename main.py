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

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger("main")

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
    return {
        "bot": "ARUNABHA ALGO BOT",
        "version": "4.0",
        "status": "running",
        "auto_trade": False,
        "manual_signals": True
    }

@app.get("/health")
async def health():
    """Health check endpoint for Railway"""
    if health_checker:
        return await health_checker.check()
    return {"status": "ok", "message": "Health checker not initialized"}

@app.get("/metrics")
async def get_metrics():
    """Performance metrics endpoint"""
    if metrics:
        return await metrics.get_all()
    return {"message": "Metrics not available"}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    """Webhook endpoint for external signals"""
    if secret != os.getenv("WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    data = await request.json()
    logger.info(f"Webhook received: {data}")
    
    # Process webhook data
    if orchestrator:
        await orchestrator.process_webhook(data)
    
    return {"status": "received"}

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    global engine, scheduler, orchestrator, telegram, health_checker, metrics
    
    logger.info("=" * 60)
    logger.info("ARUNABHA ALGO BOT v4.0 - Starting up...")
    logger.info("=" * 60)
    
    try:
        # Initialize components
        telegram = TelegramNotifier()
        engine = ArunabhaEngine(telegram)
        scheduler = TradingScheduler(engine)
        orchestrator = Orchestrator(engine, scheduler, telegram)
        health_checker = HealthChecker(engine, scheduler)
        metrics = MetricsCollector(engine)
        
        # Send startup notification with error handling
        logger.info("📱 Attempting to send startup message to Telegram...")
        try:
            await telegram.send_startup()
            logger.info("✅ Startup message sent successfully to Telegram")
        except Exception as e:
            logger.error(f"❌ Failed to send startup message: {e}")
            logger.exception(e)
        
        # Start scheduler in background
        asyncio.create_task(scheduler.start())
        
        logger.info("✅ Bot initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        logger.exception(e)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Bot shutting down...")
    
    if scheduler:
        await scheduler.stop()
    
    if telegram:
        await telegram.send_message("🛑 Bot shutting down...")
    
    logger.info("Bot shutdown complete")

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
            log_level="info"
        )

if __name__ == "__main__":
    main()
