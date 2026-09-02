#!/usr/bin/env python3
"""Send trading signals to the Go trading core."""

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://localhost:8080/api/v1/signals"


def send_signal(url: str, symbol: str, action: str, confidence: float, source: str) -> dict:
    payload = {
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "source": source,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a trading signal to the Go core")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--action", choices=["buy", "sell", "hold"], required=True)
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--source", default="manual")
    args = parser.parse_args()

    try:
        result = send_signal(args.url, args.symbol, args.action, args.confidence, args.source)
        print(json.dumps(result, indent=2))
        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Error {e.code}: {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Connection failed: {e.reason}", file=sys.stderr)
        print("Is the Go trader running? (./bin/trader --config config/config.yaml)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
