"use client";

// Authentication session state — REAL backend sessions (JWT-backed) only.
//
// Real tokens are stored in localStorage under ACCESS_TOKEN_STORAGE_KEY / REFRESH_TOKEN_STORAGE_KEY.
//
// A synthetic "DEMO" sessionType historically existed here as a client-side authentication
// bypass (hardcoded credentials, a one-click login button, no backend involvement). That
// bypass has been removed: authentication now has exactly one path — POST /auth/login on
// the real backend. SessionType/isDemo are kept in the shape below only because a separate,
// legitimate "demo data display" feature (see lib/demo/*, DataModeContext) reads them to
// decide whether to render synthetic data inside an already-authenticated REAL session;
// nothing in this file can ever produce sessionType "DEMO" anymore.
// DEMO_ORG_ID / DEMO_ORG_NAME / DEMO_USER_ID / DEMO_USER_NAME remain exported because
// lib/demo/demoTenant.ts, demoStore.ts, and demoDrones.ts key their synthetic records off
// these constants — they are data labels, not credentials, and are unrelated to authentication.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ACCESS_TOKEN_STORAGE_KEY,
  REFRESH_TOKEN_STORAGE_KEY,
  authApi,
  type CurrentUser,
} from "@/lib/apiClient";

export const DEMO_ORG_ID = "00000000-0000-0000-0000-000000000001";
export const DEMO_ORG_NAME = "KOTA Aerospace Demo Operations";
export const DEMO_USER_ID = "00000000-0000-0000-0000-000000000002";
export const DEMO_USER_NAME = "KOTA Aerospace Demo User";
// Display-only label for synthetic demo records (lib/demo/demoTenant.ts). Not paired with any
// password or login path — never used for authentication.
export const DEMO_USER_EMAIL = "demo@kotaaerospace.com";

export type SessionType = "REAL" | "DEMO";

export interface SessionContextValue {
  user: CurrentUser | null;
  accessToken: string | null;
  sessionType: SessionType | null;
  isDemo: boolean;
  isReal: boolean;
  organizationName: string | null;
  /** True while restoring a session from localStorage on first load. */
  loading: boolean;
  /** Store tokens and load /auth/me for a REAL session. Throws on failure. */
  login: (tokens: { access_token: string; refresh_token: string }) => Promise<CurrentUser>;
  logout: () => void;
  updateUser: (partialUser: Partial<CurrentUser>) => void;
  isAuthenticated: boolean;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [sessionType, setSessionType] = useState<SessionType | null>(null);
  const [loading, setLoading] = useState(true);

  const clearSession = useCallback(() => {
    setUser(null);
    setAccessToken(null);
    setSessionType(null);
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
    setSessionType("REAL");
    return me;
  }, []);

  const logout = useCallback(() => {
    clearSession();
  }, [clearSession]);

  // Session restoration on first load
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
          setSessionType("REAL");
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

  const organizationName = useMemo(() => {
    if (sessionType === "DEMO") return DEMO_ORG_NAME;
    return user?.organization_id ? `Org ${user.organization_id.slice(0, 8)}` : null;
  }, [sessionType, user]);

  const updateUser = useCallback(
    (partialUser: Partial<CurrentUser>) => {
      setUser((prev) => {
        if (!prev) return null;
        const updated = { ...prev, ...partialUser };
        if (sessionType === "DEMO" && typeof window !== "undefined") {
          try {
            const raw = window.sessionStorage.getItem("aerocomply_demo_store_v1");
            const parsed = raw ? JSON.parse(raw) : {};
            parsed.profile = { ...(parsed.profile || {}), ...partialUser };
            window.sessionStorage.setItem("aerocomply_demo_store_v1", JSON.stringify(parsed));
          } catch {
            // best-effort
          }
        }
        return updated;
      });
    },
    [sessionType]
  );

  const value = useMemo<SessionContextValue>(
    () => ({
      user,
      accessToken,
      sessionType,
      isDemo: sessionType === "DEMO",
      isReal: sessionType === "REAL",
      organizationName,
      loading,
      login,
      logout,
      updateUser,
      isAuthenticated: !!user && sessionType === "REAL" && !!accessToken,
    }),
    [user, accessToken, sessionType, organizationName, loading, login, logout, updateUser]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
