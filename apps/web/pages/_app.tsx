import "@/styles/globals.css";
import { useEffect } from "react";
import type { AppProps } from "next/app";
import Head from "next/head";

export default function App({ Component, pageProps }: AppProps) {
  useEffect(() => {
    // Registers public/sw.js — a deliberately empty pass-through worker
    // (see its own comment) that exists only so "Add to Home Screen" is
    // available on phones, not for offline support. Guarded for browsers
    // without the API and for non-HTTPS (service workers require a secure
    // context; this silently no-ops on localhost-without-HTTPS dev setups
    // some people use, rather than throwing).
    if (typeof window !== "undefined" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Installability is a nice-to-have, not a requirement to use the
        // app — a failed registration (e.g. served over plain HTTP) isn't
        // worth surfacing to the user.
      });
    }
  }, []);

  return (
    <>
      {/* No page sets its own <title>/description yet, so this default
          covers every page; a page that later needs its own just adds its
          own next/head and Next merges it in. */}
      <Head>
        <title>Gym Control</title>
        <meta name="description" content="Gym Control — gym management software. A product of Livnexa Care Pvt Ltd." />
      </Head>
      <Component {...pageProps} />
    </>
  );
}
