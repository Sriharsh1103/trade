#!/usr/bin/env python3
"""Bollinger Bands + RSI mean reversion strategy for XAUUSD demo trading.

Best for ranging gold sessions with tick-volume proxy confirmation.
Aligned with Go risk manager: 2% max loss, 10% margin TP.

Usage:
  python gold_pro_strategy.py                    # continuous loop
  python gold_pro_strategy.py --once             # single evaluation
  python gold_pro_strategy.py --backtest         # quick backtest on synthetic data
  python gold_pro_strategy.py --mirror-browser   # also POST to browser bridge
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
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
log = logging.getLogger("gold_pro")

DEFAULT_API = "http://localhost:8080"
DEFAULT_BRIDGE = "http://localhost:8090"
SYMBOL = "XAUUSD"
LOT_SIZE = 0.01
STRATEGY_NAME = "bollinger_rsi_mean_reversion"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "gold_trades.jsonl"
CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

_api_token_cache: str | None = None


def go_api_token() -> str:
    """Read server.api_token from config/config.yaml (cached).

    The Go API requires this as a Bearer token on every route but /health once
    it's set. Empty by default (matches the Go side's local-dev-only fallback).
    """
    global _api_token_cache
    if _api_token_cache is not None:
        return _api_token_cache
    token = ""
    try:
        import yaml

        if CONFIG_FILE.exists():
            data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            token = str((data.get("server") or {}).get("api_token") or "")
    except Exception:
        token = ""
    _api_token_cache = token
    return token


@dataclass
class ProConfig:
    api_url: str = DEFAULT_API
    bridge_url: str = DEFAULT_BRIDGE
    symbol: str = SYMBOL
    lot_size: float = LOT_SIZE
    bb_period: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    adx_period: int = 14
    adx_max: float = 30.0  # skip mean reversion when ADX above this (strong trend)
    candle_seconds: float = 15.0
    min_confidence: float = 0.60
    poll_seconds: float = 3.0
    mirror_browser: bool = False


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    timestamp: float


@dataclass
class TradeRecord:
    timestamp: str
    symbol: str
    action: str
    confidence: float
    bid: float
    ask: float
    signal_source: str
    indicators: dict[str, Any] = field(default_factory=dict)
    order: dict[str, Any] = field(default_factory=dict)
    account: dict[str, Any] = field(default_factory=dict)


def http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
    data = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"} if data else {}
    token = go_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def fetch_quote(cfg: ProConfig) -> dict[str, Any]:
    return http_json("GET", f"{cfg.api_url}/api/v1/quote/{cfg.symbol}")  # type: ignore[return-value]


def fetch_account(cfg: ProConfig) -> dict[str, Any]:
    return http_json("GET", f"{cfg.api_url}/api/v1/account")  # type: ignore[return-value]


def send_signal(cfg: ProConfig, action: str, confidence: float) -> dict[str, Any]:
    payload = {
        "symbol": cfg.symbol,
        "action": action,
        "confidence": confidence,
        "source": STRATEGY_NAME,
    }
    return http_json("POST", f"{cfg.api_url}/api/v1/signals", payload)  # type: ignore[return-value]


def mirror_to_browser(cfg: ProConfig, action: str, sl: float, tp: float) -> dict[str, Any] | None:
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
    log.info("Logged to %s", DATA_FILE)


DEFAULT_LEVERAGE = 100  # must match config/config.yaml demo.leverage


def calc_sl_tp(action: str, entry: float, equity: float, lot: float, leverage: int = DEFAULT_LEVERAGE) -> tuple[float, float]:
    """Match Go risk manager: 2% max loss, 10% margin TP.

    Caution: this ties SL *distance* directly to a fixed dollar amount
    (equity * max_loss_pct), independent of the instrument's actual
    volatility. On a small account this produces stops far tighter than
    gold's real hourly movement — a real backtest against 2 years of hourly
    data showed a 2.7% win rate and -84% return, with the vast majority of
    trades stopped out within the same hour regardless of direction. Prefer
    calc_sl_tp_atr() + size_lot_for_risk() for anything meant to actually
    trade; this is kept for the deprecated standalone scripts
    (run_pro_strategy.sh / run_continuous.sh) that still call it directly.
    """
    max_loss = equity * 0.02
    margin = entry * lot * 100 / leverage
    target_profit = margin * 0.10
    sl_dist = max_loss / (lot * 100)
    tp_dist = target_profit / (lot * 100)
    if action == "buy":
        return entry - sl_dist, entry + tp_dist
    return entry + sl_dist, entry - tp_dist


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """Average True Range — the instrument's actual recent volatility per bar."""
    n = len(closes)
    if n < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, n):
        h, l, c_prev = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - c_prev), abs(l - c_prev)))
    window = trs[-period:] if len(trs) >= period else trs
    return _mean(window) if window else 0.0


