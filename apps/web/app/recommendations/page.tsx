"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  approveRecommendation,
  listRecommendations,
  rejectRecommendation,
  type RecommendationOut,
  type RecommendationStatus,
} from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";
import StatusBadge from "@/components/StatusBadge";

// No "approved" tab: cp_policies.approve() moves a recommendation
// straight from pending_approval to executing, then success/failed - it
// never stays at the "approved" status value, so a filter for it would
// always be empty.
const FILTERS: { value: RecommendationStatus | "all"; label: string }[] = [
  { value: "pending_approval", label: "Pending approval" },
  { value: "all", label: "All" },
  { value: "success", label: "Success" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
];

export default function RecommendationsPage() {
  const [filter, setFilter] = useState<RecommendationStatus | "all">("pending_approval");
  const [recommendations, setRecommendations] = useState<RecommendationOut[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  function refresh() {
    const token = getAccessToken();
    if (!token) return;
    setRecommendations(null);
    listRecommendations(token, filter === "all" ? undefined : filter)
      .then(setRecommendations)
      .catch(() => setRecommendations([]));
  }

  useEffect(refresh, [filter]);

  async function handleDecision(id: string, decision: "approve" | "reject") {
    const token = getAccessToken();
    if (!token) return;
    setBusyId(id);
    setErrors((prev) => ({ ...prev, [id]: "" }));
    try {
      if (decision === "approve") {
        await approveRecommendation(token, id);
      } else {
        await rejectRecommendation(token, id);
      }
      refresh();
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        [id]: err instanceof ApiError ? err.message : "Something went wrong",
      }));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <AppShell>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Recommendations</h1>
          <p className="mt-1 text-sm text-gray-600">
            Everything an agent has proposed. Approving runs the underlying change immediately
            and writes an audit log; rejecting does nothing.
          </p>
        </div>

        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                filter === f.value
                  ? "bg-gray-900 text-white"
                  : "border border-gray-300 text-gray-700 hover:bg-gray-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3">
          {recommendations?.length === 0 && (
            <p className="rounded-lg border border-dashed border-gray-300 bg-white px-4 py-8 text-center text-sm text-gray-500">
              Nothing here. Trigger a pricing or content recommendation from the Products page.
            </p>
          )}
          {recommendations?.map((r) => (
            <div key={r.id} className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-gray-900">{r.title}</h3>
                    <StatusBadge value={r.status} />
                    <StatusBadge value={r.risk_level} />
                  </div>
                  <p className="text-xs text-gray-500">
                    {r.type} · {r.entity_type} · {new Date(r.created_at).toLocaleString()}
                    {r.confidence && ` · confidence ${Number(r.confidence) * 100}%`}
                  </p>
                  {r.reason && <p className="max-w-2xl text-sm text-gray-700">{r.reason}</p>}
                  {errors[r.id] && <p className="text-sm text-red-600">{errors[r.id]}</p>}
                </div>
                {r.status === "pending_approval" && (
                  <div className="flex gap-2">
                    <button
                      disabled={busyId === r.id}
                      onClick={() => handleDecision(r.id, "approve")}
                      className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      disabled={busyId === r.id}
                      onClick={() => handleDecision(r.id, "reject")}
                      className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
          {recommendations === null && (
            <p className="px-4 py-8 text-center text-sm text-gray-400">Loading…</p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
