"use client";

import { useState } from "react";
import { PERMISSION_MODULES, type ModulePermission, type PermissionLevel, type Role } from "@/lib/mock/roles";

const LEVELS: PermissionLevel[] = ["NONE", "VIEW", "EDIT", "APPROVE"];

export interface RoleFormValue {
  name: string;
  description: string;
  scope: string;
  permissions: ModulePermission[];
}

/** Shared Add/Edit Role form — reused by /organization/roles/new and the
 * edit mode on /organization/roles/[id] so there is exactly one role
 * editing UI, not two. Session-only prototype: the caller is responsible
 * for persisting via lib/mock/roles.ts's createRole()/updateRole(). */
export function RoleForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Role;
  submitLabel: string;
  onSubmit: (value: RoleFormValue) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [scope, setScope] = useState(initial?.scope ?? "Fleet-wide");
  const [permissions, setPermissions] = useState<ModulePermission[]>(
    initial?.permissions ?? PERMISSION_MODULES.map((m) => ({ module: m, level: "NONE" as PermissionLevel }))
  );

  function setLevel(mod: string, level: PermissionLevel) {
    setPermissions((prev) => prev.map((p) => (p.module === mod ? { ...p, level } : p)));
  }

  const canSubmit = name.trim().length > 0 && description.trim().length > 0;

  return (
    <div className="ac-card">
      <div className="ac-flex ac-flex-col ac-gap-3" style={{ marginBottom: 16 }}>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-muted">Role Name</span>
          <input className="ac-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Line Maintenance Supervisor" aria-label="Role name" />
        </label>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-muted">Description</span>
          <textarea className="ac-input" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} aria-label="Role description" />
        </label>
        <label className="ac-flex ac-flex-col ac-gap-2">
          <span className="ac-text-sm ac-text-muted">Scope</span>
          <input className="ac-input" style={{ width: 260 }} value={scope} onChange={(e) => setScope(e.target.value)} placeholder="e.g. Fleet-wide, Assigned aircraft only" aria-label="Role scope" />
        </label>
      </div>

      <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Module Access</p>
      <div className="ac-card" style={{ padding: 0, marginBottom: 16 }}>
        <table className="ac-table">
          <thead><tr><th>Module</th><th>Access Level</th></tr></thead>
          <tbody>
            {permissions.map((p) => (
              <tr key={p.module}>
                <td style={{ fontWeight: 600 }}>{p.module}</td>
                <td>
                  <select className="ac-input" style={{ width: 160 }} value={p.level} onChange={(e) => setLevel(p.module, e.target.value as PermissionLevel)} aria-label={`${p.module} access level`}>
                    {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="ac-flex ac-gap-2">
        <button className="ac-btn ac-btn-primary" disabled={!canSubmit} onClick={() => onSubmit({ name: name.trim(), description: description.trim(), scope: scope.trim() || "Fleet-wide", permissions })}>
          {submitLabel}
        </button>
        <button className="ac-btn" onClick={onCancel}>Cancel</button>
      </div>
      <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8, marginBottom: 0 }}>
        Prototype only — this updates in-memory demo data for this session; no permission here is enforced by the application, and nothing is persisted past a reload.
      </p>
    </div>
  );
}