def calc_sl_tp_atr(
    action: str,
    entry: float,
    atr_value: float,
    sl_atr_mult: float = 1.5,
    tp_atr_mult: float = 2.5,
    min_dist: float = 0.30,
) -> tuple[float, float]:
    """Volatility-based SL/TP: stop/target distance scales with the
    instrument's actual recent movement (ATR) instead of a fixed dollar
    amount, so stops stay wider than normal market noise. min_dist is a
    floor for when ATR is unavailable/near-zero (e.g. warming up)."""
    sl_dist = max(atr_value * sl_atr_mult, min_dist)
    tp_dist = max(atr_value * tp_atr_mult, min_dist * (tp_atr_mult / sl_atr_mult))
    if action == "buy":
        return entry - sl_dist, entry + tp_dist
    return entry + sl_dist, entry - tp_dist


def size_lot_for_risk(
    sl_dist: float,
    equity: float,
    max_loss_pct: float,
    min_lot: float = 0.01,
    max_lot: float = 1.0,
    lot_step: float = 0.01,
) -> float:
    """Pick the lot size so a stop-out costs at most max_loss_pct of equity,
    given an ATR-sized (not artificially shrunk) stop distance. Floors at
    min_lot — the broker's minimum — even if that exceeds the risk budget;
    callers should treat that case as "risk budget too small for this
    instrument at any lot size" rather than shrinking the stop instead."""
    max_loss = equity * max_loss_pct / 100
    if sl_dist <= 0:
        return min_lot
    lot = max_loss / (sl_dist * 100)
    lot = round(lot / lot_step) * lot_step
    return max(min_lot, min(max_lot, lot))


# ── Indicators (pure Python — no external deps) ───────────────────────────────

