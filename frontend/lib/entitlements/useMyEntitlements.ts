"use client";

// M21.4: thin fetch-once hook around entitlementApi.getMyEntitlements
// (GET /api/v1/entitlements -- tenant self-service, backed by
// app/services/entitlement_service.py). Used only by Sidebar.tsx to decide
// which nav items to gray out; UX only, never a security boundary (see
// lib/entitlements/navFeatureMap.ts's module docstring).

import { useEffect, useState } from "react";
import { entitlementApi, type EntitlementResolutionResponse } from "@/lib/api/entitlement";
import { useSession } from "@/lib/auth/SessionContext";

export function useMyEntitlements(): {
  effectiveFeatures: Record<string, boolean> | null;
  loading: boolean;
} {
  const { accessToken, isAuthenticated } = useSession();
  const [resolution, setResolution] = useState<EntitlementResolutionResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!isAuthenticated || !accessToken) {
      setResolution(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    entitlementApi
      .getMyEntitlements(accessToken)
      .then((res) => {
        if (!cancelled) setResolution(res);
      })
      .catch(() => {
        // Fail open on DISPLAY only: if the entitlement fetch fails (network
        // error, backend down, etc.), the sidebar simply shows every item
        // ungated rather than locking a tenant out of their own nav due to
        // a UX-layer fetch failure -- real authorization is unaffected
        // either way since the backend enforces it independently.
        if (!cancelled) setResolution(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, isAuthenticated]);

  return { effectiveFeatures: resolution?.effective_features ?? null, loading };
}
