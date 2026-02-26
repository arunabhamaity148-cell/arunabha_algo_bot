"""
ARUNABHA ALGO BOT - Main Engine v4.1 (FIXED)
Orchestrates all components and generates signals

FIXES:
- All methods now properly indented inside ArunabhaEngine class
- _force_fetch_all_pairs now fetches ALL pairs including BTC
- RSI + MACD confirmation added to signal direction
- SL/TP uses nearest support/resistance levels
- Trailing stop added
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

        # Trailing stop tracking
        self._trailing_stops: Dict[str, float] = {}

        logger.info("🚀 Engine initialized v4.1 (FIXED)")

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

        # Force fetch ALL pairs
        logger.info("🔄 ===== FORCE FETCHING ALL PAIRS DATA =====")
        await self._force_fetch_all_pairs()

        # Start WebSocket
        logger.info("🔌 Starting WebSocket connection...")
        await self.ws_manager.start()

        # Initial regime detection
        await self._update_regime()

        logger.info("✅ Engine started successfully")

    # ✅ FIX #1: সব method এখন class এর ভেতরে (4 space indent)

    async def _force_fetch_all_pairs(self):
        """Force fetch data for ALL trading pairs including BTC"""

        # ✅ FIX #2: config.TRADING_PAIRS use করো — BTC বাদ পড়বে না
        symbols = config.TRADING_PAIRS
        timeframes = ["5m", "15m", "1h", "4h"]

        for symbol in symbols:
            logger.info(f"📡 Processing {symbol}...")
            for tf in timeframes:
                try:
                    logger.info(f"   Fetching {symbol} {tf}...")
                    candles = await self.rest_client.fetch_ohlcv_rest(symbol, tf, 100)

                    if candles and len(candles) > 0:
                        self.cache.set_ohlcv(symbol, tf, candles)
                        logger.info(f"   ✅ {symbol} {tf}: {len(candles)} candles cached")

                        # BTC cache আলাদাভাবে update
                        if symbol == "BTC/USDT":
                            self.btc_cache[tf] = candles

                        verify = self.cache.get_ohlcv(symbol, tf)
                        if verify:
                            logger.info(f"      ✅ Verified: {len(verify)} candles")
                    else:
                        logger.warning(f"   ⚠️ No data for {symbol} {tf}")

                    await asyncio.sleep(0.3)  # Rate limit

                except Exception as e:
                    logger.error(f"   ❌ Failed to fetch {symbol} {tf}: {e}")
                    continue

            logger.info(f"✅ Completed {symbol}")

        # Final verification
        logger.info("🔍 Final cache verification:")
        for symbol in symbols:
            candles = self.cache.get_ohlcv(symbol, "15m")
            if candles:
                logger.info(f"   ✅ {symbol} 15m: {len(candles)} candles")
            else:
                logger.error(f"   ❌ {symbol} 15m: NO DATA!")

        logger.info("✅ Force fetch all pairs completed")

    async def _force_fetch_btc_data(self) -> bool:
        """Force fetch BTC data with multiple retries"""
        for attempt in range(10):
            try:
                logger.info(f"🔄 [ATTEMPT {attempt+1}/10] Fetching BTC data...")

                btc_15m = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "15m", 100)
                btc_1h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "1h", 50)
                btc_4h = await self.rest_client.fetch_ohlcv_rest("BTC/USDT", "4h", 50)

                logger.info(f"   BTC 15m: {len(btc_15m) if btc_15m else 0} candles")
                logger.info(f"   BTC 1h: {len(btc_1h) if btc_1h else 0} candles")
                logger.info(f"   BTC 4h: {len(btc_4h) if btc_4h else 0} candles")

                if btc_15m and len(btc_15m) >= 50:
                    self.btc_cache["15m"] = btc_15m
                    self.btc_cache["1h"] = btc_1h if btc_1h else []
                    self.btc_cache["4h"] = btc_4h if btc_4h else []

                    self.cache.set_ohlcv("BTC/USDT", "15m", btc_15m)
                    if btc_1h:
                        self.cache.set_ohlcv("BTC/USDT", "1h", btc_1h)
                    if btc_4h:
                        self.cache.set_ohlcv("BTC/USDT", "4h", btc_4h)

                    cache_check = self.cache.get_ohlcv("BTC/USDT", "15m")
                    if cache_check and len(cache_check) >= 50:
                        logger.info(f"✅ Cache verified: {len(cache_check)} candles for BTC 15m")
                        self._btc_data_ready = True
                    else:
                        logger.error("❌ Cache verification failed!")
                        continue

                    await self._update_regime()
                    return True
                else:
                    logger.warning(f"   ⚠️ Only {len(btc_15m) if btc_15m else 0} candles - need 50")

            except Exception as e:
                logger.error(f"   ❌ Attempt {attempt+1} failed: {e}")

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

            btc_15m = self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value)
            btc_1h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H1.value)
            btc_4h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H4.value)

            if not btc_15m or len(btc_15m) < 30:
                logger.warning(f"⚠️ Insufficient BTC data for regime: {len(btc_15m) if btc_15m else 0}/30")
                return

            self.market_type = self.regime_detector.detect_market_type(btc_15m, btc_1h)
            self.btc_regime = self.regime_detector.detect_btc_regime(btc_15m, btc_1h, btc_4h)

            logger.info(
                f"📊 Market: {self.market_type.value} | "
                f"BTC: {self.btc_regime.regime.value if self.btc_regime else 'unknown'} | "
                f"Conf: {self.btc_regime.confidence if self.btc_regime else 0}%"
            )

        except Exception as e:
            logger.error(f"❌ Regime update failed: {e}")

    async def _on_candle_close(self, symbol: str, tf: str, candles: List[List[float]]):
        """
        Callback when candle closes — signals generated here
        """
        if tf != config.PRIMARY_TF:
            return

        try:
            logger.info(f"🔔 Candle closed: {symbol} @ {candles[-1][4]:.2f}")

            self.cache.set_ohlcv(symbol, tf, candles)

            if symbol == "BTC/USDT":
                logger.info(f"✅ BTC {tf} data updated - {len(candles)} candles")
                if tf == "15m" and len(candles) >= 50 and not self._btc_data_ready:
                    self._btc_data_ready = True
                    logger.info("✅ BTC data now ready from WebSocket")
                    await self._update_regime()

            if not self._btc_data_ready:
                logger.debug(f"⏸️ {symbol}: BTC data not ready - skipping")
                return

            # Check trailing stops on every candle
            await self._check_trailing_stops(symbol, candles[-1][4])

            can_process, reason = await self._can_process_signal(symbol)
            if not can_process:
                logger.info(f"⏸️ {symbol}: {reason}")
                return

            await self._generate_signal(symbol, candles)

        except Exception as e:
            logger.error(f"❌ Error processing candle close for {symbol}: {e}")

    async def _check_trailing_stops(self, symbol: str, current_price: float):
        """
        ✅ NEW: Trailing stop logic
        Active trade এ price এগোলে SL টেনে নিয়ে আসে
        """
        if symbol not in self.risk_manager.active_trades:
            return

        trade = self.risk_manager.active_trades[symbol]
        direction = trade.get("direction")
        entry = trade.get("entry", 0)
        current_sl = trade.get("stop_loss", 0)

        if direction == "LONG":
            # Price এর 1.5 ATR নিচে trailing stop
            atr = self.technical.calculate_atr(
                self.cache.get_ohlcv(symbol, "15m") or []
            )
            new_sl = current_price - (atr * 1.5)
            if new_sl > current_sl and new_sl > entry:
                trade["stop_loss"] = round(new_sl, 6)
                logger.info(f"📈 {symbol} Trailing SL moved: {current_sl:.6f} → {new_sl:.6f}")
                await self.telegram.send_message(
                    f"📈 *Trailing Stop Updated*\n"
                    f"Symbol: `{symbol}`\n"
                    f"New SL: `{new_sl:.6f}`\n"
                    f"Current Price: `{current_price:.6f}`"
                )

        elif direction == "SHORT":
            atr = self.technical.calculate_atr(
                self.cache.get_ohlcv(symbol, "15m") or []
            )
            new_sl = current_price + (atr * 1.5)
            if new_sl < current_sl and new_sl < entry:
                trade["stop_loss"] = round(new_sl, 6)
                logger.info(f"📉 {symbol} Trailing SL moved: {current_sl:.6f} → {new_sl:.6f}")

    async def _can_process_signal(self, symbol: str) -> Tuple[bool, str]:
        """Check if we can process a signal"""

        if not self._btc_data_ready:
            return False, "BTC data not ready"

        if self.daily_signals >= self._get_daily_limit():
            return False, f"Daily signal limit reached ({self.daily_signals}/{self._get_daily_limit()})"

        if symbol in self.last_signal_time:
            elapsed = (datetime.now() - self.last_signal_time[symbol]).total_seconds() / 60
            if elapsed < config.COOLDOWN_MINUTES:
                return False, f"Cooldown ({elapsed:.1f}/{config.COOLDOWN_MINUTES} min)"

        can_trade, risk_reason = self.risk_manager.can_trade(symbol, self.market_type)
        if not can_trade:
            return False, f"Risk manager: {risk_reason}"

        return True, "OK"

    def _get_daily_limit(self) -> int:
        """Get daily signal limit based on market type"""
        limits = config.MAX_SIGNALS_PER_DAY
        return limits.get(self.market_type.value, limits["default"])

    async def _generate_signal(self, symbol: str, candles_15m: List[List[float]]):
        """Generate signal for a symbol"""

        logger.info(f"🔍 Checking {symbol} for signal...")

        data = await self._get_all_data(symbol)
        if not data:
            logger.info(f"❌ {symbol}: No data available")
            return
# ✅ FIX #3: RSI + MACD দিয়ে direction pre-check
        direction_ok, direction_reason = self._check_indicator_direction(data)
        if not direction_ok:
            logger.info(f"⏸️ {symbol}: Indicator direction mismatch — {direction_reason}")
            return

        logger.info(f"🔍 Applying filters for {symbol}...")
        filter_result = await self.filter_orchestrator.evaluate(
            symbol=symbol,
            direction=None,
            market_type=self.market_type,
            btc_regime=self.btc_regime,
            data=data
        )

        if not filter_result["passed"]:
            logger.info(f"❌ {symbol}: Filters failed - {filter_result['reason']}")
            return

        logger.info(f"✅ {symbol}: Filters passed with score {filter_result['score']}%")

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

    def _check_indicator_direction(self, data: Dict) -> Tuple[bool, str]:
        """
        ✅ NEW FIX #3: RSI + MACD দিয়ে direction confirm করো
        দুটো indicator একই দিক বললে signal allow
        """
        ohlcv_15m = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv_15m) < 30:
            return True, "Insufficient data — allowing"

        closes = [c[4] for c in ohlcv_15m]

        # RSI check
        rsi = self.technical.calculate_rsi(closes)

        # MACD check
        macd_result = self.technical.calculate_macd(closes)
        macd_line = macd_result.get("macd", 0)
        signal_line = macd_result.get("signal", 0)
        macd_histogram = macd_line - signal_line

        # Direction determination
        rsi_bullish = rsi > 45 and rsi < 75   # Not overbought, above midline
        rsi_bearish = rsi < 55 and rsi > 25   # Not oversold, below midline

        macd_bullish = macd_histogram > 0
        macd_bearish = macd_histogram < 0

        # Both must agree
        if rsi_bullish and macd_bullish:
            logger.info(f"📈 Indicator check: BULLISH (RSI={rsi:.1f}, MACD_hist={macd_histogram:.6f})")
            return True, f"BULLISH RSI={rsi:.1f} MACD_hist={macd_histogram:.6f}"
        elif rsi_bearish and macd_bearish:
            logger.info(f"📉 Indicator check: BEARISH (RSI={rsi:.1f}, MACD_hist={macd_histogram:.6f})")
            return True, f"BEARISH RSI={rsi:.1f} MACD_hist={macd_histogram:.6f}"
        else:
            return False, f"Conflicting indicators RSI={rsi:.1f} MACD_hist={macd_histogram:.6f}"

    async def _get_all_data(self, symbol: str) -> Optional[Dict]:
        """Get all required data from CACHE with REST API backup"""

        try:
            ohlcv_5m = self.cache.get_ohlcv(symbol, Timeframes.M5.value)
            ohlcv_15m = self.cache.get_ohlcv(symbol, Timeframes.M15.value)
            ohlcv_1h = self.cache.get_ohlcv(symbol, Timeframes.H1.value)
            ohlcv_4h = self.cache.get_ohlcv(symbol, Timeframes.H4.value)

            btc_15m = self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value)
            btc_1h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H1.value)
            btc_4h = self.cache.get_ohlcv("BTC/USDT", Timeframes.H4.value)

            rest_fetched = False

            if not ohlcv_15m:
                logger.warning(f"⚠️ Cache miss for {symbol} 15m, trying REST API...")
                ohlcv_15m = await self.rest_client.fetch_ohlcv_rest(symbol, "15m", 100)
                if ohlcv_15m:
                    self.cache.set_ohlcv(symbol, "15m", ohlcv_15m)
                    rest_fetched = True

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

            if not ohlcv_15m:
                logger.warning(f"⚠️ No 15m data for {symbol} from any source")
                return None

            if not btc_15m or len(btc_15m) < 30:
                logger.warning(f"⚠️ Insufficient BTC data: {len(btc_15m) if btc_15m else 0}/30")
                return None

            funding = await self.rest_client.fetch_funding_rate(symbol)
            oi = await self.rest_client.fetch_open_interest(symbol)
            orderbook = await self.rest_client.fetch_orderbook(symbol)

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

        symbol = signal["symbol"]
        self.last_signal_time[symbol] = datetime.now()
        self.daily_signals += 1

        await self.telegram.send_signal(signal, self.market_type)

        logger.info(
            f"✅✅ SIGNAL GENERATED: {symbol} {signal['direction']} @ {signal['entry']:.6f} | "
            f"Score: {signal['score']} | Grade: {signal['grade']}"
        )

    def reset_daily(self):
        """Reset daily counters"""
        self.daily_signals = 0
        self.consecutive_losses = 0
        self._trailing_stops.clear()
        self.risk_manager.reset_daily()
        logger.info("📅 Daily counters reset")

    def get_status(self) -> Dict:
        """Get engine status"""
        btc_candles = len(self.cache.get_ohlcv("BTC/USDT", Timeframes.M15.value) or [])

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