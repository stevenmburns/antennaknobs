// Two unit-3 placement facts about DesignSession.tsx (docs/plan-view-rail-
// scaling.md "Layout modes") that a behavioral test can't reach cheaply:
// the segmented control is desktop-only, and the grid-mode HUD renders once
// at the stage level rather than per cell.
//
// DesignSession.tsx is the one component this whole test suite never mounts
// directly — see every other file here testing a piece PULLED OUT of it
// instead (SolveOverlays.test.tsx, ViewPicker.test.tsx, StageOverlays'
// LayoutModeToggle.test.tsx, ViewGrid.test.tsx). It owns a WebSocket, a
// fetch-backed catalog, a capabilities gate and more; building that harness
// to check two placement facts would cost far more than the facts are
// worth. So this is a structural check instead: it slices the file's own
// source at the two branch boundaries the code already documents in its own
// comments ("if (isMobile) {" and the desktop return's `.stage` element,
// both read verbatim, not by line number) and asserts on what appears in
// each slice.
//
// Source pulled in via Vite's `?raw` (a string import, no bundling) rather
// than node:fs — this project has no Node type references at all (browser-
// only code throughout), and one `?raw` import is a smaller footprint than
// adding one.
/// <reference types="vite/client" />
import { describe, it, expect } from "vitest";
import designSessionSrc from "../components/session/DesignSession.tsx?raw";
import viewGridSrc from "../components/results/ViewGrid.tsx?raw";

const SRC = designSessionSrc;

const mobileStart = SRC.indexOf("if (isMobile) {");
const stageStart = SRC.indexOf('className="stage"');

describe("DesignSession's mobile/desktop branch split", () => {
  it("has both anchors, in the expected order (sanity: this test isn't vacuous)", () => {
    expect(mobileStart).toBeGreaterThan(-1);
    expect(stageStart).toBeGreaterThan(mobileStart);
  });

  const mobileBranch = SRC.slice(mobileStart, stageStart);
  const desktopBranch = SRC.slice(stageStart);

  it("never renders the layout segmented control in the mobile branch", () => {
    expect(mobileBranch).not.toContain("LayoutModeToggle");
  });

  it("renders the layout segmented control in the desktop branch", () => {
    expect(desktopBranch).toContain("LayoutModeToggle");
  });

  it("renders the solve-readout HUD exactly three times: mobile Info screen, rail's primary slide, grid's stage level — never per grid cell", () => {
    const count = (SRC.match(/<SolveReadout/g) ?? []).length;
    expect(count).toBe(3);
  });

  it("never imports SolveReadout into the (per-cell) ViewGrid component", () => {
    expect(viewGridSrc).not.toContain("SolveReadout");
  });
});
