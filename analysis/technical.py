"""
ARUNABHA ALGO BOT - Technical Analyzer
All technical indicators in one place
"""

import logging
import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import deque

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """
    Technical analysis indicators
    """
    
    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> float:
        """
        Calculate RSI (Relative Strength Index)
        """
        if len(closes) < period + 1:
            return 50.0
        
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period-1) + gains[i]) / period
            avg_loss = (avg_loss * (period-1) + losses[i]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_ema(values: List[float], period: int) -> float:
        """
        Calculate EMA (Exponential Moving Average)
        """
        if len(values) < period:
            return sum(values) / len(values) if values else 0
        
        k = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        
        for value in values[period:]:
            ema = value * k + ema * (1 - k)
        
        return ema
    
    @staticmethod
    def calculate_sma(values: List[float], period: int) -> float:
        """
        Calculate SMA (Simple Moving Average)
        """
        if len(values) < period:
            return sum(values) / len(values) if values else 0
        
        return sum(values[-period:]) / period
    
    @staticmethod
    def calculate_macd(
        closes: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, float]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        """
        if len(closes) < slow + signal:
            return {
                "macd": 0,
                "signal": 0,
                "histogram": 0
            }
        
        # Calculate EMAs
        ema_fast = TechnicalAnalyzer.calculate_ema(closes, fast)
        ema_slow = TechnicalAnalyzer.calculate_ema(closes, slow)
        
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line (EMA of MACD)
        # Simplified - in production you'd maintain history
        signal_line = macd_line  # Placeholder
        
        histogram = macd_line - signal_line
        
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram
        }
    
    @staticmethod
    def calculate_bollinger_bands(
        closes: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, float]:
        """
        Calculate Bollinger Bands
        """
        if len(closes) < period:
            current = closes[-1] if closes else 0
            return {
                "upper": current,
                "middle": current,
                "lower": current,
                "width": 0,
                "percent_b": 0.5
            }
        
        sma = TechnicalAnalyzer.calculate_sma(closes, period)
        
        # Calculate standard deviation
        recent = closes[-period:]
        variance = sum((x - sma) ** 2 for x in recent) / period
        std = variance ** 0.5
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        width = (upper - lower) / sma if sma > 0 else 0
        
        # %B
        current = closes[-1]
        if upper == lower:
            percent_b = 0.5
        else:
            percent_b = (current - lower) / (upper - lower)
        
        return {
            "upper": upper,
            "middle": sma,
            "lower": lower,
            "width": width,
            "percent_b": percent_b
        }
    
    @staticmethod
    def calculate_atr(ohlcv: List[List[float]], period: int = 14) -> float:
        """
        Calculate ATR (Average True Range)
        """
        if len(ohlcv) < period + 1:
            return 0.0
        
        tr_values = []
        for i in range(1, len(ohlcv)):
            high = float(ohlcv[i][2])
            low = float(ohlcv[i][3])
            prev_close = float(ohlcv[i-1][4])
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        if not tr_values:
            return 0.0
        
        # Wilder's smoothing
        atr = sum(tr_values[:period]) / period
        for i in range(period, len(tr_values)):
            atr = (atr * (period - 1) + tr_values[i]) / period
        
        return atr
    
    @staticmethod
    def calculate_adx(ohlcv: List[List[float]], period: int = 14) -> float:
        """
        Calculate ADX (Average Directional Index)
        """
        if len(ohlcv) < period + 1:
            return 20.0
        
        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        closes = [c[4] for c in ohlcv]
        
        tr_list = []
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(ohlcv)):
            # True Range
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
            
            # Directional Movement
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            
            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)
            
            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)
        
        # Smooth
        atr = sum(tr_list[-period:]) / period
        plus_di = (sum(plus_dm[-period:]) / atr) * 100 if atr > 0 else 0
        minus_di = (sum(minus_dm[-period:]) / atr) * 100 if atr > 0 else 0
        
        # DX
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        
        return dx
    
    @staticmethod
    def calculate_volume_profile(
        ohlcv: List[List[float]],
        num_bins: int = 20
    ) -> Dict[str, float]:
        """
        Calculate Volume Profile
        Returns POC (Point of Control), VAH, VAL
        """
        if len(ohlcv) < 10:
            return {
                "poc": ohlcv[-1][4] if ohlcv else 0,
                "vah": 0,
                "val": 0,
                "value_area_width": 0
            }
        
        # Get price range
        all_prices = []
        for candle in ohlcv[-50:]:
            all_prices.append(candle[2])  # high
            all_prices.append(candle[3])  # low
        
        min_price = min(all_prices)
        max_price = max(all_prices)
        bin_size = (max_price - min_price) / num_bins if max_price > min_price else 1
        
        # Create volume bins
        bins = {i: 0 for i in range(num_bins)}
        
        for candle in ohlcv[-50:]:
            high = candle[2]
            low = candle[3]
            volume = candle[5]
            
            # Distribute volume across price range
            for i in range(num_bins):
                bin_low = min_price + (i * bin_size)
                bin_high = bin_low + bin_size
                
                # Check overlap
                if high >= bin_low and low <= bin_high:
                    overlap = min(high, bin_high) - max(low, bin_low)
                    if overlap > 0:
                        bins[i] += volume * (overlap / (high - low)) if high > low else volume
        
        # Find POC (bin with max volume)
        poc_bin = max(bins, key=bins.get)
        poc = min_price + (poc_bin * bin_size) + (bin_size / 2)
        
        # Calculate Value Area (70% of volume)
        total_volume = sum(bins.values())
        value_area_volume = total_volume * 0.7
        
        # Start from POC and expand
        sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "poc": poc,
            "vah": max_price,  # Simplified
            "val": min_price,   # Simplified
            "value_area_width": max_price - min_price
        }
    
    @staticmethod
    def detect_divergence(
        prices: List[float],
        indicator: List[float],
        period: int = 5
    ) -> Tuple[bool, bool]:
        """
        Detect bullish/bearish divergence
        
        Returns: (bullish_div, bearish_div)
        """
        if len(prices) < period + 1 or len(indicator) < period + 1:
            return False, False
        
        # Get recent extremes
        price_lows = prices[-period:]
        price_highs = prices[-period:]
        ind_lows = indicator[-period:]
        ind_highs = indicator[-period:]
        
        price_low = min(price_lows)
        price_low_idx = price_lows.index(price_low)
        
        price_high = max(price_highs)
        price_high_idx = price_highs.index(price_high)
        
        ind_low = min(ind_lows)
        ind_low_idx = ind_lows.index(ind_low)
        
        ind_high = max(ind_highs)
        ind_high_idx = ind_highs.index(ind_high)
        
        # Bullish divergence: price makes lower low, indicator makes higher low
        bullish_div = (
            price_low_idx == len(price_lows) - 1 and
            ind_low_idx < len(ind_lows) - 1 and
            price_low < price_lows[0] and
            ind_low > ind_lows[0]
        )
        
        # Bearish divergence: price makes higher high, indicator makes lower high
        bearish_div = (
            price_high_idx == len(price_highs) - 1 and
            ind_high_idx < len(ind_highs) - 1 and
            price_high > price_highs[0] and
            ind_high < ind_highs[0]
        )
        
        return bullish_div, bearish_div
    
    @staticmethod
    def calculate_fibonacci_levels(high: float, low: float) -> Dict[str, float]:
        """
        Calculate Fibonacci retracement levels
        """
        diff = high - low
        
        return {
            "level_0": high,
            "level_236": high - diff * 0.236,
            "level_382": high - diff * 0.382,
            "level_5": high - diff * 0.5,
            "level_618": high - diff * 0.618,
            "level_786": high - diff * 0.786,
            "level_1": low
        }
    
    @staticmethod
    def calculate_pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
        """
        Calculate classic pivot points
        """
        pivot = (high + low + close) / 3
        
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)
        
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)
        
        return {
            "pivot": pivot,
            "r1": r1, "r2": r2, "r3": r3,
            "s1": s1, "s2": s2, "s3": s3
        }
    
    @staticmethod
    def calculate_vwap(ohlcv: List[List[float]]) -> float:
        """
        Calculate VWAP (Volume Weighted Average Price)
        """
        if not ohlcv:
            return 0
        
        total_volume = 0
        total_pv = 0
        
        for candle in ohlcv:
            typical_price = (candle[2] + candle[3] + candle[4]) / 3
            volume = candle[5]
            
            total_pv += typical_price * volume
            total_volume += volume
        
        return total_pv / total_volume if total_volume > 0 else ohlcv[-1][4]
