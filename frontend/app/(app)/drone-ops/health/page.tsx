"use client";

import { useSearchParams } from "next/navigation";
import { useSession } from "@/lib/auth/SessionContext";
import { HUMSHealthPanel } from "@/components/intelligence/HUMSHealthPanel";
import { Suspense, useEffect, useState } from "react";
import { humsApi, type HUMSAssetHealthSummary } from "@/lib/api/hums";

function HealthContent() {
  const searchParams = useSearchParams();
  const assetId = searchParams.get("assetId");
  const { accessToken } = useSession();
  const [health, setHealth] = useState<HUMSAssetHealthSummary | null>(null);

  useEffect(() => {
    if (!assetId || !accessToken) return;
    humsApi.getAssetHealth(accessToken, assetId).then(setHealth).catch(console.error);
  }, [assetId, accessToken]);

  if (!assetId) {
    return <div style={{ padding: 24, color: "var(--ac-text-muted)" }}>Select a drone to view HUMS health.</div>;
  }

  return (
    <div style={{ padding: "24px" }}>
      <h2 style={{ color: "var(--ac-text-primary)", marginTop: 0 }}>HUMS Health: {assetId}</h2>
      <HUMSHealthPanel health={health} accessToken={accessToken} />
    </div>
  );
}

export default function FleetHealthPage() {
  return (
    <Suspense fallback={<div style={{ padding: 24, color: "var(--ac-text-muted)" }}>Loading...</div>}>
      <HealthContent />
    </Suspense>
  );
}
