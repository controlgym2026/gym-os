import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import type { Session } from "@supabase/supabase-js";
import Layout from "@/components/Layout";
import DashboardSummaryView from "@/components/DashboardSummaryView";
import { supabase } from "@/lib/supabaseClient";
import { apiFetch } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";

const PENDING_GYM_NAME_KEY = "gym-os:pending-gym-name";

type Staff = {
  id: string;
  tenant_id: string;
  branch_id: string | null;
  role: string;
};

type Me = { user_id: string; email: string | null; staff: Staff | null };

function readPendingGymName(): string {
  try {
    return window.localStorage.getItem(PENDING_GYM_NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

export default function Home() {
  const router = useRouter();
  // undefined = not checked yet, null = checked and signed out.
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [me, setMe] = useState<Me | null>(null);
  const [gymName, setGymName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Track the current session.
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  // Once we know the session, redirect if signed out, else check bootstrap status.
  useEffect(() => {
    if (session === undefined) return;
    if (session === null) {
      router.replace("/login");
      return;
    }
    apiFetch<Me>("/auth/me", { token: session.access_token })
      .then((result) => {
        setMe(result);
        if (!result.staff) setGymName(readPendingGymName());
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load account"));
  }, [session, router]);

  // Once we know the user has a staff row (a tenant), load this month's
  // dashboard summary — the default range on GET /dashboard/summary.
  function loadSummary(token: string) {
    apiFetch<DashboardSummary>("/dashboard/summary", { token })
      .then(setSummary)
      .catch((err) => setSummaryError(err instanceof Error ? err.message : "Could not load dashboard"));
  }

  useEffect(() => {
    if (!session || !me?.staff) return;
    loadSummary(session.access_token);
  }, [session, me]);

  // Dashboard is owner-only (see NavBar.tsx's Owner section) — a non-owner
  // staff member landing here directly gets sent to Members instead. UI
  // convenience only: GET /dashboard/summary independently 403s anyone who
  // isn't the owner (see require_owner in auth.py).
  useEffect(() => {
    if (me?.staff && me.staff.role !== "owner") {
      router.replace("/members");
    }
  }, [me, router]);

  async function handleBootstrap(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setError(null);
    setWorking(true);
    try {
      await apiFetch("/auth/bootstrap-tenant", {
        method: "POST",
        token: session.access_token,
        body: { gym_name: gymName },
      });
      try {
        window.localStorage.removeItem(PENDING_GYM_NAME_KEY);
      } catch {
        // ignore
      }
      setMe(await apiFetch<Me>("/auth/me", { token: session.access_token }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create your gym");
    } finally {
      setWorking(false);
    }
  }

  if (session === undefined) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  if (session === null) {
    return null; // redirect to /login in flight
  }

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <p className="text-red-600 text-sm max-w-sm text-center">{error}</p>
      </main>
    );
  }

  if (!me) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p>Loading…</p>
      </main>
    );
  }

  if (!me.staff) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <form onSubmit={handleBootstrap} className="w-full max-w-sm flex flex-col gap-4">
          <h1 className="text-xl font-semibold">Name your gym</h1>
          <p className="text-sm opacity-80">
            One more step — this creates your tenant and makes you its owner.
          </p>
          <input
            className="border rounded px-3 py-2"
            value={gymName}
            onChange={(e) => setGymName(e.target.value)}
            required
          />
          <button
            type="submit"
            disabled={working}
            className="rounded bg-yellow-400 text-black py-2 disabled:opacity-50"
          >
            {working ? "Creating…" : "Create gym"}
          </button>
        </form>
      </main>
    );
  }

  if (me.staff.role !== "owner") {
    return null; // redirecting to /members in flight
  }

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <h1 className="text-xl font-semibold text-gray-900">Dashboard</h1>
        {summaryError && <p className="text-red-600 text-sm">{summaryError}</p>}
        {summary ? (
          <DashboardSummaryView
            summary={summary}
            onMemberChanged={() => session && loadSummary(session.access_token)}
          />
        ) : (
          !summaryError && <p>Loading…</p>
        )}
      </div>
    </Layout>
  );
}
