"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listAdminTenants, type AdminTenantSummary } from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";
import StatusBadge from "@/components/StatusBadge";

export default function AdminTenantsPage() {
  const [tenants, setTenants] = useState<AdminTenantSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    listAdminTenants(token)
      .then(setTenants)
      .catch(() => setError("Failed to load tenants - you may not have platform admin access."));
  }, []);

  return (
    <AppShell>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Tenants
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Read-only cross-tenant support view for the beta - connection health, plan, and the
            latest AI job per workspace. No mutation happens here; every change still goes
            through the tenant&apos;s own session.
          </p>
        </div>

        {error && <p className="text-sm text-rose-600">{error}</p>}

        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Tenant</th>
                <th className="px-4 py-3 font-medium">Plan</th>
                <th className="px-4 py-3 font-medium">Members</th>
                <th className="px-4 py-3 font-medium">Connections</th>
                <th className="px-4 py-3 font-medium">Latest AI job</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {tenants?.map((tenant) => (
                <tr key={tenant.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/admin/tenants/${tenant.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {tenant.name}
                    </Link>
                    <p className="text-xs text-slate-400">{tenant.slug}</p>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge value={tenant.plan} />{" "}
                    <StatusBadge value={tenant.subscription_status} />
                  </td>
                  <td className="px-4 py-3 text-slate-600">{tenant.member_count}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {tenant.connection_count}
                    {tenant.connection_error_count > 0 && (
                      <span className="ml-2 text-rose-600">
                        ({tenant.connection_error_count} in error)
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {tenant.latest_ai_job_status ? (
                      <StatusBadge value={tenant.latest_ai_job_status} />
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {tenants?.length === 0 && (
            <p className="px-4 py-8 text-center text-sm text-slate-500">No tenants yet.</p>
          )}
          {tenants === null && !error && (
            <p className="px-4 py-8 text-center text-sm text-slate-400">Loading…</p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
