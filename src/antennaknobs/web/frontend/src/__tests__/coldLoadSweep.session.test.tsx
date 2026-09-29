// A cold first load (AK#1806): the default chart's first /sweep must wait for
// the design to resolve. On an empty browser cache /examples can take longer
// than the sweep's 500 ms dwell, and a sweep sent before it names no design
// the server knows (the #1343 UnknownGeometryError 400). The chart's
// frequency runner waits on the same readiness the live solve does: the
// catalog holds the design and its preview has landed.
//
// Mutation (run by hand, 2026-09-29): handing the analysis runners the bare
// `active` again (no design gate) sends a /sweep for geometry "" before
// /examples answers, and the first expectation below fails.
import { describe, it, expect, afterEach, vi } from "vitest";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady, untilDom } from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function ndjson(lines: string[]): Response {
  const chunks = [new TextEncoder().encode(lines.join("\n") + "\n")];
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          chunks.length > 0 ? { done: false, value: chunks.shift() } : { done: true, value: undefined },
      }),
    },
  } as unknown as Response;
}

describe("cold load: the default chart's first /sweep (AK#1806)", () => {
  it("is not sent before /examples resolves, and is sent after", async () => {
    const log: string[] = [];
    const sweeps: { geometry: unknown; afterExamples: boolean }[] = [];
    let examplesAnswered = false;
    let releaseExamples: () => void = () => {};
    const examplesGate = new Promise<void>((r) => {
      releaseExamples = r;
    });
    mountDesignSession({
      routes: {
        "/examples": async () => {
          log.push("GET /examples (asked)");
          await examplesGate;
          examplesAnswered = true;
          log.push("GET /examples (answered)");
          return jsonResponse({ examples: [HARNESS_EXAMPLE], errors: [] });
        },
        "/sweep": (_url: string, init?: RequestInit) => {
          const body = JSON.parse(String(init?.body ?? "{}"));
          sweeps.push({ geometry: body.geometry, afterExamples: examplesAnswered });
          log.push(`POST /sweep ${String(body.geometry)}`);
          const freqs = body.freqs_mhz as number[];
          const lines = freqs.map((f) => JSON.stringify({ freq_mhz: f, z_re: 50, z_im: 0 }));
          lines.push(JSON.stringify({ done: true }));
          return ndjson(lines);
        },
      },
    });
    // Well past the sweep's 500 ms dwell with the catalog still out: a
    // runner that does not wait for the design has sent by now.
    await new Promise((r) => setTimeout(r, 1200));
    expect(sweeps, log.join("\n")).toEqual([]);

    releaseExamples();
    await sessionReady(document.body);
    await untilDom(() => sweeps.length > 0 || null);
    expect(sweeps.every((s) => s.afterExamples && s.geometry === HARNESS_EXAMPLE.name)).toBe(true);
  });
});
