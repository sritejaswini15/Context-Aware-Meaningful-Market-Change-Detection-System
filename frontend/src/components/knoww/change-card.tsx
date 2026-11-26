"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Check, ChevronRight, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/radix";
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
import { fmtDateTime, fmtPct, fmtPrice, timeAgo } from "@/lib/format";
import { useAcknowledge, useChange, useMarkSeen } from "@/lib/hooks";
import type { ChangeCard as Change, Explanation } from "@/lib/schemas";
import { cn } from "@/lib/utils";

const ACCENT = { HIGH: "before:bg-high", MEDIUM: "before:bg-medium", LOW: "before:bg-low" } as const;

export function ChangeCard({ change, onOpen, compact = false }: { change: Change; onOpen: (id: string) => void; compact?: boolean }) {
  const reviewed = change.state === "ACKNOWLEDGED";
  return (
    <Card
      className={cn(
        "relative overflow-hidden before:absolute before:inset-y-0 before:left-0 before:w-1",
        ACCENT[change.attention],
        reviewed && "opacity-75",
      )}
    >
      <article aria-labelledby={`chg-${change.id}`} className={cn("grid gap-4 p-4 pl-5 sm:p-5 sm:pl-6", !compact && "md:grid-cols-[1fr_auto]")}>
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <AttentionBadge level={change.attention} />
            {change.state === "NEW" && <Badge variant="outline">New</Badge>}
            {reviewed && (
              <Badge variant="outline">
                <Check aria-hidden /> Reviewed
              </Badge>
            )}
            <Badge variant="default">{change.context_label}</Badge>
          </div>
          <div className="flex flex-wrap items-end gap-x-5 gap-y-2">
            <div className="min-w-0">
              <h3 id={`chg-${change.id}`} className="truncate text-base font-semibold">
                {change.name}
              </h3>
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{change.symbol}</span> · {fmtPrice(change.price)}
              </p>
            </div>
            <div>
              <Delta value={change.change_pct} size="lg" />
              <p className="text-xs text-muted-foreground">since you last checked</p>
            </div>
            <div className="text-xs text-muted-foreground">
              Today <span className="num font-medium text-foreground">{fmtPct(change.day_change_pct)}</span>
            </div>
          </div>
          <p className="text-sm leading-relaxed text-foreground/90">{change.headline}</p>
          <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <div>
              <dt className="inline">{change.sector ?? "Sector"}: </dt>
              <dd className="num inline font-medium text-foreground">{fmtPct(change.sector_change_pct)}</dd>
            </div>
            <div>
              <dt className="inline">Market: </dt>
              <dd className="num inline font-medium text-foreground">{fmtPct(change.market_change_pct)}</dd>
            </div>
            <div>
              <VolumeStat ratio={change.volume_ratio} />
            </div>
          </dl>
          <DataNotice status={change.data_status} caveats={change.caveats} />
        </div>
        <div className={cn("flex items-center justify-between gap-4", !compact && "md:flex-col md:items-end md:justify-between")}>
          <div className="flex items-center gap-3">
            <div className="text-right text-xs text-muted-foreground">
              <div>Signal</div>
              <ConfidencePill level={change.confidence_level} />
            </div>
            <ScoreDial score={change.score} attention={change.attention} />
          </div>
          <Button variant={reviewed ? "outline" : "default"} size="sm" onClick={() => onOpen(change.id)} aria-label={`See why ${change.symbol} matters`}>
            See why <ChevronRight aria-hidden />
          </Button>
        </div>
      </article>
    </Card>
  );
}

