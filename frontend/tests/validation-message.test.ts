import { describe, expect, it } from "vitest";
import { friendlyValidationMessage } from "../lib/apiClient";

describe("friendlyValidationMessage", () => {
  it("turns the FastAPI repr into readable text", () => {
    const raw = "[{'type': 'value_error', 'loc': ('body', 'email'), 'msg': 'value is not a valid email address: The part after the @-sign is reserved.', 'input': 'a@b.test', 'ctx': {}}]";
    const out = friendlyValidationMessage(raw);
    expect(out).toContain("email:");
    expect(out).not.toContain("'loc'");
  });
  it("leaves ordinary messages alone", () => {
    expect(friendlyValidationMessage("Name is required")).toBe("Name is required");
  });
});
