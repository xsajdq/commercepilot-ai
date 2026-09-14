"use client";

import { Fragment, useEffect, useState } from "react";

import {
  ApiError,
  createCompetitorPrice,
  createProduct,
  generateContentRecommendation,
  generateListingPublishRecommendation,
  generatePricingRecommendation,
  listCompetitorPrices,
  listConnections,
  listProducts,
  type CompetitorPriceOut,
  type ConnectionOut,
  type ProductOut,
} from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";
import Field from "@/components/Field";
import StatusBadge from "@/components/StatusBadge";

export default function ProductsPage() {
  const [products, setProducts] = useState<ProductOut[] | null>(null);
  const [connections, setConnections] = useState<ConnectionOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionMessages, setActionMessages] = useState<Record<string, string>>({});

  const [connectionId, setConnectionId] = useState("");
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [cost, setCost] = useState("");
  const [priceAmount, setPriceAmount] = useState("");
  const [stockQuantity, setStockQuantity] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [expandedProductId, setExpandedProductId] = useState<string | null>(null);
  const [competitorPrices, setCompetitorPrices] = useState<CompetitorPriceOut[]>([]);
  const [competitorName, setCompetitorName] = useState("");
  const [competitorPrice, setCompetitorPrice] = useState("");
  const [competitorUrl, setCompetitorUrl] = useState("");
  const [competitorSubmitting, setCompetitorSubmitting] = useState(false);
  const [competitorError, setCompetitorError] = useState<string | null>(null);

  function refresh() {
    const token = getAccessToken();
    if (!token) return;
    listProducts(token).then(setProducts).catch(() => setProducts([]));
    listConnections(token).then((cs) => {
      setConnections(cs);
      if (cs.length > 0 && !connectionId) setConnectionId(cs[0].id);
    });
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const token = getAccessToken();
    if (!token) return;
    setError(null);
    setSubmitting(true);
    try {
      await createProduct(token, {
        connection_id: connectionId,
        sku,
        name,
        cost: cost || undefined,
        price_amount: priceAmount,
        stock_quantity: stockQuantity ? Number(stockQuantity) : undefined,
      });
      setSku("");
      setName("");
      setCost("");
      setPriceAmount("");
      setStockQuantity("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGenerateContent(productId: string) {
    const token = getAccessToken();
    if (!token) return;
    setActionMessages((prev) => ({ ...prev, [productId]: "Queuing…" }));
    try {
      const result = await generateContentRecommendation(token, productId);
      setActionMessages((prev) => ({
        ...prev,
        [productId]: `Content recommendation queued (task ${result.task_id.slice(0, 8)}…) - see Recommendations. Needs ANTHROPIC_API_KEY configured on the worker.`,
      }));
    } catch (err) {
      setActionMessages((prev) => ({
        ...prev,
        [productId]: err instanceof ApiError ? err.message : "Failed to queue",
      }));
    }
  }

  async function handleGeneratePricing(offerId: string) {
    const token = getAccessToken();
    if (!token) return;
    setActionMessages((prev) => ({ ...prev, [offerId]: "Queuing…" }));
    try {
      const result = await generatePricingRecommendation(token, offerId);
      setActionMessages((prev) => ({
        ...prev,
        [offerId]: `Pricing recommendation queued (task ${result.task_id.slice(0, 8)}…) - see Recommendations.`,
      }));
    } catch (err) {
      setActionMessages((prev) => ({
        ...prev,
        [offerId]: err instanceof ApiError ? err.message : "Failed to queue",
      }));
    }
  }

  async function handleGenerateListingPublish(offerId: string) {
    const token = getAccessToken();
    if (!token) return;
    setActionMessages((prev) => ({ ...prev, [offerId]: "Queuing…" }));
    try {
      const result = await generateListingPublishRecommendation(token, offerId);
      setActionMessages((prev) => ({
        ...prev,
        [offerId]: `Publish check queued (task ${result.task_id.slice(0, 8)}…) - see Recommendations. Only proposes once the offer already exists as a marketplace draft (has an external_id, e.g. from a sync).`,
      }));
    } catch (err) {
      setActionMessages((prev) => ({
        ...prev,
        [offerId]: err instanceof ApiError ? err.message : "Failed to queue",
      }));
    }
  }

  async function handleToggleCompetitors(productId: string) {
    if (expandedProductId === productId) {
      setExpandedProductId(null);
      return;
    }
    const token = getAccessToken();
    if (!token) return;
    setExpandedProductId(productId);
    setCompetitorError(null);
    setCompetitorName("");
    setCompetitorPrice("");
    setCompetitorUrl("");
    try {
      setCompetitorPrices(await listCompetitorPrices(token, productId));
    } catch {
      setCompetitorPrices([]);
    }
  }

  async function handleAddCompetitorPrice(e: React.FormEvent) {
    e.preventDefault();
    const token = getAccessToken();
    if (!token || !expandedProductId) return;
    setCompetitorSubmitting(true);
    setCompetitorError(null);
    try {
      await createCompetitorPrice(token, expandedProductId, {
        competitor_name: competitorName,
        price: competitorPrice,
        url: competitorUrl || undefined,
      });
      setCompetitorName("");
      setCompetitorPrice("");
      setCompetitorUrl("");
      setCompetitorPrices(await listCompetitorPrices(token, expandedProductId));
    } catch (err) {
      setCompetitorError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setCompetitorSubmitting(false);
    }
  }

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Products</h1>
          <p className="mt-1 text-sm text-gray-600">
            Products and their offers. Trigger the pricing and product agents from here - they
            propose changes into the Recommendations queue, never mutating anything directly.
          </p>
        </div>

        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Cost</th>
                <th className="px-4 py-3">Price</th>
                <th className="px-4 py-3">Stock</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {products?.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                    No products yet - sync a connection or add one manually below.
                  </td>
                </tr>
              )}
              {products?.map((p) => {
                const offer = p.offers[0];
                const isExpanded = expandedProductId === p.id;
                return (
                  <Fragment key={p.id}>
                    <tr>
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{p.sku}</td>
                      <td className="px-4 py-3 font-medium text-gray-900">{p.name}</td>
                      <td className="px-4 py-3 text-gray-600">{p.cost ?? "—"}</td>
                      <td className="px-4 py-3 text-gray-600">
                        {offer?.price_amount ? `${offer.price_amount} ${offer.currency}` : "—"}
                      </td>
                      <td className="px-4 py-3 text-gray-600">{offer?.stock_quantity ?? "—"}</td>
                      <td className="px-4 py-3">
                        <StatusBadge value={p.status} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex flex-col items-end gap-1">
                          <div className="flex flex-wrap justify-end gap-2">
                            <button
                              onClick={() => handleGenerateContent(p.id)}
                              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                            >
                              Generate content
                            </button>
                            {offer && (
                              <button
                                onClick={() => handleGeneratePricing(offer.id)}
                                className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                              >
                                Generate pricing
                              </button>
                            )}
                            {offer && offer.status === "draft" && (
                              <button
                                onClick={() => handleGenerateListingPublish(offer.id)}
                                className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                              >
                                Publish listing
                              </button>
                            )}
                            <button
                              onClick={() => handleToggleCompetitors(p.id)}
                              className={`rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-gray-50 ${
                                isExpanded
                                  ? "border-gray-900 bg-gray-900 text-white hover:bg-gray-700"
                                  : "border-gray-300 text-gray-700"
                              }`}
                            >
                              Competitors
                            </button>
                          </div>
                          {(actionMessages[p.id] || (offer && actionMessages[offer.id])) && (
                            <p className="max-w-xs text-right text-xs text-gray-500">
                              {actionMessages[p.id] ?? actionMessages[offer!.id]}
                            </p>
                          )}
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={7} className="bg-gray-50 px-4 py-4">
                          <div className="flex flex-col gap-3 sm:flex-row sm:gap-6">
                            <div className="flex-1">
                              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                Recent competitor prices
                              </h3>
                              {competitorPrices.length === 0 ? (
                                <p className="mt-2 text-sm text-gray-500">
                                  No observations yet - add one to feed the pricing agent.
                                </p>
                              ) : (
                                <ul className="mt-2 flex flex-col gap-1 text-sm text-gray-700">
                                  {competitorPrices.map((cp) => (
                                    <li key={cp.id} className="flex flex-wrap items-center gap-2">
                                      <span className="font-medium">{cp.competitor_name}</span>
                                      <span>
                                        {cp.price} {cp.currency}
                                      </span>
                                      <StatusBadge value={cp.source} />
                                      <span className="text-xs text-gray-400">
                                        {new Date(cp.observed_at).toLocaleDateString()}
                                      </span>
                                      {cp.url && (
                                        <a
                                          href={cp.url}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="text-xs text-gray-500 underline"
                                        >
                                          link
                                        </a>
                                      )}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                            <form
                              onSubmit={handleAddCompetitorPrice}
                              className="flex flex-1 flex-col gap-2 sm:max-w-xs"
                            >
                              <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                Record a competitor price
                              </h3>
                              <input
                                required
                                placeholder="Competitor name"
                                value={competitorName}
                                onChange={(e) => setCompetitorName(e.target.value)}
                                className="input"
                              />
                              <input
                                required
                                placeholder="Price, e.g. 89.99"
                                inputMode="decimal"
                                value={competitorPrice}
                                onChange={(e) => setCompetitorPrice(e.target.value)}
                                className="input"
                              />
                              <input
                                placeholder="URL (optional)"
                                value={competitorUrl}
                                onChange={(e) => setCompetitorUrl(e.target.value)}
                                className="input"
                              />
                              {competitorError && (
                                <p className="text-xs text-red-600">{competitorError}</p>
                              )}
                              <button
                                type="submit"
                                disabled={competitorSubmitting}
                                className="btn-primary self-start text-xs"
                              >
                                {competitorSubmitting ? "Adding…" : "Add"}
                              </button>
                            </form>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {products === null && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                    Loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="max-w-lg rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="text-base font-semibold text-gray-900">Add a product manually</h2>
          <p className="mt-1 text-xs text-gray-500">
            Normally products arrive via a connection sync - this is for testing without a live
            store.
          </p>
          {connections.length === 0 ? (
            <p className="mt-4 rounded-md border border-dashed border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-500">
              Add a connection first.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
              <Field label="Connection">
                <select
                  value={connectionId}
                  onChange={(e) => setConnectionId(e.target.value)}
                  className="input"
                >
                  {connections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="SKU">
                <input
                  required
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  className="input"
                />
              </Field>
              <Field label="Name">
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="input"
                />
              </Field>
              <Field label="Cost (optional - needed for pricing recommendations)">
                <input
                  value={cost}
                  onChange={(e) => setCost(e.target.value)}
                  className="input"
                  placeholder="60.00"
                  inputMode="decimal"
                />
              </Field>
              <Field label="Price">
                <input
                  required
                  value={priceAmount}
                  onChange={(e) => setPriceAmount(e.target.value)}
                  className="input"
                  placeholder="99.99"
                  inputMode="decimal"
                />
              </Field>
              <Field label="Stock quantity (optional)">
                <input
                  value={stockQuantity}
                  onChange={(e) => setStockQuantity(e.target.value)}
                  className="input"
                  inputMode="numeric"
                />
              </Field>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <button type="submit" disabled={submitting} className="btn-primary self-start">
                {submitting ? "Adding…" : "Add product"}
              </button>
            </form>
          )}
        </div>
      </div>
    </AppShell>
  );
}
