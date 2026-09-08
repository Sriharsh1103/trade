# Exness Auto Trading — Simple Guide (No Public API)

Exness **retail API nahi deta**. Is repo mein teen alag-alag approaches hain — ab
ek **primary** hai, baaki do **alternate/experimental** (deprecated nahi, bas
default nahi).

## Primary — Go Engine + Browser Mirror (`./scripts/run_auto.sh`)

```
Go engine (risk checks + signals) → auto_trader.py → strategy/exness_executor.py
mirrors the accepted order onto whichever practice terminal
config/credentials.yaml is filled in for (see strategy/broker_login.py)
```

| Pros | Cons |
|------|------|
| Ek jagah risk management (daily loss limit, max positions) | UI change → mirror step toot sakta hai |
| Global control gate — trading OFF by default, explicit enable/disable/stop-all | PC + browser open rehna zaroori |
| Regime-aware strategy (trend vs range) | |

**Safety gate:** trading is disabled until you call it explicitly:
```
curl -X POST -H "Authorization: Bearer <server.api_token>" \
  http://localhost:8080/api/v1/control/enable -d '{"reason":"manual start"}'
```
Stop everything at any time (disables + closes all open positions):
```
curl -X POST -H "Authorization: Bearer <server.api_token>" \
  http://localhost:8080/api/v1/control/stop-all -d '{"reason":"manual stop"}'
```

## Alternate — Pure Browser Auto-Control (`./scripts/run_exness_bot.sh`)

```
Tum login Exness Web Terminal → Bot (exness_web_bot.py) Buy/Sell/Close buttons click karta hai
```

Apna khud ka strategy loop hai, Go engine se independent — **iska control gate
se koi connection nahi**, isliye risk/daily-loss limit ya stop-all iss path par
kaam nahi karta. Manually stop karna ho to process kill karo.

| Pros | Cons |
|------|------|
| Demo abhi chal sakta hai | UI change → bot toot sakta hai |
| Extra software nahi | Global control gate se disconnected |
| | PC + browser open rehna zaroori |

## Alternate — MetaTrader 5 Expert Advisor (`mt5/GoldAutoBot.mq5`)

```
Exness MT5 app install → GoldAutoBot.mq5 attach XAUUSD chart → bot MT5 ke andar trade karta hai
```

Sabse "official" path, lekin iska **daily loss limit ya external kill switch
nahi hai** — per-trade SL/TP aur max-positions cap hi hain. Isko band karne ka
tareeka MT5 terminal ka apna **AutoTrading toggle** hai (chart ke top par),
manual step — Go control gate se wired nahi hai.

| Pros | Cons |
|------|------|
| Official Exness path | MT5 install chahiye (Windows / Wine) |
| SL/TP reliable | Linux pe Wine setup |
| API ki zaroorat nahi | No daily-loss kill switch |

---

## Ab kya use karein?

1. **Primary** → `./scripts/run_auto.sh`, phir control gate explicitly enable karo (upar dekho).
2. **Sirf browser bot chahiye** → `./scripts/run_exness_bot.sh` (control gate se independent, apna kill switch khud hai — process kill).
3. **Stable 24/7, Windows/Wine setup ready hai** → MT5 EA install karo, AutoTrading toggle hi iska on/off hai.

**Paid third-party APIs** (MetaAPI etc.) bhi hain — paise lagenge, abhi zaroori nahi.
