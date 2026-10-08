import { supabase } from "./supabaseClient";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type FetchOpts = {
  method?: string;
  /** Supabase session access token, sent as `Authorization: Bearer <token>`. */
  token?: string;
  body?: unknown;
};

function doFetch(path: string, opts: FetchOpts, token: string | undefined) {
  return fetch(`${API_BASE_URL}${path}`, {
    method: opts.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
}

/** Minimal fetch wrapper for the FastAPI backend (apps/api).
 *
 * A 401 means the access token the caller passed is invalid/expired —
 * Supabase's own background auto-refresh is supposed to keep that from
 * happening, but it can miss its window (e.g. a tab left asleep for a
 * while), and every page's own generic "Could not load X" error was
 * leaving people staring at a stuck page with no indication they just
 * needed to log back in. So: one explicit refresh-and-retry first (quietly
 * recovers the common case, a merely few-seconds-stale token), and only if
 * that also fails, sign out and send the browser to /login instead of
 * throwing into a page that'll just show a confusing error. */
export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  let res = await doFetch(path, opts, opts.token);

  if (res.status === 401 && opts.token) {
    const { data, error } = await supabase.auth.refreshSession();
    if (!error && data.session) {
      res = await doFetch(path, opts, data.session.access_token);
    }
  }

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      await supabase.auth.signOut().catch(() => {});
      window.location.href = "/login";
    }
    throw new Error("Session expired — please log in again");
  }

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${opts.method ?? "GET"} ${path} -> ${res.status} ${detail}`);
  }

  return (await res.json()) as T;
}
