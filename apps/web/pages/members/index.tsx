import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import MemberPhoto from "@/components/MemberPhoto";
import MemberDetailsModal from "@/components/MemberDetailsModal";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import { supabase } from "@/lib/supabaseClient";
import type { Member, MemberImportResult, PaginatedMembers, SubscriptionStatus } from "@/lib/types";

const PAGE_SIZE = 25;

const STATUS_BADGE: Record<SubscriptionStatus, string> = {
  ACTIVE: "bg-emerald-100 text-emerald-700",
  FROZEN: "bg-blue-100 text-blue-700",
  EXPIRED: "bg-gray-100 text-gray-600",
  CANCELLED: "bg-red-100 text-red-700",
};

function shortId(id: string) {
  return id.slice(0, 8).toUpperCase();
}

function digitsOnly(phone: string) {
  return phone.replace(/\D/g, "");
}

function daysLeftLabel(endDate: string | null, sessionsRemaining: number | null): string {
  if (endDate) {
    const ms = new Date(endDate).getTime() - new Date().setHours(0, 0, 0, 0);
    const days = Math.ceil(ms / 86_400_000);
    return days >= 0 ? `${days}d` : "Expired";
  }
  if (sessionsRemaining !== null) return `${sessionsRemaining} sessions`;
  return "—";
}

