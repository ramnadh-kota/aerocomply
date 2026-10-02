import { describe, expect, it } from "vitest";
import { missionPilotLabel } from "@/lib/api/missions";

const UUID = "11111111-2222-3333-4444-555555555555";

describe("missionPilotLabel", () => {
  it("shows the resolved pilot name", () => {
    expect(missionPilotLabel({ pilot_user_id: UUID, pilot_name: "Asha Rao" })).toBe("Asha Rao");
  });
  it("returns null when no pilot is assigned", () => {
    expect(missionPilotLabel({ pilot_user_id: null, pilot_name: null })).toBeNull();
  });
  it("falls back without leaking the raw id when the pilot is not resolvable", () => {
    for (const pilot_name of [null, undefined, "  "]) {
      const label = missionPilotLabel({ pilot_user_id: UUID, pilot_name });
      expect(label).toBe("Pilot (name unavailable)");
      expect(label).not.toContain(UUID);
    }
  });
});

describe("missionPilotLabel (flight rows)", () => {
  it("is reused for flights: name, none, and unresolved without leaking ids", () => {
    expect(missionPilotLabel({ pilot_user_id: UUID, pilot_name: "Ravi K" })).toBe("Ravi K");
    expect(missionPilotLabel({ pilot_user_id: null })).toBeNull();
    expect(missionPilotLabel({ pilot_user_id: UUID })).not.toContain(UUID);
  });
});
