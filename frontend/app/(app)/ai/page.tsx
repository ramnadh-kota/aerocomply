"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { AIConsole } from "@/components/ai/AIConsole";
import { PLATFORM_NAME, AI_NAME, AI_DESCRIPTION, AI_DEMO_DATA_FOOTER } from "@/lib/brand";

function AiAssistantBody() {
  const params = useSearchParams();
  const projectId = params.get("project") ?? undefined;
  const aircraftId = params.get("aircraft") ?? undefined;
  const initialQuestion = params.get("q") ?? undefined;
  return <AIConsole initialProjectId={projectId} initialAircraftId={aircraftId} initialQuestion={initialQuestion} />;
}

export default function AiAssistantPage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "AI Assistant" }]} />
      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">{AI_NAME}</h1>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: "2px 0 8px", fontWeight: 600 }}>{AI_DESCRIPTION}</p>
          <p className="ac-subtitle">
            {AI_DEMO_DATA_FOOTER} Ask about projects, aircraft, work orders, or inspections.
          </p>
        </div>
      </div>
      <Suspense fallback={<div className="ac-card">Loading assistant…</div>}>
        <AiAssistantBody />
      </Suspense>
    </div>
  );
}
