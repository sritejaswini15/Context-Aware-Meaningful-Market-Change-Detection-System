"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, ArrowRight, CheckCheck, ChevronDown, ListPlus, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { ChangeCard, ChangeSheet } from "@/components/knoww/change-card";
import { AttentionBadge, Delta, LastChecked } from "@/components/knoww/signals";
import { AllCaughtUp, EmptyState, ErrorState, PageHeader } from "@/components/knoww/states";
import { timeAgo } from "@/lib/format";
import { useCheckpoint, useCommandCenter } from "@/lib/hooks";
import type { CommandCenter } from "@/lib/schemas";
import { cn } from "@/lib/utils";

function DataQualityBanner({ cc }: { cc: CommandCenter }) {
  const dq = cc.data_quality;
  const msgs: string[] = [];
  if (dq.stale) msgs.push(`${dq.stale} price${dq.stale === 1 ? " is" : "s are"} stale. Treat those changes with caution.`);
  if (dq.delayed) msgs.push(`${dq.delayed} price${dq.delayed === 1 ? " is" : "s are"} delayed: the primary market feed is unavailable, so a fallback is in use.`);
  if (dq.conflicted) msgs.push(`Data providers disagree on ${dq.conflicted} price${dq.conflicted === 1 ? "" : "s"}. Confidence has been reduced.`);
  if (cc.ai.configured && !cc.ai.available) msgs.push("AI explanations are unavailable. Knoww is explaining changes from verified facts instead.");
  if (!msgs.length) return null;
  return (
    <div role="status" className="flex gap-3 rounded-xl border border-warn/30 bg-warn-soft px-4 py-3 text-sm">
      <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-warn" />
      <ul className="space-y-0.5">
        {msgs.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
    </div>
  );
}

function SummaryStrip({ cc }: { cc: CommandCenter }) {
  const c = cc.counts;
  const items = [
    { label: "High attention", value: c.high, level: "HIGH" as const },
    { label: "Medium attention", value: c.medium, level: "MEDIUM" as const },
    { label: "Quiet", value: c.low, level: "LOW" as const },
  ];
  return (
    <Card className="grid gap-4 p-5 sm:grid-cols-[1.4fr_repeat(3,1fr)] sm:items-center">
      <div>
        <p className="num text-4xl font-semibold tracking-tight">
          {c.meaningful}
          <span className="ml-2 text-lg font-medium text-muted-foreground">meaningful change{c.meaningful === 1 ? "" : "s"}</span>
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          Out of {c.tracked} stock{c.tracked === 1 ? "" : "s"} you follow{c.reviewed ? ` · ${c.reviewed} already reviewed` : ""}
        </p>
      </div>
      {items.map((i) => (
        <div key={i.label} className="flex items-center justify-between gap-2 rounded-lg bg-muted/60 px-3 py-2.5 sm:flex-col sm:items-start">
          <AttentionBadge level={i.level} compact />
          <span className="num text-xl font-semibold">{i.value}</span>
          <span className="sr-only">{i.label}</span>
        </div>
      ))}
    </Card>
  );
}

function MarketContextCard({ cc }: { cc: CommandCenter }) {
  const m = cc.market_context;
  const sectors = m.sectors.slice(0, 6);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Market context</CardTitle>
        <p className="text-sm leading-relaxed">{m.summary}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {m.market && (
          <div className="flex items-center justify-between rounded-lg bg-muted/60 px-3 py-2 text-sm">
            <span className="font-medium">S&amp;P 500</span>
            <span className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>
                Today <Delta value={m.market.day_change_pct} size="sm" />
              </span>
              <span>
                Since check <Delta value={m.market.since_check_pct} size="sm" />
              </span>
            </span>
          </div>
        )}
        <table className="w-full text-sm">
          <caption className="sr-only">Sector performance</caption>
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th scope="col" className="pb-1 font-normal">Sector</th>
              <th scope="col" className="pb-1 text-right font-normal">Today</th>
              <th scope="col" className="pb-1 text-right font-normal">Since check</th>
            </tr>
          </thead>
          <tbody>
            {sectors.map((s) => (
              <tr key={s.symbol} className="border-t border-border/60">
                <th scope="row" className="py-1.5 text-left font-normal">
                  {s.name}
                </th>
                <td className="text-right">
                  <Delta value={s.day_change_pct} size="sm" />
                </td>
                <td className="text-right">{s.since_check_pct === undefined || s.since_check_pct === null ? <span className="text-xs text-muted-foreground">—</span> : <Delta value={s.since_check_pct} size="sm" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-[11px] text-muted-foreground">
          {m.simulated ? "Simulated market (demo data)" : `Session: ${m.session.replace("_", " ").toLowerCase()}`} · Updated {timeAgo(m.last_update)}
        </p>
      </CardContent>
    </Card>
  );
}

function QuietList({ cc }: { cc: CommandCenter }) {
  const [open, setOpen] = useState(false);
  if (!cc.quiet.length) return null;
  return (
    <section aria-labelledby="quiet-h">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded-lg px-1 py-2 text-left focus-visible:outline-2 focus-visible:outline-ring"
      >
        <span>
          <span id="quiet-h" className="text-sm font-semibold">
            Quiet: {cc.quiet.length} stock{cc.quiet.length === 1 ? "" : "s"}
          </span>
          <span className="ml-2 text-sm text-muted-foreground">Knoww decided these don&apos;t need you right now.</span>
        </span>
        <ChevronDown aria-hidden className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <Card className="mt-2 overflow-hidden">
          <ul className="divide-y">
            {cc.quiet.map((q) => (
              <li key={q.symbol}>
                <Link href={`/stocks/${q.symbol}`} className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-3 px-4 py-2.5 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
                  <span className="font-semibold">{q.symbol}</span>
                  <span className="truncate text-muted-foreground">{q.signal?.context_label ?? "—"}</span>
                  <span className="flex items-center gap-3">
                    <Delta value={q.since_check_pct} size="sm" />
                    <span className="num w-8 text-right text-xs text-muted-foreground">{q.signal?.score ?? "—"}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

export default function CommandCenterPage() {
  const { data: cc, isLoading, error, refetch, isFetching } = useCommandCenter();
  const checkpoint = useCheckpoint();
  const [openId, setOpenId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
    );
  }
  if (error || !cc) return <ErrorState error={error} retry={() => refetch()} title="Couldn't load your Command Center" />;

  const noWatchlists = cc.watchlists.length === 0;
  const noStocks = !noWatchlists && cc.counts.tracked === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Command Center"
        title="Since you last checked"
        description={
          <span className="inline-flex items-center gap-2">
            <LastChecked at={cc.last_checked_at} />
            {isFetching && <Loader2 aria-label="Refreshing" className="size-3 animate-spin" />}
          </span>
        }
        actions={
          cc.counts.tracked > 0 && (
            <Button variant="outline" onClick={() => checkpoint.mutate(undefined)} disabled={checkpoint.isPending}>
              {checkpoint.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <CheckCheck aria-hidden />}
              I&apos;m caught up
            </Button>
          )
        }
      />

      <DataQualityBanner cc={cc} />

      {noWatchlists || noStocks ? (
        <EmptyState
          icon={ListPlus}
          title={noWatchlists ? "Create your first watchlist" : "Add stocks to start monitoring"}
          description="Knoww remembers what you saw, then tells you only what meaningfully changed: compared with the stock's sector, the market, and its own normal behaviour."
          action={
            <Button asChild>
              <Link href="/watchlists">{noWatchlists ? "Create a watchlist" : "Add stocks"}</Link>
            </Button>
          }
        />
      ) : (
        <>
          <SummaryStrip cc={cc} />
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="space-y-6">
              <section aria-labelledby="attention-h" className="space-y-3">
                <h2 id="attention-h" className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  Needs your attention
                </h2>
                {cc.needs_attention.length === 0 ? (
                  <AllCaughtUp lastChecked={cc.last_checked_at} marketSummary={cc.market_context.summary} quietCount={cc.quiet.length} />
                ) : (
                  <div className="space-y-3">
                    {cc.needs_attention.map((c) => (
                      <ChangeCard key={c.id} change={c} onOpen={setOpenId} />
                    ))}
                  </div>
                )}
              </section>

              {cc.reviewed.length > 0 && (
                <section aria-labelledby="reviewed-h" className="space-y-3">
                  <h2 id="reviewed-h" className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                    Reviewed
                  </h2>
                  {cc.reviewed.map((c) => (
                    <ChangeCard key={c.id} change={c} onOpen={setOpenId} />
                  ))}
                </section>
              )}

              <QuietList cc={cc} />
            </div>

            <aside className="space-y-4" aria-label="Context">
              <MarketContextCard cc={cc} />
              <Card>
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle>Your watchlists</CardTitle>
                  <Link href="/watchlists" className="text-xs text-muted-foreground hover:text-foreground">
                    Manage
                  </Link>
                </CardHeader>
                <CardContent>
                  <ul className="divide-y">
                    {cc.watchlists.map((w) => (
                      <li key={w.id}>
                        <Link href={`/watchlists/${w.id}`} className="flex items-center justify-between gap-2 py-2.5 text-sm hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                          <span className="min-w-0">
                            <span className="block truncate font-medium">{w.name}</span>
                            <span className="text-xs text-muted-foreground">{w.symbols_count} stocks</span>
                          </span>
                          <span className="flex items-center gap-1.5">
                            {w.high_count > 0 && <AttentionBadge level="HIGH" compact className="px-1.5" />}
                            {w.medium_count > 0 && <AttentionBadge level="MEDIUM" compact className="px-1.5" />}
                            <ArrowRight aria-hidden className="size-4 text-muted-foreground" />
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Recent activity</CardTitle>
                </CardHeader>
                <CardContent>
                  {cc.recent_activity.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nothing yet. Knoww is watching.</p>
                  ) : (
                    <ol className="space-y-2.5">
                      {cc.recent_activity.map((a, i) => (
                        <li key={`${a.kind}-${a.at}-${i}`} className="flex gap-2 text-sm">
                          <span aria-hidden className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", a.attention === "HIGH" ? "bg-high" : a.attention === "MEDIUM" ? "bg-medium" : "bg-low")} />
                          <span className="min-w-0">
                            {a.change_id ? (
                              <button type="button" className="text-left hover:underline" onClick={() => setOpenId(a.change_id ?? null)}>
                                {a.title}
                              </button>
                            ) : (
                              a.title
                            )}
                            <span className="block text-xs text-muted-foreground">{timeAgo(a.at)}</span>
                          </span>
                        </li>
                      ))}
                    </ol>
                  )}
                </CardContent>
              </Card>
              {!cc.ai.configured && (
                <p className="flex gap-2 px-1 text-xs text-muted-foreground">
                  <Sparkles aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                  AI explanations are off in this environment. Knoww explains each change from the same verified facts.
                </p>
              )}
            </aside>
          </div>
        </>
      )}
      <ChangeSheet id={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}
