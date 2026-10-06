import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        {/* public/favicon.ico is auto-served at /favicon.ico by convention, but
            explicit links also cover modern/high-DPI browsers and iOS — all
            generated from the Gym Control mark in public/logo.png. */}
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="icon" href="/favicon-16x16.png" type="image/png" sizes="16x16" />
        <link rel="icon" href="/favicon-32x32.png" type="image/png" sizes="32x32" />
        <link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <meta name="theme-color" content="#000000" />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />

        {/* Installable on a phone ("Add to Home Screen") as a standalone,
            app-like window — see public/manifest.json. */}
        <link rel="manifest" href="/manifest.json" />
        {/* iOS Safari ignores manifest.json for most of this and needs its
            own meta tags instead; apple-touch-icon above is shared with both. */}
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black" />
        <meta name="apple-mobile-web-app-title" content="Gym Control" />
      </Head>
      <body className="antialiased">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
