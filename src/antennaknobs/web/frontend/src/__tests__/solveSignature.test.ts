import { describe, it, expect } from "vitest";
import { solveSignature } from "../lib/solveSignature";
import type { SolveRequest } from "../lib/api";

// The tests build partial requests; the helper only walks the object.
const req = (r: Record<string, unknown>) => r as unknown as SolveRequest;

describe("solveSignature", () => {
  it("is stable under key construction order", () => {
    expect(solveSignature(req({ a: 1, b: { c: 2, d: 3 } }))).toBe(
      solveSignature(req({ b: { d: 3, c: 2 }, a: 1 })),
    );
  });

  it("exempts the metadata fields, mirroring the server blocklist", () => {
    const base = req({ geometry: "g", n_per_wire: 8 });
    const noisy = req({
      geometry: "g",
      n_per_wire: 8,
      _session: "tab-1",
      _seq: 42,
      _gen: 42,
      _approved: true,
      _request_id: "r",
      _client_ts: 1,
    });
    expect(solveSignature(noisy)).toBe(solveSignature(base));
  });

  it("drops caller-exempted keys but nothing else", () => {
    const a = req({ geometry: "g", az_elev_deg: 30 });
    const b = req({ geometry: "g", az_elev_deg: 45 });
    expect(solveSignature(a, { exempt: ["az_elev_deg"] })).toBe(
      solveSignature(b, { exempt: ["az_elev_deg"] }),
    );
    expect(solveSignature(a)).not.toBe(solveSignature(b));
  });

  it("treats any new field as load-bearing", () => {
    expect(solveSignature(req({ geometry: "g" }))).not.toBe(
      solveSignature(req({ geometry: "g", future_knob: 1 })),
    );
  });
});
