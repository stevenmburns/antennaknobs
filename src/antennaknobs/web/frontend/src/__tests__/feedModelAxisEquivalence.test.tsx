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
  defaultOptsFor,
  feedModelChoices,
  offersFeedModelChoice,
  modelOptionsForRequest,
  type BackendEntry,
} from "../lib/backends";
import { entry, SERVED_ROSTER, SERVED_VOCAB } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

function renderModal(b: BackendEntry) {
  return render(
    <BackendConfigModal
      slot="A"
      backend={b}
      backends={SERVED_ROSTER}
      requiredBackends={null}
      design={{}}
      restrictionReason={null}
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

// THIS EQUIVALENCE HAS NOW DELIBERATELY ENDED, and that is the right outcome
// rather than a regression.
//
// The tests below used to assert `offersFeedModelChoice(b) === (b.panel ===
// PANEL_SIN_GALERKIN)` for every served backend. That was the CONDITION THE
// PANEL HINT WAS ALLOWED TO BE DELETED UNDER (#1006 G2-5/G2-6): the axis path
// had to reproduce the hint exactly before the hint could go.
//
// It did, the hint went, and then momwire#891 corrected a row: the B-spline
// family declared `feed_model: ("segment-gap",)` while its constructor
// defaulted to the POINT gap, so the axis was mis-declared as single-valued
// and the choice was invisible. With the row fixed, three more backends
// legitimately offer the control — so the axis path and the retired hint now
// DISAGREE, because the hint was carrying the mistake.
//
// A migration gate has a lifetime. Holding this one after the migration would
// have pinned the old panel's mistake in place, which is the opposite of what
// it was written to protect.

describe("the axis decides, and it now says more than the hint did", () => {
  it("offers the choice wherever the axis is multi-valued AND exposed", () => {
    const offering = SERVED_ROSTER.filter(offersFeedModelChoice).map((b) => b.name);
    expect(offering).toEqual([
      "sinusoidal-galerkin",
      "bspline",
      "hmatrix",
      "arrayblock",
    ]);
  });

  it("does NOT offer it where the solver refuses the point gap", () => {
    // `sinusoidal` is the negative case and the important one: it accepts the
    // kwarg and REFUSES the value (momwire#212), so a rule keyed on the axis
    // existing — rather than on it being multi-valued and exposed — would
    // offer a choice that raises.
    expect(offersFeedModelChoice(entry("sinusoidal"))).toBe(false);
    expect(entry("sinusoidal").axes!.feed_model).toEqual(["segment-gap"]);
  });

  it("does NOT offer it on a node-port feed", () => {
    expect(offersFeedModelChoice(entry("razor-2p"))).toBe(false);
  });

  it("renders the same two tabs, with the same labels and order", () => {
    expect(feedTabs(entry("sinusoidal-galerkin"))).toEqual([
      "NEC-compatible",
      "Converged",
    ]);
  });

  it("renders those same two on the b-spline family now", () => {
    expect(feedTabs(entry("bspline"))).toEqual(["NEC-compatible", "Converged"]);
  });

  it("keeps the wire payload right on both", () => {
    const sg = entry("sinusoidal-galerkin");
    expect(defaultOptsFor(sg, SERVED_OPTION_SPECS).model.feed_model).toBe("point");
    // ...and the family that just gained it sends the value it was already
    // solving with — anchored numerically in test_feed_model_exposure_1006.py.
    const b = entry("bspline");
    expect(
      modelOptionsForRequest(b, defaultOptsFor(b, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS)
        .feed_model,
    ).toBe("point");
    // Plain sinusoidal must still not receive the key AT ALL (momwire#212).
    const sin = entry("sinusoidal");
    expect(
      "feed_model" in
        modelOptionsForRequest(sin, defaultOptsFor(sin, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS),
    ).toBe(false);
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
