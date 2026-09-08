#!/usr/bin/env bash
# DEPRECATED — an earlier momentum strategy, superseded by scripts/run_auto.sh.
# Not connected to the global trading control gate. Kept for reference. See
# docs/REMEDIATION_PLAN.md.
#
# Start continuous gold demo trading loop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure Go trader is running
if ! curl -sf http://localhost:8080/health >/dev/null 2>&1; then
  echo "Starting Go trader..."
  "$ROOT/bin/trader" --config "$ROOT/config/config.yaml" &
  sleep 1
fi

# Ensure browser bridge is running (optional, for Exness web mirror)
if ! curl -sf http://127.0.0.1:8090/health >/dev/null 2>&1; then
  echo "Starting browser bridge..."
  python3 "$ROOT/strategy/browser_bridge.py" --port 8090 &
  sleep 1
fi

echo "Starting gold momentum trader (Ctrl+C to stop)..."
cd "$ROOT/strategy"
exec python3 gold_trader.py --poll 5 --threshold 0.08 "$@"
