import { api, type Platform } from "./api";
import { getPlatform, isNative } from "./platform";

async function subscribeWebPush(): Promise<string | null> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return null;
  }

  const registration = await navigator.serviceWorker.ready;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return null;
  }

  const vapidPublicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  if (!vapidPublicKey) {
    console.warn("VAPID public key not configured");
    return null;
  }

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
  });

  return JSON.stringify(subscription);
}

async function subscribeNativePush(): Promise<string | null> {
  try {
    const { PushNotifications } = await import(
      "@capacitor/push-notifications"
    );

    const permResult = await PushNotifications.requestPermissions();
    if (permResult.receive !== "granted") {
      return null;
    }

    return new Promise((resolve) => {
      PushNotifications.addListener("registration", (token) => {
        resolve(token.value);
      });

      PushNotifications.addListener("registrationError", () => {
        resolve(null);
      });

      PushNotifications.register();
    });
  } catch {
    console.warn("Native push notifications not available");
    return null;
  }
}

export async function subscribeToPushNotifications(): Promise<boolean> {
  const platform = getPlatform();
  let token: string | null = null;
  let apiPlatform: Platform;

  if (isNative()) {
    token = await subscribeNativePush();
    apiPlatform = platform === "ios" ? "ios" : "web";
  } else {
    token = await subscribeWebPush();
    apiPlatform = "web";
  }

  if (!token) {
    return false;
  }

  try {
    await api.devices.register(token, apiPlatform);
    return true;
  } catch {
    console.error("Failed to register device token");
    return false;
  }
}

export async function setupNativeListeners(): Promise<void> {
  if (!isNative()) return;

  try {
    const { PushNotifications } = await import(
      "@capacitor/push-notifications"
    );

    PushNotifications.addListener(
      "pushNotificationReceived",
      (notification) => {
        console.log("Push notification received:", notification);
      },
    );

    PushNotifications.addListener(
      "pushNotificationActionPerformed",
      (action) => {
        const data = action.notification.data;
        if (data?.url) {
          window.location.href = data.url;
        }
      },
    );
  } catch {
    console.warn("Could not setup native push listeners");
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, "+")
    .replace(/_/g, "/");

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
