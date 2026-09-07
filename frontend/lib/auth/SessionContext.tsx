"use client";

// Real authentication session state — backed by the actual FastAPI backend
// (backend/app/api/v1/auth.py). This is distinct from lib/role-sim/RoleSimContext,
// which is a purely visual "view as role" toy that never touches the network;
// SessionContext holds the real logged-in identity (user/org/roles) from a
// real JWT, used for REAL data-mode API calls. DEMO mode does not require a
// session and ignores this context's absence.
//
// Tokens are stored in localStorage under the existing audited keys
// (ACCESS_TOKEN_STORAGE_KEY / REFRESH_TOKEN_STORAGE_KEY from apiClient.ts) —
// that tradeoff (vs httpOnly cookies) was already made in login/page.tsx.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ACCESS_TOKEN_STORAGE_KEY,
  REFRESH_TOKEN_STORAGE_KEY,
  authApi,
  type CurrentUser,
} from "@/lib/apiClient";

interface SessionContextValue {
  user: CurrentUser | null;
  accessToken: string | null;
  /** True while restoring a session from localStorage on first load. */
  loading: boolean;
  /** Store tokens and load /auth/me. Throws on failure (caller shows the error). */
  login: (tokens: { access_token: string; refresh_token: string }) => Promise<CurrentUser>;
  logout: () => void;
  isAuthenticated: boolean;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    try {
      window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
      window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    } catch {
      // best-effort
    }
  }, []);

  const login = useCallback(async (tokens: { access_token: string; refresh_token: string }) => {
    try {
      window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, tokens.access_token);
      window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, tokens.refresh_token);
    } catch {
      // best-effort
    }
    const me = await authApi.me(tokens.access_token);
    setAccessToken(tokens.access_token);
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(() => {
    clearSession();
  }, [clearSession]);

  // Session restoration on first load: if a token is stored, validate it
  // against /auth/me; clear the session if it's invalid/expired.
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      let token: string | null = null;
      try {
        token = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
      } catch {
        token = null;
      }
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const me = await authApi.me(token);
        if (!cancelled) {
          setAccessToken(token);
          setUser(me);
        }
      } catch {
        if (!cancelled) clearSession();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    restore();
    return () => {
      cancelled = true;
    };
  }, [clearSession]);

  const value = useMemo<SessionContextValue>(
    () => ({
      user,
      accessToken,
      loading,
      login,
      logout,
      isAuthenticated: !!user && !!accessToken,
    }),
    [user, accessToken, loading, login, logout]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
