"""
ARUNABHA ALGO BOT - Position Sizing Calculator
Calculates optimal position size based on risk parameters
"""

import logging
from typing import Dict, Optional
import math

import config
from core.constants import MarketType

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Calculates position sizes with multiple risk adjustments
    """
    
    def __init__(self):
        self.max_position_pct = config.MAX_POSITION_PCT
        self.min_position = config.MIN_POSITION_SIZE
    
    def calculate(
        self,
        account_size: float,
        entry: float,
        stop_loss: float,
        atr_pct: float = 1.0,
        fear_index: int = 50,
        market_type: MarketType = MarketType.UNKNOWN,
        custom_risk_pct: Optional[float] = None
    ) -> Dict:
        """
        Calculate optimal position size
        
        Returns:
            Dict with position details or {"blocked": True, "reason": "..."}
        """
        # Validate inputs
        if account_size <= 0:
            return {"blocked": True, "reason": "Invalid account size"}
        
        if entry <= 0 or stop_loss <= 0:
            return {"blocked": True, "reason": "Invalid price levels"}
        
        if entry == stop_loss:
            return {"blocked": True, "reason": "Entry equals stop loss"}
        
        # Calculate stop distance
        stop_distance = abs(entry - stop_loss)
        stop_distance_pct = (stop_distance / entry) * 100
        
        if stop_distance_pct < 0.1:
            return {"blocked": True, "reason": f"Stop too tight: {stop_distance_pct:.2f}%"}
        
        if stop_distance_pct > 5.0:
            return {"blocked": True, "reason": f"Stop too wide: {stop_distance_pct:.2f}%"}
        
        # Base risk amount
        risk_pct = custom_risk_pct if custom_risk_pct else config.RISK_PER_TRADE
        risk_amount = account_size * (risk_pct / 100)
        
        # Calculate base position size
        position_usd = risk_amount / (stop_distance_pct / 100)
        
        # Apply adjustments
        position_usd = self._apply_atr_adjustment(position_usd, atr_pct)
        position_usd = self._apply_fear_adjustment(position_usd, fear_index)
        position_usd = self._apply_market_adjustment(position_usd, market_type)
        
        # Apply maximum position limit
        max_position = account_size * (self.max_position_pct / 100)
        position_usd = min(position_usd, max_position)
        
        # Apply minimum position
        if position_usd < self.min_position:
            return {"blocked": True, "reason": f"Position too small: ${position_usd:.2f}"}
        
        # Calculate contracts
        contracts = position_usd / entry
        
        return {
            "position_usd": round(position_usd, 2),
            "contracts": round(contracts, 4),
            "risk_usd": round(risk_amount, 2),
            "risk_pct": risk_pct,
            "stop_distance_pct": round(stop_distance_pct, 2),
            "atr_pct": round(atr_pct, 2),
            "fear_index": fear_index,
            "entry": entry,
            "stop_loss": stop_loss,
            "leverage": position_usd / account_size,
            "max_position": max_position
        }
    
    def _apply_atr_adjustment(self, position_usd: float, atr_pct: float) -> float:
        """Adjust position based on ATR"""
        if atr_pct > config.MAX_ATR_PCT:
            # Too volatile - block
            return 0
        
        if atr_pct > 2.5:  # High volatility
            return position_usd * 0.5
        elif atr_pct < 0.5:  # Low volatility
            return position_usd * 0.7
        else:
            return position_usd
    
    def _apply_fear_adjustment(self, position_usd: float, fear_index: int) -> float:
        """Adjust position based on fear/greed index"""
        if fear_index < 20:  # Extreme fear
            return position_usd * 0.5
        elif fear_index < 40:  # Fear
            return position_usd * 0.8
        elif fear_index > 75:  # Extreme greed
            return position_usd * 0.3
        elif fear_index > 60:  # Greed
            return position_usd * 0.7
        else:
            return position_usd
    
    def _apply_market_adjustment(self, position_usd: float, market_type: MarketType) -> float:
        """Adjust position based on market type"""
        adjustments = {
            MarketType.TRENDING: 1.0,
            MarketType.CHOPPY: 0.8,
            MarketType.HIGH_VOL: 0.5,
            MarketType.UNKNOWN: 0.9
        }
        
        multiplier = adjustments.get(market_type, 0.9)
        return position_usd * multiplier
    
    def calculate_scaled_entry(
        self,
        account_size: float,
        entry_min: float,
        entry_max: float,
        stop_loss: float,
        num_entries: int = 3
    ) -> Dict:
        """
        Calculate scaled entry positions
        """
        if num_entries < 1:
            num_entries = 1
        
        entries = []
        total_risk = 0
        step = (entry_max - entry_min) / (num_entries - 1) if num_entries > 1 else 0
        
        for i in range(num_entries):
            entry_price = entry_min + (step * i)
            
            # Calculate position for this entry (split risk equally)
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
                total_risk += position["risk_usd"]
        
        if not entries:
            return {"blocked": True, "reason": "No valid entries"}
        
        return {
            "entries": entries,
            "total_position_usd": sum(e["position_usd"] for e in entries),
            "total_risk_usd": total_risk,
            "avg_entry": sum(e["entry"] * e["position_usd"] for e in entries) / sum(e["position_usd"] for e in entries) if entries else 0
        }
    
    def calculate_pyramid(
        self,
        base_position: Dict,
        add_price: float,
        add_size_pct: float = 0.5
    ) -> Optional[Dict]:
        """
        Calculate pyramid position addition
        """
        if "blocked" in base_position:
            return None
        
        base_entry = base_position["entry"]
        base_size = base_position["position_usd"]
        
        # Calculate additional position (50% of base by default)
        add_size = base_size * add_size_pct
        
        # Use same stop loss as base
        stop_loss = base_position["stop_loss"]
        
        # Calculate contracts for addition
        add_contracts = add_size / add_price
        
        return {
            "add_price": add_price,
            "add_size_usd": add_size,
            "add_contracts": add_contracts,
            "new_avg_entry": (base_entry * base_size + add_price * add_size) / (base_size + add_size),
            "new_total_size": base_size + add_size,
            "new_total_contracts": base_position["contracts"] + add_contracts
        }
