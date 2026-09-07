// M0.5 — Integration Hub catalog.
//
// Honesty invariant: this file describes an INGESTION ARCHITECTURE that
// KOTA'S AEROSPACE is designed around, not a live integration marketplace.
// Zero real third-party connections exist anywhere in this repository (no
// integration client code, no OAuth flows, no sync jobs). Every entry below
// MUST be NOT_CONFIGURED, except the identity/auth entry, which mirrors the
// precise language already used on the Settings > Integrations tab
// (frontend/app/(app)/settings/page.tsx): a real backend implementation
// exists (backend/app/core/security.py, backend/app/services/auth_service.py)
// but is not running in this environment (no Postgres, no backend/.env).
//
// Do not add CONNECTED, SYNCING, or a real vendor name to this file. Do not
// name specific competitor products — categories use generic descriptions
// ("your MRO system") because this is an abstraction layer, not a fake
// marketplace of named partners.

export type IntegrationCategory =
  | "MRO"
  | "ERP"
  | "Procurement"
  | "HR"
  | "Identity"
  | "Regulatory"
  | "Documents"
  | "Aircraft Data"
  | "Notifications";

export type IntegrationStatus = "CONNECTED" | "NOT_CONFIGURED" | "ERROR" | "SYNCING";

export type SyncMethod = "REST" | "Webhook" | "CSV" | "SFTP" | "Scheduled" | "Event-driven";

export interface Integration {
  id: string;
  name: string;
  category: IntegrationCategory;
  status: IntegrationStatus;
  /** ISO date string, or undefined for "Never". */
  lastSync?: string;
  recordCount?: number;
  syncMethod?: SyncMethod;
  description: string;
  /** Present only when a real backend implementation exists but isn't running here. */
  implementationNote?: string;
}

