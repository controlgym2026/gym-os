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
  // 'owner' | 'manager' | 'trainer' | 'front_desk', or null before /auth/me
  // resolves (or if the user hasn't bootstrapped a tenant yet). Only
  // 'owner' sees Dashboard/Finance/Devices — see NavBar.tsx and each of
  // those pages' own redirect guard.
  const [role, setRole] = useState<string | null>(null);
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
    apiFetch<{ staff: { tenant_id: string; role: string } | null; is_super_admin: boolean }>("/auth/me", {
      token: session.access_token,
    })
      .then((me) => {
        setTenantId(me.staff?.tenant_id ?? null);
        setIsSuperAdmin(me.is_super_admin);
        setRole(me.staff?.role ?? null);
      })
      .catch(() => {
        setTenantId(null);
        setIsSuperAdmin(false);
        setRole(null);
      })
      .finally(() => setProfileLoaded(true));
  }, [session, router]);

  return {
    session: session ?? null,
    loading: session === undefined || (session !== null && !profileLoaded),
    tenantId,
    isSuperAdmin,
    role,
  };
}

/** Redirects away from an owner-only page (Dashboard/Finance/Devices/Staff)
 * once we know the viewer isn't the owner. Returns whether the page is
 * clear to render its real content — false while loading or while a
 * redirect is in flight, same shape as useAuth's own `loading`.
 *
 * UI convenience only, same relationship as isSuperAdmin has to /admin —
 * every owner-only API call independently re-checks role server-side (see
 * require_owner in auth.py), so a non-owner who somehow lands here briefly
 * still can't actually fetch anything restricted. */
export function useRequireOwner(role: string | null, loading: boolean): boolean {
  const router = useRouter();
  useEffect(() => {
    if (!loading && role !== "owner") {
      router.replace("/members");
    }
  }, [loading, role, router]);
  return !loading && role === "owner";
}
