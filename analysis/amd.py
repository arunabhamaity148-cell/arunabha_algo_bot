"""
ARUNABHA ALGO BOT — AMD Detector v1.0
======================================
ICT Accumulation → Manipulation → Distribution

তিনটা phase detect করে:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACCUMULATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Smart money quietly position নেয়।
Price sideways range-এ আটকে থাকে।
Volume কম, ATR কম, কোনো clear direction নেই।

Signal use: BLOCK। এই phase-এ trade নয়।

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANIPULATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Retail stops sweep করে liquidity নেয়।
False breakout — range উপরে/নিচে wick করে ফিরে আসে।
Asia session range often swept by London open।

Signal use: সবচেয়ে POWERFUL entry signal।
Manipulation শেষ হলে = Distribution শুরু।
Entry zone: manipulation candle-এর 50% retracement।

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DISTRIBUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real move শুরু। Smart money position distribute করে।
Strong momentum candles, volume বাড়ে, structure break।
FVG (Fair Value Gap) তৈরি হয়।

Signal use: LONG/SHORT সিগনাল confirm।
Early distribution: aggressive entry।
Late distribution: avoid (momentum শেষ হচ্ছে)।

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SESSION AMD PATTERN (Highest Probability)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Asia session   (7-11 IST)  → ACCUMULATION (range তৈরি)
London open   (13-15 IST)  → MANIPULATION (Asia range sweep)
London/NY     (15-22 IST)  → DISTRIBUTION (real move)

এই pattern daily repeat হয়। Session-aware AMD = strongest signal।
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────
ACCUM_ATR_THRESHOLD   = 0.6   # ATR ratio নিচে = accumulation (choppy)
ACCUM_RANGE_CANDLES   = 20    # এত candle range check করবো
ACCUM_MAX_RANGE_PCT   = 2.0   # ২% এর মধ্যে সব candle = sideways

MANIP_WICK_PCT        = 0.50  # wick > 50% = manipulation candle (was 0.55)
MANIP_REVERSE_PCT     = 0.60  # reverse-এ এত % ফিরতে হবে
MANIP_LOOKBACK        = 15    # শেষ কয়টা candle check (was 6)

DISTRIB_MOMENTUM_MIN  = 1.1   # avg volume এর এতগুণ (was 1.3, too strict)
DISTRIB_BODY_PCT      = 0.45  # candle body > ৪৫% = directional (was 0.55)
DISTRIB_LOOKBACK      = 5

FVG_MIN_GAP_PCT       = 0.10  # minimum ০.১০% gap = Fair Value Gap


@dataclass
class FairValueGap:
    direction: str        # "BULL" or "BEAR"
    top: float            # gap উপরের দিক
    bottom: float         # gap নিচের দিক
    midpoint: float       # entry zone center
    gap_pct: float        # gap size %
    candle_idx: int       # কোন candle-এ তৈরি হয়েছে
    filled: bool = False  # price কি FVG fill করেছে


@dataclass
class AMDResult:
    # Current phase
    phase: str                    # "ACCUMULATION" / "MANIPULATION" / "DISTRIBUTION" / "UNKNOWN"
    phase_confidence: int         # 0-100
    phase_reason: str

    # Manipulation details
    manipulation_detected: bool
    manipulation_direction: str   # "BULL_SWEEP" / "BEAR_SWEEP" / "NONE"
    manipulation_level: float     # swept level
    manipulation_candle_idx: int  # candle index
    post_manipulation: bool       # manipulation শেষ, distribution শুরু হচ্ছে?

    # Distribution details
    distribution_active: bool
    distribution_direction: str   # "LONG" / "SHORT" / "NONE"
    distribution_strength: str    # "STRONG" / "MODERATE" / "WEAK"
    momentum_ratio: float         # current volume / avg volume

    # Fair Value Gaps
    fair_value_gaps: List[FairValueGap]
    nearest_fvg: Optional[FairValueGap]

    # Session context
    session_phase: str            # "ASIA_ACCUM" / "LONDON_MANIP" / "NY_DISTRIB" / "UNKNOWN"
    session_amd_valid: bool       # session pattern match করছে?

    # Trade signal
    amd_signal: str               # "LONG" / "SHORT" / "WAIT" / "BLOCK"
    amd_entry_zone: Tuple[float, float]  # (lower, upper) entry price range
    amd_score: int                # 0-10: কতটা strong setup


class AMDDetector:
    """
    ICT AMD (Accumulation, Manipulation, Distribution) detector.

    Bot-এ integration:
      Tier1: ACCUMULATION phase → BLOCK signal
      Tier2: MANIPULATION end detected → +15 pts (strong entry zone)
      Tier3: DISTRIBUTION + FVG → +6 pts bonus
    """

    def analyze(
        self,
        ohlcv: List[List[float]],
        direction: Optional[str] = None,
        session_hour_ist: Optional[int] = None,
    ) -> AMDResult:
        """
        Full AMD analysis।

        Args:
            ohlcv: OHLCV candles [ts, open, high, low, close, volume]
            direction: expected trade direction ("LONG"/"SHORT"/None)
            session_hour_ist: current IST hour (0-23) for session AMD
        """
        if len(ohlcv) < 30:
            return self._unknown_result(ohlcv)

        current_price = float(ohlcv[-1][4])
        atr           = self._calc_atr(ohlcv)
        avg_vol       = self._avg_volume(ohlcv, 20)

        # ── 1. Detect phase ───────────────────────────────────────
        accum_conf, accum_reason = self._detect_accumulation(ohlcv, atr)
        manip_result             = self._detect_manipulation(ohlcv)
        distrib_result           = self._detect_distribution(ohlcv, avg_vol)

        # Phase priority: Manipulation > Distribution > Accumulation
        if manip_result["detected"] and manip_result["post_manip"]:
            phase           = "DISTRIBUTION"
            phase_conf      = 80
            phase_reason    = f"Post-manipulation: {manip_result['direction']}"
        elif manip_result["detected"]:
            phase           = "MANIPULATION"
            phase_conf      = 75
            phase_reason    = f"Manipulation sweep: {manip_result['direction']}"
        elif distrib_result["active"] and accum_conf < 50:
            phase           = "DISTRIBUTION"
            phase_conf      = distrib_result["confidence"]
            phase_reason    = distrib_result["reason"]
        elif accum_conf >= 60:
            phase           = "ACCUMULATION"
            phase_conf      = accum_conf
            phase_reason    = accum_reason
        else:
            phase           = "UNKNOWN"
            phase_conf      = 30
            phase_reason    = "No clear AMD phase"

        # ── 2. Fair Value Gaps ────────────────────────────────────
        fvgs         = self._detect_fvg(ohlcv)
        nearest_fvg  = self._find_nearest_fvg(fvgs, current_price, direction)

        # ── 3. Session AMD ────────────────────────────────────────
        sess_phase, sess_valid = self._session_amd(
            session_hour_ist, phase, manip_result, direction
        )

        # ── 4. Trade signal ───────────────────────────────────────
        signal, entry_zone, score = self._generate_signal(
            phase, manip_result, distrib_result,
            nearest_fvg, direction, current_price, atr,
            sess_valid
        )

        logger.debug(
            f"AMD | Phase={phase}({phase_conf}%) "
            f"Manip={manip_result['detected']} "
            f"Distrib={distrib_result['active']} "
            f"FVGs={len(fvgs)} Session={sess_phase} "
            f"Signal={signal}({score}/10)"
        )

        return AMDResult(
            phase=phase,
            phase_confidence=phase_conf,
            phase_reason=phase_reason,
            manipulation_detected=manip_result["detected"],
            manipulation_direction=manip_result["direction"],
            manipulation_level=manip_result["level"],
            manipulation_candle_idx=manip_result["idx"],
            post_manipulation=manip_result["post_manip"],
            distribution_active=distrib_result["active"],
            distribution_direction=distrib_result["direction"],
            distribution_strength=distrib_result["strength"],
            momentum_ratio=distrib_result["momentum_ratio"],
            fair_value_gaps=fvgs,
            nearest_fvg=nearest_fvg,
            session_phase=sess_phase,
            session_amd_valid=sess_valid,
            amd_signal=signal,
            amd_entry_zone=entry_zone,
            amd_score=score,
        )

    # ── Phase Detection ───────────────────────────────────────────

    def _detect_accumulation(
        self, ohlcv: List, atr: float
    ) -> Tuple[int, str]:
        """
        Accumulation = sideways range, low ATR, no breakout।

        Check:
        1. ATR recent < ATR average × threshold
        2. High-low range < ACCUM_MAX_RANGE_PCT% over N candles
        3. No strong directional candle in last N candles
        """
        n       = min(ACCUM_RANGE_CANDLES, len(ohlcv) - 1)
        recent  = ohlcv[-n:]

        highs   = [float(c[2]) for c in recent]
        lows    = [float(c[3]) for c in recent]
        closes  = [float(c[4]) for c in recent]

        rng_pct = (max(highs) - min(lows)) / min(lows) * 100 if min(lows) > 0 else 99

        # ATR comparison
        recent_atr = self._calc_atr(ohlcv[-n:]) if len(ohlcv) >= n + 5 else atr
        full_atr   = atr
        atr_ratio  = recent_atr / full_atr if full_atr > 0 else 1.0

        # Directional bias
        up_candles   = sum(1 for c in recent if float(c[4]) > float(c[1]))
        down_candles = n - up_candles
        bias_score   = abs(up_candles - down_candles) / n

        reasons = []
        score   = 0

        if rng_pct < ACCUM_MAX_RANGE_PCT:
            score += 40
            reasons.append(f"Range {rng_pct:.1f}%<{ACCUM_MAX_RANGE_PCT}%")
        if atr_ratio < ACCUM_ATR_THRESHOLD:
            score += 35
            reasons.append(f"ATR ratio {atr_ratio:.2f} (low)")
        if bias_score < 0.3:
            score += 25
            reasons.append(f"No directional bias ({bias_score:.2f})")

        return score, " | ".join(reasons) if reasons else "Not accumulation"

    def _detect_manipulation(self, ohlcv: List) -> Dict:
        """
        Manipulation = false breakout with big wick + reverse।

        Algorithm:
        - Look at candles one-by-one from -15 to -2
        - For each candle, ref range = 20 candles BEFORE that candle
        - Check: wick breaks ref range? close back inside?
        - This way ref never includes the manipulation candle itself
        """
        null = {"detected": False, "direction": "NONE", "level": 0.0,
                "idx": -1, "post_manip": False}

        min_context = 25   # need at least this many candles before checking
        if len(ohlcv) < min_context + 3:
            return null

        # Scan last 15 candles for manipulation (not last 1)
        scan_end   = len(ohlcv) - 1   # don't check current candle
        scan_start = max(min_context, len(ohlcv) - 15)

        for idx in range(scan_start, scan_end):
            c     = ohlcv[idx]
            o, h  = float(c[1]), float(c[2])
            l, cl = float(c[3]), float(c[4])
            rng   = h - l
            if rng <= 0:
                continue

            # Reference range: 20 candles strictly BEFORE this candle
            ref_end_i   = idx
            ref_start_i = max(0, ref_end_i - 20)
            ref         = ohlcv[ref_start_i:ref_end_i]
            if len(ref) < 5:
                continue

            ref_high = max(float(c2[2]) for c2 in ref)
            ref_low  = min(float(c2[3]) for c2 in ref)

            upper_wick = (h - max(o, cl)) / rng
            lower_wick = (min(o, cl) - l) / rng

            # BULL SWEEP: wick above ref_high, close back inside
            if (h > ref_high * 1.001 and
                    upper_wick > MANIP_WICK_PCT and
                    cl < ref_high):
                post       = ohlcv[idx + 1:]
                post_rev   = len(post) >= 1 and float(post[0][4]) < cl
                return {
                    "detected":   True,
                    "direction":  "BULL_SWEEP",
                    "level":      ref_high,
                    "idx":        idx,
                    "post_manip": post_rev,
                    "wick_pct":   round(upper_wick, 2),
                }

            # BEAR SWEEP: wick below ref_low, close back inside
            if (l < ref_low * 0.999 and
                    lower_wick > MANIP_WICK_PCT and
                    cl > ref_low):
                post       = ohlcv[idx + 1:]
                post_rev   = len(post) >= 1 and float(post[0][4]) > cl
                return {
                    "detected":   True,
                    "direction":  "BEAR_SWEEP",
                    "level":      ref_low,
                    "idx":        idx,
                    "post_manip": post_rev,
                    "wick_pct":   round(lower_wick, 2),
                }

        return null

    def _detect_distribution(self, ohlcv: List, avg_vol: float) -> Dict:
        """
        Distribution = strong momentum, increasing volume, clear direction।

        Checks:
        1. Recent candles mostly bullish or bearish (body > 55%)
        2. Volume above average
        3. Consistent direction
        """
        n      = min(DISTRIB_LOOKBACK, len(ohlcv) - 1)
        recent = ohlcv[-n:]

        bull_body = 0; bear_body = 0
        vol_sum   = 0

        for c in recent:
            o, h, l, cl, vol = float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
            rng = h - l
            if rng == 0:
                continue
            body_pct = abs(cl - o) / rng
            vol_sum  += vol
            if cl > o and body_pct > DISTRIB_BODY_PCT:
                bull_body += 1
            elif cl < o and body_pct > DISTRIB_BODY_PCT:
                bear_body += 1

        avg_recent_vol  = vol_sum / n
        momentum_ratio  = avg_recent_vol / avg_vol if avg_vol > 0 else 1.0
        high_volume     = momentum_ratio >= DISTRIB_MOMENTUM_MIN

        # Direction
        if bull_body >= 2 and bull_body > bear_body:
            direction = "LONG"
            conf      = min(100, bull_body * 20 + (20 if high_volume else 0))
            strength  = "STRONG" if bull_body >= 4 else "MODERATE"
        elif bear_body >= 2 and bear_body > bull_body:
            direction = "SHORT"
            conf      = min(100, bear_body * 20 + (20 if high_volume else 0))
            strength  = "STRONG" if bear_body >= 4 else "MODERATE"
        else:
            return {"active": False, "direction": "NONE", "strength": "NONE",
                    "confidence": 0, "momentum_ratio": momentum_ratio,
                    "reason": "No clear distribution"}

        active = conf >= 30 and (high_volume or bull_body + bear_body >= 2)
        return {
            "active": active,
            "direction": direction,
            "strength": strength,
            "confidence": conf,
            "momentum_ratio": round(momentum_ratio, 2),
            "reason": (
                f"{'Bull' if direction=='LONG' else 'Bear'} dist: "
                f"{bull_body if direction=='LONG' else bear_body}/{n} candles, "
                f"vol {momentum_ratio:.1f}x"
            ),
        }

    # ── Fair Value Gap ────────────────────────────────────────────

    def _detect_fvg(self, ohlcv: List, lookback: int = 30) -> List[FairValueGap]:
        """
        Fair Value Gap = 3-candle pattern যেখানে middle candle-এর
        high/low, আগের ও পরের candle overlap করে না।

        BULL FVG: candle[i+2].low > candle[i].high
          → Gap between i.high and (i+2).low
          → Bullish imbalance, price likely returns to fill

        BEAR FVG: candle[i+2].high < candle[i].low
          → Gap between i.low and (i+2).high
          → Bearish imbalance
        """
        fvgs    = []
        n       = min(lookback, len(ohlcv) - 2)
        current = float(ohlcv[-1][4])

        for i in range(len(ohlcv) - n, len(ohlcv) - 2):
            if i < 0:
                continue
            c1, c2, c3 = ohlcv[i], ohlcv[i + 1], ohlcv[i + 2]

            h1 = float(c1[2]); l1 = float(c1[3])
            l3 = float(c3[3]); h3 = float(c3[2])

            # Bull FVG
            if l3 > h1:
                gap_pct = (l3 - h1) / h1 * 100
                if gap_pct >= FVG_MIN_GAP_PCT:
                    mid = (l3 + h1) / 2
                    filled = current <= l3   # price came down to fill
                    fvgs.append(FairValueGap(
                        direction="BULL", top=l3, bottom=h1,
                        midpoint=mid, gap_pct=round(gap_pct, 3),
                        candle_idx=i, filled=filled
                    ))

            # Bear FVG
            elif h3 < l1:
                gap_pct = (l1 - h3) / l1 * 100
                if gap_pct >= FVG_MIN_GAP_PCT:
                    mid = (h3 + l1) / 2
                    filled = current >= h3   # price came up to fill
                    fvgs.append(FairValueGap(
                        direction="BEAR", top=l1, bottom=h3,
                        midpoint=mid, gap_pct=round(gap_pct, 3),
                        candle_idx=i, filled=filled
                    ))

        # Sort by recency (newest first)
        fvgs.sort(key=lambda x: x.candle_idx, reverse=True)
        return fvgs

    def _find_nearest_fvg(
        self,
        fvgs: List[FairValueGap],
        price: float,
        direction: Optional[str]
    ) -> Optional[FairValueGap]:
        """Price-এর সবচেয়ে কাছের unfilled FVG খুঁজে দাও।"""
        unfilled = [f for f in fvgs if not f.filled]
        if not unfilled:
            return None

        # Direction filter
        if direction == "LONG":
            relevant = [f for f in unfilled if f.direction == "BULL"]
        elif direction == "SHORT":
            relevant = [f for f in unfilled if f.direction == "BEAR"]
        else:
            relevant = unfilled

        if not relevant:
            return None

        # Nearest by midpoint distance
        return min(relevant, key=lambda f: abs(f.midpoint - price))

    # ── Session AMD ───────────────────────────────────────────────

    def _session_amd(
        self,
        hour_ist: Optional[int],
        phase: str,
        manip: Dict,
        direction: Optional[str],
    ) -> Tuple[str, bool]:
        """
        Session-based AMD pattern validation।

        Asia (7-11 IST)   → Accumulation expected
        London (13-17 IST) → Manipulation expected (Asia range sweep)
        NY (18-22 IST)    → Distribution expected
        """
        if hour_ist is None:
            return "UNKNOWN", False

        if 7 <= hour_ist < 11:
            sess = "ASIA_ACCUM"
            valid = phase == "ACCUMULATION"

        elif 13 <= hour_ist < 17:
            sess = "LONDON_MANIP"
            # London: ideally manipulation in progress
            valid = (
                phase in ("MANIPULATION", "DISTRIBUTION") or
                manip["detected"]
            )

        elif 18 <= hour_ist < 22:
            sess = "NY_DISTRIB"
            valid = phase == "DISTRIBUTION"

        else:
            sess = "OFF_SESSION"
            valid = False

        return sess, valid

    # ── Signal Generation ─────────────────────────────────────────

    def _generate_signal(
        self,
        phase: str,
        manip: Dict,
        distrib: Dict,
        nearest_fvg: Optional[FairValueGap],
        direction: Optional[str],
        price: float,
        atr: float,
        session_valid: bool,
    ) -> Tuple[str, Tuple[float, float], int]:
        """
        AMD trade signal generate করো।

        Returns: (signal, entry_zone, score)
          signal: "LONG" / "SHORT" / "WAIT" / "BLOCK"
          entry_zone: (lower_price, upper_price)
          score: 0-10
        """
        null_zone = (price * 0.999, price * 1.001)

        # BLOCK: Accumulation phase
        if phase == "ACCUMULATION":
            return "BLOCK", null_zone, 0

        score = 0
        signal = "WAIT"
        entry_low = price - atr * 0.5
        entry_high = price + atr * 0.5

        # Post-manipulation → strongest signal
        if manip["detected"] and manip["post_manip"]:
            if manip["direction"] == "BEAR_SWEEP":
                signal = "LONG"
                score += 6
                # Entry: 50% retracement of manipulation candle
                entry_low  = manip["level"]
                entry_high = price
            elif manip["direction"] == "BULL_SWEEP":
                signal = "SHORT"
                score += 6
                entry_low  = price
                entry_high = manip["level"]

        # Distribution active
        if distrib["active"]:
            if distrib["direction"] == "LONG":
                signal = "LONG"
                score += 3 if distrib["strength"] == "STRONG" else 2
            elif distrib["direction"] == "SHORT":
                signal = "SHORT"
                score += 3 if distrib["strength"] == "STRONG" else 2

        # FVG confluence
        if nearest_fvg and not nearest_fvg.filled:
            dist_pct = abs(price - nearest_fvg.midpoint) / price * 100
            if dist_pct < 0.5:   # price near FVG
                score += 2
                entry_low  = nearest_fvg.bottom
                entry_high = nearest_fvg.top

        # Session AMD valid
        if session_valid:
            score += 1

        # Direction filter
        if direction and signal != "WAIT" and signal != direction:
            score = max(0, score - 3)
            signal = "WAIT"

        return signal, (round(entry_low, 8), round(entry_high, 8)), min(score, 10)

    # ── Helpers ───────────────────────────────────────────────────

    def _calc_atr(self, ohlcv: List, period: int = 14) -> float:
        if len(ohlcv) < 2:
            return 0.0
        trs = []
        for i in range(1, min(period + 1, len(ohlcv))):
            h  = float(ohlcv[-i][2])
            l  = float(ohlcv[-i][3])
            pc = float(ohlcv[-i - 1][4])
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        return sum(trs) / len(trs) if trs else 0.0

    def _avg_volume(self, ohlcv: List, n: int = 20) -> float:
        vols = [float(c[5]) for c in ohlcv[-n - 1:-1]]
        return sum(vols) / len(vols) if vols else 1.0

    def _unknown_result(self, ohlcv: List) -> AMDResult:
        price = float(ohlcv[-1][4]) if ohlcv else 0
        return AMDResult(
            phase="UNKNOWN", phase_confidence=0,
            phase_reason="Insufficient data",
            manipulation_detected=False, manipulation_direction="NONE",
            manipulation_level=0.0, manipulation_candle_idx=-1,
            post_manipulation=False, distribution_active=False,
            distribution_direction="NONE", distribution_strength="NONE",
            momentum_ratio=1.0, fair_value_gaps=[], nearest_fvg=None,
            session_phase="UNKNOWN", session_amd_valid=False,
            amd_signal="WAIT",
            amd_entry_zone=(price * 0.999, price * 1.001),
            amd_score=0,
        )
