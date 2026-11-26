"use client";

import { AlertCircle, CheckCircle2, type LucideIcon, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        {eyebrow && <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">{title}</h1>
        {description && <div className="text-sm text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col items-center gap-3 px-6 py-10 text-center", className)}>
      <div className="rounded-full bg-muted p-3">
        <Icon aria-hidden className="size-5 text-muted-foreground" />
      </div>
      <div className="space-y-1">
        <h2 className="font-semibold">{title}</h2>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </Card>
  );
}

export function ErrorState({ error, retry, title = "Couldn't load this" }: { error: unknown; retry?: () => void; title?: string }) {
  const message =
    error instanceof ApiError
      ? error.status === 503
        ? "The database is temporarily unavailable. Your data is safe; please retry in a moment."
        : error.message
      : "Knoww couldn't reach its servers. Check your connection and retry.";
  return (
    <Card role="alert" className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      <AlertCircle aria-hidden className="size-6 text-down" />
      <div className="space-y-1">
        <h2 className="font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">{message}</p>
      </div>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          <RotateCw aria-hidden /> Retry
        </Button>
      )}
    </Card>
  );
}

export function AllCaughtUp({ lastChecked, marketSummary, quietCount }: { lastChecked: string | null; marketSummary: string; quietCount: number }) {
  return (
    <Card className="flex flex-col items-start gap-4 p-6 sm:flex-row sm:items-center sm:p-8">
      <div className="rounded-full bg-secondary p-3">
        <CheckCircle2 aria-hidden className="size-7 text-ok" />
      </div>
      <div className="space-y-1.5">
        <h2 className="text-xl font-semibold tracking-tight">You&apos;re all caught up.</h2>
        <p className="text-sm text-muted-foreground">No meaningful changes since you last checked{lastChecked ? ` at ${new Date(lastChecked).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : ""}.</p>
        <p className="text-sm">
          <span className="text-muted-foreground">Market context: </span>
          {marketSummary}
        </p>
        {quietCount > 0 && (
          <p className="text-xs text-muted-foreground">
            Knoww checked {quietCount} stock{quietCount === 1 ? "" : "s"} and decided none of them needs your attention right now.
          </p>
        )}
      </div>
    </Card>
  );
}
