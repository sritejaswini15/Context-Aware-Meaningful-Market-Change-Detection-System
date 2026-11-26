"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Loader2, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, Input } from "@/components/ui/primitives";
import { Logo } from "@/components/knoww/shell";
import { api, ApiError } from "@/lib/api";
import { qk, useMe, useSearch } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const POPULAR = [
  ["NVDA", "NVIDIA"], ["AAPL", "Apple"], ["MSFT", "Microsoft"], ["AMZN", "Amazon"], ["GOOGL", "Alphabet"], ["META", "Meta"],
  ["TSLA", "Tesla"], ["JPM", "JPMorgan Chase"], ["XOM", "Exxon Mobil"], ["LLY", "Eli Lilly"], ["V", "Visa"], ["COST", "Costco"],
] as const;

const SENS = [
  { v: "LOW", t: "Low", d: "Only the clearest, strongest changes." },
  { v: "BALANCED", t: "Balanced", d: "Recommended for most people." },
  { v: "HIGH", t: "High", d: "Surface subtler changes too." },
] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: me, error } = useMe();
  const [step, setStep] = useState(0);
  const [picked, setPicked] = useState<string[]>(["NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "XOM"]);
  const [sensitivity, setSensitivity] = useState<"LOW" | "BALANCED" | "HIGH">("BALANCED");
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  const [pending, setPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const search = useSearch(dq);

  useEffect(() => {
    const t = setTimeout(() => setDq(q), 200);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) router.replace("/login");
    if (me?.onboarded) router.replace("/");
  }, [error, me, router]);

  const toggle = (s: string) => setPicked((p) => (p.includes(s) ? p.filter((x) => x !== s) : p.length >= 30 ? p : [...p, s]));

  async function start() {
    setPending(true);
    setErr(null);
    try {
      await api("/onboarding", { method: "POST", body: { watchlist_name: "My Watchlist", symbols: picked, sensitivity } });
      await qc.invalidateQueries({ queryKey: qk.me });
      router.replace("/");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't start monitoring. Please retry.");
      setPending(false);
    }
  }

  const steps = ["Welcome", "Choose stocks", "Sensitivity", "Start"];
  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col px-5 py-8">
      <div className="flex items-center justify-between">
        <Logo />
        <ol className="flex gap-1.5" aria-label="Onboarding progress">
          {steps.map((s, i) => (
            <li key={s} aria-current={i === step ? "step" : undefined} className={cn("h-1.5 w-8 rounded-full bg-muted", i <= step && "bg-primary")}>
              <span className="sr-only">
                Step {i + 1}: {s}
              </span>
            </li>
          ))}
        </ol>
      </div>

      <main className="flex flex-1 flex-col justify-center py-10">
        {step === 0 && (
          <section className="space-y-6">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Welcome to Knoww.</h1>
            <p className="text-lg text-muted-foreground">Know what matters. Most price moves are noise. Knoww tells you which ones aren&apos;t.</p>
            <ul className="space-y-3 text-sm">
              {[
                "It remembers the prices you saw when you last checked.",
                "It compares every move with the stock's sector, the market and its normal behaviour.",
                "It ranks what deserves your attention, explains why, and stays quiet when nothing does.",
              ].map((t) => (
                <li key={t} className="flex gap-2">
                  <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-ok" />
                  {t}
                </li>
              ))}
            </ul>
          </section>
        )}

        {step === 1 && (
          <section className="space-y-5">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Choose stocks to watch</h1>
              <p className="text-sm text-muted-foreground">Pick a few. You can change this any time.</p>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {POPULAR.map(([s, n]) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={picked.includes(s)}
                  onClick={() => toggle(s)}
                  className={cn(
                    "flex items-center justify-between rounded-lg border bg-card px-3 py-2.5 text-left text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
                    picked.includes(s) && "border-primary/60 bg-accent",
                  )}
                >
                  <span>
                    <span className="block font-semibold">{s}</span>
                    <span className="block text-xs text-muted-foreground">{n}</span>
                  </span>
                  {picked.includes(s) && <Check aria-hidden className="size-4" />}
                </button>
              ))}
            </div>
            <div className="space-y-2">
              <div className="relative">
                <Search aria-hidden className="absolute left-3 top-3 size-4 text-muted-foreground" />
                <Input className="pl-9" placeholder="Search for another company or ticker" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search stocks" />
              </div>
              {dq && (
                <ul className="divide-y rounded-lg border bg-card">
                  {search.data?.slice(0, 6).map((r) => (
                    <li key={r.symbol}>
                      <button type="button" className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent" onClick={() => toggle(r.symbol)} aria-pressed={picked.includes(r.symbol)}>
                        <span>
                          <span className="font-semibold">{r.symbol}</span> <span className="text-muted-foreground">{r.name}</span>
                        </span>
                        {picked.includes(r.symbol) ? <Check aria-hidden className="size-4" /> : <span className="text-xs text-muted-foreground">Add</span>}
                      </button>
                    </li>
                  ))}
                  {search.data?.length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">No matches</li>}
                </ul>
              )}
            </div>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {picked.length} selected{picked.length ? `: ${picked.join(", ")}` : ""}
            </p>
          </section>
        )}

        {step === 2 && (
          <section className="space-y-5">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">How sensitive should Knoww be?</h1>
              <p className="text-sm text-muted-foreground">This sets how readily Knoww asks for your attention.</p>
            </div>
            <div role="radiogroup" aria-label="Sensitivity" className="space-y-2">
              {SENS.map((s) => (
                <button
                  key={s.v}
                  type="button"
                  role="radio"
                  aria-checked={sensitivity === s.v}
                  onClick={() => setSensitivity(s.v)}
                  className={cn("flex w-full items-center justify-between rounded-lg border bg-card p-4 text-left hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring", sensitivity === s.v && "border-primary/60 bg-accent")}
                >
                  <span>
                    <span className="block font-semibold">{s.t}</span>
                    <span className="block text-sm text-muted-foreground">{s.d}</span>
                  </span>
                  {sensitivity === s.v && <Check aria-hidden className="size-4" />}
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="space-y-5">
            <h1 className="text-2xl font-semibold tracking-tight">Ready to start monitoring</h1>
            <Card className="space-y-2 p-5 text-sm">
              <p>
                <span className="text-muted-foreground">Watchlist:</span> My Watchlist ({picked.length} stocks)
              </p>
              <p>
                <span className="text-muted-foreground">Sensitivity:</span> {sensitivity.toLowerCase()}
              </p>
              <p className="text-muted-foreground">
                Knoww records today&apos;s prices as your starting point. When you come back, it shows you what meaningfully changed since then.
              </p>
            </Card>
            {err && (
              <p role="alert" className="text-sm text-down">
                {err}
              </p>
            )}
          </section>
        )}
      </main>

      <footer className="flex items-center justify-between">
        <Button variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={step === 0 || pending}>
          <ArrowLeft aria-hidden /> Back
        </Button>
        {step < 3 ? (
          <Button onClick={() => setStep((s) => s + 1)} disabled={step === 1 && picked.length === 0}>
            Continue <ArrowRight aria-hidden />
          </Button>
        ) : (
          <Button onClick={start} disabled={pending || picked.length === 0} size="lg">
            {pending && <Loader2 aria-hidden className="animate-spin" />} Start monitoring
          </Button>
        )}
      </footer>
    </div>
  );
}
