// Pins the conditional-rendering matrix of the slot gear menu
// (src/components/backend/BackendConfigModal.tsx, issue #673): which knobs each
// backend shows, the per-design backend allowlist gating, and the dismissal
// paths. Every visibility assertion is paired with an absence assertion on a
// backend/flag that must NOT show the field — a presence-only test still passes
// if the conditional is deleted.
//
// Since issue #628 the whole matrix is driven by the served roster fixture:
// the tab list, the labels, the generic numeric knobs (options_schema) and the
// two bespoke panels (selected by the `panel` hint). BSplineFields has no
// separate export; it is exercised through the modal with an entry whose panel
// is "bspline", which is also the only way it ships.
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  BackendConfigModal,
  type BackendConfigProps,
} from "../components/backend/BackendConfigModal";
import {
  RESTRICTED_BACKEND_REASON,
  defaultOptsFor,
  type BackendOpts,
} from "../lib/backends";
import { entry, optsWithModel, SERVED_ROSTER } from "./backendFixtures";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

// --- fixtures --------------------------------------------------------------

const NAMES = SERVED_ROSTER.map((b) => b.name);
const BSPLINE_PANEL = SERVED_ROSTER.filter((b) => b.panel === "bspline").map(
  (b) => b.name,
);

/** Stock opts for a backend, with the b-spline panel state overridden. */
/** Stock options with b-spline knobs overridden, by SERVED kwarg name. */
function bsplineOpts(
  name: string,
  over: Record<string, unknown> = {},
): BackendOpts {
  return optsWithModel(name, over);
}

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never got.
type ModalOverrides = Omit<
  Partial<BackendConfigProps>,
  "backend" | "onChangeBackend" | "onPatch" | "onReset" | "onClose"
> & { backend?: string };

function renderModal(overrides: ModalOverrides = {}) {
  const { backend: name = "bspline", ...rest } = overrides;
  const backend = entry(name);
  const spies = {
    onChangeBackend: vi.fn(),
    onPatch: vi.fn(),
    onReset: vi.fn(),
    onClose: vi.fn(),
  };
  const view = render(
    <BackendConfigModal
      slot="A"
      backend={backend}
      backends={SERVED_ROSTER}
      requiredBackends={null}
      suggestConvergedFeed={false}
      opts={defaultOptsFor(backend, SERVED_OPTION_SPECS)}
      {...rest}
      {...spies}
    />,
  );
  return { ...view, ...spies, user: userEvent.setup() };
}

// NumberField's <label> wraps only the caption/value spans, not the input, so
// there is no label→control association for getByLabelText to follow: locate
// the field by its caption text and step out to the sibling input.
function numberField(label: string): HTMLInputElement {
  const field = screen.getByText(label).closest(".field");
  if (!field) throw new Error(`no .field wrapper for "${label}"`);
  return within(field as HTMLElement).getByRole("spinbutton") as HTMLInputElement;
}

const N_QP_CONST = "n_qp_const (GL pts)";
const N_QP_PAIR = "n_qp_pair (GL pts/axis)";
const FEED_SMOOTHING_ALPHA = "α (bump width / h_feed)";
const N_QP_SOURCE = "n_qp_source";
const N_QP_SING = "n_qp_sing (GL pts/axis)";
const ENRICHMENT_MIN_K = "enrichment_min_k";
const TIKHONOV_LAMBDA = "tikhonov_lambda (λ)";
const AUTO_TAP_THRESHOLD = "auto_tap_ratio_threshold";

