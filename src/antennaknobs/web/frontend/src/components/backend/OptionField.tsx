// The generic solver-knob renderer (antennaknobs#1006 G2-6).
//
// One component for every knob the server describes, replacing the bespoke
// per-engine panels. It carries NO engine names and no per-knob branches: the
// widget follows from the spec's `kind`, the bounds and captions are the
// server's, and which knobs appear at all is `renderableOptions`.
//
// WHAT THIS DELIBERATELY DOES NOT DRAW: the axis-governed controls. `degree`
// and `feed_model` are compositional choices with their own vocabulary — tab
// pairs with real labels and tooltips — and `extended_kernel` is the EK card.
// Those keep their bespoke widgets and are filtered out by the caller. The
// offered-vs-sent rule in lib/backends.ts is the same split: an axis decides
// whether its kwarg is offered, and a knob with no axis is drawn from here.
import { NumberField } from "./fields";
import type { ModelOptionSpec } from "../../lib/backends";

/** Is `spec`'s gate satisfied — including every gate ITS gate depends on?
 *
 *  GATES CHAIN, and resolving them transitively is what reproduces the old
 *  panel's nesting without any chain syntax in the payload:
 *
 *      tikhonov_lambda -> enrichment_variant -> use_singular_enrichment
 *
 *  A single-level check would show `tikhonov_lambda` whenever the variant
 *  happened to read "tikhonov", even with enrichment switched off — the
 *  variant keeps its value while hidden.
 *
 *  The Python side asserts the chain is acyclic and shallow, so the walk
 *  below terminates; the `seen` guard is belt-and-braces for a payload that
 *  did not come from there.
 */
export function specShownWith(
  spec: ModelOptionSpec,
  model: Record<string, unknown>,
  specs: Record<string, ModelOptionSpec> = {},
): boolean {
  let cur: ModelOptionSpec | undefined = spec;
  const seen = new Set<string>();
  while (cur && cur.shown_when) {
    const key: string = cur.shown_when;
    if (seen.has(key)) return true; // cyclic payload: render rather than hide
    seen.add(key);
    const gate = model[key];
    if (cur.shown_when_value !== null && cur.shown_when_value !== undefined) {
      if (gate !== cur.shown_when_value) return false;
    } else if (!gate) {
      // TRUTHY, not `=== true`: `n_qp_source` is gated on
      // `feed_smoothing_factor`, a nullable number.
      return false;
    }
    cur = specs[key];
  }
  return true;
}

/** The render bounds, omitting any the server left unset.
 *
 *  Spread rather than passed as `min={spec.min}`: under
 *  `exactOptionalPropertyTypes` an explicit `undefined` is not the same as an
 *  absent prop, and passing one would put `min=""` on the input.
 */
function bounds(spec: ModelOptionSpec) {
  return {
    ...(spec.min === undefined ? {} : { min: spec.min }),
    ...(spec.max === undefined ? {} : { max: spec.max }),
    ...(spec.step === undefined ? {} : { step: spec.step }),
  };
}

/** A knob whose null means something — either "auto" or "off". */
function isGated(spec: ModelOptionSpec): boolean {
  return Boolean(spec.auto_when_null || spec.allow_none);
}

export function OptionField({
  name,
  spec,
  model,
  disabledReason,
  onPatch,
}: {
  name: string;
  spec: ModelOptionSpec;
  model: Record<string, unknown>;
  /** Why this control is unavailable, or null. Comes from the SERVED
   *  constraints (momwire#888) — never from a rule written here, which is
   *  what the deleted `extendedKernelRefusal` was and why it had drifted to
   *  citing the wrong issue. */
  disabledReason?: string | null;
  onPatch: (patch: Record<string, unknown>) => void;
}) {
  const value = model[name];

  if (spec.kind === "bool") {
    return (
      <div className="field">
        <label
          className="link-toggle"
          {...(disabledReason ? { title: disabledReason } : {})}
        >
          <input
            type="checkbox"
            checked={value === true}
            disabled={Boolean(disabledReason)}
            onChange={(e) => onPatch({ [name]: e.target.checked })}
          />
          {spec.label}
        </label>
      </div>
    );
  }

  if (spec.kind === "enum") {
    return (
      <div className="field">
        <label>
          {spec.label}
          <select
            value={typeof value === "string" ? value : ""}
            onChange={(e) => onPatch({ [name]: e.target.value })}
          >
            {(spec.values ?? []).map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
    );
  }

  const num = typeof value === "number" ? value : undefined;

  if (isGated(spec)) {
    // POLARITY IS DERIVED, not stored. `auto_when_null` means the box reads
    // "auto" and is CHECKED WHEN NULL; `allow_none` alone means the box turns
    // the knob ON and is checked when set. Getting this backwards would
    // invert two live controls, so both directions are pinned by tests.
    const isNull = value === null || value === undefined;
    const checked = spec.auto_when_null ? isNull : !isNull;
    // The value the gate switches ON to, from the server. NOT the spec
    // default — `n_qp_pair`'s default IS null (auto), and unticking auto has
    // always pinned 8. Guessing here would invent a different panel.
    const onValue = spec.gate_on_value ?? spec.min ?? 1;
    return (
      <div className="field">
        <label className="link-toggle">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => {
              const wantsNull = spec.auto_when_null ? e.target.checked : !e.target.checked;
              onPatch({ [name]: wantsNull ? null : onValue });
            }}
          />
          {spec.gate_label ?? spec.label}
        </label>
        {!isNull && (
          <NumberField
            label={spec.label}
            value={num ?? onValue}
            {...bounds(spec)}
            onChange={(v) => onPatch({ [name]: v })}
          />
        )}
      </div>
    );
  }

  return (
    <NumberField
      label={spec.label}
      value={num ?? (typeof spec.default === "number" ? spec.default : 0)}
      {...bounds(spec)}
      onChange={(v) => onPatch({ [name]: v })}
    />
  );
}
