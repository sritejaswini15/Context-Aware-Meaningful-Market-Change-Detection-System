"use client";

import { useState } from "react";
import { CheckCircle2, Eye } from "lucide-react";

import { Skeleton } from "@/components/ui/primitives";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/radix";
import { ChangeCard, ChangeSheet } from "@/components/knoww/change-card";
import { EmptyState, ErrorState, PageHeader } from "@/components/knoww/states";
import { useChanges, type ChangeParams } from "@/lib/hooks";
import { cn } from "@/lib/utils";

function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border bg-card p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors focus-visible:outline-2 focus-visible:outline-ring",
            value === o.value && "bg-secondary text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function ChangesPage() {
  const [attention, setAttention] = useState("ALL");
  const [state, setState] = useState("UNACKNOWLEDGED");
  const [scope, setScope] = useState<ChangeParams["scope"]>("current");
  const [sort, setSort] = useState<ChangeParams["sort"]>("importance");
  const [openId, setOpenId] = useState<string | null>(null);
  const { data, isLoading, error, refetch } = useChanges({
    attention: attention === "ALL" ? undefined : attention,
    state: state === "ALL" ? undefined : state,
    scope,
    sort,
  });
  const counts = data?.counts ?? {};

  return (
    <div className="space-y-6">
      <PageHeader
        title="Meaningful changes"
        description="Only movements Knoww judged meaningful, ranked by how much they deserve your attention."
      />
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Tabs value={attention} onValueChange={setAttention}>
          <TabsList aria-label="Filter by attention">
            <TabsTrigger value="ALL">All {counts.ALL !== undefined && <span className="num text-muted-foreground">{counts.ALL}</span>}</TabsTrigger>
            <TabsTrigger value="HIGH">High {counts.HIGH ? <span className="num text-high">{counts.HIGH}</span> : null}</TabsTrigger>
            <TabsTrigger value="MEDIUM">Medium {counts.MEDIUM ? <span className="num text-medium">{counts.MEDIUM}</span> : null}</TabsTrigger>
            <TabsTrigger value="LOW">Low</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex flex-wrap gap-2">
          <Segmented
            label="Status"
            value={state}
            onChange={setState}
            options={[
              { value: "UNACKNOWLEDGED", label: "Open" },
              { value: "NEW", label: "New" },
              { value: "ACKNOWLEDGED", label: "Reviewed" },
              { value: "ALL", label: "All" },
            ]}
          />
          <Segmented
            label="Period"
            value={scope}
            onChange={setScope}
            options={[
              { value: "current", label: "Since last check" },
              { value: "history", label: "History" },
            ]}
          />
          <Segmented
            label="Sort"
            value={sort}
            onChange={setSort}
            options={[
              { value: "importance", label: "Most important" },
              { value: "recent", label: "Most recent" },
            ]}
          />
        </div>
      </div>
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      ) : error ? (
        <ErrorState error={error} retry={() => refetch()} />
      ) : !data?.items.length ? (
        <EmptyState
          icon={state === "ACKNOWLEDGED" ? Eye : CheckCircle2}
          title={scope === "current" && state === "UNACKNOWLEDGED" ? "Nothing needs your attention" : "No changes match these filters"}
          description={
            scope === "current"
              ? "No meaningful changes since you last checked. Knoww is still watching and will surface anything that stands out from its sector and the market."
              : "Try a different filter."
          }
        />
      ) : (
        <div className="space-y-3" aria-live="polite">
          <p className="text-xs text-muted-foreground">
            {data.total} change{data.total === 1 ? "" : "s"}
          </p>
          {data.items.map((c) => (
            <ChangeCard key={c.id} change={c} onOpen={setOpenId} />
          ))}
        </div>
      )}
      <ChangeSheet id={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}