def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def rsi(closes: list[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(-period, 0)]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = _mean(gains)
    avg_loss = _mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def bollinger(closes: list[float], period: int, std_mult: float) -> tuple[float, float, float]:
    if len(closes) < period:
        mid = closes[-1]
        return mid, mid, mid
    window = closes[-period:]
    mid = _mean(window)
    std = _std(window)
    return mid - std_mult * std, mid, mid + std_mult * std


def adx(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    n = len(closes)
    if n < period + 2:
        return 0.0
    tr_list: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, n):
        h, l, c_prev = highs[i], lows[i], closes[i - 1]
        h_prev, l_prev = highs[i - 1], lows[i - 1]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_list.append(tr)
        up = h - h_prev
        down = l_prev - l
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    if len(tr_list) < period:
        return 0.0
    atr = _mean(tr_list[-period:])
    if atr == 0:
        return 0.0
    plus_di = 100.0 * _mean(plus_dm[-period:]) / atr
    minus_di = 100.0 * _mean(minus_dm[-period:]) / atr
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0.0
    return dx


# ── Candle builder ────────────────────────────────────────────────────────────

class CandleBuilder:
    """Aggregate tick quotes into OHLCV candles with tick-volume proxy."""

    def __init__(self, interval_seconds: float) -> None:
        self.interval = interval_seconds
        self.candles: deque[Candle] = deque(maxlen=200)
        self._current: Candle | None = None
        self._period_start: float = 0.0

    def update(self, mid: float, now: float | None = None) -> Candle | None:
        ts = now if now is not None else time.time()
        if self._current is None or ts - self._period_start >= self.interval:
            finished = self._current
            self._current = Candle(open=mid, high=mid, low=mid, close=mid, tick_volume=1, timestamp=ts)
            self._period_start = ts
            if finished is not None:
                self.candles.append(finished)
            return finished
        c = self._current
        c.high = max(c.high, mid)
        c.low = min(c.low, mid)
        c.close = mid
        c.tick_volume += 1
        return None

    def close_list(self) -> list[float]:
        out = [c.close for c in self.candles]
        if self._current:
            out.append(self._current.close)
        return out

    def ohlc_lists(self) -> tuple[list[float], list[float], list[float], list[float]]:
        candles = list(self.candles)
        if self._current:
            candles.append(self._current)
        if not candles:
            return [], [], [], []
        return (
            [c.high for c in candles],
            [c.low for c in candles],
            [c.close for c in candles],
            [float(c.tick_volume) for c in candles],
        )


# ── Strategy ──────────────────────────────────────────────────────────────────

class BollingerRSIStrategy:
    def __init__(self, cfg: ProConfig) -> None:
        self.cfg = cfg
        self.builder = CandleBuilder(cfg.candle_seconds)

    def update(self, mid: float, now: float | None = None) -> tuple[str, float, dict[str, Any]]:
        self.builder.update(mid, now=now)
        closes_list = self.builder.close_list()
        min_needed = max(self.cfg.bb_period, self.cfg.rsi_period + 1, self.cfg.adx_period + 2)
        if len(closes_list) < min_needed:
            return "hold", 0.0, {"reason": f"warming up ({len(closes_list)}/{min_needed} candles)"}

        closes = closes_list
        highs, lows, _, volumes = self.builder.ohlc_lists()

        lower, middle, upper = bollinger(closes, self.cfg.bb_period, self.cfg.bb_std)
        rsi_val = rsi(closes, self.cfg.rsi_period)
        adx_val = adx(highs, lows, closes, self.cfg.adx_period)
        price = closes[-1]
        avg_vol = _mean(volumes[-self.cfg.bb_period:]) if len(volumes) >= self.cfg.bb_period else 1.0
        cur_vol = volumes[-1] if volumes else 1.0
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

        meta: dict[str, Any] = {
            "price": price,
            "bb_lower": round(lower, 3),
            "bb_mid": round(middle, 3),
            "bb_upper": round(upper, 3),
            "rsi": round(rsi_val, 2),
            "adx": round(adx_val, 2),
            "tick_volume": int(cur_vol),
            "vol_ratio": round(vol_ratio, 2),
            "candles": len(closes_list),
        }

        if adx_val > self.cfg.adx_max:
            meta["reason"] = f"ADX {adx_val:.1f} > {self.cfg.adx_max} — trending, skip mean reversion"
            return "hold", 0.0, meta

        band_width = upper - lower
        if band_width <= 0:
            return "hold", 0.0, meta

        # Buy: price at/below lower band + RSI oversold
        if price <= lower and rsi_val <= self.cfg.rsi_oversold:
            dist = (lower - price) / band_width
            conf = min(0.95, 0.55 + dist * 0.3 + (self.cfg.rsi_oversold - rsi_val) / 100)
            if vol_ratio >= 0.8:
                conf = min(0.95, conf + 0.05)
            meta["signal"] = "buy_mean_reversion"
            return "buy", conf, meta

        # Sell: price at/above upper band + RSI overbought
        if price >= upper and rsi_val >= self.cfg.rsi_overbought:
            dist = (price - upper) / band_width
            conf = min(0.95, 0.55 + dist * 0.3 + (rsi_val - self.cfg.rsi_overbought) / 100)
            if vol_ratio >= 0.8:
                conf = min(0.95, conf + 0.05)
            meta["signal"] = "sell_mean_reversion"
            return "sell", conf, meta

        meta["reason"] = "no band+RSI confluence"
        return "hold", 0.0, meta


# ── Backtest ──────────────────────────────────────────────────────────────────

def run_backtest(cfg: ProConfig, bars: int = 500, seed: int = 42) -> dict[str, Any]:
    """Quick backtest on mean-reverting synthetic gold prices (ranging market)."""
    random.seed(seed)
    price = 4308.0
    mean = 4308.0
    strategy = BollingerRSIStrategy(cfg)
    trades: list[dict[str, Any]] = []
    equity = 28.54
    leverage = 2000
    cooldown = 0

    for i in range(bars):
        # Mean-reverting random walk mimics ranging gold
        reversion = (mean - price) * 0.05
        noise = (random.random() - 0.5) * 0.80
        price += reversion + noise
        mean = mean * 0.999 + price * 0.001  # slow drift
        ts = float(i) * cfg.candle_seconds / 3  # ~3 ticks per candle

        if cooldown > 0:
            cooldown -= 1
            strategy.update(price, now=ts)
            continue

        action, conf, meta = strategy.update(price, now=ts)
        if action in ("buy", "sell") and conf >= cfg.min_confidence:
            entry = price
            sl, tp = calc_sl_tp(action, entry, equity, cfg.lot_size, leverage)
            exit_price = entry
            outcome = "open"
            for _ in range(30):
                reversion = (mean - price) * 0.05
                noise = (random.random() - 0.5) * 0.80
                price += reversion + noise
                if action == "buy":
                    if price <= sl:
                        exit_price, outcome = sl, "loss"
                        break
                    if price >= tp:
                        exit_price, outcome = tp, "win"
                        break
                else:
                    if price >= sl:
                        exit_price, outcome = sl, "loss"
                        break
                    if price <= tp:
                        exit_price, outcome = tp, "win"
                        break
            else:
                exit_price = price
                outcome = "timeout"

            if action == "buy":
                pl = (exit_price - entry) * cfg.lot_size * 100
            else:
                pl = (entry - exit_price) * cfg.lot_size * 100
            equity += pl
            trades.append({"action": action, "entry": round(entry, 3), "exit": round(exit_price, 3),
                           "pl": round(pl, 4), "outcome": outcome, "conf": round(conf, 3),
                           "rsi": meta.get("rsi"), "adx": meta.get("adx")})
            cooldown = 25  # avoid overlapping signals

    wins = sum(1 for t in trades if t["pl"] > 0)
    losses = sum(1 for t in trades if t["pl"] <= 0)
    total_pl = sum(t["pl"] for t in trades)
    win_rate = wins / len(trades) * 100 if trades else 0.0
    avg_pl = total_pl / len(trades) if trades else 0.0

    result = {
        "strategy": STRATEGY_NAME,
        "bars": bars,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 1),
        "total_pl": round(total_pl, 4),
        "avg_pl_per_trade": round(avg_pl, 4),
        "final_equity": round(equity, 4),
    }
    log.info("Backtest: %d trades, win_rate=%.1f%%, total_pl=$%.4f, final_equity=$%.2f",
             len(trades), win_rate, total_pl, equity)
    return result


