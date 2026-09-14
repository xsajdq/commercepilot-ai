"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  createConnection,
  listConnections,
  syncConnection,
  testConnection,
  type ConnectionOut,
  type ConnectionPlatform,
} from "@/lib/api";
import { getAccessToken } from "@/lib/session";
import AppShell from "@/components/AppShell";
import Field from "@/components/Field";
import StatusBadge from "@/components/StatusBadge";

type SyncSupport = "full" | "partial" | "none";

const PLATFORMS: { value: ConnectionPlatform; label: string; sync: SyncSupport }[] = [
  { value: "woocommerce", label: "WooCommerce", sync: "full" },
  { value: "allegro", label: "Allegro", sync: "full" },
  { value: "shoper", label: "Shoper", sync: "full" },
  { value: "prestashop", label: "PrestaShop", sync: "full" },
  { value: "idosell", label: "IdoSell", sync: "partial" },
];

const CREDENTIAL_HELP: Record<ConnectionPlatform, string> = {
  woocommerce:
    "In your WordPress admin: WooCommerce → Settings → Advanced → REST API → Add key. Give it Read/Write permissions.",
  allegro:
    "Generate an access token for your app in Allegro's Developer Portal (apps.developer.allegro.pl) - use the client credentials or device-code flow for a seller account token.",
  shoper:
    "In your Shoper admin: Settings → API → Applications → Add application, to get a Client ID and Client Secret.",
  prestashop:
    "In your PrestaShop admin: Advanced Parameters → Webservice → Add new key. Grant it access to products, stock, and prices.",
  idosell:
    "In your IdoSell admin: Panel administracyjny → Ustawienia → Integracje → API, to generate an Admin API key.",
};

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<ConnectionOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [syncMessages, setSyncMessages] = useState<Record<string, string>>({});
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});

  const [platform, setPlatform] = useState<ConnectionPlatform>("woocommerce");
  const [name, setName] = useState("");
  const [storeUrl, setStoreUrl] = useState("");
  const [consumerKey, setConsumerKey] = useState("");
  const [consumerSecret, setConsumerSecret] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [shoperClientId, setShoperClientId] = useState("");
  const [shoperClientSecret, setShoperClientSecret] = useState("");
  const [prestashopApiKey, setPrestashopApiKey] = useState("");
  const [idosellApiKey, setIdosellApiKey] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function refresh() {
    const token = getAccessToken();
    if (!token) return;
    listConnections(token).then(setConnections).catch(() => setConnections([]));
  }

  useEffect(refresh, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const token = getAccessToken();
    if (!token) return;
    setError(null);
    setSubmitting(true);

    const credentials: Record<string, string> =
      platform === "woocommerce"
        ? { store_url: storeUrl, consumer_key: consumerKey, consumer_secret: consumerSecret }
        : platform === "allegro"
          ? { access_token: accessToken }
          : platform === "shoper"
            ? {
                store_url: storeUrl,
                client_id: shoperClientId,
                client_secret: shoperClientSecret,
              }
            : platform === "prestashop"
              ? { store_url: storeUrl, api_key: prestashopApiKey }
              : platform === "idosell"
                ? { store_url: storeUrl, api_key: idosellApiKey }
                : {};

    try {
      await createConnection(token, { platform, name, credentials });
      setName("");
      setStoreUrl("");
      setConsumerKey("");
      setConsumerSecret("");
      setAccessToken("");
      setShoperClientId("");
      setShoperClientSecret("");
      setPrestashopApiKey("");
      setIdosellApiKey("");
      setNotice("Connection added - testing it against the real store now, refresh in a moment to see the result.");
      refresh();
      setTimeout(refresh, 3000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTest(connectionId: string) {
    const token = getAccessToken();
    if (!token) return;
    setTestMessages((prev) => ({ ...prev, [connectionId]: "Testing…" }));
    try {
      await testConnection(token, connectionId);
      setTestMessages((prev) => ({ ...prev, [connectionId]: "Checking - refresh in a moment" }));
      setTimeout(refresh, 3000);
    } catch (err) {
      setTestMessages((prev) => ({
        ...prev,
        [connectionId]: err instanceof ApiError ? err.message : "Failed to queue the test",
      }));
    }
  }

  async function handleSync(connectionId: string) {
    const token = getAccessToken();
    if (!token) return;
    setSyncMessages((prev) => ({ ...prev, [connectionId]: "Queuing…" }));
    try {
      const result = await syncConnection(token, connectionId);
      setSyncMessages((prev) => ({
        ...prev,
        [connectionId]: `Sync queued (task ${result.task_id.slice(0, 8)}…)`,
      }));
    } catch (err) {
      setSyncMessages((prev) => ({
        ...prev,
        [connectionId]: err instanceof ApiError ? err.message : "Failed to queue sync",
      }));
    }
  }

  const selectedPlatform = PLATFORMS.find((p) => p.value === platform)!;

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Connections</h1>
          <p className="mt-1 text-sm text-slate-500">
            Stores and marketplaces this workspace syncs products from.
          </p>
        </div>

        {notice && (
          <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {notice}
          </p>
        )}

        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Platform</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Last synced</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {connections?.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                    No connections yet - add one below.
                  </td>
                </tr>
              )}
              {connections?.map((c) => (
                <tr key={c.id} className="transition hover:bg-slate-50/60">
                  <td className="px-4 py-3 font-medium text-slate-900">{c.name}</td>
                  <td className="px-4 py-3 text-slate-500">{c.platform}</td>
                  <td className="px-4 py-3">
                    <StatusBadge value={c.status} />
                    {c.last_error && (
                      <p className="mt-1 max-w-xs text-xs text-rose-600">{c.last_error}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {c.last_synced_at ? new Date(c.last_synced_at).toLocaleString() : "Never"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => handleTest(c.id)} className="btn-secondary">
                        Test connection
                      </button>
                      <button onClick={() => handleSync(c.id)} className="btn-secondary">
                        Sync now
                      </button>
                    </div>
                    {testMessages[c.id] && (
                      <p className="mt-1 text-xs text-slate-500">{testMessages[c.id]}</p>
                    )}
                    {syncMessages[c.id] && (
                      <p className="mt-1 text-xs text-slate-500">{syncMessages[c.id]}</p>
                    )}
                  </td>
                </tr>
              ))}
              {connections === null && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                    Loading…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card max-w-lg p-6">
          <h2 className="text-base font-semibold text-slate-900">Add a connection</h2>
          <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
            <Field label="Platform">
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value as ConnectionPlatform)}
                className="input"
              >
                {PLATFORMS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                    {p.sync === "none" ? " (sync not implemented yet)" : ""}
                    {p.sync === "partial" ? " (read-only, limited)" : ""}
                  </option>
                ))}
              </select>
            </Field>
            <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
              {CREDENTIAL_HELP[platform]}
            </p>
            <Field label="Name">
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input"
                placeholder="e.g. My WooCommerce Store"
              />
            </Field>

            {platform === "woocommerce" && (
              <>
                <Field label="Store URL">
                  <input
                    required
                    value={storeUrl}
                    onChange={(e) => setStoreUrl(e.target.value)}
                    className="input"
                    placeholder="https://shop.example.com"
                  />
                </Field>
                <Field label="Consumer key">
                  <input
                    required
                    value={consumerKey}
                    onChange={(e) => setConsumerKey(e.target.value)}
                    className="input"
                  />
                </Field>
                <Field label="Consumer secret">
                  <input
                    required
                    type="password"
                    value={consumerSecret}
                    onChange={(e) => setConsumerSecret(e.target.value)}
                    className="input"
                  />
                </Field>
              </>
            )}

            {platform === "allegro" && (
              <Field label="Access token">
                <input
                  required
                  type="password"
                  value={accessToken}
                  onChange={(e) => setAccessToken(e.target.value)}
                  className="input"
                />
              </Field>
            )}

            {platform === "shoper" && (
              <>
                <Field label="Store URL">
                  <input
                    required
                    value={storeUrl}
                    onChange={(e) => setStoreUrl(e.target.value)}
                    className="input"
                    placeholder="https://shop.example.pl"
                  />
                </Field>
                <Field label="Client ID">
                  <input
                    required
                    value={shoperClientId}
                    onChange={(e) => setShoperClientId(e.target.value)}
                    className="input"
                  />
                </Field>
                <Field label="Client secret">
                  <input
                    required
                    type="password"
                    value={shoperClientSecret}
                    onChange={(e) => setShoperClientSecret(e.target.value)}
                    className="input"
                  />
                </Field>
              </>
            )}

            {platform === "prestashop" && (
              <>
                <Field label="Store URL">
                  <input
                    required
                    value={storeUrl}
                    onChange={(e) => setStoreUrl(e.target.value)}
                    className="input"
                    placeholder="https://shop.example.com"
                  />
                </Field>
                <Field label="Webservice API key">
                  <input
                    required
                    type="password"
                    value={prestashopApiKey}
                    onChange={(e) => setPrestashopApiKey(e.target.value)}
                    className="input"
                  />
                </Field>
              </>
            )}

            {platform === "idosell" && (
              <>
                <Field label="Store URL">
                  <input
                    required
                    value={storeUrl}
                    onChange={(e) => setStoreUrl(e.target.value)}
                    className="input"
                    placeholder="https://shop.example.com"
                  />
                </Field>
                <Field label="Admin API key">
                  <input
                    required
                    type="password"
                    value={idosellApiKey}
                    onChange={(e) => setIdosellApiKey(e.target.value)}
                    className="input"
                  />
                </Field>
              </>
            )}

            {selectedPlatform.sync === "none" && (
              <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                The connection record can be created, but syncing this platform isn&apos;t built
                yet - see docs/architecture/roadmap.md.
              </p>
            )}

            {selectedPlatform.sync === "partial" && (
              <p className="rounded-xl border border-dashed border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                IdoSell&apos;s official docs were unreachable while this connector was built, so
                sync only reads real product/category ids for now - names, prices, and stock stay
                blank, and AI-driven actions (pricing, publishing) aren&apos;t available for this
                platform yet. See docs/architecture/roadmap.md.
              </p>
            )}

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <button type="submit" disabled={submitting} className="btn-primary self-start">
              {submitting ? "Adding…" : "Add connection"}
            </button>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
