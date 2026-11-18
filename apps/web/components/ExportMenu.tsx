import { useEffect, useRef, useState } from "react";
import { DownloadError, downloadFile } from "@/lib/api";

export type MemberListFilters = {
  /** The search text actually applied to the list (not what's still being typed). */
  q: string;
  status: string;
  photo: string;
  planId: string;
};

type Format = "csv" | "xlsx";

type Props = {
  token: string;
  filters: MemberListFilters;
  /** Row count of the current (filtered) list, from GET /members' total. */
  viewTotal: number;
};

function exportPath(format: Format, filters: MemberListFilters | null): string {
  const params = new URLSearchParams({ format });
  if (filters) {
    if (filters.q) params.set("q", filters.q);
    if (filters.status) params.set("filter", filters.status);
    if (filters.photo) params.set("photo", filters.photo);
    if (filters.planId) params.set("plan_id", filters.planId);
  }
  return `/members/export?${params}`;
}

/** "Export" dropdown on the Members page: CSV or Excel, and — when a search
 * or filter is active — "Current view (N members)" vs "All members". The
 * download goes through fetch + Authorization header + blob (downloadFile),
 * never a plain link. Rendered only for roles that can export (owner,
 * manager); the API enforces the same rule. */
export default function ExportMenu({ token, filters, viewTotal }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const filtered = Boolean(filters.q || filters.status || filters.photo || filters.planId);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function run(format: Format, scope: "view" | "all") {
    const label = `${scope === "view" ? "Current view" : "All members"} · ${format === "csv" ? "CSV" : "Excel"}`;
    setOpen(false);
    setBusy(label);
    setError(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await downloadFile(exportPath(format, scope === "view" ? filters : null), `members_${today}.${format}`, { token });
    } catch (err) {
      if (err instanceof DownloadError && err.status === 429) {
        setError(err.message || "Export limit reached — please try again later.");
      } else if (err instanceof DownloadError && err.status === 403) {
        setError("Your role can't export member data. Ask the gym owner or a manager.");
      } else {
        setError(`Export failed: ${err instanceof Error ? err.message : "please try again"}`);
      }
    } finally {
      setBusy(null);
    }
  }

  const item = "w-full text-left px-3 py-2 text-sm hover:bg-gray-100 disabled:opacity-50";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={busy !== null}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Download members data as CSV or Excel"
        className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
      >
        {busy ? "Exporting…" : "Export ▾"}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 sm:left-0 sm:right-auto z-20 mt-1 w-60 rounded border border-gray-200 bg-white shadow-lg py-1"
        >
          {filtered ? (
            <>
              <p className="px-3 pt-1 pb-0.5 text-xs font-medium text-gray-500">
                Current view ({viewTotal} member{viewTotal === 1 ? "" : "s"})
              </p>
              <button role="menuitem" className={item} onClick={() => run("csv", "view")}>
                CSV
              </button>
              <button role="menuitem" className={item} onClick={() => run("xlsx", "view")}>
                Excel (.xlsx)
              </button>
              <div className="my-1 border-t border-gray-100" />
              <p className="px-3 pt-1 pb-0.5 text-xs font-medium text-gray-500">All members</p>
              <button role="menuitem" className={item} onClick={() => run("csv", "all")}>
                CSV
              </button>
              <button role="menuitem" className={item} onClick={() => run("xlsx", "all")}>
                Excel (.xlsx)
              </button>
            </>
          ) : (
            <>
              <button role="menuitem" className={item} onClick={() => run("csv", "all")}>
                CSV
              </button>
              <button role="menuitem" className={item} onClick={() => run("xlsx", "all")}>
                Excel (.xlsx)
              </button>
            </>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="absolute right-0 sm:left-0 sm:right-auto z-10 mt-1 w-64 rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
          {error}{" "}
          <button className="underline" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      )}
    </div>
  );
}
