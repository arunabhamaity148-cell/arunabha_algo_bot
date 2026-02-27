"""
ARUNABHA ALGO BOT - REST Client
Handles all REST API calls to exchanges with backup support
"""

import asyncio
import logging
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import ccxt.async_support as ccxt
import config

logger = logging.getLogger(__name__)


class RESTClient:
    """
    Async REST client for exchange data with REST API backup
    """
    
    def __init__(self):
        self.exchange: Optional[ccxt.Exchange] = None
        self._rate_limiter = asyncio.Semaphore(10)  # Max 10 concurrent requests
        self._connection_attempts = 0
        
        # Binance REST API base URL
        self.binance_rest_url = "https://api.binance.com/api/v3"
        
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
            self._connection_attempts = 0
            
        except Exception as e:
            self._connection_attempts += 1
            logger.error(f"❌ REST client connection failed (attempt {self._connection_attempts}): {e}")
            raise
    
    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()
            logger.info("🔌 REST client closed")
    
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
        since: Optional[int] = None
    ) -> List[List[float]]:
        """
        Fetch OHLCV data - tries WebSocket cache first, then REST API
        Returns: List of [timestamp, open, high, low, close, volume]
        """
        # Try REST API backup first if no exchange connection
        if not self.exchange:
            logger.warning(f"⚠️ Exchange not connected, using REST API backup for {symbol}")
            return await self.fetch_ohlcv_rest(symbol, timeframe, limit)
        
        async with self._rate_limiter:
            try:
                params = {}
                if since:
                    params['since'] = since
                
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=limit, params=params
                )
                
                if ohlcv:
                    logger.debug(f"📊 CCXT: Fetched {len(ohlcv)} candles for {symbol} {timeframe}")
                    return ohlcv
                else:
                    logger.warning(f"⚠️ No data from CCXT for {symbol} {timeframe}, trying REST API")
                    return await self.fetch_ohlcv_rest(symbol, timeframe, limit)
                
            except ccxt.RateLimitExceeded as e:
                logger.warning(f"⚠️ Rate limit exceeded for {symbol}: {e}")
                await asyncio.sleep(10)
                return await self.fetch_ohlcv_rest(symbol, timeframe, limit)
                
            except ccxt.NetworkError as e:
                logger.warning(f"⚠️ Network error for {symbol}: {e}")
                return await self.fetch_ohlcv_rest(symbol, timeframe, limit)
                
            except Exception as e:
                logger.error(f"❌ CCXT fetch error {symbol}: {e}")
                return await self.fetch_ohlcv_rest(symbol, timeframe, limit)
    
    async def fetch_ohlcv_rest(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> List[List[float]]:
        """
        REST API দিয়ে সরাসরি Binance থেকে ডেটা আনা (WebSocket/CCXT ব্যাকআপ)
        """
        try:
            # Binance API URL
            url = f"{self.binance_rest_url}/klines"
            
            # সিম্বল ফরম্যাট ঠিক করা (RENDER/USDT → RENDERUSDT)
            symbol_raw = symbol.replace("/", "").upper()
            
            # Timeframe mapping
            tf_map = {
                "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1h": "1h", "4h": "4h", "1d": "1d"
            }
            interval = tf_map.get(timeframe, "15m")
            
            params = {
                "symbol": symbol_raw,
                "interval": interval,
                "limit": limit
            }
            
            logger.info(f"📡 REST API fetch: {symbol} {timeframe}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Binance ফরম্যাট থেকে আমাদের ফরম্যাটে convert
                        candles = []
                        for item in data:
                            candle = [
                                item[0],  # timestamp
                                float(item[1]),  # open
                                float(item[2]),  # high
                                float(item[3]),  # low
                                float(item[4]),  # close
                                float(item[5])   # volume
                            ]
                            candles.append(candle)
                        
                        logger.info(f"✅ REST API success: {len(candles)} candles for {symbol} {timeframe}")
                        return candles
                    else:
                        error_text = await resp.text()
                        logger.error(f"❌ REST API error {resp.status}: {error_text}")
                        return []
                        
        except aiohttp.ClientError as e:
            logger.error(f"❌ REST API connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ REST API exception: {e}")
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
            logger.warning(f"⚠️ Exchange not connected, using mock orderbook for {symbol}")
            return {"bids": [], "asks": []}
        
        async with self._rate_limiter:
            try:
                ob = await self.exchange.fetch_order_book(symbol, limit)
                return {
                    "bids": ob.get("bids", [])[:limit],
                    "asks": ob.get("asks", [])[:limit]
                }
                
            except Exception as e:
                logger.warning(f"⚠️ Orderbook fetch error {symbol}: {e}")
                return {"bids": [], "asks": []}
    
    async def fetch_orderbook_rest(self, symbol: str, limit: int = 20) -> Dict[str, List]:
        """
        REST API দিয়ে orderbook আনা (ব্যাকআপ)
        """
        try:
            url = f"{self.binance_rest_url}/depth"
            symbol_raw = symbol.replace("/", "").upper()
            
            params = {
                "symbol": symbol_raw,
                "limit": limit
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "bids": data.get("bids", [])[:limit],
                            "asks": data.get("asks", [])[:limit]
                        }
                    else:
                        return {"bids": [], "asks": []}
                        
        except Exception as e:
            logger.error(f"❌ Orderbook REST error: {e}")
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
                logger.warning(f"⚠️ Ticker fetch error {symbol}: {e}")
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
                logger.debug(f"⚠️ Funding rate fetch error {symbol}: {e}")
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
                logger.debug(f"⚠️ Open interest fetch error {symbol}: {e}")
                return 0.0
    
    async def fetch_fear_greed_index(self) -> int:
        """Fetch Fear & Greed Index"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(config.FEAR_GREED_API_URL) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return int(data["data"][0]["value"])
                        
        except Exception as e:
            logger.warning(f"⚠️ Fear & Greed fetch error: {e}")
        
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
                logger.warning(f"⚠️ Failed to fetch {symbol}: {result}")
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
        all_candles = []
        current_since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        
        while True:
            candles = await self.fetch_ohlcv_rest(
                symbol, timeframe, limit=1000
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            
            if len(candles) < 1000:
                break
            
            # Set next since to last candle timestamp + 1ms
            current_since = candles[-1][0] + 1
        
        logger.info(f"📊 Fetched {len(all_candles)} candles for {symbol} {timeframe}")
        return all_candles
    async def get_api_permissions(self) -> dict:
        """
        ISSUE 8 FIX: Fetch API key permissions from Binance.
        Uses /sapi/v1/account/apiRestrictions (spot/margin/futures info).
        Returns dict of permission flags.
        """
        try:
            import hashlib, hmac, time as t
            import aiohttp as ah

            api_key = config.BINANCE_API_KEY
            secret = config.BINANCE_SECRET

            if not api_key or not secret:
                return {"enableReading": True, "note": "no_key"}

            ts = int(t.time() * 1000)
            params = f"timestamp={ts}"
            sig = hmac.new(
                secret.encode(), params.encode(), hashlib.sha256
            ).hexdigest()
            url = f"https://api.binance.com/sapi/v1/account/apiRestrictions?{params}&signature={sig}"

            async with ah.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"X-MBX-APIKEY": api_key},
                    timeout=ah.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "enableReading":     data.get("enableReading", True),
                            "enableFutures":     data.get("enableFutures", False),
                            "enableSpotAndMarginTrading": data.get("enableSpotAndMarginTrading", False),
                            "enableWithdrawals": data.get("enableWithdrawals", False),
                            "enableInternalTransfer": data.get("enableInternalTransfer", False),
                            "ipRestrict":        data.get("ipRestrict", False),
                            "raw":               data,
                        }
                    else:
                        return {"error": f"HTTP {resp.status}", "enableReading": True}
        except Exception as e:
            logger.warning(f"API permissions fetch failed: {e}")
            return {"error": str(e), "enableReading": True}
