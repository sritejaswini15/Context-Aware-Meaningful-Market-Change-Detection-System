"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Skeleton } from "@/components/ui/primitives";
import { Switch } from "@/components/ui/radix";
import { ErrorState, PageHeader } from "@/components/knoww/states";
import { api } from "@/lib/api";
import { qk, useMe, usePreferences, useUpdatePreferences } from "@/lib/hooks";
import type { Preferences } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

const SENSITIVITY: { value: Preferences["sensitivity"]; title: string; body: string }[] = [
  { value: "LOW", title: "Low", body: "Only the clearest, strongest changes. HIGH at a score of 75+, MEDIUM at 50+." },
  { value: "BALANCED", title: "Balanced", body: "Recommended. HIGH at 65+, MEDIUM at 40+." },
  { value: "HIGH", title: "High", body: "Surface more subtle changes. HIGH at 55+, MEDIUM at 30+." },
];

const TOGGLES: { key: "include_volume" | "include_market_context" | "include_events"; title: string; body: string }[] = [
  { key: "include_volume", title: "Volume anomalies", body: "Unusual trading volume strengthens a signal (never on its own)." },
  { key: "include_market_context", title: "Market & sector context", body: "Discount moves that simply follow the market or sector. Turn off to rank by raw movement." },
  { key: "include_events", title: "Company events", body: "Earnings, guidance and news in the data add weight to a change." },
];

export default function SettingsPage() {
  const { data: prefs, isLoading, error, refetch } = usePreferences();
  const update = useUpdatePreferences();
  const { data: me } = useMe();
  const { theme, setTheme } = useTheme();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [savingName, setSavingName] = useState(false);
  useEffect(() => setName(me?.display_name ?? ""), [me?.display_name]);

  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (error || !prefs) return <ErrorState error={error} retry={() => refetch()} />;

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="These settings change how Knoww ranks signals. They are applied to your watchlists immediately." />

      <Card>
        <CardHeader>
          <CardTitle>Sensitivity</CardTitle>
          <CardDescription>How readily should Knoww ask for your attention?</CardDescription>
        </CardHeader>
        <CardContent>
          <div role="radiogroup" aria-label="Sensitivity" className="grid gap-3 sm:grid-cols-3">
            {SENSITIVITY.map((s) => (
              <button
                key={s.value}
                type="button"
                role="radio"
                aria-checked={prefs.sensitivity === s.value}
                disabled={update.isPending}
                onClick={() => update.mutate({ sensitivity: s.value })}
                className={cn(
                  "rounded-lg border p-4 text-left transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
                  prefs.sensitivity === s.value && "border-primary/60 bg-accent",
                )}
              >
                <span className="block text-sm font-semibold">{s.title}</span>
                <span className="mt-1 block text-xs text-muted-foreground">{s.body}</span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What counts as meaningful</CardTitle>
          <CardDescription>Turn off a factor and its weight moves to the others.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          {TOGGLES.map((t) => (
            <div key={t.key} className="flex items-center justify-between gap-4 py-3 first:pt-0">
              <div>
                <Label htmlFor={t.key}>{t.title}</Label>
                <p className="mt-1 text-xs text-muted-foreground">{t.body}</p>
              </div>
              <Switch id={t.key} checked={prefs[t.key]} disabled={update.isPending} onCheckedChange={(v) => update.mutate({ [t.key]: v })} />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
          <CardDescription>In-app notifications for meaningful changes only. Knoww is designed to decide when not to bother you.</CardDescription>
        </CardHeader>
        <CardContent>
          <div role="radiogroup" aria-label="Notify me about" className="flex flex-wrap gap-2">
            {(["HIGH", "MEDIUM"] as const).map((v) => (
              <button
                key={v}
                type="button"
                role="radio"
                aria-checked={prefs.notify_min_attention === v}
                onClick={() => update.mutate({ notify_min_attention: v })}
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
                  prefs.notify_min_attention === v && "border-primary/60 bg-accent font-medium",
                )}
              >
                {v === "HIGH" ? "High attention only" : "High and medium attention"}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Profile & appearance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={async (e) => {
              e.preventDefault();
              setSavingName(true);
              try {
                await api("/auth/me", { method: "PATCH", body: { display_name: name } });
                qc.invalidateQueries({ queryKey: qk.me });
                toast.success("Profile saved");
              } catch {
                toast.error("Couldn't save your profile");
              } finally {
                setSavingName(false);
              }
            }}
          >
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="name">Display name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
            </div>
            <Button type="submit" variant="outline" disabled={savingName}>
              {savingName && <Loader2 aria-hidden className="animate-spin" />} Save
            </Button>
          </form>
          <div className="space-y-2">
            <p className="text-sm font-medium">Theme</p>
            <div role="radiogroup" aria-label="Theme" className="flex gap-2">
              {["light", "dark", "system"].map((t) => (
                <button
                  key={t}
                  type="button"
                  role="radio"
                  aria-checked={theme === t}
                  onClick={() => setTheme(t)}
                  className={cn("rounded-lg border px-3 py-1.5 text-sm capitalize hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring", theme === t && "border-primary/60 bg-accent font-medium")}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">Signed in as {me?.email}</p>
        </CardContent>
      </Card>
    </div>
  );
}
