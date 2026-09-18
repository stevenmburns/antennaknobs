/**
 * The `rotational_symmetry` checkbox (momwire#1029's sector route), served
 * unadvertised on the bspline panel — issue #1567/Steve's ask, 2026-09-18.
 *
 * No bespoke widget: unlike the EK card, this control has NO per-engine
 * component of its own. It renders wherever `renderableOptions` names it
 * (the generic offered-vs-sent rule, driven entirely by the served
 * `model_kwargs` and `model_option_specs`) through the generic `OptionField`
 * — so this file tests the SAME plumbing every other generic knob goes
 * through, not a new mechanism.
 *
 * `SERVED_ROSTER`'s real `bspline` entry (mirrored from the submodule
 * pointer, which does not declare the sector route) does NOT carry the
 * kwarg — that absence is itself the "offered only where momwire declares
 * the route" claim, tested directly against the real served fixture rather
 * than a hypothetical. The PRESENT case uses `backendEntry()` overrides, the
 * same way `extendedKernelOffered.test.ts` models a momwire ahead of the one
 * actually installed.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { backendEntry, entry } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";
import {
  compositionLine,
  modelOptionsForRequest,
  renderableOptions,
  type BackendOpts,
  type CompositionVocabulary,
} from "../lib/backends";
import { OptionField } from "../components/backend/OptionField";

const SPECS = SERVED_OPTION_SPECS;

const opts = (model: Record<string, unknown>): BackendOpts =>
  ({ model }) as unknown as BackendOpts;

describe("absent from the real served roster (the submodule pointer, no #1029)", () => {
  it("bspline's real model_kwargs does not carry it", () => {
    const b = entry("bspline");
    expect(b.model_kwargs).not.toContain("rotational_symmetry");
  });

  it("so renderableOptions never offers it today", () => {
    expect(renderableOptions(entry("bspline"), SPECS)).not.toContain(
      "rotational_symmetry",
    );
  });
});

describe("offered once a backend's served model_kwargs carries it", () => {
  const withRoute = backendEntry({
    name: "bspline",
    model_kwargs: ["degree", "rotational_symmetry"],
    axes: { solve_strategy: ["dense", "sector"], basis: ["bspline-1", "bspline-2"] },
  });

  it("renders through the generic renderer, not a bespoke one", () => {
    expect(renderableOptions(withRoute, SPECS)).toContain("rotational_symmetry");
  });

  it("is absent for a sibling backend whose own model_kwargs excludes it", () => {
    // hmatrix/arrayblock never carry it even on a momwire that HAS #1029 —
    // their OWN solve_strategy axis is single-valued ("aca"/"element-block"),
    // which is a server-side fact (`_offers_rotational_symmetry`); the
    // client-side half of that claim is just: no kwarg, no control.
    const hmatrix = backendEntry({
      name: "hmatrix",
      model_kwargs: ["degree"],
      axes: { solve_strategy: ["aca"] },
    });
    expect(renderableOptions(hmatrix, SPECS)).not.toContain("rotational_symmetry");
  });

  it("modelOptionsForRequest sends it like any other plain bool", () => {
    const on = modelOptionsForRequest(withRoute, opts({ rotational_symmetry: true }), SPECS);
    expect(on).toHaveProperty("rotational_symmetry", true);
    const off = modelOptionsForRequest(withRoute, opts({}), SPECS);
    // Unset reads the spec's own default (false) — same rule `degree` and
    // `use_singular_enrichment` already follow; no extended_kernel-style
    // omission, because this key carries no pre-#1029 byte-compatibility
    // history to preserve.
    expect(off).toHaveProperty("rotational_symmetry", false);
  });

  it("renders a checkbox with the option's own tooltip and no engine name in it", () => {
    const spec = SPECS.rotational_symmetry!;
    expect(spec.description).toBeTruthy();
    render(
      <OptionField
        name="rotational_symmetry"
        spec={spec}
        model={{ rotational_symmetry: false }}
        onPatch={() => {}}
      />,
    );
    const checkbox = screen.getByRole("checkbox", {
      name: /rotational symmetry \(radial screens\)/i,
    }) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    const label = checkbox.closest("label");
    expect(label?.getAttribute("title")).toBe(spec.description);
    expect(label?.title).not.toMatch(/rotational_symmetry=|bspline|momwire/i);
  });

  it("a served disabledReason still wins over the tooltip (constraints outrank doc)", () => {
    const spec = SPECS.rotational_symmetry!;
    render(
      <OptionField
        name="rotational_symmetry"
        spec={spec}
        model={{ rotational_symmetry: false }}
        disabledReason="refused on this design"
        onPatch={() => {}}
      />,
    );
    const checkbox = screen.getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);
    expect(checkbox.closest("label")?.getAttribute("title")).toBe(
      "refused on this design",
    );
  });
});

describe("the composition line reads the checkbox back as the axis value", () => {
  const vocab: CompositionVocabulary = {
    axes: ["solve_strategy"],
    labels: { solve_strategy: { dense: "dense", sector: "sector" } },
  };
  const withRoute = backendEntry({
    name: "bspline",
    axes: { solve_strategy: ["dense", "sector"] },
    bound_axes: {},
  });

  it("reads 'sector' when the box is ticked", () => {
    const line = compositionLine(withRoute, opts({ rotational_symmetry: true }), vocab);
    expect(line).toEqual([{ axis: "solve_strategy", text: "sector", pinned: false, fixed: false }]);
  });

  it("reads 'dense' when it is not", () => {
    const line = compositionLine(withRoute, opts({}), vocab);
    expect(line).toEqual([{ axis: "solve_strategy", text: "dense", pinned: false, fixed: false }]);
  });

  it("never engages for a backend whose solve_strategy is single-valued (hmatrix/arrayblock, today's bspline)", () => {
    const single = backendEntry({ name: "hmatrix", axes: { solve_strategy: ["aca"] } });
    const line = compositionLine(single, opts({ rotational_symmetry: true }), {
      axes: ["solve_strategy"],
      labels: { solve_strategy: { aca: "ACA" } },
    });
    // FIXED, not read from the (irrelevant) option value.
    expect(line).toEqual([{ axis: "solve_strategy", text: "ACA", pinned: false, fixed: true }]);
  });
});
