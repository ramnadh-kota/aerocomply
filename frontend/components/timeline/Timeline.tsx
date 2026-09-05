import type { ReactNode } from "react";

export interface TimelineEntry {
  id: string;
  date: string; // pre-formatted display string
  title: ReactNode;
  detail?: ReactNode;
  accent?: "default" | "highlight";
}

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {entries.map((entry, idx) => (
        <li key={entry.id} style={{ display: "flex", gap: "var(--ac-space-4)" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 12, flexShrink: 0 }}>
            <span
              aria-hidden="true"
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                marginTop: 4,
                background: entry.accent === "highlight" ? "var(--ac-accent)" : "var(--ac-text-muted)",
                flexShrink: 0,
              }}
            />
            {idx < entries.length - 1 && <span aria-hidden="true" style={{ flex: 1, width: 1, background: "var(--ac-border)" }} />}
          </div>
          <div style={{ paddingBottom: "var(--ac-space-5)", flex: 1 }}>
            <div className="ac-text-sm ac-text-muted ac-mono">{entry.date}</div>
            <div style={{ fontWeight: 600, marginTop: 2 }}>{entry.title}</div>
            {entry.detail && <div className="ac-text-sm ac-text-secondary" style={{ marginTop: 2 }}>{entry.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}
