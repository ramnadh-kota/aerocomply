import { Breadcrumbs } from "@/components/layout/Breadcrumbs";

export default function SettingsPage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Settings" }]} />
      <h1 className="ac-h1">Settings</h1>
      <p className="ac-subtitle" style={{ marginBottom: 20 }}>Account, roles, and integration settings.</p>
      <div className="ac-card">
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          Not yet built in M0.5. Real RBAC/roles already exist in the M0 backend (see{" "}
          <span className="ac-mono">backend/app/core/permissions.py</span>) — this screen will surface
          them once the prototype is wired to the real API in a later milestone.
        </p>
      </div>
    </div>
  );
}
