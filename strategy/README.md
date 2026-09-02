# Strategy & ML Pipeline

Python service for signal generation, backtesting, and model training. Communicates with the Go trading core via HTTP API.

## Phase 2 Workflow

```
Historical Data → Feature Engineering → Train Model → Backtest → Paper Trade → Live (strict limits)
```

## Quick Start

```bash
cd strategy
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate a demo signal (requires Go trader running on :8080)
python signals.py --symbol EURUSD --action buy
```

## Components

| File | Purpose |
|------|---------|
| `signals.py` | Send buy/sell/hold signals to Go API |
| `train.py` | Model training pipeline (placeholder) |
| `collect_data.py` | Export demo trade logs for training |

See [docs/ML_PIPELINE.md](../docs/ML_PIPELINE.md) for the full plan.

## API Integration

The Go core exposes:

```
POST /api/v1/signals   {"symbol": "EURUSD", "action": "buy", "confidence": 0.75}
GET  /api/v1/account
GET  /api/v1/positions
GET  /api/v1/risk/status
```

All signals pass through the risk manager before execution.
