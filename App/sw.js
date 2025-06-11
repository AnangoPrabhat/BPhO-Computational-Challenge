// A unique name for your cache. Change this when you update any of the cached files.
const CACHE_NAME = 'bpho-optics-cache-v1';

// A list of all the essential files your app needs to function offline.
const URLS_TO_CACHE = [
  '/', // The main homepage
  '/static/bpho_logo.jpg',
  '/static/optics_image_1.jpg',
  '/static/Tall1.jpg',
  // The PWA icons need to be cached too. This list should match your manifest.json
  '/static/icons/icon-72x72.png',
  '/static/icons/icon-96x96.png',
  '/static/icons/icon-128x128.png',
  '/static/icons/icon-144x144.png',
  '/static/icons/icon-152x152.png',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-384x384.png',
  '/static/icons/icon-512x512.png'
];

// --- INSTALL ---
self.addEventListener('install', (event) => {
  console.log('Service Worker: Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker: Caching app shell');
        return cache.addAll(URLS_TO_CACHE);
      })
      .then(() => {
        console.log('Service Worker: Installation complete.');
        return self.skipWaiting();
      })
  );
});

// --- ACTIVATE ---
self.addEventListener('activate', (event) => {
  console.log('Service Worker: Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('Service Worker: Clearing old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
        console.log('Service Worker: Activation complete.');
        return self.clients.claim();
    })
  );
});

// --- FETCH ---
// This event fires for every network request.
// We use a "Cache-First" strategy for our static assets in URLS_TO_CACHE.
// We use a "Network falling back to cache" strategy for everything else.
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // Strategy: Cache-First for core static assets.
  if (URLS_TO_CACHE.includes(requestUrl.pathname)) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        return cachedResponse || fetch(event.request);
      })
    );
    return;
  }

  // Strategy: Network-First for dynamic content (HTML pages, plots).
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // If the fetch is successful, cache the response for offline use later.
        return caches.open(CACHE_NAME).then((cache) => {
          // We only cache GET requests.
          if (event.request.method === 'GET') {
              cache.put(event.request, networkResponse.clone());
          }
          return networkResponse;
        });
      })
      .catch(() => {
        // If the network request fails (e.g., user is offline),
        // try to serve the response from the cache.
        return caches.match(event.request);
      })
  );
});
