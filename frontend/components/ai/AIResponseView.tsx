"use client";

import type { MouseEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AiResponse } from "@/lib/mock/ai/engine";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { recordGeneratedReport } from "@/lib/mock/reports";
import { AI_NAME } from "@/lib/brand";
import { StatusBadge, priorityBadge } from "@/components/status/StatusBadge";

// Structured operational fields (priority, whatIFound, actionCategory, etc.)
// are populated only for a subset of substantive operational branches in
// engine.ts — everything below renders conditionally and falls back to the
// existing narrative/table/buttons rendering untouched when absent.
const ACTION_CATEGORY_LABEL: Record<NonNullable<AiResponse["actionCategory"]>, string> = {
  INFORMATION: "Information",
  RECOMMENDATION: "Recommendation",
  NAVIGATION: "Navigation",
  DRAFT: "Draft — needs review",
  USER_APPROVAL_REQUIRED: "Needs your approval",
  SAFETY_RESTRICTED: "Safety restricted — Lisa cannot act",
};

const CONFIDENCE_BADGE: Record<NonNullable<AiResponse["confidenceState"]>, Parameters<typeof StatusBadge>[0]["status"]> = {
  CONFIRMED: "COMPLIANT",
  PARTIAL_DATA: "REVIEW_REQUIRED",
  UNKNOWN: "INSUFFICIENT_DATA",
  NOT_CONFIGURED: "UNKNOWN",
};
const CONFIDENCE_LABEL: Record<NonNullable<AiResponse["confidenceState"]>, string> = {
  CONFIRMED: "Confirmed",
  PARTIAL_DATA: "Partial data",
  UNKNOWN: "Unknown",
  NOT_CONFIGURED: "Not configured",
};

