#!/usr/bin/env python3
"""Rule-based XAUUSD (gold) demo trader with momentum/trend signals.

Monitors gold price via Go demo API (or browser bridge), generates buy/sell
signals on M5-style momentum, and logs every trade for ML retraining.

Usage:
  python gold_trader.py                    # continuous loop
  python gold_trader.py --once             # single evaluation
  python gold_trader.py --mirror-browser   # also POST to browser bridge

Risk defaults (aligned with config/config.yaml):
  - $30 demo balance, 0.01 lot
  - Max 2% loss per trade ($0.60)
  - 10% TP target on position margin
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gold_trader")

DEFAULT_API = "http://localhost:8080"
DEFAULT_BRIDGE = "http://localhost:8090"
SYMBOL = "XAUUSD"
LOT_SIZE = 0.01
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "gold_trades.jsonl"


@dataclass
class GoldConfig:
    api_url: str = DEFAULT_API
    bridge_url: str = DEFAULT_BRIDGE
    symbol: str = SYMBOL
    lot_size: float = LOT_SIZE
    lookback: int = 5  # M5-style: last N ticks (~2.5s each at 500ms monitor)
    momentum_threshold: float = 0.15  # $0.15 move triggers signal
    min_confidence: float = 0.55
    poll_seconds: float = 5.0
    mirror_browser: bool = False


@dataclass
class TradeRecord:
    timestamp: str
    symbol: str
    action: str
    confidence: float
    bid: float
    ask: float
    momentum: float
    signal_source: str
    order: dict[str, Any] = field(default_factory=dict)
    account: dict[str, Any] = field(default_factory=dict)


def http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch_quote(cfg: GoldConfig) -> dict[str, Any]:
    return http_json("GET", f"{cfg.api_url}/api/v1/quote/{cfg.symbol}")  # type: ignore[return-value]


def fetch_account(cfg: GoldConfig) -> dict[str, Any]:
    return http_json("GET", f"{cfg.api_url}/api/v1/account")  # type: ignore[return-value]


def send_signal(cfg: GoldConfig, action: str, confidence: float) -> dict[str, Any]:
    payload = {
        "symbol": cfg.symbol,
        "action": action,
        "confidence": confidence,
        "source": "gold_trader_momentum",
    }
    return http_json("POST", f"{cfg.api_url}/api/v1/signals", payload)  # type: ignore[return-value]


def mirror_to_browser(cfg: GoldConfig, action: str, sl: float, tp: float) -> dict[str, Any] | None:
    if not cfg.mirror_browser:
        return None
    try:
        return http_json("POST", f"{cfg.bridge_url}/api/v1/orders", {
            "side": action,
            "volume": cfg.lot_size,
            "stop_loss": sl,
            "take_profit": tp,
        })  # type: ignore[return-value]
    except urllib.error.URLError as exc:
        log.warning("Browser mirror failed: %s", exc.reason)
        return None


def append_trade(record: TradeRecord) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("a") as f:
        f.write(json.dumps(asdict(record)) + "\n")
    log.info("Logged trade to %s", DATA_FILE)


class MomentumStrategy:
    """Simple trend/momentum on tick stream (proxy for M5/M15)."""

    def __init__(self, lookback: int, threshold: float) -> None:
        self.prices: deque[float] = deque(maxlen=lookback)
        self.threshold = threshold

    def update(self, mid: float) -> tuple[str, float, float]:
        self.prices.append(mid)
        if len(self.prices) < self.prices.maxlen:
            return "hold", 0.0, 0.0

        oldest = self.prices[0]
        momentum = mid - oldest
        pct_move = abs(momentum)

        if pct_move < self.threshold:
            return "hold", momentum, 0.0

        confidence = min(0.95, 0.5 + pct_move / (self.threshold * 4))
        if momentum > 0:
            return "buy", momentum, confidence
        return "sell", momentum, confidence


def calc_sl_tp(action: str, entry: float, equity: float, lot: float, leverage: int = 2000) -> tuple[float, float]:
    """Match Go risk manager: 2% max loss, 10% margin TP."""
    max_loss = equity * 0.02
    margin = entry * lot * 100 / leverage
    target_profit = margin * 0.10
    sl_dist = max_loss / (lot * 100)
    tp_dist = target_profit / (lot * 100)
    if action == "buy":
        return entry - sl_dist, entry + tp_dist
    return entry + sl_dist, entry - tp_dist


def run_once(cfg: GoldConfig, strategy: MomentumStrategy) -> bool:
    quote = fetch_quote(cfg)
    account = fetch_account(cfg)
    bid, ask = float(quote["bid"]), float(quote["ask"])
    mid = (bid + ask) / 2

    action, momentum, confidence = strategy.update(mid)
    log.info("XAUUSD mid=%.3f momentum=%.3f action=%s conf=%.2f balance=%.2f",
             mid, momentum, action, confidence, account.get("balance", 0))

    if action == "hold" or confidence < cfg.min_confidence:
        return False

    entry = ask if action == "buy" else bid
    sl, tp = calc_sl_tp(action, entry, float(account.get("equity", 30)), cfg.lot_size)

    order = send_signal(cfg, action, confidence)
    browser_result = mirror_to_browser(cfg, action, sl, tp)

    record = TradeRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=cfg.symbol,
        action=action,
        confidence=confidence,
        bid=bid,
        ask=ask,
        momentum=momentum,
        signal_source="gold_trader_momentum",
        order=order if isinstance(order, dict) else {},
        account=account if isinstance(account, dict) else {},
    )
    if browser_result:
        record.order["browser_mirror"] = browser_result
    append_trade(record)
    log.info("Signal executed: %s order_id=%s", action, order.get("id", "?"))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Gold (XAUUSD) momentum demo trader")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE)
    parser.add_argument("--once", action="store_true", help="Run one evaluation cycle")
    parser.add_argument("--mirror-browser", action="store_true", help="Mirror orders to browser bridge")
    parser.add_argument("--poll", type=float, default=5.0, help="Seconds between polls")
    parser.add_argument("--lookback", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.15, help="Min $ move for signal")
    args = parser.parse_args()

    cfg = GoldConfig(
        api_url=args.api_url,
        bridge_url=args.bridge_url,
        poll_seconds=args.poll,
        lookback=args.lookback,
        momentum_threshold=args.threshold,
        mirror_browser=args.mirror_browser,
    )

    try:
        health = http_json("GET", f"{cfg.api_url}/health")
        log.info("Connected to Go trader: mode=%s", health.get("mode"))
    except urllib.error.URLError as exc:
        log.error("Go trader not reachable at %s: %s", cfg.api_url, exc.reason)
        log.error("Start with: ./bin/trader --config config/config.yaml")
        return 1

    strategy = MomentumStrategy(cfg.lookback, cfg.momentum_threshold)

    if args.once:
        run_once(cfg, strategy)
        return 0

    log.info("Starting gold trading loop (poll=%ss, threshold=$%.2f)", cfg.poll_seconds, cfg.momentum_threshold)
    while True:
        try:
            run_once(cfg, strategy)
        except urllib.error.URLError as exc:
            log.warning("API error: %s", exc.reason)
        except KeyboardInterrupt:
            log.info("Stopped by user")
            return 0
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
