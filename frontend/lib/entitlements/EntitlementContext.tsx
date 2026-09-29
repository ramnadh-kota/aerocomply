"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { entitlementApi, type EntitlementResolutionResponse } from "@/lib/api/entitlement";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { hasFeatureKey } from "./featureKeys";
import { getDemoOrganizationEntitlements } from "@/lib/demo/demoPlatform";

export interface EntitlementContextValue {
  resolution: EntitlementResolutionResponse | null;
  effectiveFeatures: Record<string, boolean> | null;
  loading: boolean;
  hasFeature: (featureKey: string) => boolean;
  refetchEntitlements: () => Promise<void>;
  suiteId: string | null;
  suiteCode: string | null;
  suiteName: string | null;
  planId: string | null;
  planCode: string | null;
  planName: string | null;
  modules: string[];
  pages: string[];
  resolutionStatus: string | null;
}

export const ENTITLEMENT_REFRESH_MIN_INTERVAL_MS = 15_000;
const GRANTING_STATUSES = new Set<string>(["ACTIVE", "INACTIVE_PLAN"]);

const EntitlementContext = createContext<EntitlementContextValue | null>(null);

export function EntitlementProvider({ children }: { children: ReactNode }) {
  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();
  const [resolution, setResolution] = useState<EntitlementResolutionResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchEntitlements = useCallback(async () => {
    if (mode === "DEMO") {
      const orgId = user?.organization_id ?? "00000000-0000-0000-0000-000000000001";
      const demoRes = getDemoOrganizationEntitlements(orgId);
      setResolution(demoRes);
      setLoading(false);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setResolution(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const res = await entitlementApi.getMyEntitlements(accessToken);
      setResolution(res);
    } catch {
      // Fail open on DISPLAY: real authorization is checked on the backend
      setResolution(null);
    } finally {
      setLoading(false);
    }
  }, [accessToken, isAuthenticated, mode, user?.organization_id]);

  useEffect(() => {
    fetchEntitlements();
  }, [fetchEntitlements]);

  // Refresh when the tab regains focus/visibility so a Platform Admin change
  // (feature/limit/plan/suspension) shows up without a full reload. The
  // backend already re-resolves on every request; this only keeps display in
  // step with it. Throttled so rapid focus flips don't spam the API.
  useEffect(() => {
    if (typeof window === "undefined" || mode === "DEMO" || !isAuthenticated) return;
    let last = Date.now();
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      if (Date.now() - last < ENTITLEMENT_REFRESH_MIN_INTERVAL_MS) return;
      last = Date.now();
      void fetchEntitlements();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [fetchEntitlements, isAuthenticated, mode]);

  const hasFeature = useCallback(
    (featureKey: string): boolean => {
      // No resolution yet / fetch failed: display fails open; the backend
      // still authorizes every request.
      if (!resolution) return true;
      // Mirror the backend: only ACTIVE / INACTIVE_PLAN resolutions grant
      // anything (SUSPENDED, NO_SUBSCRIPTION, AMBIGUOUS, INVALID never do).
      if (!GRANTING_STATUSES.has(resolution.resolution_status)) return false;
      return hasFeatureKey(resolution.effective_features ?? {}, featureKey);
    },
    [resolution]
  );

  const value = useMemo<EntitlementContextValue>(
    () => ({
      resolution,
      effectiveFeatures: resolution?.effective_features ?? null,
      loading,
      hasFeature,
      refetchEntitlements: fetchEntitlements,
      suiteId: resolution?.suite_id ?? null,
      suiteCode: resolution?.suite_code ?? null,
      suiteName: resolution?.suite_name ?? null,
      planId: resolution?.plan_id ?? null,
      planCode: resolution?.plan_code ?? null,
      planName: resolution?.plan_name ?? null,
      modules: resolution?.modules ?? [],
      pages: resolution?.pages ?? [],
      resolutionStatus: resolution?.resolution_status ?? null,
    }),
    [resolution, loading, hasFeature, fetchEntitlements]
  );

  return <EntitlementContext.Provider value={value}>{children}</EntitlementContext.Provider>;
}

export function useEntitlements(): EntitlementContextValue {
  const ctx = useContext(EntitlementContext);
  if (!ctx) {
    // Fallback if used outside EntitlementProvider
    return {
      resolution: null,
      effectiveFeatures: null,
      loading: false,
      hasFeature: () => true,
      refetchEntitlements: async () => {},
      suiteId: null,
      suiteCode: null,
      suiteName: null,
      planId: null,
      planCode: null,
      planName: null,
      modules: [],
      pages: [],
      resolutionStatus: null,
    };
  }
  return ctx;
}

export function useMyEntitlements(): {
  effectiveFeatures: Record<string, boolean> | null;
  loading: boolean;
  hasFeature: (featureKey: string) => boolean;
  refetchEntitlements: () => Promise<void>;
} {
  const ctx = useEntitlements();
  return {
    effectiveFeatures: ctx.effectiveFeatures,
    loading: ctx.loading,
    hasFeature: ctx.hasFeature,
    refetchEntitlements: ctx.refetchEntitlements,
  };
}
