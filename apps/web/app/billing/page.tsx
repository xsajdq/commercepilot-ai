"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check } from "lucide-react";

import {
  ApiError,
  createCheckoutSession,
  createPortalSession,
  getBillingStatus,
  type BillingStatusOut,
  type PlanTier,
} from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";
import StatusBadge from "@/components/StatusBadge";

const PLAN_CARDS: {
  plan: PlanTier;
  name: string;
  price: string;
  features: string[];
}[] = [
  {
    plan: "free",
    name: "Free",
    price: "$0/mo",
    features: ["1 connected store", "$1.00 AI budget / month"],
  },
  {
    plan: "starter",
    name: "Starter",
    price: "$29/mo",
    features: ["Multiple connected stores", "$10.00 AI budget / month"],
  },
  {
    plan: "pro",
    name: "Pro",
    price: "$99/mo",
    features: ["Unlimited connected stores", "$50.00 AI budget / month"],
  },
];

function messageForCheckoutParam(checkout: string | null): string | null {
  if (checkout === "success") {
    return "Subscription updated - it may take a few seconds to reflect below.";
  }
  if (checkout === "cancelled") {
    return "Checkout was cancelled - your plan hasn't changed.";
  }
  return null;
}

export default function BillingPage() {
  return (
    <Suspense fallback={null}>
      <BillingContent />
    </Suspense>
  );
}

function BillingContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<BillingStatusOut | null>(null);
  const [busyPlan, setBusyPlan] = useState<PlanTier | null>(null);
  const [portalBusy, setPortalBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(() =>
    messageForCheckoutParam(searchParams.get("checkout")),
  );

  function refresh() {
    const token = getAccessToken();
    if (!token) return;
    getBillingStatus(token).then(setStatus).catch(() => setStatus(null));
  }

  useEffect(refresh, []);

  useEffect(() => {
    if (searchParams.get("checkout") !== "success") return;
    const timer = setTimeout(refresh, 2000);
    return () => clearTimeout(timer);
  }, [searchParams]);

  async function handleUpgrade(plan: PlanTier) {
    if (plan === "free") return;
    const token = getAccessToken();
    if (!token) return;
    setBusyPlan(plan);
    setMessage(null);
    try {
      const { checkout_url } = await createCheckoutSession(token, plan);
      // eslint-disable-next-line react-hooks/immutability -- full navigation to an external Stripe URL, not React state
      window.location.href = checkout_url;
    } catch (err) {
      setMessage(
        err instanceof ApiError && err.status === 503
          ? "Billing isn't configured on this deployment yet."
          : err instanceof ApiError
            ? err.message
            : "Failed to start checkout",
      );
      setBusyPlan(null);
    }
  }

  async function handleManageBilling() {
    const token = getAccessToken();
    if (!token) return;
    setPortalBusy(true);
    setMessage(null);
    try {
      const { portal_url } = await createPortalSession(token);
      window.location.href = portal_url;
    } catch (err) {
      setMessage(
        err instanceof ApiError && err.status === 503
          ? "Billing isn't configured on this deployment yet."
          : err instanceof ApiError
            ? err.message
            : "Failed to open the billing portal",
      );
      setPortalBusy(false);
    }
  }

  const spent = status ? Number(status.spent_this_period) : 0;
  const budget = status ? Number(status.budget) : 0;
  const pctUsed = budget > 0 ? Math.min(100, Math.round((spent / budget) * 100)) : 0;

  return (
    <AppShell>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Billing</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Your plan controls how many AI-powered agent runs you can make each month. Pricing
            math (budgets, cost estimates) is computed deterministically, never by the AI itself.
          </p>
        </div>

        {message && <p className="text-sm text-slate-600">{message}</p>}

        {status === null && (
          <p className="px-4 py-8 text-center text-sm text-slate-400">Loading…</p>
        )}

        {status && (
          <div className="card flex flex-col gap-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-500">Current plan</span>
                <span className="text-lg font-semibold capitalize text-slate-900">
                  {status.plan}
                </span>
                <StatusBadge value={status.status} />
              </div>
              {status.has_stripe_subscription && (
                <button
                  onClick={handleManageBilling}
                  disabled={portalBusy}
                  className="btn-secondary"
                >
                  {portalBusy ? "Opening…" : "Manage billing"}
                </button>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500">AI spend this period</span>
                <span className={status.is_exceeded ? "font-medium text-rose-600" : "text-slate-700"}>
                  ${status.spent_this_period} of ${status.budget}
                </span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full transition-all ${
                    status.is_exceeded ? "bg-rose-500" : "bg-brand-500"
                  }`}
                  style={{ width: `${pctUsed}%` }}
                />
              </div>
              {status.is_exceeded && (
                <p className="mt-2 text-sm text-rose-600">
                  This period&apos;s AI budget is exhausted - new AI-powered runs are blocked
                  until next month or an upgrade.
                </p>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {PLAN_CARDS.map((card) => {
            const isCurrent = status?.plan === card.plan;
            return (
              <div key={card.plan} className="card flex flex-col gap-4 p-5">
                <div>
                  <p className="text-sm font-medium text-slate-500">{card.name}</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">{card.price}</p>
                </div>
                <ul className="flex flex-1 flex-col gap-2">
                  {card.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm text-slate-600">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                      {feature}
                    </li>
                  ))}
                </ul>
                {card.plan === "free" ? (
                  <button disabled className="btn-secondary">
                    {isCurrent ? "Current plan" : "Free plan"}
                  </button>
                ) : isCurrent ? (
                  <button disabled className="btn-secondary-active">
                    Current plan
                  </button>
                ) : (
                  <button
                    onClick={() => handleUpgrade(card.plan)}
                    disabled={busyPlan !== null}
                    className="btn-primary"
                  >
                    {busyPlan === card.plan ? "Redirecting…" : `Upgrade to ${card.name}`}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
