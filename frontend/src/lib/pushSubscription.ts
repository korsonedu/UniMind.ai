/** PWA 推送订阅工具。将浏览器 PushSubscription 同步到后端。 */

import api from './api';

function urlB64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = window.atob(base64.replace(/-/g, '+').replace(/_/g, '/') + padding);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

export async function subscribeToPush(): Promise<boolean> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return false;

  const registration = await navigator.serviceWorker.ready;

  // Check existing subscription
  const existing = await registration.pushManager.getSubscription();
  if (existing) {
    // Sync to backend
    await syncSubscription(existing);
    return true;
  }

  // Request notification permission
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return false;

  // Subscribe with VAPID public key
  try {
    const vapidPublicKey = import.meta.env.VITE_VAPID_PUBLIC_KEY;
    if (!vapidPublicKey) {
      console.warn('VITE_VAPID_PUBLIC_KEY not configured');
      return false;
    }

    const sub = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8Array(vapidPublicKey),
    });

    await syncSubscription(sub);
    return true;
  } catch (e) {
    console.warn('Push subscription failed:', e);
    return false;
  }
}

async function syncSubscription(sub: PushSubscription): Promise<void> {
  const json = sub.toJSON();
  const payload = {
    endpoint: json.endpoint,
    keys: {
      p256dh: json.keys?.p256dh || '',
      auth: json.keys?.auth || '',
    },
  };
  try {
    await api.post('/users/me/push-subscribe/', payload);
  } catch {
    // ignore — will retry next time
  }
}

export async function unsubscribePush(): Promise<void> {
  const registration = await navigator.serviceWorker.ready;
  const sub = await registration.pushManager.getSubscription();
  if (sub) {
    const json = sub.toJSON();
    await sub.unsubscribe();
    try {
      await api.delete('/users/me/push-subscribe/', { data: { endpoint: json.endpoint } });
    } catch {
      // ignore
    }
  }
}
