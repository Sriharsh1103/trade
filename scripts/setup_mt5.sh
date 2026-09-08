#!/usr/bin/env bash
# Prepare MT5 connection for Exness (no public REST API — use MT5)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Exness MT5 Setup ==="
echo ""

# 1) Credentials file
if [[ ! -f config/credentials.yaml ]]; then
  cp config/credentials.example.yaml config/credentials.yaml
  echo "Created config/credentials.yaml — FILL IN login / password / server"
  echo "  OR paste them here when I ask (I will write the file)."
else
  echo "Found config/credentials.yaml"
fi

# 2) Docker env
if [[ ! -f docker/.env ]]; then
  cp docker/.env.example docker/.env
  echo "Created docker/.env"
fi

# 3) Gold-focused trading config if missing
if [[ ! -f config/config.yaml ]]; then
  cp config/config.example.yaml config/config.yaml
fi

# Ensure XAUUSD defaults in example sense (user config may already exist)
echo ""
echo "What I need from you (Exness DEMO):"
echo "  1) Account login number   (e.g. 21000184446)"
echo "  2) Password               (MT5 trading password)"
echo "  3) Server name            (e.g. Exness-MT5Trial7)"
echo ""
echo "Where to find:"
echo "  Exness Personal Area → Trading → Accounts → open Demo → MT5 details"
echo ""
echo "Two ways after credentials:"
echo "  A) MT5 EA (recommended): install Exness MT5 → attach mt5/GoldAutoBot.mq5"
echo "  B) Docker MT5 bridge:     docker compose -f docker/docker-compose.yml up -d"
echo ""
echo "Docs: mt5/README.md  |  docs/NO_API_OPTIONS.md"
