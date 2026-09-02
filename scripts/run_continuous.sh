#!/usr/bin/env bash
# Continuous analysis + trading loop for XAUUSD demo
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs data

start_trader() {
  if curl -sf http://localhost:8080/health >/dev/null 2>&1; then
    echo "Go trader already running"
    return
  fi
  echo "Starting Go trader..."
  ./bin/trader --config config/config.yaml >>logs/trader.log 2>&1 &
  sleep 2
}

start_bridge() {
  if curl -sf http://127.0.0.1:8090/health >/dev/null 2>&1; then
    echo "Browser bridge already running"
    return
  fi
  echo "Starting browser bridge..."
  python3 strategy/browser_bridge.py --port 8090 >>logs/browser_bridge.log 2>&1 &
  sleep 1
}

echo "=== Continuous gold analysis + trading ==="
start_trader
start_bridge
curl -sf -X POST http://localhost:8080/api/v1/broker/browser/enable >/dev/null || true

# Align risk with Exness demo balance (clears phantom sim daily losses)
curl -sf -X POST http://localhost:8080/api/v1/risk/reset >/dev/null && echo "Risk daily limit reset"

echo "Starting price sync..."
python3 strategy/sync_exness.py --poll 3 >>logs/sync_exness.log 2>&1 &
SYNC_PID=$!

echo "Starting analysis logger (every 30s)..."
python3 strategy/analysis_logger.py >>logs/analysis_logger.log 2>&1 &
LOG_PID=$!

echo "Starting pro strategy (continuous)..."
trap 'kill $SYNC_PID $LOG_PID 2>/dev/null || true' EXIT
exec python3 strategy/gold_pro_strategy.py --poll 3 --warmup-polls 100 --duration 0 --mirror-browser \
  >>logs/gold_pro_strategy.log 2>&1
