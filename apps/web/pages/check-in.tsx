import { useState, type FormEvent } from "react";
import Layout from "@/components/Layout";
import MemberPhoto from "@/components/MemberPhoto";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { Member, PaginatedMembers } from "@/lib/types";

type Result = { memberName: string; ok: boolean; message: string };

export default function CheckInPage() {
  const { session, loading } = useAuth();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Member[]>([]);
  const [searching, setSearching] = useState(false);
  const [checkingInId, setCheckingInId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<Result | null>(null);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!session || !q.trim()) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      const result = await apiFetch<PaginatedMembers>(`/members?q=${encodeURIComponent(q)}`, {
        token: session.access_token,
      });
      setResults(result.items);
    } finally {
      setSearching(false);
    }
  }

  // "QR" is just a scan resolving to a member_id and calling the same
  // endpoint with source: "qr" — no scanner UI this phase, tap-to-check-in
  // stands in for it.
  async function handleCheckIn(member: Member, source: "manual" | "qr" = "manual") {
    if (!session) return;
    setCheckingInId(member.id);
    setLastResult(null);
    try {
      await apiFetch("/attendance/check-in", {
        method: "POST",
        token: session.access_token,
        body: { member_id: member.id, source },
      });
      setLastResult({ memberName: member.name, ok: true, message: "Checked in" });
    } catch (err) {
      setLastResult({
        memberName: member.name,
        ok: false,
        message: err instanceof Error ? err.message : "Check-in failed",
      });
    } finally {
      setCheckingInId(null);
    }
  }

  if (loading || !session) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <Layout>
      <div className="max-w-md mx-auto flex flex-col gap-4">
        <h1 className="text-xl font-semibold">Check in</h1>
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            className="border rounded px-3 py-2 flex-1"
            placeholder="Search by name or phone"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoFocus
          />
          <button type="submit" className="rounded border px-3 py-2 text-sm">
            {searching ? "…" : "Search"}
          </button>
        </form>

        {lastResult && (
          <p className={`text-sm ${lastResult.ok ? "text-green-600" : "text-red-600"}`}>
            {lastResult.memberName}: {lastResult.message}
          </p>
        )}

        <ul className="flex flex-col divide-y border rounded">
          {results.map((m) => (
            <li key={m.id} className="flex items-center gap-3 p-3">
              <MemberPhoto path={m.photo_url} name={m.name} />
              <span className="flex-1 font-medium">{m.name}</span>
              <button
                onClick={() => handleCheckIn(m)}
                disabled={checkingInId === m.id}
                className="rounded bg-foreground text-background px-3 py-1.5 text-sm disabled:opacity-50"
              >
                {checkingInId === m.id ? "…" : "Check in"}
              </button>
            </li>
          ))}
          {results.length === 0 && (
            <li className="p-3 text-sm opacity-70">Search for a member to check them in.</li>
          )}
        </ul>
      </div>
    </Layout>
  );
}
