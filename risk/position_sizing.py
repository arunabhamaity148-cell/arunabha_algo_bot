"""
ARUNABHA ALGO BOT - Position Sizing Calculator v4.2
====================================================

Points implemented:
Point 4  — Kelly Criterion position sizing (win rate + avg RR জানার পরে)
Point 5  — Drawdown-based position scaling (5% DD → 50% size, 10% → pause)
Point 6  — State persistence integration (StateManager থেকে drawdown নেওয়া)
Point 8  — Market hours filter (low-liquidity time-এ size কমানো)
Point 10 — Regime-specific position sizing
"""

import logging
import math
from typing import Dict, Optional
from datetime import datetime

import config
from core.constants import MarketType
from utils.time_utils import ist_now

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Position sizing with Kelly Criterion + drawdown-based scaling
    """

    def __init__(self):
        self.max_position_pct = config.MAX_POSITION_PCT
        self.min_position = config.MIN_POSITION_SIZE

        # Kelly Criterion tracking
        # এই values backtest থেকে আসবে, শুরুতে conservative default
        self._kelly_win_rate: Optional[float] = None
        self._kelly_avg_win: Optional[float] = None
        self._kelly_avg_loss: Optional[float] = None
        self._kelly_fraction = 0.25   # Max Kelly fraction (25% = conservative)

    def update_kelly_params(
        self,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float
    ):
        """
        ✅ Point 4: Kelly Criterion parameters update

        Backtest বা live trading-এ পর্যাপ্ত trades হলে এই method call করো।
        তারপর Kelly-based sizing active হবে।

        Args:
            win_rate: 0.0 থেকে 1.0 (e.g. 0.55 = 55% win rate)
            avg_win_pct: Average winning trade % (e.g. 2.5)
            avg_loss_pct: Average losing trade % (positive, e.g. 1.2)
        """
        if avg_loss_pct <= 0:
            return

        self._kelly_win_rate = win_rate
        self._kelly_avg_win = avg_win_pct
        self._kelly_avg_loss = avg_loss_pct

        kelly = self._calculate_kelly_fraction(win_rate, avg_win_pct, avg_loss_pct)
        logger.info(
            f"Kelly params updated: WR={win_rate*100:.1f}% | "
            f"Avg W={avg_win_pct:.2f}% | Avg L={avg_loss_pct:.2f}% | "
            f"Kelly={kelly*100:.1f}% → capped at {self._kelly_fraction*100:.0f}%"
        )

    def _calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Kelly Criterion formula:
        K = W - (1-W)/R
        W = win rate, R = win/loss ratio

        Full Kelly অনেক aggressive, তাই quarter Kelly (K/4) use করো।
        """
        if avg_loss <= 0:
            return 0.01
        r = avg_win / avg_loss
        kelly = win_rate - (1 - win_rate) / r
        # Quarter Kelly — aggressive কিন্তু safer
        quarter_kelly = max(0.005, min(kelly / 4, self._kelly_fraction))
        return quarter_kelly

    def calculate(
        self,
        account_size: float,
        entry: float,
        stop_loss: float,
        atr_pct: float = 1.0,
        fear_index: int = 50,
        market_type: MarketType = MarketType.UNKNOWN,
        custom_risk_pct: Optional[float] = None,
        current_drawdown_pct: float = 0.0,
        signal_grade: str = "B"
    ) -> Dict:
        """
        Calculate position size with all adjustments

        Points applied:
        4  — Kelly Criterion (if params available)
        5  — Drawdown-based scaling
        8  — Market hours adjustment
        10 — Regime-specific sizing
        """
        # Validate
        if account_size <= 0:
            return {"blocked": True, "reason": "Invalid account size"}
        if entry <= 0 or stop_loss <= 0:
            return {"blocked": True, "reason": "Invalid price levels"}
        if entry == stop_loss:
            return {"blocked": True, "reason": "Entry equals stop loss"}

        stop_distance = abs(entry - stop_loss)
        stop_distance_pct = (stop_distance / entry) * 100

        if stop_distance_pct < 0.1:
            return {"blocked": True, "reason": f"Stop too tight: {stop_distance_pct:.3f}%"}
        if stop_distance_pct > 5.0:
            return {"blocked": True, "reason": f"Stop too wide: {stop_distance_pct:.2f}%"}

        # ✅ Point 5: Drawdown-based BLOCK
        if current_drawdown_pct >= 10.0:
            return {
                "blocked": True,
                "reason": f"Trading PAUSED: drawdown {current_drawdown_pct:.1f}% ≥ 10%"
            }

        # ─────────────────────────────────────────
        # Step 1: Base risk %
        # ─────────────────────────────────────────

        # ✅ Point 4: Use Kelly if available, else fixed risk
        if (self._kelly_win_rate is not None and
                self._kelly_avg_win is not None and
                self._kelly_avg_loss is not None):
            kelly_f = self._calculate_kelly_fraction(
                self._kelly_win_rate, self._kelly_avg_win, self._kelly_avg_loss
            )
            risk_pct = kelly_f * 100  # Kelly fraction → percentage
            sizing_method = f"Kelly({kelly_f*100:.1f}%)"
        else:
            risk_pct = custom_risk_pct if custom_risk_pct else config.RISK_PER_TRADE
            sizing_method = f"Fixed({risk_pct}%)"

        risk_amount = account_size * (risk_pct / 100)

        # Base position
        position_usd = risk_amount / (stop_distance_pct / 100)

        # ─────────────────────────────────────────
        # Step 2: Adjustments
        # ─────────────────────────────────────────

        # ATR adjustment
        position_usd = self._apply_atr_adjustment(position_usd, atr_pct)
        if position_usd == 0:
            return {"blocked": True, "reason": f"ATR too high: {atr_pct:.2f}%"}

        # Fear/Greed adjustment
        position_usd = self._apply_fear_adjustment(position_usd, fear_index)

        # ✅ Point 10: Regime-specific sizing
        position_usd = self._apply_regime_adjustment(position_usd, market_type)

        # ✅ Point 5: Drawdown-based scaling
        dd_multiplier = self._get_drawdown_multiplier(current_drawdown_pct)
        position_usd *= dd_multiplier

        # ✅ Point 8: Market hours adjustment
        hours_multiplier = self._get_market_hours_multiplier()
        position_usd *= hours_multiplier

        # Grade-based adjustment
        grade_multiplier = self._get_grade_multiplier(signal_grade)
        position_usd *= grade_multiplier

        # Cap at maximum
        max_position = account_size * (self.max_position_pct / 100)
        position_usd = min(position_usd, max_position)

        if position_usd < self.min_position:
            return {"blocked": True, "reason": f"Position too small: ₹{position_usd:.0f}"}

        contracts = position_usd / entry

        return {
            "position_usd": round(position_usd, 2),
            "contracts": round(contracts, 6),
            "risk_usd": round(risk_amount * dd_multiplier * hours_multiplier * grade_multiplier, 2),
            "risk_pct": round(risk_pct, 3),
            "stop_distance_pct": round(stop_distance_pct, 3),
            "atr_pct": round(atr_pct, 3),
            "fear_index": fear_index,
            "entry": entry,
            "stop_loss": stop_loss,
            "leverage": round(position_usd / account_size, 3),
            "max_position": round(max_position, 2),
            "sizing_method": sizing_method,
            "drawdown_multiplier": round(dd_multiplier, 2),
            "hours_multiplier": round(hours_multiplier, 2),
            "grade_multiplier": round(grade_multiplier, 2),
            "current_drawdown_pct": round(current_drawdown_pct, 2),
        }

    def _apply_atr_adjustment(self, position_usd: float, atr_pct: float) -> float:
        if atr_pct > config.MAX_ATR_PCT:
            return 0
        if atr_pct > 2.5:
            return position_usd * 0.5
        elif atr_pct < 0.5:
            return position_usd * 0.7
        return position_usd

    def _apply_fear_adjustment(self, position_usd: float, fear_index: int) -> float:
        if fear_index < 20:
            return position_usd * 0.5
        elif fear_index < 40:
            return position_usd * 0.8
        elif fear_index > 75:
            return position_usd * 0.3
        elif fear_index > 60:
            return position_usd * 0.7
        return position_usd

    def _apply_regime_adjustment(
        self,
        position_usd: float,
        market_type: MarketType
    ) -> float:
        """
        ✅ Point 10: Regime-specific position sizing

        Trending market: full size
        Choppy market: 70% (উভয় দিকে যেতে পারে)
        High volatility: 40% (SL hit করার সম্ভাবনা বেশি)
        """
        adjustments = {
            MarketType.TRENDING: 1.0,
            MarketType.CHOPPY: 0.7,
            MarketType.HIGH_VOL: 0.4,
            MarketType.UNKNOWN: 0.8
        }
        return position_usd * adjustments.get(market_type, 0.8)

    def _get_drawdown_multiplier(self, current_drawdown_pct: float) -> float:
        """
        ✅ Point 5: Drawdown-based position scaling

        0-3%:   full size
        3-5%:   80% size
        5-7%:   50% size
        7-10%:  25% size
        10%+:   BLOCKED (handled above)
        """
        if current_drawdown_pct >= 10.0:
            return 0.0   # Already blocked above
        elif current_drawdown_pct >= 7.0:
            return 0.25
        elif current_drawdown_pct >= 5.0:
            return 0.50
        elif current_drawdown_pct >= 3.0:
            return 0.80
        return 1.0

    def _get_market_hours_multiplier(self) -> float:
        """
        ✅ Point 8: Market hours filter

        London + NY overlap (IST 22:30-02:30): full size
        London open (IST 17:00-22:30): 90%
        NY open (IST 20:00-02:30): 90%
        Asia session (IST 07:00-12:00): 70%
        Dead zone (IST 02:30-07:00): 40% (low liquidity, wide spreads)
        """
        hour = ist_now().hour

        # Dead zone: 02:30 - 07:00 IST
        if 2 <= hour < 7:
            return 0.4

        # London+NY overlap: 22:30 - 02:30 IST (best liquidity)
        if hour >= 22 or hour < 2:
            return 1.0

        # London session: 13:00 - 22:30 IST
        if 13 <= hour < 22:
            return 0.9

        # Asia session: 07:00 - 13:00 IST
        if 7 <= hour < 13:
            return 0.7

        return 0.8

    def _get_grade_multiplier(self, grade: str) -> float:
        """Grade-based position size"""
        return {
            "A+": 1.0,
            "A": 0.9,
            "B+": 0.75,
            "B": 0.6,
            "C": 0.3,
            "D": 0.0,
        }.get(grade, 0.6)

    def get_kelly_status(self) -> Dict:
        """Current Kelly parameters status"""
        if self._kelly_win_rate is None:
            return {
                "active": False,
                "message": "Kelly not active — using fixed 1% risk",
                "trades_needed": "20+ live trades required"
            }
        kelly = self._calculate_kelly_fraction(
            self._kelly_win_rate, self._kelly_avg_win, self._kelly_avg_loss
        )
        return {
            "active": True,
            "win_rate": f"{self._kelly_win_rate*100:.1f}%",
            "avg_win": f"{self._kelly_avg_win:.2f}%",
            "avg_loss": f"{self._kelly_avg_loss:.2f}%",
            "kelly_fraction": f"{kelly*100:.1f}%",
            "effective_risk_pct": f"{kelly*100:.2f}%"
        }

    def calculate_scaled_entry(
        self,
        account_size: float,
        entry_min: float,
        entry_max: float,
        stop_loss: float,
        num_entries: int = 3
    ) -> Dict:
        """Calculate scaled entry positions"""
        if num_entries < 1:
            num_entries = 1

        entries = []
        step = (entry_max - entry_min) / (num_entries - 1) if num_entries > 1 else 0

        for i in range(num_entries):
            entry_price = entry_min + (step * i)
            position = self.calculate(
                account_size=account_size,
                entry=entry_price,
                stop_loss=stop_loss,
                custom_risk_pct=config.RISK_PER_TRADE / num_entries
            )
            if "blocked" not in position:
                entries.append({
                    "entry": entry_price,
                    "position_usd": position["position_usd"],
                    "contracts": position["contracts"]
                })

        if not entries:
            return {"blocked": True, "reason": "No valid entries"}

        return {
            "entries": entries,
            "total_position_usd": sum(e["position_usd"] for e in entries),
            "avg_entry": sum(e["entry"] * e["position_usd"] for e in entries) / sum(e["position_usd"] for e in entries)
        }
