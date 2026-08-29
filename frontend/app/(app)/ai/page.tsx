"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { AIConsole } from "@/components/ai/AIConsole";

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
          <h1 className="ac-h1">AeroComply AI</h1>
          <p className="ac-subtitle">
            AI Prototype · Based on current AeroComply demo data · Non-authoritative · Human review required. Ask
            about projects, aircraft, work orders, or inspections.
          </p>
        </div>
      </div>
      <Suspense fallback={<div className="ac-card">Loading assistant…</div>}>
        <AiAssistantBody />
      </Suspense>
    </div>
  );
}
