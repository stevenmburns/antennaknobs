/**
 * Who gets an EK control, and who must not (antennaknobs#1255).
 *
 * The EK card is a bespoke widget, not a generic axis control, and it was
 * guarded by `kind === "momwire"` under the comment "common to every momwire
 * backend". The Pulse tab (#1148) made that comment false: every other
 * momwire row serves `kernel: ["extended", "reduced"]` and Pulse serves
 * `["reduced"]`. Ticking the box on a reduced-only class offers a refusal.
 *
 * These tests read the GENERATED axes fixture through `SERVED_ROSTER` rather
 * than naming Pulse, so they keep meaning something when the next
 * reduced-only backend arrives — and they check the whole roster in both
 * directions rather than only the one row that prompted the change.
 */
import { describe, expect, it } from "vitest";

import { SERVED_AXES } from "./axesFixtures";
import { SERVED_ROSTER, backendEntry } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";
import {
  extendedKernelActive,
  offersExtendedKernel,
  modelOptionsForRequest,
  type BackendEntry,
  type BackendOpts,
} from "../lib/backends";

const optsWithEk = (): BackendOpts =>
  ({ model: { extended_kernel: true } }) as unknown as BackendOpts;

describe("the roster fixture actually covers what the server serves", () => {
  it("has every served backend except nec5, which it documents omitting", () => {
    const served = Object.keys(SERVED_AXES).filter((n) => n !== "nec5");
    const fixture = SERVED_ROSTER.map((b) => b.name);
    // Both directions. A fixture MISSING a row makes every loop below skip it
    // silently — which is exactly how `pulse` got here with no EK coverage.
    expect([...fixture].sort()).toEqual([...served].sort());
  });
});

describe("offersExtendedKernel follows the served row, not the kind", () => {
  it("offers EK to exactly the momwire rows with a multi-valued kernel axis", () => {
    for (const b of SERVED_ROSTER) {
      const vals = SERVED_AXES[b.name]?.kernel;
      const want =
        b.kind === "momwire" &&
        (b.model_kwargs ?? []).includes("extended_kernel") &&
        (vals ? vals.length > 1 : true);
      expect(offersExtendedKernel(b), `${b.name}`).toBe(want);
    }
  });

  it("refuses a reduced-only momwire row", () => {
    const reducedOnly = SERVED_ROSTER.filter(
      (b) => b.kind === "momwire" && SERVED_AXES[b.name]?.kernel?.length === 1,
    );
    // The precondition, asserted: if the roster ever has no reduced-only row
    // this test passes over an empty list and means nothing.
    expect(reducedOnly.length).toBeGreaterThan(0);
    for (const b of reducedOnly) {
      expect(offersExtendedKernel(b), `${b.name}`).toBe(false);
    }
  });

  it("still offers EK to the multi-valued rows — the change is not a blanket off", () => {
    const multi = SERVED_ROSTER.filter(
      (b) => b.kind === "momwire" && (SERVED_AXES[b.name]?.kernel?.length ?? 0) > 1,
    );
    expect(multi.length).toBeGreaterThan(0);
    for (const b of multi) {
      expect(offersExtendedKernel(b), `${b.name}`).toBe(true);
    }
  });

  it("never offers EK to a non-momwire backend", () => {
    for (const b of SERVED_ROSTER.filter((x) => x.kind !== "momwire")) {
      expect(offersExtendedKernel(b), `${b.name}`).toBe(false);
    }
  });

  it("refuses a momwire row that cannot be SENT the kwarg, whatever its axes", () => {
    // `degreeChoices`' pynec lesson in a second spelling: null axes must not
    // let a row with no such kwarg fall through the fallback and grow a box.
    const noKwarg = backendEntry({ name: "future", axes: null, model_kwargs: [] });
    expect(offersExtendedKernel(noKwarg)).toBe(false);
  });

  it("keeps the pre-#1255 answer when a momwire cannot describe itself", () => {
    // A momwire predating the axis vocabulary: axes null, kwarg present.
    // Hiding EK there would be a silent regression on the released momwire.
    const old = backendEntry({
      name: "old",
      axes: null,
      model_kwargs: ["extended_kernel"],
    });
    expect(offersExtendedKernel(old)).toBe(true);
  });
});

describe("a stale EK flag cannot leak past a backend that does not offer it", () => {
  it("reads as inactive, so the label carries no +EK and the wire carries no kwarg", () => {
    // The real path: tick EK on B-spline, then switch the slot to Pulse. The
    // opts object survives the switch, so `extended_kernel: true` is still
    // there — and it must not reach the engine, which would refuse it.
    const reducedOnly = SERVED_ROSTER.filter(
      (b) => b.kind === "momwire" && SERVED_AXES[b.name]?.kernel?.length === 1,
    );
    expect(reducedOnly.length).toBeGreaterThan(0);
    for (const b of reducedOnly) {
      expect(extendedKernelActive(b, optsWithEk()), `${b.name}`).toBe(false);
      expect(modelOptionsForRequest(b, optsWithEk(), SERVED_OPTION_SPECS)).not.toHaveProperty(
        "extended_kernel",
      );
    }
  });

  it("still sends it for a backend that does offer it", () => {
    const b = SERVED_ROSTER.find(
      (x) => x.kind === "momwire" && (SERVED_AXES[x.name]?.kernel?.length ?? 0) > 1,
    ) as BackendEntry;
    expect(b).toBeTruthy();
    expect(extendedKernelActive(b, optsWithEk())).toBe(true);
    expect(modelOptionsForRequest(b, optsWithEk(), SERVED_OPTION_SPECS)).toHaveProperty(
      "extended_kernel",
      true,
    );
  });
});
