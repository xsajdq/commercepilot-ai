const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
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
    throw new ApiError(response.status, body.detail ?? "Request failed");
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
