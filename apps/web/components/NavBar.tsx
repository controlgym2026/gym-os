import Link from "next/link";
import { useRouter } from "next/router";
import { supabase } from "@/lib/supabaseClient";
import { useAuth } from "@/lib/useAuth";
import Logo from "./Logo";

// Visible to every staff role — Members/Plans/Check-in/Unmatched are
// everyday front-desk work, unrestricted on purpose.
const STAFF_LINKS = [
  { href: "/members", label: "Members" },
  { href: "/plans", label: "Plans" },
  { href: "/check-in", label: "Check-in" },
  { href: "/attendance/unmatched", label: "Unmatched" },
];

// Owner-only — financial data and device/staff management. Hiding these
// here is a convenience; the real boundary is require_owner() on each of
// these pages' own API calls (see auth.py), re-checked independently of
// what the nav shows.
const OWNER_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/finance", label: "Finance" },
  { href: "/devices", label: "Devices" },
  { href: "/staff", label: "Staff" },
];

export default function NavBar() {
  const router = useRouter();
  // UI-only — hiding links is a convenience, not the security boundary.
  // Every /admin/* and owner-only API call independently re-checks its own
  // role requirement server-side.
  const { isSuperAdmin, role } = useAuth();
  const isOwner = role === "owner";

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  function navLink(link: { href: string; label: string }) {
    const active = router.pathname === link.href || router.pathname.startsWith(`${link.href}/`);
    return (
      <Link
        key={link.href}
        href={link.href}
        className={active ? "font-semibold text-yellow-400" : "text-yellow-100/80 hover:text-yellow-300"}
      >
        {link.label}
      </Link>
    );
  }

  return (
    <nav className="bg-black">
      <div className="flex items-center gap-6 px-4 py-3 text-sm flex-wrap">
        <Link href="/" className="shrink-0">
          <Logo size="sm" />
        </Link>

        {isOwner && (
          <>
            {/* The Owner section — Dashboard/Finance/Devices/Staff — kept
                visually separate from everyday staff links by a label and
                a divider, not just interleaved into one flat list. */}
            <span className="text-[10px] font-semibold tracking-wide uppercase text-yellow-500/70">
              Owner
            </span>
            {OWNER_LINKS.map(navLink)}
            <span className="h-4 w-px bg-yellow-400/30" aria-hidden="true" />
          </>
        )}

        {STAFF_LINKS.map(navLink)}
        {isSuperAdmin && navLink({ href: "/admin", label: "Admin" })}

        <button
          onClick={handleSignOut}
          className="ml-auto rounded border border-yellow-400 text-yellow-300 px-3 py-1 text-xs hover:bg-yellow-400 hover:text-black transition-colors"
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
