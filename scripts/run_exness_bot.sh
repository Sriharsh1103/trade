#!/usr/bin/env bash
# ALTERNATE PATH — pure browser automation with its own strategy loop
# (exness_web_bot.py --loop), independent of the Go engine, the risk manager,
# and the global trading control gate (POST /api/v1/control/enable|disable
# has no effect here). The primary supported path is scripts/run_auto.sh.
# See docs/REMEDIATION_PLAN.md.
#
# Exness Web Terminal bot — no API
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs data

pip3 install --break-system-packages -q playwright 2>/dev/null || true
python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null || {
  echo "Installing Playwright browsers..."
  playwright install chromium 2>/dev/null || python3 -m playwright install chromium
}

MODE="${1:---status}"
shift || true

echo "=== Exness Web Bot ==="
echo "Keep https://my.exness.com/webtrading/ logged in (or log in when Chromium opens)"
echo ""

case "$MODE" in
  --status|--close-all|--buy|--sell|--loop)
    exec python3 strategy/exness_web_bot.py "$MODE" "$@"
    ;;
  *)
    echo "Usage: $0 --status | --close-all | --buy | --sell | --loop"
    exit 1
    ;;
esac