describe("BackendConfigModal — backend tab list", () => {
  it("offers every served backend, marking the current one selected", () => {
    renderModal({ backend: "bspline" });
    for (const b of SERVED_ROSTER) {
      const tab = screen.getByRole("tab", { name: b.label });
      expect(tab).toHaveProperty("disabled", false);
      expect(tab.getAttribute("title")).toBeNull();
      expect(tab.getAttribute("aria-selected")).toBe(String(b.name === "bspline"));
    }
  });

  it("renders the tabs in the served order", () => {
    const { container } = renderModal({ backend: "bspline" });
    const tabs = within(
      container.querySelector(".geometry-tabs") as HTMLElement,
    ).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(
      SERVED_ROSTER.map((b) => b.label),
    );
  });

  it("fires onChangeBackend with the clicked backend's entry", async () => {
    const { user, onChangeBackend } = renderModal({ backend: "bspline" });
    await user.click(screen.getByRole("tab", { name: entry("pynec").label }));
    expect(onChangeBackend).toHaveBeenCalledWith(entry("pynec"));
    expect(onChangeBackend).toHaveBeenCalledTimes(1);
  });

  it("offers only what the roster carries (no PyNEC tab on a server without it)", () => {
    renderModal({
      backend: "bspline",
      backends: SERVED_ROSTER.filter((b) => b.kind !== "pynec"),
    });
    expect(screen.queryByRole("tab", { name: "PyNEC" })).toBeNull();
  });

  it("disables the backends a restricted design excludes, with the reason as tooltip", () => {
    renderModal({
      backend: "bspline",
      requiredBackends: ["bspline", "sinusoidal-galerkin"],
    });
    for (const b of SERVED_ROSTER) {
      const tab = screen.getByRole("tab", { name: b.label });
      const allowed = b.name === "bspline" || b.name === "sinusoidal-galerkin";
      expect(tab).toHaveProperty("disabled", !allowed);
      expect(tab.getAttribute("title")).toBe(
        allowed ? null : RESTRICTED_BACKEND_REASON,
      );
    }
  });

  it("does not fire onChangeBackend when a disallowed tab is clicked", async () => {
    const { user, onChangeBackend } = renderModal({
      backend: "bspline",
      requiredBackends: ["bspline"],
    });
    await user.click(screen.getByRole("tab", { name: entry("pynec").label }));
    expect(onChangeBackend).not.toHaveBeenCalled();
  });
});

describe("BackendConfigModal — per-backend knob visibility", () => {
  it("shows the shared mesh knobs for every backend, at the served default N", () => {
    for (const b of SERVED_ROSTER) {
      const { unmount } = renderModal({ backend: b.name });
      expect(numberField("segments / wire (N)").value).toBe(
        String(b.default_n_per_wire),
      );
      expect(numberField("wire radius (m)")).toBeTruthy();
      unmount();
    }
  });

  it.each(NAMES)("renders exactly the options_schema knobs served for %s", (name) => {
    const b = entry(name);
    renderModal({ backend: name });
    for (const f of b.options_schema) expect(screen.queryByText(f.label)).not.toBeNull();
    // n_qp_const is the one generic knob any backend serves today; anything
    // that doesn't serve it must not show it.
    expect(screen.queryByText(N_QP_CONST) !== null).toBe(
      b.options_schema.some((f) => f.key === "n_qp_const"),
    );
  });

  it("patches the generic knob under its served (wire) key", async () => {
    const { user, onPatch } = renderModal({ backend: "sinusoidal" });
    await user.type(numberField(N_QP_CONST), "1"); // "8" -> "81"
    expect(onPatch).toHaveBeenCalledWith({ model: expect.objectContaining({ n_qp_const: 81 }) });
  });

  it.each(BSPLINE_PANEL)("shows the B-spline knobs for %s", (name) => {
    renderModal({ backend: name });
    expect(screen.queryByRole("tab", { name: "d=2" })).not.toBeNull();
    // The n_qp_pair CONTROL is the auto toggle at stock settings; the number
    // field appears only once auto is unticked (antennaknobs#1064).
    expect(
      screen.queryByRole("checkbox", { name: /n_qp_pair: auto/ }),
    ).not.toBeNull();
    expect(screen.queryByText(N_QP_PAIR)).toBeNull();
  });

  it.each(NAMES.filter((n) => !BSPLINE_PANEL.includes(n)))(
    "hides the B-spline knobs for %s",
    (name) => {
      renderModal({ backend: name });
      expect(screen.queryByRole("tab", { name: "d=2" })).toBeNull();
      expect(screen.queryByText(N_QP_PAIR)).toBeNull();
    },
  );

  it("shows the no-extra-knobs note for the pynec panel only", () => {
    const { unmount } = renderModal({ backend: "pynec" });
    expect(screen.queryByText(/no extra solver knobs/)).not.toBeNull();
    unmount();
    renderModal({ backend: "bspline" });
    expect(screen.queryByText(/no extra solver knobs/)).toBeNull();
  });
});

