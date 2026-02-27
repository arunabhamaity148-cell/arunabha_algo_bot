"""
ARUNABHA ALGO BOT - Message Formatter
Formats messages for Telegram
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

import config

logger = logging.getLogger(__name__)


class MessageFormatter:
    """
    Formats various message types for Telegram
    """
    
    def format_signal(self, signal: Dict, market_type: str) -> str:
        """Format trading signal"""
        
        direction = signal.get("direction", "UNKNOWN")
        if direction == "LONG":
            emoji = "🟢"
            trend = "🚀 UPTREND"
        else:
            emoji = "🔴"
            trend = "📉 DOWNTREND"
        
        # Market emoji
        market_emoji = {
            "trending": "📈",
            "choppy": "〰️",
            "high_vol": "⚡"
        }.get(market_type, "📊")
        
        # Key factors
        factors = signal.get("key_factors", [])
        factors_text = "\n".join([f"• {f}" for f in factors[:3]])
        
        # Levels
        levels = signal.get("levels", {})
        levels_text = ""
        if levels.get("nearest_support"):
            levels_text += f"\n📊 Support: {levels['nearest_support']:.2f}"
        if levels.get("nearest_resistance"):
            levels_text += f"\n📊 Resistance: {levels['nearest_resistance']:.2f}"
        
        # Position size
        position = signal.get("position_size", {})
        position_text = ""
        if position:
            position_text = f"\n💰 Size: ${position.get('position_usd', 0):,.0f}"
        
        # Time
        timestamp = signal.get("timestamp", datetime.now().isoformat())
        try:
            time_str = datetime.fromisoformat(timestamp).strftime("%H:%M IST")
        except:
            time_str = datetime.now().strftime("%H:%M IST")
        
        # Sentiment
        sentiment_text = ""
        sentiment_info = signal.get("sentiment")
        if sentiment_info:
            fg_val = sentiment_info.get("fear_greed_value", "")
            fg_label = sentiment_info.get("fear_greed_label", "").replace("_", " ")
            alt = sentiment_info.get("alt_season_index", "")
            fg_emoji_map = {
                "EXTREME FEAR": "😱", "FEAR": "😨", "NEUTRAL": "😐",
                "GREED": "😄", "EXTREME GREED": "🤑"
            }
            fg_em = fg_emoji_map.get(fg_label, "😮")
            sentiment_text = f"\n{fg_em} <b>Sentiment:</b> {fg_label}: {fg_val} | Alt Season: {alt}"

        message = f"""
{emoji} <b>ARUNABHA SIGNAL</b> {emoji}

<b>Symbol:</b> {signal.get('symbol')}
<b>Direction:</b> {trend}
<b>Grade:</b> {signal.get('grade')} (Score: {signal.get('score')})
<b>Confidence:</b> {signal.get('confidence')}%

<b>Entry:</b> ${signal.get('entry', 0):,.2f}
<b>Stop Loss:</b> ${signal.get('stop_loss', 0):,.2f}
<b>Take Profit:</b> ${signal.get('take_profit', 0):,.2f}
<b>R:R Ratio:</b> {signal.get('rr_ratio', 0):.2f}{position_text}

<b>Market:</b> {market_emoji} {market_type.upper()}
<b>Structure:</b> {signal.get('structure_strength', 'UNKNOWN')}{sentiment_text}
{factors_text}{levels_text}

⏰ {time_str}

⚠️ <i>Manual trade only - Auto trade OFF</i>
"""
        
        return message
    
    def format_daily_summary(self, stats: Dict) -> str:
        """Format daily summary"""
        
        # Determine mood
        pnl = stats.get("total_pnl", 0)
        if pnl >= config.DAILY_PROFIT_TARGET:
            mood = "🥳🎉🍾"
            target_text = "★ TARGET ACHIEVED! ★"
        elif pnl > 0:
            mood = "😊"
            target_text = f"₹{config.DAILY_PROFIT_TARGET - pnl:.0f} to target"
        elif pnl == 0:
            mood = "😐"
            target_text = "Break even day"
        else:
            mood = "😔"
            target_text = f"Loss: ₹{abs(pnl):.0f}"
        
        # Win rate
        wins = stats.get("wins", 0)
        total = stats.get("total_trades", 0)
        win_rate = (wins / total * 100) if total > 0 else 0
        
        message = f"""
{mood} <b>Daily Summary</b> {mood}

📊 <b>Trades</b>
• Total: {total}
• Wins: {wins}
• Losses: {stats.get('losses', 0)}
• Win Rate: {win_rate:.1f}%

💰 <b>P&L</b>
• Gross: ₹{stats.get('total_pnl', 0):,.0f}
• Best: {stats.get('best_trade', 0):+.1f}%
• Worst: {stats.get('worst_trade', 0):+.1f}%

🎯 {target_text}
⚡ Risk per trade: {config.RISK_PER_TRADE}%

<i>Tomorrow is a new day!</i>
"""
        
        return message
    
    def format_weekly_summary(self, stats: Dict) -> str:
        """Format weekly summary"""
        
        message = f"""
📊 <b>Weekly Performance</b>

Trades: {stats.get('total_trades', 0)}
Win Rate: {stats.get('win_rate', 0):.1f}%
Total P&L: ₹{stats.get('total_pnl', 0):,.0f}
Profit Factor: {stats.get('profit_factor', 0):.2f}

Best Day: {stats.get('best_day', 'N/A')}
Worst Day: {stats.get('worst_day', 'N/A')}

🎯 Next week target: ₹{config.WEEKLY_PROFIT_TARGET}
"""
        
        return message
    
    def format_health_status(self, status: Dict) -> str:
        """Format health status"""
        
        emoji = "✅" if status.get("status") == "healthy" else "⚠️"
        
        message = f"""
{emoji} <b>Bot Health</b>

Market: {status.get('market', {}).get('market_type', 'unknown')}
BTC Regime: {status.get('market', {}).get('btc_regime', 'unknown')}

📊 <b>Today</b>
Signals: {status.get('market', {}).get('daily_signals', 0)}/{status.get('market', {}).get('daily_limit', 0)}
Consecutive Losses: {status.get('market', {}).get('consecutive_losses', 0)}

⚙️ <b>Components</b>
"""
        
        for comp, comp_status in status.get("components", {}).items():
            icon = "✅" if comp_status == "ok" else "❌"
            message += f"\n{icon} {comp}"
        
        message += f"\n\n⏰ {datetime.now().strftime('%H:%M IST')}"
        
        return message
    
    def format_simple(self, text: str, emoji: str = "📢") -> str:
        """Format simple message"""
        return f"{emoji} {text}"
    
    def format_error(self, error: str) -> str:
        """Format error message"""
        return f"🚨 <b>Error</b>\n<code>{error}</code>"
    
    def format_alert(self, message: str, level: str = "INFO") -> str:
        """Format alert message"""
        emoji = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🚨",
            "SUCCESS": "✅"
        }.get(level, "📢")
        
        return f"{emoji} <b>{level}</b>\n{message}"
