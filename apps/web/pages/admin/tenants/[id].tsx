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

  // Gym Control subscription (Livnexa Care's own billing relationship with
  // this gym — separate from the gym's own member subscriptions/payments).
  const [expiresAt, setExpiresAt] = useState("");
  const [memberLimit, setMemberLimit] = useState("");
  const [deviceLimit, setDeviceLimit] = useState("");
  const [branchLimit, setBranchLimit] = useState("");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentNote, setPaymentNote] = useState("");

  async function load(token: string, id: string) {
    const t = await apiFetch<TenantDetail>(`/admin/tenants/${id}`, { token });
    setTenant(t);
    setPlanTier(t.plan_tier);
    setExpiresAt(t.subscription_expires_at ?? "");
    setMemberLimit(t.member_limit !== null ? String(t.member_limit) : "");
    setDeviceLimit(t.device_limit !== null ? String(t.device_limit) : "");
    setBranchLimit(t.branch_limit !== null ? String(t.branch_limit) : "");
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

  async function handleSaveSubscription(e: FormEvent) {
    e.preventDefault();
    if (!session || !tenantId || !expiresAt) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/admin/tenants/${tenantId}`, {
        method: "PATCH",
        token: session.access_token,
        body: { subscription_expires_at: expiresAt, note: note || undefined },
      });
      setNote("");
      await load(session.access_token, tenantId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the subscription date");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveLimits(e: FormEvent) {
    e.preventDefault();
    if (!session || !tenantId) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/admin/tenants/${tenantId}`, {
        method: "PATCH",
        token: session.access_token,
        body: {
          member_limit: memberLimit ? Number(memberLimit) : undefined,
          device_limit: deviceLimit ? Number(deviceLimit) : undefined,
          branch_limit: branchLimit ? Number(branchLimit) : undefined,
          note: note || undefined,
        },
      });
      setNote("");
      await load(session.access_token, tenantId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update resource limits");
    } finally {
      setBusy(false);
    }
  }

  async function handleRecordPayment(e: FormEvent) {
    e.preventDefault();
    if (!session || !tenantId || !paymentAmount) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/admin/tenants/${tenantId}/payments`, {
        method: "POST",
        token: session.access_token,
        body: { amount: Number(paymentAmount), note: paymentNote || undefined },
      });
      setPaymentAmount("");
      setPaymentNote("");
      await load(session.access_token, tenantId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the payment");
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
            {tenant.device_count} devices · {tenant.branch_count} branches · created{" "}
            {new Date(tenant.created_at).toLocaleDateString()}
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
              className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Save plan
            </button>
          </form>
        </section>

        <section className="border rounded p-4 flex flex-col gap-3">
          <h2 className="font-semibold">Gym Control subscription (Livnexa Care billing)</h2>
          <p className="text-sm">
            {tenant.subscription_expires_at ? (
              <>
                Renews/expires <strong>{new Date(tenant.subscription_expires_at).toLocaleDateString()}</strong>
                {tenant.subscription_days_remaining !== null && (
                  <span
                    className={
                      tenant.subscription_days_remaining < 0
                        ? " text-red-600 font-medium"
                        : tenant.subscription_days_remaining <= 7
                          ? " text-amber-600 font-medium"
                          : " text-gray-500"
                    }
                  >
                    {" "}
                    (
                    {tenant.subscription_days_remaining < 0
                      ? `expired ${Math.abs(tenant.subscription_days_remaining)}d ago`
                      : `${tenant.subscription_days_remaining}d left`}
                    )
                  </span>
                )}
              </>
            ) : (
              <span className="opacity-60">No subscription date set yet.</span>
            )}
          </p>
          <form onSubmit={handleSaveSubscription} className="flex gap-2 items-end">
            <label className="flex flex-col gap-1 text-sm">
              Expires on
              <input
                type="date"
                className="border rounded px-3 py-2"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                required
              />
            </label>
            <button
              type="submit"
              disabled={busy || !expiresAt}
              className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Save date
            </button>
          </form>
        </section>

        <section className="border rounded p-4 flex flex-col gap-3">
          <h2 className="font-semibold">Resource limits</h2>
          <p className="text-xs opacity-70">
            Display-only for now — shown as usage/limit on the dashboard, not enforced against creating new
            members/devices/branches.
          </p>
          <form onSubmit={handleSaveLimits} className="flex flex-wrap gap-3 items-end">
            <label className="flex flex-col gap-1 text-sm">
              Member limit
              <input
                type="number"
                min={1}
                className="border rounded px-3 py-2 w-28"
                placeholder="Unlimited"
                value={memberLimit}
                onChange={(e) => setMemberLimit(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Device limit
              <input
                type="number"
                min={1}
                className="border rounded px-3 py-2 w-28"
                placeholder="Unlimited"
                value={deviceLimit}
                onChange={(e) => setDeviceLimit(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Branch limit
              <input
                type="number"
                min={1}
                className="border rounded px-3 py-2 w-28"
                placeholder="Unlimited"
                value={branchLimit}
                onChange={(e) => setBranchLimit(e.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Save limits
            </button>
          </form>
        </section>

        <section className="border rounded p-4 flex flex-col gap-3">
          <h2 className="font-semibold">
            Paid to Livnexa Care — <span className="font-normal">₹{tenant.amount_paid.toLocaleString()}</span>
          </h2>
          <p className="text-xs opacity-70">
            What this gym has paid for Gym Control — unrelated to their own members&rsquo; payments. Recording a
            payment adds to the running total below, rather than replacing it.
          </p>
          <form onSubmit={handleRecordPayment} className="flex flex-wrap gap-2 items-end">
            <label className="flex flex-col gap-1 text-sm">
              Amount received
              <input
                type="number"
                min={0.01}
                step="0.01"
                className="border rounded px-3 py-2 w-32"
                value={paymentAmount}
                onChange={(e) => setPaymentAmount(e.target.value)}
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-sm flex-1 min-w-[12rem]">
              Note (optional)
              <input
                className="border rounded px-3 py-2"
                placeholder="e.g. UPI transfer, annual renewal"
                value={paymentNote}
                onChange={(e) => setPaymentNote(e.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={busy || !paymentAmount}
              className="rounded bg-yellow-400 text-black px-3 py-1.5 text-sm disabled:opacity-50"
            >
              Record payment
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
