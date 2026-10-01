// Live (non-demo) global-search mapping. Results come only from the organization's own API responses.

export interface LiveSearchResult {
  type: "Aircraft" | "Drone" | "Helicopter" | "eVTOL" | "WorkOrder";
  id: string;
  title: string;
  subtitle: string;
  href: string;
}

interface AssetLike {
  id: string;
  asset_type: string;
  registration: string | null;
  serial_number: string | null;
  manufacturer: string | null;
  model: string | null;
}

interface WorkOrderLike {
  id: string;
  work_order_number: string;
  title: string | null;
  status: string;
}

const ASSET_ROUTES: Record<string, { type: LiveSearchResult["type"]; base: string }> = {
  AIRCRAFT: { type: "Aircraft", base: "/aircraft" },
  DRONE: { type: "Drone", base: "/drones" },
  HELICOPTER: { type: "Helicopter", base: "/helicopters" },
  EVTOL: { type: "eVTOL", base: "/evtols" },
};

export function assetResults(assets: AssetLike[]): LiveSearchResult[] {
  const out: LiveSearchResult[] = [];
  for (const a of assets) {
    const route = ASSET_ROUTES[a.asset_type];
    if (!route) continue;
    out.push({
      type: route.type,
      id: a.id,
      title: a.registration || a.serial_number || a.id,
      subtitle: [a.manufacturer, a.model].filter(Boolean).join(" ") || a.asset_type,
      href: `${route.base}/${a.id}`,
    });
  }
  return out;
}

export function workOrderResults(items: WorkOrderLike[]): LiveSearchResult[] {
  return items.map((w) => ({
    type: "WorkOrder" as const,
    id: w.id,
    title: w.work_order_number,
    subtitle: w.title ? `${w.title} · ${w.status}` : w.status,
    href: `/maintenance/work-orders/${w.id}`,
  }));
}

export const LIVE_GROUP_ORDER: LiveSearchResult["type"][] = ["Aircraft", "Drone", "Helicopter", "eVTOL", "WorkOrder"];

export const LIVE_GROUP_LABEL: Record<LiveSearchResult["type"], string> = {
  Aircraft: "Aircraft",
  Drone: "Drones",
  Helicopter: "Helicopters",
  eVTOL: "eVTOLs",
  WorkOrder: "Work Orders",
};
