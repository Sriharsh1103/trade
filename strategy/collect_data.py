#!/usr/bin/env python3
"""Collect gold trading data from Go API for ML retraining.

Exports account snapshots and appends closed-trade records to gold_trades.jsonl.

Usage:
  python collect_data.py --gold
  python collect_data.py --output ../data/demo_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def fetch_json(url: str) -> dict | list:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect trading data from Go API")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--output", type=Path, default=Path("../data/demo_snapshot.json"))
    parser.add_argument("--gold", action="store_true", help="Also append to data/gold_trades.jsonl")
    parser.add_argument("--jsonl", type=Path, default=Path("../data/gold_trades.jsonl"))
    args = parser.parse_args()

    snapshot = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "account": fetch_json(f"{args.base_url}/api/v1/account"),
        "positions": fetch_json(f"{args.base_url}/api/v1/positions"),
        "orders": fetch_json(f"{args.base_url}/api/v1/orders"),
        "risk": fetch_json(f"{args.base_url}/api/v1/risk/status"),
        "quote_xauusd": fetch_json(f"{args.base_url}/api/v1/quote/XAUUSD"),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2))
    print(f"Saved snapshot to {args.output}")

    if args.gold:
        append_jsonl(args.jsonl, {
            "type": "snapshot",
            **snapshot,
        })
        print(f"Appended snapshot to {args.jsonl}")
        print("\nTo retrain from collected demo trades:")
        print("  1. Accumulate gold_trades.jsonl via gold_trader.py and collect_data.py --gold")
        print("  2. Run: python train.py --input data/gold_trades.jsonl --symbol XAUUSD")
        print("  3. Deploy model signals via gold_trader.py or signals.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
