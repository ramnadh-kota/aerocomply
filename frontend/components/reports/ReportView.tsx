"use client";

import Link from "next/link";
import type { ReportData } from "@/lib/mock/reports";

function renderSectionHtml(s: ReportData["sections"][number]): string {
  let html = `<h2>${s.heading}</h2>`;
  if (s.kpis?.length) {
    html += `<div class="kpis">${s.kpis.map((k) => `<div class="kpi"><div class="kpi-label">${k.label}</div><div class="kpi-value">${k.value}</div></div>`).join("")}</div>`;
  }
  if (s.body.length) html += s.body.map((b) => `<p>${b}</p>`).join("");
  if (s.bars?.length) {
    html += s.bars.map((b) => `<div class="bar-row"><span>${b.label}</span><div class="bar-track"><div class="bar-fill" style="width:${b.percent}%"></div></div><span>${b.percent}%</span></div>`).join("");
  }
  if (s.distribution?.length) {
    html += `<p>${s.distribution.map((d) => `${d.label.replace(/_/g, " ")}: ${d.count}`).join(" · ")}</p>`;
  }
  if (s.table?.rows.length) {
    html += `<table><thead><tr>${s.table.columns.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${s.table.rows
      .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
      .join("")}</tbody></table>`;
  }
  if (s.chain?.length) html += `<p class="chain">${s.chain.join(" → ")}</p>`;
  return html;
}

function buildStandaloneHtml(report: ReportData): string {
  const style = `
    body { font-family: -apple-system, Segoe UI, Arial, sans-serif; background:#0b0f16; color:#e6e9ef; padding:32px; max-width:900px; margin:0 auto; }
    h1 { font-size:22px; margin-bottom:4px; }
    h2 { font-size:15px; margin-top:28px; border-bottom:1px solid #2a3141; padding-bottom:6px; }
    p { font-size:13px; line-height:1.5; color:#c3c9d6; }
    .meta { font-size:12px; color:#8b93a5; margin-bottom:20px; }
    .kpis { display:flex; gap:12px; flex-wrap:wrap; margin:10px 0; }
    .kpi { background:#131926; border:1px solid #2a3141; border-radius:8px; padding:10px 14px; min-width:120px; }
    .kpi-label { font-size:11px; color:#8b93a5; text-transform:uppercase; }
    .kpi-value { font-size:18px; font-weight:700; margin-top:4px; }
    table { width:100%; border-collapse:collapse; margin:10px 0; font-size:12px; }
    th, td { text-align:left; padding:6px 8px; border-bottom:1px solid #2a3141; }
    .bar-row { display:flex; align-items:center; gap:8px; font-size:12px; margin:4px 0; }
    .bar-track { flex:1; height:6px; background:#2a3141; border-radius:4px; overflow:hidden; }
    .bar-fill { height:100%; background:#3d8bff; }
    .chain { font-family:monospace; }
    .footer { margin-top:32px; font-size:11px; color:#6b7c9c; border-top:1px solid #2a3141; padding-top:12px; }
  `;
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${report.title}</title><style>${style}</style></head><body>
    <h1>AeroComply — ${report.title}</h1>
    <p class="meta">Scope: ${report.scope} · Generated: ${report.generatedDate}</p>
    ${report.sections.map(renderSectionHtml).join("")}
    <p class="footer">This is a prototype report generated from AeroComply demo data. AI-generated sections are non-authoritative and require human review. Not backend-persisted.</p>
  </body></html>`;
}

export function ReportView({ report }: { report: ReportData }) {
  function handleDownload() {
    const html = buildStandaloneHtml(report);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report.id}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="ac-card" style={{ marginBottom: 16 }}>
        <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 10 }}>
          <div>
            <p className="ac-eyebrow" style={{ marginBottom: 4 }}>AeroComply · Report</p>
            <h1 className="ac-h1" style={{ margin: 0 }}>{report.title}</h1>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
              Scope: {report.scope} · Generated {report.generatedDate}
            </p>
          </div>
          <div className="ac-flex ac-gap-2">
            <button className="ac-btn" onClick={handleDownload}>Download HTML</button>
            <button className="ac-btn" onClick={() => window.print()}>Print</button>
            <Link href="/reports" className="ac-btn">Back</Link>
          </div>
        </div>
      </div>

      {report.sections.map((s) => (
        <section key={s.heading} className="ac-card" style={{ marginBottom: 12 }}>
          <h2 className="ac-h2" style={{ marginBottom: 8 }}>{s.heading}</h2>

          {s.kpis && s.kpis.length > 0 && (
            <div className="ac-grid-3" style={{ marginBottom: 10 }}>
              {s.kpis.map((k) => (
                <div key={k.label} className="ac-card" style={{ padding: "10px 12px" }}>
                  <p className="ac-kpi-label">{k.label}</p>
                  <p className="ac-kpi-value" style={{ fontSize: 18 }}>{k.value}</p>
                </div>
              ))}
            </div>
          )}

          {s.body.map((line, idx) => (
            <p key={idx} className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 6px" }}>{line}</p>
          ))}

          {s.bars && s.bars.length > 0 && (
            <div style={{ marginTop: 6 }}>
              {s.bars.map((b) => (
                <div key={b.label} style={{ marginBottom: 8 }}>
                  <div className="ac-flex ac-justify-between ac-text-sm" style={{ marginBottom: 3 }}>
                    <span>{b.label}</span>
                    <span className="ac-text-muted">{b.percent}%</span>
                  </div>
                  <div style={{ width: "100%", height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
                    <div style={{ width: `${b.percent}%`, height: "100%", background: "var(--ac-accent)" }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {s.distribution && s.distribution.length > 0 && (
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
              {s.distribution.map((d) => (
                <span key={d.label} className="ac-badge ac-badge-unknown">{d.label.replace(/_/g, " ")}: {d.count}</span>
              ))}
            </div>
          )}

          {s.table && s.table.rows.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="ac-table">
                <thead>
                  <tr>{s.table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                </thead>
                <tbody>
                  {s.table.rows.map((row, idx) => (
                    <tr key={idx}>{row.map((cell, ci) => <td key={ci}>{cell}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {s.chain && (
            <div className="ac-flex ac-items-center ac-gap-2 ac-text-sm" style={{ flexWrap: "wrap" }}>
              {s.chain.map((step, idx) => (
                <span key={step} className="ac-flex ac-items-center ac-gap-2">
                  <span className="ac-badge ac-badge-unknown">{step}</span>
                  {idx < s.chain!.length - 1 && <span className="ac-text-muted">→</span>}
                </span>
              ))}
            </div>
          )}
        </section>
      ))}

      <p className="ac-text-sm ac-text-muted">
        Prototype limitation: this report is generated client-side from in-memory demo data. Regenerating produces
        the same result unless the underlying mock data changes; nothing here is backend-persisted.
      </p>
    </div>
  );
}
