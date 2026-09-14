import Link from "next/link";
import { Navigation } from "lucide-react";

export default function Home() {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-ink-950 px-6">
      <div className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-brand-700/30 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-20 h-96 w-96 rounded-full bg-brand-500/20 blur-3xl" />

      <div className="relative flex w-full max-w-md flex-col gap-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-glow">
            <Navigation className="h-5 w-5 -rotate-45 text-white" />
          </div>
          <span className="text-lg font-semibold tracking-tight text-white">CommercePilot</span>
        </div>

        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">
            Autopilot for your store
          </h1>
          <p className="mt-3 text-slate-400">
            AI e-commerce manager — monitors, analyzes, and proposes actions across your stores
            and marketplaces, with humans approving anything risky.
          </p>
        </div>

        <div className="flex gap-3">
          <Link href="/register" className="btn-primary">
            Create an account
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-white/10"
          >
            Log in
          </Link>
        </div>

        <p className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-400">
          Registration, login, tenant-scoped sessions, and role-based access are live, alongside
          six working agents, real WooCommerce/Allegro connectors, and a daily scheduler — see{" "}
          <code className="rounded bg-white/10 px-1 py-0.5 text-slate-300">
            docs/architecture/roadmap.md
          </code>
          .
        </p>
      </div>
    </main>
  );
}
