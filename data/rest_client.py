"""
ARUNABHA ALGO BOT - REST Client
Handles all REST API calls to exchanges
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import ccxt.async_support as ccxt
import config

logger = logging.getLogger(__name__)


class RESTClient:
    """
    Async REST client for exchange data
    """
    
    def __init__(self):
        self.exchange: Optional[ccxt.Exchange] = None
        self._rate_limiter = asyncio.Semaphore(10)  # Max 10 concurrent requests
        
    async def connect(self):
        """Connect to exchange"""
        try:
            self.exchange = ccxt.binanceusdm({
                'apiKey': config.BINANCE_API_KEY,
                'secret': config.BINANCE_SECRET,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True
                }
            })
            
            # Load markets
            await self.exchange.load_markets()
            logger.info("✅ REST client connected to Binance")
            
        except Exception as e:
            logger.error(f"REST client connection failed: {e}")
            raise
    
    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()
            logger.info("REST client closed")
    
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[List[float]]:
        """
        Fetch OHLCV data
        Returns: List of [timestamp, open, high, low, close, volume]
        """
        if not self.exchange:
            raise ConnectionError("Exchange not connected")
        
        async with self._rate_limiter:
            try:
                params = {}
                if since:
                    params['since'] = since
                
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=limit, params=params
                )
                
                return ohlcv
                
            except ccxt.RateLimitExceeded as e:
                logger.warning(f"Rate limit exceeded for {symbol}: {e}")
                await asyncio.sleep(10)
                return []
                
            except ccxt.NetworkError as e:
                logger.warning(f"Network error for {symbol}: {e}")
                return []
                
            except Exception as e:
                logger.error(f"OHLCV fetch error {symbol}: {e}")
                return []
    
    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 20
    ) -> Dict[str, List]:
        """
        Fetch orderbook
        Returns: {'bids': [[price, amount], ...], 'asks': [[price, amount], ...]}
        """
        if not self.exchange:
            return {"bids": [], "asks": []}
        
        async with self._rate_limiter:
            try:
                ob = await self.exchange.fetch_order_book(symbol, limit)
                return {
                    "bids": ob.get("bids", [])[:limit],
                    "asks": ob.get("asks", [])[:limit]
                }
                
            except Exception as e:
                logger.warning(f"Orderbook fetch error {symbol}: {e}")
                return {"bids": [], "asks": []}
    
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker"""
        if not self.exchange:
            return {}
        
        async with self._rate_limiter:
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                return {
                    "symbol": ticker.get("symbol"),
                    "last": ticker.get("last"),
                    "bid": ticker.get("bid"),
                    "ask": ticker.get("ask"),
                    "volume": ticker.get("baseVolume"),
                    "quote_volume": ticker.get("quoteVolume"),
                    "timestamp": ticker.get("timestamp")
                }
                
            except Exception as e:
                logger.warning(f"Ticker fetch error {symbol}: {e}")
                return {}
    
    async def fetch_funding_rate(self, symbol: str) -> float:
        """Fetch current funding rate"""
        if not self.exchange:
            return 0.0
        
        async with self._rate_limiter:
            try:
                funding = await self.exchange.fetch_funding_rate(symbol)
                return funding.get("fundingRate", 0.0)
                
            except Exception as e:
                logger.debug(f"Funding rate fetch error {symbol}: {e}")
                return 0.0
    
    async def fetch_open_interest(self, symbol: str) -> float:
        """Fetch open interest"""
        if not self.exchange:
            return 0.0
        
        async with self._rate_limiter:
            try:
                oi = await self.exchange.fetch_open_interest(symbol)
                return oi.get("openInterestAmount", 0.0)
                
            except Exception as e:
                logger.debug(f"Open interest fetch error {symbol}: {e}")
                return 0.0
    
    async def fetch_fear_greed_index(self) -> int:
        """Fetch Fear & Greed Index"""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(config.FEAR_GREED_API_URL) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return int(data["data"][0]["value"])
                        
        except Exception as e:
            logger.warning(f"Fear & Greed fetch error: {e}")
        
        return 50  # Default neutral
    
    async def fetch_multiple_ohlcv(
        self,
        symbols: List[str],
        timeframe: str = "15m",
        limit: int = 100
    ) -> Dict[str, List[List[float]]]:
        """
        Fetch OHLCV for multiple symbols concurrently
        """
        tasks = [self.fetch_ohlcv(sym, timeframe, limit) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch {symbol}: {result}")
                output[symbol] = []
            else:
                output[symbol] = result
        
        return output
    
    async def fetch_historical_data(
        self,
        symbol: str,
        timeframe: str,
        days: int = 30
    ) -> List[List[float]]:
        """
        Fetch historical data for backtesting
        """
        if not self.exchange:
            return []
        
        # Calculate since time
        since = self.exchange.parse8601(
            (datetime.now() - timedelta(days=days)).isoformat()
        )
        
        all_candles = []
        current_since = since
        
        while True:
            candles = await self.fetch_ohlcv(
                symbol, timeframe, limit=1000, since=current_since
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            
            if len(candles) < 1000:
                break
            
            # Set next since to last candle timestamp + 1ms
            current_since = candles[-1][0] + 1
        
        logger.info(f"Fetched {len(all_candles)} candles for {symbol} {timeframe}")
        return all_candles
