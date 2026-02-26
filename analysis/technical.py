"""
ARUNABHA ALGO BOT - Technical Analyzer v4.1
All technical indicators in one place

FIXES:
- BUG-10: MACD signal line এখন actual EMA of MACD — আগে সবসময় 0 ছিল
- BUG-11: calculate_ema_series() added — full EMA list return করে
- BUG-12: ADX calculation improved with proper Wilder's smoothing
"""

import logging
from typing import List, Dict, Optional, Tuple
from collections import deque

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """
    Technical analysis indicators
    """

    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> float:
        """Calculate RSI"""
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
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_ema(values: List[float], period: int) -> float:
        """Calculate single EMA value"""
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)

        k = 2.0 / (period + 1)
        ema = sum(values[:period]) / period
        for value in values[period:]:
            ema = value * k + ema * (1 - k)
        return ema

    @staticmethod
    def calculate_ema_series(values: List[float], period: int) -> List[float]:
        """
        ✅ FIX BUG-11: Full EMA series return করে
        MACD calculation এর জন্য দরকার
        """
        if len(values) < period:
            return [sum(values) / len(values)] * len(values) if values else []

        k = 2.0 / (period + 1)
        result = []

        # First value = SMA of first `period` values
        seed = sum(values[:period]) / period
        result.extend([None] * (period - 1))
        result.append(seed)

        ema = seed
        for value in values[period:]:
            ema = value * k + ema * (1 - k)
            result.append(ema)

        return result

    @staticmethod
    def calculate_sma(values: List[float], period: int) -> float:
        """Calculate SMA"""
        if not values:
            return 0.0
        if len(values) < period:
            return sum(values) / len(values)
        return sum(values[-period:]) / period

    @staticmethod
    def calculate_macd(
        closes: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, float]:
        """
        ✅ FIX BUG-10: MACD signal line এখন সঠিকভাবে calculate হচ্ছে
        আগে signal_line = macd_line ছিল → histogram সবসময় 0 ছিল
        এখন signal_line = EMA(macd_line_series, 9)
        """
        if len(closes) < slow + signal:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

        # Full EMA series calculate করো
        ema_fast_series = TechnicalAnalyzer.calculate_ema_series(closes, fast)
        ema_slow_series = TechnicalAnalyzer.calculate_ema_series(closes, slow)

        # MACD line = fast EMA - slow EMA (valid points only)
        macd_line_series = []
        for i in range(len(closes)):
            fast_val = ema_fast_series[i] if i < len(ema_fast_series) else None
            slow_val = ema_slow_series[i] if i < len(ema_slow_series) else None
            if fast_val is not None and slow_val is not None:
                macd_line_series.append(fast_val - slow_val)

        if len(macd_line_series) < signal:
            current_macd = macd_line_series[-1] if macd_line_series else 0.0
            return {"macd": current_macd, "signal": current_macd, "histogram": 0.0}

        # Signal line = EMA of MACD line series
        signal_line_series = TechnicalAnalyzer.calculate_ema_series(macd_line_series, signal)

        # Current values
        current_macd = macd_line_series[-1]
        current_signal = signal_line_series[-1] if signal_line_series[-1] is not None else current_macd
        histogram = current_macd - current_signal

        return {
            "macd": round(current_macd, 8),
            "signal": round(current_signal, 8),
            "histogram": round(histogram, 8)
        }

    @staticmethod
    def calculate_bollinger_bands(
        closes: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, float]:
        """Calculate Bollinger Bands"""
        if len(closes) < period:
            current = closes[-1] if closes else 0
            return {"upper": current, "middle": current, "lower": current, "width": 0, "percent_b": 0.5}

        sma = TechnicalAnalyzer.calculate_sma(closes, period)
        recent = closes[-period:]
        variance = sum((x - sma) ** 2 for x in recent) / period
        std = variance ** 0.5

        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        width = (upper - lower) / sma if sma > 0 else 0
        current = closes[-1]
        percent_b = (current - lower) / (upper - lower) if upper != lower else 0.5

        return {
            "upper": upper,
            "middle": sma,
            "lower": lower,
            "width": width,
            "percent_b": percent_b
        }

    @staticmethod
    def calculate_atr(ohlcv: List[List[float]], period: int = 14) -> float:
        """Calculate ATR with Wilder's smoothing"""
        if len(ohlcv) < period + 1:
            return 0.0

        tr_values = []
        for i in range(1, len(ohlcv)):
            high = float(ohlcv[i][2])
            low = float(ohlcv[i][3])
            prev_close = float(ohlcv[i-1][4])

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)

        if not tr_values:
            return 0.0

        atr = sum(tr_values[:period]) / period
        for i in range(period, len(tr_values)):
            atr = (atr * (period - 1) + tr_values[i]) / period

        return atr

    @staticmethod
    def calculate_adx(ohlcv: List[List[float]], period: int = 14) -> float:
        """
        ✅ FIX BUG-12: ADX এখন proper Wilder's smoothing ব্যবহার করছে
        আগে শুধু simple average ছিল
        """
        if len(ohlcv) < period * 2:
            return 20.0

        highs = [float(c[2]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        closes = [float(c[4]) for c in ohlcv]

        tr_list = []
        plus_dm_list = []
        minus_dm_list = []

        for i in range(1, len(ohlcv)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)

            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]

            plus_dm_list.append(up_move if up_move > down_move and up_move > 0 else 0)
            minus_dm_list.append(down_move if down_move > up_move and down_move > 0 else 0)

        # Wilder's smoothing
        def wilder_smooth(data, p):
            result = [sum(data[:p]) / p]
            for val in data[p:]:
                result.append((result[-1] * (p - 1) + val) / p)
            return result

        atr_smooth = wilder_smooth(tr_list, period)
        plus_dm_smooth = wilder_smooth(plus_dm_list, period)
        minus_dm_smooth = wilder_smooth(minus_dm_list, period)

        dx_values = []
        for i in range(len(atr_smooth)):
            atr_val = atr_smooth[i]
            if atr_val == 0:
                continue
            plus_di = (plus_dm_smooth[i] / atr_val) * 100
            minus_di = (minus_dm_smooth[i] / atr_val) * 100
            dmi_sum = plus_di + minus_di
            if dmi_sum > 0:
                dx = abs(plus_di - minus_di) / dmi_sum * 100
                dx_values.append(dx)

        if not dx_values:
            return 20.0

        # ADX = smoothed average of DX
        adx = sum(dx_values[-period:]) / min(period, len(dx_values))
        return round(adx, 2)

    @staticmethod
    def calculate_volume_profile(
        ohlcv: List[List[float]],
        num_bins: int = 20
    ) -> Dict[str, float]:
        """Calculate Volume Profile — POC, VAH, VAL"""
        if len(ohlcv) < 10:
            return {"poc": ohlcv[-1][4] if ohlcv else 0, "vah": 0, "val": 0, "value_area_width": 0}

        all_prices = []
        for candle in ohlcv[-50:]:
            all_prices.append(candle[2])
            all_prices.append(candle[3])

        min_price = min(all_prices)
        max_price = max(all_prices)
        bin_size = (max_price - min_price) / num_bins if max_price > min_price else 1

        bins = {i: 0 for i in range(num_bins)}

        for candle in ohlcv[-50:]:
            high = candle[2]
            low = candle[3]
            volume = candle[5]

            for i in range(num_bins):
                bin_low = min_price + (i * bin_size)
                bin_high = bin_low + bin_size
                if high >= bin_low and low <= bin_high:
                    overlap = min(high, bin_high) - max(low, bin_low)
                    if overlap > 0:
                        bins[i] += volume * (overlap / (high - low)) if high > low else volume

        poc_bin = max(bins, key=bins.get)
        poc = min_price + (poc_bin * bin_size) + (bin_size / 2)

        return {
            "poc": poc,
            "vah": max_price,
            "val": min_price,
            "value_area_width": max_price - min_price
        }

    @staticmethod
    def detect_divergence(
        prices: List[float],
        indicator: List[float],
        period: int = 5
    ) -> Tuple[bool, bool]:
        """Detect bullish/bearish divergence — returns (bullish, bearish)"""
        if len(prices) < period + 1 or len(indicator) < period + 1:
            return False, False

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

        bullish_div = (
            price_low_idx == len(price_lows) - 1 and
            ind_low_idx < len(ind_lows) - 1 and
            price_low < price_lows[0] and
            ind_low > ind_lows[0]
        )

        bearish_div = (
            price_high_idx == len(price_highs) - 1 and
            ind_high_idx < len(ind_highs) - 1 and
            price_high > price_highs[0] and
            ind_high < ind_highs[0]
        )

        return bullish_div, bearish_div

    @staticmethod
    def calculate_fibonacci_levels(high: float, low: float) -> Dict[str, float]:
        """Calculate Fibonacci retracement levels"""
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
        """Calculate classic pivot points"""
        pivot = (high + low + close) / 3
        return {
            "pivot": pivot,
            "r1": 2 * pivot - low,
            "r2": pivot + (high - low),
            "r3": high + 2 * (pivot - low),
            "s1": 2 * pivot - high,
            "s2": pivot - (high - low),
            "s3": low - 2 * (high - pivot)
        }

    @staticmethod
    def calculate_vwap(ohlcv: List[List[float]]) -> float:
        """Calculate VWAP"""
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
