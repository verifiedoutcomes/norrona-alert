const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Locale = "en-GB" | "nb-NO";

export type ChangeType = "new" | "restock" | "price_drop";

export type Platform = "web" | "ios";

export interface ProductSnapshot {
  name: string;
  url: string;
  price: number;
  original_price: number;
  discount_pct: number;
  available_sizes: string[];
  category: string;
  image_url: string;
  locale: Locale;
  scraped_at: string;
}

export interface ProductChange {
  product: ProductSnapshot;
  change_type: ChangeType;
  previous_state: ProductSnapshot | null;
  new_state: ProductSnapshot;
}

export interface UserPreferences {
  region: Locale;
  size_map: Record<string, string>;
  watchlist_terms: string[];
  max_price: number | null;
}

export interface UserRead {
  id: string;
  email: string;
  preferences: UserPreferences;
  created_at: string;
}

export interface AlertSchema {
  user_id: string;
  product_change: ProductChange;
  matched_rule: string;
}

export interface DeviceRegistration {
  id: string;
  user_id: string;
  device_token: string;
  platform: Platform;
  created_at: string;
}

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_URL}${path}`;

  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "Unknown error");
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  auth: {
    sendMagicLink(email: string): Promise<void> {
      return request("/auth/magic-link", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
    },

    verify(token: string): Promise<UserRead> {
      return request("/auth/verify", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
    },
  },

  preferences: {
    get(): Promise<UserPreferences> {
      return request("/api/preferences");
    },

    update(preferences: Partial<UserPreferences>): Promise<UserPreferences> {
      return request("/api/preferences", {
        method: "PUT",
        body: JSON.stringify(preferences),
      });
    },
  },

  outlet: {
    list(locale: Locale = "en-GB"): Promise<ProductSnapshot[]> {
      return request(`/api/outlet?locale=${locale}`);
    },
  },

  devices: {
    register(
      device_token: string,
      platform: Platform,
    ): Promise<DeviceRegistration> {
      return request("/api/devices", {
        method: "POST",
        body: JSON.stringify({ device_token, platform }),
      });
    },
  },

  health: {
    check(): Promise<{ status: string }> {
      return request("/health");
    },
  },
};

export { ApiError };
