"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { aircraft, currentRegistration } from "@/lib/mock/aircraft";
import { engines } from "@/lib/mock/engines";
import { regulatoryRequirements } from "@/lib/mock/regulations";
import { assessments } from "@/lib/mock/assessments";

interface SearchResult {
  kind: "Aircraft" | "Engine" | "Requirement" | "Assessment";
  primary: string;
  secondary: string;
  href: string;
}

function buildResults(query: string): SearchResult[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const results: SearchResult[] = [];

  for (const a of aircraft) {
    const reg = currentRegistration(a);
    if (reg.toLowerCase().includes(q) || a.msn.toLowerCase().includes(q)) {
      results.push({ kind: "Aircraft", primary: reg, secondary: `MSN ${a.msn}`, href: `/aircraft/${a.id}` });
    }
  }

  for (const e of engines) {
    if (e.serialNumber.toLowerCase().replace("sn ", "").includes(q.replace("sn ", ""))) {
      results.push({ kind: "Engine", primary: e.serialNumber, secondary: "Engine", href: `/engines/${e.id}` });
    }
  }

  for (const r of regulatoryRequirements) {
    if (r.requirementNumber.toLowerCase().includes(q) || r.description.toLowerCase().includes(q)) {
      results.push({ kind: "Requirement", primary: r.requirementNumber, secondary: "Regulatory Requirement", href: `/regulations/${r.id}` });
    }
  }

  for (const asmt of assessments) {
    if (asmt.id.toLowerCase().includes(q)) {
      results.push({ kind: "Assessment", primary: asmt.id, secondary: asmt.systemResult, href: `/assessments/${asmt.id}` });
    }
  }

  return results.slice(0, 8);
}

export function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => buildResults(query), [query]);

  function go(href: string) {
    setOpen(false);
    setQuery("");
    router.push(href);
  }

  return (
    <div style={{ position: "relative", flex: 1, maxWidth: 420 }}>
      <input
        ref={inputRef}
        type="search"
        className="ac-input"
        placeholder="Search aircraft, registration, MSN, engine SN, requirement, assessment…"
        aria-label="Global search"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && query.trim() && (
        <div
          role="listbox"
          className="ac-card"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            zIndex: 50,
            padding: "var(--ac-space-2)",
            maxHeight: 360,
            overflowY: "auto",
          }}
        >
          {results.length === 0 && <div className="ac-text-sm ac-text-muted" style={{ padding: 8 }}>No results for &ldquo;{query}&rdquo;</div>}
          {results.map((r, idx) => (
            <button
              key={idx}
              role="option"
              aria-selected={false}
              onClick={() => go(r.href)}
              className="ac-w-full"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                textAlign: "left",
                padding: "8px 10px",
                borderRadius: 6,
                border: "none",
                background: "transparent",
              }}
              onMouseDown={(e) => e.preventDefault()}
            >
              <span>
                <span className="ac-eyebrow" style={{ marginRight: 8 }}>
                  {r.kind}
                </span>
                {r.primary}
              </span>
              <span className="ac-text-sm ac-text-muted">{r.secondary}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
