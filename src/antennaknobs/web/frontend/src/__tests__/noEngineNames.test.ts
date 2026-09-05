/**
 * The frontend carries no engine names (antennaknobs#1006 G2-6).
 *
 * The whole unit is this: per-engine detail is SERVED, so `lib/backends.ts`
 * and `BackendConfigModal.tsx` should be able to render any solver the server
 * registers without naming one. This is the grep that says whether that is
 * true, and it asserts the EXACT residue rather than zero — a test that
 * demanded zero would either be a lie or force a regression to satisfy it.
 *
 * THE RESIDUE IS A TYPE, NOT A BRANCH. Until v0.68.0 one branch survived:
 * `feedModelChoices` fell back to the `sin-galerkin` panel hint when a
 * backend's `axes` was null, because that was the momwire users had while
 * the submodule pointer ran ahead of the PyPI pin. The pin moved to momwire
 * 0.48.0 (#1169), which serves the vocabulary, and the branch went with it
 * (#1170). What remains is the served payload's own `kind` field type.
 */
import { describe, expect, it } from "vitest";
// Vite's `?raw` rather than node:fs — the app's tsconfig has no node types,
// and this keeps the test running in the same environment as the code.
import backendsSrc from "../lib/backends.ts?raw";
import modalSrc from "../components/backend/BackendConfigModal.tsx?raw";

const FILES: [string, string][] = [
  ["lib/backends.ts", backendsSrc],
  ["components/backend/BackendConfigModal.tsx", modalSrc],
];

/** Engine and panel names, as string literals. Property access (`opts.model`)
 *  is not a name; a quoted `"bspline"` is.
 *
 *  The `kind` union (`"momwire" | "pynec" | "nec5"`) is deliberately NOT here:
 *  it is the served payload's own field type, not a branch on an engine, and a
 *  client cannot type the wire without it. */
const ENGINE_NAME = new RegExp(
  [
    '"bspline"',
    '"bspline-d1"',
    '"sinusoidal"',
    '"sinusoidal-galerkin"',
    '"sin-galerkin"',
    '"hmatrix"',
    '"arrayblock"',
    '"razor-2p"',
    '"razor-nec5"',
    '"pynec"',
    '"nec5"',
    '"pulse"',
    "PANEL_[A-Z_]+",
  ].join("|"),
  "g",
);

/** Code only: prose about an engine is documentation, not a branch. */
function codeLines(src: string): { line: string; n: number }[] {
  return src
    .split("\n")
    .map((line, i) => ({ line, n: i + 1 }))
    .filter(({ line }) => !/^\s*(\/\/|\*|\/\*)/.test(line));
}

describe("no engine names in the two files the unit is about", () => {
  it.each(FILES)("%s carries only the allowed residue", (_name, src) => {
    const hits = codeLines(src).flatMap(({ line, n }) =>
      (line.match(ENGINE_NAME) ?? []).map((m) => `${n}: ${m}  ${line.trim()}`),
    );
    // THE RESIDUE, NAMED EXACTLY. One thing is allowed and nothing else:
    // the `kind` union, `"momwire" | "pynec" | "nec5"`. That is the served
    // payload's own FIELD TYPE, not a branch on an engine — a client cannot
    // type the wire without writing the values the wire carries. It is
    // matched narrowly (the union line itself) so that a genuine
    // `kind === "pynec"` branch would still fail.
    const allowed = (h: string) =>
      /kind: "momwire" \| "pynec" \| "nec5";$/.test(h);
    const unexpected = hits.filter((h) => !allowed(h));
    expect(unexpected).toEqual([]);
  });

  it("no panel-hint constant survives, and nothing reads the hint", () => {
    // The axes-null fallback was the one deliberate branch (#1006 G2-6); it
    // went with the pin bump that made it dead (#1170). If a `PANEL_*`
    // constant or a read of `.panel` reappears in code, a branch on an engine
    // name has been added and this test is the place that says so.
    const hits = codeLines(backendsSrc).filter(({ line }) =>
      /PANEL_[A-Z_]+|"sin-galerkin"|\.panel\b/.test(line),
    );
    expect(hits.map((h) => `${h.n}: ${h.line.trim()}`)).toEqual([]);
  });

  it("the modal names no engine at all", () => {
    const hits = codeLines(modalSrc).filter(({ line }) =>
      ENGINE_NAME.test(line),
    );
    ENGINE_NAME.lastIndex = 0;
    expect(hits.map((h) => `${h.n}: ${h.line.trim()}`)).toEqual([]);
  });

  it("is not passing because the files moved or the pattern is broken", () => {
    // The guard this whole file needs: a regex that matches nothing, or a
    // path that no longer exists, would report a clean bill of health.
    for (const [, src] of FILES) {
      expect(codeLines(src).length).toBeGreaterThan(50);
    }
    const control = 'const x = "bspline";';
    expect(control.match(ENGINE_NAME)).toEqual(['"bspline"']);
    ENGINE_NAME.lastIndex = 0;
  });
});


describe("the residue shrinks, and the reasons are written down", () => {
  it("a `kind ===` branch would still fail, union or no union", () => {
    // The union is allowed by matching the DECLARATION line, not the names.
    // A comparison against one of those names is a branch and must not slip
    // through the same hole.
    const branch = 'if (b.kind === "pynec") return null;';
    expect(branch.match(ENGINE_NAME)).toEqual(['"pynec"']);
    ENGINE_NAME.lastIndex = 0;
    expect(/kind: "momwire" \| "pynec" \| "nec5";$/.test(branch)).toBe(false);
  });

  it("the slot seeds and the retired-name alias are SERVED, not local", () => {
    // Both were engine names in this file until #1006 G2-6:
    //   A: { backend: "bspline", nPerWire: 15 }
    //   name === "triangular" ? "bspline" : name
    // The first is three product decisions, the second a compatibility
    // mapping the server already made on the solve path. Neither is a fact
    // the client should own.
    // CODE lines only. Both shapes are QUOTED in the comments that explain
    // what was removed and why, so a whole-file `toContain` matches the
    // documentation and fails — which it did on first writing. Prose about a
    // deleted branch is not the branch.
    const code = codeLines(backendsSrc).map((l) => l.line).join("\n");
    expect(code).not.toContain('backend: "bspline"');
    expect(code).not.toContain('"triangular" ? "bspline"');
    expect(code).toContain("ServedSlotSeed");
    expect(code).toContain("aliases[name] ?? name");
  });
});
