#!/usr/bin/env python3
"""HTTP bridge between Go trading core and Exness web terminal automation.

Run alongside the Go trader when using browser-based execution:
  python browser_bridge.py --port 8090

When Playwright is installed and EXNESS_BROWSER_URL is set, the bridge can
place orders on the logged-in Exness web terminal. Otherwise it operates in
relay mode: accepts price/account sync from Cursor browser MCP or manual updates.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("browser_bridge")

DEFAULT_PORT = int(os.environ.get("BROWSER_BRIDGE_PORT", "8090"))
EXNESS_URL = os.environ.get("EXNESS_BROWSER_URL", "https://my.exness.com/webtrading/")


class BrowserState:
    """Thread-safe cache of Exness web terminal state."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.enabled = False
        self.balance = 30.0
        self.equity = 30.0
        self.symbol = "XAUUSD"
        self.bid = 4308.0
        self.ask = 4308.26
        self.positions: list[dict[str, Any]] = []
        self.trade_log: list[dict[str, Any]] = []
        self.last_sync = 0.0
        self.playwright_ready = False

    def sync_quote(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.symbol = data.get("symbol", self.symbol)
            if "bid" in data:
                self.bid = float(data["bid"])
            if "ask" in data:
                self.ask = float(data["ask"])
            if "balance" in data:
                self.balance = float(data["balance"])
            if "equity" in data:
                self.equity = float(data["equity"])
            self.last_sync = time.time()

    def account(self) -> dict[str, Any]:
        with self._lock:
            margin = sum(p.get("margin", 0) for p in self.positions)
            equity = self.equity
            free = equity - margin
            level = (equity / margin * 100) if margin > 0 else 0
            return {
                "balance": self.balance,
                "equity": equity,
                "margin": margin,
                "free_margin": free,
                "margin_level": level,
                "leverage": 100,
                "currency": "USD",
            }

    def quote(self, symbol: str) -> dict[str, Any]:
        with self._lock:
            return {
                "symbol": symbol or self.symbol,
                "bid": self.bid,
                "ask": self.ask,
                "spread": self.ask - self.bid,
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    def log_trade(self, trade: dict[str, Any]) -> None:
        with self._lock:
            trade["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.trade_log.append(trade)


STATE = BrowserState()


def try_playwright_order(side: str, volume: float, sl: float, tp: float) -> dict[str, Any]:
    """Attempt order via Playwright if available."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return {"status": "relay", "message": "Playwright not installed — order queued for MCP relay"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(os.environ.get("PLAYWRIGHT_CDP_URL", "http://127.0.0.1:9222"))
            page = browser.contexts[0].pages[0] if browser.contexts and browser.contexts[0].pages else None
            if page is None:
                page = browser.new_page()
                page.goto(EXNESS_URL)

            # Exness web terminal selectors (may need updates if UI changes)
            page.get_by_role("textbox", name="Volume").fill(str(volume))
            if sl > 0:
                page.get_by_role("textbox", name="Stop Loss").fill(f"{sl:.3f}")
            if tp > 0:
                page.get_by_role("textbox", name="Take Profit").fill(f"{tp:.3f}")

            label = "Buy" if side == "buy" else "Sell"
            page.get_by_role("button", name=label, exact=False).click()
            return {"status": "submitted", "side": side, "volume": volume, "sl": sl, "tp": tp}
    except Exception as exc:
        log.warning("Playwright order failed: %s", exc)
        return {"status": "relay", "message": str(exc)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug(fmt, *args)

    def _json(self, status: int, body: dict[str, Any] | list[Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wwrite(data)

    def wwrite(self, data: bytes) -> None:
        self.wfile.write(data)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/health":
            self._json(200, {"status": "ok", "enabled": STATE.enabled, "playwright": STATE.playwright_ready})
        elif path == "/api/v1/account":
            self._json(200, STATE.account())
        elif path.startswith("/api/v1/quote/"):
            symbol = path.rsplit("/", 1)[-1]
            self._json(200, STATE.quote(symbol))
        elif path == "/api/v1/positions":
            self._json(200, STATE.positions)
        elif path == "/api/v1/status":
            self._json(200, {
                "enabled": STATE.enabled,
                "symbol": STATE.symbol,
                "last_sync": STATE.last_sync,
                "trade_count": len(STATE.trade_log),
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/v1/browser/enable":
            STATE.enabled = True
            self._json(200, {"status": "enabled"})
        elif path == "/api/v1/sync":
            STATE.sync_quote(body)
            self._json(200, {"status": "synced", "quote": STATE.quote(STATE.symbol)})
        elif path == "/api/v1/orders":
            if not STATE.enabled:
                self._json(400, {"error": "browser bridge not enabled"})
                return
            side = body.get("side", "buy")
            volume = float(body.get("volume", 0.01))
            sl = float(body.get("stop_loss", 0))
            tp = float(body.get("take_profit", 0))
            result = try_playwright_order(side, volume, sl, tp)
            STATE.log_trade({"side": side, "volume": volume, "sl": sl, "tp": tp, **result})
            self._json(201, result)
        else:
            self._json(404, {"error": "not found"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Exness browser automation HTTP bridge")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    log.info("Browser bridge listening on http://%s:%d", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
