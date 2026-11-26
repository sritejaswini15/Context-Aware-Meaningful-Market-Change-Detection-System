"use client";

import { AlertTriangle, ArrowDownRight, ArrowUpRight, Clock, Gauge, GitCompareArrows, Minus, Radio, ShieldCheck, Zap } from "lucide-react";

import { Badge } from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/radix";
import { fmtAge, fmtPct, fmtRatio, timeAgo, volumeLabel } from "@/lib/format";
import type { Attention, Factor, Freshness } from "@/lib/schemas";
import { cn } from "@/lib/utils";

const ATT: Record<Attention, { label: string; variant: "high" | "medium" | "low"; icon: typeof Zap }> = {
  HIGH: { label: "High attention", variant: "high", icon: Zap },
  MEDIUM: { label: "Medium attention", variant: "medium", icon: Gauge },
  LOW: { label: "Low attention", variant: "low", icon: Minus },
};

export function AttentionBadge({ level, compact = false, className }: { level: Attention; compact?: boolean; className?: string }) {
  const a = ATT[level];
  const Icon = a.icon;
  return (
    <Badge variant={a.variant} className={cn("uppercase tracking-wide", className)}>
      <Icon aria-hidden />
      {compact ? level : a.label}
    </Badge>
  );
}

/** Signed % change. Direction is shown with an arrow and a sign, never colour alone. */
export function Delta({ value, className, size = "md", digits = 1 }: { value: number | null | undefined; className?: string; size?: "sm" | "md" | "lg" | "xl"; digits?: number }) {
  if (value === null || value === undefined) return <span className={cn("text-muted-foreground", className)}>—</span>;
  const flat = Math.abs(value) < 0.05;
  const Icon = flat ? Minus : value > 0 ? ArrowUpRight : ArrowDownRight;
  const sizes = { sm: "text-xs", md: "text-sm", lg: "text-lg", xl: "text-3xl" };
  return (
    <span className={cn("num inline-flex items-center gap-0.5 font-semibold", sizes[size], flat ? "text-muted-foreground" : value > 0 ? "text-up" : "text-down", className)}>
      <Icon aria-hidden className={size === "xl" ? "size-7" : size === "lg" ? "size-5" : "size-3.5"} />
      {fmtPct(value, digits)}
    </span>
  );
}

const FRESH_STYLE: Record<Freshness["status"], { variant: "ok" | "default" | "warn" | "high"; icon: typeof Radio }> = {
  LIVE: { variant: "ok", icon: Radio },
  FRESH: { variant: "default", icon: Clock },
  DELAYED: { variant: "warn", icon: Clock },
  STALE: { variant: "warn", icon: AlertTriangle },
  CONFLICTED: { variant: "warn", icon: GitCompareArrows },
};

export function FreshnessBadge({ freshness, className }: { freshness: Freshness | null | undefined; className?: string }) {
  if (!freshness) return <Badge variant="warn">No data</Badge>;
  const st = FRESH_STYLE[freshness.status];
  const Icon = st.icon;
  const tip = [
    `${freshness.label} · ${fmtAge(freshness.age_seconds)}`,
    `Source: ${freshness.provider}${freshness.simulated ? " (simulated market)" : ""}`,
    freshness.sources_count > 1 ? `Cross-checked with ${freshness.sources_count} providers` : "Single provider",
  ].join(" · ");
  return (
    <Tooltip content={tip}>
      <span tabIndex={0} className="inline-flex focus-visible:outline-2 focus-visible:outline-ring rounded-md">
        <Badge variant={st.variant} className={className}>
          <Icon aria-hidden />
          {freshness.status === "CONFLICTED" ? "Conflicted" : freshness.label}
        </Badge>
      </span>
    </Tooltip>
  );
}

export function ConfidencePill({ level, value }: { level: Attention; value?: number }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <ShieldCheck aria-hidden className={cn("size-3.5", level === "HIGH" ? "text-ok" : level === "MEDIUM" ? "text-warn" : "text-down")} />
      {level === "HIGH" ? "High" : level === "MEDIUM" ? "Medium" : "Low"} confidence
      {value !== undefined && <span className="num">({Math.round(value * 100)}%)</span>}
    </span>
  );
}

export function ScoreDial({ score, attention, size = 44 }: { score: number; attention: Attention; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const color = attention === "HIGH" ? "var(--high)" : attention === "MEDIUM" ? "var(--medium)" : "var(--low)";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`Signal score ${score} out of 100`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--muted)" strokeWidth={4} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={4} strokeLinecap="round" strokeDasharray={`${(score / 100) * c} ${c}`} />
      </svg>
      <span className="num absolute inset-0 flex items-center justify-center text-sm font-semibold">{score}</span>
    </div>
  );
}

