"""
ARUNABHA ALGO BOT - Technical Indicators v4.2
=============================================

Point 15 — Duplicate indicator elimination:
    আগে: utils/indicators.py এ signal_line = macd_line * 0.5  ← placeholder bug
         analysis/technical.py আলাদাভাবে same calculation করছিল
    এখন: এই file-ই single source of truth
         MACD signal line properly calculated as EMA-9 of MACD line series
"""

import numpy as np
from typing import List, Dict, Optional


def calculate_ema(values: List[float], period: int) -> float:
    """Single EMA value"""
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def calculate_ema_series(values: List[float], period: int) -> List[Optional[float]]:
    """
    Full EMA series — None for first (period-1) values.
    Required for proper MACD signal line calculation.
    """
    if not values or len(values) < period:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    result: List[Optional[float]] = [None] * (period - 1)
    ema = sum(values[:period]) / period
    result.append(ema)
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
        result.append(ema)
    return result


def calculate_sma(values: List[float], period: int) -> float:
    if len(values) < period:
        return sum(values) / len(values) if values else 0.0
    return sum(values[-period:]) / period


def calculate_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calculate_macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9
) -> Dict[str, float]:
    """
    ✅ FIXED Point 15: Proper MACD with EMA-9 of MACD line

    আগের bug:
        signal_line = macd_line * 0.5  ← histogram always agreed with MACD

    এখন:
        1. EMA-12 series calculate করো
        2. EMA-26 series calculate করো
        3. MACD line = EMA-12 - EMA-26 per candle
        4. Signal line = EMA-9 of MACD line
        5. Histogram = MACD - Signal
    """
    if len(closes) < slow + signal_period:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    fast_series = calculate_ema_series(closes, fast)
    slow_series = calculate_ema_series(closes, slow)

    macd_line: List[float] = []
    for f, s in zip(fast_series, slow_series):
        if f is not None and s is not None:
            macd_line.append(f - s)

    if len(macd_line) < signal_period:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    signal_series = calculate_ema_series(macd_line, signal_period)
    current_macd = macd_line[-1]
    current_signal = next(
        (v for v in reversed(signal_series) if v is not None),
        current_macd
    )
    return {
        "macd": current_macd,
        "signal": current_signal,
        "histogram": current_macd - current_signal,
    }


def calculate_atr(ohlcv: List[List[float]], period: int = 14) -> float:
    """Wilder's ATR"""
    if len(ohlcv) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(ohlcv)):
        h, l, pc = float(ohlcv[i][2]), float(ohlcv[i][3]), float(ohlcv[i-1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def calculate_adx(ohlcv: List[List[float]], period: int = 14) -> float:
    """Wilder's ADX"""
    if len(ohlcv) < period + 1:
        return 20.0
    highs = [float(c[2]) for c in ohlcv]
    lows  = [float(c[3]) for c in ohlcv]
    closes = [float(c[4]) for c in ohlcv]
    trs, pdms, mdms = [], [], []
    for i in range(1, len(ohlcv)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up = highs[i] - highs[i-1]
        dn = lows[i-1] - lows[i]
        trs.append(tr)
        pdms.append(up if up > dn and up > 0 else 0.0)
        mdms.append(dn if dn > up and dn > 0 else 0.0)
    atr = sum(trs[:period]) / period
    pdm = sum(pdms[:period]) / period
    mdm = sum(mdms[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period-1) + trs[i]) / period
        pdm = (pdm * (period-1) + pdms[i]) / period
        mdm = (mdm * (period-1) + mdms[i]) / period
    if atr == 0:
        return 20.0
    pdi = (pdm / atr) * 100
    mdi = (mdm / atr) * 100
    dx = abs(pdi - mdi) / (pdi + mdi) * 100 if (pdi + mdi) > 0 else 0.0
    return dx


def calculate_bollinger_bands(
    closes: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, float]:
    if len(closes) < period:
        c = closes[-1] if closes else 0.0
        return {"upper": c, "middle": c, "lower": c}
    sma = calculate_sma(closes, period)
    variance = sum((x - sma) ** 2 for x in closes[-period:]) / period
    std = variance ** 0.5
    return {"upper": sma + std * std_dev, "middle": sma, "lower": sma - std * std_dev}


def calculate_vwap(ohlcv: List[List[float]]) -> float:
    if not ohlcv:
        return 0.0
    total_pv = sum((c[2] + c[3] + c[4]) / 3 * c[5] for c in ohlcv)
    total_vol = sum(c[5] for c in ohlcv)
    return total_pv / total_vol if total_vol > 0 else float(ohlcv[-1][4])
