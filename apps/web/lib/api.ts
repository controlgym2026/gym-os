const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type FetchOpts = {
  method?: string;
  /** Supabase session access token, sent as `Authorization: Bearer <token>`. */
  token?: string;
  body?: unknown;
};

/** Minimal fetch wrapper for the FastAPI backend (apps/api). */
export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: opts.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${opts.method ?? "GET"} ${path} -> ${res.status} ${detail}`);
  }

  return (await res.json()) as T;
}
