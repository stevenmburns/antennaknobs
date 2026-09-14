// Pins the Files view's fetch discipline (src/components/session/
// useEngineFiles.ts, AK#1428): the source is fetched per DESIGN, the engine
// texts once per SOLVE and only for a solve the server labelled as having run
// through a binary, nothing moves while the view is not resident, a new solve
// keeps the previous texts up (stale) until its own land, and a design switch
// drops them at once.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useEngineFiles } from "../components/session/useEngineFiles";
import type { SolveRequest } from "../lib/api";

const REQ = { geometry: "dipoles.invvee", solver: "enga" } as unknown as SolveRequest;

function respond(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

let fetchMock: ReturnType<typeof vi.fn>;
let ioReply: ((body: Record<string, unknown>) => unknown) | null;

beforeEach(() => {
  vi.useFakeTimers();
  ioReply = null;
  fetchMock = vi.fn((url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    if (url === "/design_source") {
      return respond({
        available: true,
        geometry: body.geometry,
        filename: "f.py",
        language: "python",
        text: `source of ${body.geometry}`,
      });
    }
    return respond(
      ioReply?.(body) ?? {
        available: true,
        solver: "enga",
        label: "Engine-A",
        solve_id: body.solve_id,
        runs: [{ deck: `deck of ${body.solve_id}`, printout: "out", cached: false }],
      },
    );
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

type Props = {
  active: boolean;
  geometry: string;
  solveId: string | null;
  engineLabel: string | null;
};

const BASE: Props = {
  active: true,
  geometry: "dipoles.invvee",
  solveId: "s1",
  engineLabel: "Engine-A",
};

function renderFiles(initial: Partial<Props> = {}) {
  return renderHook((p: Props) => useEngineFiles({ ...p, buildRequest: () => REQ }), {
    initialProps: { ...BASE, ...initial },
  });
}

async function settle() {
  await act(async () => {
    vi.advanceTimersByTime(250);
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

const calls = (url: string) => fetchMock.mock.calls.filter((c) => c[0] === url);

describe("gating", () => {
  it("fetches nothing while the view is not resident", async () => {
    renderFiles({ active: false });
    await settle();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("never asks for engine texts on a solve that ran no binary, but loads the source", async () => {
    const { result } = renderFiles({ engineLabel: null });
    await settle();
    expect(calls("/engine_io")).toHaveLength(0);
    expect(calls("/design_source")).toHaveLength(1);
    expect(result.current.source?.available).toBe(true);
    expect(result.current.engine).toBeNull();
    expect(result.current.solved).toBe(true);
  });
});

describe("what is fetched when", () => {
  it("asks once per solve, after the debounce, naming the solve", async () => {
    const { rerender } = renderFiles();
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    expect(calls("/engine_io")).toHaveLength(0);
    await settle();
    expect(calls("/engine_io")).toHaveLength(1);
    const body = JSON.parse(String(calls("/engine_io")[0][1].body));
    expect(body).toMatchObject({ geometry: "dipoles.invvee", solver: "enga", solve_id: "s1" });

    rerender({ ...BASE });
    await settle();
    expect(calls("/engine_io")).toHaveLength(1);

    rerender({ ...BASE, solveId: "s2" });
    await settle();
    expect(calls("/engine_io")).toHaveLength(2);
  });

  it("coalesces a drag's solves into one ask", async () => {
    const { rerender } = renderFiles({ solveId: "s1" });
    rerender({ ...BASE, solveId: "s2" });
    rerender({ ...BASE, solveId: "s3" });
    await settle();
    expect(calls("/engine_io")).toHaveLength(1);
    expect(JSON.parse(String(calls("/engine_io")[0][1].body)).solve_id).toBe("s3");
  });

  it("loads the source per design, not per solve", async () => {
    const { rerender } = renderFiles();
    await settle();
    rerender({ ...BASE, solveId: "s2" });
    await settle();
    expect(calls("/design_source")).toHaveLength(1);
    rerender({ ...BASE, geometry: "user.my_yagi", solveId: null, engineLabel: null });
    await settle();
    expect(calls("/design_source")).toHaveLength(2);
  });
});

describe("stale-display policy", () => {
  it("a new solve keeps the old texts up, flagged stale, until its own land", async () => {
    const { result, rerender } = renderFiles();
    await settle();
    expect(result.current.engineIo?.runs?.[0].deck).toBe("deck of s1");
    expect(result.current.stale).toBe(false);

    rerender({ ...BASE, solveId: null, engineLabel: null });
    expect(result.current.engineIo?.runs?.[0].deck).toBe("deck of s1");
    expect(result.current.stale).toBe(true);
    // Nothing on screen names an engine mid-solve, so the texts name their own.
    expect(result.current.engine).toBe("Engine-A");

    rerender({ ...BASE, solveId: "s2" });
    await settle();
    expect(result.current.engineIo?.runs?.[0].deck).toBe("deck of s2");
    expect(result.current.stale).toBe(false);
  });

  it("a solve that ran no binary names no engine, whatever texts are held", async () => {
    const { result, rerender } = renderFiles();
    await settle();
    rerender({ ...BASE, solveId: "m1", engineLabel: null });
    expect(result.current.engine).toBeNull();
  });

  it("a design switch drops the other design's texts at once", async () => {
    const { result, rerender } = renderFiles();
    await settle();
    expect(result.current.source).not.toBeNull();
    rerender({ ...BASE, geometry: "user.my_yagi", solveId: null, engineLabel: null });
    expect(result.current.source).toBeNull();
    expect(result.current.engineIo).toBeNull();
    expect(result.current.solved).toBe(false);
  });

  it("a superseded re-run is not taken as the solve's texts", async () => {
    ioReply = () => ({ available: false, solver: "enga", superseded: true });
    const { result } = renderFiles();
    await settle();
    expect(result.current.engineIo).toBeNull();
  });
});
