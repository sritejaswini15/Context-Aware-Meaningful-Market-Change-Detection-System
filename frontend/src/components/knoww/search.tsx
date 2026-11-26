"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, Loader2, Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/radix";
import { Delta } from "@/components/knoww/signals";
import { fmtPrice } from "@/lib/format";
import { useAddStock, useCreateWatchlist, useSearch, useWatchlists } from "@/lib/hooks";

function useDebounced<T>(value: T, ms = 200): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Add a symbol to one of the user's watchlists (creates one if they have none). */
export function AddToWatchlist({ symbol, inWatchlists, size = "sm" }: { symbol: string; inWatchlists: string[]; size?: "sm" | "default" }) {
  const { data: lists } = useWatchlists();
  const add = useAddStock();
  const create = useCreateWatchlist();
  const available = (lists ?? []).filter((w) => !inWatchlists.includes(w.id));
  const busy = add.isPending || create.isPending;

  if (lists && lists.length === 0) {
    return (
      <Button size={size} variant="outline" disabled={busy} onClick={() => create.mutate({ name: "My Watchlist", symbols: [symbol] })}>
        {busy ? <Loader2 aria-hidden className="animate-spin" /> : <Plus aria-hidden />} Add
      </Button>
    );
  }
  if (inWatchlists.length && !available.length) {
    return (
      <Button size={size} variant="ghost" disabled>
        <Check aria-hidden /> Watching
      </Button>
    );
  }
  if (available.length === 1 && !inWatchlists.length) {
    return (
      <Button size={size} variant="outline" disabled={busy} onClick={() => add.mutate({ id: available[0].id, symbol })} aria-label={`Add ${symbol} to ${available[0].name}`}>
        {busy ? <Loader2 aria-hidden className="animate-spin" /> : <Plus aria-hidden />} Add
      </Button>
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size={size} variant="outline" disabled={busy} aria-label={`Add ${symbol} to a watchlist`}>
          {busy ? <Loader2 aria-hidden className="animate-spin" /> : <Plus aria-hidden />} Add
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>Add {symbol} to</DropdownMenuLabel>
        {available.map((w) => (
          <DropdownMenuItem key={w.id} onSelect={() => add.mutate({ id: w.id, symbol })}>
            {w.name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function StockSearch({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const { data, isFetching, isError } = useSearch(dq);
  const router = useRouter();

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setQ("");
      }}
    >
      <DialogContent className="top-[12vh] max-w-xl translate-y-0 gap-3 p-0">
        <DialogTitle className="sr-only">Search stocks</DialogTitle>
        <DialogDescription className="sr-only">Search by company name or ticker</DialogDescription>
        <div className="flex items-center gap-2 border-b px-4">
          <Search aria-hidden className="size-4 text-muted-foreground" />
          <Input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search company or ticker…"
            aria-label="Search company or ticker"
            className="h-12 border-0 bg-transparent px-0 shadow-none focus-visible:outline-none"
          />
          {isFetching && <Loader2 aria-hidden className="size-4 animate-spin text-muted-foreground" />}
        </div>
        <div className="max-h-[50vh] overflow-y-auto px-2 pb-2" role="listbox" aria-label="Search results">
          {!dq && <p className="px-3 py-6 text-center text-sm text-muted-foreground">Try “NVDA”, “Apple” or “bank”.</p>}
          {isError && <p className="px-3 py-6 text-center text-sm text-muted-foreground">Search is unavailable right now.</p>}
          {dq && data?.length === 0 && !isFetching && <p className="px-3 py-6 text-center text-sm text-muted-foreground">No matching stocks.</p>}
          {data?.map((r) => (
            <div key={r.symbol} role="option" aria-selected={false} className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-accent">
              <button
                type="button"
                className="flex min-w-0 flex-1 items-center gap-3 text-left focus-visible:outline-2 focus-visible:outline-ring rounded-md"
                onClick={() => {
                  onOpenChange(false);
                  router.push(`/stocks/${r.symbol}`);
                }}
              >
                <span className="w-14 shrink-0 text-sm font-semibold">{r.symbol}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{r.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">{[r.exchange, r.sector].filter(Boolean).join(" · ")}</span>
                </span>
                <span className="hidden text-right sm:block">
                  <span className="num block text-sm">{fmtPrice(r.price)}</span>
                  <Delta value={r.day_change_pct} size="sm" />
                </span>
              </button>
              <AddToWatchlist symbol={r.symbol} inWatchlists={r.in_watchlists} />
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
