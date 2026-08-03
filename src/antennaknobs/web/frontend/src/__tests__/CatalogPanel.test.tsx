// Pins the conditional-rendering matrix of src/components/session/CatalogPanel.tsx
// (issue #673): the variant-select visibility gate, the design-note and
// examples-error banners, and — the load-bearing bit — the trust_required
// split that routes a design-load error into either the AwaitingTrustPanel
// (loaded fine, awaiting a trust decision) or the plain "failed to load"
// alert, never both. Every conditional-presence assertion is paired with an
// absence assertion so a deleted guard still fails the suite.
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CatalogPanel } from "../components/session/CatalogPanel";
import type { DesignLoadError } from "../components/AwaitingTrustPanel";
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

function loadError(overrides: Partial<DesignLoadError> = {}): DesignLoadError {
  return {
    name: "some_design",
    file: "some_design.py",
    message: "boom",
    ...overrides,
  };
}

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never got.
type PanelOverrides = Partial<{
  geomGroups: ExampleGroup[];
  geometry: string;
  currentExample: ExampleDescriptor | undefined;
  geomFilter: string;
  currentVariant: string;
  examplesError: string | null;
  loadErrors: DesignLoadError[];
  trustBusy: string | null;
}>;

function renderPanel(overrides: PanelOverrides = {}) {
  const spies = {
    setGeomFilter: vi.fn(),
    setGeometry: vi.fn(),
    selectVariant: vi.fn(),
    trustDesign: vi.fn(),
  };
  const defaultExample = example();
  const props = {
    geomGroups: [group({ items: [defaultExample] })],
    geometry: defaultExample.name,
    currentExample: defaultExample,
    geomFilter: "",
    currentVariant: "default",
    examplesError: null,
    loadErrors: [],
    trustBusy: null,
    ...overrides,
    ...spies,
  };
  const view = render(<CatalogPanel {...props} />);
  return { ...view, ...spies, user: userEvent.setup() };
}

function variantSelect(): HTMLSelectElement | null {
  return screen.queryByRole("combobox", { name: "variant" }) as HTMLSelectElement | null;
}

describe("CatalogPanel — variant select", () => {
  it("shows the select when there is more than one variant", () => {
    renderPanel({ currentExample: example({ variants: ["default", "opt"] }) });
    expect(variantSelect()).not.toBeNull();
  });

  it("hides the select for exactly one variant", () => {
    renderPanel({ currentExample: example({ variants: ["default"] }) });
    expect(variantSelect()).toBeNull();
  });

  it("hides the select when currentExample is undefined", () => {
    renderPanel({ currentExample: undefined });
    expect(variantSelect()).toBeNull();
  });

  it("lists the variants as options and follows currentVariant", () => {
    renderPanel({
      currentExample: example({ variants: ["default", "opt"] }),
      currentVariant: "opt",
    });
    const select = variantSelect()!;
    expect(select.value).toBe("opt");
    const optionValues = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(optionValues).toEqual(["default", "opt"]);
  });

  it("fires selectVariant with the chosen value on change", async () => {
    const { user, selectVariant } = renderPanel({
      currentExample: example({ variants: ["default", "opt"] }),
      currentVariant: "default",
    });
    await user.selectOptions(variantSelect()!, "opt");
    expect(selectVariant).toHaveBeenCalledWith("opt");
    expect(selectVariant).toHaveBeenCalledTimes(1);
  });
});

describe("CatalogPanel — design note", () => {
  it("renders currentExample.notes in .design-note", () => {
    const { container } = renderPanel({
      currentExample: example({ notes: "careful with the feed point" }),
    });
    const note = container.querySelector(".design-note");
    expect(note).not.toBeNull();
    expect(note?.textContent).toBe("careful with the feed point");
  });

  it.each([undefined, null, ""] as const)(
    "hides .design-note when notes is %s",
    (notes) => {
      const { container } = renderPanel({ currentExample: example({ notes }) });
      expect(container.querySelector(".design-note")).toBeNull();
    },
  );
});

describe("CatalogPanel — examplesError", () => {
  it("shows the failed-to-load banner with the message", () => {
    renderPanel({ examplesError: "network down" });
    expect(screen.getByText("Failed to load /examples: network down")).not.toBeNull();
  });

  it("hides the banner when examplesError is null", () => {
    renderPanel({ examplesError: null });
    expect(screen.queryByText(/Failed to load \/examples/)).toBeNull();
  });
});

describe("CatalogPanel — trust gate (AwaitingTrustPanel)", () => {
  it("renders the trust summary with singular wording for one pending design", () => {
    renderPanel({ loadErrors: [loadError({ name: "a", trust_required: true })] });
    expect(
      screen.getByRole("button", { name: "1 design needs your OK to run" }),
    ).not.toBeNull();
  });

  it("renders the trust summary with plural wording for two pending designs", () => {
    renderPanel({
      loadErrors: [
        loadError({ name: "a", trust_required: true }),
        loadError({ name: "b", trust_required: true }),
      ],
    });
    expect(
      screen.getByRole("button", { name: "2 designs need your OK to run" }),
    ).not.toBeNull();
  });

  it("hides the trust panel when no entry has trust_required", () => {
    renderPanel({
      loadErrors: [loadError({ name: "a", trust_required: false })],
    });
    expect(screen.queryByText(/need your OK to run/)).toBeNull();
  });
});

describe("CatalogPanel — plain load errors", () => {
  it("shows the alert with singular wording and the error's fields for one error", () => {
    renderPanel({
      loadErrors: [loadError({ name: "broke", message: "SyntaxError", file: "broke.py" })],
    });
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("1 design failed to load")).not.toBeNull();
    const item = within(alert).getByText("broke").closest("li");
    expect(item).not.toBeNull();
    expect(item?.textContent).toContain("SyntaxError");
    expect(item?.textContent).toContain("broke.py");
  });

  it("shows the alert with plural wording and one <li> per error for two errors", () => {
    renderPanel({
      loadErrors: [
        loadError({ name: "a", message: "m1", file: "a.py" }),
        loadError({ name: "b", message: "m2", file: "b.py" }),
      ],
    });
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("2 designs failed to load")).not.toBeNull();
    expect(within(alert).getAllByRole("listitem")).toHaveLength(2);
  });

  it("hides the alert when every entry has trust_required", () => {
    renderPanel({ loadErrors: [loadError({ name: "a", trust_required: true })] });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("CatalogPanel — mixed loadErrors (the trust_required split)", () => {
  it("routes each entry to exactly one panel: pending -> trust list, broken -> alert list", async () => {
    const { user } = renderPanel({
      loadErrors: [
        loadError({ name: "pending_design", trust_required: true }),
        loadError({
          name: "broken_design",
          message: "boom",
          file: "broken_design.py",
          trust_required: false,
        }),
      ],
    });

    const trustButton = screen.getByRole("button", {
      name: "1 design needs your OK to run",
    });
    const trustPanel = trustButton.closest(".design-trust-panel") as HTMLElement;
    await user.click(trustButton); // expand to reveal the per-design list
    expect(within(trustPanel).getByText("pending_design")).not.toBeNull();
    expect(within(trustPanel).queryByText("broken_design")).toBeNull();

    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("broken_design")).not.toBeNull();
    expect(within(alert).queryByText("pending_design")).toBeNull();
  });
});

describe("CatalogPanel — adversarial", () => {
  it("renders neither panel when loadErrors is empty", () => {
    renderPanel({ loadErrors: [] });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText(/need your OK to run/)).toBeNull();
  });
});
