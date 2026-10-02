"use client";

import { useSearchParams } from "next/navigation";
import { useSession } from "@/lib/auth/SessionContext";
import { TelemetryPanel } from "@/components/intelligence/TelemetryPanel";
import { Suspense } from "react";

function TelemetryContent() {
  const searchParams = useSearchParams();
  const assetId = searchParams.get("assetId");
  const { accessToken } = useSession();

  if (!assetId) {
    return <div style={{ padding: 24, color: "var(--ac-text-muted)" }}>Select a drone to view telemetry.</div>;
  }

  return (
    <div style={{ padding: "24px" }}>
      <h2 style={{ color: "var(--ac-text-primary)", marginTop: 0 }}>Telemetry Stream: {assetId}</h2>
      <TelemetryPanel assetId={assetId} accessToken={accessToken} />
    </div>
  );
}

export default function TelemetryPage() {
  return (
    <Suspense fallback={<div style={{ padding: 24, color: "var(--ac-text-muted)" }}>Loading...</div>}>
      <TelemetryContent />
    </Suspense>
  );
}
