"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { COMPANY_NAME, AI_NAME } from "@/lib/brand";

// Persisted so the tour only auto-appears once per browser. Re-launchable
// any time from the Topbar's Help panel (see HelpPanel.tsx), which is why
// this component also accepts a controlled `forceOpen`/`onClose` pair
// rather than only managing its own first-visit state.
export const ONBOARDING_SEEN_KEY = "kota-aerospace-onboarding-seen";

// VT-ABC (ac-1) is the hero aircraft used across the guided walkthrough —
// see the comment above `aircraft` in lib/mock/aircraft.ts.
const DEMO_AIRCRAFT_ID = "ac-1";
const DEMO_AIRCRAFT_REG = "VT-ABC";

interface TourStep {
  title: string;
  body: string;
  why?: string;
}

const STEPS: TourStep[] = [
  {
    title: `Welcome to ${COMPANY_NAME}`,
    body: "This is an aerospace maintenance, compliance, and operational intelligence platform — one system spanning the fleet, work orders, regulatory compliance, and finance/procurement.",
    why: "Everything in the app reads from the same underlying data, so a status you see in one module (like a defect) is consistent everywhere else it's referenced.",
  },
  {
    title: "The sidebar follows the MRO lifecycle",
    body: "Sections are grouped in the order maintenance actually flows: Fleet (aircraft/engines/components) → Compliance (regulations/assessments/evidence) → Maintenance (planning through release) → Governance (audit/reports/org).",
    why: "If you're not sure where something lives, think about which stage of the lifecycle it belongs to.",
  },
  {
    title: "Opening an aircraft",
    body: "Go to Fleet → Aircraft and pick a tail number to see its detail page: current registration, installed engines/components, open work orders, defects, and regulatory assessments in one place.",
  },
  {
    title: "Work orders, evidence, and inspections",
    body: "A work order tracks one unit of maintenance work. Required Inspection Items (RII) need an independent inspector — never the technician who performed the work. An Evidence Gate blocks release until required proof-of-work is submitted and accepted by a reviewer, not just uploaded.",
    why: "These two checks are enforced the same way everywhere they're read (Task Card, Control Center, Automation Queue, and Lisa's answers) — there's no second, inconsistent copy of the rule.",
  },
  {
    title: "Release readiness and TAT",
    body: "Release Readiness (Maintenance → Release Readiness) rolls up every blocker — material, qualification, inspection, evidence, overdue deferred items — into one status per work order. TAT (turnaround time) flags work orders at risk of missing their due date because of those same open blockers.",
    why: "TAT is deliberately not a prediction — it only reads real due dates and real open blockers, never a guessed duration.",
  },
  {
    title: `Ask ${AI_NAME}`,
    body: `${AI_NAME} is the platform's aviation intelligence assistant, available from the "Ask ${AI_NAME}" button in the top bar. Ask it things like "what's blocking release on WO-1042?" or "what are the fleet-wide release blockers?"`,
    why: `${AI_NAME} answers from the same data and rules you see in the UI — it doesn't replace approved maintenance data or human inspection authority.`,
  },
  {
    title: "Try it on the demo aircraft",
    body: `${DEMO_AIRCRAFT_REG} is the aircraft used throughout this walkthrough. Jump straight to its detail page to see the concepts above in context.`,
  },
];

interface WelcomeTourProps {
  /** Controlled open state from HelpPanel's "Replay tour" action. When
   * omitted, the component manages its own first-visit auto-open. */
  forceOpen?: boolean;
  onClose?: () => void;
}

export function WelcomeTour({ forceOpen, onClose }: WelcomeTourProps = {}) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const router = useRouter();

  useEffect(() => {
    if (forceOpen) return;
    try {
      const seen = window.localStorage.getItem(ONBOARDING_SEEN_KEY);
      if (!seen) {
        setOpen(true);
      }
    } catch {
      // localStorage unavailable (private mode, etc.) — skip auto-open
      // rather than risk throwing on every render.
    }
  }, [forceOpen]);

  useEffect(() => {
    if (forceOpen) {
      setStep(0);
      setOpen(true);
    }
  }, [forceOpen]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function close() {
    setOpen(false);
    setStep(0);
    try {
      window.localStorage.setItem(ONBOARDING_SEEN_KEY, "1");
    } catch {
      // best-effort persistence only
    }
    onClose?.();
  }

  function goToDemoAircraft() {
    close();
    router.push(`/aircraft/${DEMO_AIRCRAFT_ID}`);
  }

  if (!open) return null;

  const isLast = step === STEPS.length - 1;
  const isFirst = step === 0;
  const current = STEPS[step];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="ac-tour-title"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 16,
      }}
      onClick={close}
    >
      <div className="ac-card" style={{ maxWidth: 460, width: "100%" }} onClick={(e) => e.stopPropagation()}>
        <p className="ac-eyebrow" style={{ marginBottom: 6 }}>
          Welcome tour · Step {step + 1} of {STEPS.length}
        </p>
        <h2 id="ac-tour-title" className="ac-h1" style={{ fontSize: 20, marginBottom: 10 }}>
          {current.title}
        </h2>
        <p className="ac-text-sm" style={{ marginBottom: current.why ? 8 : 16 }}>
          {current.body}
        </p>
        {current.why && (
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 16 }}>
            Why it matters: {current.why}
          </p>
        )}

        <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 14 }}>
          {STEPS.map((_, i) => (
            <span
              key={i}
              aria-hidden="true"
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: i === step ? "var(--ac-accent, var(--ac-text-primary))" : "var(--ac-border)",
              }}
            />
          ))}
        </div>

        <div className="ac-flex ac-items-center ac-gap-2" style={{ justifyContent: "space-between" }}>
          <button className="ac-btn" style={{ padding: "6px 12px", fontSize: 13 }} onClick={close}>
            Skip
          </button>
          <div className="ac-flex ac-gap-2">
            {!isFirst && (
              <button className="ac-btn" style={{ padding: "6px 12px", fontSize: 13 }} onClick={() => setStep((s) => s - 1)}>
                Back
              </button>
            )}
            {!isLast && (
              <button className="ac-btn ac-btn-primary" style={{ padding: "6px 12px", fontSize: 13 }} onClick={() => setStep((s) => s + 1)}>
                Next
              </button>
            )}
            {isLast && (
              <button className="ac-btn ac-btn-primary" style={{ padding: "6px 12px", fontSize: 13 }} onClick={goToDemoAircraft}>
                Open {DEMO_AIRCRAFT_REG}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
