import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/lib/useAuth";
import { apiFetch } from "@/lib/api";
import type { Tenant } from "@/lib/types";

const STATUS_COLOR: Record<string, string> = {
  active: "text-green-600",
  trial: "text-blue-600",
  suspended: "text-red-600",
  cancelled: "opacity-50",
};

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

  if (loading || !session || !isSuperAdmin) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  return (
    <>
      <NavBar />
      <main className="max-w-3xl mx-auto p-6 flex flex-col gap-4">
        <h1 className="text-xl font-semibold">Tenants</h1>
        {error && <p className="text-red-600 text-sm">{error}</p>}

        <div className="overflow-x-auto border rounded">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">Name</th>
                <th className="p-2">Plan</th>
                <th className="p-2">Billing</th>
                <th className="p-2">Members</th>
                <th className="p-2">Active subs</th>
                <th className="p-2">Devices</th>
                <th className="p-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id} className="border-b last:border-0 hover:bg-black/5 dark:hover:bg-white/5">
                  <td className="p-2">
                    <Link href={`/admin/tenants/${t.id}`} className="underline font-medium">
                      {t.name}
                    </Link>
                  </td>
                  <td className="p-2">{t.plan_tier}</td>
                  <td className={`p-2 font-medium ${STATUS_COLOR[t.billing_status] ?? ""}`}>{t.billing_status}</td>
                  <td className="p-2">{t.member_count}</td>
                  <td className="p-2">{t.active_subscription_count}</td>
                  <td className="p-2">{t.device_count}</td>
                  <td className="p-2 opacity-70">{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {tenants.length === 0 && !error && <p className="p-3 text-sm opacity-70">No tenants yet.</p>}
        </div>
      </main>
    </>
  );
}
