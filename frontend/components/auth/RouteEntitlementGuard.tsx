"use client";

import { type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { FeatureGuard } from "@/components/auth/FeatureGuard";
import { getRouteFeatureKey } from "@/lib/entitlements/navFeatureMap";

/**
 * Applies FeatureGuard to any route listed in NAV_FEATURE_MAP so a directly
 * typed URL is blocked the same way the sidebar item is greyed out. Display
 * only -- the backend require_feature dependency is the actual enforcement.
 */
export function RouteEntitlementGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const featureKey = getRouteFeatureKey(pathname);
  if (!featureKey) return <>{children}</>;
  return <FeatureGuard featureKey={featureKey}>{children}</FeatureGuard>;
}