function Bar({ label, percent }: { label: string; percent: number }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div className="ac-flex ac-justify-between ac-text-sm" style={{ marginBottom: 3 }}>
        <span>{label}</span>
        <span className="ac-text-muted">{percent}%</span>
      </div>
      <div style={{ width: "100%", height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
        <div style={{ width: `${percent}%`, height: "100%", background: "var(--ac-accent)" }} />
      </div>
    </div>
  );
}

const RISK_COLOR: Record<string, string> = {
  LOW: "var(--ac-status-compliant)",
  MEDIUM: "var(--ac-status-review)",
  HIGH: "var(--ac-status-non-compliant)",
};

// M-Lisa-UX — classification parsing over the EXISTING narrative[] string
// array. The engine (lib/mock/ai/engine.ts) has consistently prefixed lines
// with FACT:/INFERENCE:/RECOMMENDATION:/UNKNOWN:/SAFETY_REFUSAL: for many
// milestones now — this is a presentation-only enhancement that reads that
// existing convention and renders it as a visually distinct, labeled block
// instead of a flat paragraph. It does NOT change AiResponse's shape or
// touch any of the ~2,400 lines of engine.ts branches: a line with no
// recognized prefix still renders exactly as plain text, so nothing
// regresses for older/unlabeled branches.
type NarrativeKind = "FACT" | "INFERENCE" | "RECOMMENDATION" | "UNKNOWN" | "SAFETY_REFUSAL" | "PLAIN";

// Reuses the EXISTING StatusBadge status vocabulary (components/status/StatusBadge.tsx)
// rather than inventing new badge styling.
const KIND_BADGE_STATUS: Record<NarrativeKind, Parameters<typeof StatusBadge>[0]["status"] | null> = {
  FACT: "COMPLIANT",
  INFERENCE: "REVIEW_REQUIRED",
  RECOMMENDATION: "REVIEW_REQUIRED",
  UNKNOWN: "INSUFFICIENT_DATA",
  SAFETY_REFUSAL: "NON_COMPLIANT",
  PLAIN: null,
};
const KIND_LABEL: Record<NarrativeKind, string> = {
  FACT: "FACT",
  INFERENCE: "INFERENCE",
  RECOMMENDATION: "RECOMMENDATION",
  UNKNOWN: "UNKNOWN",
  SAFETY_REFUSAL: "SAFETY REFUSAL",
  PLAIN: "",
};

function classifyNarrativeLine(line: string): { kind: NarrativeKind; text: string } {
  const match = line.match(/^(FACT|INFERENCE|RECOMMENDATION|UNKNOWN|SAFETY_REFUSAL):\s*(.*)$/s);
  if (!match) return { kind: "PLAIN", text: line };
  return { kind: match[1] as NarrativeKind, text: match[2] };
}

export function AIResponseView({ response }: { response: AiResponse }) {
  const router = useRouter();
  const { addAuditEvent } = useMroState();

  function handleButtonClick(e: MouseEvent<HTMLAnchorElement>, href: string) {
    if (href.startsWith("/reports/") && response.suggestGenerateReport) {
      e.preventDefault();
      const { reportId, title, scope } = response.suggestGenerateReport;
      recordGeneratedReport({ id: reportId, title, generatedBy: `${AI_NAME} (Prototype)`, scope, generatedDate: new Date().toISOString().slice(0, 10), status: "READY" });
      addAuditEvent({
        actor: `${AI_NAME} (Prototype)`,
        actorRole: "AI Assistant",
        action: "report.generated",
        objectType: "Report",
        objectLabel: title,
        previousState: null,
        newState: "READY",
      });
      router.push(href);
    }
  }

  return (
    <div className="ac-card" style={{ borderColor: response.insufficientData ? "var(--ac-status-insufficient)" : undefined }}>
      <p className="ac-eyebrow" style={{ color: "var(--ac-status-insufficient)", marginBottom: 6 }}>
        {AI_NAME}&rsquo;s Analysis · Non-authoritative
      </p>

      {response.understood && (
        <div
          className="ac-text-sm"
          style={{
            margin: "0 0 12px",
            padding: "8px 10px",
            borderRadius: 6,
            border: "1px solid var(--ac-border)",
            background: "var(--ac-bg-elevated)",
          }}
        >
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{AI_NAME} Understood</p>
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", rowGap: 2, columnGap: 8 }}>
            <span className="ac-text-muted">Intent</span>
            <span>{response.understood.intent}</span>
            <span className="ac-text-muted">Scope</span>
            <span>{response.understood.scope}</span>
            <span className="ac-text-muted">Entities</span>
            <span>{response.understood.entities.join(", ")}</span>
            <span className="ac-text-muted">Data areas</span>
            <span>{response.understood.dataAreas}</span>
          </div>
        </div>
      )}

      <div className="ac-flex ac-items-center ac-gap-2" style={{ margin: "0 0 8px", flexWrap: "wrap" }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: 15 }}>{response.headline}</p>
        {response.priority && (() => {
          const pb = priorityBadge(response.priority);
          return <StatusBadge status={pb.status} label={`${pb.label} PRIORITY`} />;
        })()}
        {response.actionCategory && (
          <span className="ac-badge ac-badge-neutral">{ACTION_CATEGORY_LABEL[response.actionCategory]}</span>
        )}
        {response.confidenceState && (
          <StatusBadge status={CONFIDENCE_BADGE[response.confidenceState]} label={CONFIDENCE_LABEL[response.confidenceState]} />
        )}
      </div>

      {response.whatIFound && response.whatIFound.length > 0 && (
        <div style={{ margin: "0 0 10px" }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>What I Found</p>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {response.whatIFound.map((f, idx) => (
              <li key={idx} className="ac-text-sm ac-text-secondary">{f}</li>
            ))}
          </ul>
        </div>
      )}

      {response.whyItMatters && (
        <div style={{ margin: "0 0 10px" }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Why It Matters</p>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>{response.whyItMatters}</p>
        </div>
      )}

      <div style={{ margin: "0 0 10px" }}>
        {response.narrative.map((line, idx) => {
          const { kind, text } = classifyNarrativeLine(line);
          const badgeStatus = KIND_BADGE_STATUS[kind];
          if (kind === "PLAIN") {
            return (
              <p key={idx} className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>
                {text}
              </p>
            );
          }
          return (
            <div key={idx} className="ac-flex ac-gap-2" style={{ alignItems: "baseline", margin: "0 0 6px" }}>
              {badgeStatus && <StatusBadge status={badgeStatus} label={KIND_LABEL[kind]} />}
              <span className="ac-text-sm ac-text-secondary">{text}</span>
            </div>
          );
        })}
      </div>

      {response.kpis && response.kpis.length > 0 && (
        <div className="ac-grid-3" style={{ marginTop: 12, marginBottom: 4 }}>
          {response.kpis.map((k) => (
            <div key={k.label} className="ac-card" style={{ padding: "10px 12px" }}>
              <p className="ac-kpi-label">{k.label}</p>
              <p className="ac-kpi-value" style={{ fontSize: 18 }}>{k.value}</p>
            </div>
          ))}
        </div>
      )}

      {response.bars && response.bars.items.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 6 }}>{response.bars.title}</p>
          {response.bars.items.map((b) => (
            <Bar key={b.label} label={b.label} percent={b.percent} />
          ))}
        </div>
      )}

      {response.distribution && response.distribution.items.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 6 }}>{response.distribution.title}</p>
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            {response.distribution.items.map((d) => (
              <span key={d.label} className="ac-badge ac-badge-unknown" style={{ whiteSpace: "nowrap" }}>
                {d.label.replace(/_/g, " ")}: {d.count}
              </span>
            ))}
          </div>
        </div>
      )}

      {response.table && response.table.rows.length > 0 && (
        <div style={{ marginTop: 12, overflowX: "auto" }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 6 }}>{response.table.title}</p>
          <table className="ac-table">
            <thead>
              <tr>
                {response.table.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {response.table.rows.map((row, idx) => (
                <tr key={idx}>
                  {row.map((cell, ci) => (
                    <td key={ci}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {response.risks && response.risks.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 6 }}>Risk Areas</p>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {response.risks.map((r, idx) => (
              <li key={idx} className="ac-text-sm" style={{ marginBottom: 4 }}>
                <span style={{ color: RISK_COLOR[r.level] ?? undefined, fontWeight: 600 }}>[{r.level}]</span>{" "}
                {r.href ? <Link href={r.href}>{r.label}</Link> : r.label} — <span className="ac-text-muted">{r.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {response.complianceChain && (
        <div className="ac-flex ac-items-center ac-gap-2 ac-text-sm" style={{ marginTop: 12, flexWrap: "wrap" }}>
          {response.complianceChain.map((step, idx) => (
            <span key={step} className="ac-flex ac-items-center ac-gap-2">
              <span className="ac-badge ac-badge-unknown">{step}</span>
              {idx < response.complianceChain!.length - 1 && <span className="ac-text-muted">→</span>}
            </span>
          ))}
        </div>
      )}

      {response.recommendedActions && response.recommendedActions.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 6 }}>Recommended Actions</p>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {response.recommendedActions.map((a, idx) => (
              <li key={idx} className="ac-text-sm">{a}</li>
            ))}
          </ul>
        </div>
      )}

      {response.recommendedNextStep && (
        <div style={{ marginTop: 12 }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Recommended Next Step</p>
          <p className="ac-text-sm ac-text-secondary" style={{ margin: 0 }}>{response.recommendedNextStep}</p>
        </div>
      )}

      {response.dependencies && response.dependencies.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 4 }}>Dependencies</p>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {response.dependencies.map((d, idx) => (
              <li key={idx} className="ac-text-sm ac-text-secondary">{d}</li>
            ))}
          </ul>
        </div>
      )}

      {response.whoShouldAct && (
        <div className="ac-flex ac-gap-2" style={{ marginTop: 12, alignItems: "baseline" }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, margin: 0 }}>Who Should Act</p>
          <span className="ac-text-sm ac-text-secondary">{response.whoShouldAct}</span>
        </div>
      )}

      {response.relatedRecords && response.relatedRecords.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 6 }}>Related Records</p>
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            {response.relatedRecords.map((r) => (
              <Link key={r.href} href={r.href} className="ac-btn">
                {r.label}
              </Link>
            ))}
          </div>
        </div>
      )}

      {response.buttons && response.buttons.length > 0 && (
        <div className="ac-flex ac-gap-2" style={{ marginTop: 14, flexWrap: "wrap" }}>
          {response.buttons.map((b) => (
            <Link key={b.href} href={b.href} className="ac-btn" onClick={(e) => handleButtonClick(e, b.href)}>
              {b.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
