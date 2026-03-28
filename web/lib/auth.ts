import type { CurrentUser } from "@/lib/types";

const TOKEN_KEY = "ever_token";
const USER_KEY = "ever_user";
const ACTIVE_CAMPAIGN_KEY = "ever_active_campaign";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): CurrentUser | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawValue = window.localStorage.getItem(USER_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(rawValue) as CurrentUser;
  } catch {
    return null;
  }
}

export function setStoredUser(user: CurrentUser): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function storeSession(token: string, user: CurrentUser): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  window.localStorage.removeItem(ACTIVE_CAMPAIGN_KEY);
}

export function getActiveCampaignId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(ACTIVE_CAMPAIGN_KEY);
}

export function setActiveCampaignId(campaignId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(ACTIVE_CAMPAIGN_KEY, campaignId);
}
