// Pins the "All views" overflow picker and the two rules that only bite on a
// roster bigger than the five views we ship today: the 6-pin cap and the NEW
// badge (unit 2 of docs/plan-view-rail-scaling.md).
//
// The registry is mocked up to the plan's 9-view design target rather than
// waiting for those views to exist — with 5 real views the cap is
// unreachable, and every real view is in the picker's `seen` seed, so nothing
// could ever badge. The mock is the roster of a NEAR-FUTURE release, which is
// exactly the situation both rules are written for.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, renderHook, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

vi.mock("../lib/view", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/view")>();
  // Ids outside the shipped `View` union, so they need the cast the real
  // registry does not.
  const soon = [
    { id: "gamma", label: "|Γ| vs freq", defaultPinned: false },
    { id: "vswr", label: "VSWR vs freq", defaultPinned: false },
    { id: "optim", label: "Optimization", defaultPinned: false },
    { id: "converge", label: "Convergence", defaultPinned: false },
  ] as unknown as typeof actual.VIEWS;
  const VIEWS = [...actual.VIEWS, ...soon];
  return {
    ...actual,
    VIEWS,
    VIEW_META: Object.fromEntries(VIEWS.map((v) => [v.id, v])),
  };
});

// Imported AFTER the mock declaration for readability only — vi.mock is
// hoisted above every import in this file.
import type { View } from "../lib/view";
import { VIEW_PREFS_KEY, useViewPrefs } from "../components/session/useViewPrefs";
import { ViewPicker } from "../components/session/ViewPicker";

const FOUNDING: View[] = ["antenna", "azimuth", "elevation", "smith"];
const SHIPPED = [...FOUNDING, "schematic"];
const SOON = ["gamma", "vswr", "optim", "converge"];

beforeEach(() => {
  localStorage.clear();
});

// The picker as DesignSession wires it: real prefs hook, real active-view
// state, plus probes for the two things the rail derives.
function Harness({ initialView = "antenna" as View }) {
  const [view, setView] = useState<View>(initialView);
  const prefs = useViewPrefs();
  return (
    <>
      <div data-testid="view">{view}</div>
      <div data-testid="pinned">{prefs.pinned.join(",")}</div>
      <div data-testid="rail">
        {prefs.railViews(view).map((v) => v.id).join(",")}
      </div>
      <ViewPicker
        view={view}
        setView={setView}
        pinned={prefs.pinned}
        newIds={prefs.newIds}
        togglePin={prefs.togglePin}
        markRosterSeen={prefs.markRosterSeen}
      />
    </>
  );
}

const probe = (id: string) => screen.getByTestId(id).textContent;
const openPicker = async (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: /all views/i }));
const dot = (label: string | RegExp) =>
  screen.getByRole("button", { name: label });
const rows = () =>
  screen
    .getAllByRole("menuitem")
    .map((el) => el.textContent?.replace(/NEW$/, "") ?? "");

// --- 1. The button ----------------------------------------------------------

describe("the All-views button", () => {
  it("counts the unpinned views", () => {
    render(<Harness />);
    // 9 views, 4 pinned by default.
    expect(
      screen.getByRole("button", { name: /all views/i }).textContent,
    ).toContain("+5");
  });
});

// --- 2. The roster listing --------------------------------------------------