export const integrations: Integration[] = [
  // --- MRO ---
  {
    id: "int-mro-generic",
    name: "MRO System (AMOS / TRAX / Maintenix, or equivalent)",
    category: "MRO",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description:
      "Pulls work orders, task cards, and maintenance program data from your existing MRO system of record via its REST API, so KOTA'S AEROSPACE can overlay compliance intelligence without becoming a second system of record.",
  },
  {
    id: "int-mro-legacy-export",
    name: "MRO Legacy Export Feed",
    category: "MRO",
    status: "NOT_CONFIGURED",
    syncMethod: "CSV",
    description:
      "Batch CSV ingestion for MRO systems without a modern API — scheduled drop-folder or manual upload of work order and task card exports.",
  },

  // --- ERP ---
  {
    id: "int-erp-generic",
    name: "ERP System",
    category: "ERP",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description:
      "Synchronizes finance, inventory valuation, and cost-center data from your ERP so MRO Finance figures reconcile with your general ledger.",
  },
  {
    id: "int-erp-sftp",
    name: "ERP Batch Extract",
    category: "ERP",
    status: "NOT_CONFIGURED",
    syncMethod: "SFTP",
    description:
      "Nightly SFTP file drop for ERP environments that prefer scheduled batch extracts over live API calls.",
  },

  // --- Procurement ---
  {
    id: "int-procurement-generic",
    name: "Procurement / Supplier Portal",
    category: "Procurement",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description:
      "Connects purchase orders, vendor catalogs, and parts pricing from your procurement platform to power Parts Search and Vendor Intelligence with live data instead of mock records.",
  },

  // --- HR ---
  {
    id: "int-hr-generic",
    name: "HR / Workforce System",
    category: "HR",
    status: "NOT_CONFIGURED",
    syncMethod: "Scheduled",
    description:
      "Syncs technician certifications, licenses, and shift rosters from your HR or workforce management system to keep Technicians and Task Card assignment accurate.",
  },

  // --- Identity ---
  {
    id: "int-identity-auth",
    name: "Email + Password (JWT / Argon2)",
    category: "Identity",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description:
      "Core authentication for KOTA'S AEROSPACE user accounts — JWT session issuance with Argon2 password hashing.",
    implementationNote:
      "Backend Implemented — Not Running. A real, unit-tested implementation exists in backend/app/core/security.py and backend/app/services/auth_service.py. It is not connected in this environment because no PostgreSQL instance is running and no backend/.env is present (only .env.example).",
  },
  {
    id: "int-identity-sso",
    name: "SSO / SAML Identity Provider",
    category: "Identity",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description:
      "Enterprise single sign-on via SAML or OIDC, so organizations can provision and authenticate users through their own identity provider instead of local passwords.",
  },

  // --- Regulatory ---
  {
    id: "int-reg-faa",
    name: "FAA Dynamic Regulatory System",
    category: "Regulatory",
    status: "NOT_CONFIGURED",
    syncMethod: "Scheduled",
    description:
      "Scheduled feed of newly published FAA Airworthiness Directives and Special Airworthiness Information Bulletins into the Regulations module.",
  },
  {
    id: "int-reg-easa",
    name: "EASA ADs & SIBs Feed",
    category: "Regulatory",
    status: "NOT_CONFIGURED",
    syncMethod: "Scheduled",
    description:
      "Scheduled feed of EASA Airworthiness Directives and Safety Information Bulletins into the Regulations module.",
  },
  {
    id: "int-reg-ukcaa",
    name: "UK CAA Mandate Feed",
    category: "Regulatory",
    status: "NOT_CONFIGURED",
    syncMethod: "Scheduled",
    description: "Scheduled feed of UK CAA airworthiness mandates into the Regulations module.",
  },
  {
    id: "int-reg-dgca",
    name: "DGCA CAR Notices Feed",
    category: "Regulatory",
    status: "NOT_CONFIGURED",
    syncMethod: "Scheduled",
    description:
      "Scheduled feed of Directorate General of Civil Aviation (India) Civil Aviation Requirements notices into the Regulations module.",
  },
  {
    id: "int-reg-casa",
    name: "CASA AD Feed",
    category: "Regulatory",
    status: "NOT_CONFIGURED",
    syncMethod: "Scheduled",
    description:
      "Scheduled feed of Civil Aviation Safety Authority (Australia) Airworthiness Directives into the Regulations module.",
  },

  // --- Documents ---
  {
    id: "int-doc-storage",
    name: "Document / Evidence Storage (S3-compatible)",
    category: "Documents",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description:
      "Object storage for evidence records, certificates, and Document Library files — designed against any S3-compatible API so it can point at your existing storage rather than requiring a new one.",
  },

  // --- Aircraft Data ---
  {
    id: "int-acms",
    name: "Aircraft Data / ACMS-IoT Feed",
    category: "Aircraft Data",
    status: "NOT_CONFIGURED",
    syncMethod: "Event-driven",
    description:
      "Event-driven ingestion from Aircraft Condition Monitoring Systems and other onboard IoT telemetry, feeding component life and Fleet Health tracking with real usage data instead of manually entered hours/cycles.",
  },
  {
    id: "int-fleet-data",
    name: "Fleet / Aircraft Master Data",
    category: "Aircraft Data",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description:
      "Aircraft registration, configuration, and component master data synced from your fleet management system of record.",
  },

  // --- Notifications ---
  {
    id: "int-notify-email",
    name: "Outbound Email (SMTP / API)",
    category: "Notifications",
    status: "NOT_CONFIGURED",
    syncMethod: "REST",
    description: "Delivers AOG, TAT, and regulatory-update alerts by email via SMTP or a transactional email API.",
  },
  {
    id: "int-notify-webhook",
    name: "Notification Provider (Webhook / SMS)",
    category: "Notifications",
    status: "NOT_CONFIGURED",
    syncMethod: "Webhook",
    description:
      "Pushes alerts to Slack, Teams, or SMS gateways via outbound webhook so notifications reach the tools your team already watches.",
  },
];

export function integrationsByCategory(): { category: IntegrationCategory; items: Integration[] }[] {
  const order: IntegrationCategory[] = [
    "MRO",
    "ERP",
    "Procurement",
    "HR",
    "Identity",
    "Regulatory",
    "Documents",
    "Aircraft Data",
    "Notifications",
  ];
  return order
    .map((category) => ({ category, items: integrations.filter((i) => i.category === category) }))
    .filter((g) => g.items.length > 0);
}
