"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fmtCompact, fmtPct, fmtPrice } from "@/lib/format";
import type { History } from "@/lib/schemas";

const axis = { stroke: "var(--muted-foreground)", fontSize: 11, tickLine: false, axisLine: false } as const;
const tooltipStyle = {
  contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--popover-foreground)" },
  labelStyle: { color: "var(--muted-foreground)" },
};
const COLORS = { stock: "var(--foreground)", sector: "var(--high)", market: "var(--low)" };

function Legend({ items }: { items: { key: keyof typeof COLORS; label: string; dashed?: boolean }[] }) {
  return (
    <ul className="flex flex-wrap gap-4 text-xs text-muted-foreground" aria-hidden>
      {items.map((i) => (
        <li key={i.key} className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ background: COLORS[i.key], opacity: i.dashed ? 0.7 : 1 }} />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

function Frame({ question, children, summary }: { question: string; children: React.ReactNode; summary: string }) {
  return (
    <figure className="space-y-3">
      <figcaption className="text-sm font-medium">{question}</figcaption>
      <div className="h-56 w-full" role="img" aria-label={summary}>
        {children}
      </div>
    </figure>
  );
}

export function SinceCheckChart({ data, symbol, sectorSymbol }: { data: History["since_check"]; symbol: string; sectorSymbol: string | null }) {
  const rows = data.map((d) => ({ ...d, t: new Date(d.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) }));
  const last = rows.at(-1);
  return (
    <div className="space-y-2">
      <Frame
        question="What happened since you last checked?"
        summary={`${symbol} ${fmtPct(last?.stock)} vs sector ${fmtPct(last?.sector)} and market ${fmtPct(last?.market)} since your checkpoint`}
      >
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="t" {...axis} minTickGap={40} />
            <YAxis {...axis} width={48} tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
            <ReferenceLine y={0} stroke="var(--border)" />
            <Tooltip {...tooltipStyle} formatter={(v) => fmtPct(Number(v), 2)} />
            <Line type="stepAfter" dataKey="stock" name={symbol} stroke={COLORS.stock} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="stepAfter" dataKey="sector" name={sectorSymbol ?? "Sector"} stroke={COLORS.sector} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line type="stepAfter" dataKey="market" name="S&P 500" stroke={COLORS.market} strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Frame>
      <Legend items={[{ key: "stock", label: symbol }, { key: "sector", label: `Sector (${sectorSymbol ?? "n/a"})` }, { key: "market", label: "Market (SPY)", dashed: true }]} />
    </div>
  );
}

export function PriceChart({ data, symbol }: { data: History["price"]; symbol: string }) {
  const first = data[0]?.close;
  const last = data.at(-1)?.close;
  return (
    <Frame question={`How has ${symbol} moved over the last ${data.length} trading days?`} summary={`${symbol} from ${fmtPrice(first)} to ${fmtPrice(last)}`}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" {...axis} minTickGap={50} tickFormatter={(d: string) => d.slice(5)} />
          <YAxis {...axis} width={56} domain={["auto", "auto"]} tickFormatter={(v: number) => `$${v.toFixed(0)}`} />
          <Tooltip {...tooltipStyle} formatter={(v) => fmtPrice(Number(v))} />
          <Line type="monotone" dataKey="close" name="Close" stroke={COLORS.stock} strokeWidth={1.75} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Frame>
  );
}

export function RelativeChart({ data, symbol, sectorSymbol }: { data: History["relative"]; symbol: string; sectorSymbol: string | null }) {
  const last = data.at(-1);
  return (
    <div className="space-y-2">
      <Frame
        question="Is it keeping pace with its sector and the market?"
        summary={`Over the period: ${symbol} ${fmtPct(last?.stock)}, sector ${fmtPct(last?.sector)}, market ${fmtPct(last?.market)}`}
      >
        <ResponsiveContainer>
          <LineChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="date" {...axis} minTickGap={50} tickFormatter={(d: string) => d.slice(5)} />
            <YAxis {...axis} width={48} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
            <ReferenceLine y={0} stroke="var(--border)" />
            <Tooltip {...tooltipStyle} formatter={(v) => fmtPct(Number(v), 1)} />
            <Line type="monotone" dataKey="stock" name={symbol} stroke={COLORS.stock} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="sector" name="Sector" stroke={COLORS.sector} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="market" name="Market" stroke={COLORS.market} strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </Frame>
      <Legend items={[{ key: "stock", label: symbol }, { key: "sector", label: `Sector (${sectorSymbol ?? "n/a"})` }, { key: "market", label: "Market (SPY)", dashed: true }]} />
    </div>
  );
}

export function VolumeChart({ data, avg }: { data: History["volume"]["bars"]; avg: number | null }) {
  const recent = data.slice(-30);
  return (
    <Frame question="How unusual is recent trading volume?" summary={`Daily volume for the last ${recent.length} days with a 20-day average of ${fmtCompact(avg)}`}>
      <ResponsiveContainer>
        <BarChart data={recent} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="date" {...axis} minTickGap={40} tickFormatter={(d: string) => d.slice(5)} />
          <YAxis {...axis} width={48} tickFormatter={(v: number) => fmtCompact(v)} />
          <Tooltip {...tooltipStyle} formatter={(v) => fmtCompact(Number(v))} />
          <Bar dataKey="volume" name="Volume" fill="var(--low)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          {avg && <ReferenceLine y={avg} stroke="var(--high)" strokeDasharray="4 3" label={{ value: "20-day avg", fill: "var(--muted-foreground)", fontSize: 11, position: "insideTopRight" }} />}
        </BarChart>
      </ResponsiveContainer>
    </Frame>
  );
}
