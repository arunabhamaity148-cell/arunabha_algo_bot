"""
ARUNABHA ALGO BOT v4.0 - Master Configuration
All settings in one place
"""

import os
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Initialize logger first
logger = logging.getLogger(__name__)

# ==================== Environment ====================

ENV = os.getenv("ENVIRONMENT", "development")
DEBUG = ENV == "development"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ==================== Telegram ====================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    logger.error("Telegram credentials not set in environment")
    if ENV == "development":
        raise ValueError("Telegram credentials not set in environment")

# ==================== Exchange ====================

PRIMARY_EXCHANGE = "binance"
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")

# For Indian profit calculation
INDIAN_EXCHANGE = "CoinDCX"
TDS_RATE = 1.0  # 1% TDS on profit
GST_RATE = 18.0  # 18% GST on brokerage

# ==================== Trading Pairs ====================

TRADING_PAIRS: List[str] = [
    "BTC/USDT",
    "ETH/USDT", 
    "DOGE/USDT",
    "SOL/USDT",
    "RENDER/USDT"
]

TIMEFRAMES: List[str] = ["5m", "15m", "1h", "4h"]
PRIMARY_TF = "15m"
SECONDARY_TFS = ["5m", "1h"]
TERTIARY_TFS = ["4h"]

# ==================== Capital & Risk ====================

ACCOUNT_SIZE = float(os.getenv("ACCOUNT_SIZE", "100000"))  # ₹1,00,000
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "1.0"))  # 1% = ₹1000
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "15"))

# Position sizing
MAX_POSITION_PCT = 30  # Max 30% of account in one trade
MIN_POSITION_SIZE = 10  # Minimum $10 position

# ==================== Trade Limits ====================

MAX_CONCURRENT = 1  # Only one trade at a time (manual)
MAX_SIGNALS_PER_DAY = {
    "default": 4,
    "trending": 5,
    "choppy": 3,
    "high_vol": 2,
    "after_2_losses": 1
}

SESSION_SIGNAL_LIMITS = {
    "asia": 1,
    "london": 2,
    "ny": 2,
    "overlap": 1
}

# ==================== ATR Settings ====================

ATR_PERIOD = 14
ATR_SL_MULT = 1.5  # Stop Loss multiplier
ATR_TP_MULT = 3.0  # Take Profit multiplier
MIN_ATR_PCT = 0.4  # Min ATR % for trade
MAX_ATR_PCT = 3.0  # Max ATR % for trade

# ==================== Risk Management ====================

MAX_DAILY_DRAWDOWN_PCT = -2.0  # Stop after -2% in a day
MAX_CONSECUTIVE_LOSSES = 2  # Stop after 2 consecutive losses
BREAK_EVEN_AT_R = 0.5  # Move SL to entry at 0.5R
PARTIAL_EXIT_AT_R = 1.0  # Take 50% profit at 1.0R
COOLDOWN_MINUTES = 15  # Wait 15 min after trade

# ==================== Filters ====================

# Tier 1: Mandatory filters (must pass all)
TIER1_FILTERS = [
    "btc_regime",
    "structure",
    "volume",
    "liquidity", 
    "session"
]

# Tier 2: Quality filters (weighted scoring)
TIER2_FILTERS = {
    "mtf_confirmation": 20,
    "volume_profile": 15,
    "funding_rate": 10,
    "open_interest": 10,
    "rsi_divergence": 15,
    "ema_stack": 10,
    "atr_percent": 10,
    "vwap_position": 5,
    "support_resistance": 5
}

# Tier 3: Bonus filters
TIER3_FILTERS = [
    "whale_movement",
    "liquidity_grab",
    "iceberg_detection",
    "news_sentiment",
    "correlation_break",
    "fibonacci_level"
]

# Filter thresholds
MIN_TIER2_SCORE = 60  # Need 60% to pass
MIN_TIER3_BONUS = 0  # Bonus points add to score

# ==================== Signal Scoring ====================

SIGNAL_GRADES = {
    "A+": 90,
    "A": 80,
    "B+": 70,
    "B": 60,
    "C": 50,
    "D": 0
}

MIN_SIGNAL_SCORE = 60  # Minimum score for any signal
STRONG_SIGNAL_SCORE = 75  # Score for strong signal
MIN_RR_RATIO = 1.5  # Minimum Risk-Reward Ratio
ENTRY_CONFIRMATION_WAIT = True  # Wait for confirmation

# ==================== Market Regime ====================

MARKET_CONFIGS = {
    "trending": {
        "min_score": 65,
        "min_filters": 3,
        "min_rr": 2.0,
        "max_signals": 5,
        "position_size": 1.0,
        "sl_mult": 1.5,
        "tp_mult": 3.0
    },
    "choppy": {
        "min_score": 60,
        "min_filters": 2,
        "min_rr": 1.5,
        "max_signals": 3,
        "position_size": 0.8,
        "sl_mult": 1.2,
        "tp_mult": 1.8
    },
    "high_vol": {
        "min_score": 75,
        "min_filters": 4,
        "min_rr": 2.5,
        "max_signals": 2,
        "position_size": 0.5,
        "sl_mult": 1.0,
        "tp_mult": 2.5
    }
}

# ==================== BTC Regime ====================

BTC_REGIME_CONFIG = {
    "hard_block_confidence": 8,
    "choppy_min_confidence": 15,
    "trend_min_confidence": 20,
    "choppy_adx_min": 18,
    "trend_adx_min": 20
}

# ==================== Technical Indicators ====================

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 200

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

BB_PERIOD = 20
BB_STD = 2

VOLUME_MA_PERIOD = 20
VOLUME_MULT = 1.2

