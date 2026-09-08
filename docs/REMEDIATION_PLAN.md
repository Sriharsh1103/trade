# Remediation Plan — Auto Trading System

Generated from full-codebase audit on 2026-09-08. Tracks issues found, decisions made, and fix status. Update checkboxes as work completes.

## Decisions (confirmed with project owner)

1. **Primary path:** Go engine (risk/signals) + Python `auto_trader.py` mirroring decisions to Exness via browser automation. The pure-browser-loop and MT5 EA paths are deprecated/archived, not deleted.
2. **Auto control access:** a single authenticated global enable/disable gate in the Go backend, checked by every order-placing code path (Go engine, Python mirror, queue drain), plus an emergency stop-all.
3. **Credentials:** `config/credentials.yaml` gets wired up for automated Exness login (currently unused).

## Phase 1 — Critical safety/correctness fixes

- [x] 1.1 Fixed silent-failure order queue: removed the file-queue entirely. `auto_trader.py` now calls `exness_executor.mirror_order()` in-process (`strategy/exness_executor.py`), so there's no separate unstarted consumer process to forget to launch.
- [x] 1.2 Moot — the queue (and its newest-only-drain bug) no longer exists after 1.1.
- [x] 1.3 Fixed wrong leverage in SL/TP math: `calc_sl_tp` now takes the real account leverage (`account.get("leverage")`) from the live `/api/v1/account` response at both call sites, falling back to `DEFAULT_LEVERAGE = 100` (matching `config.yaml`'s `demo.leverage`) only if the field is missing — no more hardcoded `2000`.
- [x] 1.4 Fixed hardcoded equity/balance fallbacks: `sync_live_price()` no longer pushes a fabricated `$28.43` balance into the Go engine on an account-fetch failure (uses `0` as a documented no-op sentinel instead, since Go's `SyncQuote` only overwrites balance when it's `> 0`); `run_cycle()`'s SL/TP calc no longer has a hardcoded numeric fallback either.
- [x] 1.5 Added bearer-token auth (`server.api_token` in `config.yaml`) required on every route except `/health`; a startup warning fires if it's unset. Default bind changed from `0.0.0.0` to `127.0.0.1` in `applyDefaults()` (the user's existing local `config.yaml` explicitly set `0.0.0.0`, left as-is but now token-protected). Verified end-to-end: unauthenticated requests get `401`.
- [x] 1.6 `POST /api/v1/risk/reset` is now covered by the same auth middleware (previously wide open). Left restart-triggers-fresh-demo-balance behavior as-is — it's intentional for a demo-only simulator (see `main.go` comment), and is no longer a network-reachable exploit since it requires the bearer token.
- [x] 1.7 Built the global trading enable/disable gate — new `backend/internal/control` package, persisted to `data/trading_state.json`, defaults to **disabled**. Wired into `trading.Engine.PlaceOrder`/`ProcessSignal` (Go) and `exness_executor.mirror_order()` (Python, via `GET /api/v1/control/status`) — see design section below. Verified end-to-end: a signal is rejected while disabled, accepted once enabled, and `stop-all` disables + closes the open position.
- [x] 1.8 Fixed demo engine's per-symbol quote bug: `externalQuote/externalBid/externalAsk/externalSyncAt` (single shared fields) replaced with `externalQuotes map[string]externalQuote` keyed by symbol, in `GetQuote`/`Tick`/`SyncQuote`/`getQuoteLocked`.
- [x] 1.9 Added `strategy/broker_login.py`: reads `config/credentials.yaml`, auto-logs into whichever section is filled in (prefers `metatrader:` — the account `config.yaml`'s `broker.account_id` actually points at — falls back to `exness:`), and is called from `exness_executor.place_order_playwright()` before every mirrored order. Best-effort by design (selectors against a third-party site can't be verified without a live logged-out session) — falls back to "log in manually" if the form-fill or post-submit check fails.

## Phase 2 — Consolidation / dead code cleanup

