import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import Layout from "@/components/Layout";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { BillingStatus, TenantDetail } from "@/lib/types";

const BILLING_ACTIONS: { status: BillingStatus; label: string; confirm?: boolean }[] = [
  { status: "active", label: "Activate" },
  { status: "trial", label: "Set to trial" },
  { status: "suspended", label: "Suspend", confirm: true },
  { status: "cancelled", label: "Cancel", confirm: true },
];

export default function AdminTenantDetailPage() {
  const router = useRouter();
  const tenantId = typeof router.query.id === "string" ? router.query.id : null;
  const { session, loading, isSuperAdmin } = useAuth();

  const [tenant, setTenant] = useState<TenantDetail | null>(null);
  const [note, setNote] = useState("");
  const [planTier, setPlanTier] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(token: string, id: string) {
    const t = await apiFetch<TenantDetail>(`/admin/tenants/${id}`, { token });
    setTenant(t);
    setPlanTier(t.plan_tier);
  }

  useEffect(() => {
    if (!loading && session && !isSuperAdmin) router.replace("/");
  }, [loading, session, isSuperAdmin, router]);

  useEffect(() => {
    if (session && isSuperAdmin && tenantId) {
      load(session.access_token, tenantId).catch((e) =>
        setError(e instanceof Error ? e.message : "Could not load tenant"),
      );
    }
  }, [session, isSuperAdmin, tenantId]);

  async function applyBillingStatus(status: BillingStatus, confirmMsg?: string) {
    if (!session || !tenantId) return;
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/admin/tenants/${tenantId}`, {
        method: "PATCH",
        token: session.access_token,
        body: { billing_status: status, note: note || undefined },
      });
      setNote("");
      await load(session.access_token, tenantId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update billing status");
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePlanTier(e: FormEvent) {
    e.preventDefault();
    if (!session || !tenantId) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/admin/tenants/${tenantId}`, {
        method: "PATCH",
        token: session.access_token,
        body: { plan_tier: planTier, note: note || undefined },
      });
      setNote("");
      await load(session.access_token, tenantId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update plan tier");
    } finally {
      setBusy(false);
    }
  }

  if (loading || !session || !isSuperAdmin || !tenantId) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  if (!tenant) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <p className="text-red-600 text-sm">{error ?? "Loading…"}</p>
      </main>
    );
  }

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold">{tenant.name}</h1>
          <p className="text-sm opacity-70">
            {tenant.member_count} members · {tenant.active_subscription_count} active subscriptions ·{" "}
            {tenant.device_count} devices · created {new Date(tenant.created_at).toLocaleDateString()}
          </p>
        </div>

        {error && <p className="text-red-600 text-sm">{error}</p>}

        <section className="border rounded p-4 flex flex-col gap-3">
          <h2 className="font-semibold">
            Billing — <span className="font-normal">{tenant.billing_status}</span>
          </h2>
          <label className="flex flex-col gap-1 text-sm">
            Note (recorded in the audit log for the next action taken below)
            <input
              className="border rounded px-3 py-2"
              placeholder="e.g. non-payment, requested trial extension"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {BILLING_ACTIONS.map((a) => (
              <button
                key={a.status}
                disabled={busy || tenant.billing_status === a.status}
                onClick={() =>
                  applyBillingStatus(
                    a.status,
                    a.confirm
                      ? `${a.label} "${tenant.name}"? This changes their live Gym OS access.`
                      : undefined,
                  )
                }
                className="rounded border px-3 py-1.5 text-sm disabled:opacity-40"
              >
                {a.label}
              </button>
            ))}
          </div>

          <form onSubmit={handleSavePlanTier} className="flex gap-2 items-end pt-2 border-t mt-1">
            <label className="flex flex-col gap-1 text-sm flex-1">
              Plan tier
              <input
                className="border rounded px-3 py-2"
                value={planTier}
                onChange={(e) => setPlanTier(e.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={busy || planTier === tenant.plan_tier}
              className="rounded bg-foreground text-background px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Save plan
            </button>
          </form>
        </section>

        <section className="border rounded p-4">
          <h2 className="font-semibold mb-2">Branches ({tenant.branches.length})</h2>
          <ul className="text-sm divide-y">
            {tenant.branches.map((b) => (
              <li key={b.id} className="py-1.5">
                {b.address || "(no address)"} · {b.timezone}
              </li>
            ))}
            {tenant.branches.length === 0 && <li className="py-1.5 opacity-70">None.</li>}
          </ul>
        </section>

        <section className="border rounded p-4">
          <h2 className="font-semibold mb-2">Staff ({tenant.staff.length})</h2>
          <ul className="text-sm divide-y">
            {tenant.staff.map((s) => (
              <li key={s.id} className="py-1.5 flex justify-between">
                <span>{s.email ?? s.id}</span>
                <span className="opacity-70">{s.role}</span>
              </li>
            ))}
            {tenant.staff.length === 0 && <li className="py-1.5 opacity-70">None.</li>}
          </ul>
        </section>

        <section className="border rounded p-4">
          <h2 className="font-semibold mb-2">Audit log</h2>
          <ul className="text-sm divide-y">
            {tenant.audit_log.map((entry) => (
              <li key={entry.id} className="py-1.5">
                <span className="font-medium">{entry.action}</span> by {entry.performed_by} ·{" "}
                {new Date(entry.created_at).toLocaleString()}
                {entry.note && <div className="opacity-70">{entry.note}</div>}
              </li>
            ))}
            {tenant.audit_log.length === 0 && <li className="py-1.5 opacity-70">No actions recorded yet.</li>}
          </ul>
        </section>
      </div>
    </Layout>
  );
}
