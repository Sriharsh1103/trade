# Forex Trading Mechanics (Exness / MetaTrader 5)

How trading works on platforms like Exness, and how this system integrates.

## Platform Overview

Exness is a retail forex broker. Traders access markets through:

| Platform | Use Case |
|----------|----------|
| **MetaTrader 5 (MT5)** | Primary desktop/mobile terminal — order execution, charts, EAs |
| **Exness web terminal** | Browser-based trading (no official public REST API for retail) |
| **Exness Personal Area** | Account management, deposits, demo account creation |

Exness does **not** expose a direct retail REST trading API. Automation paths:

1. **MetaTrader5 Python library** — script talks to a running MT5 terminal logged into Exness
2. **MT5 REST bridge** — Docker container (Wine + MT5) exposing HTTP API (e.g. `xm-exness-mt5-linux`)
3. **Browser automation** — Playwright/Puppeteer on web terminal (fragile, higher latency, last resort)
4. **Third-party APIs** — API2Trade, etc. (paid middleware)

**Recommended for this project:** MT5 REST bridge in Docker, called by our Go backend.

## Core Concepts

### Currency Pairs & Quotes

- Traded in **pairs** (e.g. EUR/USD, GBP/JPY)
- **Bid** — price broker buys from you (you sell here)
- **Ask** — price broker sells to you (you buy here)
- **Spread** = Ask − Bid (primary transaction cost)
- **Pip** — smallest price increment (0.0001 for most pairs, 0.01 for JPY pairs)

### Lot Sizes

| Lot Type | Units | Approx. EUR/USD Value @ 1.10 |
|----------|-------|------------------------------|
| Standard | 100,000 | ~$110,000 |
| Mini | 10,000 | ~$11,000 |
| Micro | 1,000 | ~$1,100 |

### Leverage & Margin

```
Notional Value = Lot Size × Contract Size × Price
Required Margin = Notional Value ÷ Leverage

Example: 0.1 lot EUR/USD @ 1.1000, leverage 1:100
  Notional = 10,000 × 1.1000 = $11,000
  Margin   = $11,000 ÷ 100 = $110
```

- **Equity** = Balance + floating P&L of open positions
- **Free Margin** = Equity − Used Margin
- **Margin Level** = (Equity ÷ Used Margin) × 100%
- **Stop-out** — broker force-closes positions when margin level drops below threshold (often 0–50%)

Leverage amplifies **both** gains and losses. A 1% adverse move at 1:100 leverage ≈ 100% margin loss.

### Order Types

| Type | Behavior | Use |
|------|----------|-----|
| **Market Buy/Sell** | Execute immediately at current Ask/Bid | Enter/exit now |
| **Buy Limit** | Buy when price drops to level | Buy on pullback |
| **Sell Limit** | Sell when price rises to level | Sell on rally |
| **Buy Stop** | Buy when price rises above level | Breakout entry (long) |
| **Sell Stop** | Sell when price drops below level | Breakout entry (short) |
| **Stop Loss (SL)** | Close position at loss threshold | Risk control |
| **Take Profit (TP)** | Close position at profit target | Lock gains |
| **Trailing Stop** | SL moves with favorable price | Protect running profit |

### Slippage & Gaps

- **Slippage** — fill price worse than quoted (common during news, low liquidity)
- **Gap** — price jumps past SL/TP (weekend open, flash crash); SL does not guarantee exit price

## Demo vs Live

| Aspect | Demo | Live |
|--------|------|------|
| Money | Virtual balance | Real funds |
| Spreads | Similar to live | Real spreads + commission |
| Slippage | Often minimal | Real market conditions |
| Psychology | No emotional pressure | Real stress |
| Server | `Exness-MT5Trial` etc. | `Exness-MT5Real` etc. |

**Always start demo.** Demo fills may not reflect live slippage during volatile events.

## Trading Flow (Automated)

```
1. Connect to MT5 bridge (login + server + symbol)
2. Fetch account state (balance, equity, margin, open positions)
3. Fetch market data (bid/ask, spread, recent bars)
4. Strategy generates signal (buy/sell/hold)
5. Risk engine validates:
   - Position size within limits
   - SL/TP distances valid
   - Daily loss limit not exceeded
   - Margin level safe
6. Submit order to MT5 (market or pending)
7. Monitor open positions:
   - Check unrealized P&L vs targets
   - Auto-exit if loss threshold breached
   - Update trailing stops
8. Log trade, update metrics
```

## Exness-Specific Notes

- Demo accounts: create in Personal Area, no deposit required
- MT5 login: account number + investor/trader password + server name
- Symbols may have suffixes (e.g. `EURUSDm` vs `EURUSD`) — verify in terminal
- Swap/overnight fees apply to positions held past rollover
- Exness offers high leverage (up to 1:2000 on some accounts) — use conservatively

## Integration Endpoints (MT5 Bridge)

Expected REST API surface from MT5 bridge container:

```
POST /api/accounts          — register MT5 account
GET  /api/accounts/{id}/data      — balance, equity, margin
GET  /api/accounts/{id}/positions — open positions
GET  /api/accounts/{id}/orders    — pending orders
POST /api/accounts/{id}/order     — place order (bridge-specific)
GET  /api/accounts/{id}/price/{symbol} — bid/ask
```

Our Go backend wraps this with risk checks and demo-mode simulation.
