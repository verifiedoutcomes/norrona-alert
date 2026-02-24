"use client";

import { useEffect, useState } from "react";
import { api, type Locale, type ProductSnapshot, type UserRead } from "@/lib/api";
import { ProductCard } from "@/components/product-card";
import { PreferencesPanel } from "@/components/preferences-panel";
import { subscribeToPushNotifications } from "@/lib/notifications";

interface DashboardProps {
  user: UserRead;
  onLogout: () => void;
}

export function Dashboard({ user, onLogout }: DashboardProps) {
  const [products, setProducts] = useState<ProductSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPreferences, setShowPreferences] = useState(false);
  const [locale, setLocale] = useState<Locale>(
    user.preferences?.region || "en-GB",
  );
  const [pushEnabled, setPushEnabled] = useState(false);

  useEffect(() => {
    loadProducts();
  }, [locale]);

  async function loadProducts() {
    setLoading(true);
    try {
      const data = await api.outlet.list(locale);
      setProducts(data);
    } catch {
      // Products may not be available yet
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleEnablePush() {
    const success = await subscribeToPushNotifications();
    setPushEnabled(success);
  }

  const categories = [
    ...new Set(products.map((p) => p.category)),
  ].sort();

  return (
    <div className="min-h-full bg-background">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <h1 className="text-lg font-bold text-primary-700">
            Norr&oslash;na Alert
          </h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowPreferences(true)}
              className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Settings"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
            </button>
            <button
              onClick={onLogout}
              className="rounded-lg px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        {/* Region toggle */}
        <div className="mb-6 flex items-center gap-3">
          <div className="inline-flex rounded-lg border border-border bg-muted p-1">
            <button
              onClick={() => setLocale("en-GB")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                locale === "en-GB"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              UK
            </button>
            <button
              onClick={() => setLocale("nb-NO")}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                locale === "nb-NO"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Norway
            </button>
          </div>

          {!pushEnabled && (
            <button
              onClick={handleEnablePush}
              className="ml-auto rounded-lg border border-primary-500 px-3 py-1.5 text-sm font-medium text-primary-600 hover:bg-primary-50"
            >
              Enable notifications
            </button>
          )}
        </div>

        {/* Product grid */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-500 border-t-transparent" />
          </div>
        ) : products.length === 0 ? (
          <div className="py-20 text-center">
            <p className="text-muted-foreground">
              No outlet products found yet. Check back after the next scrape.
            </p>
          </div>
        ) : (
          <>
            <p className="mb-4 text-sm text-muted-foreground">
              {products.length} product{products.length !== 1 && "s"} on outlet
            </p>
            {categories.map((category) => {
              const categoryProducts = products.filter(
                (p) => p.category === category,
              );
              return (
                <section key={category} className="mb-8">
                  <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    {category} ({categoryProducts.length})
                  </h2>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                    {categoryProducts.map((product) => (
                      <ProductCard
                        key={product.url}
                        product={product}
                        locale={locale}
                      />
                    ))}
                  </div>
                </section>
              );
            })}
          </>
        )}
      </main>

      {/* Preferences panel */}
      {showPreferences && (
        <PreferencesPanel
          initialPreferences={user.preferences}
          onClose={() => setShowPreferences(false)}
          onSave={(prefs) => {
            if (prefs.region !== locale) {
              setLocale(prefs.region);
            }
          }}
        />
      )}
    </div>
  );
}
