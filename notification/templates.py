"""
ARUNABHA ALGO BOT - Message Templates
Pre-defined message templates for common notifications
"""

from datetime import datetime
import pytz
import config  # 🔴 এই লাইনটা যোগ করুন


class MessageTemplates:
    """
    Collection of message templates
    """
    
    @staticmethod
    def startup_message() -> str:
        """Bot startup message"""
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        return f"""
🚀 <b>ARUNABHA ALGO BOT v4.0</b> 🚀

✅ Bot started successfully
📅 {now.strftime('%A, %d %B %Y')}
⏰ {now.strftime('%H:%M IST')}

📊 <b>Configuration</b>
• Account Size: ₹{config.ACCOUNT_SIZE:,.0f}
• Risk/Trade: {config.RISK_PER_TRADE}%
• Max Leverage: {config.MAX_LEVERAGE}x
• Daily Target: ₹{config.DAILY_PROFIT_TARGET}

🎯 <i>Manual signals only - Auto trade OFF</i>
"""
    
    @staticmethod
    def shutdown_message() -> str:
        """Bot shutdown message"""
        return """
🛑 <b>ARUNABHA Bot Shutting Down</b>

Bot is going offline.
All active positions should be closed manually.

<i>See you next time!</i>
"""
    
    @staticmethod
    def trade_win(symbol: str, pnl_pct: float, pnl_usd: float) -> str:
        """Winning trade message"""
        return f"""
✅ <b>WINNING TRADE</b> ✅

Symbol: {symbol}
P&L: +{pnl_pct:.2f}% (${pnl_usd:.2f})

🎯 Target achieved!
"""
    
    @staticmethod
    def trade_loss(symbol: str, pnl_pct: float, pnl_usd: float) -> str:
        """Losing trade message"""
        return f"""
❌ <b>LOSS</b> ❌

Symbol: {symbol}
P&L: {pnl_pct:.2f}% (${pnl_usd:.2f})

💪 Next trade will be better!
"""
    
    @staticmethod
    def daily_target_hit(pnl: float) -> str:
        """Daily target reached message"""
        return f"""
🎉 <b>DAILY TARGET ACHIEVED!</b> 🎉

Profit: ₹{pnl:,.2f}
Target: ₹{config.DAILY_PROFIT_TARGET}

🏆 Excellent work!
"""
    
    @staticmethod
    def daily_loss_limit(pnl: float) -> str:
        """Daily loss limit reached message"""
        return f"""
⚠️ <b>DAILY LOSS LIMIT REACHED</b>

Loss: {pnl:.2f}%
Limit: {config.MAX_DAILY_DRAWDOWN_PCT}%

🛑 Trading stopped for today.
Tomorrow is a new day!
"""
    
    @staticmethod
    def consecutive_losses(count: int) -> str:
        """Consecutive losses message"""
        return f"""
⚠️ <b>{count} Consecutive Losses</b>

Taking a break to reset.
Cooling period: {config.COOLDOWN_MINUTES} minutes.

🧘 <i>Stay disciplined!</i>
"""
    
    @staticmethod
    def market_update(market_type: str, btc_regime: str, confidence: int) -> str:
        """Market condition update"""
        emoji = {
            "trending": "📈",
            "choppy": "〰️",
            "high_vol": "⚡"
        }.get(market_type, "📊")
        
        return f"""
{emoji} <b>Market Update</b>

Market: {market_type.upper()}
BTC Regime: {btc_regime}
Confidence: {confidence}%

🔄 Adjusting strategy accordingly...
"""
    
    @staticmethod
    def position_update(symbol: str, current_r: float, action: str) -> str:
        """Position management update"""
        emoji = "🟢" if current_r > 0 else "🔴"
        
        messages = {
            "PARTIAL_EXIT": f"{emoji} <b>Partial Exit</b>\n{action}",
            "BREAK_EVEN": f"🛡️ <b>Break Even</b>\n{action}",
            "SL_HIT": f"❌ <b>Stop Loss</b>\n{action}",
            "TP_HIT": f"✅ <b>Take Profit</b>\n{action}"
        }
        
        return messages.get(action, f"{emoji} {action}")
    
    @staticmethod
    def weekly_review(wins: int, losses: int, pnl: float, win_rate: float) -> str:
        """Weekly review message"""
        return f"""
📊 <b>Weekly Review</b>

Trades: {wins + losses}
Wins: {wins}
Losses: {losses}
Win Rate: {win_rate:.1f}%
Total P&L: ₹{pnl:,.2f}

📈 <i>Keep improving!</i>
"""
    
    @staticmethod
    def milestone_message(milestone: str, value: float) -> str:
        """Milestone achievement message"""
        return f"""
🏆 <b>MILESTONE ACHIEVED!</b>

{milestone}: {value}

🎉 Congratulations!
"""
    
    @staticmethod
    def error_alert(error_type: str, message: str) -> str:
        """Error alert message"""
        return f"""
🚨 <b>ERROR ALERT</b>

Type: {error_type}
Message: {message}

🔧 Check logs for details.
"""
    
    @staticmethod
    def connection_status(status: str, exchange: str) -> str:
        """Connection status update"""
        emoji = "✅" if status == "connected" else "❌"
        
        return f"""
{emoji} <b>Connection Status</b>

Exchange: {exchange}
Status: {status.upper()}
"""
    
    @staticmethod
    def quote_of_the_day() -> str:
        """Trading quote"""
        quotes = [
            "The trend is your friend until it ends.",
            "Cut losses short, let profits run.",
            "Plan your trade, trade your plan.",
            "Don't confuse brains with a bull market.",
            "The goal is to make your money last as long as you live.",
            "Patience is not simply enduring, it is waiting with an active goal.",
            "In trading, you must be disciplined and methodical.",
            "Risk comes from not knowing what you're doing.",
            "The stock market is a device for transferring money from the impatient to the patient.",
            "It's not whether you're right or wrong that's important, but how much money you make when you're right and how much you lose when you're wrong."
        ]
        
        import random
        return f"💭 <i>{random.choice(quotes)}</i>"
