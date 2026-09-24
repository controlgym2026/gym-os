import { useEffect, useMemo, useState } from "react";
import NavBar from "@/components/NavBar";
import DashboardSummaryView from "@/components/DashboardSummaryView";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";

type Period = "this_month" | "last_month" | "custom";

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function thisMonthRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth(), 1);
  return { from: toISODate(from), to: toISODate(now) };
}

function lastMonthRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const to = new Date(now.getFullYear(), now.getMonth(), 0); // day 0 = last day of previous month
  return { from: toISODate(from), to: toISODate(to) };
}

export default function FinancePage() {
  const { session, loading } = useAuth();
  const [period, setPeriod] = useState<Period>("this_month");
  const [customFrom, setCustomFrom] = useState(() => thisMonthRange().from);
  const [customTo, setCustomTo] = useState(() => toISODate(new Date()));
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const range = useMemo(() => {
    if (period === "this_month") return thisMonthRange();
    if (period === "last_month") return lastMonthRange();
    return { from: customFrom, to: customTo };
  }, [period, customFrom, customTo]);

  useEffect(() => {
    if (!session) return;
    apiFetch<DashboardSummary>(`/dashboard/summary?from=${range.from}&to=${range.to}`, {
      token: session.access_token,
    })
      .then(setSummary)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load finance report"));
  }, [session, range]);

  if (loading || !session) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <>
      <NavBar />
      <main className="max-w-5xl mx-auto p-6 flex flex-col gap-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <h1 className="text-xl font-semibold">Finance</h1>
          <div className="flex items-center gap-2 text-sm">
            {(["this_month", "last_month", "custom"] as Period[]).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`rounded border px-3 py-1.5 ${period === p ? "bg-foreground text-background" : ""}`}
              >
                {p === "this_month" ? "This Month" : p === "last_month" ? "Last Month" : "Custom"}
              </button>
            ))}
            {period === "custom" && (
              <>
                <input
                  type="date"
                  className="border rounded px-2 py-1"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                />
                <span>–</span>
                <input
                  type="date"
                  className="border rounded px-2 py-1"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                />
              </>
            )}
          </div>
        </div>
        <p className="text-sm opacity-70">
          {range.from} to {range.to}
        </p>

        {error && <p className="text-red-600 text-sm">{error}</p>}
        {summary ? <DashboardSummaryView summary={summary} /> : !error && <p>Loading…</p>}
      </main>
    </>
  );
}
