"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FeatureGuard } from "@/components/auth/FeatureGuard";
import { useSession } from "@/lib/auth/SessionContext";
import { getRouteFeatureKey, isPlatformPath, isPlatformRole } from "@/lib/entitlements/navFeatureMap";
import { liveRedirectFor, matchMockOnlyRoute } from "@/lib/mock-only-routes";
import { isRouteForbidden } from "@/lib/rbac/routePermissions";

/**
 * Display-side route protection for the (app) shell. Two independent rules:
 *
 *  1. /platform/* is for platform operators only. A tenant user who types the URL used to see the
 *     platform pages' chrome (headings, "Provisioning" actions) with the data refused by the API.
 *     Now they get a clear "not available" card and the platform page is never mounted.
 *  2. Routes in lib/rbac/routePermissions.ts show an "Access restricted" state when the user's role lacks the permission.
 *  3. Any route listed in NAV_FEATURE_MAP is wrapped in FeatureGuard, so a directly typed URL is
 *     blocked the same way the sidebar item is greyed out.
 *
 * Both are display only -- the backend (require_permission / require_feature) is the enforcement.
 */
export function RouteEntitlementGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { user, loading, isDemo } = useSession();
  const router = useRouter();
  const mockOnly = matchMockOnlyRoute(pathname);
  const redirectTo = !isDemo && mockOnly ? liveRedirectFor(pathname) : null;
  useEffect(() => {
    if (redirectTo) router.replace(redirectTo);
  }, [redirectTo, router]);

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
  if (mockOnly && !isDemo) {
    if (loading || redirectTo) {
      return <div className="ac-card" style={{ padding: 24, textAlign: "center" }}>{redirectTo ? "Opening the live view…" : "Checking access…"}</div>;
    }
    return (
      <div className="ac-card" role="status" style={{ padding: 32, textAlign: "center", margin: "24px 0" }}>
        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Not connected to live data yet</h2>
        <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 520, margin: "0 auto 16px" }}>
          This module currently shows demonstration data only, so it is hidden for live organizations to avoid presenting
          sample records as yours. It is available in Demo mode.
        </p>
        <Link href="/dashboard" className="ac-btn ac-btn-primary">Return to Dashboard</Link>
      </div>
    );
  }

  // RBAC: a typed URL for a page the user's role has no permission for gets an explicit 403-style state instead of a page
  // full of failed requests. Platform operators never reach tenant pages through this check (separate nav + backend).
  if (!isDemo && !isPlatformRole(user?.roles) && isRouteForbidden(pathname, user?.permissions)) {
    return (
      <div className="ac-card" role="alert" style={{ padding: 32, textAlign: "center", margin: "24px 0" }}>
        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Access restricted</h2>
        <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 480, margin: "0 auto 16px" }}>
          Your role does not include permission to use this page. Ask an Organization Administrator if you need access.
        </p>
        <Link href="/dashboard" className="ac-btn ac-btn-primary">Return to Dashboard</Link>
      </div>
    );
  }

  const featureKey = getRouteFeatureKey(pathname);
  if (!featureKey) return <>{children}</>;
  return <FeatureGuard featureKey={featureKey}>{children}</FeatureGuard>;
}
