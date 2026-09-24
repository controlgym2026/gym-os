import type { ReactNode } from "react";
import NavBar from "./NavBar";

/** Shared page chrome for every authenticated page: the nav bar + a
 * consistent, responsive max-width container. One width/theme for the
 * whole app instead of each page picking its own max-w-* — reused rather
 * than copy-pasted per page. */
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <NavBar />
      <main className="max-w-6xl mx-auto w-full px-4 sm:px-6 py-6">{children}</main>
    </>
  );
}
