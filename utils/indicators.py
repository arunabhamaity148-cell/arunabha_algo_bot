"""
ARUNABHA ALGO BOT - Technical Indicators
Pure Python implementation (no TA-Lib needed)
"""

import numpy as np
from typing import List, Dict, Optional, Tuple


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


def calculate_sma(values: List[float], period: int) -> float:
    """
    Calculate SMA (Simple Moving Average)
    """
    if len(values) < period:
        return sum(values) / len(values) if values else 0
    
    return sum(values[-period:]) / period


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
        return {"macd": 0, "signal": 0, "histogram": 0}
    
    # Calculate EMAs
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)
    
    macd_line = ema_fast - ema_slow
    
    # For signal line, we need MACD history
    # Simplified version
    signal_line = macd_line * 0.5  # Placeholder
    
    histogram = macd_line - signal_line
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }


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
        return {"upper": current, "middle": current, "lower": current}
    
    sma = calculate_sma(closes, period)
    
    # Calculate standard deviation
    recent = closes[-period:]
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = variance ** 0.5
    
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    
    return {
        "upper": upper,
        "middle": sma,
        "lower": lower
    }


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
