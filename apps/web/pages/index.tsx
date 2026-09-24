import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import type { Session } from "@supabase/supabase-js";
import NavBar from "@/components/NavBar";
import { supabase } from "@/lib/supabaseClient";
import { apiFetch } from "@/lib/api";

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
            className="rounded bg-foreground text-background py-2 disabled:opacity-50"
          >
            {working ? "Creating…" : "Create gym"}
          </button>
        </form>
      </main>
    );
  }

  return (
    <>
      <NavBar />
      <main className="min-h-screen flex flex-col items-center justify-center gap-4 p-8">
        <p>
          Signed in as <strong>{me.email}</strong> — role <strong>{me.staff.role}</strong>
        </p>
        <p className="text-sm opacity-70">tenant_id: {me.staff.tenant_id}</p>
      </main>
    </>
  );
}
