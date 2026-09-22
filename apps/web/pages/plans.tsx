import { useEffect, useState, type FormEvent } from "react";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { MembershipPlan } from "@/lib/types";

export default function PlansPage() {
  const { session, loading } = useAuth();
  const [plans, setPlans] = useState<MembershipPlan[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<MembershipPlan | null>(null);
  const [name, setName] = useState("");
  const [durationDays, setDurationDays] = useState("30");
  const [price, setPrice] = useState("");
  const [sessionLimit, setSessionLimit] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPlans(token: string) {
    setPlans(await apiFetch<MembershipPlan[]>("/membership-plans?include_inactive=true", { token }));
  }

  useEffect(() => {
    if (session) loadPlans(session.access_token).catch((e) => setError(String(e)));
  }, [session]);

  function startCreate() {
    setEditing(null);
    setName("");
    setDurationDays("30");
    setPrice("");
    setSessionLimit("");
    setShowForm(true);
  }

  function startEdit(plan: MembershipPlan) {
    setEditing(plan);
    setName(plan.name);
    setDurationDays(String(plan.duration_days));
    setPrice(String(plan.price));
    setSessionLimit(plan.session_limit === null ? "" : String(plan.session_limit));
    setShowForm(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setSaving(true);
    setError(null);
    try {
      const body = {
        name,
        duration_days: Number(durationDays),
        price: Number(price),
        session_limit: sessionLimit === "" ? null : Number(sessionLimit),
      };
      if (editing) {
        await apiFetch(`/membership-plans/${editing.id}`, {
          method: "PATCH",
          token: session.access_token,
          body,
        });
      } else {
        await apiFetch("/membership-plans", {
          method: "POST",
          token: session.access_token,
          body,
        });
      }
      setShowForm(false);
      await loadPlans(session.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save plan");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(plan: MembershipPlan) {
    if (!session) return;
    await apiFetch(`/membership-plans/${plan.id}`, {
      method: "PATCH",
      token: session.access_token,
      body: { is_active: !plan.is_active },
    });
    await loadPlans(session.access_token);
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
          <h1 className="text-xl font-semibold">Membership plans</h1>
          <button
            onClick={showForm ? () => setShowForm(false) : startCreate}
            className="rounded bg-foreground text-background px-3 py-1.5 text-sm"
          >
            {showForm ? "Cancel" : "New plan"}
          </button>
        </div>

        {showForm && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3 border rounded p-4">
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
              Duration (days)
              <input
                type="number"
                min={1}
                className="border rounded px-3 py-2"
                value={durationDays}
                onChange={(e) => setDurationDays(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Price
              <input
                type="number"
                min={0}
                step="0.01"
                className="border rounded px-3 py-2"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Session limit (leave blank for a date-based plan)
              <input
                type="number"
                min={1}
                className="border rounded px-3 py-2"
                value={sessionLimit}
                onChange={(e) => setSessionLimit(e.target.value)}
              />
            </label>
            {error && <p className="text-red-600 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-foreground text-background py-2 disabled:opacity-50"
            >
              {saving ? "Saving…" : editing ? "Save changes" : "Create plan"}
            </button>
          </form>
        )}

        <ul className="flex flex-col divide-y border rounded">
          {plans.map((p) => (
            <li key={p.id} className="flex items-center gap-3 p-3">
              <div className="flex flex-col flex-1">
                <span className={`font-medium ${p.is_active ? "" : "line-through opacity-50"}`}>{p.name}</span>
                <span className="text-sm opacity-70">
                  {p.duration_days}d · ₹{p.price}
                  {p.session_limit !== null ? ` · ${p.session_limit} sessions` : ""}
                </span>
              </div>
              <button onClick={() => startEdit(p)} className="text-sm underline">
                Edit
              </button>
              <button onClick={() => toggleActive(p)} className="text-sm underline">
                {p.is_active ? "Deactivate" : "Activate"}
              </button>
            </li>
          ))}
          {plans.length === 0 && <li className="p-3 text-sm opacity-70">No plans yet.</li>}
        </ul>
      </main>
    </>
  );
}
