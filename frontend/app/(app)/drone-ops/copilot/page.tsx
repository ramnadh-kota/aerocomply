"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { AIConsole } from "@/components/ai/AIConsole";
import { AI_NAME, AI_DESCRIPTION } from "@/lib/brand";
import { FeatureGuard } from "@/components/auth/FeatureGuard";

function CopilotBody() {
  const params = useSearchParams();
  const assetId = params.get("assetId") ?? undefined;
  const initialQuestion = params.get("q") ?? undefined;
  
  return <AIConsole initialAircraftId={assetId} initialQuestion={initialQuestion} />;
}

export default function CopilotPage() {
  return (
    <FeatureGuard featureKey="lisa_ai_copilot">
      <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto" }}>
        <Breadcrumbs items={[{ label: "Drone Operations", href: "/drone-ops/overview" }, { label: "LISA Copilot" }]} />
        <div className="ac-section-header" style={{ marginBottom: "24px" }}>
          <div>
            <h1 className="ac-h1" style={{ fontSize: "24px", fontWeight: 600, color: "var(--ac-text-primary)", margin: 0 }}>
              {AI_NAME} Copilot
            </h1>
            <p className="ac-text-sm ac-text-secondary" style={{ margin: "4px 0 0" }}>
              {AI_DESCRIPTION}
            </p>
          </div>
        </div>
        <Suspense fallback={<div className="ac-card" style={{ padding: "24px", textAlign: "center", color: "var(--ac-text-muted)" }}>Loading Copilot…</div>}>
          <CopilotBody />
        </Suspense>
      </div>
    </FeatureGuard>
  );
}
