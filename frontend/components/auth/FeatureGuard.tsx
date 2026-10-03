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
  const { hasFeature, loading, resolutionStatus, suiteCode, activeSuiteCodes, planName, planCode } = useEntitlements();
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

    let lockTitle = "Feature Not Included";
    let lockDescription = `This feature (${featureKey}) is not included in your organization's current plan or tenant configuration.`;

    if (resolutionStatus === "SUSPENDED") {
      lockTitle = "Organization Suspended";
      lockDescription = "Your organization account is currently suspended. Operational access to this module is temporarily withheld.";
    } else if (resolutionStatus === "NO_SUBSCRIPTION") {
      lockTitle = "No Active Subscription";
      lockDescription = "Your organization does not currently hold an active subscription for this platform feature.";
    } else if (resolutionStatus === "AMBIGUOUS" || resolutionStatus === "INVALID") {
      lockTitle = "Subscription Needs Review";
      lockDescription = "Your organization's subscription configuration is pending verification. Please contact Kota Aerospace Support.";
    } else {
      const heldSuites = new Set(
        [suiteCode, ...(activeSuiteCodes ?? [])].filter((c): c is string => !!c).map((c) => c.toUpperCase())
      );
      const isDroneFeature = featureKey.startsWith("drone_") || featureKey === "battery_analytics";
      const isAircraftFeature = featureKey.startsWith("aircraft_");

      if (isDroneFeature && heldSuites.has("AIRCRAFT") && !heldSuites.has("DRONE_UAV") && !heldSuites.has("MULTI_SUITE")) {
        lockTitle = "Suite Restriction";
        lockDescription = `This capability belongs to the Drone / UAV Suite, but your organization is currently on the Aircraft Suite. An add-on or multi-suite subscription is required.`;
      } else if (isAircraftFeature && heldSuites.has("DRONE_UAV") && !heldSuites.has("AIRCRAFT") && !heldSuites.has("MULTI_SUITE")) {
        lockTitle = "Suite Restriction";
        lockDescription = `This capability belongs to the Aircraft Suite, but your organization is currently on the Drone / UAV Suite.`;
      } else {
        const tier = planName || planCode ? ` (${planName || planCode})` : "";
        lockDescription = `This feature (${featureKey}) is restricted on your organization's current plan tier${tier}. Contact your administrator to upgrade.`;
      }
    }

    return (
      <div className="ac-card" style={{ padding: 32, textAlign: "center", margin: "24px 0" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>🔒</div>
        <h2 className="ac-h2" style={{ marginBottom: 8 }}>{lockTitle}</h2>
        <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 480, margin: "0 auto 16px" }}>
          {lockDescription}
        </p>
        <Link href="/tenant/subscription" className="ac-btn ac-btn-primary" style={{ display: "inline-block" }}>
          View Plan &amp; Subscription →
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