describe("BackendConfigModal — extended kernel (#849)", () => {
  const EK = /extended kernel \(EK\)/;
  const ENRICHMENT = /junction singular enrichment/;
  const MOMWIRE = NAMES.filter((n) => entry(n).kind === "momwire");

  it.each(MOMWIRE)("offers the toggle on %s, off by default", (name) => {
    renderModal({ backend: name });
    expect(screen.getByRole("checkbox", { name: EK })).toHaveProperty(
      "checked",
      false,
    );
  });

  it("offers no toggle on pynec — its extended kernel is not this knob (#414)", () => {
    renderModal({ backend: "pynec" });
    expect(screen.queryByRole("checkbox", { name: EK })).toBeNull();
  });

  it("patches extendedKernel on and off", async () => {
    const off = renderModal({ backend: "bspline" });
    await off.user.click(screen.getByRole("checkbox", { name: EK }));
    expect(off.onPatch).toHaveBeenCalledWith({ model: expect.objectContaining({ extended_kernel: true }) });
    off.unmount();

    const on = renderModal({
      backend: "bspline",
      opts: optsWithModel("bspline", { extended_kernel: true }),
    });
    expect(screen.getByRole("checkbox", { name: EK })).toHaveProperty("checked", true);
    await on.user.click(screen.getByRole("checkbox", { name: EK }));
    expect(on.onPatch).toHaveBeenCalledWith({ model: expect.objectContaining({ extended_kernel: false }) });
  });

  it("serves the toggle on Sin-Galerkin (momwire 0.27.0 un-refusal)", async () => {
    // The exact modal state that used to grey out with the momwire#246
    // reason: since momwire#246/#287/#299 the Galerkin family serves the
    // kernel, so the box is live and patches like any other basis.
    const { user, onPatch } = renderModal({
      backend: "sinusoidal-galerkin",
      opts: optsWithModel("sinusoidal-galerkin", { extended_kernel: true }),
    });
    const box = screen.getByRole("checkbox", { name: EK });
    expect(box).toHaveProperty("disabled", false);
    expect(box).toHaveProperty("checked", true);
    await user.click(box);
    expect(onPatch).toHaveBeenCalledWith({ model: expect.objectContaining({ extended_kernel: false }) });
  });

  it("keeps the Δ/a hint on the servable backends", () => {
    renderModal({ backend: "bspline" });
    expect(screen.getByText(/Δ\/a/)).toBeTruthy();
  });

  // momwire#271: the two are mutually exclusive, and the exclusion is
  // symmetric so neither box can lock the other out permanently.
  // The kernel is no longer greyed by enrichment HERE (#1006 G2-6).
  //
  // `extendedKernelRefusal` and `EK_ENRICHMENT_REASON` were a hand-written
  // copy of momwire's refusal, and a drifted one — they cited momwire#271
  // where momwire cites momwire#249 follow-up C, and gave one reason where it
  // gives three. momwire#888 added the served coupling row, so the exclusion
  // is now data on the roster and is exercised by `designRefusal`. The
  // enrichment box still greys while the kernel is on (below): that direction
  // is a local UI affordance, not a restatement of momwire's prose.

  it("greys enrichment out while the kernel is on", () => {
    renderModal({
      backend: "bspline",
      opts: optsWithModel("bspline", { extended_kernel: true }),
    });
    const enrich = screen.getByRole("checkbox", { name: ENRICHMENT });
    expect(enrich).toHaveProperty("disabled", true);
    expect(
      within(screen.getByTitle(/Unavailable while the extended kernel/)).getByRole(
        "checkbox",
      ),
    ).toBe(enrich);
    // …and the kernel itself is still live.
    expect(screen.getByRole("checkbox", { name: EK })).toHaveProperty("disabled", false);
  });

  it("leaves enrichment alone when the kernel is off", () => {
    renderModal({ backend: "bspline", opts: bsplineOpts("bspline") });
    expect(screen.getByRole("checkbox", { name: ENRICHMENT })).toHaveProperty(
      "disabled",
      false,
    );
  });
});

