"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FeatureGuard } from "@/components/auth/FeatureGuard";
import { useSession } from "@/lib/auth/SessionContext";
import { getRouteFeatureKey, isPlatformPath, isPlatformRole } from "@/lib/entitlements/navFeatureMap";
import { LIVE_EQUIVALENT, matchMockOnlyRoute } from "@/lib/mock-only-routes";

/**
 * Display-side route protection for the (app) shell. Two independent rules:
 *
 *  1. /platform/* is for platform operators only. A tenant user who types the URL used to see the
 *     platform pages' chrome (headings, "Provisioning" actions) with the data refused by the API.
 *     Now they get a clear "not available" card and the platform page is never mounted.
 *  2. Any route listed in NAV_FEATURE_MAP is wrapped in FeatureGuard, so a directly typed URL is
 *     blocked the same way the sidebar item is greyed out.
 *
 * Both are display only -- the backend (require_permission / require_feature) is the enforcement.
 */
export function RouteEntitlementGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { user, loading, isDemo } = useSession();

  if (isPlatformPath(pathname) && !isDemo) {
    if (loading) return <div className="ac-card" style={{ padding: 24, textAlign: "center" }}>Checking access…</div>;
    if (!isPlatformRole(user?.roles)) {
      return (
        <div className="ac-card" role="alert" style={{ padding: 32, textAlign: "center", margin: "24px 0" }}>
          <h2 className="ac-h2" style={{ marginBottom: 8 }}>Not authorized</h2>
          <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 480, margin: "0 auto 16px" }}>
            Platform administration is available to platform operators only.
          </p>
          <Link href="/dashboard" className="ac-btn ac-btn-primary">Return to Dashboard</Link>
        </div>
      );
    }
  }

  // Pages that only contain bundled sample data must not present it as this organization's own records.
  const mockOnly = matchMockOnlyRoute(pathname);
  if (mockOnly && !isDemo) {
    if (loading) return <div className="ac-card" style={{ padding: 24, textAlign: "center" }}>Checking access…</div>;
    const live = LIVE_EQUIVALENT[mockOnly];
    return (
      <div className="ac-card" role="status" style={{ padding: 32, textAlign: "center", margin: "24px 0" }}>
        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Not connected to live data yet</h2>
        <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 520, margin: "0 auto 16px" }}>
          This module currently shows demonstration data only, so it is hidden for live organizations to avoid presenting
          sample records as yours. It is available in Demo mode.
        </p>
        {live && (
          <p className="ac-text-sm" style={{ marginBottom: 16 }}>
            Live data for this purpose: <Link href={live.href} className="ac-link">{live.label}</Link>
          </p>
        )}
        <Link href="/dashboard" className="ac-btn ac-btn-primary">Return to Dashboard</Link>
      </div>
    );
  }

  const featureKey = getRouteFeatureKey(pathname);
  if (!featureKey) return <>{children}</>;
  return <FeatureGuard featureKey={featureKey}>{children}</FeatureGuard>;
}
