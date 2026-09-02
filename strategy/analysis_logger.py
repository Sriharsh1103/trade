#!/usr/bin/env python3
"""Append periodic analysis snapshots to data/analysis_log.jsonl."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gold_pro_strategy import BollingerRSIStrategy, ProConfig, fetch_quote

LOG_FILE = Path(__file__).resolve().parent.parent / "data" / "analysis_log.jsonl"
API = "http://localhost:8080"


def main() -> int:
    cfg = ProConfig(api_url=API, poll_seconds=3.0)
    strategy = BollingerRSIStrategy(cfg)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Warm up with existing quotes
    for _ in range(100):
        try:
            q = fetch_quote(cfg)
            mid = (float(q["bid"]) + float(q["ask"])) / 2
            strategy.update(mid)
        except urllib.error.URLError:
            pass
        time.sleep(3)

    while True:
        try:
            q = fetch_quote(cfg)
            bid, ask = float(q["bid"]), float(q["ask"])
            mid = (bid + ask) / 2
            action, conf, meta = strategy.update(mid)
            snap = {
                "time": datetime.now(timezone.utc).isoformat(),
                "bid": round(bid, 3),
                "ask": round(ask, 3),
                "rsi": meta.get("rsi"),
                "adx": meta.get("adx"),
                "bb_lower": meta.get("bb_lower"),
                "bb_mid": meta.get("bb_mid"),
                "bb_upper": meta.get("bb_upper"),
                "signal": action,
                "confidence": round(conf, 3),
                "reason": meta.get("reason") or meta.get("signal", ""),
            }
            with LOG_FILE.open("a") as f:
                f.write(json.dumps(snap) + "\n")
            print(json.dumps(snap), flush=True)
        except urllib.error.URLError as exc:
            print(f"error: {exc.reason}", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
