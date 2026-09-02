#!/usr/bin/env python3
"""Model training pipeline placeholder for Phase 2."""

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a trading strategy model")
    parser.add_argument("--data", type=Path, required=True, help="Path to training CSV")
    parser.add_argument("--output", type=Path, default=Path("models/strategy.pkl"))
    args = parser.parse_args()

    if not args.data.exists():
        print(f"Data file not found: {args.data}")
        print("Collect demo trade data first — see docs/ML_PIPELINE.md")
        return 1

    print("Training pipeline not yet implemented.")
    print(f"Would train on: {args.data}")
    print(f"Would save to:  {args.output}")
    print("\nNext steps:")
    print("  1. Collect OHLCV + trade outcomes from demo sessions")
    print("  2. Engineer features (returns, volatility, spread, time-of-day)")
    print("  3. Train classifier (buy/sell/hold) with walk-forward validation")
    print("  4. Paper-trade via signals.py before any live deployment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
