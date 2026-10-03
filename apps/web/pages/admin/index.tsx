import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import Layout from "@/components/Layout";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { Tenant } from "@/lib/types";

const STATUS_BADGE: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700",
  trial: "bg-blue-100 text-blue-700",
  suspended: "bg-red-100 text-red-700",
  cancelled: "bg-gray-100 text-gray-500",
};

function fmtMoney(n: number) {
  return `₹${n.toLocaleString()}`;
}

/** Days-remaining badge: red once lapsed, amber inside a week, green
 * otherwise — same "expiring soon" window as the members list's own
 * subscription filter, so the convention reads the same way everywhere. */
function DaysRemainingBadge({ days }: { days: number | null }) {
  if (days === null) {
    return <span className="text-xs text-gray-400">Not set</span>;
  }
  const cls =
    days < 0
      ? "bg-red-100 text-red-700"
      : days <= 7
        ? "bg-amber-100 text-amber-700"
        : "bg-emerald-100 text-emerald-700";
  const label = days < 0 ? `Expired ${Math.abs(days)}d ago` : `${days}d left`;
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>{label}</span>;
}

function UsageCell({ used, limit }: { used: number; limit: number | null }) {
  const over = limit !== null && used > limit;
  return (
    <span className={over ? "text-red-600 font-medium" : ""}>
      {used}
      {limit !== null && <span className="opacity-60"> / {limit}</span>}
    </span>
  );
}

export default function AdminTenantsPage() {
  const router = useRouter();
  const { session, loading, isSuperAdmin } = useAuth();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Client-side UX only — the real boundary is the API rejecting non-admins.
    if (!loading && session && !isSuperAdmin) router.replace("/");
  }, [loading, session, isSuperAdmin, router]);

  useEffect(() => {
    if (!session || !isSuperAdmin) return;
    apiFetch<Tenant[]>("/admin/tenants", { token: session.access_token })
      .then(setTenants)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load tenants"));
  }, [session, isSuperAdmin]);

  const stats = useMemo(() => {
    const totalPaid = tenants.reduce((sum, t) => sum + t.amount_paid, 0);
    const expiringSoon = tenants.filter(
      (t) => t.subscription_days_remaining !== null && t.subscription_days_remaining <= 7,
    ).length;
    const active = tenants.filter((t) => t.billing_status === "active").length;
    return { totalPaid, expiringSoon, active, total: tenants.length };
  }, [tenants]);

  if (loading || !session || !isSuperAdmin) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <h1 className="text-xl font-semibold text-gray-900">Super Admin Dashboard</h1>
        {error && <p className="text-red-600 text-sm">{error}</p>}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-2xl p-4 shadow-sm border bg-white border-gray-200">
            <p className="text-xs text-gray-500">Gyms on Gym Control</p>
            <p className="text-xl font-bold text-gray-900">{stats.total}</p>
          </div>
          <div className="rounded-2xl p-4 shadow-sm border bg-white border-gray-200 border-l-4 border-l-yellow-400">
            <p className="text-xs text-gray-500">Total paid to Livnexa Care</p>
            <p className="text-xl font-bold text-gray-900">{fmtMoney(stats.totalPaid)}</p>
          </div>
          <div className="rounded-2xl p-4 shadow-sm border bg-white border-gray-200">
            <p className="text-xs text-gray-500">Active billing status</p>
            <p className="text-xl font-bold text-gray-900">{stats.active}</p>
          </div>
          <div className="rounded-2xl p-4 shadow-sm border bg-white border-gray-200">
            <p className="text-xs text-gray-500">Subscription expiring ≤7d or lapsed</p>
            <p className={`text-xl font-bold ${stats.expiringSoon > 0 ? "text-red-600" : "text-gray-900"}`}>
              {stats.expiringSoon}
            </p>
          </div>
        </div>

        <div className="overflow-x-auto rounded-2xl shadow-sm border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-black text-yellow-300 text-left">
                <th className="p-2.5 font-medium">Gym</th>
                <th className="p-2.5 font-medium">Plan</th>
                <th className="p-2.5 font-medium">Billing</th>
                <th className="p-2.5 font-medium">Gym Control subscription</th>
                <th className="p-2.5 font-medium">Members</th>
                <th className="p-2.5 font-medium">Devices</th>
                <th className="p-2.5 font-medium">Branches</th>
                <th className="p-2.5 font-medium">Paid to date</th>
                <th className="p-2.5 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t, i) => (
                <tr key={t.id} className={i % 2 === 1 ? "bg-gray-50" : "bg-white"}>
                  <td className="p-2.5">
                    <Link href={`/admin/tenants/${t.id}`} className="underline font-medium text-gray-900">
                      {t.name}
                    </Link>
                  </td>
                  <td className="p-2.5 text-gray-700">{t.plan_tier}</td>
                  <td className="p-2.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[t.billing_status] ?? ""}`}>
                      {t.billing_status}
                    </span>
                  </td>
                  <td className="p-2.5">
                    <DaysRemainingBadge days={t.subscription_days_remaining} />
                  </td>
                  <td className="p-2.5 text-gray-700">
                    <UsageCell used={t.member_count} limit={t.member_limit} />
                  </td>
                  <td className="p-2.5 text-gray-700">
                    <UsageCell used={t.device_count} limit={t.device_limit} />
                  </td>
                  <td className="p-2.5 text-gray-700">
                    <UsageCell used={t.branch_count} limit={t.branch_limit} />
                  </td>
                  <td className="p-2.5 text-gray-900 font-medium">{fmtMoney(t.amount_paid)}</td>
                  <td className="p-2.5 text-gray-500">{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {tenants.length === 0 && !error && <p className="p-3 text-sm text-gray-400">No tenants yet.</p>}
        </div>
      </div>
    </Layout>
  );
}
