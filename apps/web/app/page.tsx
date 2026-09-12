import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-6">
      <h1 className="text-3xl font-semibold tracking-tight">CommercePilot</h1>
      <p className="text-gray-600">
        AI e-commerce manager — monitors, analyzes, and proposes actions across your
        stores and marketplaces, with humans approving anything risky.
      </p>
      <div className="flex gap-3">
        <Link href="/register" className="btn-primary">
          Create an account
        </Link>
        <Link
          href="/login"
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Log in
        </Link>
      </div>
      <p className="rounded-md border border-dashed border-gray-300 bg-white px-4 py-3 text-sm text-gray-500">
        Phase 1: registration, login, tenant-scoped sessions, and role-based
        access are live. Products, connectors, and the real recommendations
        dashboard land in later phases — see{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5">docs/architecture/roadmap.md</code>.
      </p>
    </main>
  );
}
