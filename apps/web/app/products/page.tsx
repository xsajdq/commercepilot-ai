"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  createProduct,
  generateContentRecommendation,
  generateListingPublishRecommendation,
  generatePricingRecommendation,
  listConnections,
  listProducts,
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
                return (
                  <tr key={p.id}>
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
                        <div className="flex gap-2">
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
                        </div>
                        {(actionMessages[p.id] || (offer && actionMessages[offer.id])) && (
                          <p className="max-w-xs text-right text-xs text-gray-500">
                            {actionMessages[p.id] ?? actionMessages[offer!.id]}
                          </p>
                        )}
                      </div>
                    </td>
                  </tr>
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
