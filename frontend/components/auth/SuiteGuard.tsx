"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import { useEntitlements } from "@/lib/entitlements/EntitlementContext";
import { useSession } from "@/lib/auth/SessionContext";

/** Allowed when no suite info is known, or any held suite (aggregated code or an active subscription) is required. */
export function isSuiteAllowed(allowed: string[], suiteCode: string | null, activeSuiteCodes: string[]): boolean {
  const held = new Set([suiteCode, ...activeSuiteCodes].filter((c): c is string => !!c).map((c) => c.toUpperCase()));
  if (held.size === 0) return true;
  return allowed.some((a) => held.has(a.toUpperCase()));
}

interface SuiteGuardProps {
  requiredSuite: string | string[];
  children: ReactNode;
  fallback?: ReactNode;
}

export function SuiteGuard({ requiredSuite, children, fallback }: SuiteGuardProps) {
  const { suiteCode, activeSuiteCodes, loading } = useEntitlements();
  const { user } = useSession();

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  if (isPlatformUser) {
    return <>{children}</>;
  }

  if (loading) {
    return (
      <div className="ac-card" style={{ padding: 24, textAlign: "center" }}>
        Validating product suite entitlement…
      </div>
    );
  }

  const allowedSuites = Array.isArray(requiredSuite)
    ? requiredSuite.map((s) => s.toUpperCase())
    : [requiredSuite.toUpperCase()];

  const isAllowed = isSuiteAllowed(allowedSuites, suiteCode, activeSuiteCodes);

  if (!isAllowed) {
    if (fallback) return <>{fallback}</>;
    return (
      <div className="ac-card" style={{ padding: 32, textAlign: "center", margin: "24px 0" }}>
        <div style={{ fontSize: 36, marginBottom: 12 }}>✈️ ⃠</div>
        <h2 className="ac-h2" style={{ marginBottom: 8 }}>Suite Entitlement Required</h2>
        <p className="ac-text-sm ac-text-muted" style={{ maxWidth: 500, margin: "0 auto 16px" }}>
          This domain capability is restricted to organizations with an active subscription to the{" "}
          <strong>{allowedSuites.join(" / ")}</strong> suite. Your organization is currently on the{" "}
          <strong>{activeSuiteCodes.length > 0 ? activeSuiteCodes.join(" + ") : suiteCode || "unassigned"}</strong> suite.
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
          <Link href="/dashboard" className="ac-btn ac-btn-outline">
            ← Return to Dashboard
          </Link>
          <Link href="/tenant/subscription" className="ac-btn ac-btn-primary">
            View Current Suite &amp; Plan →
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
