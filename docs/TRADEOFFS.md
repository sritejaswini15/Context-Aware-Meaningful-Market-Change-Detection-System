# Tradeoffs

**Deterministic scoring rather than a black-box ML model.**
Users need to know *why* something deserves attention, and the challenge is about
meaningful change, not price prediction. A transparent sum of factor points can be
explained, tested with exact expectations, tuned by sensitivity, and audited after the
fact (`signal_scores` stores inputs and points). An ML model could later *propose*
weights, evaluated against stored outcomes, without becoming the decision-maker.

**AI explains, it doesn't decide.**
Financial facts must be deterministic and auditable. The model gets computed facts and
may only restate them. Numbers are checked against the facts, attention and confidence
must match, and failures fall back to deterministic text. Knoww works fully without AI,
and the AI provider can be replaced behind one interface.

**PostgreSQL as the source of truth.**
Users, watchlists, checkpoints, snapshots, events, signals and notifications are
relational, with ownership and foreign keys. Partial unique indexes and
`ON CONFLICT DO NOTHING` provide idempotency without extra infrastructure. Redis is only
an accelerator. If it disappears, the app keeps working.

**A modular monolith, not microservices.**
Clear module boundaries (providers, ingestion, engine, change detection, AI) in one
deployable, run as api, worker and web. That gives independent scaling where it matters
without distributed transactions, service discovery, or ten pipelines to keep in sync.

**Queues for slow work.**
Market ingestion and AI calls are slow and can fail. They run on workers via SQS with
retries and a DLQ, so user requests stay fast. Deterministic evaluation is cheap, so it
also runs read-through in the API, keeping screens consistent even when the queue lags.

**EventBridge Scheduler → SQS, rather than cron in a container.**
Schedules are managed, observable infrastructure. Workers stay stateless consumers, and
overlapping triggers are absorbed by a distributed lock.

**Provider abstraction plus a mock provider.**
External market APIs change, rate-limit and fail. Swapping vendors touches only
`providers/`. The deterministic mock with eleven scenarios makes the demo reproducible
and exercises the failure paths (stale, conflict, outage) that are hard to trigger for real.

**Checkpoint baselines store benchmark prices.**
This costs a little storage but makes "sector and market over the same window" exact.
Recomputing benchmark history for arbitrary windows would be slower and less reliable.

**Snapshots only on change.**
Writing a row per poll would grow the table with time and user count. Writing on change
grows it with actual market movement. The cost is that intraday charts are step-like.

**Read-through evaluation on GET.**
A GET that can write (idempotently) is unusual. It was chosen so a user returning to the
app always sees results computed from the latest stored market state, without depending
on worker latency. Writes happen only when inputs actually changed.

**Cookies + same-origin proxy rather than tokens in the browser.**
httpOnly cookies keep tokens away from JavaScript, and the ALB path rule (or the Next.js
rewrite locally) keeps everything same-origin, so CORS stays closed.

**Mutable `latest` image tag in ECS.**
It keeps deploys simple (`force-new-deployment`). Images are also tagged with the commit
SHA. Pinning task definitions to the SHA is the next hardening step.

**Not built on purpose:** trading, portfolios, social features, chat-style AI, technical
indicators, and SMS, push or WhatsApp channels. Knoww's value is deciding when *not* to bother you.
