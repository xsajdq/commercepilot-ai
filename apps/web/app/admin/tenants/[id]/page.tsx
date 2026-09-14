"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";

import { getAdminTenantDetail, type AdminTenantDetail } from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";
import StatusBadge from "@/components/StatusBadge";

export default function AdminTenantDetailPage() {
  const params = useParams<{ id: string }>();
  const [tenant, setTenant] = useState<AdminTenantDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    getAdminTenantDetail(token, params.id)
      .then(setTenant)
      .catch(() => setError("Failed to load this tenant."));
  }, [params.id]);

  return (
    <AppShell>
      <div className="flex flex-col gap-6">
        <Link
          href="/admin/tenants"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" /> All tenants
        </Link>

        {error && <p className="text-sm text-rose-600">{error}</p>}
        {!tenant && !error && <p className="text-sm text-slate-400">Loading…</p>}

        {tenant && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
                {tenant.name}
              </h1>
              <StatusBadge value={tenant.plan} />
              <StatusBadge value={tenant.subscription_status} />
            </div>
            <p className="text-sm text-slate-400">
              {tenant.slug} · created {new Date(tenant.created_at).toLocaleDateString()}
            </p>

            <section className="card p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-900">Members</h2>
              <ul className="flex flex-col gap-2">
                {tenant.members.map((m) => (
                  <li key={m.user_id} className="flex items-center justify-between text-sm">
                    <span className="text-slate-700">
                      {m.full_name} <span className="text-slate-400">({m.email})</span>
                    </span>
                    <span className="text-xs uppercase tracking-wide text-slate-400">
                      {m.role}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="card p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-900">Connections</h2>
              {tenant.connections.length === 0 && (
                <p className="text-sm text-slate-500">No connections.</p>
              )}
              <ul className="flex flex-col gap-2">
                {tenant.connections.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="text-slate-700">
                      {c.name} <span className="text-slate-400">({c.platform})</span>
                    </span>
                    <div className="flex items-center gap-2">
                      <StatusBadge value={c.status} />
                      {c.last_error && (
                        <span className="max-w-xs truncate text-xs text-rose-600" title={c.last_error}>
                          {c.last_error}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            <section className="card p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-900">Recent AI jobs</h2>
              {tenant.recent_ai_jobs.length === 0 && (
                <p className="text-sm text-slate-500">No AI jobs yet.</p>
              )}
              <ul className="flex flex-col gap-2">
                {tenant.recent_ai_jobs.map((job) => (
                  <li key={job.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="text-slate-700">{job.agent_type}</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge value={job.status} />
                      {job.error_message && (
                        <span
                          className="max-w-xs truncate text-xs text-rose-600"
                          title={job.error_message}
                        >
                          {job.error_message}
                        </span>
                      )}
                      <span className="text-xs text-slate-400">
                        {new Date(job.created_at).toLocaleString()}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            <section className="card p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-900">
                Recent recommendations
              </h2>
              {tenant.recent_recommendations.length === 0 && (
                <p className="text-sm text-slate-500">No recommendations yet.</p>
              )}
              <ul className="flex flex-col gap-2">
                {tenant.recent_recommendations.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="text-slate-700">{r.title}</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge value={r.risk_level} />
                      <StatusBadge value={r.status} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
