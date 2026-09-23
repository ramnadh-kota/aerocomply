"use client";

// Authentication session state — supports both REAL backend sessions (JWT-backed)
// and isolated synthetic staging DEMO sessions (KOTA Aerospace Demo Operations).
//
// Real tokens are stored in localStorage under ACCESS_TOKEN_STORAGE_KEY / REFRESH_TOKEN_STORAGE_KEY.
// Demo sessions are stored under DEMO_SESSION_STORAGE_KEY and never use JWTs or contact the live backend.

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
export const DEMO_USER_EMAIL = "demo@kotaaerospace.com";
export const DEMO_USER_PASSWORD = "KotaDemo2026!";
export const DEMO_USER_ROLES = ["ORGANIZATION_ADMIN", "MAINTENANCE_MANAGER", "CHIEF_PILOT"];

export const DEMO_SESSION_STORAGE_KEY = "aerocomply_demo_session";

export const DEMO_USER: CurrentUser = {
  id: DEMO_USER_ID,
  organization_id: DEMO_ORG_ID,
  email: DEMO_USER_EMAIL,
  full_name: DEMO_USER_NAME,
  roles: DEMO_USER_ROLES,
  email_verified: true,
};

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
  /** Activate the synthetic staging DEMO session. */
  loginWithDemo: () => void;
  logout: () => void;
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
      window.localStorage.removeItem(DEMO_SESSION_STORAGE_KEY);
      window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
      window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    } catch {
      // best-effort
    }
  }, []);

  const loginWithDemo = useCallback(() => {
    try {
      window.localStorage.setItem(DEMO_SESSION_STORAGE_KEY, "true");
      window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
      window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    } catch {
      // best-effort
    }
    setUser(DEMO_USER);
    setAccessToken(null);
    setSessionType("DEMO");
  }, []);

  const login = useCallback(async (tokens: { access_token: string; refresh_token: string }) => {
    try {
      window.localStorage.removeItem(DEMO_SESSION_STORAGE_KEY);
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
      let isDemoActive = false;
      let token: string | null = null;
      try {
        isDemoActive = window.localStorage.getItem(DEMO_SESSION_STORAGE_KEY) === "true";
        token = window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
      } catch {
        isDemoActive = false;
        token = null;
      }

      if (isDemoActive) {
        if (!cancelled) {
          setUser(DEMO_USER);
          setAccessToken(null);
          setSessionType("DEMO");
          setLoading(false);
        }
        return;
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
      loginWithDemo,
      logout,
      isAuthenticated: !!user && (sessionType === "DEMO" || (sessionType === "REAL" && !!accessToken)),
    }),
    [user, accessToken, sessionType, organizationName, loading, login, loginWithDemo, logout]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
