// Pins the "All views" overflow picker and the one rule that only bites on a
// roster bigger than the cap: the 6-pin limit (unit 2 of
// docs/plan-view-rail-scaling.md).
//
// The registry is mocked up to the plan's 9-view design target rather than
// waiting for those views to exist: the cap cannot be reached while the
// shipped roster is smaller than six. The mock is the roster of a NEAR-FUTURE
// release, which is exactly the situation the rule is written for.
//
// Every expectation below is derived from the mocked VIEWS, so the roster
// growing under this file (as it did when |Γ| and VSWR landed mid-unit)
// changes nothing here.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, renderHook, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

vi.mock("../lib/view", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/view")>();
  // Tops the shipped roster up past the cap with the plan's two still-unbuilt
  // views (items 8/9). Ids already shipped are skipped — a sibling unit
  // landing one of these for real must not produce a duplicate row, which is
  // precisely how this mock broke when |Γ| and VSWR shipped. Their ids sit
  // outside the shipped `View` union, hence the cast the real registry
  // does not need.
  const soon = [
    { id: "optim", label: "Optimization", defaultPinned: false },
    { id: "converge", label: "Convergence", defaultPinned: false },
  ].filter((v) => !actual.VIEWS.some((a) => a.id === v.id)) as unknown as typeof actual.VIEWS;
  const VIEWS = [...actual.VIEWS, ...soon];
  return {
    ...actual,
    VIEWS,
    VIEW_META: Object.fromEntries(VIEWS.map((v) => [v.id, v])),
  };
});

// Imported AFTER the mock declaration for readability only — vi.mock is
// hoisted above every import in this file. VIEWS/VIEW_META here are the
// mocked ones; PIN_CAP and the hook are real.
import { VIEW_META, VIEWS, type View } from "../lib/view";
import {
  PIN_CAP,
  VIEW_PREFS_KEY,
  useViewPrefs,
} from "../components/session/useViewPrefs";
import { ViewPicker } from "../components/session/ViewPicker";

const FOUNDING: View[] = ["antenna", "azimuth", "elevation", "smith"];
const ROSTER = VIEWS.map((v) => v.id);
// A deliberate mirror of useViewPrefs' SEEN_SEED (not exported: it is a
// frozen historical fact, not a knob). Copying it here means a change to the
// production seed shows up as a failure in the badge tests, which is where
// the seed's whole meaning lives.
const PRE_PICKER: View[] = ["antenna", "azimuth", "elevation", "smith", "schematic"];
const label = (id: View) => VIEW_META[id].label;

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
    expect(
      screen.getByRole("button", { name: /all views/i }).textContent,
    ).toContain(`+${ROSTER.length - FOUNDING.length}`);
  });
});

// --- 2. The roster listing --------------------------------------------------

describe("the picker popover", () => {
  it("lists the whole roster in registry order", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    // The WHOLE roster, pinned or not, in registry order — that is the
    // picker's contract with every view that ships after it.
    expect(rows()).toEqual(ROSTER.map(label));
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
    // Pinned bottom-up, so registry order would give the opposite answer.
    const spare = ROSTER.filter((id) => !FOUNDING.includes(id));
    const [first, last] = [spare[0], spare[spare.length - 1]];
    await user.click(dot(`Pin ${label(last)}`));
    await user.click(dot(`Pin ${label(first)}`));
    expect(probe("pinned")).toBe([...FOUNDING, last, first].join(","));
  });
});

// --- 4. The cap -------------------------------------------------------------

describe("the 6-pin cap", () => {
  // The mocked roster exists to make this reachable at all.
  const spare = ROSTER.filter((id) => !FOUNDING.includes(id));
  const capped = [...FOUNDING, ...spare.slice(0, PIN_CAP - FOUNDING.length)];
  const refused = ROSTER.filter((id) => !capped.includes(id));

  it("has a roster that can actually overrun the cap", () => {
    expect(capped).toHaveLength(PIN_CAP);
    expect(refused.length).toBeGreaterThan(0);
  });

  it(`refuses pin ${PIN_CAP + 1} and disables its dot`, async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    for (const id of capped.filter((id) => !FOUNDING.includes(id))) {
      await user.click(dot(`Pin ${label(id)}`));
    }
    expect(probe("pinned")).toBe(capped.join(","));

    // Every remaining unpinned dot is now inert, and says why.
    for (const id of refused) {
      const d = dot(`Pin ${label(id)}`) as HTMLButtonElement;
      expect(d.disabled).toBe(true);
      expect(d.getAttribute("title")).toBe("Unpin a view first");
    }
    // Pointer events cannot reach a disabled button, so drive the model
    // directly to prove the refusal is the hook's, not just the DOM's.
    const { result } = renderHook(() => useViewPrefs());
    act(() => result.current.togglePin(refused[0]));
    expect(result.current.pinned.join(",")).toBe(capped.join(","));

    // Unpinning frees exactly one slot.
    await user.click(dot(`Unpin ${label(FOUNDING[3])}`));
    expect((dot(`Pin ${label(refused[0])}`) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("clamps an over-full stored record on load", () => {
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: ROSTER, seen: [] }),
    );
    const { result } = renderHook(() => useViewPrefs());
    expect(result.current.pinned).toEqual(ROSTER.slice(0, PIN_CAP));
  });
});

// --- 5. The NEW badge -------------------------------------------------------

const badges = () =>
  screen.getAllByText("NEW").map((el) => el.parentElement?.textContent ?? "");

const POST_PICKER = ROSTER.filter((id) => !PRE_PICKER.includes(id));

describe("the NEW badge", () => {
  it("marks views the seed does not cover, and stops after the picker is opened", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await openPicker(user);
    // The pre-picker views are seeded as seen; everything that shipped after
    // is announced, even though it all ships unpinned.
    expect(badges()).toEqual(POST_PICKER.map((id) => `${label(id)}NEW`));
    // Opening is what marks them seen — but the badges must survive the open
    // that revealed them.
    expect(JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}").seen).toEqual([
      ...PRE_PICKER,
      ...POST_PICKER,
    ]);

    await user.click(screen.getByRole("button", { name: /all views/i }));
    await openPicker(user);
    expect(screen.queryByText("NEW")).toBeNull();
  });

  it("badges nothing when the stored seen already covers the roster", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      VIEW_PREFS_KEY,
      JSON.stringify({ pinned: FOUNDING, seen: ROSTER }),
    );
    render(<Harness />);
    await openPicker(user);
    expect(screen.queryByText("NEW")).toBeNull();
  });
});
