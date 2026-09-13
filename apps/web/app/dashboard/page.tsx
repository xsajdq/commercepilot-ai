"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listConnections, listProducts, listRecommendations } from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";

export default function DashboardPage() {
  const [connectionCount, setConnectionCount] = useState<number | null>(null);
  const [productCount, setProductCount] = useState<number | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    listConnections(token).then((c) => setConnectionCount(c.length));
    listProducts(token).then((p) => setProductCount(p.length));
    listRecommendations(token, "pending_approval").then((r) => setPendingCount(r.length));
  }, []);

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            href="/connections"
            label="Connections"
            value={connectionCount}
            hint="Stores syncing products"
          />
          <StatCard
            href="/products"
            label="Products"
            value={productCount}
            hint="Across all connections"
          />
          <StatCard
            href="/recommendations"
            label="Pending approvals"
            value={pendingCount}
            hint="Waiting on you"
            highlight={Boolean(pendingCount)}
          />
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="text-base font-semibold text-gray-900">Getting started</h2>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-gray-600">
            <li>
              Add a <Link href="/connections" className="font-medium text-gray-900 underline">connection</Link> (a store or marketplace account).
            </li>
            <li>
              Add or sync{" "}
              <Link href="/products" className="font-medium text-gray-900 underline">products</Link>{" "}
              - give one a cost to enable pricing recommendations.
            </li>
            <li>
              Click &quot;Generate pricing&quot; or &quot;Generate content&quot; on a product to
              queue an agent - it proposes a change, never applies it directly.
            </li>
            <li>
              Review and approve or reject it on the{" "}
              <Link href="/recommendations" className="font-medium text-gray-900 underline">
                Recommendations
              </Link>{" "}
              page. Approving runs the change immediately and logs an audit event.
            </li>
          </ol>
        </div>
      </div>
    </AppShell>
  );
}

function StatCard({
  href,
  label,
  value,
  hint,
  highlight,
}: {
  href: string;
  label: string;
  value: number | null;
  hint: string;
  highlight?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`rounded-lg border p-5 transition hover:shadow-sm ${
        highlight ? "border-amber-300 bg-amber-50" : "border-gray-200 bg-white"
      }`}
    >
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold tracking-tight text-gray-900">
        {value === null ? "—" : value}
      </p>
      <p className="mt-1 text-xs text-gray-500">{hint}</p>
    </Link>
  );
}
