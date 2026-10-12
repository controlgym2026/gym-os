import { useEffect, useState } from "react";
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
  // Phones and tablets get a menu button instead of 8 links wrapping onto
  // three lines; the full row only shows from lg (1024px) up.
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const close = () => setMenuOpen(false);
    router.events.on("routeChangeStart", close);
    return () => router.events.off("routeChangeStart", close);
  }, [router.events]);

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  const links = isSuperAdmin ? [...LINKS, { href: "/admin", label: "Admin" }] : LINKS;
  const isActive = (href: string) => router.pathname === href || router.pathname.startsWith(`${href}/`);

  return (
    <nav className="bg-black sticky top-0 z-40">
      <div className="flex items-center gap-6 px-4 py-3 text-sm">
        <Link href="/" className="shrink-0">
          <Logo size="sm" />
        </Link>
        <div className="hidden lg:flex items-center gap-6">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={isActive(link.href) ? "font-semibold text-yellow-400" : "text-yellow-100/80 hover:text-yellow-300"}
            >
              {link.label}
            </Link>
          ))}
        </div>
        <button
          onClick={handleSignOut}
          className="ml-auto hidden lg:block rounded border border-yellow-400 text-yellow-300 px-3 py-1 text-xs hover:bg-yellow-400 hover:text-black transition-colors"
        >
          Sign out
        </button>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          className="ml-auto lg:hidden w-10 h-10 -mr-2 flex items-center justify-center text-yellow-300 text-2xl"
        >
          {menuOpen ? "✕" : "☰"}
        </button>
      </div>
      {menuOpen && (
        <div className="lg:hidden border-t border-white/10 px-2 pt-2 pb-3 grid grid-cols-2 sm:grid-cols-4 gap-1 text-sm">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded px-3 py-3 ${
                isActive(link.href) ? "bg-yellow-400 text-black font-semibold" : "text-yellow-100/90 hover:bg-white/10"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <button onClick={handleSignOut} className="rounded px-3 py-3 text-left border border-yellow-400 text-yellow-300">
            Sign out
          </button>
        </div>
      )}
    </nav>
  );
}
