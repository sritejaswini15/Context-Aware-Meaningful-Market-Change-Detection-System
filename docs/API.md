# API

Base path `/api`. Interactive OpenAPI docs are at `/api/docs`; the schema is at `/api/openapi.json`
(a snapshot is committed as [openapi.json](openapi.json)).

Authentication: the `knoww_session` httpOnly cookie set by `/auth/login`, or
`Authorization: Bearer <token>`. Every resource is scoped to the caller. IDs that belong to
another user return **404**.

Errors share one shape:
```json
{ "error": { "code": "not_found", "message": "Watchlist not found", "request_id": "…" } }
```

## Auth and onboarding
| Method | Path | |
|---|---|---|
| POST | `/auth/signup` | Create account (Cognito mode returns `CONFIRMATION_REQUIRED`) |
| POST | `/auth/confirm` | Confirm Cognito sign-up code |
| POST | `/auth/login` | Sign in, sets session cookie |
| POST | `/auth/refresh` | Refresh session (Cognito) |
| POST | `/auth/logout` | Clear session |
| GET / PATCH | `/auth/me` | Current user / display name |
| POST | `/onboarding` | First watchlist + sensitivity in one step |

## Command Center
| Method | Path | |
|---|---|---|
| GET | `/command-center` | "Since you last checked": counts, ranked changes, quiet stocks, market context, watchlists, recent activity, data quality |
| POST | `/checkpoint` | "I'm caught up": new baseline for all watchlists |

## Watchlists
| Method | Path | |
|---|---|---|
| GET / POST | `/watchlists` | List / create (optionally with symbols) |
| GET / PATCH / DELETE | `/watchlists/{id}` | Read / rename / delete |
| POST | `/watchlists/{id}/stocks` | Add a symbol (baseline starts now) |
| PATCH | `/watchlists/{id}/stocks/{symbol}` | Set priority `NORMAL` or `HIGH` |
| DELETE | `/watchlists/{id}/stocks/{symbol}` | Remove a symbol |
| GET | `/watchlists/{id}/snapshot` | Rows: price, today, since last check, signal, volume ratio, freshness |
| GET | `/watchlists/{id}/changes` | Active meaningful changes for this list |
| POST | `/watchlists/{id}/checkpoint` | Mark this watchlist reviewed |

## Changes
| Method | Path | |
|---|---|---|
| GET | `/changes?attention=&state=&scope=current\|history&sort=importance\|recent&symbol=` | Feed with counts |
| GET | `/changes/{id}` | Detail: explanation, factors, freshness, earlier changes |
| POST | `/changes/{id}/seen` | Opened |
| POST | `/changes/{id}/acknowledge` | Reviewed: no longer surfaced as new |
| POST | `/changes/acknowledge-all` | Review everything currently open |

## Stocks and market
| Method | Path | |
|---|---|---|
| GET | `/stocks/search?q=` | Company or ticker search, with current price if known |
| GET | `/stocks/{symbol}` | Investigation: state, signal (vs checkpoint, or previous close if not watched), factors, explanation, sector/market comparison, events, conflict, stats |
| GET | `/stocks/{symbol}/history?days=90` | Chart series: price, relative vs sector and market, volume with 20-day average, since-checkpoint path |
| GET | `/stocks/{symbol}/signals` | Your evaluation history and change timeline |
| GET | `/market/status` | Session, S&P 500, sectors (today and since your check), summary |

## Preferences, notifications, system
| Method | Path | |
|---|---|---|
| GET / PATCH | `/preferences` | Sensitivity, factor toggles, notification threshold |
| GET | `/notifications` | Latest 50 with unread count |
| POST | `/notifications/{id}/read`, `/notifications/read-all` | Mark read |
| GET | `/system/health` | Components, providers, last update, conflicts, product metrics |
| GET | `/health/live`, `/health/ready` | Load-balancer probes (ready checks the database) |

## Demo (only with `DEMO_MODE=true` and mock providers)
| Method | Path | |
|---|---|---|
| GET | `/demo/scenarios` | Scenarios and the active one |
| POST | `/demo/scenario` `{ "key": "STOCK_SPECIFIC_DROP" }` | Switch, ingest immediately, re-evaluate |
| POST | `/demo/refresh` | Run one ingestion cycle now |
