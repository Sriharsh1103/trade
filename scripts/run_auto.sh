#!/usr/bin/env bash
# Full auto trading — no browser approval needed
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs data

# Stop old strategy loops
pkill -f "gold_pro_strategy.py" 2>/dev/null || true
pkill -f "gold_trader.py" 2>/dev/null || true

# Go trader
if ! curl -sf http://localhost:8080/health >/dev/null 2>&1; then
  echo "Starting Go trader..."
  ./bin/trader --config config/config.yaml >>logs/trader.log 2>&1 &
  sleep 2
fi

# Browser bridge (price relay only)
if ! curl -sf http://127.0.0.1:8090/health >/dev/null 2>&1; then
  python3 strategy/browser_bridge.py --port 8090 >>logs/browser_bridge.log 2>&1 &
  sleep 1
fi

pip3 install -q yfinance 2>/dev/null || true

echo "=== Auto trader: analysis + buy/sell/exit (local API, no browser clicks) ==="
exec python3 strategy/auto_trader.py --poll 5
