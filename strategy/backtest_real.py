#!/usr/bin/env python3
"""Backtest the live regime-detection strategy against real historical gold data.

Unlike gold_pro_strategy.py --backtest (synthetic mean-reverting data, single
strategy only), this replays real yfinance OHLC bars through the exact same
signal path auto_trader.py uses live: detect_regime() picks trend vs range
per bar, trend_signal() (EMA crossover) or BollingerRSIStrategy.update()
(Bollinger+RSI mean reversion) produces the signal, and SL/TP sizing uses
calc_sl_tp_atr() + size_lot_for_risk() (volatility-based stops, lot size
flexes to keep risk within budget). Stops the simulation early if equity
drops to 10% of its starting value — a real account would be margin-called
before that, so trading on past that point would be fiction.

Usage:
  python backtest_real.py --period 730d --interval 1h
  python backtest_real.py --period 60d --interval 15m
  python backtest_real.py --period 730d --interval 1h --equity 3000
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from auto_trader import AutoConfig, detect_regime, trend_signal
from gold_pro_strategy import BollingerRSIStrategy, ProConfig, atr, calc_sl_tp_atr, size_lot_for_risk
from history_data import fetch_gold_bars

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [backtest] %(message)s")
log = logging.getLogger("backtest_real")

RESULT_FILE = Path(__file__).resolve().parent.parent / "data" / "backtest_real_result.json"

MIN_CONFIDENCE = 0.58  # matches AutoConfig default
WARMUP_BARS = 30


def run(period: str, interval: str, initial_equity: float = 30.0) -> dict[str, Any]:
    bars = fetch_gold_bars(period=period, interval=interval)
    if len(bars) < WARMUP_BARS + 10:
        log.error("Not enough bars (%d) for a meaningful backtest", len(bars))
        return {}

    cfg = AutoConfig(min_confidence=MIN_CONFIDENCE)
    strategy = BollingerRSIStrategy(ProConfig())

    equity = initial_equity
    peak_equity = equity
    max_drawdown_pct = 0.0
    trades: list[dict[str, Any]] = []
    regime_counts = {"trend": 0, "range": 0}
    open_pos: dict[str, Any] | None = None
    ruined_at: str | None = None
    # Stop-out floor: a real broker force-closes/margin-calls well before
    # equity hits zero. Without this, a losing streak can push simulated
    # equity negative and then "recover" during a later bull run purely
    # because lot sizing floors at min_lot regardless of (fictitious)
    # negative equity — producing a return number no real account could
    # have earned, since it would have been wiped out first.
    RUIN_FLOOR = initial_equity * 0.10

    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []

    for bar in bars:
        if ruined_at is not None:
            break
        mid = bar.close
        ts = bar.timestamp.timestamp()
        # Mirrors auto_trader.run_cycle(): update the candle builder once per
        # bar unconditionally, then again for a range-regime signal — same
        # call pattern as the live code, so this backtest tests what's
        # actually running, quirks included.
        strategy.update(mid, now=ts)
        closes.append(bar.close)
        highs.append(bar.high)
        lows.append(bar.low)

        # Manage an already-open position first — one position at a time,
        # matching config.yaml's risk.max_open_positions: 1.
        if open_pos is not None:
            action = open_pos["action"]
            outcome = None
            exit_price = None
            if action == "buy":
                if bar.low <= open_pos["sl"]:
                    outcome, exit_price = "loss", open_pos["sl"]
                elif bar.high >= open_pos["tp"]:
                    outcome, exit_price = "win", open_pos["tp"]
            else:
                if bar.high >= open_pos["sl"]:
                    outcome, exit_price = "loss", open_pos["sl"]
                elif bar.low <= open_pos["tp"]:
                    outcome, exit_price = "win", open_pos["tp"]

            if outcome:
                lot = open_pos["lot"]
                if action == "buy":
                    pl = (exit_price - open_pos["entry"]) * lot * 100
                else:
                    pl = (open_pos["entry"] - exit_price) * lot * 100
                equity += pl
                peak_equity = max(peak_equity, equity)
                dd_pct = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0.0
                max_drawdown_pct = max(max_drawdown_pct, dd_pct)
                trades.append({
                    "action": action, "entry": round(open_pos["entry"], 3),
                    "exit": round(exit_price, 3), "pl": round(pl, 4),
                    "outcome": outcome, "regime": open_pos["regime"],
                    "confidence": round(open_pos["confidence"], 3),
                    "lot": lot, "equity_after": round(equity, 2),
                })
                open_pos = None
                if equity <= RUIN_FLOOR:
                    ruined_at = bar.timestamp.isoformat()
                    log.warning("Account wiped out (equity $%.2f <= floor $%.2f) at %s — stopping simulation",
                                equity, RUIN_FLOOR, ruined_at)
            continue

        if len(closes) < WARMUP_BARS:
            continue

        regime, regime_meta = detect_regime(closes, highs, lows)
        if regime == "trend":
            action, confidence, indicators = trend_signal(closes, cfg)
        else:
            action, confidence, indicators = strategy.update(mid, now=ts)

        if action in ("buy", "sell") and confidence >= cfg.min_confidence:
            regime_counts[regime] += 1
            entry = mid
            atr_val = atr(highs, lows, closes, 14)
            sl, tp = calc_sl_tp_atr(action, entry, atr_val, cfg.sl_atr_mult, cfg.tp_atr_mult)
            sl_dist = abs(entry - sl)
            lot = size_lot_for_risk(sl_dist, equity, cfg.max_loss_pct, cfg.min_lot, cfg.max_lot) if equity > 0 else cfg.min_lot
            open_pos = {
                "action": action, "entry": entry, "sl": sl, "tp": tp, "lot": lot,
                "regime": regime, "confidence": confidence,
            }

    wins = sum(1 for t in trades if t["pl"] > 0)
    losses = sum(1 for t in trades if t["pl"] <= 0)
    total_pl = sum(t["pl"] for t in trades)
    win_rate = wins / len(trades) * 100 if trades else 0.0
    by_regime: dict[str, dict[str, Any]] = {}
    for regime in ("trend", "range"):
        rt = [t for t in trades if t["regime"] == regime]
        rw = sum(1 for t in rt if t["pl"] > 0)
        by_regime[regime] = {
            "trades": len(rt),
            "win_rate_pct": round(rw / len(rt) * 100, 1) if rt else 0.0,
            "total_pl": round(sum(t["pl"] for t in rt), 4),
        }

    result = {
        "period": period, "interval": interval, "bars": len(bars),
        "start": bars[0].timestamp.isoformat(), "end": bars[-1].timestamp.isoformat(),
        "initial_equity": initial_equity,
        "final_equity": round(equity, 2),
        "total_pl": round(total_pl, 4),
        "return_pct": round((equity - initial_equity) / initial_equity * 100, 2),
        "trades": len(trades),
        "wins": wins, "losses": losses,
        "win_rate_pct": round(win_rate, 1),
        "max_drawdown_pct": round(min(max_drawdown_pct, 100.0), 2),
        "avg_pl_per_trade": round(total_pl / len(trades), 4) if trades else 0.0,
        "by_regime": by_regime,
        "ruined": ruined_at is not None,
        "ruined_at": ruined_at,
    }

    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps({**result, "trade_log": trades}, indent=2))

    log.info(
        "%d trades over %d bars (%s..%s): win_rate=%.1f%% total_pl=$%.2f final_equity=$%.2f (%.1f%%) max_dd=%.1f%% ruined=%s",
        len(trades), len(bars), result["start"][:10], result["end"][:10],
        win_rate, total_pl, equity, result["return_pct"], result["max_drawdown_pct"], result["ruined"],
    )
    log.info("By regime: %s", by_regime)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest live strategy against real gold history")
    parser.add_argument("--period", default="730d", help="yfinance period, e.g. 730d, 60d, max")
    parser.add_argument("--interval", default="1h", help="yfinance interval, e.g. 1h, 15m")
    parser.add_argument("--equity", type=float, default=30.0, help="starting equity in USD")
    args = parser.parse_args()

    result = run(args.period, args.interval, args.equity)
    if not result:
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
