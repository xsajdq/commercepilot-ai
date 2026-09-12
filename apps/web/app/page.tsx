export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6">
      <h1 className="text-3xl font-semibold tracking-tight">CommercePilot</h1>
      <p className="text-gray-600">
        AI e-commerce manager — monitors, analyzes, and proposes actions across your
        stores and marketplaces, with humans approving anything risky.
      </p>
      <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-3 text-sm text-gray-500">
        Phase 0 bootstrap: this shell confirms the frontend container builds and boots
        behind Traefik. Auth, tenants, and the real dashboard land in later phases —
        see <code className="rounded bg-gray-100 px-1 py-0.5">docs/architecture/roadmap.md</code>.
      </p>
    </main>
  );
}
