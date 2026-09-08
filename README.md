# Forex Trading System

Automated forex trading foundation targeting Exness (MetaTrader 5) with self-managed risk controls, demo-first workflow, and a planned ML strategy pipeline.

## Status: Phase 1 Foundation

This repository contains architecture, documentation, and a **Go backend scaffold**. No live trading or browser login is performed until credentials are provided.

## Quick Start

```bash
# Copy and edit config (no credentials committed)
cp config/config.example.yaml config/config.yaml
# Set server.api_token in config.yaml — required for the API to accept requests
# once you bind it beyond 127.0.0.1. Generate one:
python3 -c "import secrets; print(secrets.token_hex(24))"

# Build backend
cd backend && go build -o ../bin/trader ./cmd/trader

# Run in demo mode
./bin/trader --config ../config/config.yaml
```

Trading is **disabled by default** — a global control gate blocks every
order-placing path until you explicitly enable it:

```bash
curl -X POST -H "Authorization: Bearer <server.api_token>" \
  http://localhost:8080/api/v1/control/enable -d '{"reason":"manual start"}'

# Stop everything at any time (disables + closes all open positions):
curl -X POST -H "Authorization: Bearer <server.api_token>" \
  http://localhost:8080/api/v1/control/stop-all -d '{"reason":"manual stop"}'
```

See `docs/ARCHITECTURE.md#trading-control-gate` for details, and
`docs/REMEDIATION_PLAN.md` for the full list of issues found and fixed in
this pass.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Strategy (Py)   │────▶│ Go Trading Core  │────▶│ MT5 Bridge      │
│ ML / signals    │     │ Risk + Orders    │     │ (Docker/Wine)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │                          │
                               ▼                          ▼
                        ┌──────────────┐          ┌──────────────┐
                        │ Demo Engine  │          │ Exness MT5   │
                        │ (simulated)  │          │ Terminal     │
                        └──────────────┘          └──────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full design.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/FOREX_MECHANICS.md](docs/FOREX_MECHANICS.md) | How forex/Exness trading works |
| [docs/BACKEND_COMPARISON.md](docs/BACKEND_COMPARISON.md) | Rust vs Node vs Go analysis |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and phases |
| [docs/ML_PIPELINE.md](docs/ML_PIPELINE.md) | ML strategy pipeline (Phase 2) |
| [strategy/README.md](strategy/README.md) | Python signal client |

## Phases

### Phase 1 (Current)
- [x] Codebase analysis (empty repo → initialized)
- [x] Architecture and forex mechanics documentation
- [x] Go backend scaffold with risk module
- [x] Demo trading mode (simulated fills)
- [ ] Connect MT5 bridge when credentials provided

### Phase 2 (Next)
- Demo trading with small amounts via Exness demo account
- Historical data collection for model training
- Strategy backtesting and paper trading
- Model training pipeline (Python)

## Risk Controls

Default configuration targets **~10% profit per trade** with strict loss limits:

- Per-trade take-profit at configurable target (default 10% of position margin)
- Stop-loss capped at configurable max loss (default 2% of account equity)
- Auto-exit when adverse price movement exceeds threshold
- Daily loss limit and max open positions
- Margin level monitoring with forced close before stop-out

**Important:** 10% per trade is an aggressive target. See caveats in docs.

## Technology Choice

**Go** for the trading backend — see [docs/BACKEND_COMPARISON.md](docs/BACKEND_COMPARISON.md).

- Retail forex latency is broker-bound (~50–200ms), not language-bound
- Go provides strong concurrency for position monitoring
- Single binary deployment alongside MT5 Docker container
- Python strategy service integrates via HTTP/gRPC

## License

Private — not for redistribution.
