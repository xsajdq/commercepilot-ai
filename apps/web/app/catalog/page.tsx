"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  listCatalogAudits,
  triggerCatalogAudit,
  type CatalogAuditOut,
} from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";
import StatusBadge from "@/components/StatusBadge";

export default function CatalogPage() {
  const [audits, setAudits] = useState<CatalogAuditOut[] | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function refresh() {
    const token = getAccessToken();
    if (!token) return;
    listCatalogAudits(token).then(setAudits).catch(() => setAudits([]));
  }

  useEffect(refresh, []);

  async function handleRunAudit() {
    const token = getAccessToken();
    if (!token) return;
    setTriggering(true);
    setMessage(null);
    try {
      const result = await triggerCatalogAudit(token);
      setMessage(
        `Audit queued (task ${result.task_id.slice(0, 8)}…) - refresh in a moment to see the result.`,
      );
      setTimeout(refresh, 2000);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Failed to queue the audit");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <AppShell>
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              Catalog health
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              Scans every product for structural problems (missing price/stock/description/EAN,
              out-of-stock, priced below cost, an active product listed nowhere). Most issues are
              informational - only an orphaned active product gets an actual archive
              recommendation, in the Recommendations queue.
            </p>
          </div>
          <button onClick={handleRunAudit} disabled={triggering} className="btn-primary shrink-0">
            {triggering ? "Queuing…" : "Run audit"}
          </button>
        </div>

        {message && <p className="text-sm text-slate-600">{message}</p>}

        <div className="flex flex-col gap-4">
          {audits?.length === 0 && (
            <p className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">
              No audits yet - click &quot;Run audit&quot; to scan your catalog.
            </p>
          )}
          {audits?.map((audit) => (
            <div key={audit.id} className="card p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge value={audit.status} />
                  <span className="text-sm text-slate-600">
                    {audit.products_scanned ?? "?"} products scanned ·{" "}
                    {audit.issues.length} issue{audit.issues.length === 1 ? "" : "s"} found
                    {audit.recommendations_proposed
                      ? ` · ${audit.recommendations_proposed} recommendation${
                          audit.recommendations_proposed === 1 ? "" : "s"
                        } proposed`
                      : ""}
                  </span>
                </div>
                <span className="text-xs text-slate-400">
                  {new Date(audit.created_at).toLocaleString()}
                </span>
              </div>
              {audit.error_message && (
                <p className="mt-2 text-sm text-rose-600">{audit.error_message}</p>
              )}
              {audit.issues.length > 0 && (
                <ul className="mt-3 flex flex-col gap-1.5 border-t border-slate-100 pt-3">
                  {audit.issues.map((issue, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
                      <StatusBadge value={issue.severity} />
                      <span className="text-slate-700">{issue.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {audits === null && (
            <p className="px-4 py-8 text-center text-sm text-slate-400">Loading…</p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