describe("BackendConfigModal — Sin-Galerkin feed model", () => {
  it("offers the feed-model tabs only for the sin-galerkin panel", () => {
    const { unmount } = renderModal({ backend: "sinusoidal-galerkin" });
    expect(screen.queryByRole("tab", { name: "Converged" })).not.toBeNull();
    expect(screen.queryByRole("tab", { name: "NEC-compatible" })).not.toBeNull();
    unmount();
    // Plain sinusoidal has no point-gap RHS, so it must not present the choice.
    renderModal({ backend: "sinusoidal" });
    expect(screen.queryByRole("tab", { name: "Converged" })).toBeNull();
  });

  it("patches feedModel to point when Converged is clicked", async () => {
    const b = entry("sinusoidal-galerkin");
    const { user, onPatch } = renderModal({
      backend: b.name,
      opts: optsWithModel(b.name, { feed_model: "segment" }),
    });
    await user.click(screen.getByRole("tab", { name: "Converged" }));
    expect(onPatch).toHaveBeenCalledWith({ model: expect.objectContaining({ feed_model: "point" }) });
    expect(onPatch).toHaveBeenCalledTimes(1);
  });

  it("patches feedModel to segment when NEC-compatible is clicked", async () => {
    const b = entry("sinusoidal-galerkin");
    const { user, onPatch } = renderModal({
      backend: b.name,
      opts: optsWithModel(b.name, { feed_model: "point" }),
    });
    await user.click(screen.getByRole("tab", { name: "NEC-compatible" }));
    expect(onPatch).toHaveBeenCalledWith({ model: expect.objectContaining({ feed_model: "segment" }) });
  });

  it("shows the Converged hint only when recommended and still on segment", () => {
    const hint = /near-open \/ high-Q/;
    const b = entry("sinusoidal-galerkin");
    const cases: Array<[boolean, "segment" | "point", boolean]> = [
      [true, "segment", true],
      [true, "point", false],
      [false, "segment", false],
      [false, "point", false],
    ];
    for (const [suggestConvergedFeed, feedModel, shown] of cases) {
      const { unmount } = renderModal({
        backend: b.name,
        suggestConvergedFeed,
        opts: optsWithModel(b.name, { feed_model: feedModel }),
      });
      expect(screen.queryByText(hint) !== null).toBe(shown);
      unmount();
    }
  });
});

describe("BSplineFields — degree and feed smoothing", () => {
  it("patches the degree of the clicked tab", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { degree: 2 }),
    });
    expect(screen.getByRole("tab", { name: "d=2" }).getAttribute("aria-selected")).toBe("true");
    await user.click(screen.getByRole("tab", { name: "d=1" }));
    expect(onPatch).toHaveBeenCalledWith({
      model: expect.objectContaining({ degree: 1 }),
    });
    expect(onPatch).toHaveBeenCalledTimes(1);
  });

  it("commits an edited number field as a patch on that key alone", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { n_qp_pair: 4 }),
    });
    await user.type(numberField(N_QP_PAIR), "2"); // "4" -> "42"
    expect(onPatch).toHaveBeenCalledWith({
      model: expect.objectContaining({ n_qp_pair: 42 }),
    });
  });

  it("hides the n_qp_pair field while the order is auto", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { n_qp_pair: null }),
    });
    const box = screen.getByRole("checkbox", { name: /n_qp_pair: auto/ });
    expect(box).toHaveProperty("checked", true);
    expect(screen.queryByText(N_QP_PAIR)).toBeNull();
  });

  it("unticking auto pins a number, and reticking returns to auto", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { n_qp_pair: null }),
    });
    await user.click(screen.getByRole("checkbox", { name: /n_qp_pair: auto/ }));
    expect(onPatch).toHaveBeenCalledWith({
      model: expect.objectContaining({ n_qp_pair: 8 }),
    });

    const back = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { n_qp_pair: 16 }),
    });
    await back.user.click(
      screen.getAllByRole("checkbox", { name: /n_qp_pair: auto/ })[1],
    );
    expect(back.onPatch).toHaveBeenCalledWith({
      model: expect.objectContaining({ n_qp_pair: null }),
    });
  });

  it("hides the smoothing sub-fields while the delta-gap is sharp", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { feed_smoothing_factor: null }),
    });
    const box = screen.getByRole("checkbox", { name: /feed source smoothing/ });
    expect(box).toHaveProperty("checked", false);
    expect(screen.queryByText(FEED_SMOOTHING_ALPHA)).toBeNull();
    expect(screen.queryByText(N_QP_SOURCE)).toBeNull();
  });

  it("shows the smoothing sub-fields once a factor is set", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { feed_smoothing_factor: 3 }),
    });
    expect(
      screen.getByRole("checkbox", { name: /feed source smoothing/ }),
    ).toHaveProperty("checked", true);
    expect(screen.queryByText(FEED_SMOOTHING_ALPHA)).not.toBeNull();
    expect(screen.queryByText(N_QP_SOURCE)).not.toBeNull();
  });

  it("toggles feedSmoothingFactor between the default 3 and null", async () => {
    const off = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { feed_smoothing_factor: null }),
    });
    await off.user.click(
      screen.getByRole("checkbox", { name: /feed source smoothing/ }),
    );
    expect(off.onPatch.mock.calls[0][0].model.feed_smoothing_factor).toBe(3);
    off.unmount();

    const on = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { feed_smoothing_factor: 3 }),
    });
    await on.user.click(
      screen.getByRole("checkbox", { name: /feed source smoothing/ }),
    );
    expect(on.onPatch.mock.calls[0][0].model.feed_smoothing_factor).toBeNull();
  });
});

