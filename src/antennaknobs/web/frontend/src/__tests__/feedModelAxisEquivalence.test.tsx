/**
 * The axis-derived feed-model control renders what the `panel` hint used to
 * (#1006 G2-5).
 *
 * `BackendConfigModal` no longer branches on `PANEL_SIN_GALERKIN` anywhere;
 * the control appears when the `feed_model` axis is multi-valued. This file is
 * the evidence that the swap was behaviour-preserving, which is the condition
 * the hint was allowed to be removed under.
 *
 * WHAT WAS ACTUALLY REMOVED, precisely — the hint did not vanish, it was
 * DEMOTED. Four `panel === PANEL_SIN_GALERKIN` branches (the modal's render,
 * `defaultOptsFor`, `backendDisplayLabel`, `buildModelOptions`) became
 * `offersFeedModelChoice`. The constant survives in exactly one place, inside
 * `feedModelChoices`, as the answer for a momwire that cannot describe itself.
 *
 * That fallback is load-bearing rather than defensive: `axes` is null on every
 * momwire predating the axis vocabulary, and the submodule pointer runs ahead
 * of the PyPI pin BY DESIGN here, so the released package users install
 * answers null today. A version probe cannot tell the two apart — momwire
 * reports 0.47.0 with and without the vocabulary — which is why the code
 * probes for the feature and why the null case below is a real shipping
 * configuration and not a museum piece.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { BackendConfigModal } from "../components/backend/BackendConfigModal";
import {
  PANEL_SIN_GALERKIN,
  defaultOptsFor,
  feedModelChoices,
  offersFeedModelChoice,
  modelOptionsForRequest,
  backendDisplayLabel,
  type BackendEntry,
} from "../lib/backends";
import { entry, optsWithModel, SERVED_ROSTER,
  SERVED_VOCAB,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

function renderModal(b: BackendEntry) {
  return render(
    <BackendConfigModal
      slot="A"
      backend={b}
      backends={SERVED_ROSTER}
      requiredBackends={null}
      design={{}}
      specs={SERVED_OPTION_SPECS}
      vocab={SERVED_VOCAB}
      designRefusalNote={null}
      suggestConvergedFeed={false}
      opts={defaultOptsFor(b, SERVED_OPTION_SPECS)}
      onChangeBackend={vi.fn()}
      onPatch={vi.fn()}
      onReset={vi.fn()}
      onClose={vi.fn()}
    />,
  );
}

function tabsIn(caption: string) {
  const field = screen.queryByText(caption)?.closest(".field");
  if (!field) return null;
  return within(field as HTMLElement)
    .getAllByRole("tab")
    .map((t) => t.textContent);
}

function feedTabs(b: BackendEntry) {
  renderModal(b);
  return tabsIn("feed model");
}

describe("the axis path and the retired hint path agree on the served roster", () => {
  it.each(SERVED_ROSTER.map((b) => b.name))(
    "offersFeedModelChoice(%s) matches the old panel hint",
    (name) => {
      const b = entry(name);
      expect(offersFeedModelChoice(b)).toBe(b.panel === PANEL_SIN_GALERKIN);
    },
  );

  it("is not passing because both sides are always false", () => {
    // The guard the equivalence claim needs: exactly one served backend is
    // supposed to offer the choice. Without this, deleting the control
    // entirely would satisfy every case above.
    const offering = SERVED_ROSTER.filter(offersFeedModelChoice).map((b) => b.name);
    expect(offering).toEqual(["sinusoidal-galerkin"]);
  });

  it("renders the same two tabs, with the same labels and order", () => {
    expect(feedTabs(entry("sinusoidal-galerkin"))).toEqual([
      "NEC-compatible",
      "Converged",
    ]);
  });

  it("still shows no feed-model control on plain sinusoidal", () => {
    // The absence assertion. `sinusoidal` declares feed_model:
    // ["segment-gap"] — it HAS a feed model and no choice of one (the point
    // gap has no collocation RHS, momwire#212). A rule keyed on the axis
    // EXISTING rather than on it being multi-valued would light this up.
    expect(entry("sinusoidal").axes!.feed_model).toEqual(["segment-gap"]);
    expect(feedTabs(entry("sinusoidal"))).toBeNull();
  });

  it("keeps the wire payload identical either way", () => {
    // The three non-render branches that also moved off the hint. A control
    // that renders the same but sends a different request would be the worse
    // failure, because nothing on screen would say so.
    const sg = entry("sinusoidal-galerkin");
    expect(defaultOptsFor(sg, SERVED_OPTION_SPECS).model.feed_model).toBe("point");
    expect(modelOptionsForRequest(sg, defaultOptsFor(sg, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS).feed_model).toBe("point");
    expect(
      modelOptionsForRequest(
        sg,
        optsWithModel("sinusoidal-galerkin", { feed_model: "segment" }),
        SERVED_OPTION_SPECS,
      ).feed_model,
    ).toBe("segment");
    // ...and plain sinusoidal must not receive the key AT ALL (momwire#212).
    const sin = entry("sinusoidal");
    expect("feed_model" in modelOptionsForRequest(sin, defaultOptsFor(sin, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS)).toBe(false);
    expect(defaultOptsFor(sin, SERVED_OPTION_SPECS).model.feed_model).toBeUndefined();
  });

  it("keeps the slot chip's (NEC gap) suffix on the same backends", () => {
    const sg = entry("sinusoidal-galerkin");
    expect(backendDisplayLabel(sg, optsWithModel("sinusoidal-galerkin", { feed_model: "segment" })))
      .toContain("(NEC gap)");
    expect(backendDisplayLabel(sg, defaultOptsFor(sg, SERVED_OPTION_SPECS))).not.toContain("(NEC gap)");
  });
});

describe("a momwire that cannot describe itself falls back to the hint", () => {
  // `axes: null` is what the CURRENTLY RELEASED momwire serves. These cases
  // are the installed-user path, not a legacy path.
  const legacySG: BackendEntry = { ...entry("sinusoidal-galerkin"), axes: null };
  const legacySin: BackendEntry = { ...entry("sinusoidal"), axes: null };

  it("still offers the choice on the hinted backend", () => {
    expect(offersFeedModelChoice(legacySG)).toBe(true);
    expect(feedModelChoices(legacySG).map((c) => c.label)).toEqual([
      "NEC-compatible",
      "Converged",
    ]);
    expect(feedTabs(legacySG)).toEqual(["NEC-compatible", "Converged"]);
  });

  it("still offers nothing on the unhinted one", () => {
    expect(legacySin.panel).toBeNull();
    expect(offersFeedModelChoice(legacySin)).toBe(false);
    expect(feedTabs(legacySin)).toBeNull();
  });
});

describe("degree tabs come from the basis axis", () => {
  it("renders d=1 and d=2 from the axis, not from a literal", () => {
    const b = entry("bspline");
    expect(b.axes!.basis).toEqual(["bspline-1", "bspline-2"]);
    renderModal(b);
    expect(tabsIn("degree")).toEqual(["d=1", "d=2"]);
  });

  it("follows the axis when the axis says something else", () => {
    // MUTATE THE DATA THE GATE READS. Flipping the served axis must change
    // the tabs; if it does not, the tabs are still hardcoded and every
    // assertion above would pass anyway.
    const d2only: BackendEntry = {
      ...entry("bspline"),
      axes: { ...entry("bspline").axes!, basis: ["bspline-2"] },
    };
    renderModal(d2only);
    expect(tabsIn("degree")).toEqual(["d=2"]);
  });

  it("keeps both tabs for a momwire that cannot be asked", () => {
    const legacy: BackendEntry = { ...entry("bspline"), axes: null };
    expect(feedModelChoices(legacy)).toEqual([]);
    renderModal(legacy);
    expect(tabsIn("degree")).toEqual(["d=1", "d=2"]);
  });
});
