// Pins the conditional-rendering matrix of the slot gear menu
// (src/components/backend/BackendConfigModal.tsx, issue #673): which knobs each
// backend shows, the per-design backend allowlist gating, and the dismissal
// paths. Every visibility assertion is paired with an absence assertion on a
// backend/flag that must NOT show the field — a presence-only test still passes
// if the conditional is deleted.
//
// BSplineFields has no separate export; it is exercised through the modal with
// a B-spline-family backend, which is also the only way it ships.
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  BackendConfigModal,
  type BackendConfigProps,
} from "../components/backend/BackendConfigModal";
import {
  BACKEND_LABEL,
  BACKEND_ORDER,
  BSPLINE_DEFAULT_OPTS,
  BSPLINE_FAMILY,
  DEFAULT_BACKEND_OPTS,
  RESTRICTED_BACKEND_REASON,
  type BSplineOpts,
  type SinGalerkinOpts,
} from "../lib/backends";

// --- fixtures --------------------------------------------------------------
// Backend labels, option shapes and defaults all come from lib/backends so the
// tests follow a rename or a default change instead of pinning a stale copy.

function bsplineOpts(over: Partial<BSplineOpts> = {}): BSplineOpts {
  return { ...BSPLINE_DEFAULT_OPTS, ...over };
}

function sinGalerkinOpts(over: Partial<SinGalerkinOpts> = {}): SinGalerkinOpts {
  return { ...DEFAULT_BACKEND_OPTS["sinusoidal-galerkin"], ...over };
}

// Callbacks are supplied by the harness (and returned as spies) rather than
// overridable, so an assertion can never target a spy the component never got.
type ModalOverrides = Partial<
  Omit<BackendConfigProps, "onChangeBackend" | "onPatch" | "onReset" | "onClose">
>;

function renderModal(overrides: ModalOverrides = {}) {
  const backend = overrides.backend ?? "bspline";
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
      backends={BACKEND_ORDER}
      requiredBackends={null}
      suggestConvergedFeed={false}
      opts={DEFAULT_BACKEND_OPTS[backend]}
      {...overrides}
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
  it("offers every backend, marking the current one selected", () => {
    renderModal({ backend: "bspline" });
    for (const b of BACKEND_ORDER) {
      const tab = screen.getByRole("tab", { name: BACKEND_LABEL[b] });
      expect(tab).toHaveProperty("disabled", false);
      expect(tab.getAttribute("title")).toBeNull();
      expect(tab.getAttribute("aria-selected")).toBe(String(b === "bspline"));
    }
  });

  it("fires onChangeBackend with the clicked backend", async () => {
    const { user, onChangeBackend } = renderModal({ backend: "bspline" });
    await user.click(screen.getByRole("tab", { name: BACKEND_LABEL.pynec }));
    expect(onChangeBackend).toHaveBeenCalledWith("pynec");
    expect(onChangeBackend).toHaveBeenCalledTimes(1);
  });

  it("disables the backends a restricted design excludes, with the reason as tooltip", () => {
    renderModal({
      backend: "bspline",
      requiredBackends: ["bspline", "sinusoidal-galerkin"],
    });
    for (const b of BACKEND_ORDER) {
      const tab = screen.getByRole("tab", { name: BACKEND_LABEL[b] });
      const allowed = b === "bspline" || b === "sinusoidal-galerkin";
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
    await user.click(screen.getByRole("tab", { name: BACKEND_LABEL.pynec }));
    expect(onChangeBackend).not.toHaveBeenCalled();
  });
});

describe("BackendConfigModal — per-backend knob visibility", () => {
  it("shows the shared mesh knobs for every backend", () => {
    for (const b of BACKEND_ORDER) {
      const { unmount } = renderModal({ backend: b });
      expect(numberField("segments / wire (N)").value).toBe(
        String(DEFAULT_BACKEND_OPTS[b].nPerWire),
      );
      expect(numberField("wire radius (m)")).toBeTruthy();
      unmount();
    }
  });

  it.each(["sinusoidal", "sinusoidal-galerkin"] as const)(
    "shows n_qp_const for %s",
    (backend) => {
      renderModal({ backend });
      expect(screen.queryByText(N_QP_CONST)).not.toBeNull();
    },
  );

  it.each(["bspline", "hmatrix", "arrayblock", "pynec"] as const)(
    "hides n_qp_const for %s",
    (backend) => {
      renderModal({ backend });
      expect(screen.queryByText(N_QP_CONST)).toBeNull();
    },
  );

  it.each(BSPLINE_FAMILY)("shows the B-spline knobs for %s", (backend) => {
    renderModal({ backend });
    expect(screen.queryByRole("tab", { name: "d=2" })).not.toBeNull();
    expect(screen.queryByText(N_QP_PAIR)).not.toBeNull();
  });

  it.each(["sinusoidal", "sinusoidal-galerkin", "pynec"] as const)(
    "hides the B-spline knobs for %s",
    (backend) => {
      renderModal({ backend });
      expect(screen.queryByRole("tab", { name: "d=2" })).toBeNull();
      expect(screen.queryByText(N_QP_PAIR)).toBeNull();
    },
  );

  it("shows the no-extra-knobs note for pynec only", () => {
    const { unmount } = renderModal({ backend: "pynec" });
    expect(screen.queryByText(/no extra solver knobs/)).not.toBeNull();
    unmount();
    renderModal({ backend: "bspline" });
    expect(screen.queryByText(/no extra solver knobs/)).toBeNull();
  });
});

