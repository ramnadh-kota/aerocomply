import { describe, it, expect } from "vitest";
import { formatScalar, humanizeKey, isIsoDateTime, scalarEntries } from "../lib/live/format";

describe("live view formatting", () => {
  it("humanizes keys and keeps acronyms upper-case", () => {
    expect(humanizeKey("part_number")).toBe("Part Number");
    expect(humanizeKey("po_id")).toBe("PO ID");
  });
  it("formats scalars without inventing values", () => {
    expect(formatScalar("x", null)).toBe("—");
    expect(formatScalar("x", "")).toBe("—");
    expect(formatScalar("approved", true)).toBe("Yes");
    expect(formatScalar("qty", 3)).toBe("3");
    expect(formatScalar("r", 0.123456)).toBe("0.123");
    expect(formatScalar("total_cents", 12345)).toMatch(/123\.45/);
    expect(formatScalar("name", "ACME")).toBe("ACME");
    expect(isIsoDateTime("2026-01-01T10:00:00Z")).toBe(true);
    expect(isIsoDateTime("not a date")).toBe(false);
  });
  it("omits tenant plumbing, secrets and nested structures from the detail table", () => {
    const keys = scalarEntries({ id: "1", organization_id: "o", hashed_password: "h", provenance: { a: 1 }, lines: [1], name: "n", n: 2, ok: false, gone: null }).map(([k]) => k);
    expect(keys).toEqual(["id", "name", "n", "ok", "gone"]);
  });
});
