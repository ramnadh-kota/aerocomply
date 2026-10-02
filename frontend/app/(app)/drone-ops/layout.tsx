import type { ReactNode } from "react";
import { DroneOpsLayout } from "@/components/drone-ops/DroneOpsLayout";
import { SuiteGuard } from "@/components/auth/SuiteGuard";

// ─────────────────────────────────────────────────────────────────────────────
// Drone Operations route group layout.
//
// Applies to all routes under /drone-ops/*.
// - Wraps in SuiteGuard(DRONE_UAV) so unauthorized orgs see an upgrade prompt
//   rather than empty/broken pages.
// - Uses DroneOpsLayout (full-screen command center) instead of the standard
//   Kota app shell — the standard .ac-shell sidebar/topbar is intentionally
//   bypassed here.
// - The outer AuthGuard + EntitlementProvider from the (app) group layout
//   (app/(app)/layout.tsx) is still active for auth protection and
//   entitlement resolution.
// ─────────────────────────────────────────────────────────────────────────────

export const metadata = {
  title: "Drone Operations — Kota Aerospace",
  description:
    "Live drone fleet monitoring, mission tracking, telemetry and LISA copilot for Kota Aerospace operators.",
};

export default function DroneOpsGroupLayout({ children }: { children: ReactNode }) {
  return (
    <SuiteGuard requiredSuite="DRONE_UAV">
      <DroneOpsLayout>{children}</DroneOpsLayout>
    </SuiteGuard>
  );
}
