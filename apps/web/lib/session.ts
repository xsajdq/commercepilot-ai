import type { TokenResponse } from "./api";

// localStorage is a pragmatic MVP choice, not a hardened one: it's
// readable by any script on the page, so an XSS bug becomes a session
// theft. Moving session storage to an httpOnly cookie (with CSRF
// protection) is tracked as production-hardening work (Phase 21), not a
// Phase 1 concern.
const ACCESS_TOKEN_KEY = "commercepilot.access_token";
const REFRESH_TOKEN_KEY = "commercepilot.refresh_token";

export function saveSession(token: TokenResponse) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, token.refresh_token);
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}
