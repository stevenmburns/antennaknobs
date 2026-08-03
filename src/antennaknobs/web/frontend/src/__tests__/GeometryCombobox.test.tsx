// Pins the controlled-filter combobox in src/components/params/GeometryCombobox.tsx
// (issue #673): the component owns only open/active state — `filter` and
// `setFilter` are props the parent normally reconciles, so any assertion that
// depends on the displayed filter text rerenders with the new prop after
// asserting the setFilter call, exactly as the real parent would. Keyboard
// navigation is pinned across a group boundary so the flat-index math (not
// per-group indices) is what's under test.
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GeometryCombobox } from "../components/params/GeometryCombobox";
import type { ExampleDescriptor, ExampleGroup } from "../lib/params";

// --- fixtures --------------------------------------------------------------
// Real (fully-typed) minimal objects rather than `as` casts, so every field
// the component might read is present and type-checked.

function example(overrides: Partial<ExampleDescriptor> = {}): ExampleDescriptor {
  return {
    name: "dipole.test",
    label: "Test Dipole",
    multi_feed: false,
    param_schema: [],
    result_schema: [],
    bands: [],
    meas_freq_range_mhz: null,
    default_view: null,
    default_freq: null,
    default_design_freq: null,
    default_backend: null,
    requires_backends: null,
    has_design_freq: true,
    variants: ["default"],
    variant_values: {},
    sweep_policy: { anchor: "design_freq", lo_factor: 0.5, hi_factor: 2 },
    ...overrides,
  };
}

function group(overrides: Partial<ExampleGroup> = {}): ExampleGroup {
  return {
    fam: "dipole",
    label: "Dipoles",
    items: [example()],
    ...overrides,
  };
}

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never got.
type ComboboxOverrides = Partial<{
  groups: ExampleGroup[];
  selected: string;
  currentLabel: string;
  filter: string;
}>;

function renderCombobox(overrides: ComboboxOverrides = {}) {
  const spies = { setFilter: vi.fn(), onSelect: vi.fn() };
  const props = {
    groups: [group()],
    selected: "dipole.test",
    currentLabel: "Test Dipole",
    filter: "",
    ...overrides,
    ...spies,
  };
  const view = render(<GeometryCombobox {...props} />);
  // Mirrors what the real parent does after a setFilter call: re-render with
  // the new filter value, everything else unchanged.
  const rerenderWithFilter = (filter: string) =>
    view.rerender(<GeometryCombobox {...props} filter={filter} />);
  return { ...view, ...spies, rerenderWithFilter, user: userEvent.setup() };
}

function input(): HTMLInputElement {
  return screen.getByRole("combobox") as HTMLInputElement;
}

