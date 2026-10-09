import { useEffect, useState, type FormEvent } from "react";
import Layout from "@/components/Layout";
import { useAuth, useRequireOwner } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { CreatableStaffRole, StaffMember } from "@/lib/types";

const ROLE_OPTIONS: { value: CreatableStaffRole; label: string }[] = [
  { value: "manager", label: "Manager" },
  { value: "trainer", label: "Trainer" },
  { value: "front_desk", label: "Front desk" },
];

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  manager: "Manager",
  trainer: "Trainer",
  front_desk: "Front desk",
};

function randomPassword(): string {
  // A reasonable default for "I'll create dummy credentials" — the owner
  // can overwrite it before submitting; this just saves typing one.
  return Math.random().toString(36).slice(2, 10) + Math.random().toString(36).slice(2, 6).toUpperCase();
}

export default function StaffPage() {
  const { session, loading, role } = useAuth();
  const authorized = useRequireOwner(role, loading);

  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [listError, setListError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(randomPassword());
  const [newRole, setNewRole] = useState<CreatableStaffRole>("front_desk");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null);

  async function loadStaff(token: string) {
    try {
      setStaff(await apiFetch<StaffMember[]>("/staff", { token }));
      setListError(null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Could not load staff");
    }
  }

  useEffect(() => {
    if (session && authorized) loadStaff(session.access_token);
  }, [session, authorized]);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch("/staff", {
        method: "POST",
        token: session.access_token,
        body: { email, password, role: newRole },
      });
      setCreated({ email, password });
      setEmail("");
      const next = randomPassword();
      setPassword(next);
      setNewRole("front_desk");
      setShowForm(false);
      await loadStaff(session.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create staff login");
    } finally {
      setSaving(false);
    }
  }

  if (loading || !session || !authorized) {
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
          <h1 className="text-xl font-semibold">Staff</h1>
          <button
            onClick={() => {
              setShowForm((v) => !v);
              setCreated(null);
            }}
            className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm"
          >
            {showForm ? "Cancel" : "Add staff"}
          </button>
        </div>
        <p className="text-sm opacity-70">
          Owner-only. Manager/Trainer/Front desk logins only see Members, Plans, Check-in, and Unmatched —
          Dashboard, Finance, and Devices stay visible to the owner alone.
        </p>

        {created && (
          <div className="rounded-lg border-2 border-yellow-400 bg-yellow-50 p-4 flex flex-col gap-1 text-sm">
            <p className="font-medium text-gray-900">
              Staff login created — hand these credentials to them directly (shown once):
            </p>
            <p>
              Email: <span className="font-mono">{created.email}</span>
            </p>
            <p>
              Password: <span className="font-mono">{created.password}</span>
            </p>
          </div>
        )}

        {showForm && (
          <form onSubmit={handleAdd} className="flex flex-col gap-3 border rounded p-4">
            <label className="flex flex-col gap-1 text-sm">
              Email
              <input
                type="email"
                className="border rounded px-3 py-2"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Password
              <input
                className="border rounded px-3 py-2 font-mono"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Role
              <select
                className="border rounded px-3 py-2"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as CreatableStaffRole)}
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
            {error && <p className="text-red-600 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-yellow-400 text-black py-2 disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create login"}
            </button>
          </form>
        )}

        {listError && <p className="text-red-600 text-sm">{listError}</p>}

        <div className="overflow-x-auto rounded-2xl shadow-sm border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="p-3 font-medium text-gray-600">Email</th>
                <th className="p-3 font-medium text-gray-600">Role</th>
                <th className="p-3 font-medium text-gray-600">Added</th>
              </tr>
            </thead>
            <tbody>
              {staff.map((s) => (
                <tr key={s.id} className="border-t border-gray-100">
                  <td className="p-3 text-gray-900">{s.email ?? "—"}</td>
                  <td className="p-3 text-gray-700">{ROLE_LABEL[s.role] ?? s.role}</td>
                  <td className="p-3 text-gray-500">{new Date(s.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {staff.length === 0 && !listError && (
                <tr>
                  <td colSpan={3} className="p-4 text-center text-gray-400">
                    No staff logins yet — just you.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
