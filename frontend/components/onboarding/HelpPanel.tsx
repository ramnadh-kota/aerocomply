"use client";

import { useEffect, useState } from "react";
import { WelcomeTour } from "./WelcomeTour";
import { AI_NAME } from "@/lib/brand";

// Definitions here are written to match what the code actually does (see
// lib/mock/ai/analytics.ts), not generic textbook aviation definitions —
// e.g. RII exclusion, the Evidence Gate's ACCEPTED-not-just-SUBMITTED
// requirement, and TAT's non-predictive due-date/blocker classification.
interface GlossaryEntry {
  term: string;
  definition: string;
}

const GLOSSARY: GlossaryEntry[] = [
  {
    term: "TAT (Turnaround Time)",
    definition:
      "A work order's turnaround-risk status: ON_TRACK, AT_RISK, DELAYED, or UNKNOWN. It's read directly from the due date and the same release-readiness blockers shown elsewhere — never a predicted duration or confidence score, since there's no historical-duration data to support one.",
  },
  {
    term: "RII vs. regular inspection",
    definition:
      "A Required Inspection Item (RII) needs an independent inspector — the technician who performed the work can never be listed as an eligible inspector for their own work order, no matter how qualified. A regular inspection has no such exclusion.",
  },
  {
    term: "Evidence Gate",
    definition:
      "Blocks release of a work order until required execution evidence (photos/proof-of-work) is not just submitted, but ACCEPTED by a reviewer. A technician's own upload can't clear the gate by itself — it stays FAIL until someone else accepts it.",
  },
  {
    term: "Release Readiness",
    definition:
      "The single rollup of every open blocker for a work order — material shortages, missing qualification, incomplete inspection, an open Evidence Gate, or an overdue deferred item on the aircraft — into one READY / BLOCKED / UNKNOWN status.",
  },
  {
    term: "MEL (Deferred Items)",
    definition:
      "A deferred item recorded against an aircraft with a due date and, once resolved, a linked evidence reference and corrective work order — it can't be closed without both. Overdue deferred items are one of the inputs to Release Readiness and AOG status.",
  },
  {
    term: "Technician Authorization",
    definition:
      "A distinct AUTHORIZED / NOT_AUTHORIZED / UNKNOWN check for whether a technician may work a specific work order — separate from the ranked recommendation of who should be assigned. Aircraft-type qualification data isn't populated in this demo, so that reason always surfaces as UNKNOWN rather than being silently ignored.",
  },
  {
    term: "AOG (Aircraft on Ground)",
    definition:
      "An aircraft's operational status when it has an open HIGH or CRITICAL defect. AOG Recovery pulls together the same deferred items and release blockers used elsewhere into one recovery view, rather than a separate calculation.",
  },
];

export function HelpPanel() {
  const [open, setOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <div style={{ position: "relative" }}>
      <button
        className="ac-btn"
        aria-label="Help"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        style={{ padding: "8px 10px" }}
        title="Help & glossary"
      >
        <span aria-hidden="true">?</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Help"
          className="ac-card"
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            width: 360,
            maxHeight: "70vh",
            overflowY: "auto",
            zIndex: 60,
          }}
        >
          <div className="ac-flex ac-items-center" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <p className="ac-eyebrow" style={{ margin: 0 }}>
              Help
            </p>
            <button className="ac-btn" style={{ padding: "2px 8px", fontSize: 12 }} onClick={() => setOpen(false)} aria-label="Close help">
              ✕
            </button>
          </div>

          <button
            className="ac-btn ac-btn-primary"
            style={{ width: "100%", padding: "8px 12px", fontSize: 13, marginBottom: 14 }}
            onClick={() => {
              setOpen(false);
              setTourOpen(true);
            }}
          >
            Replay welcome tour
          </button>

          <p className="ac-text-sm" style={{ marginBottom: 8 }}>
            Not sure what a term means? A quick glossary of the trickier concepts in the app:
          </p>

          {GLOSSARY.map((g) => (
            <div key={g.term} style={{ marginBottom: 12 }}>
              <p className="ac-text-sm" style={{ fontWeight: 600, margin: "0 0 2px" }}>
                {g.term}
              </p>
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                {g.definition}
              </p>
            </div>
          ))}

          <hr className="ac-divider" />
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Still stuck? Ask {AI_NAME} from the top bar — she reads the same data and rules described above.
          </p>
        </div>
      )}

      <WelcomeTour forceOpen={tourOpen} onClose={() => setTourOpen(false)} />
    </div>
  );
}