export function ExplanationBlock({ explanation }: { explanation: Explanation }) {
  return (
    <section aria-label="Why it matters" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Why it matters</h3>
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          {explanation.status === "PENDING" || explanation.status === "UPDATING" ? (
            <>
              <Loader2 aria-hidden className="size-3 animate-spin" /> Writing AI explanation…
            </>
          ) : explanation.source === "AI" ? (
            <>
              <Sparkles aria-hidden className="size-3" /> AI explanation of verified facts
            </>
          ) : (
            <>Generated from verified facts{explanation.error ? ` (${/not configured/i.test(explanation.error) ? "AI not configured" : "AI unavailable"})` : ""}</>
          )}
        </span>
      </div>
      <p className="text-sm font-medium leading-relaxed">{explanation.summary}</p>
      <p className="text-sm leading-relaxed text-muted-foreground">{explanation.why_it_matters}</p>
      {explanation.key_factors.length > 0 && (
        <ul className="space-y-1 text-sm">
          {explanation.key_factors.map((k) => (
            <li key={k} className="flex gap-2">
              <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-foreground/60" />
              <span>{k}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-muted-foreground">
        Prices, percentages and scores are calculated by Knoww&apos;s deterministic engine. Explanations never add facts. This is not investment advice.
      </p>
    </section>
  );
}

/** Side sheet with the full reasoning for one change. Opening it marks the change as seen. */
export function ChangeSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data, isLoading, isError } = useChange(id);
  const seen = useMarkSeen();
  const ack = useAcknowledge();

  useEffect(() => {
    if (id && data?.state === "NEW" && !seen.isPending) seen.mutate(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, data?.state]);

  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && onClose()}>
      <DialogContent side="right" aria-describedby={undefined}>
        {isLoading || !data ? (
          <div className="space-y-4 pt-6">
            <DialogTitle className="sr-only">Loading change</DialogTitle>
            {isError ? <p className="text-sm text-muted-foreground">This change could not be loaded.</p> : <Skeleton className="h-40 w-full" />}
          </div>
        ) : (
          <div className="space-y-6">
            <header className="space-y-3 pr-6">
              <div className="flex flex-wrap items-center gap-2">
                <AttentionBadge level={data.attention} />
                <Badge>{data.context_label}</Badge>
                <FreshnessBadge freshness={data.freshness} />
              </div>
              <DialogTitle>
                {data.name} <span className="text-muted-foreground">({data.symbol})</span>
              </DialogTitle>
              <DialogDescription>
                {fmtPrice(data.baseline_price)} when you last checked ({fmtDateTime(data.checked_at)}) → {fmtPrice(data.price)} now
              </DialogDescription>
              <div className="flex items-end gap-6">
                <div>
                  <Delta value={data.change_pct} size="xl" />
                  <p className="text-xs text-muted-foreground">since you last checked</p>
                </div>
                <div className="pb-1 text-sm text-muted-foreground">
                  Today <span className="num font-medium text-foreground">{fmtPct(data.day_change_pct)}</span>
                </div>
              </div>
            </header>
            <DataNotice status={data.data_status} caveats={data.caveats} />
            <ExplanationBlock explanation={data.explanation} />
            <ContextBars stock={data.change_pct} sector={data.sector_change_pct} market={data.market_change_pct} sectorName={data.sector} />
            <section aria-label="Score breakdown" className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">How the score was calculated</h3>
                <ConfidencePill level={data.confidence_level} value={data.confidence} />
              </div>
              <FactorBreakdown factors={data.factors} score={data.score} />
            </section>
            {data.history.length > 0 && (
              <section aria-label="Earlier changes" className="space-y-2">
                <h3 className="text-sm font-semibold">Earlier changes for {data.symbol}</h3>
                <ul className="divide-y rounded-lg border text-sm">
                  {data.history.slice(0, 5).map((h) => (
                    <li key={h.id} className="flex items-center justify-between gap-2 px-3 py-2">
                      <span className="flex items-center gap-2">
                        <AttentionBadge level={h.peak_attention} compact />
                        <Delta value={h.change_pct} size="sm" />
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {h.state.toLowerCase()} · {timeAgo(h.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <footer className="sticky bottom-0 -mx-6 flex flex-col gap-2 border-t bg-popover px-6 py-4 sm:flex-row sm:justify-between">
              <Button variant="outline" asChild>
                <Link href={`/stocks/${data.symbol}`} onClick={onClose}>
                  Investigate {data.symbol}
                </Link>
              </Button>
              {data.state === "ACKNOWLEDGED" ? (
                <Button variant="secondary" disabled>
                  <Check aria-hidden /> Reviewed
                </Button>
              ) : (
                <Button
                  onClick={() => ack.mutate(data.id, { onSuccess: onClose })}
                  disabled={ack.isPending}
                >
                  {ack.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <Check aria-hidden />} Mark as reviewed
                </Button>
              )}
            </footer>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