/** Stock vs sector vs market over the same window: answers "is this stock-specific?". */
export function ContextBars({
  stock,
  sector,
  market,
  sectorName,
  label = "Since you last checked",
}: {
  stock: number | null | undefined;
  sector: number | null | undefined;
  market: number | null | undefined;
  sectorName?: string | null;
  label?: string;
}) {
  const rows = [
    { name: "This stock", v: stock },
    { name: sectorName ? `${sectorName} sector` : "Sector", v: sector },
    { name: "Market (S&P 500)", v: market },
  ];
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.v ?? 0)));
  return (
    <figure className="space-y-2" aria-label={`${label}: stock compared with sector and market`}>
      <figcaption className="text-xs font-medium text-muted-foreground">{label}</figcaption>
      {rows.map((r) => (
        <div key={r.name} className="grid grid-cols-[8.5rem_1fr_4rem] items-center gap-2 text-xs">
          <span className="truncate text-muted-foreground">{r.name}</span>
          <div className="relative h-2.5 rounded-full bg-muted">
            <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
            {r.v !== null && r.v !== undefined && (
              <div
                className={cn("absolute inset-y-0 rounded-full", r.v >= 0 ? "bg-up/80 left-1/2" : "bg-down/80 right-1/2")}
                style={{ width: `${(Math.abs(r.v) / max) * 50}%` }}
              />
            )}
          </div>
          <span className="text-right">{r.v === null || r.v === undefined ? <span className="text-muted-foreground">n/a</span> : <Delta value={r.v} size="sm" />}</span>
        </div>
      ))}
    </figure>
  );
}

export function VolumeStat({ ratio }: { ratio: number | null | undefined }) {
  if (ratio === null || ratio === undefined) return <span className="text-xs text-muted-foreground">Volume unavailable</span>;
  return (
    <span className={cn("num text-xs", ratio >= 2 ? "font-semibold text-foreground" : "text-muted-foreground")}>
      {fmtRatio(ratio)} normal volume <span className="text-muted-foreground">· {volumeLabel(ratio)}</span>
    </span>
  );
}

export function FactorBreakdown({ factors, score }: { factors: Factor[]; score: number }) {
  return (
    <div className="space-y-3">
      {factors.map((f) => (
        <div key={f.key} className={cn("space-y-1", f.enabled === false && "opacity-50")}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="font-medium">{f.label}</span>
            <span className="num text-muted-foreground">
              <span className="font-semibold text-foreground">{f.points.toFixed(0)}</span> / {f.max_points.toFixed(0)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden>
            <div className="h-full rounded-full bg-primary/70" style={{ width: `${f.max_points ? (f.points / f.max_points) * 100 : 0}%` }} />
          </div>
          <p className="text-xs text-muted-foreground">{f.detail}</p>
        </div>
      ))}
      <div className="flex items-baseline justify-between border-t pt-2 text-sm">
        <span className="font-semibold">Signal score</span>
        <span className="num font-semibold">{score} / 100</span>
      </div>
    </div>
  );
}

export function DataNotice({ status, caveats, className }: { status?: string; caveats?: string[]; className?: string }) {
  const relevant = (caveats ?? []).filter((c) => /stale|disagree|unavailable|Capped|delayed/i.test(c));
  if (!relevant.length && status !== "STALE" && status !== "CONFLICTED" && status !== "DELAYED") return null;
  return (
    <div role="note" className={cn("flex gap-2 rounded-lg border border-warn/30 bg-warn-soft px-3 py-2 text-xs text-foreground", className)}>
      <AlertTriangle aria-hidden className="mt-0.5 size-3.5 shrink-0 text-warn" />
      <div className="space-y-0.5">
        {status === "DELAYED" && !relevant.length && <p>Prices are delayed. Knoww is using a fallback feed.</p>}
        {relevant.map((c) => (
          <p key={c}>{c}</p>
        ))}
      </div>
    </div>
  );
}

export function LastChecked({ at }: { at: string | null | undefined }) {
  if (!at) return <span>Not checked yet</span>;
  return (
    <span>
      Last checked{" "}
      <time dateTime={at} className="font-medium text-foreground">
        {new Date(at).toLocaleString([], { hour: "numeric", minute: "2-digit", month: "short", day: "numeric" })}
      </time>{" "}
      · {timeAgo(at)}
    </span>
  );
}
