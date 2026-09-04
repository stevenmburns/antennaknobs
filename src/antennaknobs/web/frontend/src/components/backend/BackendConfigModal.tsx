import { useEffect } from "react";
import {
  backendAllowed,
  BSPLINE_DEFAULT_OPTS,
  EK_ENRICHMENT_REASON,
  EK_HINT,
  extendedKernelActive,
  extendedKernelRefusal,
  PANEL_BSPLINE,
  degreeChoices,
  feedModelChoices,
  offersFeedModelChoice,
  type FeedModelChoice,
  PANEL_PYNEC,
  RESTRICTED_BACKEND_REASON,
  type BackendEntry,
  type BackendOpts,
  type BSplineOpts,
  type FeedModel,
  type Slot,
} from "../../lib/backends";
import { NumberField } from "./fields";

export type BackendConfigProps = {
  slot: Slot;
  backend: BackendEntry;
  backends: BackendEntry[];
  /** Per-design backend allowlist (`requires_backends`); null = all of
   *  `backends` selectable. Disallowed tabs render disabled with a tooltip
   *  explaining why, rather than disappearing — the picker stays stable
   *  across design switches and the restriction itself is the signal. */
  requiredBackends: string[] | null;
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

// Shared by the auto toggle and the pinned field so the two cannot drift.
const N_QP_PAIR_TITLE =
  "Gauss-Legendre points per segment per axis for cross-edge pair moments. Auto lets momwire choose per deck — it uses a higher order when the deck has wire at or below the ground, and the shipped order otherwise. It matters only on decks that reach the ground: on `verticals.buried_radial_vertical` at its default hub spelling the shipped order of 8 sits 0.17 \u03a9 from the converged answer, essentially all of it reactive, and 32 closes that to 0.0047 \u03a9; on a deck standing clear of the ground the two differ by 0.02 \u03a9, so on a dipole expect to see nothing. Pin a number only to reproduce a specific run \u2014 raising it is cheap on these decks (momwire#778).";

export function BackendConfigModal({
  slot,
  backend,
  backends,
  requiredBackends,
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

          {/* Generic numeric knobs, straight from the served options_schema —
              the same schema-driven loop the terrain panel uses (#560). */}
          {backend.options_schema.map((f) => (
            <NumberField
              key={f.key}
              label={f.label}
              value={opts.schema[f.key] ?? f.default}
              min={f.min}
              max={f.max}
              step={f.step}
              onChange={(v) =>
                onPatch({ schema: { ...opts.schema, [f.key]: v } })
              }
            />
          ))}

          {/* The feed-model control is AXIS-DERIVED (#1006 G2-5): it renders
              wherever `feed_model` is multi-valued, which is what the
              `sin-galerkin` panel hint used to mean. The hint survives only
              inside `feedModelChoices` as the fallback for a momwire that
              cannot describe itself.

              The B-spline panel stays bespoke and is still selected by the
              hint. Only its degree tabs are an axis; the quadrature orders,
              bump width, singular enrichment and its variant are not, so
              there is nothing for the axis vocabulary to replace them with. */}
          {offersFeedModelChoice(backend) && (
            <FeedModelField
              choices={feedModelChoices(backend)}
              value={opts.feedModel ?? "segment"}
              suggestConvergedFeed={suggestConvergedFeed}
              onPatch={onPatch}
            />
          )}

          {backend.panel === PANEL_BSPLINE && (
            <BSplineFields
              opts={opts.bspline ?? BSPLINE_DEFAULT_OPTS}
              degrees={degreeChoices(backend)}
              extendedKernel={extendedKernelActive(backend, opts)}
              onPatch={(p) =>
                onPatch({
                  bspline: { ...(opts.bspline ?? BSPLINE_DEFAULT_OPTS), ...p },
                })
              }
            />
          )}

          {backend.panel === PANEL_PYNEC && (
            <em style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>
              PyNEC has no extra solver knobs here — ground type / fast ground
              live in the main panel.
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
  const refusal = extendedKernelRefusal(backend, opts);
  return (
    <div className="field">
      <label className="link-toggle" title={refusal ?? EK_HINT}>
        <input
          type="checkbox"
          checked={extendedKernelActive(backend, opts)}
          disabled={refusal !== null}
          onChange={(e) => onPatch({ extendedKernel: e.target.checked })}
        />
        extended kernel (EK)
      </label>
      <em style={NOTE_STYLE}>
        {refusal ??
          "For fat wires — segments not much longer than the radius (Δ/a " +
            "below ~10). Thin-wire designs move a fraction of a percent."}
      </em>
    </div>
  );
}

function FeedModelField({
  choices,
  value,
  suggestConvergedFeed,
  onPatch,
}: {
  /** From the `feed_model` AXIS (lib/backends.ts), not a literal here. The
   *  labels and tooltips still live in that table — the axis says which gaps
   *  the solver implements, not what to call them. */
  choices: FeedModelChoice[];
  value: FeedModel;
  suggestConvergedFeed: boolean;
  onPatch: (patch: Partial<BackendOpts>) => void;
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
            onClick={() => onPatch({ feedModel: c.value })}
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

function BSplineFields({
  opts,
  degrees,
  extendedKernel,
  onPatch,
}: {
  opts: BSplineOpts;
  /** The degree tabs, from the `basis` AXIS. The ONLY axis-derived control in
   *  this panel — the quadrature orders, bump width and singular enrichment
   *  below are not axes, which is why this panel survives #1006 G2-5 while the
   *  sin-Galerkin one dissolved into its single axis. */
  degrees: (1 | 2)[];
  /** The slot's extended kernel is in force — enrichment is unavailable while
   *  it is (momwire#271). The exclusion is symmetric (the EK row greys out
   *  while enrichment is on), so neither box can lock the other. */
  extendedKernel: boolean;
  onPatch: (p: Partial<BSplineOpts>) => void;
}) {
  return (
    <>
      <div className="field">
        <label>
          <span>degree</span>
          <span>{opts.degree}</span>
        </label>
        <div className="geometry-tabs" role="tablist">
          {degrees.map((d) => (
            <button
              key={d}
              role="tab"
              aria-selected={opts.degree === d}
              className={opts.degree === d ? "active" : ""}
              onClick={() => onPatch({ degree: d as 1 | 2 })}
            >
              d={d}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <label className="link-toggle" title={N_QP_PAIR_TITLE}>
          <input
            type="checkbox"
            checked={opts.nQpPair == null}
            onChange={(e) => onPatch({ nQpPair: e.target.checked ? null : 8 })}
          />
          n_qp_pair: auto
        </label>
        {opts.nQpPair != null && (
          <NumberField
            label="n_qp_pair (GL pts/axis)"
            title={N_QP_PAIR_TITLE}
            value={opts.nQpPair}
            min={2}
            max={32}
            step={1}
            onChange={(v) => onPatch({ nQpPair: v })}
          />
        )}
      </div>
      <div className="field">
        <label className="link-toggle" title="Replace the delta-gap with a cos² source of width α·h_feed; removes the delta-gap's O(1/N) convergence cap so a straight-wire feed converges at the basis rate.">
          <input
            type="checkbox"
            checked={opts.feedSmoothingFactor != null}
            onChange={(e) =>
              onPatch({ feedSmoothingFactor: e.target.checked ? 3 : null })
            }
          />
          feed source smoothing
        </label>
        {opts.feedSmoothingFactor != null && (
          <NumberField
            label="α (bump width / h_feed)"
            value={opts.feedSmoothingFactor}
            min={0.5}
            max={10}
            step={0.5}
            onChange={(v) => onPatch({ feedSmoothingFactor: v })}
          />
        )}
        {opts.feedSmoothingFactor != null && (
          <NumberField
            label="n_qp_source"
            value={opts.nQpSource}
            min={4}
            max={64}
            step={1}
            onChange={(v) => onPatch({ nQpSource: v })}
          />
        )}
      </div>
      <div className="backend-config-section">validation · experimental</div>
      <p className="backend-config-note">
        The d=2 basis already resolves K≥3 junctions — enrichment does not
        improve a d=2 solve, and worsens it at coarse mesh (issue #565). Kept
        as a validation tool against the low-order (sinusoidal) basis, where the
        junction singularity genuinely matters. Not needed for production.
      </p>
      <div className="field">
        <label
          className="link-toggle"
          title={
            extendedKernel
              ? EK_ENRICHMENT_REASON
              : "VALIDATION ONLY. Adds (u/h)·log(u/h) singular basis at K ≥ enrichment_min_k junctions. This flips O(1/N) → ~O(1/N^(d+1)) for LOW-ORDER bases (sinusoidal); the d=2 B-spline already converges at that rate on its own, so enrichment is redundant here and adds a coarse-mesh transient. See issue #565."
          }
        >
          <input
            type="checkbox"
            checked={opts.useSingularEnrichment}
            disabled={extendedKernel}
            onChange={(e) => onPatch({ useSingularEnrichment: e.target.checked })}
          />
          K≥3 junction singular enrichment
        </label>
        {opts.useSingularEnrichment && (
          <>
            <NumberField
              label="n_qp_sing (GL pts/axis)"
              value={opts.nQpSing}
              min={8}
              max={64}
              step={1}
              onChange={(v) => onPatch({ nQpSing: v })}
            />
            <NumberField
              label="enrichment_min_k"
              value={opts.enrichmentMinK}
              min={2}
              max={6}
              step={1}
              onChange={(v) => onPatch({ enrichmentMinK: v })}
            />
            <label
              className="link-toggle"
              title="raw = original Φ_sing = (u/h)·log(u/h); stable = Φ_sing minus bubble-subspace L²-projection (loses Y cusp); tikhonov = raw + λ·s·I penalty on Z_ee (shrinks all α uniformly); auto = two-pass per-junction selectivity via tap_ratio (dominant-pair K=3 → off, balanced 3-way → on)."
            >
              variant:
              <select
                value={opts.enrichmentVariant}
                onChange={(e) =>
                  onPatch({
                    enrichmentVariant: e.target.value as
                      | "raw"
                      | "stable"
                      | "tikhonov"
                      | "auto",
                  })
                }
              >
                <option value="raw">raw</option>
                <option value="stable">stable</option>
                <option value="tikhonov">tikhonov</option>
                <option value="auto">auto</option>
              </select>
            </label>
            {opts.enrichmentVariant === "tikhonov" && (
              <NumberField
                label="tikhonov_lambda (λ)"
                value={opts.tikhonovLambda}
                min={0}
                max={10}
                step={0.05}
                onChange={(v) => onPatch({ tikhonovLambda: v })}
              />
            )}
            {opts.enrichmentVariant === "auto" && (
              <NumberField
                label="auto_tap_ratio_threshold"
                value={opts.autoTapRatioThreshold}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => onPatch({ autoTapRatioThreshold: v })}
              />
            )}
          </>
        )}
      </div>
    </>
  );
}
