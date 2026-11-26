"use client";

import { useState } from "react";
import { FlaskConical, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/radix";
import { useScenarios, useSetScenario } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export function ScenarioList({ onDone }: { onDone?: () => void }) {
  const { data } = useScenarios();
  const set = useSetScenario();
  const [pending, setPending] = useState<string | null>(null);
  if (!data?.enabled) return <p className="text-sm text-muted-foreground">Demo mode is disabled in this environment.</p>;
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {data.scenarios.map((s) => {
        const active = data.active === s.key;
        return (
          <li key={s.key}>
            <button
              type="button"
              disabled={set.isPending}
              aria-pressed={active}
              onClick={() => {
                setPending(s.key);
                set.mutate(s.key, { onSettled: () => setPending(null), onSuccess: () => onDone?.() });
              }}
              className={cn(
                "flex h-full w-full flex-col gap-1 rounded-lg border p-3 text-left transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-60",
                active && "border-primary/60 bg-accent",
              )}
            >
              <span className="flex items-center justify-between gap-2 text-sm font-medium">
                {s.title}
                {pending === s.key ? <Loader2 aria-hidden className="size-3.5 animate-spin" /> : active ? <Badge variant="ok">Active</Badge> : null}
              </span>
              <span className="text-xs text-muted-foreground">{s.description}</span>
              <span className="text-xs">
                <span className="text-muted-foreground">Expect: </span>
                {s.expectation}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function DemoButton() {
  const { data } = useScenarios();
  const [open, setOpen] = useState(false);
  if (!data?.enabled) return null;
  const active = data.scenarios.find((s) => s.key === data.active);
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="gap-1.5" aria-label="Open demo market controls">
        <FlaskConical aria-hidden />
        <span className="hidden md:inline">Demo market:</span>
        <span className="max-w-28 truncate font-normal text-muted-foreground">{active?.title ?? "Normal movement"}</span>
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Simulated market scenarios</DialogTitle>
            <DialogDescription>
              Change the simulated market, then see how Knoww decides what deserves attention. Prices are deterministic, and nothing here is real market data.
            </DialogDescription>
          </DialogHeader>
          <ScenarioList onDone={() => setOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
