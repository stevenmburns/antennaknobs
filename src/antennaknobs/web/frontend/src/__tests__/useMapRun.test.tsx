// The map runner (components/session/useMapRun.ts): /map streamed node by
// node, painted as it lands; the swept knobs and z0 exempt from its inputs;
// any other input stales it; a dropped stream resumes from the first node
// not yet landed; the hosted time limit keeps the partial map.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useRef } from "react";
import type { SolveRequest } from "../lib/api";
import { landed } from "../lib/mapGrid";
import { mapSignature, useMapRun } from "../components/session/useMapRun";

const X = { param: "length_factor", values: [0.9, 1.0, 1.1] };
const Y = { param: "angle_deg", values: [0, 30] };
const node = (i: number, j: number) => ({ i, j, z_re: 50 + i, z_im: j, solver: "momwire" });
const lines = (recs: object[]) => recs.map((r) => JSON.stringify(r)).join("\n") + "\n";

function mount(req: { current: SolveRequest }, over: { auto?: boolean } = {}) {
  return renderHook(
    ({ sig }: { sig: string }) => {
      const approvedComboRef = useRef(false);
      return useMapRun({
        sig,
        x: X,
        y: Y,
        wanted: true,
        auto: over.auto ?? false,
        autoSim: true,
        active: true,
        comboApproved: false,
        recommendedBackend: null,
        buildRequest: () => req.current,
        solveWithheld: () => false,
        approvedComboRef,
      });
    },
    { initialProps: { sig: mapSignature(req.current, X, Y) } },
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("the signature", () => {
  const base = { geometry: "dipoles.invvee", length_factor: 0.97, angle_deg: 31, base: 7 } as unknown as SolveRequest;
  it("is blind to the two swept knobs and z0, not to any other input", () => {
    const s = mapSignature(base, X, Y);
    expect(mapSignature({ ...base, length_factor: 1.02, angle_deg: 10 } as SolveRequest, X, Y)).toBe(s);
    expect(mapSignature({ ...base, z0_ohms: 75 } as SolveRequest, X, Y)).toBe(s);
    expect(mapSignature({ ...base, base: 8 } as SolveRequest, X, Y)).not.toBe(s);
    expect(mapSignature(base, { ...X, values: [0.9, 1.0] }, Y)).not.toBe(s);
  });
});

describe("a run", () => {
  it("paints as nodes land, sends no generation, and closes done", async () => {
    const bodies: Record<string, unknown>[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_u: string, init: RequestInit) => {
        bodies.push(JSON.parse(String(init.body)));
        return new Response(
          lines([...[0, 1].flatMap((j) => [0, 1, 2].map((i) => node(i, j))), { done: true, points: 6 }]),
        );
      }),
    );
    const req = { current: { geometry: "dipoles.invvee", _gen: 9 } as unknown as SolveRequest };
    const { result } = mount(req);
    // The dwell switch is off: nothing runs until asked.
    expect(result.current.phase).toBe("idle");
    expect(bodies).toEqual([]);
    act(() => result.current.runNow());
    await waitFor(() => expect(result.current.data?.done).toBe(true));
    const d = result.current.data!;
    expect(landed(d.grid)).toBe(6);
    expect(d.grid.re[1][2]).toBe(52);
    expect(d.received).toBe(6);
    expect(bodies[0].from).toBe(0);
    expect(bodies[0].x).toEqual(X);
    expect(bodies[0]._gen).toBe(9); // the request's own field passes through untouched
  });

  it("another input stales it (dwell off); the knobs it sweeps do not", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(lines([node(0, 0), { done: true }]))));
    const req = { current: { geometry: "g", length_factor: 1, base: 7 } as unknown as SolveRequest };
    const { result, rerender } = mount(req);
    act(() => result.current.runNow());
    await waitFor(() => expect(result.current.data?.done).toBe(true));
    req.current = { ...req.current, length_factor: 1.05 } as SolveRequest;
    rerender({ sig: mapSignature(req.current, X, Y) });
    expect(result.current.data?.stale).toBeUndefined();
    req.current = { ...req.current, base: 8 } as SolveRequest;
    rerender({ sig: mapSignature(req.current, X, Y) });
    expect(result.current.data?.stale).toBe(true);
    expect(landed(result.current.data!.grid)).toBe(1);
  });

  it("a dropped stream is asked again from the first node not yet landed", async () => {
    const froms: number[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_u: string, init: RequestInit) => {
        const from = JSON.parse(String(init.body)).from as number;
        froms.push(from);
        // The first stream drops after three nodes (no closing record).
        return from === 0
          ? new Response(lines([node(0, 0), node(1, 0), node(2, 0)]))
          : new Response(lines([node(0, 1), node(1, 1), node(2, 1), { done: true }]));
      }),
    );
    const { result } = mount({ current: { geometry: "g" } as unknown as SolveRequest });
    act(() => result.current.runNow());
    await waitFor(() => expect(result.current.data?.done).toBe(true));
    expect(froms).toEqual([0, 3]);
    expect(landed(result.current.data!.grid)).toBe(6);
  });

  it("the hosted time limit keeps the partial map and says so", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(lines([node(0, 0), node(1, 0), { done: true, stopped: "time", time_budget_s: 120 }]))),
    );
    const { result } = mount({ current: { geometry: "g" } as unknown as SolveRequest });
    act(() => result.current.runNow());
    await waitFor(() => expect(result.current.data?.done).toBe(true));
    expect(result.current.data!.timeLimitS).toBe(120);
    expect(landed(result.current.data!.grid)).toBe(2);
  });

  it("a refusal is the server's words", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "A map of 1089 points is over the live limit of 1000." }), { status: 413 })),
    );
    const { result } = mount({ current: { geometry: "g" } as unknown as SolveRequest });
    act(() => result.current.runNow());
    await waitFor(() => expect(result.current.data?.errorStatus).toBe(413));
    expect(result.current.data!.error).toMatch(/over the live limit/);
  });
});
