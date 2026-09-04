import { useEffect } from "react";
import {
  backendAllowed,
  EK_HINT,
  extendedKernelActive,
  AXIS_KWARG,
  degreeChoices,
  renderableOptions,
  type ModelOptionSpecs,
  feedModelChoices,
  offersFeedModelChoice,
  type FeedModelChoice,
  RESTRICTED_BACKEND_REASON,
  type BackendEntry,
  type BackendOpts,
  type FeedModel,
  type Slot,
} from "../../lib/backends";
import { NumberField } from "./fields";
import { OptionField, specShownWith } from "./OptionField";

// Narrowing helpers for the flat option map (#1006 G2-6). `opts.model` is
// `Record<string, unknown>` because its KEYS are the server's, so the widgets
// narrow at the point of use rather than the map pretending to a shape it
// cannot have until the schema can describe every knob.
// The kwargs an AXIS governs — these keep bespoke widgets (tab pairs with
// their own vocabulary, the EK card) and are filtered out of the generic
// loop. Derived from `AXIS_KWARG` rather than listed again, so a new axis
// cannot be drawn twice.
const AXIS_GOVERNED = new Set(Object.values(AXIS_KWARG));

/** Why this knob is unavailable on this slot, or null — from the SERVED
 *  constraints, never from a rule written here.
 *
 *  The one live case is momwire's extended-kernel / singular-enrichment
 *  exclusion (momwire#888). The frontend used to carry its own sentence for
 *  that, which had drifted to citing a different issue than momwire's own
 *  prose; this reads the served row instead, so the two cannot disagree.
 */
function disabledReasonFor(
  b: BackendEntry,
  opts: BackendOpts,
  kwarg: string,
): string | null {
  if (!opts.model.extended_kernel) return null;
  const hit = (b.constraints ?? []).find(
    (c) =>
      c.axis === "kernel" &&
      c.value === "extended" &&
      c.forbids_axis === "singular_enrichment",
  );
  if (!hit || kwarg !== "use_singular_enrichment") return null;
  return hit.reason;
}

const num = (v: unknown): number | undefined =>
  typeof v === "number" ? v : undefined;
const str = (v: unknown): string | undefined =>
  typeof v === "string" ? v : undefined;

export type BackendConfigProps = {
  slot: Slot;
  backend: BackendEntry;
  backends: BackendEntry[];
  /** Per-design backend allowlist (`requires_backends`); null = all of
   *  `backends` selectable. Disallowed tabs render disabled with a tooltip
   *  explaining why, rather than disappearing — the picker stays stable
   *  across design switches and the restriction itself is the signal. */
  requiredBackends: string[] | null;
  /** The served solver-knob catalogue (#1006 G2-6): every knob's kind,
   *  bounds, captions and gate. The panel is drawn from this, not from a
   *  per-engine table here. */
  specs: ModelOptionSpecs;
  /** Current design recommends the Converged feed model (near-open high-Q,
   *  antennaknobs#478) — shown as a hint on the Sin-Galerkin feed-model
   *  control. */
  suggestConvergedFeed: boolean;
  opts: BackendOpts;
  onChangeBackend: (b: BackendEntry) => void;
  onPatch: (patch: Partial<BackendOpts>) => void;
  onReset: () => void;
  onClose: () => void;
};


