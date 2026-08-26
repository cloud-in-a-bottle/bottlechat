// Minimal app-shell cache.  Enough to install as a PWA and survive a flaky network on launch;
// deliberately not an offline mode — chat data is never cached, and every /api and /share
// request goes straight to the network.
const CACHE = "bottlechat-shell-v1";
const SHELL = ["/", "/manifest.webmanifest", "/favicon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function isCacheable(url) {
  // Hashed build output only.  Never the API, never a share transcript.
  return url.origin === self.location.origin && url.pathname.startsWith("/assets/");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/share")) return;

  if (request.mode === "navigate") {
    // Network first: a logged-out navigation must be free to redirect to /login rather than
    // being answered from cache.
    event.respondWith(fetch(request).catch(() => caches.match("/").then((r) => r || Response.error())));
    return;
  }

  if (isCacheable(url)) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }
});
