"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, ApiError } from "@/lib/api";
import * as S from "@/lib/schemas";

export const qk = {
  me: ["me"] as const,
  cc: ["command-center"] as const,
  watchlists: ["watchlists"] as const,
  watchlist: (id: string) => ["watchlist", id] as const,
  snapshot: (id: string) => ["watchlist", id, "snapshot"] as const,
  changes: (p: object) => ["changes", p] as const,
  change: (id: string) => ["change", id] as const,
  stock: (s: string) => ["stock", s] as const,
  history: (s: string, d: number) => ["stock", s, "history", d] as const,
  signals: (s: string) => ["stock", s, "signals"] as const,
  search: (q: string) => ["search", q] as const,
  prefs: ["preferences"] as const,
  notifications: ["notifications"] as const,
  health: ["health"] as const,
  scenarios: ["scenarios"] as const,
};

function useInvalidateAll() {
  const qc = useQueryClient();
  return () => {
    for (const key of [qk.cc, qk.watchlists, ["watchlist"], ["changes"], ["change"], ["stock"], qk.notifications, qk.health]) {
      qc.invalidateQueries({ queryKey: key });
    }
  };
}

const onError = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

export const useMe = () =>
  useQuery({ queryKey: qk.me, queryFn: () => api<S.User>("/auth/me", { schema: S.UserSchema }), retry: false, staleTime: 60_000 });

export const useCommandCenter = () =>
  useQuery({
    queryKey: qk.cc,
    queryFn: () => api<S.CommandCenter>("/command-center", { schema: S.CommandCenterSchema }),
    refetchInterval: 30_000,
  });

export const useWatchlists = () =>
  useQuery({ queryKey: qk.watchlists, queryFn: () => api<S.WatchlistSummary[]>("/watchlists", { schema: S.WatchlistSummarySchema.array() }) });

export const useWatchlist = (id: string) =>
  useQuery({ queryKey: qk.watchlist(id), queryFn: () => api<S.Watchlist>(`/watchlists/${id}`, { schema: S.WatchlistSchema }), retry: false });

export const useSnapshot = (id: string) =>
  useQuery({
    queryKey: qk.snapshot(id),
    queryFn: () => api<S.StockState[]>(`/watchlists/${id}/snapshot`, { schema: S.StockStateSchema.array() }),
    refetchInterval: 30_000,
  });

export type ChangeParams = { attention?: string; state?: string; scope: "current" | "history"; sort: "importance" | "recent"; symbol?: string };

export const useChanges = (p: ChangeParams) =>
  useQuery({
    queryKey: qk.changes(p),
    queryFn: () => {
      const q = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]);
      return api<S.ChangeList>(`/changes?${q}`, { schema: S.ChangeListSchema });
    },
    placeholderData: keepPreviousData,
  });

export const useChange = (id: string | null) =>
  useQuery({
    queryKey: qk.change(id ?? ""),
    queryFn: () => api<S.ChangeDetail>(`/changes/${id}`, { schema: S.ChangeDetailSchema }),
    enabled: !!id,
    // Poll briefly while the AI explanation is being generated.
    refetchInterval: (q) => (q.state.data?.explanation.status === "PENDING" || q.state.data?.explanation.status === "UPDATING" ? 2500 : false),
  });

export const useStock = (symbol: string) =>
  useQuery({
    queryKey: qk.stock(symbol),
    queryFn: () => api<S.StockDetail>(`/stocks/${symbol}`, { schema: S.StockDetailSchema }),
    retry: false,
    refetchInterval: (q) => (q.state.data?.explanation?.status === "PENDING" ? 3000 : 30_000),
  });

export const useHistory = (symbol: string, days = 90) =>
  useQuery({ queryKey: qk.history(symbol, days), queryFn: () => api<S.History>(`/stocks/${symbol}/history?days=${days}`, { schema: S.HistorySchema }) });

export const useSignalHistory = (symbol: string) =>
  useQuery({ queryKey: qk.signals(symbol), queryFn: () => api<S.SignalHistory>(`/stocks/${symbol}/signals`, { schema: S.SignalHistorySchema }) });