# ==================== Confidence Thresholds ====================

CONFIDENCE = {
    "MIN_CONFIDENCE_ALLOW": 25,      # ২৫% কনফিডেন্স থাকলে ট্রেড করতে দেবে
    "MIN_CONFIDENCE_DIRECTION": 30,   # ডিরেকশন মিসম্যাচ হলেও ট্রেড করবে
    "MIN_CONFIDENCE_FORCE": 20,       # ফোর্স ট্রেডের জন্য
    "ADX_HIGH_CONFIDENCE": 25,        # ADX ২৫+ হলে হাই কনফিডেন্স
    "ADX_MED_CONFIDENCE": 20,         # ADX ২০-২৫ মিড কনফিডেন্স
}

# ==================== Sessions (IST) ====================

SESSIONS = {
    "asia": (7, 11),      # 7AM - 11AM IST
    "london": (13, 17),   # 1PM - 5PM IST
    "ny": (18, 22),       # 6PM - 10PM IST
    "overlap": (22, 24)   # 10PM - 12AM IST
}

BEST_TIMES = [
    (13, 15, "London Open"),
    (18, 20, "NY Open"),
    (7, 9, "Asia Open")
]

AVOID_TIMES = [
    (10, 11, "Lunch"),
    (23, 1, "Dead Zone")
]

# ==================== Fear & Greed ====================

FEAR_GREED_API_URL = "https://api.alternative.me/fng/?limit=1"
FEAR_INDEX_STOP = 75  # Don't trade above 75 (extreme greed)

# ==================== WebSocket ====================

WS_RECONNECT_DELAY = 5  # Seconds
WS_MAX_RETRIES = 10
WS_PING_INTERVAL = 20

# ==================== Cache ====================

CACHE_SIZE = 100  # Candles per symbol per timeframe
REDIS_URL = os.getenv("REDIS_URL", None)
USE_REDIS = REDIS_URL is not None

# ==================== Webhook ====================

WEBHOOK_PORT = int(os.getenv("PORT", "8080"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default-secret-change-this")

# ==================== Profit Target ====================

DAILY_PROFIT_TARGET = 500  # ₹500 per day
WEEKLY_PROFIT_TARGET = 2500  # ₹2500 per week
MONTHLY_PROFIT_TARGET = 10000  # ₹10000 per month

# ==================== Crash Mode ====================

CRASH_MODE = {
    "ACTIVE": False,  # True করলে ক্র্যাশ মোড চালু হবে
    "MIN_CONFIDENCE": 15,
    "RISK_MULTIPLIER": 0.5,
    "MAX_POSITION_SIZE": 0.3,
    "PREFER_SHORTS": True
}

# ==================== Logging ====================

LOG_FILE = "bot.log"
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# ==================== Validation ====================

@dataclass
class ConfigValidator:
    """Validate configuration on startup"""
    
    @classmethod
    def validate_all(cls):
        """Run all validations"""
        cls.validate_telegram()
        cls.validate_exchange()
        cls.validate_risk()
        cls.validate_filters()
        logger.info("✅ All configurations valid")
    
    @classmethod
    def validate_telegram(cls):
        if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
            raise ValueError("Invalid TELEGRAM_BOT_TOKEN")
        if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "your_chat_id_here":
            raise ValueError("Invalid TELEGRAM_CHAT_ID")
    
    @classmethod
    def validate_exchange(cls):
        if ENV == "production":
            if not BINANCE_API_KEY or BINANCE_API_KEY == "your_binance_api_key":
                raise ValueError("BINANCE_API_KEY required in production")
            if not BINANCE_SECRET or BINANCE_SECRET == "your_binance_secret":
                raise ValueError("BINANCE_SECRET required in production")
    
    @classmethod
    def validate_risk(cls):
        if ACCOUNT_SIZE <= 0:
            raise ValueError("ACCOUNT_SIZE must be positive")
        if RISK_PER_TRADE <= 0 or RISK_PER_TRADE > 5:
            raise ValueError("RISK_PER_TRADE must be between 0 and 5")
        if MAX_LEVERAGE <= 0 or MAX_LEVERAGE > 20:
            raise ValueError("MAX_LEVERAGE must be between 1 and 20")
    
    @classmethod
    def validate_filters(cls):
        if MIN_TIER2_SCORE < 0 or MIN_TIER2_SCORE > 100:
            raise ValueError("MIN_TIER2_SCORE must be between 0 and 100")
        if MIN_SIGNAL_SCORE < 0 or MIN_SIGNAL_SCORE > 100:
            raise ValueError("MIN_SIGNAL_SCORE must be between 0 and 100")

# ==================== Profit Calculation ====================

def calculate_indian_profit(entry: float, exit: float, qty: float, side: str) -> Dict[str, float]:
    """Calculate profit after TDS/GST for Indian exchanges"""
    if side == "LONG":
        gross_pnl = (exit - entry) * qty
    else:
        gross_pnl = (entry - exit) * qty
    
    if gross_pnl <= 0:
        return {"net_pnl": gross_pnl, "tds": 0, "gst": 0, "gross": gross_pnl}
    
    tds = gross_pnl * (TDS_RATE / 100)
    gst = gross_pnl * (GST_RATE / 100)  # Simplified, actual calculation differs
    net_pnl = gross_pnl - tds - gst
    
    return {
        "gross": round(gross_pnl, 2),
        "tds": round(tds, 2),
        "gst": round(gst, 2),
        "net_pnl": round(net_pnl, 2)
    }

# Run validation on import
logger.info("Loading configuration...")
ConfigValidator.validate_all()
logger.info("Configuration loaded successfully")
