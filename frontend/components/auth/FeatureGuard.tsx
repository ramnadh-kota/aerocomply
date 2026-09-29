"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import { useEntitlements } from "@/lib/entitlements/EntitlementContext";
import { useSession } from "@/lib/auth/SessionContext";

interface FeatureGuardProps {
  featureKey: string;
  children: ReactNode;
  fallback?: ReactNode;
}

export function FeatureGuard({ featureKey, children, fallback }: FeatureGuardProps) {
  const { hasFeature, loading } = useEntitlements();
  const { user } = useSession();
  // Platform users administering the system bypass tenant commercial feature gates
  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  if (isPlatformUser) {
    return <>{children}</>;
  }

  if (loading) {
    return <div className="ac-card" style={{ padding: 24, textAlign: "center" }}>Checking feature authorization…</div>;
  }

  const allowed = hasFeature(featureKey);

  if (!allowed) {
    if (fallback) return <>{fallback}</>;
    return (
      <div className="ac-card" style={{ padding: 32, textAlign: "center", margin: "24px 0" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Feature Not Included</h2>
        <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 480, margin: "0 auto 16px" }}>
          This feature ({featureKey}) is not included in your organization&apos;s current plan or tenant configuration.
        </p>
        <Link href="/tenant/subscription" className="ac-btn ac-btn-primary" style={{ display: "inline-block" }}>
          View Plan &amp; Subscription →
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