export function BackendConfigModal({
  slot,
  backend,
  backends,
  requiredBackends,
  specs,
  suggestConvergedFeed,
  opts,
  onChangeBackend,
  onPatch,
  onReset,
  onClose,
}: BackendConfigProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="backend-config-overlay" onClick={onClose}>
      <div
        className="backend-config-modal"
        role="dialog"
        aria-label={`Slot ${slot} options`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="backend-config-header">
          <strong>Slot {slot} — {backend.label}</strong>
          <button className="backend-config-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="backend-config-body">
          <div className="field">
            <label>
              <span>solver</span>
              <span>{backend.label}</span>
            </label>
            {/* Tabs, order and labels are the served roster's (#628): a solver
                registered server-side appears here with no frontend change. */}
            <div className="geometry-tabs" role="tablist">
              {backends.map((b) => {
                const allowed = backendAllowed(b, requiredBackends);
                return (
                  <button
                    key={b.name}
                    role="tab"
                    aria-selected={backend.name === b.name}
                    className={backend.name === b.name ? "active" : ""}
                    disabled={!allowed}
                    title={allowed ? undefined : RESTRICTED_BACKEND_REASON}
                    onClick={() => allowed && onChangeBackend(b)}
                  >
                    {b.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Mesh sizing is common to every backend and stays client-side —
              it is geometry, not a solver kwarg (it never rides
              model_options). Only its default is per-backend, and that the
              roster carries. */}
          <NumberField
            label="segments / wire (N)"
            value={opts.nPerWire}
            min={4}
            max={120}
            step={1}
            onChange={(v) => onPatch({ nPerWire: v })}
          />
          <NumberField
            label="wire radius (m)"
            value={opts.wireRadius}
            step={0.0001}
            onChange={(v) => onPatch({ wireRadius: v })}
          />

          {/* The extended thin-wire kernel (issue #849) sits next to the wire
              radius on purpose — it is the knob that decides how the on-axis
              Green's function treats that radius. Common to every momwire
              backend, so it lives here rather than in a bespoke panel; PyNEC
              gets no row at all (it sends no model_options, and its own
              extended kernel — issue #414 — is a separate, unexposed kwarg). */}
          {backend.kind === "momwire" && (
            <ExtendedKernelField backend={backend} opts={opts} onPatch={onPatch} />
          )}

          {/* Degree tabs, from the `basis` axis (#1006 G2-5). Rendered
              whenever the backend offers ANY degree, not only two: that is
              what the bespoke panel did, and a backend whose basis axis
              carried one value would otherwise lose the control that says
              which. `degreeChoices` already returns [] for a backend that
              does not expose `degree` at all, which is what keeps this off
              pynec. */}
          {degreeChoices(backend).length > 0 && (
            <DegreeField
              degrees={degreeChoices(backend)}
              value={num(opts.model.degree)}
              onSelect={(d) => onPatch({ model: { ...opts.model, degree: d } })}
            />
          )}

          {/* THE SOLVER KNOBS, drawn from the served catalogue (#1006 G2-6).
              No engine names, no panel hints, no per-knob branches: which
              knobs appear is `renderableOptions`, and each one's widget,
              bounds, captions and gate are the server's.

              The AXIS-GOVERNED controls are not here — `feed_model` and
              `degree` are compositional choices with their own vocabulary
              (tab pairs with real labels and tooltips) and `extended_kernel`
              is the EK card above. They keep their bespoke widgets, which is
              the same split the offered-vs-sent rule describes. */}
          {renderableOptions(backend, specs)
            .filter((k) => !AXIS_GOVERNED.has(k))
            .filter((k) => specShownWith(specs[k]!, opts.model, specs))
            .map((k) => (
              <OptionField
                key={k}
                name={k}
                spec={specs[k]!}
                model={opts.model}
                disabledReason={disabledReasonFor(backend, opts, k)}
                onPatch={(patch) =>
                  onPatch({ model: { ...opts.model, ...patch } })
                }
              />
            ))}



          {/* The axis-derived feed-model control (#1006 G2-5): it renders
              wherever `feed_model` is multi-valued, which is what the
              `sin-galerkin` panel hint used to mean. The hint survives only
              inside `feedModelChoices`, as the fallback for a momwire that
              cannot describe itself — it goes with the PyPI pin bump. */}
          {offersFeedModelChoice(backend) && (
            <FeedModelField
              choices={feedModelChoices(backend)}
              value={(str(opts.model.feed_model) as FeedModel) ?? "segment"}
              suggestConvergedFeed={suggestConvergedFeed}
              onSelect={(v) =>
                onPatch({ model: { ...opts.model, feed_model: v } })
              }
            />
          )}

          {renderableOptions(backend, specs).length === 0 &&
            backend.kind !== "momwire" && (
              <em style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>
                {backend.label} has no extra solver knobs here — ground type /
                fast ground live in the main panel.
              </em>
            )}
        </div>

        <div className="backend-config-footer">
          <button className="backend-config-reset" onClick={onReset}>
            reset to defaults
          </button>
        </div>
      </div>
    </div>
  );
}

// The muted one-liner under a control, as the Converged-feed hint spells it.
const NOTE_STYLE = { color: "var(--muted)", fontSize: "var(--text-sm)" };

// The EK card as a per-slot checkbox. Two combinations refuse upstream
// (momwire#246 Galerkin, momwire#271 enrichment); rather than let the user
// arm one and read the refusal out of the error banner, the box greys out and
// the reason is on the page. `checked` reads the ACTIVE state, so a disabled
// row is never shown ticked.
function ExtendedKernelField({
  backend,
  opts,
  onPatch,
}: {
  backend: BackendEntry;
  opts: BackendOpts;
  onPatch: (patch: Partial<BackendOpts>) => void;
}) {
  // The enrichment exclusion is momwire's and arrives in `constraints`
  // (momwire#888). The local `extendedKernelRefusal` that used to grey this
  // out was a hand-written copy citing the wrong issue; it is gone. Until the
  // renderer PR wires the served row into this control, the exclusion is
  // enforced where it always also was — momwire refuses the combination and
  // the solve path reports it.
  return (
    <div className="field">
      <label className="link-toggle" title={EK_HINT}>
        <input
          type="checkbox"
          checked={extendedKernelActive(backend, opts)}
          onChange={(e) =>
            onPatch({ model: { ...opts.model, extended_kernel: e.target.checked } })
          }
        />
        extended kernel (EK)
      </label>
      <em style={NOTE_STYLE}>
        {"For fat wires — segments not much longer than the radius (Δ/a " +
          "below ~10). Thin-wire designs move a fraction of a percent."}
      </em>
    </div>
  );
}

function FeedModelField({
  choices,
  value,
  suggestConvergedFeed,
  onSelect,
}: {
  /** From the `feed_model` AXIS (lib/backends.ts), not a literal here. The
   *  labels and tooltips still live in that table — the axis says which gaps
   *  the solver implements, not what to call them. */
  choices: FeedModelChoice[];
  value: FeedModel;
  suggestConvergedFeed: boolean;
  /** Just the choice — the caller owns how it lands in the option map, so
   *  this component knows nothing about the option state's shape. */
  onSelect: (v: FeedModel) => void;
}) {
  return (
    <div className="field">
      <label>
        <span>feed model</span>
      </label>
      <div className="geometry-tabs" role="tablist">
        {choices.map((c) => (
          <button
            key={c.value}
            role="tab"
            aria-selected={value === c.value}
            className={value === c.value ? "active" : ""}
            title={c.title}
            onClick={() => onSelect(c.value)}
          >
            {c.label}
          </button>
        ))}
      </div>
      {suggestConvergedFeed && value === "segment" && (
        <em
          style={{
            color: "var(--muted)",
            fontSize: "var(--text-sm)",
          }}
        >
          This design's feed is near-open / high-Q: "Converged" is
          recommended — it removes up to ~1000× of the cross-basis
          disagreement here (momwire#213). "NEC-compatible" remains
          right for NEC cross-checks.
        </em>
      )}
    </div>
  );
}

/** The B-spline degree tabs, from the `basis` AXIS (#1006 G2-5).
 *
 *  The one control the old bespoke panel held that IS a compositional
 *  choice. The other nine — quadrature orders, the bump width, singular
 *  enrichment and its variant — are ordinary knobs and are drawn by
 *  `OptionField` from the served catalogue, which is why that panel is gone.
 */
function DegreeField({
  degrees,
  value,
  onSelect,
}: {
  degrees: (1 | 2)[];
  value: number | undefined;
  onSelect: (d: 1 | 2) => void;
}) {
  return (
    <div className="field">
      <label>
        <span>degree</span>
        <span>{value}</span>
      </label>
      <div className="geometry-tabs" role="tablist">
        {degrees.map((d) => (
          <button
            key={d}
            role="tab"
            aria-selected={value === d}
            className={value === d ? "active" : ""}
            onClick={() => onSelect(d)}
          >
            d={d}
          </button>
        ))}
      </div>
    </div>
  );
}
