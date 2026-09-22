import Link from "next/link";
import { useRouter } from "next/router";
import { supabase } from "@/lib/supabaseClient";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/members", label: "Members" },
  { href: "/plans", label: "Plans" },
  { href: "/check-in", label: "Check-in" },
  { href: "/devices", label: "Devices" },
  { href: "/attendance/unmatched", label: "Unmatched" },
];

export default function NavBar() {
  const router = useRouter();

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <nav className="flex items-center gap-4 border-b px-4 py-3 text-sm">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={router.pathname === link.href ? "font-semibold underline" : "opacity-80 hover:opacity-100"}
        >
          {link.label}
        </Link>
      ))}
      <button onClick={handleSignOut} className="ml-auto opacity-70 hover:opacity-100">
        Sign out
      </button>
    </nav>
  );
}
