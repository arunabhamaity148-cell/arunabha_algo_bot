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
from analysis.market_regime import MarketRegimeDetector, BTCRegimeResult
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
        self.btc_regime: Optional[BTCRegimeResult] = None
        self.last_signal_time: Dict[str, datetime] = {}
        self.daily_signals = 0
        self.consecutive_losses = 0
        
        # BTC Data cache (backup)
        self.btc_cache = {"15m": [], "1h": [], "4h": []}
        self._btc_data_ready = False
        self._btc_fetch_attempts = 0
        self._last_btc_check = None
        
        logger.info("🚀 Engine initialized")
    
    async def start(self):
        """Start the engine"""
        logger.info("🟢 Starting engine...")
        
        # Connect to exchange
        logger.info("🔌 Connecting to exchange...")
        await self.rest_client.connect()
        
        # Seed cache with historical data
        logger.info("🌱 Seeding cache with historical data...")
        await self._seed_cache()
        
        # Force BTC data fetch with retries
        logger.info("🔄 Force fetching BTC data...")
        btc_fetched = await self._force_fetch_btc_data()
        if btc_fetched:
            logger.info("✅ BTC data loaded successfully")
        else:
            logger.error("❌ BTC data failed to load - will retry in background")
            asyncio.create_task(self._background_btc_fetcher())
        
        # 🔴 ফোর্স ফেচ অল পেয়ারস
        logger.info("🔄 Force fetching ALL pairs data...")
        await self._force_fetch_all_pairs()
        
        # Start WebSocket
        logger.info("🔌 Starting WebSocket connection...")
        await self.ws_manager.start()
        
        # Initial regime detection
        await self._update_regime()
        
        logger.info("✅ Engine started successfully")
    
    async def _force_fetch_all_pairs(self):
        """Force fetch data for all trading pairs using REST API"""
        for symbol in config.TRADING_PAIRS:
            if symbol == "BTC/USDT":
                continue
            for tf in ["5m", "15m", "1h", "4h"]:
                try:
                    candles = await self.rest_client.fetch_ohlcv_rest(symbol, tf, 100)
                    if candles:
                        self.cache.set_ohlcv(symbol, tf, candles)
                        logger.info(f"✅ Pre-fetched {symbol} {tf}: {len(candles)} candles")
                    await asyncio.sleep(0.5)  # Rate limit avoidance
                except Exception as e:
                    logger.error(f"❌ Failed to fetch {symbol} {tf}: {e}")
    
    async def _force_fetch_btc_data(self) -> bool:
        """Force fetch BTC data with multiple retries and update cache"""
        for attempt in range(10):
            try:
                logger.info(f"🔄 [ATTEMPT {attempt+1}/10] Fetching BTC data...")
                
                # Fetch from REST API
                btc_15m = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "15m", 100)
                btc_1h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "1h", 50)
                btc_4h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "4h", 50)
                
                # Log what we got
                logger.info(f"   BTC 15m: {len(btc_15m) if btc_15m else 0} candles")
                logger.info(f"   BTC 1h: {len(btc_1h) if btc_1h else 0} candles")
                logger.info(f"   BTC 4h: {len(btc_4h) if btc_4h else 0} candles")
                
                if btc_15m and len(btc_15m) >= 50:
                    # Update engine cache (backup)
                    self.btc_cache["15m"] = btc_15m
                    self.btc_cache["1h"] = btc_1h if btc_1h else []
                    self.btc_cache["4h"] = btc_4h if btc_4h else []
                    
                    # Force update main cache
                    logger.info("   🔄 Force updating main cache...")
                    self.cache.set_ohlcv("BTC/USDT", "15m", btc_15m)
                    if btc_1h:
                        self.cache.set_ohlcv("BTC/USDT", "1h", btc_1h)
                    if btc_4h:
                        self.cache.set_ohlcv("BTC/USDT", "4h", btc_4h)
                    
                    # Verify cache
                    cache_check = self.cache.get_ohlcv("BTC/USDT", "15m")
                    if cache_check and len(cache_check) >= 50:
                        logger.info(f"✅ Cache verified: {len(cache_check)} candles for BTC 15m")
                        self._btc_data_ready = True
                    else:
                        logger.error(f"❌ Cache verification failed!")
                        continue
                    
                    # Update regime
                    await self._update_regime()
                    return True
                else:
                    logger.warning(f"   ⚠️ Only {len(btc_15m) if btc_15m else 0} candles - need 50")
                    
            except Exception as e:
                logger.error(f"   ❌ Attempt {attempt+1} failed: {e}")
            
            # Wait before next attempt (increasing delay)
            wait_time = min(30, 5 * (attempt + 1))
            logger.info(f"   ⏳ Waiting {wait_time}s before next attempt...")
            await asyncio.sleep(wait_time)
        
        logger.error("❌❌ ALL BTC FETCH ATTEMPTS FAILED!")
        return False
    
    async def _background_btc_fetcher(self):
        """Background task to keep fetching BTC data"""
        while not self._btc_data_ready:
            try:
                logger.info("🔄 Background BTC fetcher running...")
                
                btc_15m = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "15m", 100)
                
                if btc_15m and len(btc_15m) >= 50:
                    self.btc_cache["15m"] = btc_15m
                    self.btc_cache["1h"] = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "1h", 50)
                    self.btc_cache["4h"] = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "4h", 50)
                    
                    # Update cache
                    self.cache.set_ohlcv("BTC/USDT", "15m", btc_15m)
                    
                    self._btc_data_ready = True
                    logger.info("✅ Background BTC fetcher succeeded")
                    await self._update_regime()
                    break
                    
            except Exception as e:
                logger.error(f"❌ Background BTC fetcher error: {e}")
            
            await asyncio.sleep(30)
    
    async def stop(self):
        """Stop the engine"""
        logger.info("🔴 Stopping engine...")
        await self.ws_manager.stop()
        await self.rest_client.close()
        logger.info("✅ Engine stopped")
    
    async def _seed_cache(self):
        """Pre-fill cache with historical data"""
        # First seed BTC
        try:
            btc_candles = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "15m", 100)
            if btc_candles:
                self.cache.set_ohlcv("BTC/USDT", "15m", btc_candles)
                logger.info(f"✅ Seeded BTC: {len(btc_candles)} candles")
                
            btc_1h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "1h", 50)
            if btc_1h:
                self.cache.set_ohlcv("BTC/USDT", "1h", btc_1h)
                
            btc_4h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "4h", 50)
            if btc_4h:
                self.cache.set_ohlcv("BTC/USDT", "4h", btc_4h)
                
        except Exception as e:
            logger.warning(f"⚠️ BTC seed failed: {e}")
        
        # Then other symbols
        for symbol in config.TRADING_PAIRS:
            if symbol == "BTC/USDT":
                continue
            for tf in config.TIMEFRAMES:
                try:
                    candles = await self.rest_client.fetch_ohlcv_rest(symbol, tf, config.CACHE_SIZE)
                    if candles:
                        self.cache.set_ohlcv(symbol, tf, candles)
                        logger.info(f"✅ Seeded {symbol} {tf}: {len(candles)} candles")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to seed {symbol} {tf}: {e}")
        
        logger.info("🌱 Cache seeding complete")
    
    async def _update_regime(self):
        """Update market regime and BTC regime"""
        try:
            if not self._btc_data_ready:
                logger.warning("⚠️ BTC data not ready - skipping regime update")
                return
            
            # Get BTC data from CACHE
            btc_15m = self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value)
            btc_1h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H1.value)
            btc_4h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H4.value)
            
            if not btc_15m or len(btc_15m) < 30:
                logger.warning(f"⚠️ Insufficient BTC data for regime: {len(btc_15m) if btc_15m else 0}/30")
                return
            
            # Detect regimes
            self.market_type = self.regime_detector.detect_market_type(btc_15m, btc_1h)
            self.btc_regime = self.regime_detector.detect_btc_regime(btc_15m, btc_1h, btc_4h)
            
            logger.info(f"📊 Market: {self.market_type.value} | BTC: {self.btc_regime.regime.value if self.btc_regime else 'unknown'} | Conf: {self.btc_regime.confidence if self.btc_regime else 0}%")
            
        except Exception as e:
            logger.error(f"❌ Regime update failed: {e}")
    
    async def _on_candle_close(self, symbol: str, tf: str, candles: List[List[float]]):
        """
        Callback when candle closes
        This is where signals are generated
        """
        if tf != config.PRIMARY_TF:
            return
        
        try:
            logger.info(f"🔔 Candle closed: {symbol} @ {candles[-1][4]:.2f}")
            
            # Update cache
            self.cache.set_ohlcv(symbol, tf, candles)
            
            # Update BTC data if this is BTC
            if symbol == "BTC/USDT":
                logger.info(f"✅ BTC {tf} data updated - {len(candles)} candles")
                if tf == "15m" and len(candles) >= 50 and not self._btc_data_ready:
                    self._btc_data_ready = True
                    logger.info("✅ BTC data now ready from WebSocket")
                    await self._update_regime()
            
            # Check if BTC data is ready
            if not self._btc_data_ready:
                logger.debug(f"⏸️ {symbol}: BTC data not ready - skipping")
                return
            
            # Check if we can process signal
            can_process, reason = await self._can_process_signal(symbol)
            if not can_process:
                logger.info(f"⏸️ {symbol}: {reason}")
                return
            
            # Generate signal
            await self._generate_signal(symbol, candles)
                
        except Exception as e:
            logger.error(f"❌ Error processing candle close for {symbol}: {e}")
    
    async def _can_process_signal(self, symbol: str) -> Tuple[bool, str]:
        """Check if we can process a signal with detailed reason"""
        
        # Check BTC data
        if not self._btc_data_ready:
            return False, "BTC data not ready"
        
        # Check daily limit
        if self.daily_signals >= self._get_daily_limit():
            return False, f"Daily signal limit reached ({self.daily_signals}/{self._get_daily_limit()})"
        
        # Check cooldown
        if symbol in self.last_signal_time:
            elapsed = (datetime.now() - self.last_signal_time[symbol]).total_seconds() / 60
            if elapsed < config.COOLDOWN_MINUTES:
                return False, f"Cooldown ({elapsed:.1f}/{config.COOLDOWN_MINUTES} min)"
        
        # Check risk manager
        can_trade, risk_reason = self.risk_manager.can_trade(symbol, self.market_type)
        if not can_trade:
            return False, f"Risk manager: {risk_reason}"
        
        return True, "OK"
    
    def _get_daily_limit(self) -> int:
        """Get daily signal limit based on market type"""
        limits = config.MAX_SIGNALS_PER_DAY
        return limits.get(self.market_type.value, limits["default"])
    
    async def _generate_signal(self, symbol: str, candles_15m: List[List[float]]):
        """Generate signal for a symbol with detailed logging"""
        
        logger.info(f"🔍 Checking {symbol} for signal...")
        
        # Get all required data from CACHE with REST API backup
        data = await self._get_all_data(symbol)
        if not data:
            logger.info(f"❌ {symbol}: No data available")
            return
        
        # Apply filters
        logger.info(f"🔍 Applying filters for {symbol}...")
        filter_result = await self.filter_orchestrator.evaluate(
            symbol=symbol,
            direction=None,
            market_type=self.market_type,
            btc_regime=self.btc_regime,
            data=data
        )
        
        # Log filter results in detail
        if not filter_result["passed"]:
            logger.info(f"❌ {symbol}: Filters failed - {filter_result['reason']}")
            return
        
        logger.info(f"✅ {symbol}: Filters passed with score {filter_result['score']}%")
        
        # Generate signal
        signal = await self.signal_generator.generate(
            symbol=symbol,
            data=data,
            filter_result=filter_result,
            market_type=self.market_type,
            btc_regime=self.btc_regime
        )
        
        if signal:
            await self._process_signal(signal)
        else:
            logger.info(f"❌ {symbol}: Signal generation failed")
    
    async def _get_all_data(self, symbol: str) -> Optional[Dict]:
        """Get all required data from CACHE for signal generation with REST API backup"""
        
        try:
            # Get OHLCV data from CACHE - use .value to get string
            ohlcv_5m = self.cache.get_ohlcv(symbol, Timeframes.M5.value)
            ohlcv_15m = self.cache.get_ohlcv(symbol, Timeframes.M15.value)
            ohlcv_1h = self.cache.get_ohlcv(symbol, Timeframes.H1.value)
            ohlcv_4h = self.cache.get_ohlcv(symbol, Timeframes.H4.value)
            
            # Get BTC data from CACHE - use .value to get string
            btc_15m = self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value)
            btc_1h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H1.value)
            btc_4h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H4.value)
            
            # 🔴 REST API ব্যাকআপ - যদি cache না থাকে
            rest_fetched = False
            
            if not ohlcv_15m:
                logger.warning(f"⚠️ Cache miss for {symbol} 15m, trying REST API...")
                ohlcv_15m = await self.rest_client.fetch_ohlcv_rest(symbol, "15m", 100)
                if ohlcv_15m:
                    self.cache.set_ohlcv(symbol, "15m", ohlcv_15m)
                    rest_fetched = True
                    logger.info(f"✅ REST API: Got {len(ohlcv_15m)} candles for {symbol} 15m")
            
            if not ohlcv_5m:
                ohlcv_5m = await self.rest_client.fetch_ohlcv_rest(symbol, "5m", 50)
                if ohlcv_5m:
                    self.cache.set_ohlcv(symbol, "5m", ohlcv_5m)
                    rest_fetched = True
            
            if not ohlcv_1h:
                ohlcv_1h = await self.rest_client.fetch_ohlcv_rest(symbol, "1h", 50)
                if ohlcv_1h:
                    self.cache.set_ohlcv(symbol, "1h", ohlcv_1h)
                    rest_fetched = True
            
            if not ohlcv_4h:
                ohlcv_4h = await self.rest_client.fetch_ohlcv_rest(symbol, "4h", 50)
                if ohlcv_4h:
                    self.cache.set_ohlcv(symbol, "4h", ohlcv_4h)
                    rest_fetched = True
            
            # BTC ডেটার জন্যও REST API ব্যাকআপ
            if not btc_15m or len(btc_15m) < 30:
                logger.warning("⚠️ Cache miss for BTC 15m, trying REST API...")
                btc_15m = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "15m", 100)
                if btc_15m:
                    self.cache.set_ohlcv("BTC/USDT", "15m", btc_15m)
                    self.btc_cache["15m"] = btc_15m
                    rest_fetched = True
            
            if not btc_1h:
                btc_1h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "1h", 50)
                if btc_1h:
                    self.cache.set_ohlcv("BTC/USDT", "1h", btc_1h)
                    self.btc_cache["1h"] = btc_1h
            
            if not btc_4h:
                btc_4h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "4h", 50)
                if btc_4h:
                    self.cache.set_ohlcv("BTC/USDT", "4h", btc_4h)
                    self.btc_cache["4h"] = btc_4h
            
            if rest_fetched:
                logger.info(f"✅ REST API fetched data for {symbol}")
                if btc_15m and len(btc_15m) >= 30 and not self._btc_data_ready:
                    self._btc_data_ready = True
                    await self._update_regime()
            
            # Log what we got
            logger.debug(f"📊 Data for {symbol}:")
            logger.debug(f"   {symbol} 5m: {len(ohlcv_5m) if ohlcv_5m else 0} candles")
            logger.debug(f"   {symbol} 15m: {len(ohlcv_15m) if ohlcv_15m else 0} candles")
            logger.debug(f"   {symbol} 1h: {len(ohlcv_1h) if ohlcv_1h else 0} candles")
            logger.debug(f"   {symbol} 4h: {len(ohlcv_4h) if ohlcv_4h else 0} candles")
            logger.debug(f"   BTC 15m: {len(btc_15m) if btc_15m else 0} candles")
            logger.debug(f"   BTC 1h: {len(btc_1h) if btc_1h else 0} candles")
            logger.debug(f"   BTC 4h: {len(btc_4h) if btc_4h else 0} candles")
            
            # Validate data
            if not ohlcv_15m:
                logger.warning(f"⚠️ No 15m data for {symbol} from any source")
                return None
            
            if not btc_15m or len(btc_15m) < 30:
                logger.warning(f"⚠️ Insufficient BTC data: {len(btc_15m) if btc_15m else 0}/30")
                return None
            
            # Get other data
            funding = await self.rest_client.fetch_funding_rate(symbol)
            oi = await self.rest_client.fetch_open_interest(symbol)
            orderbook = await self.rest_client.fetch_orderbook(symbol)
            
            # If orderbook empty, try REST
            if not orderbook.get("bids") and not orderbook.get("asks"):
                orderbook = await self.rest_client.fetch_orderbook_rest(symbol)
            
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
            logger.error(f"❌ Error getting data for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
            logger.warning(f"⏸️ Position sizing blocked: {position.get('reason')}")
            return
        
        signal["position"] = position
        
        # Update state
        symbol = signal["symbol"]
        self.last_signal_time[symbol] = datetime.now()
        self.daily_signals += 1
        
        # Send notification
        await self.telegram.send_signal(signal, self.market_type)
        
        logger.info(f"✅✅ SIGNAL GENERATED: {symbol} {signal['direction']} @ {signal['entry']:.2f} | Score: {signal['score']} | Grade: {signal['grade']}")
    
    def reset_daily(self):
        """Reset daily counters"""
        self.daily_signals = 0
        self.consecutive_losses = 0
        self.risk_manager.reset_daily()
        logger.info("📅 Daily counters reset")
    
    def get_status(self) -> Dict:
        """Get engine status"""
        btc_candles = len(self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value))
        
        return {
            "market_type": self.market_type.value,
            "btc_regime": self.btc_regime.regime.value if self.btc_regime else "unknown",
            "btc_confidence": self.btc_regime.confidence if self.btc_regime else 0,
            "btc_data_ready": self._btc_data_ready,
            "btc_candles": btc_candles,
            "daily_signals": self.daily_signals,
            "daily_limit": self._get_daily_limit(),
            "active_trades": len(self.risk_manager.active_trades),
            "day_locked": self.risk_manager.daily_lock.is_locked if hasattr(self.risk_manager, 'daily_lock') else False
        }
