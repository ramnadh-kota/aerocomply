import { describe, it, expect } from "vitest";
import { FAMILY_CONFIG, buildDetailPayload, detailToForm, formatHours, humanizeEnum } from "../lib/airframes/helpers";

const heli = FAMILY_CONFIG.helicopter.fields;
const evtol = FAMILY_CONFIG.evtol.fields;

describe("airframe detail payload", () => {
  it("omits blanks and converts numbers", () => {
    const { detail, errors } = buildDetailPayload(heli, { rotor_system: "TANDEM", engine_count: "2", main_rotor_blade_count: "", max_takeoff_weight_kg: "3700.5" });
    expect(errors).toEqual({});
    expect(detail).toEqual({ rotor_system: "TANDEM", engine_count: 2, max_takeoff_weight_kg: 3700.5 });
  });

  it("reports invalid values instead of silently coercing them", () => {
    const { detail, errors } = buildDetailPayload(heli, { rotor_system: "WARP", engine_count: "9", main_rotor_blade_count: "2.5", max_takeoff_weight_kg: "abc" });
    expect(Object.keys(errors).sort()).toEqual(["engine_count", "main_rotor_blade_count", "max_takeoff_weight_kg", "rotor_system"]);
    expect(detail).toEqual({});
  });

  it("rejects zero for positive real quantities but allows zero passengers", () => {
    expect(buildDetailPayload(evtol, { hv_bus_nominal_voltage_v: "0" }).errors.hv_bus_nominal_voltage_v).toBeDefined();
    expect(buildDetailPayload(evtol, { passenger_capacity: "0" }).detail).toEqual({ passenger_capacity: 0 });
  });

  it("round-trips API detail into form values", () => {
    expect(detailToForm(evtol, { configuration: "LIFT_CRUISE", propulsor_count: 8, passenger_capacity: null })).toMatchObject({
      configuration: "LIFT_CRUISE", propulsor_count: "8", passenger_capacity: "",
    });
  });
});

describe("formatting", () => {
  it("formats hours and enums", () => {
    expect(formatHours(150)).toBe("2.5 h");
    expect(formatHours(-5)).toBe("0.0 h");
    expect(humanizeEnum("SINGLE_MAIN_TAIL")).toBe("Single Main Tail");
    expect(humanizeEnum(null)).toBe("—");
  });
  it("binds each family to its own suite and feature", () => {
    expect(FAMILY_CONFIG.helicopter.suite).toBe("HELICOPTER");
    expect(FAMILY_CONFIG.evtol.feature).toBe("evtol_fleet_management");
  });
});
