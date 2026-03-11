"""
ARUNABHA ALGO BOT - Trading Scheduler v5.0

FIXES:
- BUG-A:  _force_scan এ engine._generate_signal() call ছিল — method exist করে না!
          Fix: engine._analyze_symbol() তে rename করা হয়েছে (AttributeError runtime crash fix)
- BUG-21: timezone localize error fixed
  আগে: datetime.combine() naive datetime তৈরি করত, তারপর localize() crash করত
  কারণ: now = datetime.now(self.timezone) → aware datetime
        target = datetime.combine(now.date(), target_time) → naive datetime
        self.timezone.localize(target) → pytz এ এটা ঠিক আছে কিন্তু
        (target - now) করলে aware vs naive comparison error হতো
  Fix: সব datetime consistently aware রাখা হয়েছে

- BUG-22: NY session scheduler 18:00 তে fire করে
  কিন্তু tier1_filters.py তে 17:00 থেকে NY session active দেখায়
  Fix: scheduler এ 17:00 তে NY session start করা হয়েছে (17-22 IST)
       constants.py ও align করা হয়েছে
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
import pytz

import config
from core.constants import SessionType

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Scheduler for trading operations based on time and sessions
    """

    def __init__(self, engine):
        self.engine = engine
        self.tasks: List[asyncio.Task] = []
        self.running = False
        self.timezone = pytz.timezone('Asia/Kolkata')

        # Session callbacks
        self.session_callbacks: Dict[SessionType, List[Callable]] = {
            session: [] for session in SessionType
        }

        # ✅ FIX BUG-22: NY session এখন 17:00 IST তে শুরু হবে
        # আগে 18:00 ছিল — কিন্তু tier1_filters.py 17:00 থেকে allow করে
        # এখন দুটো align হয়েছে: 17:00–22:00 IST = NY session
        self.scheduled_tasks = [
            {"time": "00:00", "callback": self._daily_reset,   "name": "daily_reset"},
            {"time": "01:00", "callback": self._update_regime, "name": "regime_update"},
            {"time": "07:00", "callback": self._session_start, "name": "asia_start",
             "session": SessionType.ASIA},
            {"time": "13:00", "callback": self._session_start, "name": "london_start",
             "session": SessionType.LONDON},
            {"time": "17:00", "callback": self._session_start, "name": "ny_start",
             "session": SessionType.NY},           # ✅ FIXED: 18 → 17
            {"time": "22:00", "callback": self._session_start, "name": "overlap_start",
             "session": SessionType.OVERLAP},
        ]

        # ✅ FIX BUG-1: HTF refresh interval (seconds)
        # WebSocket শুধু 15m candle দেয়। 1h/4h এর জন্য periodic REST fetch দরকার।
        self._htf_refresh_interval = 3600  # 1 ঘণ্টা

    async def start(self):
        """Start the scheduler"""
        self.running = True
        logger.info("🚀 Scheduler started")

        self.tasks.append(asyncio.create_task(self._main_loop()))
        self.tasks.append(asyncio.create_task(self._force_scan()))

        # ✅ FIX BUG-1: BTC 1h/4h stale cache fix
        # WebSocket শুধু 15m feed করে। 1h/4h প্রতি ঘণ্টায় REST দিয়ে refresh করতে হবে।
        self.tasks.append(asyncio.create_task(self._periodic_htf_refresh()))

        for task_config in self.scheduled_tasks:
            self.tasks.append(asyncio.create_task(
                self._run_scheduled(task_config)
            ))

    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        logger.info("Scheduler stopped")

    async def _main_loop(self):
        """Main scheduler loop — runs every minute"""
        while self.running:
            try:
                now = datetime.now(self.timezone)
                current_session = self._get_current_session()
                if now.minute == 0:
                    logger.info(f"⏰ {now.strftime('%H:%M')} IST | Session: {current_session}")
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler main loop error: {e}")
                await asyncio.sleep(60)

    async def _force_scan(self):
        """Force scan all pairs every 15 minutes"""
        while self.running:
            try:
                now = datetime.now()
                minutes = now.minute
                next_scan = 15 - (minutes % 15)
                if next_scan == 0:
                    next_scan = 15

                logger.info(f"⏰ Next force scan in {next_scan} min")
                await asyncio.sleep(next_scan * 60)

                if not self.running:
                    break

                logger.info("🔍 ===== FORCE SCANNING ALL PAIRS =====")

                if not self.engine._btc_data_ready:
                    logger.warning("⚠️ BTC data not ready — skipping scan")
                    continue

                for symbol in config.TRADING_PAIRS:
                    try:
                        candles = self.engine.cache.get_ohlcv(symbol, "15m")
                        if candles and len(candles) > 20:
                            logger.info(f"🔍 Scanning {symbol} ({len(candles)} candles)")
                            await self.engine._analyze_symbol(symbol, candles)
                        else:
                            logger.warning(f"⚠️ {symbol}: {len(candles) if candles else 0} candles (need 20+)")
                    except Exception as e:
                        logger.error(f"❌ Scan error for {symbol}: {e}")

                logger.info("✅ ===== SCAN COMPLETE =====")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Force scan loop error: {e}")
                await asyncio.sleep(60)

    async def _run_scheduled(self, task_config: Dict):
        """
        Run a scheduled task at specific time every day

        ✅ FIX BUG-21: timezone comparison ঠিক করা হয়েছে
        আগে: datetime.combine() naive datetime দিত → localize() তে crash বা
              aware vs naive comparison error হতো
        এখন: সব datetime aware রাখা হয়েছে, astimezone() ব্যবহার করা হচ্ছে
        """
        target_time_str = task_config["time"]
        target_hour, target_minute = map(int, target_time_str.split(":"))

        while self.running:
            try:
                # ✅ FIX: সবসময় aware datetime ব্যবহার করো
                now = datetime.now(self.timezone)

                # আজকের target time (timezone-aware)
                target = now.replace(
                    hour=target_hour,
                    minute=target_minute,
                    second=0,
                    microsecond=0
                )

                # Target পার হয়ে গেলে কালকের জন্য set করো
                if now >= target:
                    target = target + timedelta(days=1)

                # ✅ FIX: দুটোই aware datetime, তাই comparison safe
                wait_seconds = (target - now).total_seconds()

                logger.debug(
                    f"⏳ Task '{task_config['name']}' scheduled in "
                    f"{wait_seconds/3600:.1f}h (at {target_time_str} IST)"
                )

                await asyncio.sleep(wait_seconds)

                if not self.running:
                    break

                logger.info(f"📅 Running scheduled task: {task_config['name']}")

                if "session" in task_config:
                    await task_config["callback"](task_config["session"])
                else:
                    await task_config["callback"]()

                # 61 seconds wait করো যাতে একই minute এ double execute না হয়
                await asyncio.sleep(61)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Scheduled task '{task_config['name']}' error: {e}")
                await asyncio.sleep(60)

    def _get_current_session(self) -> Optional[SessionType]:
        """Get current trading session based on IST hour"""
        hour = datetime.now(self.timezone).hour
        for session in SessionType:
            start, end = session.hours
            if start <= hour < end:
                return session
        return None

    # ✅ FIX BUG-1: Periodic HTF (1h/4h) BTC cache refresh
    async def _periodic_htf_refresh(self):
        """
        প্রতি 1 ঘণ্টায় BTC 1h ও 4h candle REST দিয়ে refresh করো।

        কেন দরকার:
          WebSocket শুধু 15m candle feed করে।
          Bot start-এ _force_fetch_btc_data() 1h/4h আনে —
          কিন্তু এরপর আর কখনো update হয় না।
          _update_regime() তখন stale data দিয়ে regime detect করে।

        Fix: প্রতি ঘণ্টায় engine._force_fetch_btc_data() call করো,
             তারপর _update_regime() দিয়ে regime তাৎক্ষণিক refresh করো।
        """
        # প্রথম run-এ 1 ঘণ্টা পর শুরু (bot-start এই data fresh আছে)
        await asyncio.sleep(self._htf_refresh_interval)

        while self.running:
            try:
                logger.info("🔄 HTF refresh: fetching BTC 1h/4h via REST...")
                ok = await self.engine._force_fetch_btc_data()
                if ok:
                    logger.info("✅ BTC 1h/4h cache refreshed successfully")
                    await self.engine._update_regime()
                    logger.info("✅ Regime updated with fresh HTF data")
                else:
                    logger.warning("⚠️ HTF refresh failed — will retry next cycle")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ HTF refresh error: {e}")

            await asyncio.sleep(self._htf_refresh_interval)

    async def _daily_reset(self):
        """Reset daily counters at midnight IST"""
        logger.info("📅 Daily reset triggered")
        try:
            self.engine.reset_daily()
            logger.info("✅ Daily reset complete")
        except Exception as e:
            logger.error(f"❌ Daily reset error: {e}")

    async def _update_regime(self):
        """Update market regime"""
        logger.info("📊 Scheduled regime update")
        try:
            await self.engine._update_regime()
        except Exception as e:
            logger.error(f"❌ Regime update error: {e}")

    async def _session_start(self, session: SessionType):
        """Handle session start notification"""
        logger.info(f"🕐 Session started: {session.value}")
        try:
            if self.engine.telegram:
                start_h, end_h = session.hours
                await self.engine.telegram.send_message(
                    f"🕐 <b>{session.value.upper()} session started</b>\n"
                    f"⏰ Active: {start_h:02d}:00 – {end_h:02d}:00 IST\n"
                    f"📊 Market: {self.engine.market_type.value}"
                )

            # Session callbacks (from Orchestrator)
            for callback in self.session_callbacks.get(session, []):
                try:
                    await callback(session)
                except Exception as e:
                    logger.error(f"Session callback error: {e}")

        except Exception as e:
            logger.error(f"❌ Session start handler error: {e}")

    def register_session_callback(self, session: SessionType, callback: Callable):
        """Register a callback to run when a session starts"""
        self.session_callbacks[session].append(callback)
        logger.debug(f"Callback registered for {session.value} session")

    def is_trading_time(self) -> bool:
        """Check if current time is suitable for trading"""
        session = self._get_current_session()
        if not session or session == SessionType.DEAD:
            return False

        hour = datetime.now(self.timezone).hour
        for start, end, _ in config.AVOID_TIMES:
            # ✅ Handle midnight crossing properly (e.g. 23:00–01:00)
            if start > end:
                if hour >= start or hour < end:
                    return False
            else:
                if start <= hour < end:
                    return False

        return True

    def get_session_info(self) -> Dict:
        """Get current session information"""
        now = datetime.now(self.timezone)
        session = self._get_current_session()

        return {
            "current_session": session.value if session else "none",
            "hour_ist": now.hour,
            "time_ist": now.strftime("%H:%M"),
            "is_trading_time": self.is_trading_time(),
            "next_session": self._get_next_session(),
            "scheduler_running": self.running,
            "active_tasks": len([t for t in self.tasks if not t.done()])
        }

    def _get_next_session(self) -> Optional[Dict]:
        """Get next upcoming trading session"""
        current_hour = datetime.now(self.timezone).hour

        # Build session list sorted by start hour
        sessions = sorted(
            [{"name": s.value, "start": s.hours[0], "end": s.hours[1]} for s in SessionType],
            key=lambda x: x["start"]
        )

        # Find next session after current hour
        for s in sessions:
            if s["start"] > current_hour:
                return {
                    "name": s["name"],
                    "start_ist": f"{s['start']:02d}:00",
                    "end_ist": f"{s['end']:02d}:00",
                    "hours_away": s["start"] - current_hour
                }

        # Wrap around to tomorrow's first session
        first = sessions[0]
        return {
            "name": first["name"],
            "start_ist": f"{first['start']:02d}:00",
            "end_ist": f"{first['end']:02d}:00",
            "hours_away": (24 - current_hour) + first["start"]
        }
