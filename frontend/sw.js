// P:accine PWA 서비스워커 — 앱 셸(정적 자산)만 캐시. API/데이터는 항상 네트워크(민감·동적 데이터라 캐시 금지).
// 셸은 network-first(캐시는 오프라인 폴백)로 서빙 → 배포 시 항상 최신 UI가 뜨고, 캐시는 오프라인 대비용으로만 유지.
const SHELL_CACHE = "paccine-shell-v2";
const SHELL_ASSETS = [
  "/",
  "/app.js",
  "/styles.css",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API/데이터 요청은 캐시하지 않고 항상 네트워크로 (동적·민감 콘텐츠 보호).
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // 앱 셸/일반 자산 모두 network-first + 캐시 폴백 → 온라인이면 항상 최신 코드, 오프라인이면 캐시.
  const isShellAsset = SHELL_ASSETS.includes(url.pathname);
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (isShellAsset && response && response.ok) {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
