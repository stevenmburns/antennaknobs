// A stale curve is kept only for the cell it was solved for (AC6LA, QRZ, on
// v0.97.1). Picking the inverted vee's "height" after "Sweep a knob" left
// the knob sweep (base 1-16 m on Sommerfeld · average) drawn, dimmed, on the
// chart's first runner, which the pick had moved to the free-space cell: the
// legend named a Sommerfeld curve "free space". A knob sweep that only
// changed its inputs on the same cell still stays, dimmed ("re-run?").
//
// Mutation note (run by hand, 2026-10-06; reverted after): dropping the
// `sameCell` test in useParamSweep's stale branch fails "another cell's
// curve is cleared".
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useParamSweep } from "../components/session/useParamSweep";

type P = { sig: string; cell: string; values: number[] };

function mount() {
  const lines = [
    { param: "base", value: 1, z_re: 980, z_im: 1900, solver: "momwire" },
    { done: true, solver: "momwire" },
  ];
  const text = lines.map((l) => JSON.stringify(l)).join("\n") + "\n";
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(text, { status: 200 })),
  );
  return renderHook(
    (p: P) => {
      const seqRef = useRef(1);
      const approvedComboRef = useRef(false);
      return useParamSweep({
        req: { param: "base", values: p.values, label: "base", auto: false },
        sig: p.sig,
        wanted: true,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        buildRequest: () => ({ geometry: "dipoles.invvee" }) as never,
        solveWithheld: () => false,
        seqRef,
        approvedComboRef,
        cell: p.cell,
      });
    },
    { initialProps: { sig: "knob", cell: "solo", values: [1, 16] } },
  );
}

describe("a stale curve stays only on its own cell", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("the same cell, new inputs: kept, dimmed", async () => {
    const { result, rerender } = mount();
    result.current.runNow();
    await waitFor(() => expect(result.current.data?.values).toEqual([1]));
    rerender({ sig: "height", cell: "solo", values: [2, 20] });
    expect(result.current.data?.stale).toBe(true);
  });

  it("another cell's curve is cleared, not drawn under the new cell's name", async () => {
    const { result, rerender } = mount();
    result.current.runNow();
    await waitFor(() => expect(result.current.data?.values).toEqual([1]));
    rerender({ sig: "height", cell: "A|Y", values: [2, 20] });
    expect(result.current.data).toBeNull();
  });
});
