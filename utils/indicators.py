"""
ARUNABHA ALGO BOT - Technical Indicators
Pure Python implementation (no TA-Lib needed)

FIXES v4.2:
- CRITICAL FIX: calculate_macd() — signal_line এখন real EMA-9 of MACD history
  আগে ছিল: signal_line = macd_line * 0.5  ← সম্পূর্ণ ভুল placeholder
  এখন: পুরো MACD line series calculate করে তার EMA-9 নেওয়া হচ্ছে
- calculate_ema_series() added — full EMA list return করে (MACD-এর জন্য দরকার)
"""

import numpy as np
from typing import List, Dict, Optional, Tuple


def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """
    Calculate RSI (Relative Strength Index)
    Wilder's smoothing method use করা হচ্ছে
    """
    if len(closes) < period + 1:
        return 50.0

    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_ema(values: List[float], period: int) -> float:
    """
    Calculate single EMA value (last value of EMA series)
    """
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)

    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for value in values[period:]:
        ema = value * k + ema * (1 - k)
    return ema


def calculate_ema_series(values: List[float], period: int) -> List[Optional[float]]:
    """
    Calculate full EMA series — প্রতিটি point-এর EMA value return করে
    MACD signal line calculation-এর জন্য এটা দরকার

    Returns: List of floats (first `period-1` entries are None)
    """
    if not values:
        return []
    if len(values) < period:
        avg = sum(values) / len(values)
        return [avg] * len(values)

    k = 2.0 / (period + 1)
    result: List[Optional[float]] = [None] * (period - 1)

    seed = sum(values[:period]) / period
    result.append(seed)

    ema = seed
    for value in values[period:]:
        ema = value * k + ema * (1 - k)
        result.append(ema)

    return result


def calculate_sma(values: List[float], period: int) -> float:
    """
    Calculate SMA (Simple Moving Average)
    """
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    return sum(values[-period:]) / period


def calculate_macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Dict[str, float]:
    """
    ✅ FIXED: Calculate MACD (Moving Average Convergence Divergence)

    আগের bug:
        signal_line = macd_line * 0.5  ← এটা কোনো real signal line না
        এর ফলে histogram সবসময় MACD-এর same direction-এ থাকত
        অর্থাৎ MACD vote সবসময় একই দিকে — কোনো real confirmation নেই

    এখন:
        1. পুরো fast EMA series calculate করা হচ্ছে
        2. পুরো slow EMA series calculate করা হচ্ছে
        3. MACD line series = fast_series - slow_series
        4. Signal line = EMA-9 of MACD line series  ← real calculation
        5. Histogram = MACD line - Signal line
    """
    if len(closes) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    # Step 1: পুরো EMA series বের করো
    ema_fast_series = calculate_ema_series(closes, fast)
    ema_slow_series = calculate_ema_series(closes, slow)

    # Step 2: MACD line series — valid (non-None) points only
    macd_line_series: List[float] = []
    for i in range(len(closes)):
        f = ema_fast_series[i] if i < len(ema_fast_series) else None
        s = ema_slow_series[i] if i < len(ema_slow_series) else None
        if f is not None and s is not None:
            macd_line_series.append(f - s)

    if len(macd_line_series) < signal:
        current_macd = macd_line_series[-1] if macd_line_series else 0.0
        return {"macd": current_macd, "signal": current_macd, "histogram": 0.0}

    # Step 3: Signal line = EMA-9 of MACD line series (real calculation)
    signal_line_series = calculate_ema_series(macd_line_series, signal)

    # Step 4: Current values
    current_macd = macd_line_series[-1]
    # signal_line_series[-1] কখনো None হওয়া উচিত নয় কারণ আমরা length check করেছি
    current_signal = signal_line_series[-1] if signal_line_series[-1] is not None else current_macd
    histogram = current_macd - current_signal

    return {
        "macd": round(current_macd, 8),
        "signal": round(current_signal, 8),
        "histogram": round(histogram, 8)
    }


def calculate_atr(ohlcv: List[List[float]], period: int = 14) -> float:
    """
    Calculate ATR (Average True Range) — Wilder's smoothing
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
    Calculate ADX (Average Directional Index) — Wilder's smoothing
    """
    if len(ohlcv) < period * 2:
        return 20.0

    highs = [float(c[2]) for c in ohlcv]
    lows = [float(c[3]) for c in ohlcv]
    closes = [float(c[4]) for c in ohlcv]

    tr_list: List[float] = []
    plus_dm: List[float] = []
    minus_dm: List[float] = []

    for i in range(1, len(ohlcv)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)

        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]

        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0.0)

        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0.0)

    # Wilder's smoothed ATR, +DM, -DM
    def wilder_smooth(data: List[float], p: int) -> List[float]:
        if len(data) < p:
            return [sum(data) / len(data)] * len(data) if data else []
        smoothed = [sum(data[:p]) / p]
        for i in range(p, len(data)):
            smoothed.append((smoothed[-1] * (p - 1) + data[i]) / p)
        return smoothed

    atr_s = wilder_smooth(tr_list, period)
    plus_s = wilder_smooth(plus_dm, period)
    minus_s = wilder_smooth(minus_dm, period)

    # DX series
    dx_list: List[float] = []
    for i in range(len(atr_s)):
        atr_v = atr_s[i]
        if atr_v == 0:
            dx_list.append(0.0)
            continue
        pdi = (plus_s[i] / atr_v) * 100
        mdi = (minus_s[i] / atr_v) * 100
        denom = pdi + mdi
        dx_list.append(abs(pdi - mdi) / denom * 100 if denom > 0 else 0.0)

    if not dx_list:
        return 20.0

    # ADX = smoothed DX
    adx_s = wilder_smooth(dx_list, period)
    return round(adx_s[-1], 2) if adx_s else 20.0


def calculate_bollinger_bands(
    closes: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, float]:
    """
    Calculate Bollinger Bands
    """
    if len(closes) < period:
        current = closes[-1] if closes else 0.0
        return {"upper": current, "middle": current, "lower": current}

    sma = calculate_sma(closes, period)
    recent = closes[-period:]
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = variance ** 0.5

    return {
        "upper": round(sma + std * std_dev, 8),
        "middle": round(sma, 8),
        "lower": round(sma - std * std_dev, 8)
    }


def calculate_vwap(ohlcv: List[List[float]]) -> float:
    """
    Calculate VWAP (Volume Weighted Average Price)
    """
    if not ohlcv:
        return 0.0

    total_pv = 0.0
    total_volume = 0.0

    for candle in ohlcv:
        typical_price = (float(candle[2]) + float(candle[3]) + float(candle[4])) / 3
        volume = float(candle[5])
        total_pv += typical_price * volume
        total_volume += volume

    return total_pv / total_volume if total_volume > 0 else float(ohlcv[-1][4])
