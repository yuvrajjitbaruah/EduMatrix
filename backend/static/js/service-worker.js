const CACHE_NAME = 'edumatrix-pwa-v7';
const CORE_ASSETS = [
  '/',
  '/offline/',
  '/about/',
  '/contact/',
  '/terms-and-conditions/',
  '/privacy-policy/',
  '/login/',
  '/signup/student/',
  '/signup/teacher/',
  '/static/css/styles.css?v=platform-polish-2026-04-24b',
  '/static/img/edumatrix-logo-transparent.png',
  '/static/img/edumatrix-icon-192.png',
  '/static/img/edumatrix-icon-512.png',
  '/static/manifest.webmanifest'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  event.respondWith(
    fetch(request)
      .then(response => {
        const clone = response.clone();
        if (response.ok && !url.pathname.startsWith('/dashboard/')) {
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => {
        if (request.mode === 'navigate') {
          return caches.match('/offline/').then(cached => cached || caches.match('/'));
        }
        return caches.match(request).then(cached => cached || caches.match('/offline/'));
      })
  );
});
