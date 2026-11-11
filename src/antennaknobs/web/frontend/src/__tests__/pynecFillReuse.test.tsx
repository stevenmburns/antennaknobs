// PyNEC's fill reuse (pynec-accel 1.7.7) as a checkbox on the PyNEC pane.
//
// An ordinary served bool (`fill_reuse`), exposed by the pynec roster row only
// where the server's PyNEC has `set_fill_reuse`, so the pane draws it with the
// generic OptionField and the request carries it in `model_options` the way
// the NEC-4.2 slot's Sommerfeld choice rides. Pinned here: it shows on the
// PyNEC pane and nowhere else, it is off by default, a tick patches the slot,
// and a PyNEC without it sends nothing at all, as before.
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BackendConfigModal } from "../components/backend/BackendConfigModal";
import {
  defaultOptsFor,
  modelOptionsForRequest,
  type BackendOpts,
  type BackendRoster,
} from "../lib/backends";
import {
  ROSTER_WITH_PYNEC_FILL_REUSE,
  SERVED_ROSTER,
  SERVED_VOCAB,
  entry,
} from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const LABEL = /reuse repeated geometry \(faster fill\)/;
const pynec = entry("pynec", ROSTER_WITH_PYNEC_FILL_REUSE);

function renderModal(name: string, roster: BackendRoster, opts?: BackendOpts) {
  const backend = entry(name, roster);
  const onPatch = vi.fn();
  render(
    <BackendConfigModal
      slot="C"
      backend={backend}
      backends={roster}
      requiredBackends={null}
      design={{}}
      restrictionReason={null}
      specs={SERVED_OPTION_SPECS}
      vocab={SERVED_VOCAB}
      designRefusalNote={null}
      suggestConvergedFeed={false}
      opts={opts ?? defaultOptsFor(backend, SERVED_OPTION_SPECS)}
      onChangeBackend={vi.fn()}
      onPatch={onPatch}
      onReset={vi.fn()}
      onClose={vi.fn()}
    />,
  );
  return { onPatch, user: userEvent.setup() };
}

describe("the option on the wire", () => {
  it("is off by default, and the request says so", () => {
    const opts = defaultOptsFor(pynec, SERVED_OPTION_SPECS);
    expect(opts.model).toEqual({ fill_reuse: false });
    expect(modelOptionsForRequest(pynec, opts, SERVED_OPTION_SPECS)).toEqual({
      fill_reuse: false,
    });
  });

  it("sends a tick", () => {
    const base = defaultOptsFor(pynec, SERVED_OPTION_SPECS);
    const on = { ...base, model: { ...base.model, fill_reuse: true } };
    expect(modelOptionsForRequest(pynec, on, SERVED_OPTION_SPECS)).toEqual({ fill_reuse: true });
  });

  it("a PyNEC without it sends no model_options, as before", () => {
    const b = entry("pynec", SERVED_ROSTER);
    const opts = defaultOptsFor(b, SERVED_OPTION_SPECS);
    const stray = { ...opts, model: { ...opts.model, fill_reuse: true } };
    expect(modelOptionsForRequest(b, stray, SERVED_OPTION_SPECS)).toEqual({});
  });

  it("no other backend sends it", () => {
    for (const b of ROSTER_WITH_PYNEC_FILL_REUSE) {
      if (b.kind === "pynec") continue;
      const opts = defaultOptsFor(b, SERVED_OPTION_SPECS);
      const stray = { ...opts, model: { ...opts.model, fill_reuse: true } };
      expect(modelOptionsForRequest(b, stray, SERVED_OPTION_SPECS)).not.toHaveProperty(
        "fill_reuse",
      );
    }
  });
});

describe("the PyNEC pane", () => {
  it("shows the checkbox, unticked", () => {
    renderModal("pynec", ROSTER_WITH_PYNEC_FILL_REUSE);
    const box = screen.getByRole("checkbox", { name: LABEL });
    expect((box as HTMLInputElement).checked).toBe(false);
    expect((box as HTMLInputElement).disabled).toBe(false);
  });

  it("patches the slot's options on a tick", async () => {
    const { onPatch, user } = renderModal("pynec", ROSTER_WITH_PYNEC_FILL_REUSE);
    await user.click(screen.getByRole("checkbox", { name: LABEL }));
    expect(onPatch).toHaveBeenCalledWith({ model: { fill_reuse: true } });
  });

  it("is absent on a PyNEC without it", () => {
    renderModal("pynec", SERVED_ROSTER);
    expect(screen.queryByRole("checkbox", { name: LABEL })).toBeNull();
  });

  it.each(SERVED_ROSTER.filter((b) => b.kind !== "pynec").map((b) => b.name))(
    "is absent on %s",
    (name) => {
      renderModal(name, ROSTER_WITH_PYNEC_FILL_REUSE);
      // The B-spline tab's pair_reuse shares the caption on purpose (one
      // idea, two engines), so the count it may show is its own one.
      const own = (entry(name, ROSTER_WITH_PYNEC_FILL_REUSE).model_kwargs ?? []).includes(
        "pair_reuse",
      );
      expect(screen.queryAllByRole("checkbox", { name: LABEL })).toHaveLength(own ? 1 : 0);
    },
  );
});
