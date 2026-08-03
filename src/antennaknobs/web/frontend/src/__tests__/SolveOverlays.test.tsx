// Pins the conditional-rendering matrix of the solve-status overlays
// (src/components/session/SolveOverlays.tsx, issue #673): the cancel button's
// showBusy×solving gate, the two mutually-exclusive solver-mismatch banners
// (disallowed vs. poor-match) and their message-branch selection, and the
// solve-error alert. Every visibility assertion is paired with an absence
// assertion on a prop combination that must NOT show the element — a
// presence-only test still passes if the conditional is deleted.
//
// The disallowed banner's sub-text and "Switch to X" button run
// requiredBackends through normalizeBackend before display, which is the
// only thing standing between a stale/retired backend name ("triangular",
// still recommended by older adapters) and a broken switch action — that
// mapping gets its own adversarial case below, not just the happy path.
//
// The title/sub spans interleave a JSX expression with literal text as
// sibling text nodes, so they are read via textContent rather than
// getByText (which would need an awkward custom matcher for a node whose
// text is split across children) — plain textContent/property assertions,
// no jest-dom, matching the BackendConfigModal precedent.
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SolveOverlays } from "../components/session/SolveOverlays";
import { BACKEND_LABEL, normalizeBackend, type Backend } from "../lib/backends";

// --- fixtures --------------------------------------------------------------

type OverlayOverrides = Partial<{
  showBusy: boolean;
  solving: boolean;
  solverWarning: boolean;
  backendDisallowed: boolean;
  backend: Backend;
  requiredBackends: string[] | null;
  recommendedBackend: Backend | null;
  solveError: string | null;
}>;

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never
// got.
function renderOverlays(overrides: OverlayOverrides = {}) {
  const spies = {
    onCancelSolve: vi.fn(),
    onSwitchBackend: vi.fn(),
    onPause: vi.fn(),
    onSolveAnyway: vi.fn(),
  };
  const view = render(
    <SolveOverlays
      showBusy={false}
      solving={false}
      solverWarning={false}
      backendDisallowed={false}
      backend="bspline"
      requiredBackends={null}
      recommendedBackend={null}
      solveError={null}
      {...overrides}
      {...spies}
    />,
  );
  return { ...view, ...spies, user: userEvent.setup() };
}

function cancelButton() {
  return screen.queryByRole("button", { name: "Cancel solve" });
}

function disallowedBanner() {
  return screen.queryByRole("alertdialog", {
    name: "Solver unavailable for this design",
  });
}

function mismatchBanner() {
  return screen.queryByRole("alertdialog", { name: "Solver mismatch" });
}

// --- 1. Cancel button: showBusy × solving -----------------------------------

describe("SolveOverlays — cancel button", () => {
  it.each([
    [true, true, true],
    [true, false, false],
    [false, true, false],
    [false, false, false],
  ])("showBusy=%s solving=%s -> rendered=%s", (showBusy, solving, rendered) => {
    renderOverlays({ showBusy, solving });
    expect(cancelButton() !== null).toBe(rendered);
  });

  it("fires onCancelSolve when clicked", async () => {
    const { user, onCancelSolve } = renderOverlays({
      showBusy: true,
      solving: true,
    });
    await user.click(cancelButton() as HTMLElement);
    expect(onCancelSolve).toHaveBeenCalledTimes(1);
  });
});

// --- 2. Disallowed banner ----------------------------------------------------

describe("SolveOverlays — disallowed banner", () => {
  it("shows the backend-specific title", () => {
    renderOverlays({ solverWarning: true, backendDisallowed: true, backend: "hmatrix" });
    const banner = disallowedBanner();
    expect(banner?.querySelector(".solver-suggest-title")?.textContent).toBe(
      `${BACKEND_LABEL.hmatrix} can't run this design`,
    );
  });

  it.each([
    [null, "a supported solver"],
    [[], "a supported solver"],
    [["nosuch"], "a supported solver"],
    [["bspline", "sinusoidal-galerkin"], `${BACKEND_LABEL.bspline} / ${BACKEND_LABEL["sinusoidal-galerkin"]}`],
  ] as const)("lists requiredBackends %s as %s", (requiredBackends, expected) => {
    renderOverlays({
      solverWarning: true,
      backendDisallowed: true,
      requiredBackends: requiredBackends as string[] | null,
    });
    const sub = disallowedBanner()?.querySelector(".solver-suggest-sub")?.textContent ?? "";
    expect(sub).toContain(`Switch to ${expected} to solve it`);
  });

  it("offers a Switch-to primary button for the normalized first required backend", async () => {
    const { user, onSwitchBackend } = renderOverlays({
      solverWarning: true,
      backendDisallowed: true,
      requiredBackends: ["bspline", "pynec"],
    });
    const btn = screen.getByRole("button", { name: `Switch to ${BACKEND_LABEL.bspline}` });
    await user.click(btn);
    expect(onSwitchBackend).toHaveBeenCalledWith("bspline");
    expect(onSwitchBackend).toHaveBeenCalledTimes(1);
  });

  // normalizeBackend maps the retired "triangular" name to "bspline" — the
  // load-bearing mapping a stale recommendation depends on.
  it("normalizes a retired backend name (triangular) before offering the switch", async () => {
    expect(normalizeBackend("triangular")).toBe("bspline");
    const { user, onSwitchBackend } = renderOverlays({
      solverWarning: true,
      backendDisallowed: true,
      requiredBackends: ["triangular"],
    });
    const btn = screen.getByRole("button", { name: `Switch to ${BACKEND_LABEL.bspline}` });
    await user.click(btn);
    expect(onSwitchBackend).toHaveBeenCalledWith("bspline");
    expect(onSwitchBackend).toHaveBeenCalledTimes(1);
  });

  it("omits the primary button when the first required backend does not normalize", () => {
    renderOverlays({
      solverWarning: true,
      backendDisallowed: true,
      requiredBackends: ["nosuch"],
    });
    expect(screen.queryByRole("button", { name: /^Switch to/ })).toBeNull();
    const sub = disallowedBanner()?.querySelector(".solver-suggest-sub")?.textContent ?? "";
    expect(sub).toContain("Switch to a supported solver to solve it");
  });

  it("fires onPause when Pause simulation is clicked", async () => {
    const { user, onPause } = renderOverlays({
      solverWarning: true,
      backendDisallowed: true,
    });
    await user.click(screen.getByRole("button", { name: "Pause simulation" }));
    expect(onPause).toHaveBeenCalledTimes(1);
  });
});

