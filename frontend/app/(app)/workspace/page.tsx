import { Breadcrumbs } from "@/components/layout/Breadcrumbs";

export default function WorkspacePage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Workspace" }]} />
      <h1 className="ac-h1">Workspace</h1>
      <p className="ac-subtitle" style={{ marginBottom: 20 }}>Saved views, watchlists, and team workflows.</p>
      <div className="ac-card">
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          Not yet built in M0.5. This prototype focuses on the core compliance-intelligence loop —
          Dashboard, Aircraft, Engines, Components, Regulations, Assessments, Evidence, and Audit
          Trail.
        </p>
      </div>
    </div>
  );
}
