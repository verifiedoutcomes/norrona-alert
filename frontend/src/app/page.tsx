"use client";

import { useEffect, useState } from "react";
import { api, type UserRead } from "@/lib/api";
import { LoginPage } from "@/components/login-page";
import { Dashboard } from "@/components/dashboard";

export default function Home() {
  const [user, setUser] = useState<UserRead | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.preferences
      .get()
      .then((prefs) => {
        // If we can fetch preferences, we're authenticated
        setUser({ preferences: prefs } as UserRead);
      })
      .catch(() => {
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-500 border-t-transparent" />
      </div>
    );
  }

  if (!user) {
    return <LoginPage onLogin={setUser} />;
  }

  return <Dashboard user={user} onLogout={() => setUser(null)} />;
}
