import { z } from "zod";

const ts = z.string();
const num = z.number();
const nnum = z.number().nullable();
const nstr = z.string().nullable();

export const AttentionSchema = z.enum(["LOW", "MEDIUM", "HIGH"]);
export type Attention = z.infer<typeof AttentionSchema>;

export const UserSchema = z.object({
  id: z.string(),
  email: z.string(),
  display_name: nstr,
  onboarded: z.boolean(),
  auth_provider: z.string(),
  created_at: ts,
});
export type User = z.infer<typeof UserSchema>;

export const FreshnessSchema = z.object({
  status: z.enum(["LIVE", "FRESH", "DELAYED", "STALE", "CONFLICTED"]),
  label: z.string(),
  age_seconds: num,
  is_stale: z.boolean(),
  is_conflicted: z.boolean(),
  market_timestamp: ts,
  provider: z.string(),
  sources_count: num,
  simulated: z.boolean(),
});
export type Freshness = z.infer<typeof FreshnessSchema>;

export const SignalSchema = z.object({
  score: num,
  attention: AttentionSchema,
  movement_type: z.string(),
  context_label: z.string(),
  confidence: num,
  confidence_level: AttentionSchema,
  headline: z.string(),
  caveats: z.array(z.string()),
  evaluated_at: nstr.optional(),
});

export const StockStateSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  sector: nstr,
  sector_benchmark: nstr,
  exchange: nstr,
  currency: z.string(),
  kind: z.string(),
  priority: nstr.optional(),
  price: nnum,
  day_change_pct: nnum,
  since_check_pct: nnum,
  sector_since_check_pct: nnum.optional(),
  market_since_check_pct: nnum.optional(),
  volume: nnum,
  volume_ratio: nnum,
  freshness: FreshnessSchema.nullable(),
  baseline: z.object({ price: num, checked_at: ts, reason: z.string(), status: z.string() }).nullable(),
  signal: SignalSchema.nullable(),
  change_id: nstr.optional(),
  change_state: nstr.optional(),
});
export type StockState = z.infer<typeof StockStateSchema>;

export const FactorSchema = z.object({
  key: z.string(),
  label: z.string(),
  points: num,
  max_points: num,
  detail: z.string(),
  enabled: z.boolean().optional(),
});
export type Factor = z.infer<typeof FactorSchema>;

export const ExplanationSchema = z.object({
  source: z.enum(["AI", "FALLBACK"]),
  status: z.enum(["READY", "PENDING", "UPDATING"]),
  summary: z.string(),
  why_it_matters: z.string(),
  key_factors: z.array(z.string()),
  attention: z.string(),
  confidence: z.string(),
  model: nstr.optional(),
  error: nstr.optional(),
  is_latest: z.boolean(),
  generated_at: ts,
});
export type Explanation = z.infer<typeof ExplanationSchema>;

export const ChangeCardSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  name: z.string(),
  sector: nstr,
  attention: AttentionSchema,
  peak_attention: AttentionSchema,
  score: num,
  movement_type: z.string(),
  context_label: z.string(),
  direction: z.enum(["UP", "DOWN"]),
  change_pct: num,
  day_change_pct: nnum,
  sector_change_pct: nnum,
  market_change_pct: nnum,
  volume_ratio: nnum,
  price: nnum,
  baseline_price: nnum,
  checked_at: nstr,
  confidence: num,
  confidence_level: AttentionSchema,
  data_status: z.string(),
  headline: z.string(),
  summary: nstr.optional(),
  state: z.enum(["NEW", "SEEN", "ACKNOWLEDGED"]),
  status: z.string(),
  generation: num,
  created_at: ts,
  updated_at: ts,
  caveats: z.array(z.string()),
});
export type ChangeCard = z.infer<typeof ChangeCardSchema>;

export const ChangeDetailSchema = ChangeCardSchema.extend({
  factors: z.array(FactorSchema),
  explanation: ExplanationSchema,
  freshness: FreshnessSchema.nullable(),
  history: z.array(ChangeCardSchema),
});
export type ChangeDetail = z.infer<typeof ChangeDetailSchema>;

export const ChangeListSchema = z.object({
  items: z.array(ChangeCardSchema),
  total: num,
  counts: z.record(z.string(), num),
});
export type ChangeList = z.infer<typeof ChangeListSchema>;

export const MarketBenchSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  price: nnum,
  day_change_pct: nnum,
  since_check_pct: nnum.optional(),
  freshness: FreshnessSchema.nullable(),
});
export type MarketBench = z.infer<typeof MarketBenchSchema>;

export const MarketContextSchema = z.object({
  session: z.string(),
  simulated: z.boolean(),
  scenario: nstr,
  market: MarketBenchSchema.nullable(),
  sectors: z.array(MarketBenchSchema),
  summary: z.string(),
  last_update: nstr,
});
export type MarketContext = z.infer<typeof MarketContextSchema>;

export const WatchlistSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  symbols_count: num,
  symbols: z.array(z.string()),
  high_count: num,
  medium_count: num,
  created_at: ts,
  updated_at: ts,
});
export type WatchlistSummary = z.infer<typeof WatchlistSummarySchema>;

export const WatchlistSchema = WatchlistSummarySchema.extend({
  items: z.array(z.object({ symbol: z.string(), name: z.string(), priority: z.string(), added_at: ts })),
});
export type Watchlist = z.infer<typeof WatchlistSchema>;

export const ActivitySchema = z.object({
  kind: z.string(),
  at: ts,
  title: z.string(),
  symbol: nstr.optional(),
  attention: nstr.optional(),
  change_id: nstr.optional(),
});

