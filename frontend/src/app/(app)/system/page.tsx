"use client";

import { Activity, AlertTriangle, CheckCircle2, CircleDashed, XCircle } from "lucide-react";

import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { ScenarioList } from "@/components/knoww/demo";
import { ErrorState, PageHeader } from "@/components/knoww/states";
import { fmtDateTime, timeAgo } from "@/lib/format";
import { useHealth, useScenarios } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const STATUS = {
  HEALTHY: { label: "Healthy", icon: CheckCircle2, cls: "text-ok" },
  DEGRADED: { label: "Degraded", icon: AlertTriangle, cls: "text-warn" },
  DOWN: { label: "Down", icon: XCircle, cls: "text-down" },
  NOT_CONFIGURED: { label: "Not configured", icon: CircleDashed, cls: "text-muted-foreground" },
  UNKNOWN: { label: "Unknown", icon: CircleDashed, cls: "text-muted-foreground" },
} as const;

function StatusLabel({ status }: { status: string }) {
  const s = STATUS[status as keyof typeof STATUS] ?? STATUS.UNKNOWN;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-medium", s.cls)}>
      <s.icon aria-hidden className="size-4" />
      {s.label}
    </span>
  );
}

export default function SystemPage() {
  const { data, isLoading, error, refetch } = useHealth();
  const scenarios = useScenarios();
  if (isLoading) return <Skeleton className="h-96 w-full" />;
  if (error || !data) return <ErrorState error={error} retry={() => refetch()} />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="System health"
        description={
          <>
            Overall <StatusLabel status={data.status} /> · checked {timeAgo(data.checked_at)} · v{data.version} · {data.environment}
          </>
        }
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.components.map((c) => (
          <Card key={c.key} className="p-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">{c.name}</h2>
              <StatusLabel status={c.status} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{c.detail}</p>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity aria-hidden className="size-4" /> Market data providers
          </CardTitle>
          <CardDescription>
            Last market update {data.last_market_update ? `${fmtDateTime(data.last_market_update)} (${timeAgo(data.last_market_update)})` : "never"} · {data.conflicts_24h} data conflict
            {data.conflicts_24h === 1 ? "" : "s"} in the last 24h
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Provider status</caption>
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="pb-2 font-medium">Provider</th>
                <th scope="col" className="pb-2 font-medium">Status</th>
                <th scope="col" className="pb-2 text-right font-medium">Reliability</th>
                <th scope="col" className="pb-2 font-medium">Last success</th>
                <th scope="col" className="pb-2 font-medium">Last error</th>
              </tr>
            </thead>
            <tbody>
              {data.providers.map((p) => (
                <tr key={p.name} className="border-t align-top">
                  <th scope="row" className="py-2 pr-2 text-left font-medium">
                    {p.name} {p.simulated && <Badge className="ml-1">simulated</Badge>}
                  </th>
                  <td className="py-2 pr-2">
                    <StatusLabel status={p.status} />
                  </td>
                  <td className="num py-2 pr-2 text-right">{Math.round(p.reliability * 100)}%</td>
                  <td className="py-2 pr-2 text-xs text-muted-foreground">{timeAgo(p.last_success_at)}</td>
                  <td className="max-w-56 py-2 text-xs text-muted-foreground">{p.consecutive_failures ? p.last_error : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Signal quality (last 7 days)</CardTitle>
          <CardDescription>Knoww is measured on signal quality, not alert volume.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 sm:grid-cols-4">
            {[
              ["Signals evaluated", data.product_metrics.signals_evaluated_7d.toLocaleString()],
              ["Meaningful changes surfaced", data.product_metrics.meaningful_changes_7d.toLocaleString()],
              ["High-attention reviewed", data.product_metrics.high_reviewed_pct === null ? "—" : `${data.product_metrics.high_reviewed_pct}%`],
              ["Median time to first look", data.product_metrics.median_seconds_to_first_look === null ? "—" : `${Math.round(data.product_metrics.median_seconds_to_first_look / 60)} min`],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted-foreground">{k}</dt>
                <dd className="num text-xl font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      {scenarios.data?.enabled && (
        <Card>
          <CardHeader>
            <CardTitle>Demo scenarios</CardTitle>
            <CardDescription>
              Drive the simulated market to see how Knoww tells ordinary movement apart from meaningful movement, and how it behaves when dependencies fail.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ScenarioList />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
