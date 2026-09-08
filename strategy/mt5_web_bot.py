#!/usr/bin/env python3
"""MetaTrader Web Terminal bot (web.metatrader.app) — browser automation.

Works with MetaQuotes-Demo or broker web MT5 when logged in.
Uses Playwright persistent profile OR CDP attach.

Usage:
  python mt5_web_bot.py --status
  python mt5_web_bot.py --buy
  python mt5_web_bot.py --sell
  python mt5_web_bot.py --close-all
  python mt5_web_bot.py --loop
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [mt5_web] %(message)s")
log = logging.getLogger("mt5_web")

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "mt5_web_profile"
LOG_FILE = ROOT / "data" / "mt5_web_trades.jsonl"
DEFAULT_URL = "https://web.metatrader.app/terminal?lang=en"
VOLUME = "0.01"
# For XAUUSD / gold-like; for FX pairs offsets are smaller — auto-detect below
SL_GOLD = 0.80
TP_GOLD = 0.40
SL_FX = 0.0015
TP_FX = 0.0010


def log_trade(event: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    event["time"] = datetime.now(timezone.utc).isoformat()
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(event) + "\n")


def connect():
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    cdp = os.environ.get("PLAYWRIGHT_CDP_URL", "").strip()
    url = os.environ.get("MT5_WEB_URL", DEFAULT_URL)
    if cdp:
        browser = p.chromium.connect_over_cdp(cdp)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = next((pg for pg in ctx.pages if "metatrader" in (pg.url or "") or "exness" in (pg.url or "")), None)
        if page is None:
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded")
        return p, browser, page, False

    PROFILE.mkdir(parents=True, exist_ok=True)
    browser = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=False,
        viewport={"width": 1400, "height": 900},
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    if "metatrader" not in (page.url or ""):
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)
    return p, browser, page, True


def wait_terminal(page, timeout=90000) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout)
    time.sleep(2)


def offsets_for_symbol(symbol: str) -> tuple[float, float]:
    s = symbol.upper()
    if "XAU" in s or "GOLD" in s:
        return SL_GOLD, TP_GOLD
    return SL_FX, TP_FX


def try_select_symbol(page, symbol: str = "XAUUSD") -> None:
    """Best-effort symbol search in web terminal."""
    for sel in (
        'input[placeholder*="Search"]',
        'input[placeholder*="Symbol"]',
        'input[type="search"]',
        '[data-testid="symbol-search"]',
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.click(timeout=2000)
                loc.fill(symbol)
                time.sleep(0.5)
                page.keyboard.press("Enter")
                time.sleep(1)
                return
        except Exception:
            continue
    # Click Market Watch row if visible
    try:
        page.get_by_text(symbol, exact=True).first.click(timeout=3000)
    except Exception:
        log.warning("Could not auto-select %s — select manually in Market Watch", symbol)


def place_order(page, side: str, symbol: str = "AUDCAD") -> dict:
    wait_terminal(page)
    try_select_symbol(page, symbol)
    sl_off, tp_off = offsets_for_symbol(symbol)

    # Open New Order dialog — common web MT5 patterns
    opened = False
    for name in ("New Order", "Order", "Trade"):
        btn = page.get_by_role("button", name=re.compile(name, re.I))
        if btn.count() > 0:
            try:
                btn.first.click(timeout=3000)
                opened = True
                break
            except Exception:
                pass
    if not opened:
        page.keyboard.press("F9")  # classic MT5 new order
        time.sleep(1)

    time.sleep(0.8)
    # Volume
    for label in ("Volume", "Lots", "Lot"):
        tb = page.get_by_role("textbox", name=re.compile(label, re.I))
        if tb.count() > 0:
            tb.first.fill(VOLUME)
            break
        spin = page.locator(f'input[name*="{label.lower()}" i], input[aria-label*="{label}" i]')
        if spin.count() > 0:
            spin.first.fill(VOLUME)
            break

    # Side + submit
    if side == "buy":
        targets = ("Buy by Market", "Buy", "BUY")
    else:
        targets = ("Sell by Market", "Sell", "SELL")

    clicked = False
    for name in targets:
        b = page.get_by_role("button", name=re.compile(rf"^{re.escape(name)}$", re.I))
        if b.count() == 0:
            b = page.get_by_role("button", name=re.compile(name, re.I))
        if b.count() > 0:
            try:
                b.first.click(timeout=3000)
                clicked = True
                break
            except Exception:
                continue
    if not clicked:
        # Overlay often intercepts Playwright clicks — force via DOM
        js_side = "Buy by Market" if side == "buy" else "Sell by Market"
        clicked = bool(
            page.evaluate(
                """(label) => {
                  const b = [...document.querySelectorAll('button')]
                    .find(el => (el.textContent || '').trim() === label);
                  if (!b) return false;
                  b.click();
                  return true;
                }""",
                js_side,
            )
        )

    result = {"action": side, "symbol": symbol, "volume": VOLUME, "clicked": clicked}
    log_trade(result)
    if not clicked:
        raise RuntimeError("Could not find Buy/Sell button — UI may differ; use Cursor browser control")
    log.info("Order submitted: %s %s %s", side, VOLUME, symbol)
    time.sleep(1.5)
    return result


def close_all(page) -> bool:
    wait_terminal(page)
    # Trade tab → right click / Close All
    for name in ("Close All", "Close all", "Close"):
        b = page.get_by_role("button", name=re.compile(name, re.I))
        if b.count() > 0:
            try:
                b.first.click(timeout=3000)
                time.sleep(0.5)
                for conf in ("OK", "Yes", "Confirm"):
                    c = page.get_by_role("button", name=re.compile(conf, re.I))
                    if c.count() > 0:
                        c.first.click(timeout=2000)
                        break
                log_trade({"action": "close_all"})
                log.info("Close all clicked")
                return True
            except Exception:
                continue
    # Keyboard shortcut sometimes works in web
    try:
        page.get_by_text(re.compile(r"Trade|Positions", re.I)).first.click(timeout=2000)
    except Exception:
        pass
    log.warning("Close all not found automatically")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--buy", action="store_true")
    parser.add_argument("--sell", action="store_true")
    parser.add_argument("--close-all", action="store_true")
    parser.add_argument("--symbol", default=os.environ.get("MT5_SYMBOL", "AUDCAD"))
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--poll", type=float, default=45.0)
    args = parser.parse_args()

    pw, browser, page, owned = connect()
    try:
        wait_terminal(page)
        log.info("URL=%s", page.url)
        if args.close_all:
            close_all(page)
        elif args.buy:
            place_order(page, "buy", args.symbol)
        elif args.sell:
            place_order(page, "sell", args.symbol)
        elif args.loop:
            while True:
                try:
                    place_order(page, "buy", args.symbol)
                    time.sleep(args.poll)
                    close_all(page)
                    time.sleep(args.poll)
                except KeyboardInterrupt:
                    break
                except Exception as exc:
                    log.warning("%s", exc)
                    time.sleep(10)
        else:
            print(json.dumps({"url": page.url, "title": page.title()}, indent=2))
        return 0
    finally:
        if owned:
            browser.close()
        pw.stop()


if __name__ == "__main__":
    raise SystemExit(main())