// --- 3. Poor-match banner -----------------------------------------------------

describe("SolveOverlays — poor-match banner", () => {
  it("shows the backend-specific title", () => {
    renderOverlays({ solverWarning: true, backendDisallowed: false, backend: "arrayblock" });
    const banner = mismatchBanner();
    expect(banner?.querySelector(".solver-suggest-title")?.textContent).toBe(
      `${BACKEND_LABEL.arrayblock} is a poor match for this design`,
    );
  });

  it("shows the benchmark-sized message when recommendedBackend is sinusoidal", () => {
    renderOverlays({
      solverWarning: true,
      backendDisallowed: false,
      recommendedBackend: "sinusoidal",
      backend: "bspline",
    });
    const sub = mismatchBanner()?.querySelector(".solver-suggest-sub")?.textContent ?? "";
    expect(sub).toContain("This mesh is benchmark-sized");
  });

  it.each(["arrayblock", "hmatrix"] as const)(
    "shows the accelerator-overkill message for %s when there is no benchmark recommendation",
    (backend) => {
      renderOverlays({
        solverWarning: true,
        backendDisallowed: false,
        recommendedBackend: null,
        backend,
      });
      const sub = mismatchBanner()?.querySelector(".solver-suggest-sub")?.textContent ?? "";
      expect(sub).toContain("This accelerator is overkill on a single-element design");
    },
  );

  it("shows the large-array message for a non-accelerator backend with no benchmark recommendation", () => {
    renderOverlays({
      solverWarning: true,
      backendDisallowed: false,
      recommendedBackend: "arrayblock",
      backend: "pynec",
    });
    const sub = mismatchBanner()?.querySelector(".solver-suggest-sub")?.textContent ?? "";
    expect(sub).toContain("This is a large array");
  });

  // The sinusoidal-recommendation check comes first in the ternary: it must
  // win even for an accelerator backend that would otherwise match the
  // overkill branch.
  it("prioritizes the benchmark-sized message over the accelerator branch", () => {
    renderOverlays({
      solverWarning: true,
      backendDisallowed: false,
      recommendedBackend: "sinusoidal",
      backend: "arrayblock",
    });
    const sub = mismatchBanner()?.querySelector(".solver-suggest-sub")?.textContent ?? "";
    expect(sub).toContain("This mesh is benchmark-sized");
    expect(sub).not.toContain("overkill");
  });

  it("fires onSolveAnyway when Solve anyway is clicked", async () => {
    const { user, onSolveAnyway } = renderOverlays({
      solverWarning: true,
      backendDisallowed: false,
    });
    await user.click(screen.getByRole("button", { name: "Solve anyway" }));
    expect(onSolveAnyway).toHaveBeenCalledTimes(1);
  });

  it("fires onPause when Pause simulation is clicked", async () => {
    const { user, onPause } = renderOverlays({
      solverWarning: true,
      backendDisallowed: false,
    });
    await user.click(screen.getByRole("button", { name: "Pause simulation" }));
    expect(onPause).toHaveBeenCalledTimes(1);
  });
});

// --- 4. Mutual exclusion ------------------------------------------------------

describe("SolveOverlays — banner mutual exclusion", () => {
  it("renders only the disallowed banner when backendDisallowed is true", () => {
    renderOverlays({ solverWarning: true, backendDisallowed: true });
    expect(disallowedBanner()).not.toBeNull();
    expect(mismatchBanner()).toBeNull();
  });

  it("renders only the poor-match banner when backendDisallowed is false", () => {
    renderOverlays({ solverWarning: true, backendDisallowed: false });
    expect(mismatchBanner()).not.toBeNull();
    expect(disallowedBanner()).toBeNull();
  });

  it.each([true, false])(
    "renders neither banner when solverWarning is false (backendDisallowed=%s)",
    (backendDisallowed) => {
      renderOverlays({ solverWarning: false, backendDisallowed });
      expect(disallowedBanner()).toBeNull();
      expect(mismatchBanner()).toBeNull();
    },
  );
});

// --- 5. Solve error ------------------------------------------------------------

describe("SolveOverlays — solve error", () => {
  it("shows the error text inside a <code> element", () => {
    renderOverlays({ solveError: "singular matrix at segment 12" });
    const alert = screen.getByRole("alert");
    const code = alert.querySelector("code");
    expect(code?.tagName).toBe("CODE");
    expect(code?.textContent).toBe("singular matrix at segment 12");
  });

  it("omits the alert when solveError is null", () => {
    renderOverlays({ solveError: null });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
