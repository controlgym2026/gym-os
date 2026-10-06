// Deliberately minimal — this service worker exists ONLY to satisfy the
// "Add to Home Screen" / install-prompt criteria some browsers (Android
// Chrome in particular) require, not to provide offline support. It never
// caches anything: every request goes straight to the network. This app is
// live-data-only (member status, check-ins, payments) — serving a stale
// cached response while offline would be actively wrong, e.g. showing an
// expired member as active, or letting a check-in appear to succeed when
// it never reached the server. If real offline support is ever wanted,
// that's a deliberate, separate feature, not a side effect of installability.
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request));
});
