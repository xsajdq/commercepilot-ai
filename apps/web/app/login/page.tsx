"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, login, type MembershipOut } from "@/lib/api";
import { saveSession } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [tenantChoices, setTenantChoices] = useState<MembershipOut[] | null>(null);

  async function attemptLogin(tenantId?: string) {
    setError(null);
    setSubmitting(true);
    try {
      const result = await login({ email, password, tenant_id: tenantId });
      if (result.requires_tenant_selection) {
        setTenantChoices(result.memberships);
        return;
      }
      if (result.token) {
        saveSession(result.token);
        router.push("/dashboard");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  if (tenantChoices) {
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Choose a workspace</h1>
          <p className="mt-1 text-sm text-gray-600">
            Your account belongs to more than one store.
          </p>
        </div>
        <div className="flex flex-col gap-2">
          {tenantChoices.map((m) => (
            <button
              key={m.tenant.id}
              disabled={submitting}
              onClick={() => attemptLogin(m.tenant.id)}
              className="flex items-center justify-between rounded-md border border-gray-300 px-4 py-3 text-left text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              <span className="font-medium text-gray-900">{m.tenant.name}</span>
              <span className="text-gray-500">{m.role}</span>
            </button>
          ))}
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          attemptLogin();
        }}
        className="flex flex-col gap-4"
      >
        <label className="flex flex-col gap-1 text-sm font-medium text-gray-700">
          Email
          <input
            required
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
            autoComplete="email"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-gray-700">
          Password
          <input
            required
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input"
            autoComplete="current-password"
          />
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button type="submit" disabled={submitting} className="btn-primary">
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>

      <p className="text-sm text-gray-600">
        No account yet?{" "}
        <Link href="/register" className="font-medium text-gray-900 underline">
          Create one
        </Link>
      </p>
    </main>
  );
}
