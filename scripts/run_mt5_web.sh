#!/usr/bin/env bash
# EXPERIMENTAL / ALTERNATE PATH — a fourth execution surface (web.metatrader.app)
# with its own strategy loop, independent of the Go engine and the global
# trading control gate. The primary supported path is scripts/run_auto.sh.
# See docs/REMEDIATION_PLAN.md.
#
# MetaTrader Web Terminal bot helper
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs data
export MT5_WEB_URL="${MT5_WEB_URL:-https://web.metatrader.app/terminal?lang=en}"
# $30 MetaQuotes demo: XAUUSD 0.01 often fails margin — default FX pair
export MT5_SYMBOL="${MT5_SYMBOL:-AUDCAD}"
MODE="${1:---status}"
shift || true
exec python3 strategy/mt5_web_bot.py "$MODE" --symbol "$MT5_SYMBOL" "$@"