# ── Live runner ───────────────────────────────────────────────────────────────

def run_once(cfg: ProConfig, strategy: BollingerRSIStrategy) -> bool:
    quote = fetch_quote(cfg)
    account = fetch_account(cfg)
    bid, ask = float(quote["bid"]), float(quote["ask"])
    mid = (bid + ask) / 2

    action, confidence, indicators = strategy.update(mid)
    log.info("XAUUSD mid=%.3f rsi=%s adx=%s action=%s conf=%.2f balance=%.2f",
             mid,
             indicators.get("rsi", "?"),
             indicators.get("adx", "?"),
             action,
             confidence,
             account.get("balance", 0))

    if action == "hold" or confidence < cfg.min_confidence:
        if indicators.get("reason"):
            log.debug("Hold: %s", indicators["reason"])
        return False

    entry = ask if action == "buy" else bid
    leverage = int(account.get("leverage") or DEFAULT_LEVERAGE)
    sl, tp = calc_sl_tp(action, entry, float(account.get("equity", 28.54)), cfg.lot_size, leverage)

    order = send_signal(cfg, action, confidence)
    browser_result = mirror_to_browser(cfg, action, sl, tp)

    record = TradeRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=cfg.symbol,
        action=action,
        confidence=confidence,
        bid=bid,
        ask=ask,
        signal_source=STRATEGY_NAME,
        indicators=indicators,
        order=order if isinstance(order, dict) else {},
        account=account if isinstance(account, dict) else {},
    )
    if browser_result:
        record.order["browser_mirror"] = browser_result
    append_trade(record)
    log.info("Signal executed: %s order_id=%s sl=%.2f tp=%.2f", action, order.get("id", "?"), sl, tp)
    return True


