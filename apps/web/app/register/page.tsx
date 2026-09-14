"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Navigation } from "lucide-react";

import { ApiError, registerAccount } from "@/lib/api";
import { saveSession } from "@/lib/session";
import Field from "@/components/Field";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const token = await registerAccount({
        email,
        password,
        full_name: fullName,
        tenant_name: tenantName,
      });
      saveSession(token);
      router.push("/dashboard");
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
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            Create your account
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            This creates your store&apos;s workspace and makes you its owner.
          </p>

          <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
            <Field label="Your name">
              <input
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="input"
                autoComplete="name"
              />
            </Field>
            <Field label="Store / company name">
              <input
                required
                value={tenantName}
                onChange={(e) => setTenantName(e.target.value)}
                className="input"
                placeholder="e.g. Alice's Shop"
              />
            </Field>
            <Field label="Email">
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                autoComplete="email"
              />
            </Field>
            <Field label="Password">
              <input
                required
                minLength={8}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                autoComplete="new-password"
              />
            </Field>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <button type="submit" disabled={submitting} className="btn-primary mt-1">
              {submitting ? "Creating account…" : "Create account"}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-slate-400">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-white underline underline-offset-2">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
