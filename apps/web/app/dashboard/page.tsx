"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  getDashboardMetrics,
  listConnections,
  listDashboardNarratives,
  triggerDashboardNarrative,
  type AnalyticsReportOut,
  type DashboardMetricsOut,
} from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";

export default function DashboardPage() {
  const [connectionCount, setConnectionCount] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetricsOut | null>(null);
  const [latestNarrative, setLatestNarrative] = useState<AnalyticsReportOut | null>(null);
  const [generating, setGenerating] = useState(false);
  const [insightMessage, setInsightMessage] = useState<string | null>(null);

  function refresh() {
    const token = getAccessToken();
    if (!token) return;
    listConnections(token).then((c) => setConnectionCount(c.length));
    getDashboardMetrics(token).then(setMetrics);
    listDashboardNarratives(token).then((reports) => setLatestNarrative(reports[0] ?? null));
  }

  useEffect(refresh, []);

  async function handleGenerateInsight() {
    const token = getAccessToken();
    if (!token) return;
    setGenerating(true);
    setInsightMessage(null);
    try {
      const result = await triggerDashboardNarrative(token);
      setInsightMessage(
        `Insight queued (task ${result.task_id.slice(0, 8)}…) - refresh in a moment. Needs ANTHROPIC_API_KEY configured on the worker.`,
      );
      setTimeout(refresh, 2000);
    } catch (err) {
      setInsightMessage(err instanceof ApiError ? err.message : "Failed to queue");
    } finally {
      setGenerating(false);
    }
  }

  const pendingCount = metrics?.recommendations_by_status["pending_approval"] ?? 0;
  const issueCount = metrics?.latest_catalog_issue_count ?? 0;

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard
            href="/connections"
            label="Connections"
            value={connectionCount}
            hint="Stores syncing products"
          />
          <StatCard
            href="/products"
            label="Products"
            value={metrics?.total_products ?? null}
            hint="Across all connections"
          />
          <StatCard
            href="/catalog"
            label="Catalog issues"
            value={metrics ? issueCount : null}
            hint="From the last audit"
            highlight={Boolean(issueCount)}
          />
          <StatCard
            href="/recommendations"
            label="Pending approvals"
            value={metrics ? pendingCount : null}
            hint="Waiting on you"
            highlight={Boolean(pendingCount)}
          />
          <StatCard
            href="/products"
            label="Catalog value"
            value={metrics ? `${metrics.total_catalog_value} PLN` : null}
            hint="Price × stock, where known"
          />
          <StatCard
            href="/products"
            label="Avg. margin"
            value={
              metrics?.average_margin_rate != null
                ? `${(Number(metrics.average_margin_rate) * 100).toFixed(0)}%`
                : "—"
            }
            hint="Across priced, costed offers"
          />
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900">AI insight</h2>
            <button
              onClick={handleGenerateInsight}
              disabled={generating}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {generating ? "Queuing…" : "Generate insight"}
            </button>
          </div>
          {insightMessage && <p className="mt-2 text-sm text-gray-600">{insightMessage}</p>}
          {latestNarrative?.narrative ? (
            <div className="mt-3">
              <p className="text-sm text-gray-800">{latestNarrative.narrative.summary}</p>
              {latestNarrative.narrative.highlights.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-600">
                  {latestNarrative.narrative.highlights.map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <p className="mt-3 text-sm text-gray-500">
              No insight generated yet - click &quot;Generate insight&quot; for a short AI summary
              of the metrics above.
            </p>
          )}
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
              Run a{" "}
              <Link href="/catalog" className="font-medium text-gray-900 underline">
                catalog audit
              </Link>{" "}
              to find structural problems (missing price/stock, out of stock, priced below cost).
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
  value: number | string | null;
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
