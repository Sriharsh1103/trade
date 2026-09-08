#!/usr/bin/env bash
# DEPRECATED — superseded by scripts/run_auto.sh, which uses this same
# Bollinger+RSI strategy (gold_pro_strategy.py) but through auto_trader.py's
# unified regime-detection loop and the global trading control gate. Kept
# for reference/manual backtesting. See docs/REMEDIATION_PLAN.md.
#
# Start Bollinger+RSI pro gold strategy (demo)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! curl -sf http://localhost:8080/health >/dev/null 2>&1; then
  echo "Starting Go trader..."
  "$ROOT/bin/trader" --config "$ROOT/config/config.yaml" &
  sleep 2
fi

if ! curl -sf http://127.0.0.1:8090/health >/dev/null 2>&1; then
  echo "Starting browser bridge (optional)..."
  python3 "$ROOT/strategy/browser_bridge.py" --port 8090 &
  sleep 1
fi

echo "Starting price sync (bridge → Go demo engine)..."
python3 "$ROOT/strategy/sync_exness.py" --poll 3 &
SYNC_PID=$!
sleep 1

echo "Starting gold pro strategy (Bollinger+RSI)..."
cd "$ROOT/strategy"
trap 'kill $SYNC_PID 2>/dev/null || true' EXIT
exec python3 gold_pro_strategy.py --poll 3 --warmup-polls 100 "$@"
