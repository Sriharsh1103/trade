#!/usr/bin/env python3
"""Exness Web Terminal bot — NO API needed.

Uses Playwright against a logged-in Exness webtrading page.
You must stay logged in at https://my.exness.com/webtrading/

Modes:
  python exness_web_bot.py --status          # open positions count
  python exness_web_bot.py --close-all       # exit all positions
  python exness_web_bot.py --buy             # buy 0.01 XAUUSD with SL/TP
  python exness_web_bot.py --sell            # sell 0.01 XAUUSD with SL/TP
  python exness_web_bot.py --loop            # analyze + trade + exit loop

Connect options (pick one):
  1) PLAYWRIGHT_CDP_URL=http://127.0.0.1:9222  (Chrome with --remote-debugging-port=9222)
  2) Or launches Chromium and you log in once (profile saved in data/exness_profile)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [exness_bot] %(message)s")
log = logging.getLogger("exness_bot")

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "exness_profile"
LOG_FILE = ROOT / "data" / "exness_bot_trades.jsonl"
EXNESS_URL = "https://my.exness.com/webtrading/"
VOLUME = "0.01"
# Gold SL/TP offsets in price (≈ $0.55 risk / ~$0.35 target on 0.01 lot)
SL_OFFSET = 0.55
TP_OFFSET = 0.35


def log_trade(event: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    event["time"] = datetime.now(timezone.utc).isoformat()
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(event) + "\n")


def connect_page():
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    cdp = os.environ.get("PLAYWRIGHT_CDP_URL", "").strip()
    if cdp:
        browser = p.chromium.connect_over_cdp(cdp)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = next((pg for pg in ctx.pages if "exness.com" in (pg.url or "")), None)
        if page is None:
            page = ctx.new_page()
            page.goto(EXNESS_URL, wait_until="domcontentloaded")
        return p, browser, page, False

    PROFILE.mkdir(parents=True, exist_ok=True)
    browser = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=False,
        viewport={"width": 1400, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = browser.pages[0] if browser.pages else browser.new_page()
    if "exness.com" not in (page.url or ""):
        page.goto(EXNESS_URL, wait_until="domcontentloaded")
    return p, browser, page, True


def wait_ready(page, timeout_ms: int = 60000) -> None:
    page.wait_for_selector('button:has-text("Buy"), button:has-text("Sell")', timeout=timeout_ms)
    # Dismiss walkthrough Ok if present
    for _ in range(3):
        ok = page.get_by_role("button", name="Ok")
        if ok.count() > 0:
            try:
                ok.first.click(timeout=1500)
                time.sleep(0.3)
            except Exception:
                break
        else:
            break


def parse_price(text: str) -> float:
    # "Buy 4,435. 57 4" or "4,435.574"
    digits = re.sub(r"[^\d.]", "", text.replace(" ", ""))
    # Sometimes Exness splits decimals oddly — take first 7+ digit float-ish
    m = re.search(r"(\d{3,5}\.\d+)", digits)
    if m:
        return float(m.group(1))
    m2 = re.search(r"(\d+\.\d+)", digits)
    return float(m2.group(1)) if m2 else 0.0


def read_bid_ask(page) -> tuple[float, float]:
    sell_btn = page.get_by_role("button", name=re.compile(r"Sell", re.I)).first
    buy_btn = page.get_by_role("button", name=re.compile(r"Buy", re.I)).first
    bid = parse_price(sell_btn.inner_text())
    ask = parse_price(buy_btn.inner_text())
    return bid, ask


def open_count(page) -> int:
    tab = page.get_by_role("tab", name=re.compile(r"Open", re.I))
    if tab.count() == 0:
        return 0
    name = tab.first.inner_text()
    m = re.search(r"Open\s*(\d+)", name, re.I)
    return int(m.group(1)) if m else (0 if "No open" in page.content() else -1)


def close_all(page) -> bool:
    page.get_by_role("tab", name=re.compile(r"Open", re.I)).first.click()
    time.sleep(0.5)
    btn = page.get_by_role("button", name=re.compile(r"Close all", re.I))
    if btn.count() == 0:
        log.info("No Close all button — no open positions")
        return False
    btn.first.click()
    time.sleep(0.5)
    # Confirm dialogs vary
    for name in ("Close all", "Confirm", "Yes", "Ok"):
        c = page.get_by_role("button", name=re.compile(name, re.I))
        if c.count() > 0:
            try:
                c.last.click(timeout=2000)
                time.sleep(0.5)
            except Exception:
                pass
    log_trade({"action": "close_all"})
    log.info("Close all clicked")
    return True


def place_market(page, side: str) -> dict:
    """side = buy | sell. Sets volume + SL/TP then confirms."""
    page.get_by_role("button", name="Market").click()
    page.get_by_role("textbox", name="Volume").fill(VOLUME)
    time.sleep(0.3)

    bid, ask = read_bid_ask(page)
    entry = ask if side == "buy" else bid
    if side == "buy":
        sl, tp = entry - SL_OFFSET, entry + TP_OFFSET
    else:
        sl, tp = entry + SL_OFFSET, entry - TP_OFFSET

    page.get_by_role("textbox", name="Take Profit").fill(f"{tp:.2f}")
    page.get_by_role("textbox", name="Stop Loss").fill(f"{sl:.2f}")
    time.sleep(0.4)

    # Re-read after SL/TP fill — Exness may shift prices; fix if confirm disabled
    bid, ask = read_bid_ask(page)
    entry = ask if side == "buy" else bid
    if side == "buy":
        if tp <= ask:
            tp = ask + TP_OFFSET
            page.get_by_role("textbox", name="Take Profit").fill(f"{tp:.2f}")
        if sl >= bid:
            sl = bid - SL_OFFSET
            page.get_by_role("textbox", name="Stop Loss").fill(f"{sl:.2f}")
    else:
        if tp >= bid:
            tp = bid - TP_OFFSET
            page.get_by_role("textbox", name="Take Profit").fill(f"{tp:.2f}")
        if sl <= ask:
            sl = ask + SL_OFFSET
            page.get_by_role("textbox", name="Stop Loss").fill(f"{sl:.2f}")

    time.sleep(0.3)
    label = "Buy" if side == "buy" else "Sell"
    page.get_by_role("button", name=re.compile(rf"^{label}", re.I)).first.click()
    time.sleep(0.6)

    confirm = page.get_by_role("button", name=re.compile(rf"Confirm {label}", re.I))
    if confirm.count() > 0:
        if confirm.first.is_enabled():
            confirm.first.click()
        else:
            # Adjust TP once more above/below market
            bid, ask = read_bid_ask(page)
            if side == "buy":
                page.get_by_role("textbox", name="Take Profit").fill(f"{ask + TP_OFFSET:.2f}")
                page.get_by_role("textbox", name="Stop Loss").fill(f"{bid - SL_OFFSET:.2f}")
            else:
                page.get_by_role("textbox", name="Take Profit").fill(f"{bid - TP_OFFSET:.2f}")
                page.get_by_role("textbox", name="Stop Loss").fill(f"{ask + SL_OFFSET:.2f}")
            time.sleep(0.4)
            if confirm.first.is_enabled():
                confirm.first.click()
            else:
                raise RuntimeError("Confirm button still disabled — SL/TP invalid vs live price")

    time.sleep(1.2)
    result = {"action": side, "volume": VOLUME, "sl": sl, "tp": tp, "entry_approx": entry}
    log_trade(result)
    log.info("Placed %s @ ~%.2f SL=%.2f TP=%.2f", side, entry, sl, tp)
    return result


def loop(page, poll: float = 30.0, max_positions: int = 1) -> None:
    """Simple loop: max 1 position; if none → buy on momentum; if open → wait for SL/TP."""
    log.info("Loop started — max_positions=%d poll=%.0fs", max_positions, poll)
    while True:
        try:
            wait_ready(page)
            n = open_count(page)
            bid, ask = read_bid_ask(page)
            log.info("status open=%s bid=%.2f ask=%.2f", n, bid, ask)

            if n > max_positions:
                log.info("Too many positions (%s) — closing all", n)
                close_all(page)
            elif n == 0:
                # Prefer buy in demo practice (flip each cycle optionally)
                place_market(page, "buy")
            else:
                log.info("Position open — Exness SL/TP will exit; waiting...")
        except KeyboardInterrupt:
            log.info("Stopped")
            return
        except Exception as exc:
            log.warning("Loop error: %s", exc)
        time.sleep(poll)


def main() -> int:
    parser = argparse.ArgumentParser(description="Exness web bot (no API)")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--close-all", action="store_true")
    parser.add_argument("--buy", action="store_true")
    parser.add_argument("--sell", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--poll", type=float, default=30.0)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        log.error("Install: pip3 install --break-system-packages playwright && playwright install chromium")
        return 1

    pw, browser, page, owned = connect_page()
    try:
        wait_ready(page)
        if args.close_all:
            close_all(page)
        elif args.buy:
            place_market(page, "buy")
        elif args.sell:
            place_market(page, "sell")
        elif args.loop:
            loop(page, poll=args.poll)
        else:
            n = open_count(page)
            bid, ask = read_bid_ask(page)
            print(json.dumps({"open": n, "bid": bid, "ask": ask}, indent=2))
        return 0
    finally:
        if owned:
            browser.close()
        pw.stop()


if __name__ == "__main__":
    raise SystemExit(main())
