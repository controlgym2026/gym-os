import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import MemberPhoto from "@/components/MemberPhoto";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import { supabase } from "@/lib/supabaseClient";
import type { Member, MemberImportResult } from "@/lib/types";

export default function MembersPage() {
  const { session, loading, tenantId } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
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

  async function loadMembers(token: string, query: string) {
    try {
      const params = query ? `?q=${encodeURIComponent(query)}` : "";
      setMembers(await apiFetch<Member[]>(`/members${params}`, { token }));
      setListError(null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Could not load members");
    }
  }

  useEffect(() => {
    if (session) loadMembers(session.access_token, "");
  }, [session]);

  function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (session) loadMembers(session.access_token, q);
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
      await loadMembers(session.access_token, q);
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
      await loadMembers(session.access_token, q);
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

        <ul className="flex flex-col divide-y border rounded">
          {members.map((m) => (
            <li key={m.id}>
              <Link href={`/members/${m.id}`} className="flex items-center gap-3 p-3 hover:bg-black/5">
                <MemberPhoto path={m.photo_url} />
                <div className="flex flex-col">
                  <span className="font-medium">{m.name}</span>
                  <span className="text-sm opacity-70">{m.phone || m.email || "—"}</span>
                </div>
              </Link>
            </li>
          ))}
          {members.length === 0 && !listError && (
            <li className="p-3 text-sm opacity-70">No members yet.</li>
          )}
        </ul>
      </div>
    </Layout>
  );
}
