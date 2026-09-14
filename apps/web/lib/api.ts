const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type FastApiValidationError = {
  loc: (string | number)[];
  msg: string;
};

// FastAPI's `detail` is a plain string for most errors (401/403/404/409),
// but for a 422 it's a list of Pydantic validation errors instead - each
// with its own `loc`/`msg`, not a single message. Passing that array
// straight to `Error`/`ApiError` stringifies it as "[object Object]"
// (Array.prototype.toString calls each element's own toString, and a
// plain object's is literally that string) - flatten it into something
// a human can actually read instead.
function extractErrorMessage(body: unknown): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return "Request failed";
  }
  const detail = (body as { detail: unknown }).detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item: FastApiValidationError) => {
        const field = item.loc?.filter((part) => part !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }

  return "Request failed";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, extractErrorMessage(body));
  }

  return (await response.json()) as T;
}

export type TenantOut = {
  id: string;
  name: string;
  slug: string;
};

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  tenant_id: string;
  role: string;
};

export type MembershipOut = {
  tenant: TenantOut;
  role: string;
};

export type LoginResponse = {
  requires_tenant_selection: boolean;
  token: TokenResponse | null;
  memberships: MembershipOut[] | null;
};

export type MeResponse = {
  user: { id: string; email: string; full_name: string };
  tenant: TenantOut;
  role: string;
};

export function registerAccount(payload: {
  email: string;
  password: string;
  full_name: string;
  tenant_name: string;
}): Promise<TokenResponse> {
  return request("/auth/register", { method: "POST", body: JSON.stringify(payload) });
}

export function login(payload: {
  email: string;
  password: string;
  tenant_id?: string;
}): Promise<LoginResponse> {
  return request("/auth/login", { method: "POST", body: JSON.stringify(payload) });
}

