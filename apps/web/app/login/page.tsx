"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Navigation } from "lucide-react";

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

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-ink-950 px-6 py-12">
      <div className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-brand-700/30 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-20 h-96 w-96 rounded-full bg-brand-500/20 blur-3xl" />

      <div className="relative flex w-full max-w-sm flex-col gap-6">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-glow">
            <Navigation className="h-4 w-4 -rotate-45 text-white" />
          </div>
          <span className="text-base font-semibold tracking-tight text-white">CommercePilot</span>
        </Link>

        <div className="card p-6">
          {tenantChoices ? (
            <div className="flex flex-col gap-5">
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-slate-900">
                  Choose a workspace
                </h1>
                <p className="mt-1 text-sm text-slate-500">
                  Your account belongs to more than one store.
                </p>
              </div>
              <div className="flex flex-col gap-2">
                {tenantChoices.map((m) => (
                  <button
                    key={m.tenant.id}
                    disabled={submitting}
                    onClick={() => attemptLogin(m.tenant.id)}
                    className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-left text-sm transition hover:border-brand-300 hover:bg-brand-50 disabled:opacity-50"
                  >
                    <span className="font-medium text-slate-900">{m.tenant.name}</span>
                    <span className="text-slate-500">{m.role}</span>
                  </button>
                ))}
              </div>
              {error && <p className="text-sm text-rose-600">{error}</p>}
            </div>
          ) : (
            <div className="flex flex-col gap-5">
              <h1 className="text-xl font-semibold tracking-tight text-slate-900">Log in</h1>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  attemptLogin();
                }}
                className="flex flex-col gap-4"
              >
                <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700">
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
                <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700">
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

                {error && <p className="text-sm text-rose-600">{error}</p>}

                <button type="submit" disabled={submitting} className="btn-primary mt-1">
                  {submitting ? "Logging in…" : "Log in"}
                </button>
              </form>
            </div>
          )}
        </div>

        <p className="text-center text-sm text-slate-400">
          No account yet?{" "}
          <Link href="/register" className="font-medium text-white underline underline-offset-2">
            Create one
          </Link>
        </p>
      </div>
    </main>
  );
}
