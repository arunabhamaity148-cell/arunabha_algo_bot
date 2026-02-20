"""
ARUNABHA ALGO BOT - Main Engine
Orchestrates all components and generates signals
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import config
from core.constants import (
    MarketType, TradeDirection, SignalGrade, Timeframes,
    BTCRegime, SessionType, ERROR_MESSAGES
)
from data.websocket_manager import WebSocketManager
from data.rest_client import RESTClient
from data.cache_manager import CacheManager
from analysis.market_regime import MarketRegimeDetector
from analysis.technical import TechnicalAnalyzer
from analysis.structure import StructureDetector
from analysis.volume_profile import VolumeProfileAnalyzer
from filters.filter_orchestrator import FilterOrchestrator
from risk.risk_manager import RiskManager
from signals.signal_generator import SignalGenerator
from notification.telegram_bot import TelegramNotifier
from monitoring.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class ArunabhaEngine:
    """
    Main engine that coordinates all components
    """
    
    def __init__(self, telegram: Optional[TelegramNotifier] = None):
        self.telegram = telegram or TelegramNotifier()
        
        # Initialize components
        self.ws_manager = WebSocketManager(self._on_candle_close)
        self.rest_client = RESTClient()
        self.cache = CacheManager()
        
        self.regime_detector = MarketRegimeDetector()
        self.technical = TechnicalAnalyzer()
        self.structure = StructureDetector()
        self.volume = VolumeProfileAnalyzer()
        
        self.filter_orchestrator = FilterOrchestrator()
        self.risk_manager = RiskManager()
        self.signal_generator = SignalGenerator()
        
        self.metrics = MetricsCollector(self)
        
        # State
        self.market_type = MarketType.UNKNOWN
        self.btc_regime = BTCRegime.UNKNOWN
        self.last_signal_time: Dict[str, datetime] = {}
        self.daily_signals = 0
        self.consecutive_losses = 0
        
        logger.info("Engine initialized")
    
    async def start(self):
        """Start the engine"""
        logger.info("Starting engine...")
        
        # Connect to exchange
        await self.rest_client.connect()
        
        # Seed cache with historical data
        await self._seed_cache()
        
        # Start WebSocket
        await self.ws_manager.start()
        
        # Initial regime detection
        await self._update_regime()
        
        logger.info("Engine started")
    
    async def stop(self):
        """Stop the engine"""
        logger.info("Stopping engine...")
        
        await self.ws_manager.stop()
        await self.rest_client.close()
        
        logger.info("Engine stopped")
    
    async def _seed_cache(self):
        """Pre-fill cache with historical data"""
        logger.info("Seeding cache with historical data...")
        
        for symbol in config.TRADING_PAIRS:
            for tf in config.TIMEFRAMES:
                try:
                    candles = await self.rest_client.fetch_ohlcv(
                        symbol, tf, limit=config.CACHE_SIZE
                    )
                    if candles:
                        self.cache.set_ohlcv(symbol, tf, candles)
                        logger.debug(f"Seeded {symbol} {tf}: {len(candles)} candles")
                except Exception as e:
                    logger.warning(f"Failed to seed {symbol} {tf}: {e}")
        
        logger.info("Cache seeding complete")
    
    async def _update_regime(self):
        """Update market regime and BTC regime"""
        try:
            # Get BTC data
            btc_15m = self.cache.get_ohlcv("BTC/USDT", Timeframes.M15)
            btc_1h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H1)
            btc_4h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H4)
            
            if not btc_15m or len(btc_15m) < 30:
                logger.warning("Insufficient BTC data for regime detection")
                return
            
            # Detect regimes
            self.market_type = self.regime_detector.detect_market_type(btc_15m, btc_1h)
            self.btc_regime = self.regime_detector.detect_btc_regime(btc_15m, btc_1h, btc_4h)
            
            logger.info(f"Market: {self.market_type.value} | BTC: {self.btc_regime.value}")
            
        except Exception as e:
            logger.error(f"Regime update failed: {e}")
    
    async def _on_candle_close(self, symbol: str, tf: str, candles: List[List[float]]):
        """
        Callback when candle closes
        This is where signals are generated
        """
        if tf != config.PRIMARY_TF:
            return
        
        try:
            # Update cache
            self.cache.set_ohlcv(symbol, tf, candles)
            
            # Check if we can trade
            if not await self._can_process_signal(symbol):
                return
            
            # Update regime every hour
            if datetime.now().minute == 0:
                await self._update_regime()
            
            # Generate signal
            signal = await self._generate_signal(symbol, candles)
            
            if signal:
                await self._process_signal(signal)
                
        except Exception as e:
            logger.error(f"Error processing candle close for {symbol}: {e}")
    
    async def _can_process_signal(self, symbol: str) -> bool:
        """Check if we can process a signal"""
        
        # Check daily limit
        if self.daily_signals >= self._get_daily_limit():
            logger.debug(f"Daily signal limit reached: {self.daily_signals}")
            return False
        
        # Check cooldown
        if symbol in self.last_signal_time:
            elapsed = (datetime.now() - self.last_signal_time[symbol]).total_seconds() / 60
            if elapsed < config.COOLDOWN_MINUTES:
                logger.debug(f"Cooldown for {symbol}: {elapsed:.1f}/{config.COOLDOWN_MINUTES}")
                return False
        
        # Check risk manager
        if not self.risk_manager.can_trade(symbol):
            logger.debug(f"Risk manager blocked {symbol}")
            return False
        
        return True
    
    def _get_daily_limit(self) -> int:
        """Get daily signal limit based on market type"""
        limits = config.MAX_SIGNALS_PER_DAY
        
        if self.consecutive_losses >= 2:
            return limits["after_2_losses"]
        
        return limits.get(self.market_type.value, limits["default"])
    
    async def _generate_signal(self, symbol: str, candles_15m: List[List[float]]) -> Optional[Dict]:
        """Generate signal for a symbol"""
        
        # Get all required data
        data = await self._get_all_data(symbol)
        if not data:
            return None
        
        # Apply filters
        filter_result = await self.filter_orchestrator.evaluate(
            symbol=symbol,
            direction=None,  # Will be determined
            market_type=self.market_type,
            btc_regime=self.btc_regime,
            data=data
        )
        
        if not filter_result["passed"]:
            logger.debug(f"Filters failed for {symbol}: {filter_result['reason']}")
            return None
        
        # Generate signal
        signal = await self.signal_generator.generate(
            symbol=symbol,
            data=data,
            filter_result=filter_result,
            market_type=self.market_type,
            btc_regime=self.btc_regime
        )
        
        return signal
    
    async def _get_all_data(self, symbol: str) -> Optional[Dict]:
        """Get all required data for signal generation"""
        
        try:
            # Get OHLCV data
            ohlcv_5m = self.cache.get_ohlcv(symbol, Timeframes.M5)
            ohlcv_15m = self.cache.get_ohlcv(symbol, Timeframes.M15)
            ohlcv_1h = self.cache.get_ohlcv(symbol, Timeframes.H1)
            ohlcv_4h = self.cache.get_ohlcv(symbol, Timeframes.H4)
            
            # Get BTC data
            btc_15m = self.cache.get_ohlcv("BTC/USDT", Timeframes.M15)
            btc_1h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H1)
            btc_4h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H4)
            
            # Validate data
            if not all([ohlcv_15m, btc_15m]):
                logger.warning(f"Insufficient data for {symbol}")
                return None
            
            # Get other data
            funding = await self.rest_client.fetch_funding_rate(symbol)
            oi = await self.rest_client.fetch_open_interest(symbol)
            orderbook = await self.rest_client.fetch_orderbook(symbol)
            
            return {
                "symbol": symbol,
                "ohlcv": {
                    "5m": ohlcv_5m,
                    "15m": ohlcv_15m,
                    "1h": ohlcv_1h,
                    "4h": ohlcv_4h
                },
                "btc": {
                    "15m": btc_15m,
                    "1h": btc_1h,
                    "4h": btc_4h
                },
                "funding_rate": funding,
                "open_interest": oi,
                "orderbook": orderbook,
                "current_price": ohlcv_15m[-1][4] if ohlcv_15m else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting data for {symbol}: {e}")
            return None
    
    async def _process_signal(self, signal: Dict):
        """Process and send signal"""
        
        # Calculate position size
        position = self.risk_manager.calculate_position(
            account_size=config.ACCOUNT_SIZE,
            entry=signal["entry"],
            stop_loss=signal["stop_loss"],
            atr_pct=signal.get("atr_pct", 1.0),
            fear_index=signal.get("fear_index", 50)
        )
        
        if position.get("blocked"):
            logger.warning(f"Position sizing blocked: {position.get('reason')}")
            return
        
        signal["position"] = position
        
        # Update state
        symbol = signal["symbol"]
        self.last_signal_time[symbol] = datetime.now()
        self.daily_signals += 1
        
        # Send notification
        await self.telegram.send_signal(signal, self.market_type)
        
        # Update metrics
        await self.metrics.record_signal(signal)
        
        logger.info(
            f"✅ Signal generated: {symbol} {signal['direction']} "
            f"@ {signal['entry']:.2f} | Score: {signal['score']} | "
            f"Grade: {signal['grade']}"
        )
    
    async def on_trade_result(self, symbol: str, pnl_pct: float):
        """Called when a trade is closed"""
        
        if pnl_pct < 0:
            self.consecutive_losses += 1
            logger.warning(f"Loss #{self.consecutive_losses}: {symbol} @ {pnl_pct:.2f}%")
        else:
            self.consecutive_losses = 0
            logger.info(f"Win: {symbol} @ {pnl_pct:.2f}%")
        
        # Update risk manager
        self.risk_manager.update_daily_pnl(pnl_pct)
    
    def reset_daily(self):
        """Reset daily counters"""
        self.daily_signals = 0
        self.consecutive_losses = 0
        self.risk_manager.reset_daily()
        logger.info("Daily counters reset")
    
    def get_status(self) -> Dict:
        """Get engine status"""
        return {
            "market_type": self.market_type.value,
            "btc_regime": self.btc_regime.value,
            "daily_signals": self.daily_signals,
            "daily_limit": self._get_daily_limit(),
            "consecutive_losses": self.consecutive_losses,
            "active_trades": self.risk_manager.active_trades_count,
            "daily_pnl": self.risk_manager.daily_pnl,
            "day_locked": self.risk_manager.day_locked
        }
