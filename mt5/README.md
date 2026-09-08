# Exness MT5 Setup (chosen path — no REST API)

## Credentials you will give me

Send these **3 fields** (demo first):

| Field | Example | Where |
|-------|---------|--------|
| **Login** | `21000184446` | Personal Area → Accounts |
| **Password** | `********` | MT5 password (not email password) |
| **Server** | `Exness-MT5Trial7` | Same page — exact server string |

I will put them only in `config/credentials.yaml` (gitignored). Never commit.

## Recommended path on your PC: MT5 + EA

1. Download **Exness MetaTrader 5** from Personal Area (Windows, or Linux if offered)
2. Login with the demo login / password / server above
3. Open chart **XAUUSD** → timeframe **M5**
4. Copy `mt5/GoldAutoBot.mq5` into MT5 Experts folder:
   - Windows: `C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\<id>\MQL5\Experts\`
5. MetaEditor → Compile `GoldAutoBot`
6. Drag EA onto XAUUSD chart
7. Enable **Algo Trading** (toolbar)
8. Inputs: LotSize `0.01`, MaxPositions `1`

EA will: signal → buy/sell → SL/TP → auto exit. No browser, no Exness API.

## Optional path: Docker MT5 bridge (Linux)

Heavier (Wine). Use only if you want Go backend to place orders via HTTP.

```bash
# After credentials.yaml + docker/.env filled:
docker compose -f docker/docker-compose.yml --profile mt5 up -d
```

Then set `broker.account_id` / `api_token` in `config/config.yaml` and run Go trader.

## Safety

- Start on **Demo** only
- Lot `0.01` only until strategy is proven
- Never share credentials in public chats/repos
