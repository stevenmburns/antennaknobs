/**
 * AK#1891: a deck read as NEC-4 or NEC-5 solves with the extended kernel ON
 * by default, and the slot's EK toggle shows that default.
 *
 * The default is the design's (`extended_kernel_default`, served per design)
 * and the switch is the user's: on (`model.extended_kernel`) and off
 * (`ekOff`, recorded only against a design whose default is on) both win.
 * Neither set, the slot follows the design, so a "Read as" change — a new
 * design descriptor — re-resolves it. A backend or deck that refuses the
 * kernel takes the reduced one, as the server does, rather than a refusal.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { BackendConfigModal } from "../components/backend/BackendConfigModal";
import {
  backendDisplayLabel,
  defaultOptsFor,
  extendedKernelActive,
  modelOptionsForRequest,
  offersExtendedKernel,
  type BackendOpts,
  type DesignConstraintInputs,
} from "../lib/backends";
import { entry, optsWithModel, SERVED_ROSTER, SERVED_VOCAB } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const DECK: DesignConstraintInputs = { extended_kernel_default: true };
const CATALOG: DesignConstraintInputs = {};
const stock = (name: string): BackendOpts =>
  defaultOptsFor(entry(name), SERVED_OPTION_SPECS);
const payload = (name: string, opts: BackendOpts, design: DesignConstraintInputs) =>
  modelOptionsForRequest(entry(name), opts, SERVED_OPTION_SPECS, design);

const OFFERED = SERVED_ROSTER.filter(offersExtendedKernel).map((b) => b.name);

describe("the slot follows the design's kernel", () => {
  it("has backends to check", () => {
    expect(OFFERED.length).toBeGreaterThan(0);
  });

  it.each(OFFERED)("%s: on for a NEC-4/5 deck, off for a catalog design", (name) => {
    expect(extendedKernelActive(entry(name), stock(name), DECK)).toBe(true);
    expect(extendedKernelActive(entry(name), stock(name), CATALOG)).toBe(false);
    expect(extendedKernelActive(entry(name), stock(name))).toBe(false);
  });

  it("never on a reduced-only backend", () => {
    expect(extendedKernelActive(entry("pulse"), stock("pulse"), DECK)).toBe(false);
  });

  it("the user's off wins over the default, and the user's on over its absence", () => {
    const off = { ...stock("bspline"), ekOff: true };
    expect(extendedKernelActive(entry("bspline"), off, DECK)).toBe(false);
    const on = optsWithModel("bspline", { extended_kernel: true });
    expect(extendedKernelActive(entry("bspline"), on, CATALOG)).toBe(true);
  });

  it("falls back to reduced where the deck refuses it: a buried wire", () => {
    const buried = { ...DECK, buried: true };
    expect(extendedKernelActive(entry("bspline"), stock("bspline"), buried)).toBe(false);
  });

  it("says +EK on the chip where the default is in force", () => {
    expect(backendDisplayLabel(entry("bspline"), stock("bspline"), DECK)).toMatch(/\+EK$/);
    expect(backendDisplayLabel(entry("bspline"), stock("bspline"), CATALOG)).not.toMatch(
      /\+EK/,
    );
  });
});

describe("what the request says", () => {
  it("leaves the default to the server: no key, as on a catalog design", () => {
    expect(payload("bspline", stock("bspline"), DECK)).not.toHaveProperty("extended_kernel");
    expect(payload("bspline", stock("bspline"), CATALOG)).not.toHaveProperty(
      "extended_kernel",
    );
  });

  it("sends the user's off against a deck's default, and only there", () => {
    const off = { ...stock("bspline"), ekOff: true };
    expect(payload("bspline", off, DECK).extended_kernel).toBe(false);
    // A catalog design's request stays byte-identical to before.
    expect(payload("bspline", off, CATALOG)).toEqual(payload("bspline", stock("bspline"), CATALOG));
  });

  it("sends the user's on everywhere", () => {
    const on = optsWithModel("bspline", { extended_kernel: true });
    expect(payload("bspline", on, DECK).extended_kernel).toBe(true);
    expect(payload("bspline", on, CATALOG).extended_kernel).toBe(true);
  });
});

describe("the gear's EK toggle", () => {
  const EK = /extended kernel \(EK\)/;

  function renderFor(design: DesignConstraintInputs, opts = stock("bspline")) {
    const onPatch = vi.fn();
    render(
      <BackendConfigModal
        slot="A"
        backend={entry("bspline")}
        backends={SERVED_ROSTER}
        requiredBackends={null}
        design={design}
        restrictionReason={null}
        specs={SERVED_OPTION_SPECS}
        vocab={SERVED_VOCAB}
        designRefusalNote={null}
        suggestConvergedFeed={false}
        opts={opts}
        onChangeBackend={vi.fn()}
        onPatch={onPatch}
        onReset={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    return { onPatch, user: userEvent.setup() };
  }

  it("shows the deck's default on, and says why", () => {
    renderFor(DECK);
    expect(screen.getByRole("checkbox", { name: EK })).toHaveProperty("checked", true);
    expect(screen.getByText(/On by default: the deck is read as NEC-4 or NEC-5/)).toBeTruthy();
  });

  it("records turning it off as the user's off", async () => {
    const { onPatch, user } = renderFor(DECK);
    await user.click(screen.getByRole("checkbox", { name: EK }));
    expect(onPatch).toHaveBeenCalledWith({
      model: expect.objectContaining({ extended_kernel: false }),
      ekOff: true,
    });
  });

  it("shows a catalog design's off, with no default note", () => {
    renderFor(CATALOG);
    expect(screen.getByRole("checkbox", { name: EK })).toHaveProperty("checked", false);
    expect(screen.queryByText(/On by default/)).toBeNull();
  });
});
