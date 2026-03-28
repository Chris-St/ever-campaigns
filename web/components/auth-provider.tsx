"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { apiRequest } from "@/lib/api";
import {
  clearSession,
  getStoredToken,
  getStoredUser,
  setStoredUser,
  storeSession,
} from "@/lib/auth";
import type { AuthResponse, CurrentUser } from "@/lib/types";

interface AuthContextValue {
  token: string | null;
  user: CurrentUser | null;
  loading: boolean;
  setSessionData: (payload: AuthResponse) => void;
  refreshUser: (explicitToken?: string | null) => Promise<CurrentUser | null>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setToken(getStoredToken());
      setUser(getStoredUser());
      setLoading(false);
    });

    return () => window.cancelAnimationFrame(frame);
  }, []);

  function setSessionData(payload: AuthResponse) {
    storeSession(payload.access_token, payload.user);
    setToken(payload.access_token);
    setUser(payload.user);
  }

  async function refreshUser(explicitToken?: string | null) {
    const resolvedToken = explicitToken ?? getStoredToken();
    if (!resolvedToken) {
      setToken(null);
      setUser(null);
      return null;
    }

    try {
      const me = await apiRequest<CurrentUser>("/auth/me", {
        method: "GET",
        token: resolvedToken,
      });
      setStoredUser(me);
      setToken(resolvedToken);
      setUser(me);
      return me;
    } catch {
      clearSession();
      setToken(null);
      setUser(null);
      return null;
    }
  }

  function logout() {
    clearSession();
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        loading,
        setSessionData,
        refreshUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