export const useSearch = (q: string) =>
  useQuery({
    queryKey: qk.search(q),
    queryFn: () => api<S.SearchResult[]>(`/stocks/search?q=${encodeURIComponent(q)}`, { schema: S.SearchResultSchema.array() }),
    enabled: q.trim().length >= 1,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

export const usePreferences = () =>
  useQuery({ queryKey: qk.prefs, queryFn: () => api<S.Preferences>("/preferences", { schema: S.PreferencesSchema }) });

export const useNotifications = () =>
  useQuery({
    queryKey: qk.notifications,
    queryFn: () => api<S.NotificationList>("/notifications", { schema: S.NotificationListSchema }),
    refetchInterval: 30_000,
  });

export const useHealth = () =>
  useQuery({ queryKey: qk.health, queryFn: () => api<S.Health>("/system/health", { schema: S.HealthSchema }), refetchInterval: 15_000 });

export const useScenarios = () =>
  useQuery({ queryKey: qk.scenarios, queryFn: () => api<S.Scenarios>("/demo/scenarios", { schema: S.ScenariosSchema }) });

// ----------------------------------------------------------------------------- mutations
export function useCreateWatchlist() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: (body: { name: string; symbols?: string[] }) => api<S.Watchlist>("/watchlists", { method: "POST", body }),
    onSuccess: (wl) => {
      inv();
      toast.success(`Created "${wl.name}"`);
    },
    onError,
  });
}

export function useRenameWatchlist() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api<S.Watchlist>(`/watchlists/${id}`, { method: "PATCH", body: { name } }),
    onSuccess: () => inv(),
    onError,
  });
}

export function useDeleteWatchlist() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/watchlists/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      inv();
      toast.success("Watchlist deleted");
    },
    onError,
  });
}

export function useAddStock() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, symbol }: { id: string; symbol: string }) => api<S.Watchlist>(`/watchlists/${id}/stocks`, { method: "POST", body: { symbol } }),
    onSuccess: (wl, v) => {
      inv();
      toast.success(`${v.symbol} added to ${wl.name}`, { description: "Knoww will measure changes from this price." });
    },
    onError,
  });
}

export function useRemoveStock() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, symbol }: { id: string; symbol: string }) => api<S.Watchlist>(`/watchlists/${id}/stocks/${symbol}`, { method: "DELETE" }),
    onSuccess: (_, v) => {
      inv();
      toast.success(`${v.symbol} removed`);
    },
    onError,
  });
}

export function useSetPriority() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: ({ id, symbol, priority }: { id: string; symbol: string; priority: "NORMAL" | "HIGH" }) =>
      api<S.Watchlist>(`/watchlists/${id}/stocks/${symbol}`, { method: "PATCH", body: { priority } }),
    onSuccess: () => inv(),
    onError,
  });
}

export function useCheckpoint() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: (watchlistId?: string) => api(watchlistId ? `/watchlists/${watchlistId}/checkpoint` : "/checkpoint", { method: "POST" }),
    onSuccess: () => {
      inv();
      toast.success("You're caught up", { description: "Knoww will measure new changes from this moment." });
    },
    onError,
  });
}

export function useAcknowledge() {
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: (id: string) => api<S.ChangeCard>(`/changes/${id}/acknowledge`, { method: "POST" }),
    onSuccess: (c) => {
      inv();
      toast.success(`${c.symbol} marked as reviewed`, { description: "It won't be surfaced as new unless it moves materially further." });
    },
    onError,
  });
}

export function useMarkSeen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<S.ChangeCard>(`/changes/${id}/seen`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.cc });
      qc.invalidateQueries({ queryKey: ["changes"] });
    },
  });
}

export function useUpdatePreferences() {
  const qc = useQueryClient();
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: (body: Partial<S.Preferences>) => api<S.Preferences>("/preferences", { method: "PATCH", body }),
    onSuccess: (p) => {
      qc.setQueryData(qk.prefs, p);
      inv();
      toast.success("Preferences saved", { description: "Signals have been re-ranked." });
    },
    onError,
  });
}

export function useReadNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string | "all") => api(id === "all" ? "/notifications/read-all" : `/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.notifications });
      qc.invalidateQueries({ queryKey: qk.cc });
    },
  });
}

export function useSetScenario() {
  const qc = useQueryClient();
  const inv = useInvalidateAll();
  return useMutation({
    mutationFn: (key: string) =>
      api<{ active: string; updated: number; meaningful_symbols: string[]; provider_errors: Record<string, string> }>("/demo/scenario", {
        method: "POST",
        body: { key },
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: qk.scenarios });
      inv();
      toast.success("Market updated", {
        description: r.meaningful_symbols.length ? `Meaningful changes: ${r.meaningful_symbols.join(", ")}` : "No meaningful changes for your watchlists.",
      });
    },
    onError,
  });
}
