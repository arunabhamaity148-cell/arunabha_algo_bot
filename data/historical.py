"""
ARUNABHA ALGO BOT - Historical Data
Fetches and manages historical data for backtesting
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import csv
import os

import pandas as pd
import config
from data.rest_client import RESTClient

logger = logging.getLogger(__name__)


class HistoricalData:
    """
    Historical data fetcher and manager
    """
    
    def __init__(self):
        self.rest_client = RESTClient()
        self.data_dir = "historical_data"
        
        # Create data directory if not exists
        os.makedirs(self.data_dir, exist_ok=True)
    
    async def connect(self):
        """Connect to exchange"""
        await self.rest_client.connect()
    
    async def close(self):
        """Close connection"""
        await self.rest_client.close()
    
    async def fetch_for_backtest(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Fetch historical data for backtesting
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Timeframe (e.g., "15m")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), default = today
        
        Returns:
            DataFrame with OHLCV data
        """
        # Parse dates
        start = datetime.strptime(start_date, "%Y-%m-%d")
        
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end = datetime.now()
        
        days = (end - start).days
        logger.info(f"Fetching {days} days of {symbol} {timeframe} data...")
        
        # Fetch data
        candles = await self.rest_client.fetch_historical_data(
            symbol, timeframe, days=days
        )
        
        if not candles:
            logger.error(f"No data fetched for {symbol}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume'
        ])
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Filter by date range
        df = df[start:end]
        
        logger.info(f"Fetched {len(df)} candles from {df.index[0]} to {df.index[-1]}")
        
        return df
    
    async def fetch_multiple_symbols(
        self,
        symbols: List[str],
        timeframe: str,
        start_date: str,
        end_date: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical data for multiple symbols
        """
        results = {}
        
        for symbol in symbols:
            try:
                df = await self.fetch_for_backtest(symbol, timeframe, start_date, end_date)
                results[symbol] = df
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                results[symbol] = pd.DataFrame()
        
        return results
    
    def save_to_csv(self, df: pd.DataFrame, filename: str):
        """Save DataFrame to CSV"""
        filepath = os.path.join(self.data_dir, filename)
        df.to_csv(filepath)
        logger.info(f"Saved to {filepath}")
    
    def load_from_csv(self, filename: str) -> pd.DataFrame:
        """Load DataFrame from CSV"""
        filepath = os.path.join(self.data_dir, filename)
        
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return pd.DataFrame()
        
        df = pd.read_csv(filepath, index_col=0, parse_dates=True)
        logger.info(f"Loaded {len(df)} rows from {filepath}")
        
        return df
    
    def prepare_for_backtest(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15
    ) -> Dict[str, pd.DataFrame]:
        """
        Split data for backtesting
        
        Returns:
            {
                "train": training data,
                "validation": validation data,
                "test": test data
            }
        """
        total = len(df)
        train_idx = int(total * train_ratio)
        val_idx = int(total * (train_ratio + val_ratio))
        
        return {
            "train": df.iloc[:train_idx],
            "validation": df.iloc[train_idx:val_idx],
            "test": df.iloc[val_idx:]
        }
    
    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to DataFrame"""
        # Make a copy
        result = df.copy()
        
        # Simple Moving Averages
        result['sma_20'] = result['close'].rolling(window=20).mean()
        result['sma_50'] = result['close'].rolling(window=50).mean()
        result['sma_200'] = result['close'].rolling(window=200).mean()
        
        # Exponential Moving Averages
        result['ema_9'] = result['close'].ewm(span=9, adjust=False).mean()
        result['ema_21'] = result['close'].ewm(span=21, adjust=False).mean()
        
        # RSI
        delta = result['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        result['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = result['close'].ewm(span=12, adjust=False).mean()
        exp2 = result['close'].ewm(span=26, adjust=False).mean()
        result['macd'] = exp1 - exp2
        result['macd_signal'] = result['macd'].ewm(span=9, adjust=False).mean()
        result['macd_hist'] = result['macd'] - result['macd_signal']
        
        # Bollinger Bands
        result['bb_middle'] = result['close'].rolling(window=20).mean()
        bb_std = result['close'].rolling(window=20).std()
        result['bb_upper'] = result['bb_middle'] + (bb_std * 2)
        result['bb_lower'] = result['bb_middle'] - (bb_std * 2)
        
        # ATR
        high_low = result['high'] - result['low']
        high_close = (result['high'] - result['close'].shift()).abs()
        low_close = (result['low'] - result['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        result['atr'] = tr.rolling(window=14).mean()
        result['atr_pct'] = (result['atr'] / result['close']) * 100
        
        return result
