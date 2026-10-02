import "@/styles/globals.css";
import type { AppProps } from "next/app";
import Head from "next/head";

export default function App({ Component, pageProps }: AppProps) {
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
