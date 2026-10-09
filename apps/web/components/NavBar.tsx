import Link from "next/link";
import { useRouter } from "next/router";
import { supabase } from "@/lib/supabaseClient";
import { useAuth } from "@/lib/useAuth";
import Logo from "./Logo";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/finance", label: "Finance" },
  { href: "/members", label: "Members" },
  { href: "/plans", label: "Plans" },
  { href: "/check-in", label: "Check-in" },
  { href: "/devices", label: "Devices" },
  { href: "/attendance/unmatched", label: "Unmatched" },
];

export default function NavBar() {
  const router = useRouter();
  // UI-only — hiding the link is a convenience, not the security boundary.
  // Every /admin/* API call independently re-checks super-admin status.
  const { isSuperAdmin } = useAuth();

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  const links = isSuperAdmin ? [...LINKS, { href: "/admin", label: "Admin" }] : LINKS;

  return (
    <nav className="bg-black">
      <div className="flex items-center gap-6 px-4 py-3 text-sm flex-wrap">
        <Link href="/" className="shrink-0">
          <Logo size="sm" />
        </Link>
        {links.map((link) => {
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
        })}
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
