# 🤖 ARUNABHA ALGO BOT v5.0
### বাংলায় সম্পূর্ণ ডকুমেন্টেশন

> **Binance Futures-এ automatic crypto trading করার জন্য তৈরি।**
> Python-based, Telegram-controlled, 3-tier filter system সহ।

---

## 📑 সূচিপত্র

1. [Bot কী করে](#-bot-কী-করে)
2. [File Structure](#-file-structure)
3. [কীভাবে কাজ করে — Flow](#-কীভাবে-কাজ-করে--flow)
4. [3-Tier Filter System](#-3-tier-filter-system)
5. [Signal Grading System](#-signal-grading-system)
6. [Risk Management](#-risk-management)
7. [Sentiment Analysis](#-sentiment-analysis)
8. [Paper Trading Mode](#-paper-trading-mode)
9. [Adaptive Threshold System](#-adaptive-threshold-system)
10. [Session-Aware Sizing](#-session-aware-sizing)
11. [Telegram Commands](#-telegram-commands)
12. [API Endpoints](#-api-endpoints)
13. [.env Configuration](#-env-configuration)
14. [Deploy করার গাইড](#-deploy-করার-গাইড)
15. [Backtest করার নিয়ম](#-backtest-করার-নিয়ম)

---

## 🎯 Bot কী করে

| কাজ | Details |
|-----|---------|
| **Pairs** | BTC/USDT, ETH/USDT, DOGE/USDT, SOL/USDT, RENDER/USDT |
| **Exchange** | Binance Futures (USDT-margined) |
| **Primary TF** | 15m candle close-এ signal |
| **MTF Check** | 15m + 1h + 4h alignment verify |
| **Signal/Day** | Trending: 5, Choppy: 3, High-Vol: 2 |
| **Notification** | Telegram-এ real-time signal + alert |
| **Paper Mode** | Real order ছাড়া পুরো simulation |

---

## 📁 File Structure

```
arunabha_algo_bot/
│
├── main.py                          ← Entry point, FastAPI server, CLI
├── config.py                        ← সব settings এখানে
│
├── core/                            ← Bot-এর মূল brain
│   ├── engine.py                    ← Main engine — সব coordinate করে
│   ├── orchestrator.py              ← Webhook handler, command routing
│   ├── scheduler.py                 ← Daily reset, regime update timer
│   ├── state_manager.py             ← State persist (bot_state.json)
│   ├── constants.py                 ← Enum: MarketType, TradeDirection, Grade
│   └── expectancy_tracker.py        ← Trade expectancy track করে
│
├── data/                            ← Market data layer
│   ├── websocket_manager.py         ← Binance WS feed, auto-reconnect, heartbeat
│   ├── rest_client.py               ← REST API calls, rate limit handling
│   ├── cache_manager.py             ← In-memory cache (200 candles/symbol/tf)
│   └── sentiment_fetcher.py         ← Fear & Greed + Altcoin Season API
│
├── analysis/                        ← Technical analysis modules
│   ├── market_regime.py             ← BTC regime detect (BULLISH/BEARISH/CHOPPY)
│   ├── technical.py                 ← ATR, RSI, EMA, VWAP calculations
│   ├── structure.py                 ← BOS/CHoCH detection, S/R levels
│   ├── volume_profile.py            ← POC, Value Area, HVN/LVN
│   ├── liquidity.py                 ← Liquidity zones detect
│   ├── divergence.py                ← RSI divergence detection
│   ├── correlation.py               ← Pearson correlation with BTC
│   └── sentiment.py                 ← Mood analysis (RISK_ON/OFF/RECOVERY)
│
├── filters/                         ← 3-Tier filter system
│   ├── filter_orchestrator.py       ← Tier1 → Tier2 → Tier3 coordinate করে
│   ├── tier1_filters.py             ← Mandatory filters (সব pass না হলে block)
│   ├── tier2_filters.py             ← Weighted scoring (60% চাই)
│   └── tier3_filters.py             ← Bonus points (+4 to +21)
│
├── signals/                         ← Signal generation
│   ├── signal_generator.py          ← SL/TP calculate, signal assemble
│   ├── scorer.py                    ← Final score calculate
│   ├── confidence_calculator.py     ← Confidence % বের করে
│   ├── validator.py                 ← Signal valid কিনা check
│   └── signal_models.py             ← Signal, SignalResult dataclass
│
├── risk/                            ← Risk management layer
│   ├── risk_manager.py              ← Central risk coordinator
│   ├── position_sizing.py           ← Kelly Criterion + ATR-based sizing
│   ├── drawdown_controller.py       ← Drawdown track, 10% হলে pause
│   ├── daily_lock.py                ← Daily target/loss lock
│   ├── consecutive_loss.py          ← 2 consecutive loss → stop
│   └── trade_logger.py              ← Trade history log
│
├── notification/                    ← Telegram notification
│   ├── telegram_bot.py              ← Bot instance, message send
│   ├── message_formatter.py         ← Signal message format করে
│   └── templates.py                 ← Message templates
│
├── monitoring/                      ← Health & metrics
│   ├── health_check.py              ← Bot alive কিনা check
│   ├── metrics_collector.py         ← Performance metrics collect
│   └── logger.py                    ← Rotating file logger setup
│
├── backtest/                        ← Backtesting system
│   ├── backtest_engine.py           ← Historical data-এ signal simulate
│   ├── backtest_runner.py           ← Runner + walk-forward (mandatory)
│   ├── walk_forward.py              ← 60/40 train-test split, overfitting check
│   └── report_generator.py          ← txt/csv/json/html report তৈরি
│
└── utils/                           ← Helper utilities
    ├── indicators.py                 ← Technical indicator utilities
    ├── profit_calculator.py          ← Indian TDS/GST/brokerage calculate
    └── time_utils.py                 ← IST session helpers
```

---

## 🔄 কীভাবে কাজ করে — Flow

```
Binance WebSocket (15m candle close)
            │
            ▼
    engine._on_candle_close()
            │
            ├─── BTC/USDT? ──► btc_cache update → regime detect
            │
            └─── Other pairs ──► _analyze_symbol()
                                        │
                        ┌───────────────┴──────────────────┐
                        │         Pre-checks                │
                        │  • BTC data ready?                │
                        │  • Daily lock active?             │
                        │  • Max signals reached?           │
                        │  • Cooldown (15min)?              │
                        │  • Risk Manager: can_trade?       │
                        └───────────────┬──────────────────┘
                                        │
                              _build_data_packet()
                              (ohlcv 15m/1h/4h, btc_ohlcv,
                               sentiment, orderbook, funding)
                                        │
                                        ▼
                            filter_orchestrator.evaluate()
                            ┌──────────────────────────────┐
                            │  TIER 1 (Mandatory — 6 filters)│
                            │  ❌ Fail → Signal blocked      │
                            └──────────────┬───────────────┘
                                           │ ✅ Pass
                            ┌──────────────▼───────────────┐
                            │  TIER 2 (Weighted — 11 filters)│
                            │  Score < adaptive threshold?  │
                            │  ❌ Fail → Signal blocked      │
                            └──────────────┬───────────────┘
                                           │ ✅ Pass
                            ┌──────────────▼───────────────┐
                            │  TIER 3 (Bonus — 6 filters)   │
                            │  +0 to +21 bonus points       │
                            └──────────────┬───────────────┘
                                           │
                              signal_generator.generate()
                              (SL/TP calc, grade, confidence)
                                           │
                              _process_signal()
                              ┌────────────┴────────────┐
                              │   Entry Zone Check       │
                              │   Session Size Mult      │
                              │   Paper Trade? / Live    │
                              └────────────┬────────────┘
                                           │
                              telegram.send_signal()
                              state_manager.persist()
```

---

## 🔍 3-Tier Filter System

### Tier 1 — Mandatory Filters (সব pass করতেই হবে)

| Filter | কী দেখে | Block করে যখন |
|--------|---------|--------------|
| **BTC Regime** | BTC-এর trend direction ও confidence | Confidence < 20%, Direction mismatch |
| **Market Structure** | BOS/CHoCH detected কিনা | Structure WEAK এবং no BOS |
| **Volume** | Current volume vs 4-candle avg | < 0.7× average |
| **Liquidity** | Spread ও order book depth | Spread > 0.1%, Depth < $10,000 |
| **Session** | IST time check | Dead zone (10-11, 23-24, 0-1 IST) |
| **Sentiment** | Fear & Greed + ROC | F&G ≤ 15 → LONG block, F&G ≥ 75 rising fast → SHORT block, FALLING_FAST below 40 → LONG block |

### Tier 2 — Quality Scoring (min 60% চাই)

| Filter | Max Points | কী দেখে |
|--------|-----------|---------|
| MTF Confirmation | 20 | 15m + 1h + 4h structure/EMA alignment |
| Volume Profile | 15 | POC/Value Area position |
| Sentiment Score | 15 | F&G ROC + mood alignment |
| RSI Divergence | 15 | Bullish/Bearish divergence |
| EMA Stack | 10 | EMA9 > EMA21 > EMA200 (1h) |
| ATR Percent | 10 | 0.4% – 3.0% range |
| Funding Rate | 10 | Neutral/supportive funding |
| Open Interest | 10 | OI change direction |
| Volume on BOS | 10 | BOS candle-এ > 1.5× avg volume |
| VWAP Position | 5 | Price above/below VWAP |
| Support/Resistance | 5 | Nearest S/R distance |
| **Total Max** | **125 pts** | Score% = earned/total × 100 |

> **Adaptive Threshold:** Bot নিজে threshold adjust করে।
> Last 20 signals win rate < 40% → threshold +5%
> Win rate > 65% → threshold -3%

### Tier 3 — Bonus Points (signal quality বাড়ায়)

| Bonus | Max | কী দেখে |
|-------|-----|---------|
| Whale Movement | +5 | Volume ≥ 3× average |
| Liquidity Grab | +5 | Stop hunt wick > 60% candle range |
| Correlation Break | +4 | BTC correlation r < 0.3 (decorrelated) |
| Order Book Imbalance | +4 | bid/ask ratio > 2.0 বা < 0.5 |
| Fibonacci Level | +3 | 0.382 / 0.5 / 0.618 confluence |

---

## 🎖️ Signal Grading System

```
Score    Grade    Trade করবে?
─────    ─────    ──────────
≥ 90%    A+       ✅ হ্যাঁ (Best — full size)
≥ 80%    A        ✅ হ্যাঁ
≥ 70%    B+       ✅ হ্যাঁ
≥ 60%    B        ✅ হ্যাঁ (Minimum)
≥ 50%    C        ❌ না
< 50%    D        ❌ না (Blocked)
```

---

## 🛡️ Risk Management

### Position Sizing

```
Kelly Criterion (Quarter Kelly):
  K = win_rate - (1 - win_rate) / avg_rr
  Position = Account × (K/4) × ATR_adjustment

Fear & Greed adjustment:
  F&G > 70 (Greed) → size × 0.8
  F&G < 30 (Fear)  → size × 0.7
  F&G 40-60 (Neutral) → size × 1.0

Signal Grade adjustment:
  A+ → 1.2×,  A → 1.0×,  B+ → 0.9×,  B → 0.8×
```

### Trade Management

| Level | Action |
|-------|--------|
| **0.5R profit** | SL → Entry (Break Even) |
| **1.0R profit** | 50% position exit (Partial) |
| **1.5× ATR** | Trailing Stop activate |
| **TP hit** | Full exit |
| **SL hit** | Full exit |
| **90min timeout** | Force exit (choppy: 60min) |

### Daily Limits

| Limit | Value | Action |
|-------|-------|--------|
| Daily profit target | ₹500 | 🔒 Lock for day |
| Daily drawdown max | 2% | 🔒 Lock for day |
| Max drawdown | 10% | 🚨 Trading pause |
| Consecutive losses | 2 | ⏸️ Stop till next day |
| Cooldown between signals | 15 min | ⏳ Wait |

### Correlation Protection

```
Dynamic (preferred):
  Pearson r > 0.75 with active position → block same direction

Static fallback groups:
  BTC ↔ ETH   (always correlated)
  ETH ↔ SOL   (ecosystem)
  SOL ↔ RENDER (Solana ecosystem)
  DOGE        (isolated)
```

---

## 😱 Sentiment Analysis

**Fear & Greed Index** (alternative.me) + **Altcoin Season** (CoinGecko)

```
Market Mood এর ধরন:

RISK_ON    → Greed (60+) + AltSeason (60+) → LONG boost
RISK_OFF   → Extreme Fear (≤20) falling, বা Extreme Greed (≥80) rising
RECOVERY   → Fear (≤25) কিন্তু rising → early LONG opportunity ✅
NEUTRAL    → বাকি সব

Rate of Change (ROC):
  RISING_FAST   → F&G আজকে গতকালের চেয়ে +5 বা বেশি
  RISING        → +1 to +4
  STABLE        → 0
  FALLING       → -1 to -4
  FALLING_FAST  → -5 বা কম → LONG block (below 40)

Cache: 15 মিনিট (API বারবার call হয় না)
```

---

## 📄 Paper Trading Mode

```bash
# .env-এ set করো:
PAPER_TRADING=true
```

- Real order **দেওয়া হয় না**
- Signal Telegram-এ `[PAPER]` tag সহ আসে
- P&L simulate হয় এবং `bot_state.json`-এ save হয়
- Restart করলেও paper P&L থাকে
- Paper win rate → adaptive threshold learn করে
- ন্যূনতম **২ সপ্তাহ** paper trading করো লাইভের আগে

---

## 🎯 Adaptive Threshold System

Bot নিজে নিজে Tier2 threshold adjust করে:

```
Initial threshold: 60% (config.MIN_TIER2_SCORE)

প্রতিটা signal result record হয়।
শেষ 20টা signal-এর win rate দেখে:

win_rate < 40% → threshold +5% (বেশি সতর্ক)
win_rate > 65% → threshold -3% (বেশি signal allow)

Hard bounds:
  Minimum: 50% (নিচে যাবে না)
  Maximum: 80% (উপরে যাবে না)

Result দেওয়ার command: /trade_result BTCUSDT +2.3
```

---

## ⏰ Session-Aware Sizing

IST time অনুযায়ী position size automatically adjust হয়:

| Session | IST Time | Multiplier | কারণ |
|---------|----------|-----------|------|
| London Open | 13:00–15:00 | **1.2×** | সবচেয়ে ভালো liquidity |
| NY Open | 18:00–20:00 | **1.2×** | High volume |
| Asia | 07:00–11:00 | **0.7×** | কম volume, wide spread |
| High Volatility | যেকোনো সময় | **0.8×** | Risk কমানো |
| Default | বাকি সময় | **1.0×** | Normal |

`.env`-এ override করা যায়:
```
SIZE_MULT_LONDON=1.2
SIZE_MULT_NY=1.2
SIZE_MULT_ASIA=0.7
SIZE_MULT_HIGH_VOL=0.8
```

---

## 📱 Telegram Commands

Bot চলাকালীন Telegram-এ পাঠানো যায়:

| Command | কী করে |
|---------|--------|
| `/status` | Bot-এর current status |
| `/scan` | সব pairs manual scan |
| `/force_signal BTCUSDT` | নির্দিষ্ট pair-এ force signal |
| `/trade_result BTCUSDT +2.3` | Trade result দাও (adaptive threshold update) |
| `/reset_daily` | Daily stats reset |
| `/regime` | BTC regime update |
| `/debug` | Technical debug info |

---

## 🌐 API Endpoints

Bot একটি FastAPI server চালায়:

| Endpoint | Method | কাজ |
|----------|--------|-----|
| `/` | GET | Bot info |
| `/health` | GET | Health check |
| `/debug` | GET | Full debug status |
| `/logs` | GET | Recent logs |
| `/reload` | POST | Config hot-reload (restart ছাড়া) |
| `/webhook/{secret}` | POST | Telegram webhook |
| `/backtest` | POST | Backtest trigger |

### `/debug` response-এ কী থাকে:
```json
{
  "btc_data_ready": true,
  "market_type": "trending",
  "paper_trading": true,
  "adaptive_threshold": 62.5,
  "ws_connected": true,
  "ws_last_message_ago": 8.2,
  "ws_reconnects": 0,
  "daily_signals": 2,
  "consecutive_losses": 0,
  "current_drawdown_pct": 0.5
}
```

---

## ⚙️ .env Configuration

```bash
# ── Telegram (mandatory) ──────────────────────────────
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# ── Binance (paper mode-এ empty রাখো) ─────────────────
BINANCE_API_KEY=your_api_key
BINANCE_SECRET=your_secret
# Testnet-এ: testnet.binancefuture.com এর key দাও

# ── Capital ───────────────────────────────────────────
ACCOUNT_SIZE=100000              # ₹1,00,000
RISK_PER_TRADE=1.0               # 1% = ₹1,000 per trade
MAX_LEVERAGE=15

# ── Mode ──────────────────────────────────────────────
ENVIRONMENT=development          # development / production
PAPER_TRADING=true               # true = paper, false = live
LOG_LEVEL=INFO

# ── Session sizing (optional override) ────────────────
SIZE_MULT_LONDON=1.2
SIZE_MULT_NY=1.2
SIZE_MULT_ASIA=0.7
SIZE_MULT_HIGH_VOL=0.8

# ── Server ────────────────────────────────────────────
PORT=8080
WEBHOOK_SECRET=change-this-secret

# ── Redis (optional) ──────────────────────────────────
# REDIS_URL=redis://localhost:6379
```

---

## 🚀 Deploy করার গাইড

### Step 1: Install

```bash
git clone <repo>
cd arunabha_algo_bot
pip install -r requirements.txt
cp .env.example .env
# .env edit করো
```

### Step 2: Paper mode-এ শুরু

```bash
# .env-এ PAPER_TRADING=true রাখো
python main.py --mode web
```

### Step 3: Debug দিয়ে verify

```
http://localhost:8080/debug
```
এখানে দেখো:
- `btc_data_ready: true` হয়েছে?
- `ws_connected: true`?
- `market_type` detect হয়েছে?

### Step 4: Backtest

```bash
python main.py --mode backtest --symbol BTCUSDT --days 90
# Walk-forward result দেখো
# verdict: ROBUST হলে ভালো
# verdict: OVERFIT হলে strategy tweak করো
```

### Step 5: ২ সপ্তাহ paper trading

- Signal আসছে?
- Win rate কত?
- Adaptive threshold কোথায় settle করছে?
- `/debug` দিয়ে প্রতিদিন check করো

### Step 6: Live শুরু

```bash
# .env-এ:
PAPER_TRADING=false
ENVIRONMENT=production
RISK_PER_TRADE=0.5    # প্রথম সপ্তাহ half size

python main.py --mode web
```

---

## 📊 Backtest করার নিয়ম

```bash
# Basic backtest
python main.py --mode backtest \
  --symbol BTCUSDT \
  --days 90 \
  --timeframe 15m

# Output:
# ✅ Total trades: 47
# ✅ Win rate: 58.5%
# ✅ Total return: +12.3%
# ✅ Profit factor: 1.85
# ✅ Sharpe ratio: 1.42
# ✅ Max drawdown: -6.2%
# ✅ Walk-forward verdict: ROBUST ← এটাই দেখতে হবে
```

Walk-forward verdict মানে:

| Verdict | মানে |
|---------|------|
| `ROBUST` | ✅ Train vs Test performance কাছাকাছি — strategy solid |
| `MODERATE` | ⚠️ কিছুটা overfit — parameter tweak করো |
| `OVERFIT` | ❌ Train ভালো কিন্তু Test খারাপ — strategy ব্যবহার করো না |

---

## 🔧 WebSocket Health

Bot WebSocket-এর স্বাস্থ্য নিজেই monitor করে:

```
প্রতি 10 সেকেন্ডে heartbeat check হয়।
30 সেকেন্ড কোনো data না আসলে:
  → সংযোগ মৃত ঘোষণা
  → Session বন্ধ (memory leak নেই)
  → Auto reconnect শুরু
  → Telegram-এ alert

Reconnect strategy:
  1st retry: 3s
  2nd retry: 6s
  3rd retry: 12s
  ...
  Max wait: 120s (তারপর আবার 3s থেকে শুরু)
```

---

## 💾 State Persistence

`bot_state.json` ফাইলে সব কিছু save হয়:

```json
{
  "date": "2025-03-01",
  "daily_trades": 3,
  "daily_wins": 2,
  "daily_pnl_inr": 450.0,
  "consecutive_losses": 0,
  "current_balance": 100450.0,
  "paper_pnl_inr": 1200.0,
  "paper_trades": 8,
  "active_directions": {
    "ETH/USDT": "LONG"
  }
}
```

Bot restart হলে এই file থেকে সব restore হয়।
নতুন দিন হলে daily stats reset হয়, balance থাকে।

---

## 🇮🇳 Indian Tax Calculation

প্রতিটা trade-এ automatically:

```
TDS:       Gross profit-এর 1%
Brokerage: Trade value-এর 0.05% (CoinDCX)
GST:       Brokerage-এর 18% শুধু

Net P&L = Gross - TDS - Brokerage - GST
```

---

## ⚠️ Important Notes

1. **Paper trading skip করো না** — code ভালো হলেও real market অপ্রত্যাশিত
2. **প্রথম সপ্তাহ half size** — `RISK_PER_TRADE=0.5`
3. **API key-এ withdrawal permission রাখবে না** — bot detect করে block করে
4. **Testnet দিয়ে শুরু** — `testnet.binancefuture.com`
5. **`/trade_result` দাও** — না দিলে adaptive threshold কাজ করবে না

---

## 📈 Version History

| Version | Changes |
|---------|---------|
| v5.0 | Paper trading, Adaptive threshold, Session sizing, Correlation fix, Walk-forward mandatory |
| v4.2 | Sentiment ROC, WebSocket heartbeat, F&G rate of change |
| v4.1 | BOS/CHoCH volume confirmation, MTF real alignment, Kelly sizing |
| v4.0 | 3-tier filter system, State persistence, Indian tax calculation |

---

*Arunabha Algo Bot — Binance Futures এ intelligent crypto trading*
*সব কিছু নিজের risk-এ করবে। এটা financial advice নয়।*
