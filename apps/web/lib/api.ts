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

/** Shared by apiFetch and downloadFile below: does the request, and on a
 * 401 — the access token the caller passed is invalid/expired, which
 * shouldn't normally happen (Supabase's own background auto-refresh is
 * supposed to keep it from happening) but can if e.g. a tab was left
 * asleep long enough to miss its refresh window — tries one explicit
 * refreshSession() and retries before concluding the session is actually
 * dead, signing out, and sending the browser to /login. Returns the raw
 * Response; callers still need to check res.ok themselves (one wants
 * .json(), the other wants .blob()). */
async function fetchWithAuth(path: string, opts: FetchOpts): Promise<Response> {
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

  return res;
}

/** Minimal JSON fetch wrapper for the FastAPI backend (apps/api). */
export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const res = await fetchWithAuth(path, opts);

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${opts.method ?? "GET"} ${path} -> ${res.status} ${detail}`);
  }

  return (await res.json()) as T;
}

/** Fetches a binary response (PDF/Excel/etc.) and triggers a browser
 * download — `apiFetch` above assumes JSON, which a file response isn't. A
 * plain `<a href>` can't carry the Authorization header, so this goes
 * through fetch + blob + a throwaway object URL instead. */
export async function downloadFile(path: string, filename: string, opts: FetchOpts = {}): Promise<void> {
  const res = await fetchWithAuth(path, opts);

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${opts.method ?? "GET"} ${path} -> ${res.status} ${detail}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