export default function MembersPage() {
  const { session, loading, tenantId } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const importInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<MemberImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);

  async function loadMembers(token: string, query: string, pageNum: number) {
    try {
      const params = new URLSearchParams({ page: String(pageNum), page_size: String(PAGE_SIZE) });
      if (query) params.set("q", query);
      const result = await apiFetch<PaginatedMembers>(`/members?${params}`, { token });
      // Defensive: fail with a message instead of crashing the page if the
      // response is ever not the shape this page expects (e.g. a stale
      // cached bundle talking to a backend that changed shape, or a bad
      // deploy) — members.map() on a non-array is exactly what "Application
      // error: a client-side exception" looks like to a user.
      if (!Array.isArray(result?.items)) {
        throw new Error("Unexpected response from the server — try refreshing the page.");
      }
      setMembers(result.items);
      setTotal(result.total);
      setPage(result.page);
      setListError(null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Could not load members");
    }
  }

  useEffect(() => {
    if (session) loadMembers(session.access_token, "", 1);
  }, [session]);

  function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (session) loadMembers(session.access_token, q, 1); // new search always starts at page 1
  }

  function goToPage(pageNum: number) {
    if (session) loadMembers(session.access_token, q, pageNum);
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setSaving(true);
    setError(null);
    try {
      const member = await apiFetch<Member>("/members", {
        method: "POST",
        token: session.access_token,
        body: {
          name,
          phone: phone || undefined,
          email: email || undefined,
        },
      });

      if (photoFile && tenantId) {
        const ext = photoFile.name.split(".").pop() || "jpg";
        const path = `${tenantId}/members/${member.id}/photo.${ext}`;
        const { error: uploadError } = await supabase.storage
          .from("member-media")
          .upload(path, photoFile, { upsert: true });
        if (!uploadError) {
          await apiFetch(`/members/${member.id}`, {
            method: "PATCH",
            token: session.access_token,
            body: { photo_url: path },
          });
        }
      }

      setName("");
      setPhone("");
      setEmail("");
      setPhotoFile(null);
      setShowForm(false);
      await loadMembers(session.access_token, q, page);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add member");
    } finally {
      setSaving(false);
    }
  }

  async function handleImportFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file later
    if (!file || !session) return;
    setImporting(true);
    setImportError(null);
    setImportResult(null);
    try {
      const text = await file.text();
      const result = await apiFetch<MemberImportResult>("/members/import", {
        method: "POST",
        token: session.access_token,
        body: { csv: text },
      });
      setImportResult(result);
      await loadMembers(session.access_token, q, page);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Could not import CSV");
    } finally {
      setImporting(false);
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
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h1 className="text-xl font-semibold">Members</h1>
          <div className="flex gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept=".csv,text/csv"
              hidden
              onChange={handleImportFile}
            />
            <button
              onClick={() => importInputRef.current?.click()}
              disabled={importing}
              title="CSV columns: name (required), phone, email, plan_name"
              className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
            >
              {importing ? "Importing…" : "Import CSV"}
            </button>
            <button
              onClick={() => setShowForm((v) => !v)}
              className="rounded bg-foreground text-background px-3 py-1.5 text-sm"
            >
              {showForm ? "Cancel" : "Add member"}
            </button>
          </div>
        </div>

        {importError && <p className="text-red-600 text-sm">{importError}</p>}
        {importResult && (
          <div className="border rounded p-3 text-sm flex flex-col gap-1">
            <p>
              ✓ {importResult.imported} imported
              {importResult.subscriptions_started > 0 && ` · ${importResult.subscriptions_started} subscription(s) started`}
              {importResult.skipped.length > 0 && ` · ${importResult.skipped.length} skipped`}
              {importResult.plan_warnings.length > 0 && ` · ${importResult.plan_warnings.length} plan(s) not found`}
            </p>
            {importResult.skipped.length > 0 && (
              <ul className="text-xs opacity-70 list-disc list-inside">
                {importResult.skipped.map((s, i) => (
                  <li key={i}>
                    row {s.line}: {s.reason}
                  </li>
                ))}
              </ul>
            )}
            {importResult.plan_warnings.length > 0 && (
              <ul className="text-xs opacity-70 list-disc list-inside">
                {importResult.plan_warnings.map((w, i) => (
                  <li key={i}>
                    row {w.line}: plan &ldquo;{w.plan_name}&rdquo; not found — member imported, no subscription started
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {showForm && (
          <form onSubmit={handleAdd} className="flex flex-col gap-3 border rounded p-4">
            <label className="flex flex-col gap-1 text-sm">
              Name
              <input
                className="border rounded px-3 py-2"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Phone
              <input
                className="border rounded px-3 py-2"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Email
              <input
                type="email"
                className="border rounded px-3 py-2"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Photo
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setPhotoFile(e.target.files?.[0] ?? null)}
              />
            </label>
            {error && <p className="text-red-600 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-foreground text-background py-2 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save member"}
            </button>
          </form>
        )}

        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            className="border rounded px-3 py-2 flex-1"
            placeholder="Search by name or phone"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button type="submit" className="rounded border px-3 py-2 text-sm">
            Search
          </button>
        </form>

        {listError && <p className="text-red-600 text-sm">{listError}</p>}

        <div className="overflow-x-auto rounded-2xl shadow-sm border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="p-3 font-medium text-gray-600">Member</th>
                <th className="p-3 font-medium text-gray-600">Phone Number</th>
                <th className="p-3 font-medium text-gray-600">Days Left</th>
                <th className="p-3 font-medium text-gray-600">Expiry Date</th>
                <th className="p-3 font-medium text-gray-600">Due Amount</th>
                <th className="p-3 font-medium text-gray-600">Status</th>
                <th className="p-3 font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => {
                const sub = m.current_subscription;
                return (
                  <tr key={m.id} className="border-t border-gray-100">
                    <td className="p-3">
                      <Link href={`/members/${m.id}`} className="flex items-center gap-3 hover:underline">
                        <MemberPhoto path={m.photo_url} name={m.name} />
                        <div className="flex flex-col">
                          <span className="font-medium text-gray-900">{m.name}</span>
                          <span className="text-xs text-gray-400">#{shortId(m.id)}</span>
                        </div>
                      </Link>
                    </td>
                    <td className="p-3 text-gray-700">{m.phone || "—"}</td>
                    {sub ? (
                      <>
                        <td className="p-3 text-gray-700">{daysLeftLabel(sub.end_date, sub.sessions_remaining)}</td>
                        <td className="p-3 text-gray-700">{sub.end_date ?? "—"}</td>
                        <td className="p-3">
                          {sub.due_amount > 0 ? (
                            <span className="text-amber-600 font-medium">₹{sub.due_amount}</span>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td className="p-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[sub.status]}`}>
                            {sub.status.charAt(0) + sub.status.slice(1).toLowerCase()}
                          </span>
                        </td>
                      </>
                    ) : (
                      <td colSpan={4} className="p-3 text-gray-400">
                        No active plan
                      </td>
                    )}
                    <td className="p-3">
                      <div className="flex gap-2">
                        {m.phone ? (
                          <a
                            href={`https://wa.me/${digitsOnly(m.phone)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="WhatsApp"
                            className="w-8 h-8 rounded-full border border-emerald-600 text-emerald-700 flex items-center justify-center hover:bg-emerald-50"
                          >
                            🟢
                          </a>
                        ) : (
                          <span className="w-8 h-8" />
                        )}
                        <button
                          onClick={() => setSelectedMemberId(m.id)}
                          title="View details"
                          className="w-8 h-8 rounded-full border flex items-center justify-center hover:bg-gray-50"
                        >
                          👁️
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {members.length === 0 && !listError && (
                <tr>
                  <td colSpan={7} className="p-4 text-center text-gray-400">
                    No members yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {total > 0 && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total} members
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => goToPage(page - 1)}
                disabled={page <= 1}
                className="rounded border px-3 py-1.5 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                onClick={() => goToPage(page + 1)}
                disabled={page * PAGE_SIZE >= total}
                className="rounded border px-3 py-1.5 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {selectedMemberId && (
        <MemberDetailsModal
          memberId={selectedMemberId}
          onClose={() => setSelectedMemberId(null)}
          onChanged={() => session && loadMembers(session.access_token, q, page)}
        />
      )}
    </Layout>
  );
}
