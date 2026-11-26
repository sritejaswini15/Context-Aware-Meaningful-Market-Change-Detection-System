"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, List, Loader2, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, Input, Label, Skeleton } from "@/components/ui/primitives";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/radix";
import { AttentionBadge } from "@/components/knoww/signals";
import { EmptyState, ErrorState, PageHeader } from "@/components/knoww/states";
import { timeAgo } from "@/lib/format";
import { useCreateWatchlist, useDeleteWatchlist, useRenameWatchlist, useWatchlists } from "@/lib/hooks";
import type { WatchlistSummary } from "@/lib/schemas";
import { NameDialog } from "@/components/knoww/name-dialog";

function WatchlistCard({ w }: { w: WatchlistSummary }) {
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const rename = useRenameWatchlist();
  const del = useDeleteWatchlist();
  return (
    <Card className="group relative flex flex-col gap-3 p-5 transition-colors hover:border-foreground/20">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/watchlists/${w.id}`} className="min-w-0 after:absolute after:inset-0 focus-visible:outline-2 focus-visible:outline-ring rounded-md">
          <h2 className="truncate font-semibold">{w.name}</h2>
          <p className="text-xs text-muted-foreground">
            {w.symbols_count} stock{w.symbols_count === 1 ? "" : "s"} · updated {timeAgo(w.updated_at)}
          </p>
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative z-10 -mr-2 -mt-1" aria-label={`Actions for ${w.name}`}>
              <MoreHorizontal aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => setRenaming(true)}>
              <Pencil aria-hidden /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setDeleting(true)} className="text-down">
              <Trash2 aria-hidden /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
        {w.symbols.slice(0, 8).map((s) => (
          <span key={s} className="rounded bg-muted px-1.5 py-0.5 font-medium text-foreground/80">
            {s}
          </span>
        ))}
        {w.symbols.length > 8 && <span>+{w.symbols.length - 8}</span>}
        {w.symbols.length === 0 && <span>No stocks yet</span>}
      </div>
      <div className="mt-auto flex items-center justify-between">
        <span className="flex gap-1.5">
          {w.high_count > 0 && <AttentionBadge level="HIGH" compact />}
          {w.medium_count > 0 && <AttentionBadge level="MEDIUM" compact />}
          {!w.high_count && !w.medium_count && <span className="text-xs text-muted-foreground">Nothing needs attention</span>}
        </span>
        <ArrowRight aria-hidden className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </div>
      <NameDialog
        open={renaming}
        onOpenChange={setRenaming}
        title="Rename watchlist"
        initial={w.name}
        submitLabel="Save"
        pending={rename.isPending}
        onSubmit={(name) => rename.mutate({ id: w.id, name }, { onSuccess: () => setRenaming(false) })}
      />
      <Dialog open={deleting} onOpenChange={setDeleting}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete &quot;{w.name}&quot;?</DialogTitle>
            <DialogDescription>This removes the watchlist. Stocks that are not in another watchlist stop being monitored.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(false)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={del.isPending} onClick={() => del.mutate(w.id, { onSuccess: () => setDeleting(false) })}>
              {del.isPending && <Loader2 aria-hidden className="animate-spin" />} Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export default function WatchlistsPage() {
  const { data, isLoading, error, refetch } = useWatchlists();
  const create = useCreateWatchlist();
  const [creating, setCreating] = useState(false);
  return (
    <div className="space-y-6">
      <PageHeader
        title="Watchlists"
        description="Knoww watches every stock here and tells you only what meaningfully changed."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus aria-hidden /> New watchlist
          </Button>
        }
      />
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} retry={() => refetch()} />
      ) : !data?.length ? (
        <EmptyState
          icon={List}
          title="No watchlists yet"
          description="Create a watchlist and add the stocks you care about. Knoww records what you saw and measures every change from there."
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden /> Create watchlist
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((w) => (
            <WatchlistCard key={w.id} w={w} />
          ))}
        </div>
      )}
      <NameDialog
        open={creating}
        onOpenChange={setCreating}
        title="New watchlist"
        submitLabel="Create"
        pending={create.isPending}
        onSubmit={(name) => create.mutate({ name }, { onSuccess: () => setCreating(false) })}
      />
    </div>
  );
}
