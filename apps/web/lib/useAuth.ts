import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabaseClient";
import { apiFetch } from "@/lib/api";

/** Session + tenant_id for the Phase 1 pages. Redirects to /login when
 * signed out — same session-tracking pattern as pages/index.tsx, factored
 * out so the new members/plans/check-in pages don't each reimplement it.
 * Does not touch the auth pages themselves. */
export function useAuth() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  // getSession() resolves near-instantly (reads local storage), but
  // isSuperAdmin/tenantId only become accurate after the /auth/me round
  // trip below finishes — they start at their false/null defaults. A page
  // that gates a decision (e.g. admin pages redirecting non-admins away)
  // on `loading` alone would act on that stale default before the real
  // value ever arrives. profileLoaded tracks the /auth/me call specifically
  // so `loading` below covers both steps, not just session resolution.
  const [profileLoaded, setProfileLoaded] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (session === undefined) return;
    if (session === null) {
      router.replace("/login");
      return;
    }
    apiFetch<{ staff: { tenant_id: string } | null; is_super_admin: boolean }>("/auth/me", {
      token: session.access_token,
    })
      .then((me) => {
        setTenantId(me.staff?.tenant_id ?? null);
        setIsSuperAdmin(me.is_super_admin);
      })
      .catch(() => {
        setTenantId(null);
        setIsSuperAdmin(false);
      })
      .finally(() => setProfileLoaded(true));
  }, [session, router]);

  return {
    session: session ?? null,
    loading: session === undefined || (session !== null && !profileLoaded),
    tenantId,
    isSuperAdmin,
  };
}
