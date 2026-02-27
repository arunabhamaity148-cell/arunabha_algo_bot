"""
ARUNABHA ALGO BOT - Correlation Analyzer
Checks if a symbol is breaking/maintaining BTC correlation.
Used by Tier3 filters for correlation-break bonus.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CorrelationResult:
    symbol: str
    btc_correlation: float        # -1.0 to 1.0
    is_decorrelated: bool         # True if r < 0.3
    direction: str                # "BREAKING_UP" / "BREAKING_DOWN" / "CORRELATED"
    lookback: int
    reason: str


class CorrelationAnalyzer:
    """
    Calculates Pearson correlation between a symbol's returns and BTC returns.
    Low correlation = symbol moving independently = higher quality signal.
    """

    def analyze(
        self,
        symbol: str,
        prices: List[float],
        btc_prices: Optional[List[float]] = None,
        lookback: int = 20
    ) -> CorrelationResult:
        """
        Analyze correlation between symbol and BTC.
        If btc_prices not provided, returns neutral result.
        """
        if not prices or len(prices) < lookback:
            return CorrelationResult(
                symbol=symbol,
                btc_correlation=1.0,
                is_decorrelated=False,
                direction="CORRELATED",
                lookback=lookback,
                reason="Insufficient price data"
            )

        # If no BTC prices provided, use internal estimation
        if btc_prices is None or len(btc_prices) < lookback:
            return CorrelationResult(
                symbol=symbol,
                btc_correlation=0.5,
                is_decorrelated=False,
                direction="CORRELATED",
                lookback=lookback,
                reason="BTC prices not available — neutral"
            )

        # Calculate returns
        sym_returns = self._returns(prices[-lookback:])
        btc_returns = self._returns(btc_prices[-lookback:])

        if not sym_returns or not btc_returns:
            return CorrelationResult(
                symbol=symbol,
                btc_correlation=1.0,
                is_decorrelated=False,
                direction="CORRELATED",
                lookback=lookback,
                reason="Cannot compute returns"
            )

        correlation = self._pearson(sym_returns, btc_returns)

        is_decorrelated = abs(correlation) < 0.3

        if is_decorrelated:
            # Determine direction of independent move
            if sym_returns[-1] > 0:
                direction = "BREAKING_UP"
            else:
                direction = "BREAKING_DOWN"
        else:
            direction = "CORRELATED"

        reason = (
            f"r={correlation:.2f} over {lookback} candles — "
            f"{'decorrelated ✅' if is_decorrelated else 'correlated with BTC'}"
        )

        return CorrelationResult(
            symbol=symbol,
            btc_correlation=correlation,
            is_decorrelated=is_decorrelated,
            direction=direction,
            lookback=lookback,
            reason=reason
        )

    def _returns(self, prices: List[float]) -> List[float]:
        """Compute percentage returns"""
        if len(prices) < 2:
            return []
        return [
            (prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices))
            if prices[i - 1] != 0
        ]

    def _pearson(self, x: List[float], y: List[float]) -> float:
        """Pearson correlation coefficient"""
        n = min(len(x), len(y))
        if n < 3:
            return 0.0

        x = x[-n:]
        y = y[-n:]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = (sum((v - mean_x) ** 2 for v in x) / n) ** 0.5
        std_y = (sum((v - mean_y) ** 2 for v in y) / n) ** 0.5

        if std_x == 0 or std_y == 0:
            return 0.0

        return cov / (n * std_x * std_y)
