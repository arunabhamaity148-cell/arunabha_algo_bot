"""
ARUNABHA ALGO BOT - Anchored VWAP v1.0
=======================================
3 ধরনের Anchored VWAP:

1. SESSION VWAP  — প্রতিদিনের candle[0] (day open) থেকে anchor
   → Intraday key level। দিনের শুরু থেকে কত দামে average trade হয়েছে।

2. WEEKLY VWAP   — সপ্তাহের প্রথম candle থেকে anchor
   → Swing traders use করে। Weekly consensus price।

3. EVENT VWAP    — BOS/CHoCH candle থেকে anchor
   → সবচেয়ে powerful। Market structure break-এর পর নতুন VWAP zone।
   Smart money কোথায় accumulate করছে তা দেখায়।

কীভাবে ব্যবহার করবে:
  - Price > Anchored VWAP → LONG bias
  - Price < Anchored VWAP → SHORT bias
  - Price at VWAP ± 0.3% → High probability entry zone
  - Multiple VWAP agree → Strong confluence

Signal generation-এ:
  - Session VWAP: Tier2 vwap_position replace করবে (বেশি accurate)
  - Event VWAP: Tier3 bonus (+3 pts) — BOS-anchored VWAP near entry = strong
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class AnchoredVWAPResult:
    session_vwap: float          # দিনের শুরু থেকে
    weekly_vwap: float           # সপ্তাহের শুরু থেকে
    event_vwap: Optional[float]  # BOS/CHoCH থেকে (None if no event)
    event_anchor_idx: int        # কোন candle থেকে event VWAP শুরু
    price_vs_session: str        # "ABOVE" / "BELOW" / "AT"
    price_vs_weekly: str
    price_vs_event: str          # "ABOVE" / "BELOW" / "AT" / "NO_EVENT"
    confluence_score: int        # 0-3: কতটা VWAP একমত
    confluence_direction: str    # "LONG" / "SHORT" / "MIXED"
    deviation_pct: Dict[str, float]  # % deviation from each VWAP


class AnchoredVWAPAnalyzer:
    """
    Calculates session, weekly, and event-anchored VWAPs from OHLCV data.
    
    OHLCV format: [timestamp_ms, open, high, low, close, volume]
    Timestamps used to determine session/weekly boundaries.
    """

    AT_VWAP_THRESHOLD_PCT = 0.30   # ±0.30% = "AT" VWAP

    def analyze(
        self,
        ohlcv: List[List[float]],
        bos_idx: Optional[int] = None   # index of BOS/CHoCH candle
    ) -> AnchoredVWAPResult:
        """
        Main analysis function.
        
        Args:
            ohlcv: List of OHLCV candles
            bos_idx: Index of the BOS/CHoCH candle for event VWAP.
                     If None, auto-detects from volume spike.
        """
        if len(ohlcv) < 5:
            price = float(ohlcv[-1][4]) if ohlcv else 0
            return self._empty_result(price)

        current_price = float(ohlcv[-1][4])

        # ── 1. Session VWAP (today's candles) ─────────────────────────
        session_candles = self._get_session_candles(ohlcv)
        session_vwap = self._calculate_vwap(session_candles)

        # ── 2. Weekly VWAP ─────────────────────────────────────────────
        weekly_candles = self._get_weekly_candles(ohlcv)
        weekly_vwap = self._calculate_vwap(weekly_candles)

        # ── 3. Event VWAP (BOS/CHoCH anchor) ──────────────────────────
        if bos_idx is None:
            bos_idx = self._auto_detect_event(ohlcv)

        event_vwap = None
        event_anchor_idx = -1
        if bos_idx is not None and 0 <= bos_idx < len(ohlcv):
            event_candles = ohlcv[bos_idx:]
            if len(event_candles) >= 3:
                event_vwap = self._calculate_vwap(event_candles)
                event_anchor_idx = bos_idx

        # ── 4. Position relative to each VWAP ────────────────────────
        pos_session = self._classify_position(current_price, session_vwap)
        pos_weekly  = self._classify_position(current_price, weekly_vwap)
        pos_event   = (
            self._classify_position(current_price, event_vwap)
            if event_vwap else "NO_EVENT"
        )

        # ── 5. Confluence ─────────────────────────────────────────────
        score, direction = self._confluence(pos_session, pos_weekly, pos_event)

        # ── 6. Deviation % ───────────────────────────────────────────
        deviation = {
            "session": self._deviation_pct(current_price, session_vwap),
            "weekly":  self._deviation_pct(current_price, weekly_vwap),
            "event":   self._deviation_pct(current_price, event_vwap) if event_vwap else 0.0,
        }

        event_vwap_str = f"{event_vwap:.4f}" if event_vwap else "N/A"
        logger.debug(
            f"AVWAP | Session={session_vwap:.4f}({pos_session}) "
            f"Weekly={weekly_vwap:.4f}({pos_weekly}) "
            f"Event={event_vwap_str}({pos_event}) "
            f"Confluence={score}/{direction}"
        )

        return AnchoredVWAPResult(
            session_vwap=round(session_vwap, 8),
            weekly_vwap=round(weekly_vwap, 8),
            event_vwap=round(event_vwap, 8) if event_vwap else None,
            event_anchor_idx=event_anchor_idx,
            price_vs_session=pos_session,
            price_vs_weekly=pos_weekly,
            price_vs_event=pos_event,
            confluence_score=score,
            confluence_direction=direction,
            deviation_pct=deviation,
        )

    # ── VWAP calculation ──────────────────────────────────────────────

    def _calculate_vwap(self, candles: List[List[float]]) -> float:
        """Standard VWAP: Σ(typical_price × volume) / Σ(volume)"""
        if not candles:
            return 0.0
        total_pv = 0.0
        total_vol = 0.0
        for c in candles:
            tp = (float(c[2]) + float(c[3]) + float(c[4])) / 3
            vol = float(c[5])
            total_pv  += tp * vol
            total_vol += vol
        return total_pv / total_vol if total_vol > 0 else float(candles[-1][4])

    # ── Session boundary detection ────────────────────────────────────

    def _get_session_candles(self, ohlcv: List[List[float]]) -> List[List[float]]:
        """
        Return candles from today's session start.
        Uses timestamp_ms to find where the UTC day started.
        If no timestamp → fallback to last 96 candles (15m × 96 = 24h).
        """
        if not ohlcv or not ohlcv[0][0]:
            return ohlcv[-96:] if len(ohlcv) >= 96 else ohlcv

        try:
            # Find today's UTC midnight
            last_ts = int(ohlcv[-1][0])
            last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            midnight_ts = int(datetime(
                last_dt.year, last_dt.month, last_dt.day,
                tzinfo=timezone.utc
            ).timestamp() * 1000)

            session = [c for c in ohlcv if int(c[0]) >= midnight_ts]
            return session if session else ohlcv[-96:]
        except Exception:
            return ohlcv[-96:]

    def _get_weekly_candles(self, ohlcv: List[List[float]]) -> List[List[float]]:
        """
        Return candles from this week's Monday UTC 00:00.
        Fallback: last 672 candles (15m × 672 = 7 days).
        """
        if not ohlcv or not ohlcv[0][0]:
            return ohlcv[-672:] if len(ohlcv) >= 672 else ohlcv

        try:
            last_ts = int(ohlcv[-1][0])
            last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
            # Go back to Monday
            days_since_monday = last_dt.weekday()  # Mon=0
            monday_dt = datetime(
                last_dt.year, last_dt.month, last_dt.day,
                tzinfo=timezone.utc
            )
            from datetime import timedelta
            monday_dt -= timedelta(days=days_since_monday)
            monday_ts = int(monday_dt.timestamp() * 1000)

            weekly = [c for c in ohlcv if int(c[0]) >= monday_ts]
            return weekly if weekly else ohlcv[-672:]
        except Exception:
            return ohlcv[-672:]

    # ── Event detection ───────────────────────────────────────────────

    def _auto_detect_event(self, ohlcv: List[List[float]]) -> Optional[int]:
        """
        Auto-detect BOS/CHoCH candle from volume spike.
        Largest volume candle in last 30 candles = likely structure candle.
        Only use if volume is > 2x average (significant event).
        """
        lookback = min(30, len(ohlcv))
        if lookback < 10:
            return None

        recent = ohlcv[-lookback:]
        volumes = [float(c[5]) for c in recent]
        avg_vol = sum(volumes[:-5]) / max(len(volumes) - 5, 1)
        max_vol = max(volumes)

        if avg_vol > 0 and max_vol >= avg_vol * 2.0:
            local_idx = volumes.index(max_vol)
            global_idx = len(ohlcv) - lookback + local_idx
            # Need at least 3 candles after event for VWAP to be meaningful
            if global_idx < len(ohlcv) - 3:
                return global_idx
        return None

    # ── Classification helpers ────────────────────────────────────────

    def _classify_position(self, price: float, vwap: float) -> str:
        if vwap <= 0:
            return "UNKNOWN"
        dev_pct = abs(price - vwap) / vwap * 100
        if dev_pct <= self.AT_VWAP_THRESHOLD_PCT:
            return "AT"
        return "ABOVE" if price > vwap else "BELOW"

    def _deviation_pct(self, price: float, vwap: Optional[float]) -> float:
        if not vwap or vwap <= 0:
            return 0.0
        return round((price - vwap) / vwap * 100, 4)

    def _confluence(
        self, pos_session: str, pos_weekly: str, pos_event: str
    ) -> Tuple[int, str]:
        """
        Score: 1 pt per VWAP that agrees with direction.
        Direction: LONG if price above, SHORT if below.
        AT = neutral (0.5 — treated as both).
        """
        long_count = 0
        short_count = 0

        for pos in [pos_session, pos_weekly, pos_event]:
            if pos == "ABOVE":
                long_count += 1
            elif pos == "BELOW":
                short_count += 1
            elif pos == "AT":
                long_count += 0.5
                short_count += 0.5
            # NO_EVENT or UNKNOWN → skip

        score = max(long_count, short_count)
        score = round(score)  # 0, 1, 2, or 3

        if long_count > short_count:
            direction = "LONG"
        elif short_count > long_count:
            direction = "SHORT"
        else:
            direction = "MIXED"

        return score, direction

    def _empty_result(self, price: float) -> AnchoredVWAPResult:
        return AnchoredVWAPResult(
            session_vwap=price,
            weekly_vwap=price,
            event_vwap=None,
            event_anchor_idx=-1,
            price_vs_session="UNKNOWN",
            price_vs_weekly="UNKNOWN",
            price_vs_event="NO_EVENT",
            confluence_score=0,
            confluence_direction="MIXED",
            deviation_pct={"session": 0.0, "weekly": 0.0, "event": 0.0},
        )
