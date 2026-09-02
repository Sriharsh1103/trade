#!/usr/bin/env python3
"""Push live Exness quotes from browser bridge into Go demo engine.

Usage:
  # Poll bridge and sync to Go API every 3s:
  python sync_exness.py --poll 3

  # One-shot manual sync:
  python sync_exness.py --bid 4324.5 --ask 4324.76 --balance 28.43
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync_exness")

DEFAULT_API = "http://localhost:8080"
DEFAULT_BRIDGE = "http://127.0.0.1:8090"
SYMBOL = "XAUUSD"


def http_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch_bridge(symbol: str, bridge_url: str) -> dict:
    quote = http_json("GET", f"{bridge_url}/api/v1/quote/{symbol}")
    account = http_json("GET", f"{bridge_url}/api/v1/account")
    return {"quote": quote, "account": account}


def push_to_go(api_url: str, symbol: str, bid: float, ask: float, balance: float, equity: float) -> dict:
    payload = {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "balance": balance,
        "equity": equity,
    }
    return http_json("POST", f"{api_url}/api/v1/broker/browser/sync", payload)


def sync_once(
    api_url: str,
    bridge_url: str,
    symbol: str,
    bid: float | None,
    ask: float | None,
    balance: float | None,
    equity: float | None,
) -> dict:
    if bid is None or ask is None:
        data = fetch_bridge(symbol, bridge_url)
        quote = data["quote"]
        account = data["account"]
        bid = float(quote["bid"])
        ask = float(quote["ask"])
        balance = float(account.get("balance", 0))
        equity = float(account.get("equity", balance))

    result = push_to_go(api_url, symbol, bid, ask, balance or 0, equity or balance or 0)
    log.info("synced %s bid=%.3f ask=%.3f balance=%.2f", symbol, bid, ask, balance or 0)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Exness prices into Go demo engine")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE)
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--bid", type=float)
    parser.add_argument("--ask", type=float)
    parser.add_argument("--balance", type=float)
    parser.add_argument("--equity", type=float)
    parser.add_argument("--poll", type=float, default=0, help="Poll interval seconds (0 = once)")
    args = parser.parse_args()

    try:
        if args.poll > 0:
            log.info("Polling bridge every %.1fs → Go API", args.poll)
            while True:
                try:
                    sync_once(
                        args.api_url,
                        args.bridge_url,
                        args.symbol,
                        args.bid,
                        args.ask,
                        args.balance,
                        args.equity,
                    )
                except urllib.error.URLError as exc:
                    log.warning("sync failed: %s", exc.reason)
                time.sleep(args.poll)
        else:
            sync_once(
                args.api_url,
                args.bridge_url,
                args.symbol,
                args.bid,
                args.ask,
                args.balance,
                args.equity,
            )
    except KeyboardInterrupt:
        log.info("Stopped")
    except urllib.error.URLError as exc:
        log.error("Failed: %s", exc.reason)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
