# Reference analysis

Two repositories were reviewed once, before implementation, as reference material.

## Licensing

| Repository | License claim | LICENSE file in the archive | Decision |
|---|---|---|---|
| `adrianhajdin/signalist_stock-tracker-app` | README says MIT | **Not included** | Inspiration only, no code copied |
| `Mkayuni/stockTrack` | README badge says MIT | **Not included** | Inspiration only, no code copied |

Neither archive ships a LICENSE file. A README badge is not a license grant, so **no
source code was copied**. Knoww's code is original. Separately, `stockTrack` commits a
`server/.env` file to the repository, which Knoww deliberately avoids (`.env.example` only, secrets in Secrets Manager).

## Signalist (Next.js 15 / TypeScript)

- **Architecture**: Next.js App Router with server actions calling Finnhub directly. MongoDB via Mongoose, Better Auth, Inngest for event-driven/cron jobs (welcome email, daily news summary with AI), Nodemailer.
- **Frontend patterns**: shadcn/ui (new-york) on Radix, `cmdk` command palette for search, sonner toasts, route groups `(auth)` / `(root)`.
- **Watchlist**: one flat collection keyed by `(userId, symbol)` with a unique index. There are no named watchlists and no price memory.
- **Search**: Finnhub `/search` plus `/stock/profile2` for popular symbols, cached with React `cache`.
- **Charts**: embedded TradingView widgets (third-party iframes, no data ownership).
- **Market data**: the Finnhub API key is read in server actions, with a `NEXT_PUBLIC_` fallback that would expose it to the browser.
- **AI**: summarises news for email digests.
- **Realtime**: none. The data is request-time only.

**Taken as inspiration:** command-palette search, route-group layout, shadcn/Radix
component approach, Finnhub endpoint choices (`/quote`, `/search`, `/stock/profile2`, `/company-news`).
**Avoided:** API keys reachable from the browser, iframe charts (Knoww's charts are
drawn from its own data, so they can say *since you checked*), MongoDB for relational data.

## stockTrack (React CRA + Express + Sequelize)

- **Architecture**: CRA frontend and an Express REST API with controllers / models / migrations (Sequelize + SQLite) and JWT middleware.
- **Backend patterns**: controller-per-resource, an `authenticateToken` middleware, an admin role check, Sequelize migrations including volume made nullable.
- **Market data**: stock prices stored per symbol in a `stockPrice` table, with fetch-and-persist controllers.
- **Frontend**: stock cards, a graph component, search fields, a portfolio page.
- **Realtime**: the README describes WebSocket updates, but the archived source has no WebSocket code (outside `node_modules`). Updates are request-driven.

**Taken as inspiration:** a conventional REST resource layout, persisting observations
instead of fetching on every view, and treating volume as nullable data.
**Avoided:** SQLite in production, the committed `.env`, prices without freshness metadata. Knoww schedules ingestion (EventBridge → SQS → worker) and refreshes clients on focus or interval. WebSockets add little when the signal changes per minute, not per tick.

## What Knoww does differently

Neither reference remembers what the user saw, compares moves with their sector or the
market, scores significance, models data freshness or conflicts, or degrades gracefully.
Those are the parts Knoww is built around.
