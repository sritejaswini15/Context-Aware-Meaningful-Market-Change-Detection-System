"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, CheckCheck, Loader2, Pencil, Plus, Search, Star, Trash2, TrendingUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, Input, Skeleton } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, Tooltip } from "@/components/ui/radix";
import { NameDialog } from "@/components/knoww/name-dialog";
import { AttentionBadge, Delta, FreshnessBadge } from "@/components/knoww/signals";
import { EmptyState, ErrorState, PageHeader } from "@/components/knoww/states";
import { ApiError } from "@/lib/api";
import { fmtDateTime, fmtPrice, fmtRatio } from "@/lib/format";
import { useAddStock, useCheckpoint, useRemoveStock, useRenameWatchlist, useSearch, useSetPriority, useSnapshot, useWatchlist } from "@/lib/hooks";
import type { StockState } from "@/lib/schemas";
import { cn } from "@/lib/utils";

function AddStockDialog({ watchlistId, existing, open, onOpenChange }: { watchlistId: string; existing: string[]; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDq(q), 200);
    return () => clearTimeout(t);
  }, [q]);
  const { data, isFetching } = useSearch(dq);
  const add = useAddStock();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a stock</DialogTitle>
          <DialogDescription>Knoww starts measuring changes from the current price.</DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search aria-hidden className="absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input autoFocus className="pl-9" placeholder="Company or ticker" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Company or ticker" />
        </div>
        <ul className="max-h-80 space-y-1 overflow-y-auto" aria-live="polite">
          {isFetching && !data && <li className="px-2 py-4 text-sm text-muted-foreground">Searching…</li>}
          {dq && data?.length === 0 && <li className="px-2 py-4 text-sm text-muted-foreground">No matching stocks.</li>}
          {data?.map((r) => {
            const added = existing.includes(r.symbol);
            const busy = add.isPending && add.variables?.symbol === r.symbol;
            return (
              <li key={r.symbol} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-accent">
                <span className="w-14 text-sm font-semibold">{r.symbol}</span>
                <span className="min-w-0 flex-1 truncate text-sm">{r.name}</span>
                <span className="num hidden text-sm text-muted-foreground sm:inline">{fmtPrice(r.price)}</span>
                <Button size="sm" variant={added ? "ghost" : "outline"} disabled={added || add.isPending} onClick={() => add.mutate({ id: watchlistId, symbol: r.symbol })}>
                  {busy ? <Loader2 aria-hidden className="animate-spin" /> : added ? "Added" : <><Plus aria-hidden /> Add</>}
                </Button>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

function Row({ s, watchlistId }: { s: StockState; watchlistId: string }) {
  const router = useRouter();
  const remove = useRemoveStock();
  const prio = useSetPriority();
  const high = s.priority === "HIGH";
  const open = () => router.push(`/stocks/${s.symbol}`);
  return (
    <tr
      className="cursor-pointer border-t transition-colors hover:bg-accent/60 focus-within:bg-accent/60"
      onClick={open}
      onKeyDown={(e) => e.key === "Enter" && e.target === e.currentTarget && open()}
      tabIndex={0}
      aria-label={`${s.name}: open details`}
    >
      <td className="py-3 pl-4 pr-2">
        <div className="flex items-center gap-2">
          <div className="min-w-0">
            <Link href={`/stocks/${s.symbol}`} onClick={(e) => e.stopPropagation()} className="font-semibold hover:underline">
              {s.symbol}
            </Link>
            <p className="max-w-44 truncate text-xs text-muted-foreground">{s.name}</p>
          </div>
        </div>
      </td>
      <td className="num px-2 text-right text-sm">{fmtPrice(s.price, s.currency)}</td>
      <td className="hidden px-2 text-right md:table-cell">
        <Delta value={s.day_change_pct} size="sm" />
      </td>
      <td className="px-2 text-right">
        <Delta value={s.since_check_pct} size="sm" />
        {s.baseline && <p className="hidden text-[11px] text-muted-foreground lg:block">from {fmtPrice(s.baseline.price)}</p>}
      </td>
      <td className="px-2">
        {s.signal ? (
          <div className="flex items-center gap-2">
            <AttentionBadge level={s.signal.attention} compact />
            <span className="num text-xs text-muted-foreground">{s.signal.score}</span>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">Pending</span>
        )}
        <p className="hidden truncate text-[11px] text-muted-foreground xl:block">{s.signal?.context_label}</p>
      </td>
      <td className="num hidden px-2 text-right text-xs lg:table-cell">
        {s.volume_ratio === null ? <span className="text-muted-foreground">Unavailable</span> : <span className={cn(s.volume_ratio >= 2 && "font-semibold")}>{fmtRatio(s.volume_ratio)}</span>}
      </td>
      <td className="hidden px-2 sm:table-cell">
        <FreshnessBadge freshness={s.freshness} />
      </td>
      <td className="py-2 pl-2 pr-3 text-right" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-end">
          <Tooltip content={high ? "High priority: adds weight to its signal" : "Mark as high priority"}>
            <Button
              variant="ghost"
              size="icon"
              aria-pressed={high}
              aria-label={high ? `Unmark ${s.symbol} as high priority` : `Mark ${s.symbol} as high priority`}
              onClick={() => prio.mutate({ id: watchlistId, symbol: s.symbol, priority: high ? "NORMAL" : "HIGH" })}
            >
              <Star aria-hidden className={cn(high && "fill-medium text-medium")} />
            </Button>
          </Tooltip>
          <Button variant="ghost" size="icon" aria-label={`Remove ${s.symbol}`} disabled={remove.isPending} onClick={() => remove.mutate({ id: watchlistId, symbol: s.symbol })}>
            <Trash2 aria-hidden />
          </Button>
        </div>
      </td>
    </tr>
  );
}

export default function WatchlistDetailPage() {
  const { id } = useParams<{ id: string }>();
  const wl = useWatchlist(id);
  const snap = useSnapshot(id);
  const checkpoint = useCheckpoint();
  const rename = useRenameWatchlist();
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState(false);

  if (wl.error instanceof ApiError && wl.error.status === 404) {
    return <EmptyState icon={TrendingUp} title="Watchlist not found" description="It may have been deleted." action={<Button asChild><Link href="/watchlists">Back to watchlists</Link></Button>} />;
  }
  if (wl.error) return <ErrorState error={wl.error} retry={() => wl.refetch()} />;
  if (!wl.data) return <Skeleton className="h-64 w-full" />;

  const rows = snap.data ?? [];
  const lastChecked = rows.map((r) => r.baseline?.checked_at).filter(Boolean).sort()[0];
  return (
    <div className="space-y-6">
      <Link href="/watchlists" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft aria-hidden className="size-4" /> Watchlists
      </Link>
      <PageHeader
        title={wl.data.name}
        description={
          <>
            {wl.data.symbols_count} stock{wl.data.symbols_count === 1 ? "" : "s"}
            {lastChecked ? ` · changes measured since ${fmtDateTime(lastChecked)}` : ""}
          </>
        }
        actions={
          <>
            <Button variant="ghost" size="icon" aria-label="Rename watchlist" onClick={() => setRenaming(true)}>
              <Pencil aria-hidden />
            </Button>
            {rows.length > 0 && (
              <Button variant="outline" onClick={() => checkpoint.mutate(id)} disabled={checkpoint.isPending}>
                {checkpoint.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <CheckCheck aria-hidden />} Mark reviewed
              </Button>
            )}
            <Button onClick={() => setAdding(true)}>
              <Plus aria-hidden /> Add stock
            </Button>
          </>
        }
      />
      {wl.data.items.length === 0 ? (
        <EmptyState
          icon={Plus}
          title="This watchlist is empty"
          description="Add a few stocks. Knoww will remember their prices now and tell you when something meaningful changes."
          action={
            <Button onClick={() => setAdding(true)}>
              <Plus aria-hidden /> Add stock
            </Button>
          }
        />
      ) : snap.error ? (
        <ErrorState error={snap.error} retry={() => snap.refetch()} />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <caption className="sr-only">Stocks in {wl.data.name}, sorted by attention</caption>
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="py-2.5 pl-4 pr-2 text-left font-medium">Stock</th>
                  <th scope="col" className="px-2 text-right font-medium">Price</th>
                  <th scope="col" className="hidden px-2 text-right font-medium md:table-cell">Today</th>
                  <th scope="col" className="px-2 text-right font-medium">Since last check</th>
                  <th scope="col" className="px-2 text-left font-medium">Signal</th>
                  <th scope="col" className="hidden px-2 text-right font-medium lg:table-cell">Volume</th>
                  <th scope="col" className="hidden px-2 text-left font-medium sm:table-cell">Freshness</th>
                  <th scope="col" className="pr-3 text-right font-medium">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {snap.isLoading
                  ? wl.data.items.map((i) => (
                      <tr key={i.symbol} className="border-t">
                        <td colSpan={8} className="p-3">
                          <Skeleton className="h-8 w-full" />
                        </td>
                      </tr>
                    ))
                  : rows.map((s) => <Row key={s.symbol} s={s} watchlistId={id} />)}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <AddStockDialog watchlistId={id} existing={wl.data.items.map((i) => i.symbol)} open={adding} onOpenChange={setAdding} />
      <NameDialog
        open={renaming}
        onOpenChange={setRenaming}
        title="Rename watchlist"
        initial={wl.data.name}
        submitLabel="Save"
        pending={rename.isPending}
        onSubmit={(name) => rename.mutate({ id, name }, { onSuccess: () => setRenaming(false) })}
      />
    </div>
  );
}