export const CommandCenterSchema = z.object({
  user: UserSchema,
  last_checked_at: nstr,
  counts: z.record(z.string(), num),
  needs_attention: z.array(ChangeCardSchema),
  reviewed: z.array(ChangeCardSchema),
  quiet: z.array(StockStateSchema),
  market_context: MarketContextSchema,
  watchlists: z.array(WatchlistSummarySchema),
  recent_activity: z.array(ActivitySchema),
  data_quality: z.record(z.string(), num),
  ai: z.object({ configured: z.boolean(), available: z.boolean() }),
  unread_notifications: num,
});
export type CommandCenter = z.infer<typeof CommandCenterSchema>;

export const SearchResultSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  exchange: nstr,
  sector: nstr,
  price: nnum,
  day_change_pct: nnum,
  in_watchlists: z.array(z.string()),
});
export type SearchResult = z.infer<typeof SearchResultSchema>;

export const EventSchema = z.object({
  id: num,
  event_type: z.string(),
  headline: z.string(),
  summary: nstr,
  source: nstr,
  url: nstr,
  event_time: ts,
  significance: num,
});

export const StockDetailSchema = z.object({
  state: StockStateSchema,
  signal_basis: z.enum(["CHECKPOINT", "PREVIOUS_CLOSE", "NONE"]),
  factors: z.array(FactorSchema),
  change: ChangeCardSchema.nullable(),
  explanation: ExplanationSchema.nullable(),
  sector: MarketBenchSchema.nullable(),
  market: MarketBenchSchema.nullable(),
  events: z.array(EventSchema),
  conflict: z
    .object({
      detected_at: ts,
      observations: z.array(z.object({ provider: z.string(), price: num, market_timestamp: ts, reliability: num })),
      chosen_provider: z.string(),
      chosen_price: num,
      spread_pct: num,
      tolerance_pct: num,
      resolution: z.string(),
    })
    .nullable(),
  in_watchlists: z.array(z.string()),
  stats: z.object({ daily_volatility_pct: nnum, avg_volume_20d: nnum, history_available: z.boolean() }),
});
export type StockDetail = z.infer<typeof StockDetailSchema>;

export const HistorySchema = z.object({
  symbol: z.string(),
  sector_symbol: nstr,
  market_symbol: z.string(),
  price: z.array(z.object({ date: z.string(), close: num, volume: nnum })),
  relative: z.array(z.object({ date: z.string(), stock: nnum, sector: nnum.optional(), market: nnum.optional() })),
  volume: z.object({ bars: z.array(z.object({ date: z.string(), close: num, volume: nnum })), avg_20d: nnum, available: z.boolean() }),
  since_check: z.array(z.object({ at: z.string(), stock: nnum, sector: nnum, market: nnum })),
  baseline_at: nstr,
  history_available: z.boolean(),
});
export type History = z.infer<typeof HistorySchema>;

export const SignalHistorySchema = z.object({
  signals: z.array(
    z.object({ id: num, at: ts, score: num, attention: AttentionSchema, movement_type: z.string(), confidence: num, change_pct: nnum, data_status: nstr, headline: z.string() }),
  ),
  changes: z.array(ChangeCardSchema),
});
export type SignalHistory = z.infer<typeof SignalHistorySchema>;

export const PreferencesSchema = z.object({
  sensitivity: z.enum(["LOW", "BALANCED", "HIGH"]),
  include_volume: z.boolean(),
  include_market_context: z.boolean(),
  include_events: z.boolean(),
  notify_min_attention: z.enum(["HIGH", "MEDIUM"]),
  updated_at: ts,
});
export type Preferences = z.infer<typeof PreferencesSchema>;

export const NotificationSchema = z.object({
  id: z.string(),
  kind: z.string(),
  title: z.string(),
  body: z.string(),
  attention: nstr,
  symbol: nstr,
  change_event_id: nstr,
  read_at: nstr,
  created_at: ts,
});
export const NotificationListSchema = z.object({ items: z.array(NotificationSchema), unread: num });
export type NotificationList = z.infer<typeof NotificationListSchema>;

export const HealthSchema = z.object({
  status: z.string(),
  checked_at: ts,
  components: z.array(z.object({ key: z.string(), name: z.string(), status: z.string(), detail: z.string() })),
  providers: z.array(
    z.object({
      name: z.string(),
      status: z.string(),
      reliability: num,
      realtime: z.boolean(),
      last_success_at: nstr,
      last_failure_at: nstr,
      consecutive_failures: num,
      last_error: nstr,
      simulated: z.boolean(),
    }),
  ),
  last_market_update: nstr,
  conflicts_24h: num,
  environment: z.string(),
  version: z.string(),
  demo_mode: z.boolean(),
});
export type Health = z.infer<typeof HealthSchema>;

export const ScenariosSchema = z.object({
  enabled: z.boolean(),
  active: nstr,
  activated_at: nstr,
  scenarios: z.array(z.object({ key: z.string(), title: z.string(), description: z.string(), expectation: z.string(), faults: z.array(z.string()) })),
});
export type Scenarios = z.infer<typeof ScenariosSchema>;

export const AuthResultSchema = z.object({
  status: z.enum(["OK", "CONFIRMATION_REQUIRED"]),
  user: UserSchema.nullable().optional(),
  token: nstr.optional(),
});

// Forms
export const CredentialsSchema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
});
export const WatchlistNameSchema = z.string().trim().min(1, "Name is required").max(80, "Keep it under 80 characters");
