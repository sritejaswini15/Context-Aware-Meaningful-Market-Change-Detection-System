import type { z } from "zod";

export class ApiError extends Error {
  status: number;
  code: string;
  fields?: { loc: string[]; msg: string }[];

  constructor(status: number, code: string, message: string, fields?: { loc: string[]; msg: string }[]) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  refreshing ??= fetch("/api/auth/refresh", { method: "POST", credentials: "include" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => setTimeout(() => (refreshing = null), 0));
  return refreshing;
}

type Options = { method?: string; body?: unknown; schema?: z.ZodType; retry?: boolean };

/** Same-origin API call (Next.js proxies /api to FastAPI). Session lives in an httpOnly cookie. */
export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? "GET",
    credentials: "include",
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401 && opts.retry !== false && !path.startsWith("/auth/")) {
    if (await tryRefresh()) return api<T>(path, { ...opts, retry: false });
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; fields?: { loc: string[]; msg: string }[] } } | null)?.error;
    const message =
      res.status >= 500 && !err?.message
        ? "Knoww is having trouble reaching its servers. Please retry."
        : err?.message ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, err?.code ?? "error", message, err?.fields);
  }
  if (opts.schema) {
    const parsed = opts.schema.safeParse(data);
    if (!parsed.success) {
      // Never break the UI on a contract drift; surface it to developers.
      console.warn(`[knoww] response for ${path} did not match schema`, parsed.error.issues.slice(0, 5));
      return data as T;
    }
    return parsed.data as T;
  }
  return data as T;
}
