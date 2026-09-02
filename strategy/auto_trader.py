#!/usr/bin/env python3
"""Fully autonomous gold trader — no browser approval needed.

- Loads online historical data (yfinance GC=F / XAUUSD=X)
- Detects market regime: trending vs ranging
- Trending → EMA crossover + momentum (buy/sell)
- Ranging → Bollinger + RSI mean reversion
- Syncs live prices to Go API, places orders via local API, auto-exits on SL/TP

Usage:
  python auto_trader.py              # run forever
  python auto_trader.py --once       # one cycle
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gold_pro_strategy import (
    BollingerRSIStrategy,
    ProConfig,
    adx,
    append_trade,
    calc_sl_tp,
    fetch_account,
    fetch_quote,
    http_json,
    rsi,
    send_signal,
    TradeRecord,
)
from history_data import fetch_gold_bars, live_gold_quote

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [auto] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_DIR / "auto_trader.log"),
    ],
)
log = logging.getLogger("auto_trader")

API = "http://localhost:8080"
BRIDGE = "http://127.0.0.1:8090"
ANALYSIS_LOG = Path(__file__).resolve().parent.parent / "data" / "analysis_log.jsonl"
TRADES_LOG = Path(__file__).resolve().parent.parent / "data" / "gold_trades.jsonl"


@dataclass
class AutoConfig:
    api_url: str = API
    bridge_url: str = BRIDGE
    poll_seconds: float = 5.0
    min_confidence: float = 0.58
    lot_size: float = 0.01
    ema_fast: int = 9
    ema_slow: int = 21
    adx_trend_threshold: float = 25.0


def ema(values: list[float], period: int) -> float:
    if len(values) < period:
        return values[-1] if values else 0.0
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def sync_live_price(cfg: AutoConfig) -> bool:
    """Push yfinance live gold price → bridge → Go demo engine."""
    q = live_gold_quote()
    if not q:
        return False
    try:
        account = fetch_account(ProConfig(api_url=cfg.api_url))
        balance = float(account.get("balance", 28.43))
    except urllib.error.URLError:
        balance = 28.43
    payload = {
        "symbol": "XAUUSD",
        "bid": q["bid"],
        "ask": q["ask"],
        "balance": balance,
        "equity": balance,
    }
    try:
        http_json("POST", f"{cfg.bridge_url}/api/v1/sync", payload)
    except urllib.error.URLError:
        pass
    try:
        http_json("POST", f"{cfg.api_url}/api/v1/broker/browser/sync", payload)
    except urllib.error.URLError:
        pass
    return True


def ensure_stack(cfg: AutoConfig) -> None:
    try:
        http_json("GET", f"{cfg.api_url}/health")
    except urllib.error.URLError:
        log.error("Go trader not running. Start: ./bin/trader --config config/config.yaml")
        raise SystemExit(1)
    try:
        http_json("POST", f"{cfg.api_url}/api/v1/broker/browser/enable", {})
    except urllib.error.URLError:
        pass
    try:
        status = http_json("POST", f"{cfg.api_url}/api/v1/risk/reset", {})
        if isinstance(status, dict) and status.get("trading_allowed"):
            log.info("Risk reset OK — trading allowed")
    except urllib.error.URLError:
        log.warning("Risk reset endpoint unavailable (rebuild trader binary)")


def load_history_into_strategy(strategy: BollingerRSIStrategy) -> int:
    bars = fetch_gold_bars(period="5d", interval="15m")
    if not bars:
        return 0
    for bar in bars:
        mid = (bar.high + bar.low) / 2
        ts = bar.timestamp.timestamp()
        strategy.update(mid, now=ts)
    return len(bars)


def detect_regime(closes: list[float], highs: list[float], lows: list[float]) -> tuple[str, dict[str, Any]]:
    """Return 'trend' or 'range' with indicator snapshot."""
    if len(closes) < 25:
        return "range", {"reason": "insufficient history"}
    adx_val = adx(highs, lows, closes, 14)
    rsi_val = rsi(closes, 14)
    ef = ema(closes, 9)
    es = ema(closes, 21)
    meta = {
        "adx": round(adx_val, 2),
        "rsi": round(rsi_val, 2),
        "ema_fast": round(ef, 3),
        "ema_slow": round(es, 3),
    }
    if adx_val >= 25.0:
        meta["regime"] = "trend"
        return "trend", meta
    meta["regime"] = "range"
    return "range", meta


def trend_signal(closes: list[float], cfg: AutoConfig) -> tuple[str, float, dict[str, Any]]:
    """EMA crossover + RSI for trending gold."""
    if len(closes) < cfg.ema_slow + 2:
        return "hold", 0.0, {"reason": "warming up trend"}
    ef = ema(closes, cfg.ema_fast)
    es = ema(closes, cfg.ema_slow)
    ef_prev = ema(closes[:-1], cfg.ema_fast)
    es_prev = ema(closes[:-1], cfg.ema_slow)
    rsi_val = rsi(closes, 14)
    price = closes[-1]
    meta = {"ema_fast": round(ef, 3), "ema_slow": round(es, 3), "rsi": round(rsi_val, 2), "strategy": "ema_trend"}

    # Golden cross → BUY
    if ef_prev <= es_prev and ef > es and rsi_val > 45:
        conf = min(0.92, 0.60 + (ef - es) / price * 100)
        meta["signal"] = "buy_trend"
        return "buy", conf, meta

    # Death cross → SELL
    if ef_prev >= es_prev and ef < es and rsi_val < 55:
        conf = min(0.92, 0.60 + (es - ef) / price * 100)
        meta["signal"] = "sell_trend"
        return "sell", conf, meta

    # Momentum continuation in strong trend
    if ef > es and rsi_val > 60 and price > ef:
        return "buy", 0.62, {**meta, "signal": "buy_momentum"}
    if ef < es and rsi_val < 40 and price < ef:
        return "sell", 0.62, {**meta, "signal": "sell_momentum"}

    meta["reason"] = "no trend signal"
    return "hold", 0.0, meta


def get_open_positions(cfg: AutoConfig) -> list[dict[str, Any]]:
    try:
        result = http_json("GET", f"{cfg.api_url}/api/v1/positions")
        return result if isinstance(result, list) else []
    except urllib.error.URLError:
        return []


def close_position(cfg: AutoConfig, pos_id: str) -> None:
    req = urllib.request.Request(
        f"{cfg.api_url}/api/v1/positions/{pos_id}",
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("Closed position %s: %s", pos_id, resp.read().decode()[:200])
    except urllib.error.URLError as exc:
        log.warning("Close failed %s: %s", pos_id, exc.reason)


def log_analysis(snap: dict[str, Any]) -> None:
    ANALYSIS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ANALYSIS_LOG.open("a") as f:
        f.write(json.dumps(snap) + "\n")


def run_cycle(cfg: AutoConfig, bb_strategy: BollingerRSIStrategy) -> str:
    sync_live_price(cfg)

    quote = fetch_quote(ProConfig(api_url=cfg.api_url))
    account = fetch_account(ProConfig(api_url=cfg.api_url))
    bid, ask = float(quote["bid"]), float(quote["ask"])
    mid = (bid + ask) / 2

    # Update live candle
    bb_strategy.update(mid)
    closes = bb_strategy.builder.close_list()
    highs, lows, _, _ = bb_strategy.builder.ohlc_lists()

    regime, regime_meta = detect_regime(closes, highs, lows)

    if regime == "trend":
        action, confidence, indicators = trend_signal(closes, cfg)
        indicators["regime"] = regime
        indicators.update(regime_meta)
    else:
        action, confidence, indicators = bb_strategy.update(mid)
        indicators["regime"] = regime
        indicators.update(regime_meta)

    risk = http_json("GET", f"{cfg.api_url}/api/v1/risk/status")
    positions = get_open_positions(cfg)

    snap = {
        "time": datetime.now(timezone.utc).isoformat(),
        "bid": round(bid, 3),
        "ask": round(ask, 3),
        "regime": regime,
        "signal": action,
        "confidence": round(confidence, 3),
        "balance": account.get("balance"),
        "open_positions": len(positions),
        "trading_allowed": risk.get("trading_allowed") if isinstance(risk, dict) else True,
        **{k: indicators.get(k) for k in ("rsi", "adx", "ema_fast", "ema_slow", "bb_lower", "bb_upper", "strategy", "reason", "signal")},
    }
    log_analysis(snap)

    log.info(
        "mid=%.2f regime=%s signal=%s conf=%.2f rsi=%s adx=%s pos=%d allowed=%s",
        mid, regime, action, confidence,
        indicators.get("rsi", "?"), indicators.get("adx", "?"),
        len(positions), snap.get("trading_allowed"),
    )

    # Auto-exit: close if unrealized loss > 5% margin (Go monitor handles SL/TP too)
    for pos in positions:
        upl = float(pos.get("unrealized_pl", 0))
        margin = float(pos.get("margin", 0.01))
        if margin > 0 and upl / margin * 100 <= -5:
            log.info("Auto-exit losing position %s pl=%.2f", pos.get("id"), upl)
            close_position(cfg, pos["id"])
            return "exit"

    if not isinstance(risk, dict) or not risk.get("trading_allowed", True):
        return "blocked"

    if len(positions) >= 3:
        return "max_positions"

    if action in ("buy", "sell") and confidence >= cfg.min_confidence:
        entry = ask if action == "buy" else bid
        equity = float(account.get("equity", 28.43))
        sl, tp = calc_sl_tp(action, entry, equity, cfg.lot_size)
        order = send_signal(ProConfig(api_url=cfg.api_url), action, confidence)
        record = TradeRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol="XAUUSD",
            action=action,
            confidence=confidence,
            bid=bid,
            ask=ask,
            signal_source=f"auto_{indicators.get('strategy', regime)}",
            indicators=indicators,
            order=order if isinstance(order, dict) else {},
            account=account if isinstance(account, dict) else {},
        )
        append_trade(record)
        log.info("TRADE %s @ %.2f sl=%.2f tp=%.2f id=%s", action.upper(), entry, sl, tp, order.get("id", "?"))
        return action

    return "hold"


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous gold trader")
    parser.add_argument("--poll", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    cfg = AutoConfig(poll_seconds=args.poll)
    Path(__file__).resolve().parent.parent.joinpath("logs").mkdir(exist_ok=True)

    ensure_stack(cfg)
    bb = BollingerRSIStrategy(ProConfig(api_url=cfg.api_url, poll_seconds=cfg.poll_seconds))

    n = load_history_into_strategy(bb)
    log.info("Loaded %d historical bars from yfinance — ready for analysis", n)
    if n < 20:
        log.info("Warming up from live quotes (30 polls)...")
        for _ in range(30):
            sync_live_price(cfg)
            try:
                q = fetch_quote(ProConfig(api_url=cfg.api_url))
                mid = (float(q["bid"]) + float(q["ask"])) / 2
                bb.update(mid)
            except urllib.error.URLError:
                pass
            time.sleep(2)

    if args.once:
        run_cycle(cfg, bb)
        return 0

    log.info("Auto-trader running (poll=%ss) — no browser approval needed", cfg.poll_seconds)
    while True:
        try:
            run_cycle(cfg, bb)
        except KeyboardInterrupt:
            log.info("Stopped")
            return 0
        except Exception as exc:
            log.warning("Cycle error: %s", exc)
        time.sleep(cfg.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