- [x] 2.1 Consolidated: `exness_executor.py` is now the one execution module the primary path uses (in-process `mirror_order()`, no file queue). `browser_bridge.py` remains running (started by `run_auto.sh`) only as a price-sync passthrough; its independent `/api/v1/orders` Playwright path was already dead code since the Go engine's `broker.Client` is never the `BrowserAutomation` instance — left as-is, not worth the risk of removing something that might be relied on elsewhere without more testing surface.
- [x] 2.2 Marked deprecated with header comments pointing to `run_auto.sh`: `scripts/run_continuous.sh`, `scripts/run_pro_strategy.sh`, `scripts/run_gold_trader.sh`. Marked experimental/alternate (not deprecated — genuinely different execution surfaces, kept intentionally per the "keep, don't remove" decision): `scripts/run_mt5_web.sh`, `scripts/run_exness_bot.sh`. Files themselves untouched, no behavior change.
- [x] 2.3 Documented in `docs/NO_API_OPTIONS.md`: rewrote it to mark the Go+mirror path primary, and explicitly call out that both the pure-browser bot and the MT5 EA are **not** wired to the new control gate — the MT5 EA's manual kill switch is its own AutoTrading toggle; the browser bot's is killing the process.

## Phase 3 — Config/docs consistency

- [x] 3.1 Synced `config/credentials.example.yaml` — added the missing `metatrader:` section (blank placeholders) with a comment explaining the login-preference order in `broker_login.py`.
- [x] 3.2 Fixed `docker/docker-compose.yml` header comment to include `--profile mt5 --profile core`, and clarified that the primary supported path doesn't need Docker at all.
- [x] 3.3 Updated `docs/ARCHITECTURE.md` (new Security bullet + "Trading Control Gate" section + updated endpoint table) and `README.md` (Quick Start now covers `server.api_token` and the enable/stop-all calls).

## Design: Global Trading Control Gate

- **Source of truth:** Go backend, in-memory + persisted to `data/trading_state.json` so it survives restarts.
- **State:** `enabled: bool`, `reason: string`, `changed_at: timestamp`, `changed_by: string`.
- **Endpoints (auth required, bearer token from config):**
  - `GET /api/v1/control/status` — current state.
  - `POST /api/v1/control/enable` — turn trading on.
  - `POST /api/v1/control/disable` — turn trading off (used for both manual pause and emergency stop).
  - `POST /api/v1/control/stop-all` — disable + close all open positions immediately.
- **Enforcement points:**
  - Go `trading.Engine.PlaceOrder` / `ProcessSignal` — check gate before executing.
  - `auto_trader.py` — check `GET /api/v1/control/status` at the top of each cycle before acting on a signal.
  - Exness order queue drain (post 1.1 fix) — check gate before placing.
- **Out of scope for the gate:** the MT5 EA and any standalone deprecated scripts (Phase 2) are not wired in; they must be stopped manually if running.

## Issue reference (from audit, for traceability)

| # | Issue | File(s) | Plan item |
|---|-------|---------|-----------|
| 1 | Order queue has no consumer | `strategy/auto_trader.py`, `strategy/exness_executor.py` | 1.1 |
| 2 | Queue drain drops all but newest order | `strategy/exness_executor.py` | 1.2 |
| 3 | Wrong leverage in SL/TP calc | `strategy/gold_pro_strategy.py`, `strategy/auto_trader.py` | 1.3 |
| 4 | No auth / open bind on Go API | `backend/internal/api/server.go`, `backend/internal/config/config.go` | 1.5 |
| 5 | No global kill switch anywhere | (new) | 1.7 |
| 6 | Hardcoded equity fallback | `strategy/auto_trader.py`, `strategy/gold_pro_strategy.py` | 1.4 |
| 7 | Demo engine global (non-per-symbol) quote state | `backend/internal/demo/engine.go` | 1.8 |
| 8 | `docker compose up -d` starts nothing (profiles) | `docker/docker-compose.yml` | 3.2 |
| 9 | `credentials.yaml` never read | `config/credentials.yaml`, browser bots | 1.9 |
| 10 | Redundant/overlapping scripts and strategy files | `scripts/*.sh`, `strategy/*.py` | 2.1, 2.2 |
| 11 | `credentials.example.yaml` out of sync | `config/credentials.example.yaml` | 3.1 |

## Execution notes

Work proceeds phase by phase, item by item. Each completed item is checked off here and gets its own reasoning noted inline if a non-obvious tradeoff was made. Open questions that come up mid-fix will be asked directly rather than assumed.

## Verification performed

