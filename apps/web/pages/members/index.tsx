import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import NavBar from "@/components/NavBar";
import MemberPhoto from "@/components/MemberPhoto";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import { supabase } from "@/lib/supabaseClient";
import type { Member } from "@/lib/types";

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
      <main className="max-w-2xl mx-auto p-6 flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Members</h1>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="rounded bg-foreground text-background px-3 py-1.5 text-sm"
          >
            {showForm ? "Cancel" : "Add member"}
          </button>
        </div>

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
              <Link href={`/members/${m.id}`} className="flex items-center gap-3 p-3 hover:bg-black/5 dark:hover:bg-white/5">
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
      </main>
    </>
  );
}