export function fetchMe(accessToken: string): Promise<MeResponse> {
  return request("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export type ConnectionPlatform = "woocommerce" | "allegro" | "shoper" | "prestashop" | "idosell";
export type ConnectionStatus = "connected" | "disconnected" | "error";

export type ConnectionOut = {
  id: string;
  platform: ConnectionPlatform;
  name: string;
  status: ConnectionStatus;
  last_synced_at: string | null;
  last_error: string | null;
};

export type OfferOut = {
  id: string;
  connection_id: string;
  status: string;
  price_amount: string | null;
  currency: string | null;
  stock_quantity: number | null;
};

export type ProductOut = {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  cost: string | null;
  status: string;
  offers: OfferOut[];
};

export type RecommendationStatus =
  | "proposed"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "executing"
  | "success"
  | "failed";

export type RecommendationOut = {
  id: string;
  type: string;
  risk_level: "low" | "medium" | "high";
  status: RecommendationStatus;
  entity_type: string;
  entity_id: string;
  title: string;
  reason: string | null;
  confidence: string | null;
  created_at: string;
};

export type TaskTriggeredResponse = { task_id: string };

export type AIJobStatus = "queued" | "running" | "succeeded" | "failed";

export type CatalogIssueOut = {
  type: string;
  severity: "low" | "medium" | "high";
  entity_type: string;
  entity_id: string;
  sku: string;
  message: string;
};

export type CatalogAuditOut = {
  id: string;
  status: AIJobStatus;
  products_scanned: number | null;
  recommendations_proposed: number | null;
  issues: CatalogIssueOut[];
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export function listConnections(token: string): Promise<ConnectionOut[]> {
  return request("/connections", { headers: authHeaders(token) });
}

export function createConnection(
  token: string,
  payload: { platform: ConnectionPlatform; name: string; credentials: Record<string, string> },
): Promise<ConnectionOut> {
  return request("/connections", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export function syncConnection(token: string, connectionId: string): Promise<TaskTriggeredResponse> {
  return request(`/connections/${connectionId}/sync`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function listProducts(token: string): Promise<ProductOut[]> {
  return request("/products", { headers: authHeaders(token) });
}

export function createProduct(
  token: string,
  payload: {
    connection_id: string;
    sku: string;
    name: string;
    cost?: string;
    vat_rate?: string;
    price_amount: string;
    currency?: string;
    stock_quantity?: number;
  },
): Promise<ProductOut> {
  return request("/products", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export type CompetitorPriceOut = {
  id: string;
  competitor_name: string;
  url: string | null;
  price: string;
  currency: string;
  source: "manual" | "api";
  observed_at: string;
};

export function listCompetitorPrices(
  token: string,
  productId: string,
): Promise<CompetitorPriceOut[]> {
  return request(`/products/${productId}/competitor-prices`, { headers: authHeaders(token) });
}

export function createCompetitorPrice(
  token: string,
  productId: string,
  payload: { competitor_name: string; price: string; url?: string },
): Promise<CompetitorPriceOut> {
  return request(`/products/${productId}/competitor-prices`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  });
}

export function generateContentRecommendation(
  token: string,
  productId: string,
): Promise<TaskTriggeredResponse> {
  return request(`/products/${productId}/generate-content-recommendation`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function generatePricingRecommendation(
  token: string,
  offerId: string,
): Promise<TaskTriggeredResponse> {
  return request(`/offers/${offerId}/generate-pricing-recommendation`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function generateListingPublishRecommendation(
  token: string,
  offerId: string,
): Promise<TaskTriggeredResponse> {
  return request(`/offers/${offerId}/generate-listing-publish-recommendation`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

export function listRecommendations(
  token: string,
  status?: RecommendationStatus,
): Promise<RecommendationOut[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/recommendations${query}`, { headers: authHeaders(token) });
}

export function approveRecommendation(
  token: string,
  id: string,
  decisionReason?: string,
): Promise<RecommendationOut> {
  return request(`/recommendations/${id}/approve`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ decision_reason: decisionReason ?? null }),
  });
}

export function rejectRecommendation(
  token: string,
  id: string,
  decisionReason?: string,
): Promise<RecommendationOut> {
  return request(`/recommendations/${id}/reject`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ decision_reason: decisionReason ?? null }),
  });
}

export function triggerCatalogAudit(token: string): Promise<TaskTriggeredResponse> {
  return request("/catalog/audit", { method: "POST", headers: authHeaders(token) });
}

export function listCatalogAudits(token: string): Promise<CatalogAuditOut[]> {
  return request("/catalog/audits", { headers: authHeaders(token) });
}

export type DashboardMetricsOut = {
  total_products: number;
  products_by_status: Record<string, number>;
  total_offers: number;
  offers_missing_price: number;
  out_of_stock_offers: number;
  total_catalog_value: string;
  average_margin_rate: string | null;
  recommendations_by_status: Record<string, number>;
  recommendations_by_type: Record<string, number>;
  latest_catalog_issue_count: number | null;
};

export type DashboardNarrativeOut = {
  summary: string;
  highlights: string[];
};

export type AnalyticsReportOut = {
  id: string;
  status: AIJobStatus;
  metrics: DashboardMetricsOut | null;
  narrative: DashboardNarrativeOut | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export function getDashboardMetrics(token: string): Promise<DashboardMetricsOut> {
  return request("/analytics/dashboard", { headers: authHeaders(token) });
}

export function triggerDashboardNarrative(token: string): Promise<TaskTriggeredResponse> {
  return request("/analytics/narrative", { method: "POST", headers: authHeaders(token) });
}

export function listDashboardNarratives(token: string): Promise<AnalyticsReportOut[]> {
  return request("/analytics/narratives", { headers: authHeaders(token) });
}

export type PlanTier = "free" | "starter" | "pro";
export type SubscriptionStatus = "active" | "past_due" | "canceled" | "incomplete";

export type BillingStatusOut = {
  plan: PlanTier;
  status: SubscriptionStatus;
  budget: string;
  spent_this_period: string;
  remaining: string;
  is_exceeded: boolean;
  has_stripe_subscription: boolean;
};

export function getBillingStatus(token: string): Promise<BillingStatusOut> {
  return request("/billing", { headers: authHeaders(token) });
}

export function createCheckoutSession(
  token: string,
  plan: "starter" | "pro",
): Promise<{ checkout_url: string }> {
  return request("/billing/checkout", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ plan }),
  });
}

export function createPortalSession(token: string): Promise<{ portal_url: string }> {
  return request("/billing/portal", { method: "POST", headers: authHeaders(token) });
}