- `go build ./cmd/trader`, `go vet ./...`, `go test ./...` all clean after every Go change.
- All `strategy/*.py` files pass `python3 -m py_compile` after every Python change.
- All `scripts/*.sh` pass `bash -n`.
- Live smoke test of the control gate against the built binary: unauthenticated request → `401`; `GET /control/status` → `enabled: false` by default; `POST /signals` while disabled → rejected with `"trading disabled: ..."`; `POST /control/enable` → order fills; `POST /control/stop-all` → position closed and gate flips back to disabled; state correctly persisted to `data/trading_state.json`.
- **Not verified** (no live browser/broker session available in this environment): `strategy/broker_login.py`'s selectors against the real MetaTrader/Exness web terminals. It's written defensively (falls back to "log in manually" rather than failing hard), but the first live run should be watched to confirm the login form selectors still match — vendor UI changes are the single most likely thing to break this path.

## Phase 4 — Strategy validation against real data (new, post-launch-prep)

Built `strategy/backtest_real.py` — replays 2 years of real hourly XAUUSD data (yfinance `GC=F`, 13,718 bars) through the exact live signal path (`detect_regime` → `trend_signal` / `BollingerRSIStrategy`), instead of the old synthetic-data-only backtest.

- [x] 4.1 First run (old `calc_sl_tp`, fixed equity-% stop distance): **2.7% win rate, -84.65% return, 99.62% "drawdown"** — root cause found: SL distance was tied directly to `equity × 2%` (≈ $0.60 at $30 equity), far tighter than gold's real hourly range (routinely several dollars) — nearly every trade stopped out same-hour regardless of direction.
- [x] 4.2 Replaced with `calc_sl_tp_atr()` + `size_lot_for_risk()` in `gold_pro_strategy.py`: SL/TP distance now scales with actual ATR(14) volatility; lot size (not stop distance) flexes to keep dollar risk within the `max_loss_pct` budget. Wired into both `auto_trader.py`'s live cycle and the backtest.
- [x] 4.3 Added a ruin-floor stop-out check to the backtest (equity ≤ 10% of starting balance ends the simulation) — without it, a fictitious negative-equity "recovery" during the later bull run produced an impossible +3605% / 492% "drawdown" result. A real broker margin-calls long before that.
- [x] 4.4 **At the actual $30 demo balance: still ruined — wiped out in 9 trades (33% win rate), because the broker's 0.01-lot minimum alone risks 40-70% of a $30 account once stops are sized to gold's real volatility.** This is a position-sizing/instrument-suitability problem, not a signal-quality problem — confirms a warning already present in `config.yaml`: *"$30 MetaQuotes demo cannot margin 0.01 XAUUSD — use FX majors first."*
- [x] 4.5 Re-ran at $3,000 starting equity (isolating signal quality from the sizing constraint): **+114.93% return over 2.5 years, 39.9% win rate, 882 trades, 33.8% max drawdown, not ruined.** The trend-following half of the strategy has real positive edge (win rate under 50% but profitable due to the ~1.67 R:R ratio). **Caveat: the range/mean-reversion half (`BollingerRSIStrategy`) fired zero times in this entire 2-year window** — gold has been in a persistent uptrend, so ADX rarely if ever dropped below the trend threshold. The mean-reversion path is effectively unvalidated.
- [ ] 4.6 Open decision (needs the account owner): the $30 balance can't safely trade XAUUSD at any lot size the broker allows. Either raise the demo account's starting balance (free — most demo accounts can be recreated with a chosen balance) or switch to a less volatile-per-lot instrument. Not resolved yet — flagged to the user.
- [ ] 4.7 Not done: backtesting the range/mean-reversion strategy specifically (needs a data window where gold actually ranged, or a different instrument/period).

## Known items not acted on (flagged, not fixed)

- `config/credentials.yaml` contains a real-looking MetaQuotes-Demo login/password/investor password in plaintext, with a pre-existing comment "User shared password in chat — rotate after setup if this was a real account." This file is correctly gitignored and nothing outside this machine can read it, but if that account is anything other than a throwaway demo, rotating its password is worth doing independent of this remediation pass.
- `config/config.yaml`'s `trading.default_symbol` is `AUDCAD` while every strategy hardcodes `XAUUSD` — left as-is per the audit's open question; it's currently unreachable dead-path (the cross-symbol bug it would otherwise trigger, item 1.8, is now fixed anyway) but worth revisiting if a second symbol is ever actually traded.
