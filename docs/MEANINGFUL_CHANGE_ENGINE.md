# The meaningful-change engine

`backend/app/services/signal_engine/engine.py`: a pure function
`evaluate(SignalInputs, Preferences) -> SignalResult`. There is no I/O, no randomness
and no ML. The same inputs always give the same score, and each result is stored with
its inputs and per-factor points (`signal_scores`), so any decision can be audited later.

## Inputs (all computed by the backend, never by AI)

| Input | Source |
|---|---|
| `change_pct` | Current resolved price vs the price **you saw** at your checkpoint |
| `sector_change_pct` | Sector ETF now vs the sector ETF price stored **with your checkpoint** |
| `market_change_pct` | SPY now vs SPY at your checkpoint |
| `day_change_pct` | vs previous close (shown, not scored) |
| `volume_ratio` | Cumulative volume ÷ (20-day average × fraction of the session elapsed) |
| `daily_volatility_pct` | Std-dev of the last 20 daily returns |
| `events` | Provider events from 12h before your checkpoint until now |
| `priority` | Starred in any of your watchlists |
| `data_status`, conflict | From the freshness classifier and conflict resolution |

Storing benchmark prices *with the checkpoint* is what makes the context fair. Stock,
sector and market are all measured over the same window.

## Factors (default weights; `EngineConfig`)

`ramp(x, lo, hi)` is 0 below `lo`, 1 above `hi`, and linear in between.

1. **Price movement: 30.** `magnitude = |change| / (σ_daily × √max(1, trading_days))`,
   points = `30 × ramp(magnitude, 0.25, 2.0)`. If no history exists, raw % is used (`ramp(|change|, 0.4, 4.0)`) and a caveat is added.
   **Market dampening:** if the market moved the same way, `explained = min(1, |market| / |change|)` and points are multiplied by `1 − 0.65 × explained`.
2. **Relative performance: 30.** `max( ramp(|change − sector|, 0.5, 4.0), 0.5 × ramp(|change − market|, 0.5, 4.0) )`.
   A stock moving with its sector while the market is flat still earns half credit, because the sector move is itself news.
3. **Volume anomaly: 20.** `20 × ramp(volume_ratio, 1.1, 3.0)`, **halved if the price barely moved**. Volume alone can't make a signal.
4. **Event significance: 15.** `15 × significance` of the strongest event in the window (earnings 1.0, regulatory 0.8, analyst 0.5, news 0.35–0.4, dividend 0.3).
5. **Watchlist priority: 5.** If starred.

The points add up to the score (0–100). If you switch off a factor in Settings, its
weight is spread proportionally over the remaining factors, so the scale stays 0–100.

## Attention

| Sensitivity | HIGH | MEDIUM |
|---|---|---|
| Low | ≥ 75 | ≥ 50 |
| Balanced | ≥ 65 | ≥ 40 |
| High | ≥ 55 | ≥ 30 |

Guardrails:
- HIGH needs **price + relative points ≥ 25**. Volume and events strengthen a signal but can't create one.
- **Stale** or **conflicting** data caps attention at MEDIUM until the data is fresh and consistent.

## Confidence

Starts at 1.0. Stale −0.45, delayed −0.15, conflicted −0.35; missing volume, sector, market or history −0.08 each; cross-verified by two agreeing providers +0.05. Levels: HIGH ≥ 0.75, MEDIUM ≥ 0.5, otherwise LOW.

## Movement type (the context label)

| Type | Rule | Label |
|---|---|---|
| QUIET | `|change| < max(0.5, 0.35σ)` | In line with the market |
| MARKET_WIDE | same sign as market and `|change − market| ≤ max(0.75, 25% of |change|)` | Broad market movement |
| SECTOR_WIDE | as above vs sector, and the sector diverged from the market by > 0.75 pts | Energy sector movement |
| STOCK_SPECIFIC | otherwise | Stock-specific |

## Worked examples (Balanced)

| Case | Inputs | Score | Attention |
|---|---|---:|---|
| Stock-specific drop | NVDA −4.8%, sector −0.7, market −0.3, 2.8× vol, σ 2.4 | 77 | HIGH |
| + earnings event | same, with earnings | 92 | HIGH |
| Broad market drop | NVDA −4.8%, sector −4.2, market −3.9, 1.6× vol | 21 | LOW (market-wide) |
| Sector move | XOM −3.9%, sector −3.6, market −0.2, 1.7× vol | 49 | MEDIUM (sector-wide) |
| Surge | TSLA +6.2%, sector +0.3, 2.4× vol, σ 3.5 | 69 | HIGH |
| Volume spike | MSFT +1.1%, 3.4× vol | 33 | LOW (MEDIUM on High sensitivity) |
| Stale | NVDA drop, data 95 min old | 77 | MEDIUM (capped), confidence 0.55 |

These cases are covered by `backend/tests/test_engine.py`.

## From score to change event

`ChangeDetectionService.evaluate_user` (`services/change_detection/detector.py`):

- One **ChangeEvent** per (user, symbol, baseline, direction, generation). Re-evaluating the same market state writes nothing new (deterministic `dedupe_key`s on scores and events).
- **Escalation** (MEDIUM → HIGH) re-surfaces the same event as NEW and notifies once.
- **Acknowledged** events stay acknowledged. A new generation is created only if the move extends by ≥ max(1.5 pts, 1σ) or attention escalates.
- Signals that fade below MEDIUM become **RESOLVED**. A new checkpoint **ARCHIVES** everything measured against the old baseline.
- The Command Center shows ACTIVE events. LOW items are listed as *Quiet: Knoww decided these don't need you.*

## Tuning

All thresholds live in `EngineConfig`. Bump `ENGINE_VERSION` when changing it. Stored
scores record the version, so old and new behaviour can be compared, for example
against users' review behaviour (see the product metrics on `/system`).
