import { useEffect } from "react";
import {
  backendAllowed,
  BACKEND_LABEL,
  isBSplineFamily,
  RESTRICTED_BACKEND_REASON,
  type Backend,
  type BackendOptsMap,
  type BSplineOpts,
  type SinGalerkinOpts,
  type SinusoidalOpts,
  type Slot,
} from "../../lib/backends";
import { NumberField } from "./fields";

export type BackendConfigProps = {
  slot: Slot;
  backend: Backend;
  backends: Backend[];
  /** Per-design backend allowlist (`requires_backends`); null = all of
   *  `backends` selectable. Disallowed tabs render disabled with a tooltip
   *  explaining why, rather than disappearing — the picker stays stable
   *  across design switches and the restriction itself is the signal. */
  requiredBackends: string[] | null;
  /** Current design recommends the Converged feed model (near-open high-Q,
   *  antennaknobs#478) — shown as a hint on the Sin-Galerkin feed-model
   *  control. */
  suggestConvergedFeed: boolean;
  opts: BackendOptsMap[Backend];
  onChangeBackend: (b: Backend) => void;
  onPatch: (patch: Partial<BackendOptsMap[Backend]>) => void;
  onReset: () => void;
  onClose: () => void;
};

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
          <strong>Slot {slot} — {BACKEND_LABEL[backend]}</strong>
          <button className="backend-config-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="backend-config-body">
          <div className="field">
            <label>
              <span>solver</span>
              <span>{BACKEND_LABEL[backend]}</span>
            </label>
            <div className="geometry-tabs" role="tablist">
              {backends.map((b) => {
                const allowed = backendAllowed(b, requiredBackends);
                return (
                  <button
                    key={b}
                    role="tab"
                    aria-selected={backend === b}
                    className={backend === b ? "active" : ""}
                    disabled={!allowed}
                    title={allowed ? undefined : RESTRICTED_BACKEND_REASON}
                    onClick={() => allowed && onChangeBackend(b)}
                  >
                    {BACKEND_LABEL[b]}
                  </button>
                );
              })}
            </div>
          </div>

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

          {(backend === "sinusoidal" || backend === "sinusoidal-galerkin") && (
            <NumberField
              label="n_qp_const (GL pts)"
              value={(opts as SinusoidalOpts).nQpConst}
              min={2}
              max={32}
              step={1}
              onChange={(v) => onPatch({ nQpConst: v } as never)}
            />
          )}

          {backend === "sinusoidal-galerkin" && (
            <div className="field">
              <label>
                <span>feed model</span>
              </label>
              <div className="geometry-tabs" role="tablist">
                {(
                  [
                    ["segment", "NEC-compatible"],
                    ["point", "Converged"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    role="tab"
                    aria-selected={
                      (opts as SinGalerkinOpts).feedModel === value
                    }
                    className={
                      (opts as SinGalerkinOpts).feedModel === value
                        ? "active"
                        : ""
                    }
                    title={
                      value === "segment"
                        ? "NEC's segment-wide gap: reproduces NEC/EZNEC " +
                          "behaviour, including reactance drift with mesh " +
                          "density. Use when cross-checking against NEC " +
                          "results."
                        : "Zero-width (point) gap: converges to the " +
                          "B-spline answer and gives a reciprocal Y. " +
                          "Recommended for near-open high-Q designs " +
                          "(momwire#213)."
                    }
                    onClick={() => onPatch({ feedModel: value } as never)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {suggestConvergedFeed &&
                (opts as SinGalerkinOpts).feedModel === "segment" && (
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
          )}

          {isBSplineFamily(backend) && (
            <BSplineFields
              opts={opts as BSplineOpts}
              onPatch={(p) => onPatch(p as never)}
            />
          )}

          {backend === "pynec" && (
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

function BSplineFields({
  opts,
  onPatch,
}: {
  opts: BSplineOpts;
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
          {[1, 2].map((d) => (
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
      <NumberField
        label="n_qp_pair (GL pts/axis)"
        value={opts.nQpPair}
        min={2}
        max={16}
        step={1}
        onChange={(v) => onPatch({ nQpPair: v })}
      />
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
        <label className="link-toggle" title="VALIDATION ONLY. Adds (u/h)·log(u/h) singular basis at K ≥ enrichment_min_k junctions. This flips O(1/N) → ~O(1/N^(d+1)) for LOW-ORDER bases (sinusoidal); the d=2 B-spline already converges at that rate on its own, so enrichment is redundant here and adds a coarse-mesh transient. See issue #565.">
          <input
            type="checkbox"
            checked={opts.useSingularEnrichment}
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