describe("BSplineFields — singular enrichment", () => {
  it("hides every enrichment sub-field while enrichment is off", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { use_singular_enrichment: false }),
    });
    expect(
      screen.getByRole("checkbox", { name: /junction singular enrichment/ }),
    ).toHaveProperty("checked", false);
    expect(screen.queryByText(N_QP_SING)).toBeNull();
    expect(screen.queryByText(ENRICHMENT_MIN_K)).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("reveals the enrichment sub-fields when it is on", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { use_singular_enrichment: true }),
    });
    expect(screen.queryByText(N_QP_SING)).not.toBeNull();
    expect(screen.queryByText(ENRICHMENT_MIN_K)).not.toBeNull();
    expect(screen.getByRole("combobox")).toHaveProperty("value", "raw");
  });

  it("patches useSingularEnrichment on toggle", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { use_singular_enrichment: false }),
    });
    await user.click(
      screen.getByRole("checkbox", { name: /junction singular enrichment/ }),
    );
    expect(onPatch.mock.calls[0][0].model.use_singular_enrichment).toBe(true);
  });

  it("patches enrichmentVariant from the select", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", { use_singular_enrichment: true }),
    });
    await user.selectOptions(screen.getByRole("combobox"), "auto");
    expect(onPatch.mock.calls[0][0].model.enrichment_variant).toBe("auto");
  });

  // Each variant owns exactly one extra knob; the other must stay hidden.
  it.each([
    ["raw", false, false],
    ["stable", false, false],
    ["tikhonov", true, false],
    ["auto", false, true],
  ] as const)(
    "variant %s shows tikhonov_lambda=%s / auto_tap_ratio_threshold=%s",
    (enrichmentVariant, lambdaShown, thresholdShown) => {
      renderModal({
        backend: "bspline",
        opts: bsplineOpts("bspline", {
          use_singular_enrichment: true,
          enrichment_variant: enrichmentVariant,
        }),
      });
      expect(screen.queryByText(TIKHONOV_LAMBDA) !== null).toBe(lambdaShown);
      expect(screen.queryByText(AUTO_TAP_THRESHOLD) !== null).toBe(thresholdShown);
    },
  );

  it("keeps the variant knobs hidden when enrichment itself is off", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts("bspline", {
        use_singular_enrichment: false,
        enrichment_variant: "tikhonov",
      }),
    });
    expect(screen.queryByText(TIKHONOV_LAMBDA)).toBeNull();
  });
});

describe("BackendConfigModal — dismissal and footer", () => {
  it("closes on Escape", async () => {
    const { user, onClose } = renderModal();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores other keys", async () => {
    const { user, onClose } = renderModal();
    await user.keyboard("{Enter}");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on an overlay click but not on a click inside the modal", async () => {
    const { user, onClose, container } = renderModal();
    await user.click(screen.getByRole("dialog", { name: "Slot A options" }));
    expect(onClose).not.toHaveBeenCalled();

    const overlay = container.querySelector(".backend-config-overlay");
    expect(overlay).not.toBeNull();
    await user.click(overlay as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on the × button", async () => {
    const { user, onClose } = renderModal();
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("fires onReset from the footer without touching onPatch", async () => {
    const { user, onReset, onPatch } = renderModal();
    await user.click(screen.getByRole("button", { name: /reset to defaults/ }));
    expect(onReset).toHaveBeenCalledTimes(1);
    expect(onPatch).not.toHaveBeenCalled();
  });
});
