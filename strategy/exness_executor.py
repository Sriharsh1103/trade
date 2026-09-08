#!/usr/bin/env python3
"""Places a mirrored order on the practice web terminal via Playwright.

Called in-process from auto_trader.py right after the Go engine accepts a
signal — there is no queue/poll step. (An earlier version wrote orders to
data/exness_order_queue.jsonl for a separate `exness_executor.py --poll`
process to pick up, but nothing launched that process, so mirrored orders
were silently never placed. Direct in-process calls remove that failure mode
entirely.)

Every call re-checks the Go control gate (GET /api/v1/control/status) so this
mirror path can never place an order while trading is globally disabled, even
if it's invoked from somewhere other than auto_trader.py's own gate check.

Usage (manual one-off test):
  python exness_executor.py --test buy
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.error
from pathlib import Path

import broker_login

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [exness] %(message)s")
log = logging.getLogger("exness_executor")

DONE_LOG = Path(__file__).resolve().parent.parent / "data" / "exness_orders_done.jsonl"
API_URL = os.environ.get("TRADER_API_URL", "http://localhost:8080")


class TradingDisabled(RuntimeError):
    pass


def _control_enabled() -> tuple[bool, str]:
    from gold_pro_strategy import http_json

    try:
        status = http_json("GET", f"{API_URL}/api/v1/control/status")
    except urllib.error.URLError as exc:
        # Go API unreachable — fail closed, don't place a real order blind.
        return False, f"control status unreachable: {exc}"
    if not isinstance(status, dict):
        return False, "control status: unexpected response"
    return bool(status.get("enabled")), str(status.get("reason", ""))


def place_order_playwright(side: str, volume: float, sl: float, tp: float) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        cdp = os.environ.get("PLAYWRIGHT_CDP_URL", "http://127.0.0.1:9222")
        try:
            browser = p.chromium.connect_over_cdp(cdp)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = next((pg for pg in ctx.pages if "exness.com" in pg.url or "metatrader" in pg.url), None)
            if page is None:
                page = ctx.new_page()
                target = broker_login.target_platform()
                page.goto(target[1] if target else broker_login.EXNESS_URL, wait_until="domcontentloaded")
                time.sleep(3)
        except Exception:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            target = broker_login.target_platform()
            page.goto(target[1] if target else broker_login.EXNESS_URL, wait_until="domcontentloaded")
            time.sleep(2)

        if not broker_login.ensure_logged_in(page):
            return {"status": "error", "message": "Not logged in — log in manually in the opened browser, then retry"}

        page.get_by_role("textbox", name="Volume").fill(str(volume))
        if sl > 0:
            page.get_by_role("textbox", name="Stop Loss").fill(f"{sl:.2f}")
        if tp > 0:
            page.get_by_role("textbox", name="Take Profit").fill(f"{tp:.2f}")

        label = "Buy" if side == "buy" else "Sell"
        page.get_by_role("button", name=label).first.click()
        time.sleep(0.5)

        confirm = page.get_by_role("button", name=f"Confirm {label}")
        if confirm.count() > 0 and confirm.is_enabled():
            confirm.click()
            time.sleep(1)
            return {"status": "filled", "side": side, "volume": volume, "sl": sl, "tp": tp}

        # One-click buy/sell without confirm dialog
        if page.get_by_role("tab", name="Open").count() > 0:
            return {"status": "submitted", "side": side, "volume": volume}
        return {"status": "pending", "side": side}


def _log_done(order: dict, result: dict) -> None:
    DONE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DONE_LOG.open("a") as f:
        f.write(json.dumps({**order, "result": result}) + "\n")


def mirror_order(side: str, sl: float, tp: float, volume: float = 0.01, source: str = "auto") -> dict:
    """Place a mirrored order now. Raises TradingDisabled if the gate is off."""
    import uuid

    enabled, reason = _control_enabled()
    if not enabled:
        raise TradingDisabled(reason or "trading disabled")

    order = {
        "id": str(uuid.uuid4()),
        "side": side,
        "volume": volume,
        "stop_loss": sl,
        "take_profit": tp,
        "source": source,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        result = place_order_playwright(side, volume, sl, tp)
    except Exception as exc:
        result = {"status": "error", "message": f"Playwright failed: {exc}"}
    log.info("Mirror order %s: %s", order["id"], result)
    _log_done(order, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", choices=["buy", "sell"], help="Place a single test order and exit")
    parser.add_argument("--volume", type=float, default=0.01)
    parser.add_argument("--sl", type=float, default=0.0)
    parser.add_argument("--tp", type=float, default=0.0)
    args = parser.parse_args()

    if not args.test:
        parser.print_help()
        return 1

    try:
        result = mirror_order(args.test, args.sl, args.tp, args.volume, source="manual_test")
    except TradingDisabled as exc:
        log.error("Trading is disabled: %s — enable it first: POST /api/v1/control/enable", exc)
        return 1
    log.info("Result: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
