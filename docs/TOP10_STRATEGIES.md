# Top 10 Famous Trading Strategies — XAUUSD (Gold) Analysis

> **Account context:** Exness demo ~$28.54, 0.01 lot, 2000× leverage, max ~$0.57 loss/trade (2% equity).
> **Volume note:** Gold has no central exchange volume. All strategies below use **tick volume** (quote update count) as a proxy.

---

## Comparison Table

| # | Strategy | Best Market | Volume Dep. | $28 Demo Fit | Complexity | Typical Win Rate | Typical R:R | XAUUSD Score |
|---|----------|-------------|-------------|--------------|------------|------------------|-------------|--------------|
| 1 | MA Crossover (Golden/Death Cross) | Trending | Low | Poor — lags, whipsaws on M5 | Low | 35–45% | 1:2 | ★★☆☆☆ |
| 2 | RSI Overbought/Oversold | Ranging | Low | Good — tight SL works | Low | 55–65% | 1:1.2 | ★★★★☆ |
| 3 | MACD Signal Crossover | Trending | Medium | Moderate — needs trend | Medium | 40–50% | 1:1.5 | ★★★☆☆ |
| 4 | **Bollinger + RSI Mean Reversion** | **Ranging** | **Low** | **Excellent — defined bands** | **Medium** | **58–68%** | **1:1.3** | **★★★★★** |
| 5 | Support/Resistance Breakout | Trending (post-break) | High | Poor — false breakouts costly | High | 40–55% | 1:2.5 | ★★☆☆☆ |
| 6 | Fibonacci Retracement | Trending pullbacks | Low | Moderate — subjective levels | Medium | 45–55% | 1:1.5 | ★★★☆☆ |
| 7 | Ichimoku Cloud | Trending | Low | Poor — too many signals, wide stops | High | 45–55% | 1:2 | ★★☆☆☆ |
| 8 | Volume Profile / VWAP | Intraday institutional | **Very High** | Poor — tick volume unreliable for gold | High | 50–60% | 1:1.5 | ★★☆☆☆ |
| 9 | Price Action (Pin Bar / Engulfing) | Any (context-dependent) | Medium | Moderate — needs screen time | Medium | 50–60% | 1:2 | ★★★☆☆ |
| 10 | Trend Following (ADX + EMA) | Strong trends only | Medium | Moderate — ADX filter helps | Medium | 35–45% | 1:3 | ★★★☆☆ |

---

## Detailed Strategy Evaluations

### 1. Moving Average Crossover (Golden/Death Cross)

**Logic:** Buy when fast MA crosses above slow MA; sell on reverse cross.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Strong in sustained trends (London/NY open). Fails in ranging gold — frequent whipsaws. |
| Volume | Low dependency. Lagging indicator; volume confirmation optional. |
| $28 Demo | Poor. Crossovers arrive late; $0.57 SL often hit before move develops on 0.01 lot. |
| Complexity | Low — two EMAs (e.g. 9/21). |
| Win Rate / R:R | ~35–45% win rate, 1:2 R:R in trends. |

**XAUUSD verdict:** Avoid on small demo account without higher timeframe filter.

---

### 2. RSI Overbought/Oversold

**Logic:** Buy when RSI < 30 (oversold); sell when RSI > 70 (overbought).

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Best in ranging/consolidation. Dangerous in strong trends (RSI stays overbought). |
| Volume | Low. Works on price alone. |
| $28 Demo | Good standalone, better combined with Bollinger bands for location filter. |
| Complexity | Low — 14-period RSI standard. |
| Win Rate / R:R | ~55–65%, 1:1.2 typical. |

**XAUUSD verdict:** Strong component strategy; use with band/trend filter.

---

### 3. MACD Signal Line Crossover

**Logic:** Buy on MACD line crossing above signal line; sell on cross below.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Trending markets. Choppy in Asian session gold. |
| Volume | Medium — histogram volume helps confirm momentum. |
| $28 Demo | Moderate. Needs 26/12/9 default settings; slow on M5 gold. |
| Complexity | Medium. |
| Win Rate / R:R | ~40–50%, 1:1.5. |

**XAUUSD verdict:** Secondary confirmation only, not primary for micro account.

---

### 4. Bollinger Bands Mean Reversion ★ CHOSEN

**Logic:** Buy at lower band when RSI confirms oversold; sell at upper band when RSI overbought. Exit at middle band (SMA) or opposite band.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | **Excels in ranging/choppy gold** (Asian session, post-NY consolidation). Use ADX < 25 filter. |
| Volume | Low — price std-dev based. Tick volume spike at band touch adds confidence. |
| $28 Demo | **Excellent.** Tight, defined entries; SL just beyond band (~$0.50–0.57). |
| Complexity | Medium — BB(20,2) + RSI(14). |
| Win Rate / R:R | ~58–68%, 1:1.3. Higher win rate suits small account survival. |

**XAUUSD verdict:** **Best choice** for current demo conditions — gold ranging ~4300–4320, high tick activity, previous momentum trade stopped out (trend-following failed).

---

### 5. Support/Resistance Breakout

**Logic:** Enter on break above resistance or below support with volume confirmation.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Post-breakout trending. |
| Volume | **High** — false breakouts common without real volume. Tick volume unreliable for gold. |
| $28 Demo | Poor — one false breakout = 2% account loss. |
| Complexity | High — level detection, retest logic. |
| Win Rate / R:R | ~40–55%, 1:2.5 when genuine. |

