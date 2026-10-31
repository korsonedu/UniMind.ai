/// <reference lib="WebWorker" />

import { precacheAndRoute, cleanupOutdatedCaches, createHandlerBoundToURL } from 'workbox-precaching';
import { clientsClaim } from 'workbox-core';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { NetworkFirst, NetworkOnly } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Parameters<typeof precacheAndRoute>[0] };

self.skipWaiting();
clientsClaim();

// Precache
cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

// Offline navigation for the app shell; APIs stay network-only below.
registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), {
  denylist: [/^\/api\//, /^\/admin\//, /^\/media\//, /^\/static\//, /^\/assets\//, /^\/health\//],
}));

// API runtime caching
registerRoute(
  ({ url }) => url.pathname === '/api/users/me/',
  new NetworkOnly(),
);
// Notes and practice data come from the encrypted desktop cache when offline;
// never serve another account's cached response.
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/notes/') || url.pathname.startsWith('/api/ai/practice/'),
  new NetworkOnly(),
);
registerRoute(
  /^https?:\/\/.*\/api\/.*/i,
  new NetworkFirst({
    cacheName: 'api-cache',
    plugins: [new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 300 })],
  }),
);

self.addEventListener('activate', event => {
  event.waitUntil(caches.delete('api-cache'));
});

// ── Push notifications ──

self.addEventListener('push', (event: PushEvent) => {
  if (!event.data) return;
  try {
    const payload = event.data.json();
    const title = payload.title || 'UniMind';
    const options: NotificationOptions & { vibrate?: number[] } = {
      body: payload.body || '',
      icon: '/pwa-192x192.png',
      badge: '/pwa-192x192.png',
      data: { link: payload.link || '/' },
      vibrate: [200, 100, 200],
      requireInteraction: true,
    };
    event.waitUntil(self.registration.showNotification(title, options));
  } catch {
    event.waitUntil(
      self.registration.showNotification('UniMind', {
        body: event.data.text(),
        icon: '/pwa-192x192.png',
      })
    );
  }
});

self.addEventListener('notificationclick', (event: NotificationEvent) => {
  event.notification.close();
  const link = event.notification.data?.link || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes(link) && 'focus' in client) {
          return (client as WindowClient).focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(link);
      }
    })
  );
});

export {};