describe("the picker popover", () => {
  it("lists the whole roster in registry order", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    expect(rows()).toEqual([
      "Antenna",
      "Azimuth (xy)",
      "Elevation (yz)",
      "Smith",
      "Schematic",
      "|Γ| vs freq",
      "VSWR vs freq",
      "Optimization",
      "Convergence",
    ]);
  });

  it("marks the active row", async () => {
    const user = userEvent.setup();
    render(<Harness initialView={"smith" as View} />);
    await openPicker(user);
    const current = screen
      .getAllByRole("menuitem")
      .filter((el) => el.getAttribute("aria-current") === "true");
    expect(current.map((el) => el.textContent)).toEqual(["Smith"]);
  });

  it("closes on a backdrop click", async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);
    await openPicker(user);
    await user.click(container.querySelector(".view-picker-backdrop") as Element);
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

// --- 3. Row click vs. dot click ---------------------------------------------

describe("row click", () => {
  it("shows an unpinned view WITHOUT pinning it (peek), and closes", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    await user.click(screen.getByRole("menuitem", { name: "Schematic" }));
    expect(probe("view")).toBe("schematic");
    expect(probe("pinned")).toBe(FOUNDING.join(","));
    // Peek displaces no thumb: the rail is every pin.
    expect(probe("rail")).toBe(FOUNDING.join(","));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("switches to a pinned view and drops it from the rail", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    await user.click(screen.getByRole("menuitem", { name: "Smith" }));
    expect(probe("view")).toBe("smith");
    expect(probe("rail")).toBe("antenna,azimuth,elevation");
  });
});

describe("pin-dot click", () => {
  it("toggles the pin without switching the view or closing", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    await user.click(dot("Pin Schematic"));
    expect(probe("pinned")).toBe([...FOUNDING, "schematic"].join(","));
    expect(probe("view")).toBe("antenna");
    expect(screen.getByRole("menu")).not.toBeNull();
    // Curating is a run of gestures, so the dot stays available, now inverted.
    await user.click(dot("Unpin Schematic"));
    expect(probe("pinned")).toBe(FOUNDING.join(","));
    expect(probe("view")).toBe("antenna");
  });

  it("appends new pins in the order pinned (no reorder in v1)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    await user.click(dot("Pin VSWR vs freq"));
    await user.click(dot("Pin Schematic"));
    expect(probe("pinned")).toBe([...FOUNDING, "vswr", "schematic"].join(","));
  });
});

// --- 4. The cap -------------------------------------------------------------

describe("the 6-pin cap", () => {
  it("refuses a 7th pin and disables its dot", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    await user.click(dot("Pin Schematic"));
    await user.click(dot("Pin |Γ| vs freq"));
    const capped = [...FOUNDING, "schematic", "gamma"].join(",");
    expect(probe("pinned")).toBe(capped);

    // Every remaining unpinned dot is now inert, and says why.
    for (const label of ["Pin VSWR vs freq", "Pin Optimization", "Pin Convergence"]) {
      expect((dot(label) as HTMLButtonElement).disabled).toBe(true);
      expect(dot(label).getAttribute("title")).toBe("Unpin a view first");
    }
    // Pointer events cannot reach a disabled button, so drive the model
    // directly to prove the refusal is the hook's, not just the DOM's.
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin("vswr" as View));
    expect(result.current.pinned.join(",")).toBe(capped);

    // Unpinning frees exactly one slot.
    await user.click(dot("Unpin Smith"));
    expect((dot("Pin VSWR vs freq") as HTMLButtonElement).disabled).toBe(false);
  });

  it("clamps an over-full stored record on load", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: [...SHIPPED, ...SOON], seen: [] }),
    );
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual([...SHIPPED, "gamma"]);
  });
});

// --- 5. The NEW badge -------------------------------------------------------

const badges = () =>
  screen.getAllByText("NEW").map((el) => el.parentElement?.textContent ?? "");

describe("the NEW badge", () => {
  it("marks views the seed does not cover, and stops after the picker is opened", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    // The five pre-picker views are seeded as seen; the four later ones are
    // announced even though they ship unpinned.
    expect(badges()).toEqual([
      "|Γ| vs freqNEW",
      "VSWR vs freqNEW",
      "OptimizationNEW",
      "ConvergenceNEW",
    ]);
    // Opening is what marks them seen — but the badges must survive the open
    // that revealed them.
    expect(JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}").seen).toEqual([
      ...SHIPPED,
      ...SOON,
    ]);

    await user.click(screen.getByRole("button", { name: /all views/i }));
    await openPicker(user);
    expect(screen.queryByText("NEW")).toBeNull();
  });

  it("badges nothing when the stored seen already covers the roster", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: FOUNDING, seen: [...SHIPPED, ...SOON] }),
    );
    render(<Harness />);
    await openPicker(user);
    expect(screen.queryByText("NEW")).toBeNull();
  });
});