describe("GeometryCombobox — closed/open display", () => {
  it("closed: aria-expanded false, value is currentLabel, no listbox", () => {
    renderCombobox({ currentLabel: "Test Dipole", filter: "stale filter text" });
    expect(input().getAttribute("aria-expanded")).toBe("false");
    expect(input().value).toBe("Test Dipole");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("open (focused): aria-expanded true, value is the filter prop, listbox appears", async () => {
    const { user } = renderCombobox({ currentLabel: "Test Dipole", filter: "di" });
    await user.click(input());
    expect(input().getAttribute("aria-expanded")).toBe("true");
    expect(input().value).toBe("di");
    expect(screen.queryByRole("listbox")).not.toBeNull();
  });
});

describe("GeometryCombobox — typing", () => {
  // A single keystroke: with setFilter mocked (a no-op), the filter prop
  // never advances, so a second keystroke would type into a field the
  // component has re-rendered back to "" — a real controlled-input effect,
  // not a test bug. One character keeps the assertion about what onChange
  // actually reports, not about the mock's inability to drive a rerender.
  it("calls setFilter with the typed character and opens the list", async () => {
    const { user, setFilter } = renderCombobox({ filter: "" });
    await user.type(input(), "y");
    expect(setFilter).toHaveBeenCalledWith("y");
    expect(input().getAttribute("aria-expanded")).toBe("true");
  });

  it("shows the new text once the parent reconciles the filter prop", async () => {
    const { user, setFilter, rerenderWithFilter } = renderCombobox({ filter: "" });
    await user.type(input(), "y");
    expect(setFilter).toHaveBeenCalledWith("y");
    rerenderWithFilter("y");
    expect(input().value).toBe("y");
  });
});

describe("GeometryCombobox — list rendering", () => {
  it("renders group labels and options; marks the selected and active items", async () => {
    const g = group({
      fam: "dipole",
      label: "Dipoles",
      items: [example({ name: "d1", label: "D1" }), example({ name: "d2", label: "D2" })],
    });
    const { user } = renderCombobox({ groups: [g], selected: "d2" });
    await user.click(input());
    expect(screen.getByText("Dipoles")).not.toBeNull();

    const opt1 = screen.getByRole("option", { name: "D1" });
    const opt2 = screen.getByRole("option", { name: "D2" });
    expect(opt1.getAttribute("aria-selected")).toBe("false");
    expect(opt2.getAttribute("aria-selected")).toBe("true");
    // active starts at flat index 0 -> the first item, not the selected one.
    expect(opt1.className).toContain("is-active");
    expect(opt2.className).not.toContain("is-active");
  });

  it("shows 'no antennas match' and no options when every group is empty", async () => {
    const { user } = renderCombobox({ groups: [group({ items: [] })] });
    await user.click(input());
    expect(screen.getByText("no antennas match")).not.toBeNull();
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });
});

describe("GeometryCombobox — keyboard", () => {
  function twoGroups(): ExampleGroup[] {
    return [
      group({
        fam: "g1",
        label: "G1",
        items: [example({ name: "a", label: "A" }), example({ name: "b", label: "B" })],
      }),
      group({
        fam: "g2",
        label: "G2",
        items: [example({ name: "c", label: "C" }), example({ name: "d", label: "D" })],
      }),
    ];
  }

  it("ArrowDown moves the active option forward across a group boundary, clamped at the end", async () => {
    const { user } = renderCombobox({ groups: twoGroups(), selected: "a" });
    await user.click(input());
    expect(screen.getByRole("option", { name: "A" }).className).toContain("is-active");

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: "B" }).className).toContain("is-active");
    expect(screen.getByRole("option", { name: "A" }).className).not.toContain("is-active");

    await user.keyboard("{ArrowDown}"); // crosses from group g1 into g2
    expect(screen.getByRole("option", { name: "C" }).className).toContain("is-active");

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: "D" }).className).toContain("is-active");

    await user.keyboard("{ArrowDown}"); // already at the last flat item
    expect(screen.getByRole("option", { name: "D" }).className).toContain("is-active");
  });

  it("ArrowUp moves the active option back and stops at 0", async () => {
    const { user } = renderCombobox({ groups: twoGroups(), selected: "a" });
    await user.click(input());
    await user.keyboard("{ArrowDown}{ArrowDown}"); // active -> "c" (flat index 2)
    expect(screen.getByRole("option", { name: "C" }).className).toContain("is-active");

    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("option", { name: "B" }).className).toContain("is-active");

    await user.keyboard("{ArrowUp}{ArrowUp}{ArrowUp}"); // overshoot below 0
    expect(screen.getByRole("option", { name: "A" }).className).toContain("is-active");
  });

  it("Enter with the list open chooses the active item", async () => {
    const g = group({
      items: [example({ name: "a", label: "A" }), example({ name: "b", label: "B" })],
    });
    const { user, onSelect, setFilter } = renderCombobox({
      groups: [g],
      selected: "a",
      filter: "x",
    });
    await user.click(input());
    await user.keyboard("{ArrowDown}"); // active -> "b"
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("b");
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(setFilter).toHaveBeenCalledWith("");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("Escape closes and clears the filter WITHOUT selecting", async () => {
    const { user, onSelect, setFilter } = renderCombobox({ filter: "x" });
    await user.click(input());
    expect(screen.queryByRole("listbox")).not.toBeNull();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(setFilter).toHaveBeenCalledWith("");
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe("GeometryCombobox — mouse", () => {
  it("mousedown on an option chooses it", async () => {
    const g = group({
      items: [example({ name: "a", label: "A" }), example({ name: "b", label: "B" })],
    });
    const { user, onSelect, setFilter } = renderCombobox({ groups: [g], selected: "a" });
    await user.click(input());
    await user.click(screen.getByRole("option", { name: "B" }));
    expect(onSelect).toHaveBeenCalledWith("b");
    expect(setFilter).toHaveBeenCalledWith("");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("mousedown outside the component closes the list and clears the filter", async () => {
    const setFilter = vi.fn();
    const onSelect = vi.fn();
    render(
      <div>
        <GeometryCombobox
          groups={[group()]}
          selected="dipole.test"
          currentLabel="Test Dipole"
          filter="abc"
          setFilter={setFilter}
          onSelect={onSelect}
        />
        <button>outside target</button>
      </div>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox"));
    expect(screen.queryByRole("listbox")).not.toBeNull();

    await user.click(screen.getByText("outside target"));
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(setFilter).toHaveBeenCalledWith("");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("mousedown on the caret toggles open/closed", async () => {
    const { user, container } = renderCombobox();
    const caret = container.querySelector(".combobox-caret");
    expect(caret).not.toBeNull();

    expect(screen.queryByRole("listbox")).toBeNull();
    await user.click(caret as HTMLElement);
    expect(screen.queryByRole("listbox")).not.toBeNull();

    await user.click(caret as HTMLElement);
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

describe("GeometryCombobox — adversarial", () => {
  it("has no listbox in the DOM while closed", () => {
    renderCombobox();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("Enter with the list closed fires no onSelect", () => {
    const { onSelect } = renderCombobox();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(onSelect).not.toHaveBeenCalled();
  });
});
