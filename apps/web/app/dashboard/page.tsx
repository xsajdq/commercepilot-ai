"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Plug,
  Package,
  AlertTriangle,
  ListChecks,
  Wallet,
  Percent,
  Sparkles,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";

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
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900">Overview</h1>
          <p className="mt-1 text-sm text-gray-500">
            A snapshot of your catalog, pricing, and what still needs your approval.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard
            href="/connections"
            icon={Plug}
            label="Connections"
            value={connectionCount}
            hint="Stores syncing products"
          />
          <StatCard
            href="/products"
            icon={Package}
            label="Products"
            value={metrics?.total_products ?? null}
            hint="Across all connections"
          />
          <StatCard
            href="/catalog"
            icon={AlertTriangle}
            label="Catalog issues"
            value={metrics ? issueCount : null}
            hint="From the last audit"
            highlight={Boolean(issueCount)}
          />
          <StatCard
            href="/recommendations"
            icon={ListChecks}
            label="Pending approvals"
            value={metrics ? pendingCount : null}
            hint="Waiting on you"
            highlight={Boolean(pendingCount)}
          />
          <StatCard
            href="/products"
            icon={Wallet}
            label="Catalog value"
            value={metrics ? `${metrics.total_catalog_value} PLN` : null}
            hint="Price × stock, where known"
          />
          <StatCard
            href="/products"
            icon={Percent}
            label="Avg. margin"
            value={
              metrics?.average_margin_rate != null
                ? `${(Number(metrics.average_margin_rate) * 100).toFixed(0)}%`
                : "—"
            }
            hint="Across priced, costed offers"
          />
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-100 text-violet-600">
                <Sparkles className="h-4 w-4" />
              </div>
              <h2 className="text-base font-semibold text-gray-900">AI insight</h2>
            </div>
            <button
              onClick={handleGenerateInsight}
              disabled={generating}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
            >
              {generating ? "Queuing…" : "Generate insight"}
            </button>
          </div>
          {insightMessage && <p className="mt-3 text-sm text-gray-600">{insightMessage}</p>}
          {latestNarrative?.narrative ? (
            <div className="mt-4">
              <p className="text-sm leading-relaxed text-gray-800">
                {latestNarrative.narrative.summary}
              </p>
              {latestNarrative.narrative.highlights.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {latestNarrative.narrative.highlights.map((h, i) => (
                    <li key={i} className="flex gap-2 text-sm text-gray-600">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
                      {h}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-gray-500">
              No insight generated yet - click &quot;Generate insight&quot; for a short AI summary
              of the metrics above.
            </p>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900">Getting started</h2>
          <ol className="mt-4 space-y-3">
            <GettingStartedStep n={1}>
              Add a <Link href="/connections" className="font-medium text-gray-900 underline underline-offset-2">connection</Link> (a store or marketplace account).
            </GettingStartedStep>
            <GettingStartedStep n={2}>
              Add or sync{" "}
              <Link href="/products" className="font-medium text-gray-900 underline underline-offset-2">products</Link>{" "}
              - give one a cost to enable pricing recommendations.
            </GettingStartedStep>
            <GettingStartedStep n={3}>
              Click &quot;Generate pricing&quot; or &quot;Generate content&quot; on a product to
              queue an agent - it proposes a change, never applies it directly.
            </GettingStartedStep>
            <GettingStartedStep n={4}>
              Run a{" "}
              <Link href="/catalog" className="font-medium text-gray-900 underline underline-offset-2">
                catalog audit
              </Link>{" "}
              to find structural problems (missing price/stock, out of stock, priced below cost).
            </GettingStartedStep>
            <GettingStartedStep n={5}>
              Review and approve or reject it on the{" "}
              <Link href="/recommendations" className="font-medium text-gray-900 underline underline-offset-2">
                Recommendations
              </Link>{" "}
              page. Approving runs the change immediately and logs an audit event.
            </GettingStartedStep>
          </ol>
        </div>
      </div>
    </AppShell>
  );
}

function StatCard({
  href,
  icon: Icon,
  label,
  value,
  hint,
  highlight,
}: {
  href: string;
  icon: LucideIcon;
  label: string;
  value: number | string | null;
  hint: string;
  highlight?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`group rounded-xl border p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
        highlight ? "border-amber-300 bg-amber-50" : "border-gray-200 bg-white"
      }`}
    >
      <div className="flex items-start justify-between">
        <div
          className={`flex h-9 w-9 items-center justify-center rounded-lg ${
            highlight ? "bg-amber-100 text-amber-700" : "bg-gray-100 text-gray-600"
          }`}
        >
          <Icon className="h-4 w-4" />
        </div>
        <ArrowRight className="h-4 w-4 text-gray-300 opacity-0 transition group-hover:opacity-100" />
      </div>
      <p className="mt-3 text-sm font-medium text-gray-500">{label}</p>
      <p className="mt-0.5 text-3xl font-semibold tracking-tight text-gray-900">
        {value === null ? "—" : value}
      </p>
      <p className="mt-1 text-xs text-gray-500">{hint}</p>
    </Link>
  );
}

function GettingStartedStep({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gray-900 text-[11px] font-semibold text-white">
        {n}
      </span>
      <span className="text-sm text-gray-600">{children}</span>
    </li>
  );
}
