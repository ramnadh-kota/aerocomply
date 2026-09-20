// Shared page-header primitive. Consolidates the "Breadcrumbs + ac-section-header
// (h1 title / subtitle / optional actions)" pattern that was hand-rolled with
// small variations across the Dashboard, Drones list, Drone detail, Findings
// detail, and Maintenance pages (see M21.3 audit for file:line evidence).
// Presentation-only: renders existing globals.css classes (ac-section-header,
// ac-h1, ac-subtitle, ac-eyebrow) and the existing Breadcrumbs component --
// introduces no new visual language.

import type { ReactNode } from "react";
import { Breadcrumbs, type Crumb } from "./Breadcrumbs";

export function PageHeader({
  breadcrumbs,
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  breadcrumbs?: Crumb[];
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <>
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="ac-section-header">
        <div>
          {eyebrow && (
            <p className="ac-eyebrow" style={{ margin: 0 }}>
              {eyebrow}
            </p>
          )}
          <h1 className="ac-h1">{title}</h1>
          {subtitle && <p className="ac-subtitle">{subtitle}</p>}
        </div>
        {actions && (
          <div className="ac-flex ac-gap-2 ac-items-center" style={{ flexWrap: "wrap" }}>
            {actions}
          </div>
        )}
      </div>
    </>
  );
}
