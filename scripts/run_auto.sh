#!/usr/bin/env bash
# Auto trading: Go engine (risk/signals) + Python auto_trader.py mirroring
# accepted signals to the practice web terminal (see strategy/exness_executor.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs data

pkill -f "auto_trader.py" 2>/dev/null || true

if ! curl -sf http://localhost:8080/health >/dev/null 2>&1; then
  echo "Starting Go trader..."
  ./bin/trader --config config/config.yaml >>logs/trader.log 2>&1 &
  sleep 2
fi

if ! curl -sf http://127.0.0.1:8090/health >/dev/null 2>&1; then
  python3 strategy/browser_bridge.py --port 8090 >>logs/browser_bridge.log 2>&1 &
  sleep 1
fi

API_TOKEN="$(python3 -c "
import yaml
try:
    d = yaml.safe_load(open('config/config.yaml')) or {}
    print((d.get('server') or {}).get('api_token') or '')
except Exception:
    print('')
" 2>/dev/null || true)"
AUTH_HEADER=()
if [[ -n "$API_TOKEN" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer $API_TOKEN")
fi

curl -sf "${AUTH_HEADER[@]}" -X POST http://localhost:8080/api/v1/broker/browser/enable >/dev/null || true
curl -sf "${AUTH_HEADER[@]}" -X POST http://localhost:8080/api/v1/risk/reset >/dev/null 2>/dev/null || true

CONTROL_STATUS="$(curl -sf "${AUTH_HEADER[@]}" http://localhost:8080/api/v1/control/status 2>/dev/null || echo '{}')"
if ! echo "$CONTROL_STATUS" | grep -q '"enabled": *true'; then
  echo "=== Trading is DISABLED (safety default) ==="
  echo "The bot will analyze and log signals but will NOT place any order until you enable it:"
  echo "  curl -X POST ${AUTH_HEADER[*]} http://localhost:8080/api/v1/control/enable -d '{\"reason\":\"manual start\"}'"
  echo "Stop everything at any time:"
  echo "  curl -X POST ${AUTH_HEADER[*]} http://localhost:8080/api/v1/control/stop-all -d '{\"reason\":\"manual stop\"}'"
fi

echo "=== Auto trader (Go engine + practice-terminal mirror) ==="
echo "Mirrored trades land on whichever platform config/credentials.yaml is filled in for (see strategy/broker_login.py)."
exec python3 strategy/auto_trader.py --poll 10
