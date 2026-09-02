#!/usr/bin/env python3
"""Fetch XAUUSD historical OHLCV from free online sources (yfinance)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("history_data")

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "history"
# COMEX gold futures — tracks spot closely; 15m bars for strategy warmup
YF_SYMBOL = "GC=F"
FALLBACK_SYMBOL = "XAUUSD=X"


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def _scalar(val: Any) -> float:
    import pandas as pd

    if isinstance(val, pd.Series):
        val = val.iloc[0]
    return float(val)


def _download(symbol: str, period: str, interval: str) -> list[Bar]:
    import yfinance as yf

    t = yf.Ticker(symbol)
    df = t.history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        return []

    bars: list[Bar] = []
    for idx, row in df.iterrows():
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        o = _scalar(row["Open"])
        h = _scalar(row["High"])
        l = _scalar(row["Low"])
        c = _scalar(row["Close"])
        v = _scalar(row["Volume"]) if "Volume" in row.index else 0.0
        bars.append(Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=v))
    return bars


def fetch_gold_bars(period: str = "5d", interval: str = "15m") -> list[Bar]:
    """Download gold OHLCV; tries GC=F then 1h fallback."""
    for sym, iv in ((YF_SYMBOL, interval), (YF_SYMBOL, "1h"), (FALLBACK_SYMBOL, "1h")):
        try:
            bars = _download(sym, period, iv)
            if len(bars) >= 20:
                log.info("Loaded %d bars from %s (%s %s)", len(bars), sym, period, iv)
                return bars
        except Exception as exc:
            log.warning("yfinance %s/%s failed: %s", sym, iv, exc)
    log.warning("No historical data — will warm up from live quotes")
    return []


def live_gold_quote() -> dict[str, Any] | None:
    """Latest gold bid/ask proxy from yfinance (no browser needed)."""
    import yfinance as yf

    for sym in (YF_SYMBOL, FALLBACK_SYMBOL):
        try:
            t = yf.Ticker(sym)
            info = t.fast_info
            last = float(getattr(info, "last_price", 0) or 0)
            if last <= 0:
                hist = t.history(period="1d", interval="1m")
                if hist is not None and not hist.empty:
                    last = float(hist["Close"].iloc[-1])
            if last > 0:
                spread = 0.26  # typical XAUUSD spread
                return {
                    "symbol": "XAUUSD",
                    "bid": round(last - spread / 2, 3),
                    "ask": round(last + spread / 2, 3),
                    "source": sym,
                }
        except Exception as exc:
            log.debug("live quote %s: %s", sym, exc)
    return None


def bars_to_closes(bars: list[Bar]) -> list[float]:
    return [b.close for b in bars]


def bars_to_ohlc(bars: list[Bar]) -> tuple[list[float], list[float], list[float], list[float]]:
    return (
        [b.high for b in bars],
        [b.low for b in bars],
        [b.close for b in bars],
        [b.volume for b in bars],
    )
