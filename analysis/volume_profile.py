"""
ARUNABHA ALGO BOT - Volume Profile Analyzer
Analyzes volume distribution and identifies key levels
"""

import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VolumeProfileResult:
    """Volume profile analysis result"""
    poc: float  # Point of Control
    vah: float  # Value Area High
    val: float  # Value Area Low
    volume_nodes: List[Dict[str, float]]
    is_expanding: bool
    buy_volume_ratio: float
    sell_volume_ratio: float


class VolumeProfileAnalyzer:
    """
    Analyzes volume profile to identify key levels
    """
    
    def __init__(self, num_bins: int = 20):
        self.num_bins = num_bins
    
    def analyze(
        self,
        ohlcv: List[List[float]],
        num_periods: int = 50
    ) -> VolumeProfileResult:
        """
        Analyze volume profile
        """
        if len(ohlcv) < num_periods:
            num_periods = len(ohlcv)
        
        recent = ohlcv[-num_periods:]
        
        # Get price range
        prices = []
        for candle in recent:
            prices.append(candle[2])  # high
            prices.append(candle[3])  # low
        
        min_price = min(prices)
        max_price = max(prices)
        
        if max_price <= min_price:
            max_price = min_price + 1
        
        bin_size = (max_price - min_price) / self.num_bins
        
        # Create volume bins
        bins = []
        for i in range(self.num_bins):
            bin_low = min_price + (i * bin_size)
            bin_high = bin_low + bin_size
            bins.append({
                "low": bin_low,
                "high": bin_high,
                "volume": 0.0,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "trades": 0
            })
        
        # Distribute volume
        total_buy_volume = 0
        total_sell_volume = 0
        
        for candle in recent:
            high = candle[2]
            low = candle[3]
            close = candle[4]
            open_price = candle[1]
            volume = candle[5]
            
            # Determine if bullish or bearish candle
            is_bullish = close > open_price
            
            for bin_data in bins:
                if high >= bin_data["low"] and low <= bin_data["high"]:
                    overlap = min(high, bin_data["high"]) - max(low, bin_data["low"])
                    if overlap > 0:
                        # Distribute volume proportionally
                        candle_range = high - low
                        if candle_range > 0:
                            volume_share = volume * (overlap / candle_range)
                            
                            bin_data["volume"] += volume_share
                            bin_data["trades"] += 1
                            
                            if is_bullish:
                                bin_data["buy_volume"] += volume_share
                                total_buy_volume += volume_share
                            else:
                                bin_data["sell_volume"] += volume_share
                                total_sell_volume += volume_share
        
        # Find POC (bin with max volume)
        poc_bin = max(bins, key=lambda x: x["volume"])
        poc = (poc_bin["low"] + poc_bin["high"]) / 2
        
        # Calculate Value Area (70% of volume)
        total_volume = sum(b["volume"] for b in bins)
        value_area_volume = total_volume * 0.7
        
        # Sort bins by volume
        sorted_bins = sorted(bins, key=lambda x: x["volume"], reverse=True)
        
        # Find value area
        current_volume = 0
        value_area_bins = []
        
        for bin_data in sorted_bins:
            if current_volume < value_area_volume:
                value_area_bins.append(bin_data)
                current_volume += bin_data["volume"]
            else:
                break
        
        if value_area_bins:
            vah = max(b["high"] for b in value_area_bins)
            val = min(b["low"] for b in value_area_bins)
        else:
            vah = max_price
            val = min_price
        
        # Check if volume is expanding
        recent_volumes = [c[5] for c in recent[-10:]]
        older_volumes = [c[5] for c in recent[-20:-10]]
        
        avg_recent = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
        avg_older = sum(older_volumes) / len(older_volumes) if older_volumes else 0
        
        is_expanding = avg_recent > avg_older * 1.2
        
        # Calculate buy/sell ratios
        total_vol = total_buy_volume + total_sell_volume
        if total_vol > 0:
            buy_ratio = total_buy_volume / total_vol * 100
            sell_ratio = total_sell_volume / total_vol * 100
        else:
            buy_ratio = 50
            sell_ratio = 50
        
        # Prepare volume nodes
        volume_nodes = []
        for bin_data in sorted(bins, key=lambda x: x["low"]):
            volume_nodes.append({
                "price": (bin_data["low"] + bin_data["high"]) / 2,
                "volume": bin_data["volume"],
                "buy_volume": bin_data["buy_volume"],
                "sell_volume": bin_data["sell_volume"],
                "trades": bin_data["trades"]
            })
        
        return VolumeProfileResult(
            poc=poc,
            vah=vah,
            val=val,
            volume_nodes=volume_nodes,
            is_expanding=is_expanding,
            buy_volume_ratio=buy_ratio,
            sell_volume_ratio=sell_ratio
        )
    
    def get_high_volume_nodes(
        self,
        result: VolumeProfileResult,
        threshold_pct: float = 70
    ) -> List[Dict[str, float]]:
        """
        Get high volume nodes (above threshold % of max)
        """
        if not result.volume_nodes:
            return []
        
        max_volume = max(node["volume"] for node in result.volume_nodes)
        threshold = max_volume * (threshold_pct / 100)
        
        high_vol_nodes = []
        for node in result.volume_nodes:
            if node["volume"] >= threshold:
                high_vol_nodes.append({
                    "price": node["price"],
                    "volume": node["volume"],
                    "volume_pct": (node["volume"] / max_volume) * 100
                })
        
        return high_vol_nodes
    
    def get_imbalance_zones(
        self,
        result: VolumeProfileResult,
        imbalance_threshold: float = 60  # 60% imbalance
    ) -> List[Dict[str, float]]:
        """
        Find zones with significant buy/sell imbalance
        """
        zones = []
        
        for node in result.volume_nodes:
            total = node["buy_volume"] + node["sell_volume"]
            if total == 0:
                continue
            
            buy_pct = (node["buy_volume"] / total) * 100
            sell_pct = (node["sell_volume"] / total) * 100
            
            if buy_pct >= imbalance_threshold:
                zones.append({
                    "price": node["price"],
                    "type": "buy_imbalance",
                    "strength": buy_pct,
                    "volume": node["volume"]
                })
            elif sell_pct >= imbalance_threshold:
                zones.append({
                    "price": node["price"],
                    "type": "sell_imbalance",
                    "strength": sell_pct,
                    "volume": node["volume"]
                })
        
        return zones
    
    def is_price_in_value_area(
        self,
        price: float,
        result: VolumeProfileResult
    ) -> bool:
        """
        Check if price is in value area
        """
        return result.val <= price <= result.vah
    
    def get_value_area_position(
        self,
        price: float,
        result: VolumeProfileResult
    ) -> str:
        """
        Get position relative to value area
        """
        if price < result.val:
            return "BELOW_VA"
        elif price > result.vah:
            return "ABOVE_VA"
        else:
            return "IN_VA"
    
    def calculate_volume_delta(
        self,
        ohlcv: List[List[float]],
        period: int = 10
    ) -> float:
        """
        Calculate cumulative volume delta
        Positive = buying pressure, Negative = selling pressure
        """
        if len(ohlcv) < period:
            period = len(ohlcv)
        
        recent = ohlcv[-period:]
        delta = 0.0
        
        for candle in recent:
            close = candle[4]
            open_price = candle[1]
            volume = candle[5]
            
            if close > open_price:
                delta += volume  # Buying pressure
            elif close < open_price:
                delta -= volume  # Selling pressure
            # else: do nothing for doji
        
        return delta
