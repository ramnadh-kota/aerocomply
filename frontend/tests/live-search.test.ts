import { describe, it, expect } from "vitest";
import { assetResults, workOrderResults } from "../lib/search/live";

describe("live global search mapping", () => {
  it("routes each asset family to its own live page", () => {
    const base = { registration: null, serial_number: null, manufacturer: null, model: null };
    const r = assetResults([
      { ...base, id: "a", asset_type: "AIRCRAFT", registration: "N1" },
      { ...base, id: "d", asset_type: "DRONE", serial_number: "SN9", manufacturer: "Acme", model: "X" },
      { ...base, id: "h", asset_type: "HELICOPTER", registration: "H1" },
      { ...base, id: "e", asset_type: "EVTOL", registration: "E1" },
      { ...base, id: "z", asset_type: "SPACESHIP", registration: "Z" },
    ]);
    expect(r.map((x) => x.href)).toEqual(["/aircraft/a", "/drones/d", "/helicopters/h", "/evtols/e"]);
    expect(r[1].title).toBe("SN9");
    expect(r[1].subtitle).toBe("Acme X");
  });

  it("maps work orders", () => {
    const r = workOrderResults([{ id: "w1", work_order_number: "WO-1", title: "Brake", status: "OPEN" }]);
    expect(r[0]).toMatchObject({ href: "/maintenance/work-orders/w1", title: "WO-1", subtitle: "Brake · OPEN" });
  });
});
