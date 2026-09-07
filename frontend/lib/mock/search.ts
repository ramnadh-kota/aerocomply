// Global search index. Pulls directly from existing mock data modules — no
// fabricated records. Each SearchResult links to a real detail page for an
// object that actually exists in the seed data.

import { aircraft, currentRegistration } from "./aircraft";
import { engines } from "./engines";
import { components, componentInstances, componentForInstance } from "./components";
import { parts } from "./parts";
import { workOrders } from "./workOrders";
import { technicians } from "./technicians";
import { vendors, purchaseOrders } from "./procurement";
import { regulatoryRequirements } from "./regulations";

export type SearchResultType =
  | "Aircraft"
  | "Engine"
  | "Component"
  | "Part"
  | "WorkOrder"
  | "Technician"
  | "Vendor"
  | "PurchaseOrder"
  | "Regulation";

export interface SearchResult {
  type: SearchResultType;
  id: string;
  title: string;
  subtitle: string;
  href: string;
}

function includesQ(value: string | null | undefined, q: string): boolean {
  return !!value && value.toLowerCase().includes(q);
}

export function searchAll(query: string): SearchResult[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const results: SearchResult[] = [];

  for (const a of aircraft) {
    const reg = currentRegistration(a);
    if (includesQ(reg, q) || includesQ(a.msn, q)) {
      results.push({
        type: "Aircraft",
        id: a.id,
        title: reg,
        subtitle: `MSN ${a.msn}`,
        href: `/aircraft/${a.id}`,
      });
    }
  }

  for (const e of engines) {
    if (includesQ(e.serialNumber, q)) {
      results.push({
        type: "Engine",
        id: e.id,
        title: e.serialNumber,
        subtitle: "Engine",
        href: `/engines/${e.id}`,
      });
    }
  }

  for (const ci of componentInstances) {
    const component = componentForInstance(ci.id);
    if (!component) continue;
    if (includesQ(ci.serialNumber, q) || includesQ(component.partNumber, q) || includesQ(component.description, q)) {
      results.push({
        type: "Component",
        id: ci.id,
        title: `${component.partNumber} — SN ${ci.serialNumber}`,
        subtitle: component.description,
        href: `/components/${ci.id}`,
      });
    }
  }

  for (const p of parts) {
    if (includesQ(p.partNumber, q) || includesQ(p.serialNumber, q) || includesQ(p.description, q) || includesQ(p.batchOrLot, q)) {
      results.push({
        type: "Part",
        id: p.id,
        title: p.serialNumber ? `${p.partNumber} — SN ${p.serialNumber}` : p.partNumber,
        subtitle: p.description,
        href: `/maintenance/parts/${p.id}`,
      });
    }
  }

  for (const wo of workOrders) {
    if (includesQ(wo.workOrderNumber, q) || includesQ(wo.title, q)) {
      results.push({
        type: "WorkOrder",
        id: wo.id,
        title: wo.workOrderNumber,
        subtitle: wo.title,
        href: `/maintenance/work-orders/${wo.id}`,
      });
    }
  }

  for (const t of technicians) {
    if (includesQ(t.name, q) || includesQ(t.role, q)) {
      results.push({
        type: "Technician",
        id: t.id,
        title: t.name,
        subtitle: t.role,
        href: `/maintenance/technicians/${t.id}`,
      });
    }
  }

  for (const v of vendors) {
    if (includesQ(v.name, q) || includesQ(v.vendorCode, q) || includesQ(v.legalName, q)) {
      results.push({
        type: "Vendor",
        id: v.id,
        title: v.name,
        subtitle: v.vendorCode ?? "Vendor",
        href: `/procurement/vendors/${v.id}`,
      });
    }
  }

  for (const po of purchaseOrders) {
    if (includesQ(po.poNumber, q)) {
      results.push({
        type: "PurchaseOrder",
        id: po.id,
        title: po.poNumber,
        subtitle: po.status,
        href: `/procurement/purchase-orders/${po.id}`,
      });
    }
  }

  for (const r of regulatoryRequirements) {
    if (includesQ(r.requirementNumber, q) || includesQ(r.description, q)) {
      results.push({
        type: "Regulation",
        id: r.id,
        title: r.requirementNumber,
        subtitle: r.requirementType,
        href: `/regulations/${r.id}`,
      });
    }
  }

  return results;
}