**XAUUSD verdict:** Not suitable for $28 demo without institutional volume data.

---

### 6. Fibonacci Retracement

**Logic:** Enter at 38.2%, 50%, 61.8% retracement levels in established trend.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Trending pullbacks only. |
| Volume | Low. |
| $28 Demo | Moderate — subjective swing high/low selection causes inconsistency. |
| Complexity | Medium. |
| Win Rate / R:R | ~45–55%, 1:1.5. |

**XAUUSD verdict:** Good for manual trading; hard to automate reliably on tick data.

---

### 7. Ichimoku Cloud

**Logic:** Multi-component system — price above cloud = bullish, Tenkan/Kijun crosses, etc.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Trending. Too many conflicting signals in range. |
| Volume | Low. |
| $28 Demo | Poor — wide stops required; account can't absorb. |
| Complexity | High — 5 lines + cloud. |
| Win Rate / R:R | ~45–55%, 1:2. |

**XAUUSD verdict:** Over-engineered for micro demo account.

---

### 8. Volume Profile / VWAP

**Logic:** Trade around high-volume nodes (POC) and VWAP deviations.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Intraday mean reversion around VWAP. |
| Volume | **Very High** — requires accurate volume. Gold OTC tick volume is a poor proxy. |
| $28 Demo | Poor — unreliable signals from broker tick count. |
| Complexity | High. |
| Win Rate / R:R | ~50–60% with real exchange volume; much lower with tick proxy. |

**XAUUSD verdict:** Avoid until real volume data available.

---

### 9. Price Action (Pin Bar / Engulfing)

**Logic:** Enter on reversal candlestick patterns at key levels.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Both — context-dependent. |
| Volume | Medium — engulfing with volume stronger. |
| $28 Demo | Moderate — needs 5+ candles context; subjective pattern recognition. |
| Complexity | Medium (automated) to High (manual). |
| Win Rate / R:R | ~50–60%, 1:2. |

**XAUUSD verdict:** Good manual skill; harder to automate consistently on synthetic candles.

---

### 10. Trend Following (ADX + EMA)

**Logic:** Trade only when ADX > 25 (strong trend); direction from EMA slope.

| Criterion | Assessment |
|-----------|------------|
| Trending vs Ranging | Strong trends only. Sits out ranges (good filter). |
| Volume | Medium. |
| $28 Demo | Moderate — fewer trades but larger moves needed for TP. |
| Complexity | Medium. |
| Win Rate / R:R | ~35–45%, 1:3 (fewer wins, bigger rewards). |

**XAUUSD verdict:** Good trend filter to **combine** with mean reversion (ADX < 25 → use BB+RSI; ADX > 25 → skip or switch to trend mode).

---

## Current Gold Conditions (Sep 2, 2026)

| Metric | Observation |
|--------|-------------|
| Price zone | ~4308–4320 XAUUSD (post first trade SL at 4319) |
| Volatility | High — $1–2 intraday swings typical |
| Session | Mixed — ranging behavior after NY move |
| Tick activity | Moderate on Exness demo (500ms monitor interval) |
| Prior result | Momentum buy stopped out −$1.46 (trend-following failed in range) |

---

## Strategy Selection

### 🏆 Primary: Bollinger Bands + RSI Mean Reversion

**Why:**
1. Previous momentum trade lost money — gold was **ranging**, not trending.
2. Tick volume proxy shows moderate activity (good for band-touch exhaustion, bad for breakout).
3. High win rate (~60%) suits $28 survival — can't afford many consecutive losses.
4. Defined entry at band edge + RSI extreme = clear SL beyond band (~$0.57 max).
5. Low volume dependency — works on price alone.

### 🥈 Secondary (future): ADX + EMA Trend Following

Use when ADX > 25 during London/NY overlap for trend continuation trades. Not implemented now — one strategy done well.

---

## Implementation Parameters (gold_pro_strategy.py)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| BB Period | 20 | Standard; ~5 min of 15s candles |
| BB Std Dev | 2.0 | Captures ~95% of price action |
| RSI Period | 14 | Industry standard |
| RSI Oversold | 30 | Mean reversion buy zone |
| RSI Overbought | 70 | Mean reversion sell zone |
| ADX Filter | < 30 | Skip strong trends (mean reversion unsafe) |
| Candle Interval | 15s | Fast enough for demo signal generation |
| Min Confidence | 0.60 | Filter weak band touches |
| SL/TP | Go risk manager | 2% equity SL, 10% margin TP |

---

## Risk Alignment

Matches `config/config.yaml` and Go `risk.Manager`:
- **Max loss:** 2% of equity (~$0.57 on $28.54)
- **Take profit:** 10% of position margin (~$0.21 on 0.01 lot XAUUSD)
- **Daily loss limit:** 5% (~$1.43)
- **Lot size:** 0.01 (minimum)

---

## How to Run

```bash
# Terminal 1: Go demo trader
./bin/trader --config config/config.yaml

# Terminal 2: Pro strategy (continuous)
./scripts/run_pro_strategy.sh

# Single evaluation + backtest
python3 strategy/gold_pro_strategy.py --once --backtest
```
