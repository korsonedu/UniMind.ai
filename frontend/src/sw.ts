/// <reference lib="WebWorker" />

import { precacheAndRoute, cleanupOutdatedCaches, createHandlerBoundToURL } from 'workbox-precaching';
import { clientsClaim } from 'workbox-core';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { NetworkOnly } from 'workbox-strategies';

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Parameters<typeof precacheAndRoute>[0] };

self.skipWaiting();
clientsClaim();

// Precache
cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

// Offline navigation for the app shell; APIs stay network-only below.
registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), {
  denylist: [/^\/api\//, /^\/accounts\//, /^\/account-api\//, /^\/admin\//, /^\/media\//, /^\/static\//, /^\/assets\//, /^\/health\//],
}));

// Private API data stays out of shared browser caches. Desktop offline data is account-bound.
registerRoute(
  /^https?:\/\/.*\/api\/.*/i,
  new NetworkOnly(),
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
