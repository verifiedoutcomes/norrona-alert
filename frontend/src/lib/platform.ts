declare global {
  interface Window {
    Capacitor?: {
      isNativePlatform: () => boolean;
      getPlatform: () => string;
    };
  }
}

export function isNative(): boolean {
  if (typeof window === "undefined") return false;
  return !!window.Capacitor?.isNativePlatform();
}

export function isWeb(): boolean {
  return !isNative();
}

export function getPlatform(): "web" | "ios" | "android" {
  if (typeof window === "undefined") return "web";
  if (!window.Capacitor?.isNativePlatform()) return "web";
  const platform = window.Capacitor.getPlatform();
  if (platform === "ios") return "ios";
  if (platform === "android") return "android";
  return "web";
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    ("standalone" in window.navigator &&
      (window.navigator as Record<string, unknown>).standalone === true)
  );
}

export function canInstallPWA(): boolean {
  return isWeb() && !isStandalone() && !isNative();
}
