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

/** Thrown by downloadFile for a non-2xx response. `message` is the API's
 * own `detail` text when there is one (e.g. the export rate-limit message),
 * so callers can show it to staff as-is. */
export class DownloadError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "DownloadError";
  }
}

/** filename="…" from a Content-Disposition header, if the server sent one
 * (and CORS exposes it — see expose_headers in apps/api/main.py). */
function filenameFromDisposition(header: string | null): string | null {
  const match = header?.match(/filename="?([^";]+)"?/i);
  return match ? match[1] : null;
}

/** Fetches a binary response (PDF/Excel/etc.) and triggers a browser
 * download — `apiFetch` above assumes JSON, which a file response isn't. A
 * plain `<a href>` can't carry the Authorization header, so this goes
 * through fetch + blob + a throwaway object URL instead. `filename` is the
 * fallback; a server-sent Content-Disposition file name wins. */
export async function downloadFile(path: string, filename: string, opts: FetchOpts = {}): Promise<void> {
  const res = await fetchWithAuth(path, opts);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = text;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      /* not JSON — keep the raw text */
    }
    throw new DownloadError(detail || `${opts.method ?? "GET"} ${path} -> ${res.status}`, res.status);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filenameFromDisposition(res.headers.get("Content-Disposition")) ?? filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