describe("BackendConfigModal — Sin-Galerkin feed model", () => {
  it("offers the feed-model tabs only for sinusoidal-galerkin", () => {
    const { unmount } = renderModal({
      backend: "sinusoidal-galerkin",
      opts: sinGalerkinOpts(),
    });
    expect(screen.queryByRole("tab", { name: "Converged" })).not.toBeNull();
    expect(screen.queryByRole("tab", { name: "NEC-compatible" })).not.toBeNull();
    unmount();
    // Plain sinusoidal has no point-gap RHS, so it must not present the choice.
    renderModal({ backend: "sinusoidal" });
    expect(screen.queryByRole("tab", { name: "Converged" })).toBeNull();
  });

  it("patches feedModel to point when Converged is clicked", async () => {
    const { user, onPatch } = renderModal({
      backend: "sinusoidal-galerkin",
      opts: sinGalerkinOpts({ feedModel: "segment" }),
    });
    await user.click(screen.getByRole("tab", { name: "Converged" }));
    expect(onPatch).toHaveBeenCalledWith({ feedModel: "point" });
    expect(onPatch).toHaveBeenCalledTimes(1);
  });

  it("patches feedModel to segment when NEC-compatible is clicked", async () => {
    const { user, onPatch } = renderModal({
      backend: "sinusoidal-galerkin",
      opts: sinGalerkinOpts({ feedModel: "point" }),
    });
    await user.click(screen.getByRole("tab", { name: "NEC-compatible" }));
    expect(onPatch).toHaveBeenCalledWith({ feedModel: "segment" });
  });

  it("shows the Converged hint only when recommended and still on segment", () => {
    const hint = /near-open \/ high-Q/;
    const cases: Array<[boolean, "segment" | "point", boolean]> = [
      [true, "segment", true],
      [true, "point", false],
      [false, "segment", false],
      [false, "point", false],
    ];
    for (const [suggestConvergedFeed, feedModel, shown] of cases) {
      const { unmount } = renderModal({
        backend: "sinusoidal-galerkin",
        suggestConvergedFeed,
        opts: sinGalerkinOpts({ feedModel }),
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
      opts: bsplineOpts({ degree: 2 }),
    });
    expect(screen.getByRole("tab", { name: "d=2" }).getAttribute("aria-selected")).toBe("true");
    await user.click(screen.getByRole("tab", { name: "d=1" }));
    expect(onPatch).toHaveBeenCalledWith({ degree: 1 });
    expect(onPatch).toHaveBeenCalledTimes(1);
  });

  it("commits an edited number field as a patch on that key alone", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts({ nQpPair: 4 }),
    });
    await user.type(numberField(N_QP_PAIR), "2"); // "4" -> "42"
    expect(onPatch).toHaveBeenCalledWith({ nQpPair: 42 });
  });

  it("hides the smoothing sub-fields while the delta-gap is sharp", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts({ feedSmoothingFactor: null }),
    });
    const box = screen.getByRole("checkbox", { name: /feed source smoothing/ });
    expect(box).toHaveProperty("checked", false);
    expect(screen.queryByText(FEED_SMOOTHING_ALPHA)).toBeNull();
    expect(screen.queryByText(N_QP_SOURCE)).toBeNull();
  });

  it("shows the smoothing sub-fields once a factor is set", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts({ feedSmoothingFactor: 3 }),
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
      opts: bsplineOpts({ feedSmoothingFactor: null }),
    });
    await off.user.click(
      screen.getByRole("checkbox", { name: /feed source smoothing/ }),
    );
    expect(off.onPatch).toHaveBeenCalledWith({ feedSmoothingFactor: 3 });
    off.unmount();

    const on = renderModal({
      backend: "bspline",
      opts: bsplineOpts({ feedSmoothingFactor: 3 }),
    });
    await on.user.click(
      screen.getByRole("checkbox", { name: /feed source smoothing/ }),
    );
    expect(on.onPatch).toHaveBeenCalledWith({ feedSmoothingFactor: null });
  });
});

describe("BSplineFields — singular enrichment", () => {
  it("hides every enrichment sub-field while enrichment is off", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts({ useSingularEnrichment: false }),
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
      opts: bsplineOpts({ useSingularEnrichment: true }),
    });
    expect(screen.queryByText(N_QP_SING)).not.toBeNull();
    expect(screen.queryByText(ENRICHMENT_MIN_K)).not.toBeNull();
    expect(screen.getByRole("combobox")).toHaveProperty("value", "raw");
  });

  it("patches useSingularEnrichment on toggle", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts({ useSingularEnrichment: false }),
    });
    await user.click(
      screen.getByRole("checkbox", { name: /junction singular enrichment/ }),
    );
    expect(onPatch).toHaveBeenCalledWith({ useSingularEnrichment: true });
  });

  it("patches enrichmentVariant from the select", async () => {
    const { user, onPatch } = renderModal({
      backend: "bspline",
      opts: bsplineOpts({ useSingularEnrichment: true }),
    });
    await user.selectOptions(screen.getByRole("combobox"), "auto");
    expect(onPatch).toHaveBeenCalledWith({ enrichmentVariant: "auto" });
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
        opts: bsplineOpts({ useSingularEnrichment: true, enrichmentVariant }),
      });
      expect(screen.queryByText(TIKHONOV_LAMBDA) !== null).toBe(lambdaShown);
      expect(screen.queryByText(AUTO_TAP_THRESHOLD) !== null).toBe(thresholdShown);
    },
  );

  it("keeps the variant knobs hidden when enrichment itself is off", () => {
    renderModal({
      backend: "bspline",
      opts: bsplineOpts({
        useSingularEnrichment: false,
        enrichmentVariant: "tikhonov",
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
