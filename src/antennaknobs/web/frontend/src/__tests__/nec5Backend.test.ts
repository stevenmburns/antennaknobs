// NEC-5 as a served backend (issue #825): the entry rides the same
// roster-membership availability contract as pynec, with kind "nec5"
// steering the solver request field and suppressing momwire_model.
import { describe, expect, it } from "vitest";

import {
  backendDisplayLabel,
  defaultOptsFor,
  findBackend,
  modelOptionsForRequest,
} from "../lib/backends";
import { ROSTER_WITH_NEC5, SERVED_ROSTER } from "./backendFixtures";

describe("nec5 backend entry", () => {
  it("is absent from the default served roster (hosted shape)", () => {
    expect(SERVED_ROSTER.some((b) => b.kind === "nec5")).toBe(false);
  });

  it("resolves by name when served and labels its chip plainly", () => {
    const b = findBackend(ROSTER_WITH_NEC5, "nec5");
    expect(b?.kind).toBe("nec5");
    expect(backendDisplayLabel(b!, defaultOptsFor(b!))).toContain("NEC-5");
  });

  it("contributes no momwire model options", () => {
    const b = findBackend(ROSTER_WITH_NEC5, "nec5");
    expect(modelOptionsForRequest(b!, defaultOptsFor(b!))).toEqual({});
  });
});