def warm_up(cfg: ProConfig, strategy: BollingerRSIStrategy, polls: int) -> None:
    """Collect candles before live trading."""
    log.info("Warming up: collecting %d quote polls (~%ds)...", polls, int(polls * cfg.poll_seconds))
    for i in range(polls):
        try:
            quote = fetch_quote(cfg)
            mid = (float(quote["bid"]) + float(quote["ask"])) / 2
            strategy.update(mid)
        except urllib.error.URLError:
            pass
        time.sleep(cfg.poll_seconds)
    log.info("Warm-up done: %d candles ready", len(strategy.builder.close_list()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Gold Bollinger+RSI pro strategy")
    parser.add_argument("--api-url", default=DEFAULT_API)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--backtest", action="store_true", help="Run synthetic backtest and exit")
    parser.add_argument("--mirror-browser", action="store_true")
    parser.add_argument("--poll", type=float, default=3.0)
    parser.add_argument("--warmup-polls", type=int, default=25, help="Quote polls to build candle history")
    parser.add_argument("--duration", type=float, default=180.0, help="Run seconds (0=infinite)")
    args = parser.parse_args()

    cfg = ProConfig(
        api_url=args.api_url,
        bridge_url=args.bridge_url,
        poll_seconds=args.poll,
        mirror_browser=args.mirror_browser,
    )

    if args.backtest:
        result = run_backtest(cfg)
        print(json.dumps(result, indent=2))
        append_trade(TradeRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            symbol=SYMBOL,
            action="backtest",
            confidence=0.0,
            bid=0.0,
            ask=0.0,
            signal_source=f"{STRATEGY_NAME}_backtest",
            indicators=result,
        ))
        return 0

    try:
        health = http_json("GET", f"{cfg.api_url}/health")
        log.info("Connected: mode=%s strategy=%s", health.get("mode"), STRATEGY_NAME)
    except urllib.error.URLError as exc:
        log.error("Go trader not reachable at %s: %s", cfg.api_url, exc.reason)
        log.error("Start with: ./bin/trader --config config/config.yaml")
        return 1

    strategy = BollingerRSIStrategy(cfg)
    warm_up(cfg, strategy, args.warmup_polls)

    if args.once:
        run_once(cfg, strategy)
        return 0

    log.info("Starting pro strategy loop (poll=%ss, min_conf=%.2f)", cfg.poll_seconds, cfg.min_confidence)
    start = time.time()
    while True:
        if args.duration > 0 and time.time() - start >= args.duration:
            log.info("Duration limit reached (%.0fs)", args.duration)
            break
        try:
            run_once(cfg, strategy)
        except urllib.error.URLError as exc:
            log.warning("API error: %s", exc.reason)
        except KeyboardInterrupt:
            log.info("Stopped by user")
            return 0
        time.sleep(cfg.poll_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
