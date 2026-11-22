/**
 * momwire#2091: the tabs are `bs2`, `sg` and `razor2p` now. A recommendation
 * or a required-backend list that still names an old spelling (an older
 * server's hint, a saved design's) resolves to the same tab through the
 * SERVED alias map, so the frontend carries no table of its own.
 */
import { describe, expect, it } from "vitest";
import { normalizeBackend } from "../lib/backends";
import { entry, SERVED_ALIASES, SERVED_ROSTER } from "./backendFixtures";

describe("an old engine name opens the same tab", () => {
  it.each([
    ["bspline", "bs2"],
    ["sinusoidal-galerkin", "sg"],
    ["razor-2p", "razor2p"],
  ])("%s -> %s", (old, now) => {
    expect(normalizeBackend(old, SERVED_ROSTER, SERVED_ALIASES)).toBe(entry(now));
  });

  it("serves no tab under an old name", () => {
    const names = SERVED_ROSTER.map((b) => b.name);
    for (const old of Object.keys(SERVED_ALIASES)) expect(names).not.toContain(old);
  });
});
