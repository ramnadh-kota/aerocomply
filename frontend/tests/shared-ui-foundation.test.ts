import { describe, it, expect } from "vitest";
import {
  assetStatusBadge,
  findingSeverityBadge,
  findingStatusBadge,
} from "../components/status/StatusBadge";
import { readinessStatusBadge } from "../components/readiness/ReadinessIndicator";

// M21.3 — pure-function tests for the shared UI foundation's new
// StatusBadge/readiness helpers, following this repo's existing convention
// (tests/sidebar-navigation.test.ts, tests/finding-detail.test.ts) of testing
// the real mapping/contract a component uses without mounting React (no RTL
// configured in this repo). PageHeader and ReadinessIndicator are pure
// rendering components with no exported logic beyond these helpers, so their
// JSX output is not independently unit-tested here — see M21_3_REPORT.md §H
// for what could and could not be covered this way.

describe("assetStatusBadge (extracted from drones list/detail local statusBadge helpers)", () => {
  it("maps ACTIVE/GOOD/READY to COMPLIANT", () => {
    expect(assetStatusBadge("ACTIVE")).toEqual({ status: "COMPLIANT", label: "ACTIVE" });
    expect(assetStatusBadge("GOOD")).toEqual({ status: "COMPLIANT", label: "GOOD" });
    expect(assetStatusBadge("READY")).toEqual({ status: "COMPLIANT", label: "READY" });
  });

  it("maps GROUNDED/CRITICAL/BLOCKED to NON_COMPLIANT", () => {
    expect(assetStatusBadge("GROUNDED")).toEqual({ status: "NON_COMPLIANT", label: "GROUNDED" });
    expect(assetStatusBadge("CRITICAL")).toEqual({ status: "NON_COMPLIANT", label: "CRITICAL" });
    expect(assetStatusBadge("BLOCKED")).toEqual({ status: "NON_COMPLIANT", label: "BLOCKED" });
  });

  it("falls back to UNKNOWN for any other string", () => {
    expect(assetStatusBadge("SOMETHING_ELSE")).toEqual({ status: "UNKNOWN", label: "SOMETHING_ELSE" });
  });
});

describe("findingSeverityBadge (extracted from findings/[id] local severityBadge)", () => {
  it("maps CRITICAL and MAJOR to NON_COMPLIANT", () => {
    expect(findingSeverityBadge("CRITICAL")).toEqual({ status: "NON_COMPLIANT", label: "CRITICAL" });
    expect(findingSeverityBadge("MAJOR")).toEqual({ status: "NON_COMPLIANT", label: "MAJOR" });
  });

  it("maps MINOR and OBSERVATION to PENDING (preserving exact prior behavior, not merging severities)", () => {
    expect(findingSeverityBadge("MINOR")).toEqual({ status: "PENDING", label: "MINOR" });
    expect(findingSeverityBadge("OBSERVATION")).toEqual({ status: "PENDING", label: "OBSERVATION" });
  });
});

describe("findingStatusBadge (extracted from findings/[id] local statusBadge)", () => {
  it("maps CLOSED to COMPLIANT, IN_PROGRESS to REVIEW_REQUIRED, OPEN to PENDING", () => {
    expect(findingStatusBadge("CLOSED")).toEqual({ status: "COMPLIANT", label: "CLOSED" });
    expect(findingStatusBadge("IN_PROGRESS")).toEqual({ status: "REVIEW_REQUIRED", label: "IN PROGRESS" });
    expect(findingStatusBadge("OPEN")).toEqual({ status: "PENDING", label: "OPEN" });
  });
});

describe("readinessStatusBadge (shared ReadinessIndicator, used by drone detail + RealReleaseReadinessPanel)", () => {
  it("maps READY to COMPLIANT and BLOCKED to NON_COMPLIANT", () => {
    expect(readinessStatusBadge("READY")).toEqual({ status: "COMPLIANT", label: "Ready" });
    expect(readinessStatusBadge("BLOCKED")).toEqual({ status: "NON_COMPLIANT", label: "Blocked" });
  });

  it("passes through any other status as UNKNOWN with the raw string as label", () => {
    expect(readinessStatusBadge("PENDING_REVIEW")).toEqual({ status: "UNKNOWN", label: "PENDING_REVIEW" });
  });
});
