"use client";

import { useState, type FormEvent } from "react";
import { api, type Locale, type UserPreferences } from "@/lib/api";

const CATEGORIES = [
  "Jackets",
  "Pants",
  "Fleece",
  "Base Layer",
  "Vests",
  "Shirts",
  "Shorts",
  "Accessories",
  "Bags",
  "Footwear",
];

const SIZES = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL"];

interface PreferencesPanelProps {
  initialPreferences: UserPreferences;
  onClose: () => void;
  onSave: (prefs: UserPreferences) => void;
}

export function PreferencesPanel({
  initialPreferences,
  onClose,
  onSave,
}: PreferencesPanelProps) {
  const [region, setRegion] = useState<Locale>(
    initialPreferences.region || "en-GB",
  );
  const [sizeMap, setSizeMap] = useState<Record<string, string>>(
    initialPreferences.size_map || {},
  );
  const [watchlist, setWatchlist] = useState(
    (initialPreferences.watchlist_terms || []).join(", "),
  );
  const [maxPrice, setMaxPrice] = useState(
    initialPreferences.max_price?.toString() || "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function handleSizeChange(category: string, size: string) {
    setSizeMap((prev) => {
      if (prev[category] === size) {
        const next = { ...prev };
        delete next[category];
        return next;
      }
      return { ...prev, [category]: size };
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");

    const prefs: UserPreferences = {
      region,
      size_map: sizeMap,
      watchlist_terms: watchlist
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      max_price: maxPrice ? parseFloat(maxPrice) : null,
    };

    try {
      const saved = await api.preferences.update(prefs);
      onSave(saved);
      onClose();
    } catch {
      setError("Failed to save preferences. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-background p-6 shadow-xl sm:rounded-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Alert preferences</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted"
            aria-label="Close"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 space-y-6">
          {/* Region */}
          <div>
            <label className="block text-sm font-medium">Region</label>
            <div className="mt-2 inline-flex rounded-lg border border-border bg-muted p-1">
              <button
                type="button"
                onClick={() => setRegion("en-GB")}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  region === "en-GB"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground"
                }`}
              >
                UK
              </button>
              <button
                type="button"
                onClick={() => setRegion("nb-NO")}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  region === "nb-NO"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground"
                }`}
              >
                Norway
              </button>
            </div>
          </div>

          {/* Size preferences */}
          <div>
            <label className="block text-sm font-medium">
              Size by category
            </label>
            <p className="mt-1 text-xs text-muted-foreground">
              Select your preferred size for each category you care about.
            </p>
            <div className="mt-3 space-y-3">
              {CATEGORIES.map((cat) => (
                <div key={cat}>
                  <span className="text-sm text-foreground">{cat}</span>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {SIZES.map((size) => (
                      <button
                        key={size}
                        type="button"
                        onClick={() => handleSizeChange(cat, size)}
                        className={`rounded-md border px-2 py-1 text-xs font-medium transition-colors ${
                          sizeMap[cat] === size
                            ? "border-primary-500 bg-primary-500 text-white"
                            : "border-border text-muted-foreground hover:border-primary-300 hover:text-foreground"
                        }`}
                      >
                        {size}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Watchlist */}
          <div>
            <label htmlFor="watchlist" className="block text-sm font-medium">
              Watchlist terms
            </label>
            <p className="mt-1 text-xs text-muted-foreground">
              Comma-separated product names or keywords to watch for.
            </p>
            <input
              id="watchlist"
              type="text"
              value={watchlist}
              onChange={(e) => setWatchlist(e.target.value)}
              placeholder="falketind, lofoten, trollveggen"
              className="mt-1.5 block w-full rounded-lg border border-border bg-background px-3.5 py-2.5 text-sm placeholder:text-muted-foreground focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
            />
          </div>

          {/* Max price */}
          <div>
            <label htmlFor="max-price" className="block text-sm font-medium">
              Max price
            </label>
            <p className="mt-1 text-xs text-muted-foreground">
              Only alert for products at or below this price. Leave blank for no
              limit.
            </p>
            <input
              id="max-price"
              type="number"
              min="0"
              step="1"
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
              placeholder="e.g. 2000"
              className="mt-1.5 block w-full rounded-lg border border-border bg-background px-3.5 py-2.5 text-sm placeholder:text-muted-foreground focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex flex-1 items-center justify-center rounded-lg bg-primary-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
            >
              {saving ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                "Save preferences"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
