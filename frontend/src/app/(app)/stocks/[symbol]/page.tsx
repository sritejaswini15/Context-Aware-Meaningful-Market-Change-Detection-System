"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, CalendarClock, Check, GitCompareArrows, LineChart as LineIcon, Loader2, SearchX } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/radix";
import { ExplanationBlock } from "@/components/knoww/change-card";
import { PriceChart, RelativeChart, SinceCheckChart, VolumeChart } from "@/components/knoww/charts";
import { AddToWatchlist } from "@/components/knoww/search";
import {
  AttentionBadge,
  ConfidencePill,
  ContextBars,
  DataNotice,
  Delta,
  FactorBreakdown,
  FreshnessBadge,
  ScoreDial,
  VolumeStat,
} from "@/components/knoww/signals";
import { EmptyState, ErrorState } from "@/components/knoww/states";
import { ApiError } from "@/lib/api";
import { fmtCompact, fmtDateTime, fmtPct, fmtPrice, timeAgo } from "@/lib/format";
import { useAcknowledge, useHistory, useSignalHistory, useStock } from "@/lib/hooks";

export default function StockPage() {
  const { symbol: raw } = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(raw).toUpperCase();
  const { data, isLoading, error, refetch } = useStock(symbol);
  const history = useHistory(symbol);
  const signals = useSignalHistory(symbol);
  const ack = useAcknowledge();
  const [tab, setTab] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-28 w-full" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 404) {
    return (
      <EmptyState
        icon={SearchX}
        title={`We couldn't find ${symbol}`}
        description="The symbol may be wrong, or no market data is available for it right now."
        action={<Button asChild variant="outline"><Link href="/">Back to Command Center</Link></Button>}
      />
    );
  }
  if (error || !data) return <ErrorState error={error} retry={() => refetch()} />;

  const s = data.state;
  const sig = s.signal;
  const watched = data.in_watchlists.length > 0;
  const basisLabel = data.signal_basis === "CHECKPOINT" ? "since you last checked" : "today (vs previous close)";
  const h = history.data;
  const defaultTab = tab ?? (watched && h?.since_check.length ? "since" : "relative");

  return (
    <div className="space-y-6">
      <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft aria-hidden className="size-4" /> Command Center
      </Link>

      {/* 1. What changed, and how important */}
      <Card className="p-5 sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {sig && <AttentionBadge level={sig.attention} />}
              {sig && <Badge>{sig.context_label}</Badge>}
              <FreshnessBadge freshness={s.freshness} />
              {data.change?.state === "ACKNOWLEDGED" && (
                <Badge variant="outline">
                  <Check aria-hidden /> Reviewed
                </Badge>
              )}
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{s.name}</h1>
              <p className="text-sm text-muted-foreground">
                <span className="font-semibold text-foreground">{s.symbol}</span>
                {[s.exchange, s.sector].filter(Boolean).map((x) => ` · ${x}`)}
              </p>
            </div>
            <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
              <div>
                <p className="num text-3xl font-semibold">{fmtPrice(s.price, s.currency)}</p>
                <p className="text-xs text-muted-foreground">Updated {s.freshness ? timeAgo(s.freshness.market_timestamp) : "—"}</p>
              </div>
              <div>
                <Delta value={data.signal_basis === "CHECKPOINT" ? s.since_check_pct : s.day_change_pct} size="xl" />
                <p className="text-xs text-muted-foreground">{basisLabel}</p>
              </div>
              <div className="space-y-0.5 pb-1 text-sm">
                <p className="text-muted-foreground">
                  Today <span className="num font-medium text-foreground">{fmtPct(s.day_change_pct)}</span>
                </p>
                {s.baseline && (
                  <p className="text-xs text-muted-foreground">
                    You last saw {fmtPrice(s.baseline.price)} · {fmtDateTime(s.baseline.checked_at)}
                  </p>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4 lg:flex-col lg:items-end">
            {sig && (
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Signal score</p>
                  <ConfidencePill level={sig.confidence_level} value={sig.confidence} />
                </div>
                <ScoreDial score={sig.score} attention={sig.attention} size={56} />
              </div>
            )}
            <div className="flex gap-2">
              {data.change && data.change.state !== "ACKNOWLEDGED" && (
                <Button onClick={() => ack.mutate(data.change!.id)} disabled={ack.isPending}>
                  {ack.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <Check aria-hidden />} Mark as reviewed
                </Button>
              )}
              <AddToWatchlist symbol={s.symbol} inWatchlists={data.in_watchlists} size="default" />
            </div>
          </div>
        </div>
        {!watched && (
          <p className="mt-4 rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
            You don&apos;t follow {s.symbol} yet, so this signal compares today&apos;s move with the previous close. Add it to a watchlist and Knoww will measure changes from the moment you last checked.
          </p>
        )}
        <DataNotice className="mt-4" status={s.freshness?.status} caveats={sig?.caveats} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-6">
          {/* 2. Why */}
          <Card>
            <CardContent className="pt-5">
              {data.explanation ? (
                <ExplanationBlock explanation={data.explanation} />
              ) : (
                <section className="space-y-2">
                  <h2 className="text-sm font-semibold">Why it matters</h2>
                  <p className="text-sm">{sig?.headline ?? "No signal yet."}</p>
                  <p className="text-xs text-muted-foreground">
                    {sig?.attention === "LOW" ? "Knoww doesn't consider this a meaningful change, so it isn't asking for your attention." : "No active change for this stock."}
                  </p>
                </section>
              )}
            </CardContent>
          </Card>

          {/* 3. Context, then charts */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <LineIcon aria-hidden className="size-4" /> Charts
              </CardTitle>
            </CardHeader>
            <CardContent>
              {history.isLoading ? (
                <Skeleton className="h-56 w-full" />
              ) : !h || !h.history_available ? (
                <p className="py-10 text-center text-sm text-muted-foreground">
                  No historical data is available from the current market data provider. Knoww is not inventing a chart.
                </p>
              ) : (
                <Tabs value={defaultTab} onValueChange={setTab}>
                  <TabsList className="flex-wrap">
                    {watched && h.since_check.length > 0 && <TabsTrigger value="since">Since you checked</TabsTrigger>}
                    <TabsTrigger value="relative">vs sector &amp; market</TabsTrigger>
                    <TabsTrigger value="price">Price</TabsTrigger>
                    <TabsTrigger value="volume">Volume</TabsTrigger>
                  </TabsList>
                  {watched && h.since_check.length > 0 && (
                    <TabsContent value="since">
                      <SinceCheckChart data={h.since_check} symbol={symbol} sectorSymbol={h.sector_symbol} />
                    </TabsContent>
                  )}
                  <TabsContent value="relative">
                    <RelativeChart data={h.relative} symbol={symbol} sectorSymbol={h.sector_symbol} />
                  </TabsContent>
                  <TabsContent value="price">
                    <PriceChart data={h.price} symbol={symbol} />
                  </TabsContent>
                  <TabsContent value="volume">
                    {h.volume.available ? (
                      <VolumeChart data={h.volume.bars} avg={h.volume.avg_20d} />
                    ) : (
                      <p className="py-10 text-center text-sm text-muted-foreground">Volume unavailable from the data provider.</p>
                    )}
                  </TabsContent>
                </Tabs>
              )}
            </CardContent>
          </Card>

          {/* Timeline */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarClock aria-hidden className="size-4" /> Timeline
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {data.events.length === 0 ? (
                <p className="text-sm text-muted-foreground">No company events in the available data. Knoww never invents events.</p>
              ) : (
                <ul className="space-y-2.5">
                  {data.events.map((e) => (
                    <li key={e.id} className="flex gap-3 text-sm">
                      <Badge variant={e.event_type === "EARNINGS" ? "high" : "default"} className="mt-0.5 shrink-0">
                        {e.event_type.toLowerCase()}
                      </Badge>
                      <span className="min-w-0">
                        {e.url ? (
                          <a href={e.url} target="_blank" rel="noreferrer noopener" className="hover:underline">
                            {e.headline}
                          </a>
                        ) : (
                          e.headline
                        )}
                        <span className="block text-xs text-muted-foreground">
                          {fmtDateTime(e.event_time)}
                          {e.source ? ` · ${e.source}` : ""}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {signals.data && signals.data.signals.length > 0 && (
                <div className="space-y-2 border-t pt-4">
                  <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Signal history</h3>
                  <ol className="space-y-1.5">
                    {signals.data.signals.slice(0, 8).map((x) => (
                      <li key={x.id} className="grid grid-cols-[5.5rem_4.5rem_1fr] items-center gap-2 text-xs">
                        <span className="text-muted-foreground">{fmtDateTime(x.at)}</span>
                        <AttentionBadge level={x.attention} compact className="justify-self-start" />
                        <span className="flex items-center gap-2">
                          <span className="num w-6 text-right font-medium">{x.score}</span>
                          <Delta value={x.change_pct} size="sm" />
                          {x.data_status && x.data_status !== "LIVE" && x.data_status !== "FRESH" && <Badge variant="warn">{x.data_status.toLowerCase()}</Badge>}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-4" aria-label="Context and data">
          <Card>
            <CardHeader>
              <CardTitle>Is it the stock, the sector or the market?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <ContextBars
                stock={data.signal_basis === "CHECKPOINT" ? s.since_check_pct : s.day_change_pct}
                sector={data.sector?.since_check_pct ?? (data.signal_basis === "CHECKPOINT" ? null : data.sector?.day_change_pct)}
                market={data.market?.since_check_pct ?? (data.signal_basis === "CHECKPOINT" ? null : data.market?.day_change_pct)}
                sectorName={s.sector}
                label={data.signal_basis === "CHECKPOINT" ? "Since you last checked" : "Today"}
              />
              {data.signal_basis === "CHECKPOINT" && (
                <ContextBars stock={s.day_change_pct} sector={data.sector?.day_change_pct} market={data.market?.day_change_pct} sectorName={s.sector} label="Today" />
              )}
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Volume</span>
                <VolumeStat ratio={s.volume_ratio} />
              </div>
            </CardContent>
          </Card>

          {data.factors.length > 0 && sig && (
            <Card>
              <CardHeader>
                <CardTitle>Score breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <FactorBreakdown factors={data.factors} score={sig.score} />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Data quality</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
                <dt className="text-muted-foreground">Freshness</dt>
                <dd className="text-right">{s.freshness ? <FreshnessBadge freshness={s.freshness} /> : "—"}</dd>
                <dt className="text-muted-foreground">Source</dt>
                <dd className="truncate text-right">
                  {s.freshness?.provider ?? "—"}
                  {s.freshness?.simulated ? " (simulated)" : ""}
                </dd>
                <dt className="text-muted-foreground">Cross-checked</dt>
                <dd className="text-right">{s.freshness && s.freshness.sources_count > 1 ? `${s.freshness.sources_count} providers` : "Single provider"}</dd>
                <dt className="text-muted-foreground">Typical daily move</dt>
                <dd className="num text-right">{data.stats.daily_volatility_pct ? `${data.stats.daily_volatility_pct.toFixed(1)}%` : "Unknown"}</dd>
                <dt className="text-muted-foreground">20-day avg volume</dt>
                <dd className="num text-right">{fmtCompact(data.stats.avg_volume_20d)}</dd>
              </dl>
              {data.conflict && (
                <div className="mt-3 space-y-2 rounded-lg border border-warn/30 bg-warn-soft p-3">
                  <p className="flex items-center gap-1.5 text-xs font-semibold">
                    <GitCompareArrows aria-hidden className="size-3.5 text-warn" /> Providers disagree ({data.conflict.spread_pct.toFixed(2)}% apart)
                  </p>
                  <table className="w-full text-xs">
                    <caption className="sr-only">Provider observations</caption>
                    <tbody>
                      {data.conflict.observations.map((o) => (
                        <tr key={o.provider}>
                          <th scope="row" className="py-0.5 text-left font-normal">
                            {o.provider}
                            {o.provider === data.conflict!.chosen_provider && <span className="ml-1 text-muted-foreground">(preferred)</span>}
                          </th>
                          <td className="num text-right">{fmtPrice(o.price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="text-[11px] text-muted-foreground">{data.conflict.resolution}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
