"""
ARUNABHA ALGO BOT - Tier 1 Filters
Mandatory filters - must pass all to continue
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

import config
from core.constants import MarketType, BTCRegime, SessionType
from analysis.technical import TechnicalAnalyzer
from analysis.market_regime import BTCRegimeResult

logger = logging.getLogger(__name__)


class Tier1Filters:
    """
    Tier 1 mandatory filters
    All must pass for signal to be considered
    """
    
    def __init__(self):
        self.analyzer = TechnicalAnalyzer()
    
    def evaluate_all(
        self,
        symbol: str,
        direction: Optional[str],
        market_type: MarketType,
        btc_regime: BTCRegimeResult,
        data: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluate all Tier 1 filters with detailed messages
        """
        results = {}
        
        # Filter 1: BTC Regime
        btc_passed, btc_msg = self._check_btc_regime(btc_regime, direction)
        results["btc_regime"] = {
            "passed": btc_passed,
            "message": btc_msg,
            "weight": "MANDATORY"
        }
        
        # Filter 2: Market Structure
        struct_passed, struct_msg = self._check_structure(data)
        results["structure"] = {
            "passed": struct_passed,
            "message": struct_msg,
            "weight": "MANDATORY"
        }
        
        # Filter 3: Volume
        vol_passed, vol_msg = self._check_volume(data)
        results["volume"] = {
            "passed": vol_passed,
            "message": vol_msg,
            "weight": "MANDATORY"
        }
        
        # Filter 4: Liquidity
        liq_passed, liq_msg = self._check_liquidity(data)
        results["liquidity"] = {
            "passed": liq_passed,
            "message": liq_msg,
            "weight": "MANDATORY"
        }
        
        # Filter 5: Session
        session_passed, session_msg = self._check_session()
        results["session"] = {
            "passed": session_passed,
            "message": session_msg,
            "weight": "MANDATORY"
        }
        
        # Overall result - ALL must pass
        all_passed = all(r["passed"] for r in results.values())
        
        return all_passed, results
    
    def _check_btc_regime(
        self,
        btc_regime: BTCRegimeResult,
        direction: Optional[str]
    ) -> Tuple[bool, str]:
        """Check if BTC regime allows trading"""
        
        if not btc_regime:
            return False, "BTC regime data not available"
        
        if not btc_regime.can_trade:
            return False, f"BTC regime blocks: {btc_regime.reason}"
        
        # If direction specified, check alignment
        if direction:
            if direction == "LONG" and btc_regime.direction == "DOWN":
                return False, f"BTC {btc_regime.direction} but trying LONG"
            if direction == "SHORT" and btc_regime.direction == "UP":
                return False, f"BTC {btc_regime.direction} but trying SHORT"
        
        # Check confidence
        if btc_regime.confidence < 20:
            return False, f"BTC confidence too low: {btc_regime.confidence}%"
        
        return True, f"BTC {btc_regime.regime.value} ({btc_regime.confidence}%, {btc_regime.direction})"
    
    def _check_structure(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Check market structure"""
        
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, "Insufficient data for structure (need 20 candles)"
        
        from analysis.structure import StructureDetector
        detector = StructureDetector()
        structure = detector.detect(ohlcv)
        
        # Must have clear structure
        if structure.strength == "WEAK" and not structure.bos_detected:
            return False, f"Structure too weak: {structure.reason}"
        
        return True, f"Structure: {structure.direction} ({structure.strength})"
    
    def _check_volume(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Check volume conditions"""
        
        ohlcv = data.get("ohlcv", {}).get("15m", [])
        if len(ohlcv) < 20:
            return False, "Insufficient data for volume check (need 20 candles)"
        
        recent_volumes = [c[5] for c in ohlcv[-5:]]
        avg_volume = sum(recent_volumes[:-1]) / (len(recent_volumes)-1) if len(recent_volumes) > 1 else recent_volumes[0]
        current_volume = recent_volumes[-1]
        
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        # Volume must be at least 70% of average
        if volume_ratio < 0.7:
            return False, f"Volume too low: {volume_ratio:.1f}x average"
        
        return True, f"Volume: {volume_ratio:.1f}x average"
    
    def _check_liquidity(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Check liquidity conditions"""
        
        orderbook = data.get("orderbook", {})
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        if not bids or not asks:
            return True, "No orderbook data - allowing"  # Optional if no data
        
        # Check spread
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        
        if best_bid and best_ask:
            spread_pct = (best_ask - best_bid) / best_bid * 100
            if spread_pct > 0.1:  # Spread > 0.1%
                return False, f"Spread too wide: {spread_pct:.3f}%"
        
        # Check market depth
        bid_depth = sum(b[1] for b in bids[:5])
        ask_depth = sum(a[1] for a in asks[:5])
        
        if bid_depth < 10000 or ask_depth < 10000:  # Less than $10k depth
            return False, f"Insufficient depth: Bid ${bid_depth:,.0f}, Ask ${ask_depth:,.0f}"
        
        spread_pct = (best_ask - best_bid) / best_bid * 100 if best_bid else 0
        return True, f"Spread: {spread_pct:.3f}%, Depth: ${bid_depth+ask_depth:,.0f}"
    
    def _check_session(self) -> Tuple[bool, str]:
        """Check if current session is tradable"""
        
        from datetime import datetime
        import pytz
        
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        hour = now.hour
        
        # Check if in avoid times
        for start, end, name in config.AVOID_TIMES:
            if start <= hour < end:
                return False, f"Avoid time: {name} ({hour:02d}:00-{end:02d}:00 IST)"
        
        # Determine current session
        if 7 <= hour < 11:
            return True, f"Active session: ASIA ({hour:02d}:00 IST)"
        elif 13 <= hour < 17:
            return True, f"Active session: LONDON ({hour:02d}:00 IST)"
        elif 17 <= hour < 22:
            return True, f"Active session: NY ({hour:02d}:00 IST)"
        elif 22 <= hour < 24:
            return True, f"Active session: OVERLAP ({hour:02d}:00 IST)"
        else:
            return False, f"Dead zone - no trading ({hour:02d}:00 IST)"