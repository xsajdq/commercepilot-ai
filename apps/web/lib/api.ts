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
