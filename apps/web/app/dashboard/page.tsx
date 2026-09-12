"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchMe, type MeResponse } from "@/lib/api";
import { clearSession, getAccessToken } from "@/lib/session";

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    fetchMe(token)
      .then(setMe)
      .catch(() => {
        clearSession();
        router.replace("/login");
      })
      .finally(() => setLoading(false));
  }, [router]);

  function handleLogout() {
    clearSession();
    router.push("/login");
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-gray-500">Loading…</p>
      </main>
    );
  }

  if (!me) return null;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{me.tenant.name}</h1>
          <p className="text-sm text-gray-600">
            {me.user.full_name} ({me.user.email}) · {me.role}
          </p>
        </div>
        <button
          onClick={handleLogout}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Log out
        </button>
      </div>

      <div className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-3 text-sm text-gray-500">
        This is the Phase 1 placeholder dashboard - it only proves that
        registration, login, and authenticated requests work end to end.
        The real recommendations-first dashboard from the product spec lands
        in Phase 16, once products, connectors, and agents exist to feed it.
      </div>
    </main>
  );
}
