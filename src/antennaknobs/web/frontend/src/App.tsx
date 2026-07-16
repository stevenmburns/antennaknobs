import {
  createContext,
  Fragment,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { CSSProperties } from "react";

type Wire = {
  label: string;
  knot_positions: [number, number, number][];
  knot_currents_re: number[];
  knot_currents_im: number[];
  // Optional finer-grained samples: knots interleaved with segment midpoints
  // (length 2*N_seg + 1). Present from momwire backends, absent from PyNEC.
  sample_positions?: [number, number, number][];
  sample_currents_re?: number[];
  sample_currents_im?: number[];
};

// Schema served by `GET /examples`. The backend's web/examples/_base.py
// owns the source of truth; this type just mirrors the JSON shape.
type SchemaEnumOption = {
  value: string;
  label: string;
  // Free-form metadata. Fan_dipole's band entries carry freq_min /
  // freq_max / freq_default for range_from_enum_option + on_change_set.
  [key: string]: unknown;
};

type SchemaParamSpec = {
  name: string;
  label: string;
  default: number | string | boolean;
  kind: "float" | "int" | "bool" | "enum";
  min: number | null;
  max: number | null;
  step: number | null;
  precision: number;
  unit: string | null;
  visible_when: { name: string; op: string; value: number } | null;
  enum_options?: SchemaEnumOption[] | null;
  range_from_enum_option?: { param: string; min_key: string; max_key: string } | null;
  on_change_set?: { set: string; from_enum_key: string } | null;
  linked_to_design_freq?: boolean;
  // Flat-schema sibling of the group-level link: when this scalar
  // changes, push the current value of the named sibling param into
  // measFreq. Self-reference is allowed (and used by freq_NN params
  // in multi-band antennas).
  link_meas_freq_to_param?: string | null;
  // Optional explicit placement in the param grid (1-indexed CSS grid
  // lines). When present the field opts out of auto-flow and lands at the
  // given row/col, optionally spanning multiple tracks. null = auto-flow.
  layout?: KnobLayout | null;
};

// Per-knob grid placement. All fields optional; mapped onto inline
// grid-row / grid-column. Pairs with ExampleDescriptor.layout.columns.
type KnobLayout = {
  row?: number | null;
  col?: number | null;
  row_span?: number | null;
  col_span?: number | null;
};

type SchemaParamGroupSpec = {
  kind: "group";
  name: string;
  label_template: string;
  repeat_count: string;
  max_repeats: number;
  params: SchemaItem[];
  default_overrides: { [param: string]: unknown }[];
  // When set, names a sibling param inside this group's `params`
  // (typically "freq") whose per-instance value the frontend pushes
  // into the global measFreq state on every touch of any leaf inside
  // that instance. Gated by the linkMeas toggle.
  link_meas_freq_to_param?: string | null;
};

type SchemaItem = SchemaParamSpec | SchemaParamGroupSpec;

function isGroup(item: SchemaItem): item is SchemaParamGroupSpec {
  return (item as SchemaParamGroupSpec).kind === "group";
}

// State for a schema-driven antenna: nested map where scalars are
// numbers (float/int) or strings (enum), and groups are arrays of
// child bags (one per instance, pre-allocated to max_repeats).
type ParamValueBag = {
  [key: string]: number | string | boolean | ParamValueBag[];
};

type ResultFieldSpec = {
  field: string;
  label: string;
  precision: number;
  unit: string | null;
};

type SweepPolicy = {
  anchor: "design_freq" | "meas_freq";
  lo_factor: number;
  hi_factor: number;
  band_locked?: boolean;
};

type BandSpec = {
  key: string;
  label: string;
  freq_mhz: number;
  min_mhz: number;
  max_mhz: number;
};

type ResultGroupItem = {
  kind: "group";
  name: string;
  label_template: string;
  fields: ResultFieldSpec[];
};
type ResultSchemaItem = ResultFieldSpec | ResultGroupItem;

type ExampleDescriptor = {
  name: string;
  label: string;
  multi_feed: boolean;
  param_schema: SchemaItem[];
  result_schema: ResultSchemaItem[];
  bands: BandSpec[];
  meas_freq_range_mhz: [number, number] | null;
  /** Null for a deferred (user) design with no override — the real view is
   *  auto-detected and arrives with the first geometry/solve response. */
  default_view: Projection | null;
  /** The freq this antenna is naturally designed for. Used by the
   *  band-snap-on-example-change effect; null = no preferred freq. */
  default_freq_mhz: number | null;
  /** Recommended solver backend for this design (e.g. "arrayblock" for grid
   *  arrays). The active slot's backend is seeded from this on selection
   *  unless the user has manually picked a backend. null = keep the UI
   *  default. Typed as a plain string because the server may name a backend
   *  this UI has retired (e.g. "triangular"); run it through
   *  normalizeBackend before use. */
  default_backend: string | null;
  /** True when the Builder has a `design_freq` param that scales
   *  geometry (design_freq-sized designs). When false, the design-freq
   *  band-tab row is hidden because dragging it would be a no-op. */
  has_design_freq: boolean;
  /** Alternate seed dicts on the Builder, e.g. ["default", "opt"].
   *  The bare name is what the frontend sends back in `variant`.
   *  Single-entry lists ("default") hide the selector. */
  variants: string[];
  /** Per-variant param values, keyed by variant name. Lets the UI
   *  reset the schema sliders + design freq when the user switches
   *  variants. Complex-valued params arrive as {re, im}. */
  variant_values: { [variant: string]: { [key: string]: unknown } };
  sweep_policy: SweepPolicy;
  /** Informational note shown under the antenna selector — deck-backed
   *  designs list the NEC cards the import recorded but did not apply.
   *  null (the norm) renders nothing. */
  notes?: string | null;
  /** Per-variant UI-hint overrides, keyed by variant name. Only variants
   *  whose derived hints differ from the design-level values appear; look up
   *  the active variant and fall back to the top-level field (e.g.
   *  `sweep_policy`) for any variant not listed. */
  variant_ui?: {
    [variant: string]: {
      sweep_policy?: SweepPolicy;
      /** Explicit per-param presentation overrides for this variant
       *  (slider min/max/step, precision, unit, label), overlaid on
       *  param_schema entries by name. Values come from variant_values,
       *  never from here. */
      params?: {
        [name: string]: Partial<
          Pick<
            SchemaParamSpec,
            "min" | "max" | "step" | "precision" | "unit" | "label"
          >
        > & { hidden?: boolean };
      };
    };
  };
  /** Grid-level layout for the top-level knob rail. {columns: N} pins the
   *  grid to a fixed column count so per-knob `layout.col` positions are
   *  stable. null = responsive auto-flow packing. */
  layout?: { columns?: number | null } | null;
};

// One advisory finding from the design screener (what a design does that a
// typical one doesn't), attached to a trust-required entry.
type DesignAdvisory = { severity: string; message: string; line: number };

// A user design reported by GET /examples that didn't register. Either a real
// load error (bad Python), or — when `trust_required` — a design that loaded
// fine but hasn't been trusted to run yet, carrying its screener `advisory`.
type DesignLoadError = {
  name: string;
  file: string;
  message: string;
  trust_required?: boolean;
  advisory?: DesignAdvisory[];
};

// Design names are `family.design` (e.g. "dipoles.invvee"). The selector
// groups by that family prefix; this fixes display order + labels and keeps
// any unknown family rendering last under its bare name.
const FAMILY_ORDER = [
  "user", "dipoles", "loops", "verticals", "beams", "wire",
  "broadband", "multiband", "specialty", "arrays",
] as const;
const FAMILY_LABELS: Record<string, string> = {
  user: "Your designs", dipoles: "Dipoles", loops: "Loops",
  verticals: "Verticals", beams: "Beams", wire: "Wire / traveling-wave",
  broadband: "Broadband", multiband: "Multiband", specialty: "Specialty",
  arrays: "Arrays",
};
// Extra search keywords so cryptic or historically-named designs are findable
// by something other than their terse name (the old pre-regroup names live
// here too, since names changed in the family reorg).
const SEARCH_KEYWORDS: Record<string, string> = {
  "broadband.g5rv": "doublet ladder line multiband all band",
  "broadband.t2fd": "terminated tilted folded dipole all band",
  "broadband.lpda": "log periodic dipole array beam",
  "broadband.discone": "vhf uhf scanner wideband",
  "wire.zepp": "end fed zeppelin",
  "wire.rhombic": "traveling wave terminated",
  "wire.vbeam": "v beam traveling wave",
  "wire.lazy_h": "lazy-h collinear",
  "verticals.jpole": "j-pole slim jim",
  "verticals.bobtail": "bobtail curtain",
  "beams.yagi": "yagi-uda beam directional",
  "beams.moxon": "moxon rectangle beam",
  "loops.quad": "cubical quad loop",
};

const familyOf = (name: string): string => name.split(".")[0];

function familyRank(fam: string): number {
  const i = (FAMILY_ORDER as readonly string[]).indexOf(fam);
  return i === -1 ? FAMILY_ORDER.length : i;
}

function matchesQuery(ex: ExampleDescriptor, q: string): boolean {
  if (!q) return true;
  const hay = `${ex.name} ${ex.label} ${familyOf(ex.name)} ${
    SEARCH_KEYWORDS[ex.name] ?? ""
  }`.toLowerCase();
  return hay.includes(q);
}

function applyVisibility(spec: SchemaParamSpec, values: ParamValueBag): boolean {
  const v = spec.visible_when;
  if (!v) return true;
  const cur = values[v.name];
  if (cur == null) return true;
  // Visibility comparisons only make sense for numeric controls today
  // (e.g. yagi's `n_directors > 0`). Enum-valued conditions would need
  // a different comparator — flag in v1 but punt on implementation.
  if (typeof cur !== "number") return true;
  switch (v.op) {
    case "eq": return cur === v.value;
    case "ne": return cur !== v.value;
    case "gt": return cur > v.value;
    case "ge": return cur >= v.value;
    case "lt": return cur < v.value;
    case "le": return cur <= v.value;
    default: return true;
  }
}

// Seed defaults for one ParamValueBag from a flat list of schema items.
// `overrides` (optional) overlays per-instance defaults from a group's
// default_overrides[i] entry — used when seeding a group instance.
function seedDefaults(
  schema: SchemaItem[],
  overrides?: { [k: string]: unknown },
): ParamValueBag {
  const out: ParamValueBag = {};
  for (const item of schema) {
    if (isGroup(item)) {
      const arr: ParamValueBag[] = [];
      for (let i = 0; i < item.max_repeats; i++) {
        arr.push(seedDefaults(item.params, item.default_overrides[i]));
      }
      out[item.name] = arr;
    } else {
      const ov = overrides?.[item.name];
      if (ov !== undefined) {
        out[item.name] = ov as number | string | boolean;
      } else if (item.kind === "enum") {
        out[item.name] = String(item.default);
      } else if (item.kind === "bool") {
        out[item.name] = Boolean(item.default);
      } else {
        out[item.name] = Number(item.default);
      }
    }
  }
  return out;
}

// Walk the schema collecting (param, value) pairs for every leaf marked
// `linked_to_design_freq`. Fan_dipole's first band's freq is the
// canonical example: when it changes, the global design frequency
// should follow.
// The design-switch band snap, as a pure function of the example descriptor:
// the band containing the design's native freq (else the first band — which
// the adapter's synthetic-band rule keeps from being a wrong-by-decades 160 m
// fallback, issue #390) and the frequency to park designFreq on. Shared by
// the snap effect on currentExample AND the antenna-switch preview fetch,
// which fires in the same commit and would otherwise race the snapped state
// by one render, fetching its preview with the PREVIOUS design's freqs.
function snapForExample(
  ex: ExampleDescriptor | undefined,
): { bandKey: string; freq: number } | null {
  if (!ex || ex.bands.length === 0) return null;
  const d = ex.default_freq_mhz;
  const containing =
    d != null ? ex.bands.find((b) => d >= b.min_mhz && d <= b.max_mhz) : null;
  const target = containing ?? ex.bands[0];
  // Use the design's native freq when the band contains it; otherwise the
  // band's own default. This avoids the small designFreq drift that would
  // happen if we always snapped to band.freq_mhz (e.g. dipole's 28.57 →
  // 10m band's 28.470).
  return {
    bandKey: target.key,
    freq: containing && d != null ? d : target.freq_mhz,
  };
}

function findLinkedDesignFreq(
  schema: SchemaItem[],
  values: ParamValueBag,
): number | null {
  for (const item of schema) {
    if (isGroup(item)) {
      const instances = values[item.name];
      if (!Array.isArray(instances) || instances.length === 0) continue;
      // Only the first instance's linked param drives design freq.
      // Extending to "any instance" needs a tie-break policy; not
      // worth designing until a second antenna asks for it.
      const found = findLinkedDesignFreq(item.params, instances[0]);
      if (found != null) return found;
    } else if (item.linked_to_design_freq) {
      const v = values[item.name];
      if (typeof v === "number") return v;
    }
  }
  return null;
}

// Blend two #rrggbb colors; t=0 -> a, t=1 -> b. Used to warm the knob's value
// arc from --accent toward --hot as it nears max (an "energizing" cue).
function mixHex(a: string, b: string, t: number): string {
  const ch = (s: string, i: number) => parseInt(s.slice(i, i + 2), 16);
  const r = Math.round(ch(a, 1) + (ch(b, 1) - ch(a, 1)) * t);
  const g = Math.round(ch(a, 3) + (ch(b, 3) - ch(a, 3)) * t);
  const bl = Math.round(ch(a, 5) + (ch(b, 5) - ch(a, 5)) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

// A dependency-free rotary knob — a drop-in alternative to the range
// slider for float/int params. Semantically a slider (role="slider"), so
// it stays keyboard- and screen-reader-accessible: vertical drag, scroll
// wheel, and arrow keys all adjust the value; double-click (or Enter) to
// type an exact number. The dial sweeps ~270° from min (lower-left) to
// max (lower-right). Absolute-angle dragging is deliberately avoided —
// drag is a *relative* vertical delta, which is far easier to do
// precisely than chasing the pointer around a circle.
function Knob({
  knobId,
  value,
  min,
  max,
  step,
  precision,
  unit,
  label,
  onChange,
  startDeg = -135,
  sweepDeg = 270,
  variant = "param",
  disabled = false,
}: {
  // Stable id, emitted as data-knob-id for testing/debugging.
  knobId: string;
  value: number;
  min: number;
  max: number;
  step: number;
  precision: number;
  unit: string | null;
  label: string;
  onChange: (v: number) => void;
  // Dial geometry in clock-angle degrees (0 = 12 o'clock, +CW). The default is
  // the classic 270° gauge sweeping clockwise from 7:30 (lower-left) to 4:30.
  // Pass startDeg=90, sweepDeg=-(max-min) for a CCW dial starting at 3 o'clock
  // (elevation: -90 quarter-arc; azimuth: -360 full circle) — degrees then map
  // 1:1 onto the dial face.
  startDeg?: number;
  sweepDeg?: number;
  // "vfo" = the big weighted measurement-freq tuning dial: knurled skirt +
  // finger dimple on an eased rotor, outer band arc that warms toward the edge.
  // "param" = the compact setup/cut dials (clean accent, no warming).
  variant?: "param" | "vfo";
  // Locked (e.g. measurement freq while "lock to design freq" is on): dims the
  // dial and ignores drag/wheel/keys.
  disabled?: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ y: number; v: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const isVfo = variant === "vfo";
  const span = max - min || 1;
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  // Clamp + round to the param's precision so we emit clean values (2.46, not
  // 2.4600000001) and don't spam the live solve with fp noise. No grid snap —
  // used where the exact value matters (Home/End reaching min/max).
  const roundP = (v: number) => {
    const p = precision >= 0 ? precision : 6;
    return clamp(Number(v.toFixed(p)));
  };
  // Snap to the nearest multiple of `step` — a clean grid anchored at 0, not at
  // `min`. Anchoring at min offset the whole grid by min's fractional part, so
  // nudging an off-grid value kept that offset (1.03 + 0.2 -> 1.23). Anchored at
  // 0 it lands on a round increment (1.03 + 0.2 -> 1.2). min/max are bounds, not
  // the grid origin; they stay reachable exactly via roundP (Home/End).
  const snap = (v: number) => {
    if (step > 0) v = Math.round(v / step) * step;
    return roundP(v);
  };

  const frac = Math.min(1, Math.max(0, (value - min) / span));
  const ang = startDeg + frac * sweepDeg;
  const Rarc = isVfo ? 42 : 38;
  const polar = (deg: number, r: number): [number, number] => {
    const a = (deg * Math.PI) / 180;
    return [50 + r * Math.sin(a), 50 - r * Math.cos(a)];
  };
  const arc = (r: number, a0: number, a1: number): string => {
    const [x0, y0] = polar(a0, r);
    const [x1, y1] = polar(a1, r);
    const delta = a1 - a0;
    const large = Math.abs(delta) > 180 ? 1 : 0;
    // Sweep-flag follows the traversal direction: clockwise (SVG +angle) for an
    // increasing clock-angle, counter-clockwise for a decreasing one. Lets a
    // negative sweepDeg (CCW dials: elevation, azimuth) bend the correct way.
    const sweep = delta >= 0 ? 1 : 0;
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} ${sweep} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  };
  // Param-knob indicator notch across the cap face (center-out), at value.
  const [nx0, ny0] = polar(ang, 3);
  const [nx1, ny1] = polar(ang, 14);
  // Only the VFO's band arc warms --accent -> --hot over the top ~40% of travel
  // ("redlining" near the band edge). Small knobs stay a clean accent.
  const warm = Math.max(0, (frac - 0.6) / 0.4);
  const fillColor = isVfo ? mixHex("#2f5fb0", "#cf7a22", warm) : undefined;

  // Scroll wheel: ±step per detent (×10 with Shift). Attached natively so
  // we can preventDefault — React's onWheel is passive and can't stop the
  // page from scrolling under the dial.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (disabled) return;
      e.preventDefault();
      const dir = e.deltaY < 0 ? 1 : -1;
      const mult = e.shiftKey ? 10 : 1;
      let v = value + dir * step * mult;
      // Snap to the step grid anchored at 0 (clean multiples), matching snap().
      if (step > 0) v = Math.round(v / step) * step;
      const p = precision >= 0 ? precision : 6;
      onChange(Math.min(max, Math.max(min, Number(v.toFixed(p)))));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [value, step, min, max, precision, onChange, disabled]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (editing || disabled) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = { y: e.clientY, v: value };
    setDragging(true);
    wrapRef.current?.focus();
    e.preventDefault();
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dy = d.y - e.clientY; // drag up = increase
    const sens = e.shiftKey ? 0.25 : 1; // hold Shift for fine control
    onChange(snap(d.v + (dy / 180) * span * sens)); // ~180px = full sweep
  };
  const endDrag = (e: React.PointerEvent) => {
    dragRef.current = null;
    setDragging(false);
    (e.target as Element).releasePointerCapture?.(e.pointerId);
  };

  // Apply a single nav/edit key to this knob. Shared by the local onKeyDown
  // (when the knob is focused) and the global sticky-selection router (when it
  // isn't). Returns true when the key was consumed, so callers can
  // preventDefault only for keys we actually handled.
  const applyKey = (key: string): boolean => {
    if (disabled) return false;
    if (key === "Enter") {
      setEditing(true);
      return true;
    }
    let next: number | null = null;
    switch (key) {
      case "ArrowUp":
      case "ArrowRight":
        next = value + step;
        break;
      case "ArrowDown":
      case "ArrowLeft":
        next = value - step;
        break;
      case "PageUp":
        next = value + step * 10;
        break;
      case "PageDown":
        next = value - step * 10;
        break;
      case "Home":
        // Jump to exactly min/max — these are bounds, not grid points, so skip
        // the step snap (roundP clamps + rounds to precision only).
        onChange(roundP(min));
        return true;
      case "End":
        onChange(roundP(max));
        return true;
      default:
        return false;
    }
    onChange(snap(next));
    return true;
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (applyKey(e.key)) e.preventDefault();
  };

  const commit = (raw: string) => {
    const n = Number(raw);
    if (Number.isFinite(n)) onChange(snap(n));
    setEditing(false);
  };

  const p = Math.max(0, precision);
  return (
    <div
      className={`knob${isVfo ? " is-vfo" : ""}${disabled ? " is-disabled" : ""}`}
      data-knob-id={knobId}
      ref={wrapRef}
      role="slider"
      tabIndex={editing || disabled ? -1 : 0}
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={`${value.toFixed(p)}${unit ?? ""}`}
      aria-disabled={disabled || undefined}
      onKeyDown={onKeyDown}
    >
      {editing ? (
        <input
          className="knob-edit"
          type="number"
          autoFocus
          defaultValue={value}
          min={min}
          max={max}
          step={step}
          onBlur={(e) => commit((e.target as HTMLInputElement).value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit((e.target as HTMLInputElement).value);
            else if (e.key === "Escape") setEditing(false);
            e.stopPropagation();
          }}
        />
      ) : (
        <svg
          // The VFO's 270° gauge opens at the bottom (~6 o'clock) and its
          // content stops by y≈82, so crop the empty bottom off the box rather
          // than reserve a full square. NOT for the others: the azimuth dial is
          // a full circle that uses the bottom.
          viewBox={isVfo ? "0 0 100 88" : "0 0 100 100"}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onDoubleClick={() => setEditing(true)}
        >
          <path
            className="knob-track"
            d={arc(Rarc, startDeg, startDeg + sweepDeg)}
          />
          <path
            className="knob-fill"
            style={fillColor ? { stroke: fillColor } : undefined}
            d={arc(Rarc, startDeg, ang)}
          />
          {/* Focus ring drawn in SVG space so it's a true circle centered on the
              dial (50,50) — the wrapper's box-shadow ring would be an ellipse on
              the VFO's non-square 112×99 box. Just outside the gauge arc (Rarc).
              Shown on keyboard focus via .vfo-focus-ring CSS. */}
          {isVfo && <circle className="vfo-focus-ring" cx="50" cy="50" r="50.5" />}
          {isVfo ? (
            // The whole knob body spins; the band arc behind it stays put — a
            // fixed scale with a turning dial, exactly like a transceiver VFO.
            <g
              className={`knob-rotor${dragging ? " no-ease" : ""}`}
              style={{ transform: `rotate(${ang.toFixed(2)}deg)` }}
            >
              <circle className="knob-cap" cx="50" cy="50" r="30" />
              {Array.from({ length: 30 }, (_, i) => {
                const a = (i * 360) / 30;
                const [sx0, sy0] = polar(a, 27.5);
                const [sx1, sy1] = polar(a, 32);
                return (
                  <line
                    key={i}
                    className="knob-skirt"
                    x1={sx0.toFixed(2)}
                    y1={sy0.toFixed(2)}
                    x2={sx1.toFixed(2)}
                    y2={sy1.toFixed(2)}
                  />
                );
              })}
              <line className="knob-notch" x1="50" y1="39" x2="50" y2="24" />
              <circle className="knob-dimple" cx="50" cy="30" r="3.4" />
            </g>
          ) : (
            <>
              <circle className="knob-cap" cx="50" cy="50" r="15" />
              <line
                className="knob-notch"
                x1={nx0.toFixed(2)}
                y1={ny0.toFixed(2)}
                x2={nx1.toFixed(2)}
                y2={ny1.toFixed(2)}
              />
            </>
          )}
        </svg>
      )}
    </div>
  );
}

// Designs that loaded clean but haven't been trusted to run yet. A user design
// is a Python program that runs with your privileges, so it executes only once
// you trust it (see design_trust.py). This panel is collapsed to one line by
// default — click a design to see what it does (the screener advisory) and to
// trust it. Enforcement happens at scan time (untrusted files are never
// executed); this is just where you make the decision, per design.
function AwaitingTrustPanel({
  designs,
  busy,
  onTrust,
}: {
  designs: DesignLoadError[];
  busy: string | null;
  onTrust: (stem: string, allowEdits: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [openName, setOpenName] = useState<string | null>(null);
  const n = designs.length;
  return (
    <div className="design-trust-panel">
      <button
        className="design-trust-summary"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="design-trust-lock" aria-hidden="true">
          🔒
        </span>
        {n} design{n === 1 ? " needs" : "s need"} your OK to run
        <span className="design-trust-caret" aria-hidden="true">
          {expanded ? "▾" : "▸"}
        </span>
      </button>
      {expanded && (
        <ul className="design-trust-list">
          {designs.map((d) => {
            const open = openName === d.name;
            const isBusy = busy === d.name;
            return (
              <li key={d.name} className="design-trust-item">
                <button
                  className="design-trust-item-head"
                  aria-expanded={open}
                  onClick={() => setOpenName(open ? null : d.name)}
                >
                  <code>{d.name}</code>
                  <span className="design-trust-caret" aria-hidden="true">
                    {open ? "▾" : "▸"}
                  </span>
                </button>
                {open && (
                  <div className="design-trust-detail">
                    {d.advisory && d.advisory.length > 0 ? (
                      <>
                        <div className="design-trust-advisory-head">
                          Heads up — this design does things a normal antenna
                          design doesn&apos;t. Look before you let it run:
                        </div>
                        <ul className="design-trust-advisory">
                          {d.advisory.map((a, i) => (
                            <li key={i} className={`sev-${a.severity}`}>
                              line {a.line}: {a.message}
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : (
                      <div className="design-trust-advisory-head">
                        Nothing unusual — it only builds antenna geometry.
                      </div>
                    )}
                    <div className="design-trust-actions">
                      <button
                        className="design-trust-btn"
                        disabled={isBusy}
                        onClick={() => onTrust(d.name, false)}
                      >
                        Allow it to run
                      </button>
                      <button
                        className="design-trust-btn is-edits"
                        disabled={isBusy}
                        onClick={() => onTrust(d.name, true)}
                        title="For a design you're writing yourself — won't ask again when you save changes"
                      >
                        Allow + my edits
                      </button>
                    </div>
                    <div className="design-trust-note">
                      A design is a small program that runs on your computer.
                      Only allow ones from people you trust.
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// Searchable antenna picker: merges the old filter box + grouped <select> into
// one combobox (type to filter, ▾ to open) so it fits on one line beside the
// variant select. Keeps the family grouping the native <optgroup> list had.
function GeometryCombobox({
  groups,
  selected,
  currentLabel,
  filter,
  setFilter,
  onSelect,
}: {
  groups: { fam: string; label: string; items: ExampleDescriptor[] }[];
  selected: string;
  currentLabel: string;
  filter: string;
  setFilter: (s: string) => void;
  onSelect: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const flat = groups.flatMap((g) => g.items);

  // Close (and clear the filter) on an outside click.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setFilter("");
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open, setFilter]);

  const choose = (name: string) => {
    onSelect(name);
    setFilter("");
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(flat.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      if (open && flat[active]) {
        e.preventDefault();
        choose(flat[active].name);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setFilter("");
      inputRef.current?.blur();
    }
  };

  return (
    <div className="combobox" ref={rootRef}>
      <input
        ref={inputRef}
        className="geometry-filter combobox-input"
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-label="antenna"
        placeholder="search antennas…"
        value={open ? filter : currentLabel}
        onChange={(e) => {
          setFilter(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      <span
        className="combobox-caret"
        aria-hidden="true"
        onMouseDown={(e) => {
          e.preventDefault();
          if (open) {
            setOpen(false);
          } else {
            inputRef.current?.focus();
            setOpen(true);
          }
        }}
      >
        ▾
      </span>
      {open && (
        <ul className="combobox-list" role="listbox">
          {flat.length === 0 ? (
            <li className="combobox-empty">no antennas match</li>
          ) : (
            groups.map((g) => (
              <li key={g.fam} className="combobox-group">
                <div className="combobox-group-label">{g.label}</div>
                <ul>
                  {g.items.map((ex) => {
                    const idx = flat.indexOf(ex);
                    return (
                      <li
                        key={ex.name}
                        role="option"
                        aria-selected={ex.name === selected}
                        className={`combobox-option${
                          ex.name === selected ? " is-selected" : ""
                        }${idx === active ? " is-active" : ""}`}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          choose(ex.name);
                        }}
                        onMouseEnter={() => setActive(idx)}
                      >
                        {ex.label}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

// Band picker — a click-only dropdown, deliberately NOT a native <select>.
// A focused <select> captures the arrow keys, which would fight the sticky
// meas-freq dial (the "physical dial survives focus loss" affordance): the dial
// shows armed but arrows would drive the pulldown. This is a plain <button> +
// popover, so it never captures arrows — they always flow to the armed knob.
function BandDropdown({
  bands,
  value,
  onSelect,
  disabled,
  ariaLabel,
}: {
  bands: BandSpec[];
  value: string;
  onSelect: (key: string) => void;
  disabled?: boolean;
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const current = bands.find((b) => b.key === value) ?? bands[0];

  return (
    <div className="band-dropdown" ref={rootRef}>
      <button
        type="button"
        className="band-select band-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="band-dropdown-value">{current?.label ?? ""}</span>
        <span className="band-dropdown-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && !disabled && (
        <ul className="band-dropdown-list" role="listbox" aria-label={ariaLabel}>
          {bands.map((b) => (
            <li
              key={b.key}
              role="option"
              aria-selected={b.key === value}
              className={`band-dropdown-option${
                b.key === value ? " is-selected" : ""
              }`}
              onMouseDown={(e) => {
                e.preventDefault();
                onSelect(b.key);
                setOpen(false);
              }}
            >
              {b.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Translate a knob's optional layout hint into inline grid-placement
// styles. Returns undefined when nothing is set so auto-flow fields stay
// untouched. `col_span` / `row_span` use the CSS `span N` form; an explicit
// `col` / `row` pins the start line (1-indexed). `col` + `col_span`
// together place a spanning field at a fixed column.
function layoutStyle(layout?: KnobLayout | null): CSSProperties | undefined {
  if (!layout) return undefined;
  const style: CSSProperties = {};
  const colStart = layout.col ?? null;
  const rowStart = layout.row ?? null;
  const colSpan = layout.col_span ?? null;
  const rowSpan = layout.row_span ?? null;
  if (colStart != null) {
    style.gridColumn = colSpan != null ? `${colStart} / span ${colSpan}` : `${colStart}`;
  } else if (colSpan != null) {
    style.gridColumn = `span ${colSpan}`;
  }
  if (rowStart != null) {
    style.gridRow = rowSpan != null ? `${rowStart} / span ${rowSpan}` : `${rowStart}`;
  } else if (rowSpan != null) {
    style.gridRow = `span ${rowSpan}`;
  }
  return Object.keys(style).length ? style : undefined;
}

function ParamForm({
  schema,
  values,
  onChange,
  pathPrefix = [],
  disabledFields,
  opt,
}: {
  schema: SchemaItem[];
  values: ParamValueBag;
  onChange: (path: (string | number)[], value: number | string | boolean) => void;
  pathPrefix?: (string | number)[];
  // Param names that should render as disabled even though they're
  // visible in the schema. Used to grey out controls whose effect
  // depends on the active backend (e.g. daisy_chain only works on
  // PyNEC; momwire engines don't support transmission lines yet).
  disabledFields?: Set<string>;
  // Optimiser integration (top-level rail only). `settings` overrides a knob's
  // effective min/max/step; `onContext` opens that knob's right-click menu;
  // `onToggleVary` flips a knob's "Optimize this knob" flag (the `o` shortcut,
  // parallel to the menu checkbox).
  opt?: {
    settings: Record<string, KnobOpt>;
    onContext: (name: string, e: React.MouseEvent) => void;
    onToggleVary: (name: string) => void;
  };
}) {
  return (
    <>
      {schema.map((item) => {
        if (isGroup(item)) {
          const countRaw = values[item.repeat_count];
          const count = typeof countRaw === "number" ? Math.round(countRaw) : 0;
          const instances = values[item.name];
          if (!Array.isArray(instances)) return null;
          return (
            <div key={item.name} className="param-group">
              {Array.from({ length: Math.min(count, instances.length) }, (_, i) => (
                <div key={`${item.name}-${i}`} className="param-group-instance">
                  <div className="param-group-header">
                    {item.label_template.replace("{i}", String(i))}
                  </div>
                  {/* Wrap the band's controls in their own .param-grid so they
                      pack 3-across just like the top-level rail. Without this
                      the nested ParamForm block-stacks one control per row. */}
                  <div className="param-grid is-knobs">
                    <ParamForm
                      schema={item.params}
                      values={instances[i]}
                      onChange={onChange}
                      pathPrefix={[...pathPrefix, item.name, i]}
                      disabledFields={disabledFields}
                    />
                  </div>
                </div>
              ))}
            </div>
          );
        }
        // Scalar leaf.
        if (!applyVisibility(item, values)) return null;
        const currentRaw = values[item.name];
        const currentNum =
          typeof currentRaw === "number" ? currentRaw : Number(item.default);
        const currentStr =
          typeof currentRaw === "string" ? currentRaw : String(item.default);

        // Resolve dynamic min/max from a sibling enum's currently-
        // selected option, when configured. Falls back to the static
        // min/max if the lookup misses.
        let effMin = item.min ?? 0;
        let effMax = item.max ?? 1;
        const rfe = item.range_from_enum_option;
        if (rfe) {
          const siblingVal = values[rfe.param];
          const siblingSchema = schema.find(
            (s) => !isGroup(s) && s.name === rfe.param,
          ) as SchemaParamSpec | undefined;
          const opts = siblingSchema?.enum_options;
          if (opts && typeof siblingVal === "string") {
            const opt = opts.find((o) => o.value === siblingVal);
            if (opt) {
              const lo = opt[rfe.min_key];
              const hi = opt[rfe.max_key];
              if (typeof lo === "number") effMin = lo;
              if (typeof hi === "number") effMax = hi;
            }
          }
        }

        if (item.kind === "bool") {
          const checked = Boolean(currentRaw ?? item.default);
          const isDisabled = disabledFields?.has(item.name) ?? false;
          return (
            <div key={item.name} className="field field-bool" style={layoutStyle(item.layout)}>
              <label
                className={`field-bool-label${isDisabled ? " field-disabled" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={isDisabled}
                  onChange={(e) =>
                    onChange(
                      [...pathPrefix, item.name],
                      (e.target as HTMLInputElement).checked,
                    )
                  }
                />
                <span>{item.label}</span>
              </label>
            </div>
          );
        }

        if (item.kind === "enum") {
          const opts = item.enum_options ?? [];
          return (
            <div key={item.name} className="field field-enum" style={layoutStyle(item.layout)}>
              <label>
                <span>{item.label}</span>
              </label>
              <select
                value={currentStr}
                onChange={(e) => {
                  const next = (e.target as HTMLSelectElement).value;
                  onChange([...pathPrefix, item.name], next);
                  // On-change side effect: set a sibling's value to a
                  // key from the new enum option. Fan_dipole uses this
                  // to snap freq to the band's default.
                  const oc = item.on_change_set;
                  if (oc) {
                    const opt = opts.find((o) => o.value === next);
                    if (opt) {
                      const k = opt[oc.from_enum_key];
                      if (typeof k === "number" || typeof k === "string") {
                        onChange([...pathPrefix, oc.set], k);
                      }
                    }
                  }
                }}
              >
                {opts.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          );
        }

        const shown =
          item.kind === "int"
            ? String(Math.round(currentNum))
            : currentNum.toFixed(item.precision);
        // Every float/int param is a rotary knob: label on top, dial in the
        // middle, value on the bottom. (The slider alternative and its toggle
        // were retired — knobs are the brand.)
        // Per-knob optimiser override: display extents + manual step come from
        // the knob's menu when set, and `vary` marks it a free variable.
        const ko = opt?.settings[item.name];
        const knobMin = ko ? ko.dispMin : effMin;
        const knobMax = ko ? ko.dispMax : effMax;
        const knobStep = ko?.step ?? item.step ?? 0.001;
        return (
          <div
            key={item.name}
            className={`field field-knob${ko?.vary ? " is-opt-var" : ""}`}
            style={layoutStyle(item.layout)}
            onContextMenu={opt ? (e) => opt.onContext(item.name, e) : undefined}
            // `o` toggles this knob's "Optimize this knob" flag while it's
            // focused — the keyboard parallel to the right-click menu. The event
            // bubbles up from the focused role="slider" Knob; the edit <input>
            // stops propagation, so typing a value never triggers it. Ignore it
            // when a modifier is held (reserved for other shortcuts) or on
            // auto-repeat (holding the key mustn't flip-flop the flag).
            onKeyDown={
              opt
                ? (e) => {
                    if (
                      e.key.toLowerCase() === "o" &&
                      !e.ctrlKey &&
                      !e.metaKey &&
                      !e.altKey &&
                      !e.repeat
                    ) {
                      e.preventDefault();
                      opt.onToggleVary(item.name);
                    }
                  }
                : undefined
            }
          >
            <span
              className="knob-label"
              title={item.name === item.label ? item.label : `${item.label} · param: ${item.name}`}
            >
              {item.label}
            </span>
            <Knob
              knobId={[...pathPrefix, item.name].join(".")}
              value={currentNum}
              min={knobMin}
              max={knobMax}
              step={knobStep}
              precision={item.kind === "int" ? 0 : item.precision}
              unit={item.unit}
              label={item.label}
              onChange={(v) => onChange([...pathPrefix, item.name], v)}
            />
            <span className="knob-value">{shown}{item.unit ?? ""}</span>
          </div>
        );
      })}
    </>
  );
}

function formatScalar(raw: unknown, precision: number, unit: string | null): string {
  return typeof raw === "number" ? `${raw.toFixed(precision)}${unit ?? ""}` : "—";
}

// label_template substitutions for ResultGroupItem:
//   {i}            → 0-based index
//   {i1}           → 1-based index
//   {name:.Nf}     → result[name][i] formatted as a fixed-N-decimal float
function renderGroupLabel(template: string, i: number, result: Record<string, unknown> | null): string {
  let out = template.replace(/\{i1\}/g, String(i + 1)).replace(/\{i\}/g, String(i));
  out = out.replace(/\{(\w+):\.(\d+)f\}/g, (_, name: string, decimals: string) => {
    const arr = result?.[name];
    if (!Array.isArray(arr)) return "—";
    const v = arr[i];
    return typeof v === "number" ? v.toFixed(Number(decimals)) : "—";
  });
  return out;
}

function ResultPanel({
  schema,
  result,
}: {
  schema: ResultSchemaItem[];
  result: Record<string, unknown> | null;
}) {
  // Render one row per schema entry. Scalar items read the field off the
  // response by name; group items repeat over the first inner field's
  // top-level array. Missing/non-numeric values render as an em-dash so
  // the row layout doesn't collapse mid-update.
  return (
    <>
      {schema.map((item) => {
        if ("kind" in item && item.kind === "group") {
          const repeatField = item.fields[0]?.field;
          const arr = repeatField ? result?.[repeatField] : undefined;
          if (!Array.isArray(arr)) return null;
          return (
            <Fragment key={`result-group-${item.name}`}>
              {arr.map((_, i) => (
                <div className="row" key={`result-group-${item.name}-${i}`}>
                  <span>{renderGroupLabel(item.label_template, i, result)}</span>
                  <span className="val">
                    {item.fields.map((f, fi) => {
                      const sub = result?.[f.field];
                      const v = Array.isArray(sub) ? sub[i] : undefined;
                      return (
                        <span key={`${item.name}-${i}-${fi}`}>
                          {formatScalar(v, f.precision, f.unit)}
                        </span>
                      );
                    })}
                  </span>
                </div>
              ))}
            </Fragment>
          );
        }
        const s = item as ResultFieldSpec;
        return (
          <div className="row" key={`result-${s.field}`}>
            <span>{s.label}</span>
            <span className="val">{formatScalar(result?.[s.field], s.precision, s.unit)}</span>
          </div>
        );
      })}
    </>
  );
}

type FeedEntry = {
  wire_index: number;
  knot_index: number;
  /** Exact 3D feed point; preferred over the knot lookup for the marker dot. */
  feed_position?: [number, number, number];
  z_re: number;
  z_im: number;
  v_re: number;
  v_im: number;
};

type SolveResponse = {
  geometry: string;
  wires: Wire[];
  feed_wire_index: number;
  feed_knot_index: number;
  /** Exact 3D feed point for the primary feed; the marker dot uses this so
   *  it stays on the true feed regardless of solver-basis parity. */
  feed_position?: [number, number, number];
  z_in_re: number;
  z_in_im: number;
  /** Multi-feed geometries (bowtie 1×2 array) populate this; single-feed
   *  geometries omit it. Primary feed is feeds[0] when present. */
  feeds?: FeedEntry[];
  design_freq_mhz: number;
  measurement_freq_mhz: number;
  lambda_design_m: number;
  solve_ms: number;
  /** Echoed from the request. The latest-wins /ws protocol orders and prunes
   *  responses by this; a higher `_seq` implicitly acks every lower one.
   *  Absent from geometry-preview payloads (they never carry a request seq). */
  _seq?: number;
  directivity_norm?: number;
  ground?: boolean;
  height_m?: number;
  ground_eps_r?: number;
  ground_sigma?: number;
  ground_eps_im?: number;
  /** What the impedance solve actually used. Momwire: "refl-coef" |
   *  "pec-image" | "free"; PyNEC adds "sommerfeld". Authoritative — the
   *  readout's ground row shows this rather than re-deriving it from
   *  backend + groundType state. */
  ground_model_applied?: string;
  /** Per-branch network dissipation from the MNA solve (issue #299):
   *  one entry per TL / TwoPort / Shunt / Load branch, in watts for the
   *  canonical 1 V drive. Absent or all-~0 for plain and lossless
   *  designs; input_power_w is the 100% reference. */
  power_budget?: { label: string; watts: number }[];
  input_power_w?: number;
  k_meas_m_inv?: number;
  // V-specific
  arm_len_m?: number;
  // Yagi-specific
  driver_length_m?: number;
  reflector_length_m?: number;
  spacing_m?: number;
  // Moxon-specific
  long_m?: number;
  short_m?: number;
  tipspacer_m?: number;
  t0_m?: number;
  halfdriver_m?: number;
  // Hexbeam-specific
  radius_m?: number;
  t1_m?: number;
  // Fan dipole-specific
  n_bands?: number;
  band_lengths_m?: number[];
  band_freqs_mhz?: number[];
  slope?: number;
  cone_radius_m?: number;
  // Hentenna-specific
  half_width_m?: number;
  top_height_m?: number;
  mid_offset_m?: number;
  // Bowtie-1×2-array-specific
  y_m?: number;
  z_m?: number;
  length_m?: number;
  del_y_m?: number;
  phase_lr_deg?: number;
  /** Per-geometry SWR / Smith chart reference impedance. Falls back to
   *  50 Ω when the server doesn't supply one. Bowtie array returns 100 Ω
   *  because each element is designed for a 100 Ω feedline. */
  z0_ohms?: number;
  /** Geometry-derived UI hints folded into the solve/geometry response.
   *  User designs defer these (the builder runs lazily on selection), so the
   *  authoritative values arrive here rather than on the /examples descriptor;
   *  prefer them over the example fields when present. */
  multi_feed?: boolean;
  default_view?: Projection;
  /** Recommended solver backend for this design (e.g. "arrayblock" for grid
   *  arrays). Carried on the geometry preview so the frontend can seed the
   *  backend from it and *then* fire the first solve, instead of the descriptor
   *  racing the preview. Absent / null = no recommendation. Plain string —
   *  may name a retired backend; normalizeBackend before use. */
  default_backend?: string | null;
  /** Set when the solve/geometry request failed — e.g. a user design's
   *  build_wires() raised. Carries a short, formatted message (type + file +
   *  line). Mutually exclusive with a normal result payload. */
  error?: string;
};

// Backend selector — Momwire model variants + PyNEC. Per-backend
// `model_options` are forwarded to server.py's _make_momwire_sim.
// "triangular" is retired from the UI (the server still accepts it);
// see normalizeBackend for how a stale recommendation is mapped.
type Backend =
  | "sinusoidal"
  | "bspline"
  | "hmatrix"
  | "arrayblock"
  | "pynec";

const BACKEND_LABEL: Record<Backend, string> = {
  sinusoidal: "Sinusoidal",
  bspline: "B-spline",
  hmatrix: "H-matrix (ACA)",
  arrayblock: "Array-block",
  pynec: "PyNEC",
};

// A design/solver combo is "inappropriate" when the solver is a poor fit: a
// dense solver (or PyNEC) on a large array is very slow, an accelerator
// (array-block / H-matrix) on a single-element design is pure overhead, and
// on a benchmark-class mesh (thousands of segments) every b-spline-family
// solver is minutes per solve where sinusoidal (or PyNEC) is seconds. `rec`
// is the server's recommended backend ("arrayblock" for grid arrays,
// "sinusoidal" for huge meshes, else null).
function comboInappropriate(b: Backend, rec: Backend | null): boolean {
  const accel = b === "arrayblock" || b === "hmatrix";
  if (rec === "arrayblock") return !accel; // an array wants an accelerator
  if (rec === "sinusoidal") return b !== "sinusoidal" && b !== "pynec";
  return accel; // everything else doesn't need one
}

const BACKEND_ORDER: Backend[] = [
  "sinusoidal",
  "bspline",
  "hmatrix",
  "arrayblock",
  "pynec",
];

// hmatrix (hierarchical H-matrix / ACA) and arrayblock (element-aware block
// solver for arrays) are accelerators built on the same B-spline basis as
// bspline; they share its options and request shape, and fall back to the
// dense bspline path for ground/enrichment.
const BSPLINE_FAMILY: Backend[] = ["bspline", "hmatrix", "arrayblock"];
function isBSplineFamily(b: Backend): boolean {
  return BSPLINE_FAMILY.includes(b);
}

// The UI separates WHAT the ground is from HOW it's solved. GroundType is
// the shared, backend-agnostic choice: a finite ground (εr=10, σ=0.002) or
// a perfectly conducting one. It never promises more than the physics —
// each backend solves it as best it can: PyNEC and the plain B-spline
// backend offer a method sub-choice (Sommerfeld-Norton vs the
// reflection-coefficient approximation) — since momwire 0.8.0 every
// momwire backend honours both, so the choice is uniform across solvers;
// either way the finite constants reach the far-field Fresnel cut.
type GroundType = "finite" | "pec";
// Finite-ground solve method, shown for every finite-ground backend:
// PyNEC (NEC ITYPE=2 vs ITYPE=0) and, since momwire 0.8.0, every momwire
// solver (true Sommerfeld on bspline dense, sinusoidal field-based, and
// the hmatrix/arrayblock fast paths). "fast" is the default everywhere;
// Sommerfeld is opt-in because it is more expensive: the first solve at a
// new frequency fills an interpolation grid (~0.2-0.5 s on a small box;
// the first sweep pays that per point), and repeat solves at seen
// frequencies reuse cached grids (tens of ms).
type FiniteGroundMethod = "sommerfeld" | "fast";
// The wire value (`ground_model` on SolveRequest): derived from groundType
// (+ the method wherever finite ground is supported).
type GroundModel = "sommerfeld" | "fast" | "pec";

function backendSupportsGround(b: Backend): boolean {
  return b === "sinusoidal" || isBSplineFamily(b) || b === "pynec";
}

// Coerce a server-supplied backend name into something this UI knows.
// "triangular" was retired from the frontend (the server still accepts
// it and may still recommend it, e.g. from an older adapter or a saved
// design hint): map it to "bspline", the default working solver on the
// same dense path. Anything else unrecognised falls back to null ("no
// recommendation") so a stale value never reaches state or the wire.
function normalizeBackend(b: string | null | undefined): Backend | null {
  if (!b) return null;
  if (b === "triangular") return "bspline";
  return (BACKEND_ORDER as string[]).includes(b) ? (b as Backend) : null;
}

type CommonOpts = { nPerWire: number; wireRadius: number };

type SinusoidalOpts = CommonOpts & { nQpConst: number };
type BSplineOpts = CommonOpts & {
  degree: 1 | 2;
  nQpPair: number;
  feedSmoothingFactor: number | null; // null = sharp delta-gap
  useSingularEnrichment: boolean;
  // "raw"      → Φ_sing(t) = t·log(t), PR #45/#47 original shape.
  // "stable"   → Φ_sing − bubble-subspace L²-projection: faster large-N
  //              convergence on dominant-pair K=3 junctions; larger
  //              small-N transient; loses Y-fixture cusp benefit. d=1
  //              collapses to raw bit-exact.
  // "tikhonov" → raw basis + λ·s·I penalty on Z_ee at solve time.
  //              λ→0 is raw; λ→∞ kills enrichment. λ=0.1 preserves
  //              Y-fixture cusp; λ=1.0 fully suppresses the small-N
  //              transient on dominant-pair K=3 junctions but loses Y cusp.
  // "auto"     → two-pass: solve once without enrichment, measure
  //              tap_ratio at each K≥3 junction, apply raw enrichment
  //              only where tap_ratio > autoTapRatioThreshold. Cleanly
  //              separates dominant-pair K=3 (tap_ratio ≈ 0.16) from
  //              balanced 3-way (Y ≈ 0.50). The selectivity that
  //              raw/stable/tikhonov can't deliver algebraically.
  enrichmentVariant: "raw" | "stable" | "tikhonov" | "auto";
  tikhonovLambda: number;
  autoTapRatioThreshold: number;
  nQpSing: number;
  enrichmentMinK: number;
  nQpSource: number;
};
type PyNECOpts = CommonOpts;

// hmatrix and arrayblock share BSplineOpts (same basis + knobs); the ACA
// tolerances use the solver defaults.
type BackendOptsMap = {
  sinusoidal: SinusoidalOpts;
  bspline: BSplineOpts;
  hmatrix: BSplineOpts;
  arrayblock: BSplineOpts;
  pynec: PyNECOpts;
};

const BSPLINE_DEFAULT_OPTS: BSplineOpts = {
  nPerWire: 30,
  wireRadius: 0.0005,
  degree: 2,
  nQpPair: 4,
  feedSmoothingFactor: null,
  useSingularEnrichment: false,
  enrichmentVariant: "raw",
  tikhonovLambda: 0.1,
  autoTapRatioThreshold: 0.3,
  nQpSing: 32,
  enrichmentMinK: 3,
  nQpSource: 16,
};

const DEFAULT_BACKEND_OPTS: BackendOptsMap = {
  sinusoidal: { nPerWire: 30, wireRadius: 0.0005, nQpConst: 8 },
  bspline: { ...BSPLINE_DEFAULT_OPTS },
  hmatrix: { ...BSPLINE_DEFAULT_OPTS },
  // Arrays auto-select this; 21 segs/wire is the converged, correct-parity
  // choice for B-spline d=2 (odd → interior knot at the feed). The old
  // inherited 40 was both too many and the wrong (even) parity.
  arrayblock: { ...BSPLINE_DEFAULT_OPTS, nPerWire: 21 },
  pynec: { nPerWire: 21, wireRadius: 0.0005 },
};

// Three abstract solver slots. Each holds one backend choice and its
// options; the user picks A/B/C with the row of buttons, configures the
// inhabitants from the per-slot gear menu. Lets the same UI compare
// e.g. "B-spline d=2 @ N=21" against "B-spline d=1 @ N=40" without
// losing either setup.
type Slot = "A" | "B" | "C";
const SLOT_ORDER: Slot[] = ["A", "B", "C"];

type SlotConfig = {
  backend: Backend;
  opts: BackendOptsMap[Backend];
};

// Display label for a configured backend: B-spline-family entries carry
// their spline degree so two b-spline slots (the default A d=2 / B d=1
// pair) stay distinguishable at a glance.
function backendDisplayLabel(b: Backend, opts: BackendOptsMap[Backend]): string {
  return isBSplineFamily(b)
    ? `${BACKEND_LABEL[b]} d=${(opts as BSplineOpts).degree}`
    : BACKEND_LABEL[b];
}

const DEFAULT_SLOTS: Record<Slot, SlotConfig> = {
  // A is the default working solver: B-spline d=2 — most accurate per
  // unknown, converged at a small odd N (interior knot at the feed), and
  // its impedance solve honours finite grounds (Triangular, the old,
  // now-retired default, folded them to the PEC image).
  A: {
    backend: "bspline",
    opts: { ...DEFAULT_BACKEND_OPTS.bspline, nPerWire: 21 },
  },
  // B is the cross-check basis: B-spline d=1 needs a larger N to reach
  // the same answer (slower), which is what makes agreement with A a
  // meaningful second opinion rather than the same solve twice.
  B: {
    backend: "bspline",
    opts: { ...DEFAULT_BACKEND_OPTS.bspline, degree: 1, nPerWire: 40 },
  },
  C: {
    backend: "pynec",
    opts: { ...DEFAULT_BACKEND_OPTS.pynec },
  },
};

// Translates the camelCase frontend options into the snake_case kwargs the
// server forwards to each Momwire model class constructor.
function modelOptionsForRequest(
  backend: Backend,
  opts: BackendOptsMap[Backend],
): Record<string, unknown> {
  if (backend === "sinusoidal") {
    const o = opts as SinusoidalOpts;
    return { n_qp_const: o.nQpConst };
  }
  if (isBSplineFamily(backend)) {
    // bspline, hmatrix, and arrayblock all take the B-spline kwargs; the
    // accelerators read additional aca_tol/solve_tol from their own defaults.
    const o = opts as BSplineOpts;
    return {
      degree: o.degree,
      n_qp_pair: o.nQpPair,
      n_qp_source: o.nQpSource,
      feed_smoothing_factor: o.feedSmoothingFactor,
      use_singular_enrichment: o.useSingularEnrichment,
      enrichment_variant: o.enrichmentVariant,
      tikhonov_lambda: o.tikhonovLambda,
      auto_tap_ratio_threshold: o.autoTapRatioThreshold,
      n_qp_sing: o.nQpSing,
      enrichment_min_k: o.enrichmentMinK,
    };
  }
  return {};
}

type SolveRequest = {
  geometry: string;
  /** Which `<name>_params` dict on the Builder to seed from. Omitted
   *  → backend falls back to default_params. */
  variant?: string;
  solver: "momwire" | "pynec";
  momwire_model?:
    | "sinusoidal"
    | "bspline"
    | "hmatrix"
    | "arrayblock";
  model_options?: Record<string, unknown>;
  n_per_wire: number;
  design_freq_mhz: number;
  measurement_freq_mhz: number;
  wire_radius: number;
  ground: boolean;
  ground_fast: boolean;
  ground_model?: GroundModel;
  // V
  angle_deg?: number;
  halfdriver_factor?: number;
  // Yagi
  driver_length_factor?: number;
  reflector_length_factor?: number;
  spacing_wavelengths?: number;
  n_directors?: number;
  director_spacing_wavelengths?: number;
  director_size_factor?: number;
  // Moxon (+ hexbeam: hexbeam reuses tipspacer_factor and t0_factor too)
  aspect_ratio?: number;
  tipspacer_factor?: number;
  t0_factor?: number;
  // Fan dipole
  n_bands?: number;
  band_lengths_m?: number[];
  band_freqs_mhz?: number[];
  band_halfdriver_factors?: number[];
  slope?: number;
  cone_radius_m?: number;
  // Hentenna
  width_factor?: number;
  top_height_factor?: number;
  mid_height_factor?: number;
  // Bowtie 1×2 array (slope shared with fan_dipole tip-droop convention)
  length_factor?: number;
  del_y_m?: number;
  phase_lr_deg?: number;
  /** Monotonic per-tab sequence number for the latest-wins /ws protocol. The
   *  server echoes it back and keeps only the freshest queued request. */
  _seq?: number;
  /** Solve-lane session id (issue #382): one per workbench tab, minted at
   *  mount. The server serializes all of a session's solve-producing work
   *  (live solve, sweeps, converge, norm-check, pattern) on one lane. */
  _session?: string;
  /** Batch-request generation: the value of the `_seq` counter when the batch
   *  was issued, so a newer knob drag (higher live `_seq`) supersedes it. */
  _gen?: number;
  /** Set when the user clicked through the poor-match gate ("Solve anyway");
   *  the server refuses warned batches without it. */
  _approved?: boolean;
};

type SweepData = {
  freqs_mhz: number[];
  z_re: number[];
  z_im: number[];
  /** Multi-feed geometries (bowtie 1×2 array) populate these; each row is a
   *  per-feed Z array of length n_feeds. Index alignment with freqs_mhz.
   *  Single-feed geometries omit them and the Smith chart falls back to
   *  the legacy single-trajectory render driven by z_re/z_im. */
  feeds_z_re?: number[][];
  feeds_z_im?: number[][];
};

type ConvergeData = {
  n_values: number[];
  z_re: number[];
  z_im: number[];
  // Richardson extrapolation Z(1/N) → Z(0). Filled once ≥3 points are in.
  z_re_extrap: number | null;
  z_im_extrap: number | null;
  /** Multi-feed convergence — per-N per-feed Z. Outer index aligns with
   *  n_values; inner index aligns with feed order. Single-feed
   *  geometries omit these and the chart falls back to the legacy
   *  single-trail render driven by z_re/z_im. */
  feeds_z_re?: number[][];
  feeds_z_im?: number[][];
  /** Per-feed Richardson Z*. Indexed by feed order, same length as a row
   *  of feeds_z_re. Entries are null until ≥3 sample points are in. */
  feeds_z_re_extrap?: (number | null)[];
  feeds_z_im_extrap?: (number | null)[];
};

// Result of the far-field norm consistency check: the live gain norm comes
// from the circuit side (input power); `pattern_norm` recomputes it from the
// field side (closed-form pattern integral). `delta_db` is the gap between
// them — the solver's power-balance error (NEC's "average gain" diagnostic),
// rendered as the offset between the solid and dotted lobes. Over a finite
// ground the same ratio, with the structural efficiency folded back out,
// is the third efficiency ledger: `radiated_fraction` = P_radiated/P_input
// including real ground absorption (issue #339) — the norm check restated
// as a percentage.
type NormCheckData = {
  directivity_norm: number;
  pattern_norm: number;
  method: string;
  delta_db: number;
  radiated_fraction: number;
  radiation_efficiency: number;
};

// Log-spaced segments-per-wire ladder for the convergence sweep. Hentenna's
// 8N+2 total segments at N=68 puts the dense LU at a ~550-cell matrix —
// still snappy at this N range on all backends, but enough span to see
// O(1/N) trajectories clearly. Same ladder across backends so the curves
// are directly comparable when the user switches slots.
const CONVERGE_N_VALUES: number[] = [8, 12, 17, 24, 34, 48, 68];

// Richardson-style extrapolation Z(1/N) → Z(N→∞). Fits Z = a₀ + a₁·h + a₂·h²
// (h = 1/N) on the last `nLast` points via least squares and returns a₀.
// Quadratic gives a sane answer for O(1/N) limit (BSpline without
// enrichment) AND O(1/N^p) for p slightly above 1 — basis-cap, enrichment,
// etc. With ≤2 points we can't fit; return null.
function richardsonExtrap(
  invN: number[],
  vals: number[],
  nLast = 5,
): number | null {
  const m = Math.min(nLast, invN.length);
  if (m < 3) return null;
  const start = invN.length - m;
  // Solve Ax = b for x = [a₀, a₁, a₂] using normal equations on the last m
  // points. m × 3 → 3 × 3 — small, no need for an LAPACK call.
  let s0 = 0, s1 = 0, s2 = 0, s3 = 0, s4 = 0;
  let t0 = 0, t1 = 0, t2 = 0;
  for (let i = start; i < invN.length; i++) {
    const h = invN[i];
    const y = vals[i];
    s0 += 1;
    s1 += h;
    s2 += h * h;
    s3 += h * h * h;
    s4 += h * h * h * h;
    t0 += y;
    t1 += y * h;
    t2 += y * h * h;
  }
  // 3x3 linear system: [[s0,s1,s2],[s1,s2,s3],[s2,s3,s4]] · [a0,a1,a2] = [t0,t1,t2]
  const m00 = s0, m01 = s1, m02 = s2;
  const m10 = s1, m11 = s2, m12 = s3;
  const m20 = s2, m21 = s3, m22 = s4;
  const det =
    m00 * (m11 * m22 - m12 * m21) -
    m01 * (m10 * m22 - m12 * m20) +
    m02 * (m10 * m21 - m11 * m20);
  if (Math.abs(det) < 1e-30) return null;
  const a0 =
    (t0 * (m11 * m22 - m12 * m21) -
      m01 * (t1 * m22 - m12 * t2) +
      m02 * (t1 * m21 - m11 * t2)) /
    det;
  return a0;
}

type PatternData = {
  theta_deg: number[];
  phi_deg: number[];
  gain_dbi: number[][];
  measurement_freq_mhz: number;
};

// Match the page's scheme: a wss:// upgrade is required on HTTPS pages (e.g. the
// deployed site behind Fly's force_https), where browsers block insecure ws://
// as mixed content. Plain ws:// only works on http:// (local dev).
const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`;

type View = "antenna" | "azimuth" | "elevation" | "smith";
const VIEWS: { id: View; label: string }[] = [
  { id: "antenna", label: "Antenna" },
  { id: "azimuth", label: "Azimuth (xy)" },
  { id: "elevation", label: "Elevation (yz)" },
  { id: "smith", label: "Smith" },
];

// The mobile output carousel's screens: the 4 chart views plus a dedicated
// Info screen for the solve readout (which floats as a HUD on desktop but
// deserves its own page on a phone). "info" stays out of the `View` union on
// purpose — `view` (and every data effect keyed on it) only ever holds a
// chart view; the Info screen leaves `view` parked on the last chart.
const MOBILE_SCREENS: { id: View | "info"; label: string }[] = [
  ...VIEWS,
  { id: "info", label: "Info" },
];

// Antenna-canvas camera projections. Pick two world axes to map to canvas
// (horizontal, vertical) and project. The hidden axis is the camera ray.
type Projection = "xy" | "xz" | "yz" | "iso";
type Vec3 = readonly [number, number, number];
// Each projection is an orthonormal screen basis: `h` maps to canvas-right,
// `v` to canvas-up, and the camera ray (toward the viewer) is h×v. The three
// axis-aligned views keep their original semantics (h/v pick world axes);
// "iso" is the classic isometric from the (+1,+1,+1) corner — x recedes to
// the lower-left, y to the lower-right, z stays up — so ground-plane layout
// and vertical structure are readable in one view.
const ISO_S2 = Math.SQRT1_2; // 1/√2
const ISO_S6 = 1 / Math.sqrt(6);
const PROJECTIONS: { id: Projection; label: string; h: Vec3; v: Vec3 }[] = [
  { id: "xy", label: "Top (xy)",   h: [1, 0, 0], v: [0, 1, 0] },
  { id: "xz", label: "Front (xz)", h: [1, 0, 0], v: [0, 0, 1] },
  { id: "yz", label: "Side (yz)",  h: [0, 1, 0], v: [0, 0, 1] },
  { id: "iso", label: "Iso", h: [-ISO_S2, ISO_S2, 0], v: [-ISO_S6, -ISO_S6, 2 * ISO_S6] },
];
const dot3 = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross3 = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

// `reattachKey`: the measuring effect early-returns while the ref is detached,
// so a caller whose measured element mounts LATER (e.g. the layout branch flips
// between mobile and desktop at runtime) must pass a value that changes with
// the branch, re-running the effect once the element exists.
function useSlideSize(maxSize = 720, reattachKey?: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(maxSize);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      const s = Math.min(rect.width, rect.height, maxSize);
      setSize(Math.max(160, Math.floor(s) - 16));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [maxSize, reattachKey]);
  return { ref, size };
}

// Mirror of the stylesheet's phone breakpoint. The query string MUST stay
// identical to the mobile `@media` prelude in styles.css so the JS layout
// branch and the CSS rules can never disagree about which viewports are
// "mobile": max-width 700px catches portrait phones, and the short+coarse
// clause catches landscape phones that are wider than 700px.
const MOBILE_MEDIA_QUERY =
  "(max-width: 700px), (max-height: 500px) and (pointer: coarse)";
const PORTRAIT_MEDIA_QUERY = "(orientation: portrait)";

function useMediaQuery(query: string): boolean {
  // useSyncExternalStore is StrictMode-safe and avoids the subscribe/setState
  // races of a hand-rolled effect. The snapshot is a boolean primitive — an
  // object snapshot would be re-created every call, which React rejects
  // ("The result of getSnapshot should be cached").
  const [subscribe, getSnapshot] = useMemo(() => {
    const mql = window.matchMedia(query);
    const sub = (onChange: () => void) => {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    };
    return [sub, () => mql.matches] as const;
  }, [query]);
  return useSyncExternalStore(subscribe, getSnapshot);
}

function useIsMobile() {
  const isMobile = useMediaQuery(MOBILE_MEDIA_QUERY);
  const portrait = useMediaQuery(PORTRAIT_MEDIA_QUERY);
  return {
    isMobile,
    orientation: portrait ? ("portrait" as const) : ("landscape" as const),
  };
}

// Document-fullscreen state + toggle for the gear menu's "full screen" check.
// This is the phone answer to browser chrome: on Android it hides BOTH the
// system status bar and the nav bar (the manifest's old standalone mode only
// hid the URL bar, and made Chrome nag to "install the app" besides).
// `supported` is false where element fullscreen doesn't exist (iPhone
// Safari), which hides the control. The subscribe pattern mirrors
// useMediaQuery: fullscreenchange fires on Esc / back-gesture exits too, so
// the checkbox can never disagree with the actual state.
function useFullscreen() {
  const [subscribe, getSnapshot] = useMemo(() => {
    const sub = (onChange: () => void) => {
      document.addEventListener("fullscreenchange", onChange);
      return () => document.removeEventListener("fullscreenchange", onChange);
    };
    return [sub, () => document.fullscreenElement != null] as const;
  }, []);
  const active = useSyncExternalStore(subscribe, getSnapshot);
  const toggle = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      document.documentElement
        .requestFullscreen({ navigationUI: "hide" })
        .catch(() => {});
    }
  }, []);
  return {
    active,
    toggle,
    supported: typeof document.documentElement.requestFullscreen === "function",
  };
}

function useThumbColumnSize(
  stripRef: React.RefObject<HTMLDivElement>,
  maxThumb = 280,
  reattachKey?: unknown, // see useSlideSize
) {
  // Vertical thumbstrip: 3 thumbs scaled so they ALWAYS fit (the strip never
  // scrolls — overflow:hidden in CSS). Fixed overhead:
  //   strip padding (12+12) + 2 gaps (2*8) +
  //   per-thumb (button padding 8+6 + label ~14 + gap 6 + border 2) * 3 ≈ 148.
  // Bias slightly high (150) so they fit with a hair of slack rather than
  // clip; floor low so a short window shrinks them instead of overflowing.
  const [size, setSize] = useState(180);
  useEffect(() => {
    const el = stripRef.current;
    if (!el) return;
    const update = () => {
      const h = el.clientHeight;
      if (h <= 0) return;
      const perThumb = (h - 150) / 3;
      setSize(Math.max(40, Math.min(maxThumb, Math.floor(perThumb))));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [stripRef, maxThumb, reattachKey]);
  return size;
}

type Theme = "light" | "dark";
const ThemeContext = createContext<Theme>("light");
// Theme is global (owned by the shell) but the toggle button lives in each
// session's sidebar header; sessions reach the setter through this context so
// the single button drives the one shared theme.
const ThemeControlContext = createContext<(next: Theme) => void>(() => {});

// The open design sessions and the controls to switch / add / close them. The
// shell provides this; each session renders a <TabStrip> off it, so all
// mounted sessions show the same tabs (only the active one is visible).
type SessionMeta = { id: number };
type SessionsCtx = {
  sessions: SessionMeta[];
  activeId: number;
  add: () => void;
  close: (id: number) => void;
  setActive: (id: number) => void;
  // Per-session one-line summary (design · solver · segs · ground) for the tab
  // hover, reported up from each session (which owns that state).
  summaries: Record<number, string>;
  reportSummary: (id: number, summary: string) => void;
};
const SessionsContext = createContext<SessionsCtx>({
  sessions: [],
  activeId: 0,
  add: () => {},
  close: () => {},
  setActive: () => {},
  summaries: {},
  reportSummary: () => {},
});

// Pinned far-field patterns, shared across all design sessions: pin in one
// tab, compare against it in any other. Owned by the shell — a pin is a
// frozen snapshot (full solve response + fetched metrics) with no live tie to
// the session that made it, so it survives design switches and tab closes.
// A separate context from SessionsContext: pin churn (async metrics arrivals)
// shouldn't invalidate the memoized tab-strip context.
type PinsCtx = {
  pins: PinnedPattern[];
  // Snapshot `result` under `label`; `req` is the request that produced it,
  // used to fetch the compare-table metrics.
  addPin: (label: string, result: SolveResponse, req: SolveRequest) => void;
  removePin: (id: string) => void;
  // Flip a pin's ghost overlay on/off without losing the snapshot.
  togglePin: (id: string) => void;
  clearPins: () => void;
};
const PinsContext = createContext<PinsCtx>({
  pins: [],
  addPin: () => {},
  removePin: () => {},
  togglePin: () => {},
  clearPins: () => {},
});

// The session tab strip, atop each session's sidebar. Global state comes from
// SessionsContext, so every mounted session renders an identical strip. Tabs
// are labelled "D1", "D2", … to stay compact for many designs; the full
// design/solver/segs/ground summary is on hover.
function TabStrip() {
  const { sessions, activeId, add, close, setActive, summaries } =
    useContext(SessionsContext);
  // The session whose close (×) was clicked and is awaiting confirmation, plus
  // the viewport coords of that × so the popover can anchor to it. Closing a
  // session discards its unsaved knob state, so we guard it behind this popover
  // rather than closing on the first click. The popover is position:fixed (not
  // absolute) because .tab-strip is an overflow:auto scroll container that would
  // otherwise clip it against the top/left edge.
  const [confirm, setConfirm] = useState<
    { id: number; x: number; y: number } | null
  >(null);
  const confirmId = confirm?.id ?? null;

  // Dismiss the confirm popover on Escape or an outside click. Clicks on any
  // tab-close × are excluded so switching the popover to another tab (or
  // reopening it) doesn't fight this dismiss handler.
  useEffect(() => {
    if (confirmId === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setConfirm(null);
    };
    const onDoc = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (!t.closest(".tab-close-confirm") && !t.closest(".tab-close")) {
        setConfirm(null);
      }
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [confirmId]);

  return (
    <div className="tab-strip" role="tablist" aria-label="Design sessions">
      {sessions.map((s) => (
        <div
          key={s.id}
          className={`tab ${s.id === activeId ? "active" : ""}`}
        >
          <button
            type="button"
            role="tab"
            aria-selected={s.id === activeId}
            className="tab-btn"
            onClick={() => setActive(s.id)}
            title={summaries[s.id] ?? `Design ${s.id}`}
          >
            D{s.id}
          </button>
          {sessions.length > 1 && (
            <button
              type="button"
              className="tab-close"
              onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                setConfirm({ id: s.id, x: r.left, y: r.bottom });
              }}
              aria-label={`Close design ${s.id}`}
              title={`Close design ${s.id}`}
              aria-haspopup="dialog"
              aria-expanded={confirmId === s.id}
            >
              ×
            </button>
          )}
        </div>
      ))}
      <button
        type="button"
        className="tab-add"
        onClick={add}
        aria-label="New design"
        title="New design"
      >
        +
      </button>
      {confirm !== null &&
        sessions.some((s) => s.id === confirm.id) && (
          <div
            className="tab-close-confirm"
            role="dialog"
            aria-label={`Close design ${confirm.id}?`}
            style={{ left: confirm.x, top: confirm.y + 6 }}
          >
            <span className="tab-close-confirm-msg">
              Close design {confirm.id}?
            </span>
            <div className="tab-close-confirm-actions">
              <button
                type="button"
                className="tab-close-confirm-cancel"
                autoFocus
                onClick={() => setConfirm(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="tab-close-confirm-ok"
                onClick={() => {
                  close(confirm.id);
                  setConfirm(null);
                }}
              >
                Close
              </button>
            </div>
          </div>
        )}
    </div>
  );
}

// Response from POST /optimize.
type OptMetrics = { z_in_re: number; z_in_im: number; z0_ohms: number; swr: number };
type OptimizeResult = {
  objective: string;
  params: Record<string, number>;
  objective_before: number;
  objective_after: number;
  metrics_before: OptMetrics;
  metrics_after: OptMetrics;
  n_evals: number;
  improved: boolean;
};
type OptObjective = "swr" | "resonance" | "match_z0";
const OPT_OBJECTIVE_LABELS: Record<OptObjective, string> = {
  swr: "SWR",
  resonance: "Resonance",
  match_z0: "Match Z₀",
};
// The two objectives offered in the compact control next to meas-freq.
const OPT_OBJECTIVES: OptObjective[] = ["swr", "resonance"];

// Per-knob optimisation settings (per geometry, per param name). `vary` marks
// the knob as a free variable the optimiser may change; opt extents bound the
// search; display extents are the knob's own slider range; step is the manual
// turn granularity (the optimiser itself is continuous). Absent for a knob =
// schema defaults.
type KnobOpt = {
  vary: boolean;
  optMin: number;
  optMax: number;
  dispMin: number;
  dispMax: number;
  step: number;
};

// Why the optimizer auto-paused, for the transient cue. `knob` = the user grabbed
// a marked knob by hand; `load` = a new design/variant was loaded (its marks and
// ranges no longer apply).
type OptPause = { kind: "knob"; name: string } | { kind: "load" };

// One antenna design session: the entire left sidebar + right stage plus all
// the state, effects, and the WebSocket that drive them. The shell (`App`,
// below) mounts one instance per tab and passes `active` — true only for the
// visible tab. An inactive session stays mounted, so its inputs survive, but
// suspends its WebSocket, global key listeners, and background solves via the
// `active` gates threaded through the effects below. Theme is global and lives
// in the shell; the canvases here read it through ThemeContext.
function DesignSession({ id, active }: { id: number; active: boolean }) {
  const [geometry, setGeometry] = useState<string>("");

  // Theme is global (shell-owned); the sidebar toggle reads the current value
  // and writes through the control context so it drives the one shared theme.
  const theme = useContext(ThemeContext);
  const applyTheme = useContext(ThemeControlContext);

  // Report this session's one-line summary up to the shell for the tab hover.
  const { reportSummary } = useContext(SessionsContext);

  // Tools (gear) dropdown in the header. Tucked away because it holds
  // occasional actions like the NEC deck export, not per-solve controls.
  const [gearMenuOpen, setGearMenuOpen] = useState(false);
  // Transient "Copied ✓" confirmation on the Copy-params menu item.
  const [copiedParams, setCopiedParams] = useState(false);
  // Document fullscreen (global, like theme) — the gear check is just the
  // nearest settings surface to reach it from.
  const fullscreen = useFullscreen();

  // Schema-driven parameter controls. Each registered example bundles
  // its parameter schema in web/examples/<name>.py; the backend serves
  // them on GET /examples and we render generic sliders from the result.
  //
  // Multi-band antennas (fan_dipole) get a nested shape for groups —
  // `paramValues[name].bands` is an array of per-instance bags,
  // pre-allocated to ParamGroupSpec.max_repeats so dialing the
  // repeat-count down and back up preserves the values.
  const [examples, setExamples] = useState<ExampleDescriptor[]>([]);
  const [examplesError, setExamplesError] = useState<string | null>(null);
  // User designs that failed to load (bad Python, no Builder, geometry error).
  // Surfaced from /examples so the author / Claude can see and fix them.
  const [loadErrors, setLoadErrors] = useState<DesignLoadError[]>([]);
  // Free-text filter for the antenna selector — matches name / label /
  // family / keywords so users can find a design without knowing its family.
  const [geomFilter, setGeomFilter] = useState<string>("");
  const [paramValues, setParamValues] = useState<Record<string, ParamValueBag>>({});
  // Per-geometry variant selection (which `<name>_params` dict on the
  // Builder to seed from). Falls back to the example's variants[0]
  // when this map has no entry — `default` for designs that declare
  // it, otherwise whatever the example shipped first.
  const [variantByGeom, setVariantByGeom] = useState<Record<string, string>>({});

  // --- Reactive knob optimiser (POST /optimize) ---
  // Live simulation: when on, knob/freq changes auto-solve (and the optimiser
  // runs). When off ("Paused"), edits update the geometry but the engine is held
  // — the user keeps changing the design, then clicks Live to resume and solve.
  // This replaces the old fire-and-forget "Cancel" on the solver-mismatch prompt,
  // which left the plots blank with no obvious way back. Defaults on.
  const [autoSim, setAutoSim] = useState(true);

  // Master enable + objective live in the compact control by meas-freq; per-knob
  // "vary" + extents + step live in each knob's right-click menu (knobOpt).
  const [optEnabled, setOptEnabled] = useState(false);
  const [optObjective, setOptObjective] = useState<OptObjective>("swr");
  // The objective ("optimise for") picker lives in a small gear popover next to
  // the Optimize button, mirroring the solver-slot gear.
  const [optMenuOpen, setOptMenuOpen] = useState(false);
  const [knobOpt, setKnobOpt] = useState<Record<string, Record<string, KnobOpt>>>({});
  // Open knob context menu: which param + anchor position.
  const [knobMenu, setKnobMenu] = useState<{ name: string; x: number; y: number } | null>(
    null,
  );
  const [optRunning, setOptRunning] = useState(false);
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null);
  const [optError, setOptError] = useState<string | null>(null);
  // When something auto-pauses the optimizer, this holds *why* for a brief cue
  // (cleared on re-enable / after a few seconds): grabbing a knob marked for
  // optimization by hand ("changing X by hand"), or loading a new design/variant
  // ("loaded a new design").
  const [optPausedBy, setOptPausedBy] = useState<OptPause | null>(null);
  const optAbortRef = useRef<AbortController | null>(null);
  // Latest optEnabled mirrored into a ref so the design-load reset (effects keyed
  // on geometry, and selectVariant) can tell whether the optimizer was actually
  // running — to show the pause cue only then — without taking optEnabled as a
  // dep (which would re-run the reset on every toggle).
  const optEnabledRef = useRef(false);
  optEnabledRef.current = optEnabled; // mirror latest for the design-load reset
  // Per-knob settings persist per geometry (knobOpt is keyed by geometry); just
  // close any open menu / clear the last result / abort any in-flight run when
  // the antenna changes. The optimizer also *pauses* on a design switch — its
  // objective and marks belong to the design you left — but this design's marks
  // are kept (they're keyed by geometry), so returning restores them; only the
  // running toggle is switched off. Show the cue only if it was actually on.
  useEffect(() => {
    optAbortRef.current?.abort();
    setKnobMenu(null);
    setOptResult(null);
    setOptError(null);
    if (optEnabledRef.current) {
      setOptEnabled(false);
      setOptPausedBy({ kind: "load" });
    }
    // optEnabledRef is read (not a dep) on purpose — see its declaration.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry]);

  // Load (or reload) the design catalog. Extracted so a trust action can
  // re-fetch it — trusting a design registers it server-side, and re-fetching
  // moves it out of the "awaiting trust" list into the selector.
  const loadExamples = useCallback(async () => {
    try {
      const j = await (await fetch("/examples")).json();
      const list: ExampleDescriptor[] = j.examples ?? [];
      setExamples(list);
      setExamplesError(null);
      setLoadErrors(Array.isArray(j.errors) ? j.errors : []);
      // Walk each example's schema and pre-seed defaults — including
      // pre-allocated group instance arrays — so the sliders have
      // something to render against on first show.
      setParamValues((prev) => {
        const next = { ...prev };
        for (const ex of list) {
          if (next[ex.name]) continue;
          next[ex.name] = seedDefaults(ex.param_schema);
        }
        return next;
      });
    } catch (e: unknown) {
      setExamplesError(String((e as Error)?.message ?? e));
    }
  }, []);

  useEffect(() => {
    loadExamples();
  }, [loadExamples]);

  // Trust a user design from the UI (local-only; the backend refuses when
  // hosted). `stem` is the design name (e.g. "user.my_dipole"); `allowEdits`
  // trusts future edits too (path-level, for a design you author).
  const [trustBusy, setTrustBusy] = useState<string | null>(null);
  const trustDesign = useCallback(
    async (stem: string, allowEdits: boolean) => {
      setTrustBusy(stem);
      try {
        const r = await fetch("/trust", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stem, allow_edits: allowEdits }),
        });
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          setExamplesError(`Trust failed: ${j.detail ?? r.status}`);
          return;
        }
        await loadExamples();
      } finally {
        setTrustBusy(null);
      }
    },
    [loadExamples],
  );

  // Auto-select a sensible default once /examples resolves, and recover if
  // the current selection disappears (e.g. backend dropped an example).
  // dipoles.invvee is the canonical simple antenna (also the CLI default);
  // fall back to the first example if it isn't registered.
  useEffect(() => {
    if (examples.length === 0) return;
    if (!examples.some((e) => e.name === geometry)) {
      const preferred = examples.find((e) => e.name === "dipoles.invvee");
      setGeometry((preferred ?? examples[0]).name);
    }
  }, [examples, geometry]);

  const currentExample = examples.find((e) => e.name === geometry);
  const currentValues = paramValues[geometry] ?? {};

  // Selector contents: filter by the search box (always keeping the current
  // selection visible so the <select> value stays valid), then group by
  // family in FAMILY_ORDER.
  const geomQuery = geomFilter.trim().toLowerCase();
  const geomGroups = (() => {
    const visible = examples.filter(
      (ex) => ex.name === geometry || matchesQuery(ex, geomQuery),
    );
    const byFam = new Map<string, ExampleDescriptor[]>();
    for (const ex of visible) {
      const fam = familyOf(ex.name);
      (byFam.get(fam) ?? byFam.set(fam, []).get(fam)!).push(ex);
    }
    return [...byFam.entries()]
      .map(([fam, items]) => ({
        fam,
        label: FAMILY_LABELS[fam] ?? fam,
        items: items.sort((a, b) => a.label.localeCompare(b.label)),
      }))
      .sort((a, b) => familyRank(a.fam) - familyRank(b.fam));
  })();
  const currentVariant =
    variantByGeom[geometry] ?? currentExample?.variants?.[0] ?? "default";

  // param_schema with the active variant's explicit presentation
  // overrides (variant_ui[variant].params) overlaid per param — e.g.
  // invvee's long-wire variants carry their own length_factor slider
  // range. Feeds the knob rail and the per-knob optimiser menu so both
  // see variant-correct bounds; value seeding stays on the raw schema
  // (defaults/values are variant_values' job).
  const currentSchema = useMemo<SchemaItem[]>(() => {
    if (!currentExample) return [];
    const over = currentExample.variant_ui?.[currentVariant]?.params;
    if (!over) return currentExample.param_schema;
    return currentExample.param_schema
      .map((item) =>
        !isGroup(item) && over[item.name]
          ? { ...item, ...over[item.name] }
          : item,
      )
      .filter(
        // A variant can hide a base-visible knob (e.g. invvee:dipole's
        // angle_deg — flat by definition, value pinned at 0 by the
        // variant). Display-only: the value still rides variant_values.
        (item) => isGroup(item) || !(item as { hidden?: boolean }).hidden,
      );
  }, [currentExample, currentVariant]);

  // Switch to a different variant: overlay the variant's per-param
  // values onto the existing slider state for this geometry (keeping
  // schema-derived defaults for any key the variant doesn't supply),
  // then snap designFreq / measFreq to the variant's `freq` so the
  // band tabs follow too. Sweep / live solve will pick up `variant`
  // via buildRequest on the next tick.
  function selectVariant(nextVariant: string) {
    if (!currentExample) return;
    // Loading a variant bulk-replaces the knob values, so any optimize marks and
    // their ranges (scaled to the values you're leaving) no longer apply. Drop
    // this geometry's marks and pause the optimizer — the same "you took over"
    // pause as grabbing a free knob by hand. (Unlike a design switch, the marks
    // *are* wiped here: it's the same geometry, so keeping them would silently
    // carry stale ranges into the new variant.)
    optAbortRef.current?.abort();
    setKnobOpt((prev) => {
      if (!prev[geometry]) return prev;
      const next = { ...prev };
      delete next[geometry];
      return next;
    });
    if (optEnabledRef.current) {
      setOptEnabled(false);
      setOptPausedBy({ kind: "load" });
    }
    setVariantByGeom((prev) => ({ ...prev, [geometry]: nextVariant }));
    const vv = currentExample.variant_values?.[nextVariant];
    if (!vv) return;
    setParamValues((prev) => {
      const base = seedDefaults(currentExample.param_schema);
      for (const k of Object.keys(base)) {
        if (k in vv) base[k] = vv[k] as never;
      }
      return { ...prev, [geometry]: base };
    });
    if (typeof vv.freq === "number") {
      setDesignFreq(vv.freq);
      // Fixed-geometry designs re-anchor unconditionally: their lock is
      // inert (measLockable), so only the variant freq is meaningful.
      if (linkMeas || !currentExample.has_design_freq) setMeasFreq(vv.freq);
    }
  }
  // Stable, primitive-only signature of the active antenna's params for
  // useEffect dependency arrays. Object identity isn't reliable because
  // setParamValues replaces the inner object on every onChange.
  const currentValuesKey = useMemo(
    () => JSON.stringify(currentValues),
    [currentValues],
  );
  // Deep-immutable path setter. ParamForm calls with paths like
  // ["bands", 2, "freq"] for nested groups, or ["angle_deg"] for
  // scalars. Recursive clone along the path so React sees a new
  // reference at every level it watches.
  function setParamAtPath(
    path: (string | number)[],
    value: number | string | boolean,
  ) {
    const setIn = (node: unknown, ps: (string | number)[]): unknown => {
      if (ps.length === 0) return value;
      const [head, ...rest] = ps;
      if (typeof head === "number") {
        const arr = ((node as unknown[]) ?? []).slice();
        arr[head] = setIn(arr[head], rest);
        return arr;
      }
      const obj = { ...((node as Record<string, unknown>) ?? {}) };
      obj[head] = setIn(obj[head], rest);
      return obj;
    };
    // Compute the new geometry bag eagerly (outside the setter) so the
    // meas-freq follow logic below can read newRoot reliably. React's
    // useState eager-bailout optimization runs the updater synchronously
    // only when no updates are queued; rapid slider drags batch
    // multiple updates, so a `newRoot` captured inside the updater
    // closure is null on the fast path — which manifests as the linked
    // measFreq snap working on slow drags but not on fast ones.
    const newRoot = setIn(paramValues[geometry] ?? {}, path) as ParamValueBag;
    setParamValues((prev) => ({
      ...prev,
      [geometry]: setIn(prev[geometry] ?? {}, path) as ParamValueBag,
    }));

    // Schema-driven meas-freq follow. Two variants:
    //   * group leaf: `path = [groupName, instanceIdx, leafName]` and
    //     the group declares `link_meas_freq_to_param` — push that
    //     instance's value of the named sibling into measFreq.
    //   * flat scalar: `path = [paramName]` and the ParamSpec declares
    //     `link_meas_freq_to_param` — push the current value of the
    //     named sibling (possibly itself) into measFreq. Used by
    //     multi-band antennas with parallel length_NN / freq_NN flat
    //     sliders (antennaknobs's fandipole).
    if (!linkMeas) return;
    const ex = currentExample;
    if (!ex) return;
    if (path.length === 1 && typeof path[0] === "string") {
      const paramName = path[0];
      const spec = ex.param_schema.find(
        (s) => !isGroup(s) && s.name === paramName,
      ) as SchemaParamSpec | undefined;
      const linked = spec?.link_meas_freq_to_param;
      if (!linked) return;
      const freqValue = newRoot[linked];
      if (typeof freqValue === "number") setMeasFreq(freqValue);
      return;
    }
    if (path.length < 3) return;
    const groupName = path[0];
    const instanceIdx = path[1];
    if (typeof groupName !== "string" || typeof instanceIdx !== "number") return;
    const group = ex.param_schema.find(
      (s) => isGroup(s) && s.name === groupName,
    ) as SchemaParamGroupSpec | undefined;
    if (!group || !group.link_meas_freq_to_param) return;
    const instances = newRoot[groupName];
    if (!Array.isArray(instances)) return;
    const inst = instances[instanceIdx];
    if (!inst) return;
    const freqValue = inst[group.link_meas_freq_to_param];
    if (typeof freqValue === "number") setMeasFreq(freqValue);
  }

  // A user-originated knob change (drag / arrow key) — the optimizer's own
  // write-back calls setParamAtPath directly and never routes through here, so
  // this is exactly the "the human moved it" path. If the knob the user grabbed
  // is one marked for optimization, hand them manual control: abort any
  // in-flight optimize (so its write-back can't clobber this change) and switch
  // Optimize off. Re-enabling resumes from the current values. (Fixed-knob
  // changes fall through untouched, so the reactive optimizer still re-solves
  // toward the objective on those.)
  function handleUserParamChange(
    path: (string | number)[],
    value: number | string | boolean,
  ) {
    if (optEnabled && path.length === 1 && typeof path[0] === "string") {
      const ko = (knobOpt[geometry] ?? {})[path[0]];
      if (ko?.vary) {
        optAbortRef.current?.abort();
        setOptEnabled(false);
        setOptPausedBy({ kind: "knob", name: path[0] });
      }
    }
    setParamAtPath(path, value);
  }
  // Fan_dipole was hand-rolled here pre-PR — fanNBands / fanBandIds /
  // fanBandFreqs / fanHalfdriverFactors / fanSlope / fanConeRadius
  // useState hooks plus a fanBandLengths memo. All of that now lives in
  // paramValues["fan_dipole"], seeded from the schema's defaults +
  // default_overrides. The deletion removed ~25 lines of state plus the
  // setFanBandSlot / setFanBandFreq / setFanHalfdriverFactor helpers.
  // Solver slots A / B / C — each one holds its own backend + options so
  // the user can switch between configured solvers with a single click
  // and tune each one independently from its gear menu.
  const [activeSlot, setActiveSlot] = useState<Slot>("A");
  const [slots, setSlots] = useState<Record<Slot, SlotConfig>>(DEFAULT_SLOTS);
  // Set once the user picks a backend by hand; after that we stop auto-seeding
  // the per-antenna recommended solver so their choice sticks.
  const backendTouchedRef = useRef(false);
  // True once the user clicked "Solve anyway" for the current design+solver
  // combo, so re-solves (knob drags) don't re-warn. Reset whenever the design or
  // solver changes (see the reset effect below). Mirrored into state so the
  // sweep/converge/norm-check effects re-fire on approval (issue #382 replaced
  // their 200 ms re-poll loops with plain effect dependencies); the ref stays
  // for the imperative reads in the solve path.
  const approvedComboRef = useRef(false);
  const [comboApproved, setComboApproved] = useState(false);
  // Shown when the current design+solver is a poor match — a dense solver on a
  // large array (slow), or an accelerator on a single element (overkill). The
  // solve is withheld until the user clicks "Solve anyway" or changes the solver
  // themselves; the app never switches solvers on its own.
  const [solverWarning, setSolverWarning] = useState(false);
  const [gearOpen, setGearOpen] = useState<Slot | null>(null);
  const activeConfig = slots[activeSlot];
  const backend = activeConfig.backend;
  const currentOpts = activeConfig.opts;
  const nPerWire = currentOpts.nPerWire;
  const wireRadius = currentOpts.wireRadius;
  // Stable hash of the active slot's config so useEffect can depend on it.
  const backendOptsKey = JSON.stringify(activeConfig);
  function updateSlotOpts(slot: Slot, patch: Partial<BackendOptsMap[Backend]>) {
    setSlots((prev) => ({
      ...prev,
      [slot]: {
        ...prev[slot],
        opts: { ...prev[slot].opts, ...patch } as BackendOptsMap[Backend],
      },
    }));
  }
  function setSlotBackend(slot: Slot, newBackend: Backend) {
    // Preserve segments-per-wire and wire-radius across the swap so the
    // user keeps their geometry-sizing choices when comparing models;
    // model-specific kwargs revert to that backend's defaults.
    setSlots((prev) => {
      const prevOpts = prev[slot].opts;
      const defaults = DEFAULT_BACKEND_OPTS[newBackend];
      return {
        ...prev,
        [slot]: {
          backend: newBackend,
          opts: {
            ...defaults,
            nPerWire: prevOpts.nPerWire,
            wireRadius: prevOpts.wireRadius,
          } as BackendOptsMap[Backend],
        },
      };
    });
  }
  function resetSlot(slot: Slot) {
    setSlots((prev) => ({ ...prev, [slot]: DEFAULT_SLOTS[slot] }));
  }
  // band/designFreq/measFreq seed to placeholders; the auto-select
  // effect below picks the first band of the active example and
  // overwrites them once /examples resolves.
  const [band, setBand] = useState<string>("");
  // Selected *measurement* band, authoritative while unlocked. Kept separate
  // from the design `band` (and from re-deriving via bandContaining(measFreq),
  // which collapses the moment the dial nudges measFreq out of a narrow ham
  // band and would strand the VFO window on the design band). Set on unlock and
  // by the meas-band picker; the dial roams measFreq within it without moving
  // it. Only consulted while unlocked — the meas controls are disabled locked.
  const [measBand, setMeasBand] = useState<string>("");
  const [designFreq, setDesignFreq] = useState(14.3);
  const [measFreq, setMeasFreq] = useState(14.3);
  const [linkMeas, setLinkMeas] = useState(true);
  // The meas↔design lock only means something when the design HAS a design
  // frequency to follow. Fixed-geometry designs (hand-tuned metres, imported
  // NEC decks) hide the design-freq row, so honouring the lock would chain
  // the dial to an invisible, meaningless value — a 406 MHz whip stuck
  // measuring at whatever the previous design left behind (issue #390). For
  // those the lock is inert and hidden, and the dial is always live; the
  // user's global linkMeas preference survives untouched for the next
  // design_freq-scaled design.
  const measLockable = currentExample?.has_design_freq ?? true;
  const measLocked = linkMeas && measLockable;
  // Ground plane at z = 0 (model per backend; see groundType). ON by
  // default: this is an HF wire-antenna workbench, and the over-ground
  // picture (takeoff angle, ground-lobed elevation pattern, shifted Z)
  // is the decision-relevant one — free space is the idealization you
  // opt into. The whole catalog solves grounded (75/75 audit, all
  // designs above z=0) on the default B-spline refl-coef path.
  const [groundEnabled, setGroundEnabled] = useState(true);
  // Shared ground choice — one selector describing the GROUND (finite vs
  // PEC); every backend solves it as best it can (see the GroundType note).
  const [groundType, setGroundType] = useState<GroundType>("finite");
  // Finite-ground method; hidden (and inert) on backends with a single
  // finite model, but kept in state so it survives backend flips during
  // engine comparison. Defaults to "fast" — Sommerfeld is opt-in (it costs
  // seconds per solve on the B-spline backend).
  const [finiteGroundMethod, setFiniteGroundMethod] =
    useState<FiniteGroundMethod>("fast");
  // Wire value derived for the server protocol (see GroundModel).
  const groundModel: GroundModel =
    groundType === "pec"
      ? "pec"
      : backendSupportsGround(backend)
        ? finiteGroundMethod
        : "fast";

  // One-line tab-hover summary: design · solver N=segs · ground model.
  // Every backend honours the selected method (momwire >= 0.8.0), so the
  // wording is uniform; "free space" when ground is off or unsupported.
  const groundActiveForSummary = groundEnabled && backendSupportsGround(backend);
  const groundSummary = !groundActiveForSummary
    ? "free space"
    : groundModel === "pec"
      ? "PEC ground"
      : groundModel === "fast"
        ? "reflection-coef ground"
        : "Sommerfeld ground";
  const tabSummary = `${(currentExample?.label ?? geometry) || "new design"} · ${backendDisplayLabel(backend, currentOpts)} N=${nPerWire} · ${groundSummary}`;
  useEffect(() => {
    reportSummary(id, tabSummary);
  }, [id, tabSummary, reportSummary]);
  // Far-field cut angles. The azimuth plot slices the pattern at elevation
  // `azElevDeg`; the elevation plot slices the vertical plane at azimuth
  // bearing `elevAzDeg` (0° = +x). Defaults give the conventional views.
  const [azElevDeg, setAzElevDeg] = useState(15);
  // Default elevation-cut azimuth is 0° (+x) for every geometry: Yagi,
  // moxon, and hexbeam beam +x; the inverted V now runs its arms along
  // ±y so its broadside lobe also peaks at ±x.
  const [elevAzDeg, setElevAzDeg] = useState(0);

  // When linked, design and measurement freq move together.
  function updateDesignFreq(v: number) {
    setDesignFreq(v);
    if (linkMeas) setMeasFreq(v);
  }
  function toggleLink(next: boolean) {
    setLinkMeas(next);
    if (next) {
      setMeasFreq(designFreq);
    } else {
      // Unlocking: seed the measurement band from where measFreq sits right now
      // (== the design band, since it was tracking designFreq while locked), so
      // the VFO window and meas-band picker start on the band you were viewing.
      setMeasBand(bandContaining(measFreq) ?? band);
    }
  }

  // The pre-PR setFanBandSlot / setFanBandFreq / setFanHalfdriverFactor
  // helpers (which also juggled measFreq to follow band tuning) are gone
  // — schema-driven ParamForm fires onChange for each input directly.
  // The "tuning a band → snap measFreq to that band's freq" affordance
  // was a fan-dipole-only side effect; recreating it generically would
  // require the schema to express "set this global state when a sibling
  // group leaf changes," which doesn't pay for itself for one antenna.
  // measFreq still follows designFreq via the linkMeas useEffect below.

  const [result, setResult] = useState<SolveResponse | null>(null);
  // Geometry-only snapshot of the just-selected antenna (wires + feed marker,
  // no currents), fetched fast so a large design's shape renders immediately
  // instead of waiting tens of seconds for the full solve. Superseded by
  // `result` the moment the real solve lands; only consulted while result is
  // null (i.e. right after an antenna switch).
  const [preview, setPreview] = useState<SolveResponse | null>(null);
  // The server's per-design solver recommendation ("arrayblock" for grid
  // arrays, "sinusoidal" for benchmark-sized meshes, null otherwise) — used
  // by the withhold gate and to pick the right warning copy.
  const recommendedBackend = normalizeBackend(
    preview?.default_backend ?? currentExample?.default_backend,
  );
  // True while the live solve is being withheld by the solver-mismatch gate.
  // The batch runners (sweep / converge / norm-check) decline to fire on
  // this: they are batches of the same solves the gate is protecting the
  // machine from (a dense sweep on a benchmark mesh is 41 multi-GiB solves).
  // Their effects depend on `comboApproved`, so "Solve anyway" re-fires them;
  // the server's cost model refuses warned batches without the approval flag
  // anyway (issue #382) — this gate is UX, not the enforcement.
  function solveWithheld(): boolean {
    return (
      comboInappropriate(backend, recommendedBackend) &&
      !approvedComboRef.current
    );
  }
  // Set when the selected design fails to solve/build — most often a user
  // design whose build_wires() raises. Geometry errors are deferred to
  // selection now (the builder isn't run at registration), so this banner is
  // where they surface. Cleared on every antenna switch.
  const [solveError, setSolveError] = useState<string | null>(null);
  // Name of the geometry whose preview has landed (and seeded the backend).
  // Gates the first solve after an antenna switch: we want preview → seed
  // backend → solve, not preview racing the solve. Reset to null on every
  // switch; the preview's .then sets it. Slider drags on the *same* antenna
  // keep solving freely (it stays equal to `geometry`).
  const [previewReady, setPreviewReady] = useState<string | null>(null);
  // Whether to render the per-feed (multi-feed) UI. Prefer the value the
  // server folds into the live solve / geometry response — authoritative for
  // user designs, which derive it lazily — and fall back to the example
  // descriptor (eager built-ins) before the first response lands.
  const effectiveMultiFeed =
    result?.multi_feed ??
    preview?.multi_feed ??
    currentExample?.multi_feed ??
    false;
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [rttMs, setRttMs] = useState<number | null>(null);
  // True whenever a main solve is outstanding (in flight or queued) — i.e. the
  // displayed analysis isn't current yet. `showBusy` is the *debounced* view of
  // it: the progress bar / panel dimming only appear once a solve outlasts
  // ~300 ms, so fast updates (cache hits, small designs) snap in cleanly
  // without a flash of busy chrome.
  const [solving, setSolving] = useState(false);
  const [showBusy, setShowBusy] = useState(false);
  const [sweep, setSweep] = useState<SweepData | null>(null);
  const [sweepRunning, setSweepRunning] = useState(false);
  // Smith-chart overlay toggles. Both are debounced sweeps that re-fire
  // whenever any antenna/backend parameter changes; gating them with these
  // checkboxes lets the user pause an expensive sweep (e.g. BSpline d=2
  // convergence on slow geometries) without leaving the Smith view.
  const [sweepEnabled, setSweepEnabled] = useState(true);
  const [convergeEnabled, setConvergeEnabled] = useState(false);
  const [converge, setConverge] = useState<ConvergeData | null>(null);
  const [convergeRunning, setConvergeRunning] = useState(false);
  // Far-field norm consistency check: on dwell, recompute the gain norm from
  // the pattern integral (field side) and overlay the resulting pattern
  // (dotted) against the live input-power norm (circuit side). The gap is the
  // solver's power-balance error. Cheap (closed form), so on by default;
  // the checkbox hides the overlay. `normCheck` is null while off or pending.
  const [normCheckEnabled, setNormCheckEnabled] = useState(true);
  const [normCheck, setNormCheck] = useState<NormCheckData | null>(null);
  // NEC's rp_card pattern, fetched on a debounce so we don't fire one per
  // slider tick. Overlaid on the cuts as a comparison line.
  const [pattern, setPattern] = useState<PatternData | null>(null);
  // Pinned far-field overlays for cross-antenna pattern comparison — shared
  // across all sessions through the shell (see PinsContext), so a pattern
  // pinned in one tab can be compared against in any other. The live
  // antenna's metrics for the side-by-side table stay per-session.
  const {
    pins: pinnedPatterns,
    addPin,
    removePin,
    togglePin,
    clearPins,
  } = useContext(PinsContext);
  const [liveMetrics, setLiveMetrics] = useState<PatternMetrics | null>(null);
  const [view, setView] = useState<View>("antenna");
  const [cameraProjection, setCameraProjection] = useState<Projection>("xy");
  // When the user switches antennas, reset the camera to that example's
  // natural starting view (declared on the backend via default_view).
  // Explicit user override sticks until the next geometry change.
  //
  // A deferred (user) design reports default_view === null — its real view is
  // auto-detected and arrives with the first geometry preview (handled where
  // the preview lands, below). Holding the current camera until then avoids
  // snapping to a wrong provisional view and flipping when the preview arrives.
  useEffect(() => {
    if (currentExample?.default_view) {
      setCameraProjection(currentExample.default_view);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentExample?.name]);

  // The app never switches solvers on its own. When the current design+solver
  // combo is a poor match the solve is withheld and a warning is shown; these
  // handle its two buttons. (To change solver, the user uses the gear menu.)

  // "Solve anyway": approve this combo so re-solves don't re-warn, then solve.
  function solveAnyway() {
    approvedComboRef.current = true;
    setComboApproved(true);
    setSolverWarning(false);
    controlsRef.current = buildRequest();
    requestSolve();
  }
  // "Pause simulation": stop auto-solving so the user can keep editing the design
  // without the engine running, instead of the old "Cancel" that just hid the
  // prompt and left the plots blank with no way forward. Approves this solver too,
  // so clicking Live to resume continues the simulation rather than re-warning.
  function pauseSimulation() {
    approvedComboRef.current = true;
    setComboApproved(true);
    setSolverWarning(false);
    setAutoSim(false);
  }
  // Cancel an IN-FLIGHT solve: stop waiting and discard its result. The server
  // keeps computing (its /ws loop is sequential and a running MoM solve can't be
  // interrupted), so this cancels the wait, not the computation.
  function cancelSolve() {
    if (lastSentSeqRef.current <= lastReceivedSeqRef.current) return; // nothing in flight
    // Mark every seq sent so far as cancelled: onmessage will advance the
    // received watermark for these but drop their results. A newer knob change
    // bumps lastSentSeq past this and solves again.
    canceledThroughSeqRef.current = lastSentSeqRef.current;
    syncSolving();
  }

  // Schema-driven design-freq link: when the active example has any
  // leaf marked `linked_to_design_freq`, sync the global designFreq
  // state to its value.
  const linkedDesignFreq = useMemo(
    () =>
      currentExample
        ? findLinkedDesignFreq(currentExample.param_schema, currentValues)
        : null,
    // currentValues is a fresh reference whenever setParamValues fires;
    // currentValuesKey is the stable primitive signature.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentExample, currentValuesKey],
  );
  useEffect(() => {
    if (linkedDesignFreq != null) {
      setDesignFreq(linkedDesignFreq);
      if (linkMeas) setMeasFreq(linkedDesignFreq);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkedDesignFreq, linkMeas]);
  // Antenna-canvas current visualization is split into two independent
  // toggles: the per-segment current-magnitude heatmap (wire color/width)
  // and the |I| envelope curve overlay. Either or both can be turned off;
  // the wires and feed marker are always drawn.
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showEnvelope, setShowEnvelope] = useState(false);
  // Wire labels and feed names can crowd dense geometries (and PyNEC returns
  // many more wires than the momwire engines), so let them be toggled. Wire
  // labels default OFF — they're the noisiest, especially on PyNEC.
  const [showWireLabels, setShowWireLabels] = useState(false);
  const [showFeedNames, setShowFeedNames] = useState(true);
  // Layout branch. Desktop never reads isMobile except as the sizing hooks'
  // reattach key, so no desktop viewport is affected; the key makes both
  // hooks re-measure if the window is resized across the breakpoint.
  const { isMobile, orientation } = useIsMobile();
  const { ref: slideRef, size: chartSize } = useSlideSize(720, isMobile);
  const thumbStripRef = useRef<HTMLDivElement>(null);
  const thumbSize = useThumbColumnSize(thumbStripRef, 280, isMobile);

  // Mobile output carousel (all hooks unconditional — desktop leaves them
  // inert). mobileIndex is which of the 5 screens the snap carousel rests on;
  // `view` stays the source of truth for the 4 chart screens and their data
  // effects, kept in sync by the scroll handler / reverse-sync effect below.
  const [mobileIndex, setMobileIndex] = useState(0);
  const mobileCarouselRef = useRef<HTMLDivElement>(null);
  const mobileScrollRafRef = useRef<number | null>(null);
  const { ref: mobRef, size: mobChartSize } = useSlideSize(720, isMobile);
  // The pinned-pattern comparison table minimizes to a "{n} pinned" chip so
  // it can get off the chart — it grows a row per pin and swallows a phone
  // screen. Starts collapsed on mobile, expanded on desktop (the pre-existing
  // behavior); pinning always expands it so the new row is seen.
  const [compareCollapsed, setCompareCollapsed] = useState(isMobile);

  // Track where a swipe/fling snaps and mirror it into state. rAF-throttled:
  // scroll events arrive per frame during a fling, one rounding per frame is
  // plenty. The rounded-index compare inside the setters keeps this from
  // fighting the programmatic scrolls below.
  const onMobileCarouselScroll = () => {
    if (mobileScrollRafRef.current !== null) return;
    mobileScrollRafRef.current = requestAnimationFrame(() => {
      mobileScrollRafRef.current = null;
      const el = mobileCarouselRef.current;
      if (!el || el.clientWidth === 0) return;
      const i = Math.round(el.scrollLeft / el.clientWidth);
      setMobileIndex((prev) => (prev === i ? prev : i));
      if (i < VIEWS.length) setView(VIEWS[i].id);
    });
  };

  // Dot tap: jump to a screen. Info (the last index) is reachable only here
  // and by swipe — it deliberately leaves `view` on the last chart screen.
  const goToMobileScreen = (i: number) => {
    setMobileIndex(i);
    if (i < VIEWS.length) setView(VIEWS[i].id);
    const el = mobileCarouselRef.current;
    if (el) el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" });
  };

  // Reverse sync: anything else that sets `view` (the arrow-key cycler) pages
  // the carousel to match. The DOM scroll position is the ground truth for
  // "where are we" — comparing rounded indices means we never fight an
  // in-progress swipe, and parking on Info ignores view changes entirely.
  useEffect(() => {
    if (!isMobile) return;
    const el = mobileCarouselRef.current;
    if (!el || el.clientWidth === 0) return;
    const target = VIEWS.findIndex((v) => v.id === view);
    const current = Math.round(el.scrollLeft / el.clientWidth);
    if (target < 0 || current >= VIEWS.length || current === target) return;
    setMobileIndex(target);
    el.scrollTo({ left: target * el.clientWidth, behavior: "smooth" });
  }, [view, isMobile]);

  // An orientation flip (or any pane resize) changes the screen width, so
  // scrollLeft no longer sits on a snap point; re-center the active screen
  // once the new layout lands (hence the rAF). Skipped when the rounded
  // position already matches — never fights a drag.
  useEffect(() => {
    if (!isMobile) return;
    const raf = requestAnimationFrame(() => {
      const el = mobileCarouselRef.current;
      if (!el || el.clientWidth === 0) return;
      const i = Math.round(el.scrollLeft / el.clientWidth);
      if (i !== mobileIndex) el.scrollTo({ left: mobileIndex * el.clientWidth });
    });
    return () => cancelAnimationFrame(raf);
  }, [isMobile, orientation, mobChartSize, mobileIndex]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      // Don't hijack arrows while a knob (e.g. the cut-angle dials) or a real
      // field is focused — those consume arrows to turn/edit their own value.
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.isContentEditable ||
          t.classList.contains("knob"))
      ) {
        return;
      }
      const idx = VIEWS.findIndex((v) => v.id === view);
      const next = e.key === "ArrowDown" ? (idx + 1) % VIEWS.length : (idx - 1 + VIEWS.length) % VIEWS.length;
      setView(VIEWS[next].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, active]);

  const sweepTimerRef = useRef<number | null>(null);
  const sweepAbortRef = useRef<AbortController | null>(null);
  const patternTimerRef = useRef<number | null>(null);
  const patternAbortRef = useRef<AbortController | null>(null);
  const convergeTimerRef = useRef<number | null>(null);
  const convergeAbortRef = useRef<AbortController | null>(null);
  const normCheckTimerRef = useRef<number | null>(null);
  const normCheckAbortRef = useRef<AbortController | null>(null);
  const previewAbortRef = useRef<AbortController | null>(null);
  // JSON of the request the currently-displayed preview wireframe was built
  // from. When Live is off no solve redraws the geometry, so the solve effect
  // refetches the preview itself on a param/variant/freq change — but only when
  // this signature actually changed, so it skips the redundant refetch right
  // after an antenna switch (whose preview the switch effect already built).
  const previewSigRef = useRef<string | null>(null);
  // Timestamp (performance.now) when the busy chrome last became visible, so
  // the reveal effect can enforce a minimum-visible window. null = not shown.
  const shownAtRef = useRef<number | null>(null);
  // Latest selected antenna, mirrored into a ref so the (mount-once) WebSocket
  // onmessage handler can drop responses for an antenna the user already
  // switched away from. Updated every render — cheap and always current.
  const geometryRef = useRef(geometry);
  geometryRef.current = geometry;

  const wsRef = useRef<WebSocket | null>(null);
  // Latest-wins /ws protocol counters. Every knob change is sent eagerly with a
  // monotonic `_seq`; the server keeps only the freshest queued request and may
  // skip-send superseded results, so the client orders and prunes by `_seq`. A
  // solve is outstanding iff more has been sent than received. These live in
  // refs so they survive StrictMode/HMR socket teardown — the counter must
  // never rewind below what's already been received.
  const seqRef = useRef(0); // last _seq assigned (monotonic, never reset)
  // Solve-lane session id (issue #382): one per workbench tab (A/B compare
  // tabs are separate App instances, hence separate sessions). The server
  // keys its single-lane scheduler on this — everything this tab asks for
  // runs one-at-a-time server-side, live solve first.
  const sessionIdRef = useRef<string>(
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `s-${Math.random().toString(36).slice(2)}`,
  );
  const lastSentSeqRef = useRef(0); // highest _seq put on the wire
  const lastReceivedSeqRef = useRef(0); // highest _seq received or implicitly acked
  const canceledThroughSeqRef = useRef(0); // drop rendering for _seq <= this
  const sentAtRef = useRef<Map<number, number>>(new Map()); // _seq → send time (RTT)
  const solveRafRef = useRef<number | null>(null); // trailing-edge rAF throttle handle

  function buildRequest(): SolveRequest {
    // ground_model is shared across backends (εr=10, σ=0.002 for the finite
    // models): PyNEC honours it directly; momwire's B-spline family solves
    // the finite models with its reflection-coefficient ground, while
    // Sinusoidal folds them to the PEC image solve (the server
    // ships the real εr/σ for the pattern either way).
    const groundActive = groundEnabled && backendSupportsGround(backend);
    const base: SolveRequest = {
      _session: sessionIdRef.current,
      geometry,
      variant: currentVariant,
      solver: backend === "pynec" ? "pynec" : "momwire",
      n_per_wire: nPerWire,
      design_freq_mhz: designFreq,
      measurement_freq_mhz: measFreq,
      wire_radius: wireRadius,
      ground: groundActive,
      // ground_fast is the legacy boolean; ground_model is authoritative
      // server-side when present. Send both so either server version agrees.
      ground_fast: groundActive && groundModel === "fast",
      ground_model: groundModel,
    };
    if (backend !== "pynec") {
      base.momwire_model = backend;
      const opts = modelOptionsForRequest(backend, currentOpts);
      // BSplineSolver rejects ground_z + use_singular_enrichment together
      // (image reaction for enrichment bases isn't worked out yet). Force
      // enrichment off in the request when ground is active so the user
      // gets a sensible solve instead of a server error; the gear shows
      // an inline note.
      if (isBSplineFamily(backend) && groundActive) {
        opts.use_singular_enrichment = false;
      }
      base.model_options = opts;
    }
    // Schema-driven antennas (all of them now): merge the active
    // paramValues straight in. For fan_dipole this includes a nested
    // `bands: [{band_id, freq, length_factor}, ...]` array; the backend
    // unpacks it in _bands_from_request().
    Object.assign(base, currentValues);
    // hexbeam_5band's daisy_chain feed mode uses NEC TL cards; momwire
    // engines reject any non-empty build_tls(). The daisy_chain gear
    // is greyed out when a momwire slot is active (see the disabled prop
    // on the schema control), and we belt-and-suspenders force the
    // request to daisy_chain=false here so a stale value from a
    // previously-active pynec slot doesn't slip through.
    if (backend !== "pynec" && "daisy_chain" in base) {
      base.daisy_chain = false;
    }
    return base;
  }

  // Run the optimiser once: POST the current solve request + the free knobs
  // (from each knob's menu) and objective, then apply the returned params to the
  // knobs (re-solving via the normal onChange path). Warm-started from the
  // current values; a newer run aborts the previous so stale results are
  // dropped. Always uses the momwire engine server-side.
  async function runOptimize() {
    const settings = knobOpt[geometry] ?? {};
    const free = Object.entries(settings)
      .filter(([, o]) => o.vary)
      .map(([name, o]) => ({ name, min: o.optMin, max: o.optMax }));
    if (free.length === 0) return;
    optAbortRef.current?.abort();
    const ctrl = new AbortController();
    optAbortRef.current = ctrl;
    setOptRunning(true);
    setOptError(null);
    try {
      const resp = await fetch("/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          ...buildRequest(),
          // Reactive runs are warm-started, so a modest eval cap keeps them snappy.
          optimize: { free, objective: optObjective, max_evals: 40 },
        }),
      });
      const data = await resp.json();
      if (ctrl.signal.aborted) return; // superseded by a newer run
      if (data.error) {
        setOptError(String(data.error));
      } else {
        setOptResult(data as OptimizeResult);
        for (const [name, val] of Object.entries((data as OptimizeResult).params)) {
          setParamAtPath([name], val);
        }
      }
    } catch (e) {
      if (!ctrl.signal.aborted) setOptError(String(e));
    } finally {
      if (optAbortRef.current === ctrl) {
        optAbortRef.current = null;
        setOptRunning(false);
      }
    }
  }

  // Reactive optimisation. When enabled with >=1 free knob, re-tune shortly
  // after the user pauses on any *fixed* input. The trigger is a signature of
  // everything the optimiser depends on EXCEPT the free knobs' values — the
  // optimiser writes those, so including them would loop. Turning it on produces
  // a fresh signature, so it also tunes immediately on enable.
  const optFixedSig = useMemo(() => {
    if (!optEnabled) return "";
    const settings = knobOpt[geometry] ?? {};
    const free = Object.entries(settings).filter(([, o]) => o.vary);
    if (free.length === 0) return "";
    const freeSet = new Set(free.map(([n]) => n));
    const fixed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(currentValues)) {
      if (!freeSet.has(k)) fixed[k] = v;
    }
    return JSON.stringify({
      geometry,
      objective: optObjective,
      backend,
      designFreq,
      measFreq,
      bounds: free.map(([n, o]) => [n, o.optMin, o.optMax]),
      fixed,
    });
    // currentValuesKey stands in for currentValues' contents in the deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    optEnabled,
    knobOpt,
    geometry,
    optObjective,
    backend,
    designFreq,
    measFreq,
    currentValuesKey,
  ]);

  useEffect(() => {
    // Paused (Live off) holds the optimiser too — it drives engine solves, so it
    // must respect the same gate as the main solve. Resuming re-runs this effect
    // (autoSim is a dep) and re-tunes.
    if (!optFixedSig || !autoSim || !active) return;
    const t = setTimeout(() => {
      runOptimize();
    }, 400);
    return () => clearTimeout(t);
    // runOptimize captured here reflects the state at this signature; re-running
    // only when the signature changes is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optFixedSig, autoSim, active]);

  // The "paused — changing X by hand" cue is a brief flash: clear it a few
  // seconds after it appears so it doesn't linger while Optimize stays off.
  useEffect(() => {
    if (!optPausedBy) return;
    const t = setTimeout(() => setOptPausedBy(null), 5000);
    return () => clearTimeout(t);
  }, [optPausedBy]);

  // The effective per-knob optimiser settings: the stored entry, or seeded from
  // the schema (extents = slider bounds, step = schema step, not varying).
  function knobOptFor(name: string): KnobOpt {
    const existing = knobOpt[geometry]?.[name];
    if (existing) return existing;
    const s = currentSchema.find(
      (x): x is SchemaParamSpec => !isGroup(x) && x.name === name,
    );
    const min = s?.min ?? 0;
    const max = s?.max ?? 1;
    return {
      vary: false,
      optMin: min,
      optMax: max,
      dispMin: min,
      dispMax: max,
      step: s?.step ?? 0.001,
    };
  }
  function updateKnobOpt(name: string, patch: Partial<KnobOpt>) {
    const base = knobOptFor(name);
    setKnobOpt((prev) => ({
      ...prev,
      [geometry]: { ...(prev[geometry] ?? {}), [name]: { ...base, ...patch } },
    }));
  }

  // Close the knob menu on Escape.
  useEffect(() => {
    if (!knobMenu || !active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setKnobMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [knobMenu, active]);

  // Export the current design as a NEC2 .nec card deck and trigger a
  // browser download. The backend reuses the same builder construction as
  // the live solve, so the deck matches what's on screen. Designs with no
  // faithful native-NEC form (TL/DiffTL networks) come back 422; surface
  // the server's message rather than downloading an error page.
  async function downloadNec() {
    setGearMenuOpen(false);
    try {
      const resp = await fetch("/export_nec", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequest()),
      });
      if (!resp.ok) {
        let detail = `NEC export failed (${resp.status}).`;
        try {
          detail = (await resp.json()).detail ?? detail;
        } catch {
          /* non-JSON error body — keep the status-based message */
        }
        window.alert(detail);
        return;
      }
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") ?? "";
      const m = cd.match(/filename="([^"]+)"/);
      const filename = m ? m[1] : `${geometry.replace(/\./g, "_") || "antenna"}.nec`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      window.alert(`NEC export failed: ${e}`);
    }
  }

  // Copy the current knob values as a paste-ready Python `default_params`
  // (or `<variant>_params`) block. Replaces the old workflow of hand-copying
  // the values printed on screen back into a design file. The backend reuses
  // the same variant + live-knob overlay as the solve, so what you copy is
  // exactly the antenna on screen.
  async function copyParams() {
    try {
      const resp = await fetch("/params_source", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequest()),
      });
      const data = await resp.json();
      if (!resp.ok || data.available === false || data.error) {
        window.alert(data.error ?? "Copy params is unavailable for this design.");
        return;
      }
      const src: string = data.source;
      try {
        await navigator.clipboard.writeText(src);
        setCopiedParams(true);
        window.setTimeout(() => setCopiedParams(false), 1500);
      } catch {
        // Clipboard API blocked (e.g. insecure context) — fall back to a
        // prompt the user can copy from by hand.
        window.prompt("Copy these params:", src);
      }
    } catch (e) {
      window.alert(`Copy params failed: ${e}`);
    }
  }

  const currentBands: BandSpec[] = currentExample?.bands ?? [];

  // Anchor for the measurement-freq VFO window: the snap-freq of the *selected*
  // measurement band (`measBand`), falling back to designFreq before one is
  // chosen. Anchoring on the selected band — not on bandContaining(measFreq) —
  // keeps the window stable as the dial roams measFreq within (or a touch
  // outside) a narrow ham band; deriving it from measFreq would collapse the
  // window back to the design band the instant measFreq left the band edge.
  const measBandAnchor =
    currentBands.find((b) => b.key === measBand)?.freq_mhz ?? designFreq;

  // When the active example changes (or first loads), snap band /
  // designFreq / measFreq to the band whose [min, max] window contains
  // the design's native freq (from the schema's freq ParamSpec). If
  // there's no freq param or it falls outside every band, fall back
  // to the first band so the snap is still well-defined. Skipped
  // entirely for examples that suppress the row (bands === []) —
  // those own their design freq via their own schema controls.
  useEffect(() => {
    if (!currentExample) return;
    if (currentBands.length === 0) {
      if (band !== "") setBand("");
      return;
    }
    // Always re-snap on geometry switch — every HF example shares the
    // DEFAULT_HF_BANDS list, so a sticky band key (e.g. "10m" from the
    // previous 28 MHz design) would otherwise survive a switch into a
    // 14 MHz design and keep the slider parked on the wrong band.
    // (The containing-band / native-freq logic lives in snapForExample,
    // shared with the antenna-switch preview fetch — see there.)
    const snap = snapForExample(currentExample)!;
    setBand(snap.bandKey);
    setDesignFreq(snap.freq);
    // Re-anchor the dial too: always when locked, and also for
    // fixed-geometry designs — their lock is inert (see measLockable), so
    // a measFreq left over from the previous design would strand the
    // measurement outside this design's window entirely.
    if (linkMeas || !currentExample.has_design_freq) {
      setMeasFreq(snap.freq);
      setMeasBand(snap.bandKey);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentExample]);

  function selectBand(nextKey: string) {
    const nb = currentBands.find((b) => b.key === nextKey);
    if (!nb) return;
    setBand(nextKey);
    setDesignFreq(nb.freq_mhz);
    if (linkMeas) setMeasFreq(nb.freq_mhz);
    else if (measFreq < nb.min_mhz || measFreq > nb.max_mhz) {
      setMeasFreq(nb.freq_mhz);
    }
  }

  // Measurement-band quick selector: jumps measFreq to the band centre and
  // auto-unlinks from design so the antenna geometry isn't retuned.
  function selectMeasBand(nextKey: string) {
    const nb = currentBands.find((b) => b.key === nextKey);
    if (!nb) return;
    // Only a *live* lock needs breaking; an inert one (fixed-geometry
    // design) is the user's global preference — leave it for the next
    // design_freq-scaled design.
    if (measLocked) setLinkMeas(false);
    setMeasBand(nextKey);
    setMeasFreq(nb.freq_mhz);
  }

  // Which band (if any) currently contains the measurement freq — drives
  // the active-tab highlight on the meas-band selector. Falls outside any
  // band → no tab highlighted.
  function bandContaining(f: number): string | null {
    for (const b of currentBands) {
      if (f >= b.min_mhz && f <= b.max_mhz) return b.key;
    }
    return null;
  }

  // The latest control values, used to send a new request when the prior one
  // completes (drops intermediate values rather than queuing them all up).
  const controlsRef = useRef<SolveRequest>(buildRequest());

  // --- Pattern compare (pin / ghost overlay) --------------------------------
  // Pin the current pattern: snapshot the solve response (for the ghost trace)
  // into the shared cross-session pin list. The snapshot is frozen — it won't
  // change as the live knobs move, which is the whole point of comparing.
  function pinCurrentPattern() {
    if (!result) return;
    const label = `${currentExample?.label ?? geometry} @ ${measFreq.toFixed(2)} MHz`;
    addPin(label, result, controlsRef.current);
  }

  // Keep the live antenna's metrics fresh for the table, but only while a
  // comparison is actually on screen (≥1 pin and a pattern view) — the metrics
  // need a full far-field solve, so don't pay for it otherwise. Debounced so it
  // doesn't fire on every knob tick.
  const pinCount = pinnedPatterns.length;
  const comparing = pinCount > 0 && (view === "azimuth" || view === "elevation");
  useEffect(() => {
    if (!comparing || !result || !active) {
      setLiveMetrics(null);
      return;
    }
    let cancelled = false;
    const h = window.setTimeout(() => {
      fetchMetrics(controlsRef.current).then((m) => {
        if (!cancelled) setLiveMetrics(m);
      });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(h);
    };
    // result identity changes per solve; that's the cue to refresh.
  }, [comparing, result, active]);

  // Reset the "solve anyway" approval whenever the design or solver changes, so
  // an inappropriate combo is re-evaluated (and re-warned) rather than riding a
  // stale approval. Defined before the solve effect so it runs first.
  useEffect(() => {
    approvedComboRef.current = false;
    setComboApproved(false);
  }, [geometry, backend, backendOptsKey]);

  useEffect(() => {
    if (!active) return;
    // Hold the first solve after an antenna switch until that antenna's preview
    // has landed (previewReady === geometry). Param/freq tweaks on the *same*
    // antenna keep solving freely — previewReady stays equal to geometry until
    // the next switch resets it to null.
    if (previewReady !== geometry) return;
    controlsRef.current = buildRequest();
    // Paused: keep controlsRef fresh (so resuming sends the latest design) but
    // don't solve, and suppress the combo warning — nothing is running to warn
    // about. Toggling Live back on re-runs this effect (autoSim is a dep) and
    // solves the current state.
    if (!autoSim) {
      setSolverWarning(false);
      // Live is off, so no solve will run to redraw the geometry. Keep the
      // preview wireframe in sync with the knobs ourselves: a variant switch
      // or knob/freq change should still reshape the antenna. Refetch the cheap
      // geometry-only preview (build_wires, no solve) when the request actually
      // changed — the signature guard skips the redundant fetch right after an
      // antenna switch, and unchanged re-renders. No camera snap or gate reset:
      // this is in-place tuning of the same antenna.
      const sig = JSON.stringify(controlsRef.current);
      if (sig !== previewSigRef.current) {
        previewSigRef.current = sig;
        // A prior solve's result (rendered in preference to preview, and its
        // impedance/far-field) is now stale for these knobs. Drop it so the
        // fresh preview shows and no stale solved metrics linger.
        setResult(null);
        previewAbortRef.current?.abort();
        const controller = new AbortController();
        previewAbortRef.current = controller;
        fetch("/geometry", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: sig,
          signal: controller.signal,
        })
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => {
            if (controller.signal.aborted) return;
            if (data && data.error) {
              setSolveError(data.error as string);
              return;
            }
            if (data && data.wires) {
              setSolveError(null);
              setPreview(data as SolveResponse);
            }
          })
          .catch(() => {});
      }
      return;
    }
    // Withhold the solve when the design/solver combo is a poor match and the
    // user hasn't approved it — show a warning instead. The app never switches
    // the solver itself; the user does that in the gear menu, which changes
    // `backend` and re-runs this effect.
    if (
      comboInappropriate(backend, recommendedBackend) &&
      !approvedComboRef.current
    ) {
      setSolverWarning(true);
      return;
    }
    setSolverWarning(false);
    requestSolve();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    active,
    autoSim,
    geometry, previewReady, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
  ]);

  // Antenna switch: drop the previous antenna's results immediately so nothing
  // stale lingers (the old geometry/impedance/far-field would otherwise stay on
  // screen for the tens of seconds a large array takes to solve), then fetch a
  // fast geometry-only preview so the NEW antenna's shape draws right away. The
  // live /ws solve (fired by the effect above) replaces the preview with the
  // real currents/impedance/far-field when it lands. Keyed on `geometry` alone:
  // param/freq tweaks on the *same* antenna keep updating in place (no flicker),
  // matching the prior behaviour for the fast designs where this isn't a pain.
  useEffect(() => {
    // Skip the "unset" initial state. On a fresh load `geometry` is "" until the
    // /examples list resolves and the auto-select effect picks the default
    // (dipoles.invvee). Fetching a preview for "" would POST an empty key, which
    // the server resolves to the alphabetically-first design (arrays.bowtiearray)
    // — building and rendering a geometry nobody asked for, only to be replaced a
    // beat later. Bail here so the first preview is the real default.
    if (!geometry) return;
    setResult(null);
    setPreview(null);
    setSolveError(null);
    setPreviewReady(null); // close the solve gate until this antenna's preview lands
    setSolverWarning(false); // drop any combo warning from the prior design
    previewAbortRef.current?.abort();
    const controller = new AbortController();
    previewAbortRef.current = controller;
    // Capture the geometry this run is for, so the gate is released for the
    // right antenna even if `geometry` changed by the time the fetch resolves.
    const forGeometry = geometry;
    const req = buildRequest();
    // The band-snap effect (on currentExample, above) runs in this same
    // commit, but its setDesignFreq/setMeasFreq only land NEXT render —
    // while this preview goes out NOW and is keyed on `geometry`, so
    // nothing refetches it once the snap lands. Left alone it frames the
    // canvas for the PREVIOUS design's wavelength until a real solve
    // replaces it — or indefinitely, when the solve is withheld (solver
    // gate) or Live is off (issue #390). Bake the snapped freqs into this
    // request instead of reading the one-render-stale state.
    const snap = snapForExample(currentExample);
    if (snap) {
      req.design_freq_mhz = snap.freq;
      if (linkMeas || !currentExample!.has_design_freq) {
        req.measurement_freq_mhz = snap.freq;
      }
    }
    previewSigRef.current = JSON.stringify(req);
    fetch("/geometry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (controller.signal.aborted) return;
        if (data && data.error) {
          // build_wires raised while building the preview — surface it and
          // leave the gate closed: a live solve would just reproduce the same
          // error, so there's nothing to render. (The error banner shows it.)
          setSolveError(data.error as string);
          return;
        }
        if (data && data.wires) {
          setPreview(data as SolveResponse);
          // A deferred (user) design derives its natural view only when the
          // builder first runs — which is this preview. Snap the camera to it
          // here, once per selection (this effect is keyed on `geometry`).
          const dv = (data as SolveResponse).default_view;
          if (dv) setCameraProjection(dv);
        }
        // Release the gate. The solve effect then either solves or — if the
        // design/solver combo is a poor match — withholds and warns.
        setPreviewReady(forGeometry);
      })
      .catch(() => {
        // Aborted or offline. If this run wasn't superseded, still release the
        // gate so the live solve renders the antenna (its own error path
        // surfaces anything that goes wrong there).
        if (!controller.signal.aborted) setPreviewReady(forGeometry);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry]);

  // Debounced sweep across measurement freq. Re-runs whenever any antenna
  // parameter changes. Single-band geometries sweep around designFreq, so
  // moving the measFreq slider doesn't re-sweep (the existing data already
  // covers the new slider position). Fan dipole sweeps around measFreq,
  // so measFreq is part of the deps there to re-anchor.
  useEffect(() => {
    // Cancel any in-flight sweep fetch immediately. Without this the
    // previous sweep keeps streaming for hundreds of ms (PyNEC ground at
    // 100 ms/point × 41 points = ~4 s) and starves the live /ws solve of
    // CPU — the user moves a slider but the next impedance update is
    // delayed behind the now-stale sweep finishing.
    sweepAbortRef.current?.abort();
    if (sweepTimerRef.current) {
      window.clearTimeout(sweepTimerRef.current);
    }
    setSweep(null);
    setSweepRunning(false);
    if (!sweepEnabled || !active) {
      return;
    }
    // The 500 ms dwell only debounces network churn; ordering against the
    // live solve is the server lane's job now (live outranks sweeps).
    sweepTimerRef.current = window.setTimeout(runSweep, 500);
    return () => {
      if (sweepTimerRef.current) window.clearTimeout(sweepTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq,
    groundEnabled, groundModel,
    sweepEnabled,
    active,
    // measFreq/measLocked drive the anchor now (meas_freq policy, or any
    // unlocked design — incl. fixed-geometry designs whose lock is inert),
    // so a meas-band change or dial turn re-runs the sweep.
    measFreq, measLocked,
    // A variant can override sweep_policy (variant_ui) without changing any
    // param — e.g. a band-locked variant. currentValuesKey wouldn't move then,
    // so depend on currentVariant directly to re-run the sweep on switch.
    currentVariant,
    // The poor-match gate: while it withholds, runSweep declines to issue the
    // batch; approving ("Solve anyway") or a new recommendation re-fires this
    // effect (issue #382 — replaces the old 200 ms re-poll loop).
    comboApproved, recommendedBackend,
  ]);

  // Debounced convergence sweep over segments-per-wire. Independent of the
  // freq sweep above: re-runs on any antenna/backend change, gated by its
  // own overlay checkbox. The active slot's `nPerWire` is *overridden* by
  // the ladder values for the duration of the sweep — the per-slot opts
  // stay untouched, so the live /ws solve keeps using the user's setting.
  useEffect(() => {
    convergeAbortRef.current?.abort();
    if (convergeTimerRef.current) {
      window.clearTimeout(convergeTimerRef.current);
    }
    setConverge(null);
    setConvergeRunning(false);
    if (!convergeEnabled || !active) {
      return;
    }
    // Debounce only; the server lane orders it behind the live solve.
    convergeTimerRef.current = window.setTimeout(runConverge, 500);
    return () => {
      if (convergeTimerRef.current) window.clearTimeout(convergeTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    convergeEnabled,
    active,
    // Poor-match gate (see the sweep effect).
    comboApproved, recommendedBackend,
  ]);

  // Debounced far-field norm consistency check. Same shape as the converge
  // sweep: re-runs on any antenna/param change (which invalidates the norm),
  // gated by its own overlay checkbox. The server lane runs it after the
  // live solve (priority ordering), so it lands on that solve's cached
  // currents rather than forcing a re-solve.
  useEffect(() => {
    normCheckAbortRef.current?.abort();
    if (normCheckTimerRef.current) {
      window.clearTimeout(normCheckTimerRef.current);
    }
    setNormCheck(null);
    if (!normCheckEnabled || !active) {
      return;
    }
    normCheckTimerRef.current = window.setTimeout(runNormCheck, 500);
    return () => {
      if (normCheckTimerRef.current) window.clearTimeout(normCheckTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    normCheckEnabled,
    active,
    // Poor-match gate (see the sweep effect).
    comboApproved, recommendedBackend,
  ]);

  // Debounced NEC pattern fetch. PyNEC only — for momwire there's no rp_card
  // equivalent. Tracks measurement freq too (unlike the impedance sweep).
  useEffect(() => {
    if (patternTimerRef.current) window.clearTimeout(patternTimerRef.current);
    setPattern(null);
    if (backend !== "pynec" || !active) return;
    patternTimerRef.current = window.setTimeout(() => {
      runPattern();
      patternTimerRef.current = null;
    }, 500);
    return () => {
      if (patternTimerRef.current) window.clearTimeout(patternTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    active,
  ]);

  async function runSweep() {
    // No competition with the live solve to time around anymore: the server's
    // per-session solve lane (issue #382) runs everything one-at-a-time with
    // the live solve first, so this just sends. While the poor-match gate is
    // withholding, don't issue batches of the very solves it's blocking — the
    // effect re-fires on approval (comboApproved is a dependency).
    if (solveWithheld()) return;
    sweepTimerRef.current = null;
    sweepAbortRef.current?.abort();
    const controller = new AbortController();
    sweepAbortRef.current = controller;

    // Sweep range, log-spaced. Sommerfeld ground stays at half resolution:
    // momwire 0.7.0's C++ fill + grid cache made warm sweeps fast (~30 ms
    // per point once the per-frequency grids are cached; measured 0.6 s for
    // 21 points at 2 threads), but the FIRST sweep after enabling it still
    // fills one grid per point (measured 4.3 s for 21 points at 2 threads;
    // 41 would be ~9 s) — half resolution halves that cold hit. Fast
    // (reflection-coefficient) ground and momwire PEC ground are cheap
    // enough for full resolution.
    //
    // Anchor + span come from the active example's sweep_policy. See
    // SweepPolicy in web/examples/_base.py for the meaning of the fields.
    // A variant can override the policy (e.g. a band-locked variant): prefer
    // the active variant's entry in variant_ui, falling back to the
    // design-level sweep_policy.
    const slowGround =
      backendSupportsGround(backend) &&
      groundEnabled &&
      groundModel === "sommerfeld";
    const N = slowGround ? 21 : 41;
    const policy =
      currentExample?.variant_ui?.[currentVariant]?.sweep_policy ??
      currentExample?.sweep_policy;
    // Anchor on the measurement frequency whenever the sweep should follow what
    // the user is *viewing*: multiband designs declare anchor="meas_freq", and
    // any design that's been unlocked from its design freq (to check the pattern
    // on another band) should sweep that band too — not stay pinned to the
    // design band. Locked single-resonance designs keep sweeping design_freq
    // (where measFreq == designFreq anyway).
    const sweepAnchor =
      !measLocked || policy?.anchor === "meas_freq" ? measFreq : designFreq;
    // Band-locked sweep: when the active band contains the anchor,
    // snap the sweep range to that band's [min_mhz, max_mhz] so the
    // trace stays inside the band the user is tuning instead of
    // bleeding into adjacent ones. Falls through to the multiplicative
    // window if the anchor sits outside every band.
    let fLo: number;
    let fHi: number;
    const bandLocked = policy?.band_locked
      ? currentBands.find(
          (b) => sweepAnchor >= b.min_mhz && sweepAnchor <= b.max_mhz,
        )
      : undefined;
    if (bandLocked) {
      fLo = bandLocked.min_mhz;
      fHi = bandLocked.max_mhz;
    } else {
      fLo = Math.max(0.5, sweepAnchor * (policy?.lo_factor ?? 0.8));
      fHi = Math.min(60, sweepAnchor * (policy?.hi_factor ?? 1.25));
    }
    const freqs = Array.from({ length: N }, (_, i) =>
      Math.exp(Math.log(fLo) + (i / (N - 1)) * (Math.log(fHi) - Math.log(fLo))),
    );

    const body = {
      ...buildRequest(),
      freqs_mhz: freqs,
      // Lane metadata (issue #382): issued-at generation (a newer knob drag
      // supersedes this batch server-side) + the gate's approval, which the
      // server requires for a warned batch (poor-match combo backstop).
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setSweepRunning(true);
    const acc: SweepData = {
      freqs_mhz: [],
      z_re: [],
      z_im: [],
      feeds_z_re: undefined,
      feeds_z_im: undefined,
    };
    try {
      const resp = await fetch("/sweep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`sweep failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const pt = JSON.parse(line);
          if (pt.done) continue;
          // A failed point/chunk ends the stream with {error} instead of
          // tearing the connection down (e.g. an approved poor-match combo
          // whose dense fill can't allocate). Keep whatever points landed.
          if (pt.error) {
            console.error("sweep error", pt.error);
            continue;
          }
          acc.freqs_mhz.push(pt.freq_mhz);
          acc.z_re.push(pt.z_re);
          acc.z_im.push(pt.z_im);
          // Multi-feed sweep records (bowtie) ship per-feed Z alongside
          // the primary. Allocate the per-feed buffers lazily on first
          // sight so single-feed sweeps stay on the original code path.
          if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
            if (!acc.feeds_z_re) acc.feeds_z_re = [];
            if (!acc.feeds_z_im) acc.feeds_z_im = [];
            acc.feeds_z_re.push(pt.feeds_z_re);
            acc.feeds_z_im.push(pt.feeds_z_im);
          }
          if (!controller.signal.aborted) {
            // New object so React re-renders the Smith chart per point.
            setSweep({
              freqs_mhz: acc.freqs_mhz.slice(),
              z_re: acc.z_re.slice(),
              z_im: acc.z_im.slice(),
              feeds_z_re: acc.feeds_z_re
                ? acc.feeds_z_re.map((row) => row.slice())
                : undefined,
              feeds_z_im: acc.feeds_z_im
                ? acc.feeds_z_im.map((row) => row.slice())
                : undefined,
            });
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("sweep error", e);
    } finally {
      if (sweepAbortRef.current === controller) {
        sweepAbortRef.current = null;
        setSweepRunning(false);
      }
    }
  }

  async function runConverge() {
    // Same as runSweep: the server lane serializes and prioritizes; only the
    // poor-match gate holds this back (effect re-fires on approval).
    if (solveWithheld()) return;
    convergeTimerRef.current = null;
    convergeAbortRef.current?.abort();
    const controller = new AbortController();
    convergeAbortRef.current = controller;

    // The active slot's nPerWire is irrelevant during a converge sweep —
    // n_values overrides it on the server. We strip `n_per_wire` from the
    // request anyway to make that explicit.
    const body = {
      ...buildRequest(),
      n_values: CONVERGE_N_VALUES,
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setConvergeRunning(true);
    const acc: ConvergeData = {
      n_values: [],
      z_re: [],
      z_im: [],
      z_re_extrap: null,
      z_im_extrap: null,
      feeds_z_re: undefined,
      feeds_z_im: undefined,
      feeds_z_re_extrap: undefined,
      feeds_z_im_extrap: undefined,
    };
    try {
      const resp = await fetch("/converge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`converge failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const pt = JSON.parse(line);
          if (pt.done) continue;
          // A solver failure for one N (rare — degenerate small-N geometry)
          // is reported by the backend as {n_per_wire, error}; skip rather
          // than poisoning the trajectory.
          if (pt.error) continue;
          acc.n_values.push(pt.n_per_wire);
          acc.z_re.push(pt.z_re);
          acc.z_im.push(pt.z_im);
          // Multi-feed convergence records ship per-feed Z alongside the
          // primary; allocate the buffers lazily on first sight.
          if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
            if (!acc.feeds_z_re) acc.feeds_z_re = [];
            if (!acc.feeds_z_im) acc.feeds_z_im = [];
            acc.feeds_z_re.push(pt.feeds_z_re);
            acc.feeds_z_im.push(pt.feeds_z_im);
          }
          const invN = acc.n_values.map((n) => 1 / n);
          acc.z_re_extrap = richardsonExtrap(invN, acc.z_re);
          acc.z_im_extrap = richardsonExtrap(invN, acc.z_im);
          // Per-feed Richardson Z*. Each feed's series is the column of
          // feeds_z_re / feeds_z_im at that feed index across all sampled
          // N values; richardsonExtrap returns null until ≥3 points are
          // in, so the diamonds light up the same time the primary one
          // does.
          if (acc.feeds_z_re && acc.feeds_z_im) {
            const nFeeds = acc.feeds_z_re[0].length;
            const feedsRe: (number | null)[] = [];
            const feedsIm: (number | null)[] = [];
            for (let fi = 0; fi < nFeeds; fi++) {
              const re = acc.feeds_z_re.map((row) => row[fi]);
              const im = acc.feeds_z_im.map((row) => row[fi]);
              feedsRe.push(richardsonExtrap(invN, re));
              feedsIm.push(richardsonExtrap(invN, im));
            }
            acc.feeds_z_re_extrap = feedsRe;
            acc.feeds_z_im_extrap = feedsIm;
          }
          if (!controller.signal.aborted) {
            setConverge({
              n_values: acc.n_values.slice(),
              z_re: acc.z_re.slice(),
              z_im: acc.z_im.slice(),
              z_re_extrap: acc.z_re_extrap,
              z_im_extrap: acc.z_im_extrap,
              feeds_z_re: acc.feeds_z_re
                ? acc.feeds_z_re.map((row) => row.slice())
                : undefined,
              feeds_z_im: acc.feeds_z_im
                ? acc.feeds_z_im.map((row) => row.slice())
                : undefined,
              feeds_z_re_extrap: acc.feeds_z_re_extrap
                ? acc.feeds_z_re_extrap.slice()
                : undefined,
              feeds_z_im_extrap: acc.feeds_z_im_extrap
                ? acc.feeds_z_im_extrap.slice()
                : undefined,
            });
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("converge error", e);
    } finally {
      if (convergeAbortRef.current === controller) {
        convergeAbortRef.current = null;
        setConvergeRunning(false);
      }
    }
  }

  async function runNormCheck() {
    // The pattern norm reuses the settled live solve (a server cache hit):
    // the lane's live-first priority guarantees that ordering now, no
    // client-side timing needed. Only the poor-match gate holds this back.
    if (solveWithheld()) return;
    normCheckTimerRef.current = null;
    normCheckAbortRef.current?.abort();
    const controller = new AbortController();
    normCheckAbortRef.current = controller;
    try {
      const resp = await fetch("/norm_check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...buildRequest(),
          _gen: seqRef.current,
          _approved: approvedComboRef.current,
        }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`norm check failed: ${resp.status}`);
      const data = await resp.json();
      if (controller.signal.aborted) return;
      if (!data.available) {
        setNormCheck(null);
        return;
      }
      const delta = 10 * Math.log10(data.pattern_norm / data.directivity_norm);
      setNormCheck({
        directivity_norm: data.directivity_norm,
        pattern_norm: data.pattern_norm,
        method: data.method,
        delta_db: delta,
        radiated_fraction: data.radiated_fraction ?? 0,
        radiation_efficiency: data.radiation_efficiency ?? 1,
      });
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("norm check error", e);
    } finally {
      if (normCheckAbortRef.current === controller) {
        normCheckAbortRef.current = null;
      }
    }
  }

  async function runPattern() {
    patternAbortRef.current?.abort();
    const controller = new AbortController();
    patternAbortRef.current = controller;
    try {
      const resp = await fetch("/pattern", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...buildRequest(), _gen: seqRef.current }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`pattern failed: ${resp.status}`);
      const data = await resp.json();
      if (!data.available) {
        setPattern(null);
        return;
      }
      if (!controller.signal.aborted) setPattern(data as PatternData);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("pattern error", e);
    } finally {
      if (patternAbortRef.current === controller) patternAbortRef.current = null;
    }
  }

  // Mirror the seq counters into `solving` state so the UI can react. Called
  // wherever the sent / received / cancel watermarks move. A solve reads as
  // running when more has been sent than received — unless everything
  // outstanding was cancelled (lastSentSeq hasn't advanced past the cancel
  // watermark), in which case the wait is over even though a doomed response
  // is still coming.
  function syncSolving() {
    setSolving(
      lastSentSeqRef.current > lastReceivedSeqRef.current &&
        lastSentSeqRef.current > canceledThroughSeqRef.current,
    );
  }

  // Busy-chrome reveal with two guards:
  //  - dwell: only show once a solve has been outstanding >BUSY_DWELL_MS. 1 s
  //    is the classic "flow of thought" threshold — below it users tolerate the
  //    wait without feedback; at/above it the bar reassures them it's working.
  //    A solve that finishes sooner clears the timer in cleanup, so the bar
  //    never flips on for quick updates.
  //  - min-visible: once shown, keep it up at least BUSY_MIN_VISIBLE_MS so a
  //    solve that lands just past the dwell can't make it sub-perceptibly
  //    flash.
  const BUSY_DWELL_MS = 1000;
  const BUSY_MIN_VISIBLE_MS = 400;
  useEffect(() => {
    if (solving) {
      const t = window.setTimeout(() => {
        shownAtRef.current = performance.now();
        setShowBusy(true);
      }, BUSY_DWELL_MS);
      return () => window.clearTimeout(t);
    }
    // Solve finished. If the bar never showed (fast solve), hide immediately;
    // otherwise hold it for the remainder of the minimum-visible window.
    if (shownAtRef.current === null) {
      setShowBusy(false);
      return;
    }
    const remaining =
      BUSY_MIN_VISIBLE_MS - (performance.now() - shownAtRef.current);
    if (remaining <= 0) {
      shownAtRef.current = null;
      setShowBusy(false);
      return;
    }
    const t = window.setTimeout(() => {
      shownAtRef.current = null;
      setShowBusy(false);
    }, remaining);
    return () => window.clearTimeout(t);
  }, [solving]);

  // The progress bar (`showBusy`) honors the min-visible window so it can't
  // flash, but the *dimming* and the "solving…" label mean "what you're
  // looking at is stale" — so they must clear the instant the result lands,
  // even while the bar lingers out its minimum. `solving` flips false
  // immediately on result-land, so `showBusy && solving` is exactly that: dim
  // only after the dwell (showBusy) AND while genuinely still solving.
  const stale = showBusy && solving;

  function requestSolve() {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Can't send now. onopen resends controlsRef.current on (re)connect, so
      // the latest state is solved as soon as the socket comes up.
      return;
    }
    // Trailing-edge rAF throttle: coalesce a burst of knob changes within one
    // animation frame to a single send of the latest controls. Bounds upload to
    // ≤~60 msg/s during a drag and keeps localhost message churn near what the
    // old one-in-flight gate produced; the server's latest-wins mailbox squashes
    // whatever still piles up. The freshest value always wins within the frame.
    if (solveRafRef.current !== null) return;
    solveRafRef.current = requestAnimationFrame(() => {
      solveRafRef.current = null;
      const sock = wsRef.current;
      if (!sock || sock.readyState !== WebSocket.OPEN) return;
      const seq = ++seqRef.current;
      lastSentSeqRef.current = seq;
      sentAtRef.current.set(seq, performance.now());
      sock.send(JSON.stringify({ ...controlsRef.current, _seq: seq }));
      // Keep the preview signature current so that toggling Live *off* right
      // after a solve doesn't see a stale signature and needlessly refetch the
      // wireframe / drop the just-solved result — the solved geometry already
      // matches these controls.
      previewSigRef.current = JSON.stringify(controlsRef.current);
      syncSolving();
    });
  }

  useEffect(() => {
    if (!active) return;
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    ws.onopen = () => {
      setStatus("open");
      // A prior socket's in-flight responses can never arrive on this new one.
      // Treat everything sent so far as received so `solving` can't stick true,
      // drop stale RTT timers, then send fresh current state. StrictMode and HMR
      // both tear the socket down + recreate it; the seq counters survive in
      // refs, so they must never rewind below what's already been received.
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      sentAtRef.current.clear();
      requestSolve();
    };
    ws.onclose = () => {
      setStatus("closed");
      // No solve can progress while disconnected — collapse the outstanding
      // count so the busy bar can't spin under a "closed" status (reconnect
      // re-arms it via onopen).
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      setSolving(false);
    };
    ws.onerror = () => {
      setStatus("closed");
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      setSolving(false);
    };
    ws.onmessage = (ev) => {
      const data: SolveResponse = JSON.parse(ev.data);
      const seq = data._seq ?? 0;
      // One socket delivers in order, and the server may skip-send superseded
      // results — so a higher `_seq` implicitly acknowledges every lower one.
      // Ignore a straggler/duplicate at or below the received watermark.
      if (seq <= lastReceivedSeqRef.current) {
        syncSolving();
        return;
      }
      lastReceivedSeqRef.current = seq;
      // RTT from this seq's send; prune every acked entry (≤ seq) from the map —
      // seqs skipped server-side never get their own response, so a single
      // higher-seq arrival clears the whole run of them.
      const sentAt = sentAtRef.current;
      const t0 = sentAt.get(seq);
      if (t0 !== undefined) setRttMs(performance.now() - t0);
      for (const k of sentAt.keys()) {
        if (k <= seq) sentAt.delete(k);
      }
      // Cancelled through this seq: the user bailed on it (and everything
      // before). The watermark advanced above so `solving` can clear; just drop
      // the result rather than rendering it.
      if (seq <= canceledThroughSeqRef.current) {
        syncSolving();
        return;
      }
      // Drop a response for an antenna the user already switched away from: a
      // slow in-flight solve for the previous selection must not stomp the new
      // antenna's geometry preview (and briefly show the wrong antenna).
      const staleGeom = !!data.geometry && data.geometry !== geometryRef.current;
      if (!staleGeom) {
        if (data.error) {
          // A solve that raised (e.g. a user design's build_wires) — show the
          // message and clear stale plot data rather than rendering an empty
          // result on top of the last antenna.
          setSolveError(data.error);
          setResult(null);
        } else {
          setSolveError(null);
          setResult(data);
        }
      }
      syncSolving();
    };
    return () => {
      if (solveRafRef.current !== null) {
        cancelAnimationFrame(solveRafRef.current);
        solveRafRef.current = null;
      }
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Hoisted JSX shared between the desktop tree below and the mobile tree
  // (Phase B). These close over the session's locals, so they are consts /
  // a closure rather than components — zero prop surface, identical DOM.
  // The moved blocks keep their original indentation so the refactor diff
  // shows them as pure moves.
  const controls = (
    <>
        <TabStrip />
        <div className="sidebar-header">
          <div className="brand">
            <h1>AntennaKNoBs</h1>
            <span className="byline">by KK7KNB</span>
          </div>
          <div className="header-actions">
            <div className="gear-menu-wrap">
              <button
                type="button"
                className="header-icon-btn"
                onClick={() => setGearMenuOpen((o) => !o)}
                title="Tools"
                aria-label="Tools menu"
                aria-haspopup="menu"
                aria-expanded={gearMenuOpen}
              >
                ⚙
              </button>
              {gearMenuOpen && (
                <>
                  <div
                    className="gear-menu-backdrop"
                    onClick={() => setGearMenuOpen(false)}
                  />
                  <div className="gear-menu" role="menu">
                    <button
                      type="button"
                      className="gear-menu-item"
                      role="menuitem"
                      onClick={copyParams}
                      title="Copy the current knob values as a paste-ready Python default_params block"
                    >
                      {copiedParams ? "Copied ✓" : "Copy params (Python)"}
                    </button>
                    <button
                      type="button"
                      className="gear-menu-item"
                      role="menuitem"
                      onClick={downloadNec}
                      title="Download this design as a NEC2 .nec card deck (for xnec2c, 4nec2, EZNEC, …)"
                    >
                      Download .nec deck
                    </button>
                    {/* Reactive copies of the chart-overlay toggles (same state
                        the overlays use, so the two locations can never
                        disagree). On mobile the checkbox overlays are not
                        rendered on the chart screens — small screens can't
                        spare the chart area — so this menu is the only place
                        to reach them there; on desktop it's a convenience
                        duplicate. */}
                    <div className="gear-menu-divider" />
                    {/* Mobile-layout only: it exists to reclaim the phone's
                        status/nav bars; on desktop F11 already does this and
                        the menu entry would be clutter. Also needs element
                        fullscreen (missing on iPhone Safari). */}
                    {isMobile && fullscreen.supported && (
                      <>
                        <div className="gear-menu-section">display</div>
                        <label
                          className="gear-menu-check"
                          title="Take over the whole screen — hides the system status and navigation bars. Uncheck (or use the back gesture) to exit."
                        >
                          <input
                            type="checkbox"
                            checked={fullscreen.active}
                            onChange={fullscreen.toggle}
                          />
                          full screen
                        </label>
                      </>
                    )}
                    <div className="gear-menu-section">antenna chart</div>
                    <label
                      className="gear-menu-check"
                      title="Color wire segments by current magnitude; modulate wire width"
                    >
                      <input
                        type="checkbox"
                        checked={showHeatmap}
                        onChange={(e) => setShowHeatmap(e.target.checked)}
                      />
                      heatmapped currents
                    </label>
                    <label
                      className="gear-menu-check"
                      title="Draw the |I| envelope curve along each wire"
                    >
                      <input
                        type="checkbox"
                        checked={showEnvelope}
                        onChange={(e) => setShowEnvelope(e.target.checked)}
                      />
                      current waveforms
                    </label>
                    <label
                      className="gear-menu-check"
                      title="Draw the per-wire labels (off to declutter dense geometries)"
                    >
                      <input
                        type="checkbox"
                        checked={showWireLabels}
                        onChange={(e) => setShowWireLabels(e.target.checked)}
                      />
                      wire labels
                    </label>
                    <label
                      className="gear-menu-check"
                      title="Draw the 'feed' name beside each feedpoint marker"
                    >
                      <input
                        type="checkbox"
                        checked={showFeedNames}
                        onChange={(e) => setShowFeedNames(e.target.checked)}
                      />
                      feed labels
                    </label>
                    <div className="gear-menu-section">smith chart</div>
                    <label
                      className="gear-menu-check"
                      title="Sweep Z across measurement freq and plot the locus on the Smith chart"
                    >
                      <input
                        type="checkbox"
                        checked={sweepEnabled}
                        onChange={(e) => setSweepEnabled(e.target.checked)}
                      />
                      freq sweep
                    </label>
                    <label
                      className="gear-menu-check"
                      title={`Re-solve at N = ${CONVERGE_N_VALUES.join(", ")} segments/wire and Richardson-extrapolate Z to N→∞`}
                    >
                      <input
                        type="checkbox"
                        checked={convergeEnabled}
                        onChange={(e) => setConvergeEnabled(e.target.checked)}
                      />
                      converge sweep
                    </label>
                    <div className="gear-menu-section">azimuth / elevation</div>
                    <label
                      className="gear-menu-check"
                      title="On dwell, renormalise the pattern by its own integrated radiated power (dotted) instead of the input power the solid line uses. Overlap ⇒ the solve conserves power; a visible gap is the solver's discretisation error (NEC's 'average gain' check)."
                    >
                      <input
                        type="checkbox"
                        checked={normCheckEnabled}
                        onChange={(e) => setNormCheckEnabled(e.target.checked)}
                      />
                      norm check
                    </label>
                  </div>
                </>
              )}
            </div>
            <button
              type="button"
              className="theme-toggle"
              onClick={() => applyTheme(theme === "dark" ? "light" : "dark")}
              title="Toggle light / dark theme"
              aria-label="Toggle light / dark theme"
            >
              {theme === "dark" ? "☀" : "☾"}
            </button>
          </div>
        </div>

        <div className="antenna-row">
          <GeometryCombobox
            groups={geomGroups}
            selected={geometry}
            currentLabel={currentExample?.label ?? ""}
            filter={geomFilter}
            setFilter={setGeomFilter}
            onSelect={setGeometry}
          />
          {currentExample && currentExample.variants.length > 1 && (
            <select
              id="variant-select"
              className="geometry-select variant-select"
              value={currentVariant}
              onChange={(e) => selectVariant(e.target.value)}
              aria-label="variant"
              title="variant"
            >
              {currentExample.variants.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          )}
        </div>
        {currentExample?.notes && (
          <div className="design-note">{currentExample.notes}</div>
        )}
        {examplesError && (
          <div className="examples-error">
            Failed to load /examples: {examplesError}
          </div>
        )}
        {loadErrors.some((e) => e.trust_required) && (
          <AwaitingTrustPanel
            designs={loadErrors.filter((e) => e.trust_required)}
            busy={trustBusy}
            onTrust={trustDesign}
          />
        )}
        {loadErrors.some((e) => !e.trust_required) && (
          <div className="design-load-errors" role="alert">
            {(() => {
              const errs = loadErrors.filter((e) => !e.trust_required);
              return (
                <>
                  <div className="design-load-errors-title">
                    {errs.length} design{errs.length === 1 ? "" : "s"} failed to
                    load
                  </div>
                  <ul>
                    {errs.map((err) => (
                      <li key={err.name}>
                        <code>{err.name}</code> — {err.message}
                        <span className="design-load-errors-file">
                          {err.file}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <div className="design-load-errors-hint">
                    Fix the file and refresh. See CLAUDE.md in your designs
                    folder.
                  </div>
                </>
              );
            })()}
          </div>
        )}


        {currentExample && (
          <div
            className="param-grid is-knobs"
            style={
              currentExample.layout?.columns
                ? { gridTemplateColumns: `repeat(${currentExample.layout.columns}, minmax(0, 1fr))` }
                : undefined
            }
          >
            <ParamForm
              schema={currentSchema}
              values={currentValues}
              onChange={handleUserParamChange}
              // hexbeam_5band's daisy_chain mode emits NEC TL cards;
              // momwire engines reject any non-empty build_tls() so the
              // toggle has no effect there. Grey it out when the active
              // slot's backend is momwire — the request-build side also
              // forces daisy_chain=false so a stale value doesn't slip
              // through.
              disabledFields={
                backend !== "pynec" ? new Set(["daisy_chain"]) : undefined
              }
              // Per-knob optimiser hooks: effective min/max/step come from the
              // knob's menu settings (overriding schema), and right-click opens
              // that menu.
              opt={{
                settings: knobOpt[geometry] ?? {},
                onContext: (name, e) => {
                  e.preventDefault();
                  setKnobMenu({ name, x: e.clientX, y: e.clientY });
                },
                onToggleVary: (name) =>
                  updateKnobOpt(name, { vary: !knobOptFor(name).vary }),
              }}
            />
          </div>
        )}

        {currentBands.length > 0 && currentExample?.has_design_freq && (() => {
          // Highlight the band whose window contains the current
          // designFreq — same behaviour as the meas-freq row below.
          // The slider min/max also tracks that band, so sliding past
          // its edge auto-re-anchors to the neighbouring band.
          // Gated on has_design_freq so the row is hidden for
          // hand-tuned absolute designs where the slider would do
          // nothing.
          const activeKey = bandContaining(designFreq);
          const active = currentBands.find((b) => b.key === activeKey) ?? currentBands[0];
          return (
            <div className="field">
              <label>
                <span>design freq</span>
                <span>{designFreq.toFixed(3)} MHz</span>
              </label>
              <div className="band-row">
                <BandDropdown
                  bands={currentBands}
                  value={active.key}
                  onSelect={selectBand}
                  ariaLabel="band"
                />
                <input
                  type="range"
                  min={active.min_mhz}
                  max={active.max_mhz}
                  step={0.005}
                  value={designFreq}
                  onInput={(e) =>
                    updateDesignFreq(Number((e.target as HTMLInputElement).value))
                  }
                />
              </div>
            </div>
          );
        })()}

        {/* Per-knob optimiser menu (right-click a knob): vary toggle + extents +
            turn step. Position-fixed at the click point. */}
        {knobMenu &&
          currentExample &&
          (() => {
            const name = knobMenu.name;
            const ko = knobOptFor(name);
            const s = currentSchema.find(
              (x): x is SchemaParamSpec => !isGroup(x) && x.name === name,
            );
            const num = (v: number) => (Number.isFinite(v) ? v : 0);
            const set = (patch: Partial<KnobOpt>) => updateKnobOpt(name, patch);
            return (
              <>
                <div
                  className="knob-menu-backdrop"
                  onClick={() => setKnobMenu(null)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setKnobMenu(null);
                  }}
                />
                <div
                  className="knob-menu"
                  style={{ left: knobMenu.x, top: knobMenu.y }}
                  onContextMenu={(e) => e.preventDefault()}
                >
                  <div className="knob-menu-title">{s?.label ?? name}</div>
                  <label className="knob-menu-vary">
                    <input
                      type="checkbox"
                      checked={ko.vary}
                      onChange={(e) => set({ vary: e.target.checked })}
                    />
                    Optimize this knob
                    <kbd
                      className="knob-menu-kbd"
                      title="Focus a knob and press O to toggle"
                    >
                      O
                    </kbd>
                  </label>
                  <div className="knob-menu-row">
                    <span>Optimize range</span>
                    <KnobMenuNumber
                      value={num(ko.optMin)}
                      onChange={(v) => set({ optMin: v })}
                    />
                    <KnobMenuNumber
                      value={num(ko.optMax)}
                      onChange={(v) => set({ optMax: v })}
                    />
                  </div>
                  <div className="knob-menu-row">
                    <span>Display range</span>
                    <KnobMenuNumber
                      value={num(ko.dispMin)}
                      onChange={(v) => set({ dispMin: v })}
                    />
                    <KnobMenuNumber
                      value={num(ko.dispMax)}
                      onChange={(v) => set({ dispMax: v })}
                    />
                  </div>
                  <div className="knob-menu-row">
                    <span>Turn step</span>
                    <KnobMenuNumber
                      value={num(ko.step)}
                      onChange={(v) => set({ step: v })}
                    />
                  </div>
                </div>
              </>
            );
          })()}

        {/* Measurement freq = the rig's tuning control: a weighted VFO dial +
            frequency-counter readout. Top line: band select + the LCD. Below:
            the Live/Optimize toggles stacked at the left of the dial, with the
            lock pinned to the dial's lower-right corner ("lock to design freq"
            disables the dial). */}
        <h2 className="group-label">measurement freq</h2>
        <div className={`field vfo-field${measLocked ? " is-locked" : ""}`}>
          <div className="vfo-top">
            {currentBands.length > 0 && (
              <BandDropdown
                bands={currentBands}
                // Locked: mirror the design band (measFreq tracks designFreq).
                // Unlocked: the persistent selection, stable as the dial roams.
                value={
                  measLocked
                    ? bandContaining(measFreq) ?? currentBands[0].key
                    : measBand || currentBands[0].key
                }
                onSelect={selectMeasBand}
                disabled={measLocked}
                ariaLabel="measurement band"
              />
            )}
            <div className="freq-lcd" title={`${measFreq.toFixed(3)} MHz`}>
              <span className="lcd-digits">
                <span className="lcd-ghost">
                  {measFreq.toFixed(3).replace(/\d/g, "8")}
                </span>
                <span className="lcd-live">{measFreq.toFixed(3)}</span>
              </span>
              <span className="lcd-unit">MHz</span>
            </div>
          </div>

          <div className="vfo-body">
            {/* Live / Optimize: two matching push-button toggles (depressed =
                on), stacked at the left of the dial. Live gates auto-solving on
                knob turns; Optimize gates the reactive tuner. The objective
                ("optimise for") picker is the gear next to Optimize. */}
            <div className="sim-controls">
              <button
                type="button"
                className={`toggle-btn${autoSim ? " is-on" : ""}`}
                aria-pressed={autoSim}
                onClick={() => setAutoSim((v) => !v)}
                title={
                  autoSim
                    ? "Live: knob changes re-solve automatically. Click to pause and edit without solving."
                    : "Paused: edit the design freely; the engine is held. Click to resume and solve."
                }
              >
                <span className="toggle-led" aria-hidden="true" />
                {autoSim ? "Live" : "Paused"}
              </button>
              <div className="opt-cell">
                <button
                  type="button"
                  className={`toggle-btn opt-toggle${optEnabled ? " is-on" : ""}`}
                  aria-pressed={optEnabled}
                  onClick={() => {
                    setOptEnabled((v) => !v);
                    setOptPausedBy(null);
                  }}
                  title="Reactive optimiser: vary the knobs you mark (right-click a knob) to hit the objective whenever a fixed knob changes. Changing a marked knob by hand pauses it — turn it back on to resume."
                >
                  <span className="toggle-led" aria-hidden="true" />
                  Optimize
                  {optRunning ? <span className="opt-pip">●</span> : null}
                </button>
                <button
                  type="button"
                  className="opt-gear-btn"
                  aria-label="Optimisation method"
                  aria-haspopup="menu"
                  aria-expanded={optMenuOpen}
                  title={`Optimise for: ${OPT_OBJECTIVE_LABELS[optObjective]}`}
                  onClick={() => setOptMenuOpen((o) => !o)}
                >
                  ⚙
                </button>
                {optMenuOpen && (
                  <>
                    <div
                      className="gear-menu-backdrop"
                      onClick={() => setOptMenuOpen(false)}
                    />
                    <div className="opt-menu" role="menu">
                      <div className="opt-menu-title">Optimise for</div>
                      {OPT_OBJECTIVES.map((k) => (
                        <button
                          key={k}
                          type="button"
                          role="menuitemradio"
                          aria-checked={optObjective === k}
                          className={`gear-menu-item${optObjective === k ? " is-active" : ""}`}
                          onClick={() => {
                            setOptObjective(k);
                            setOptMenuOpen(false);
                          }}
                        >
                          {OPT_OBJECTIVE_LABELS[k]}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              {optEnabled && optResult && (
                <span className="opt-readout" title="SWR after optimisation">
                  SWR {optResult.metrics_after.swr.toFixed(2)}
                </span>
              )}
              {optEnabled && optError && (
                <span
                  className="opt-readout opt-readout-err"
                  title={optError}
                >
                  {optError}
                </span>
              )}
              {!optEnabled && optPausedBy && (
                <span
                  className="opt-readout opt-paused"
                  title={
                    optPausedBy.kind === "knob"
                      ? "You changed a knob marked for optimization, so Optimize paused. Turn it back on to resume."
                      : "Loading a design clears its optimize marks and pauses Optimize. Re-mark knobs and turn it back on to resume."
                  }
                >
                  {optPausedBy.kind === "knob"
                    ? `Paused — changing ${optPausedBy.name} by hand`
                    : "Paused — loaded a new design"}
                </span>
              )}
            </div>

            <div className="vfo-dial">
              <Knob
                knobId="meas_freq"
                variant="vfo"
                value={measFreq}
                min={
                  currentExample?.meas_freq_range_mhz
                    ? currentExample.meas_freq_range_mhz[0]
                    : Math.max(0.5, measBandAnchor * 0.8)
                }
                max={
                  currentExample?.meas_freq_range_mhz
                    ? currentExample.meas_freq_range_mhz[1]
                    : Math.min(60, measBandAnchor * 1.25)
                }
                step={0.005}
                precision={3}
                unit=" MHz"
                label="measurement frequency"
                onChange={setMeasFreq}
                disabled={measLocked}
              />
              {/* No design frequency → nothing to lock to; the button would
                  only re-disable the one meaningful control (issue #390). */}
              {measLockable && (
                <button
                  type="button"
                  className="vfo-lock"
                  aria-pressed={linkMeas}
                  aria-label="Lock measurement frequency to the design frequency"
                  title={
                    linkMeas
                      ? "Locked to the design frequency — the dial is fixed. Click to unlock and tune freely."
                      : "Lock the measurement frequency to the design frequency."
                  }
                  onClick={() => toggleLink(!linkMeas)}
                >
                  <svg className="lock-glyph" viewBox="0 0 16 16" aria-hidden="true">
                    <rect x="3.5" y="7.2" width="9" height="6.3" rx="1.3" />
                    <path className="shackle" d="M5.3 7.2V5a2.7 2.7 0 0 1 5.4 0v2.2" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>

        <h2 className="group-label">simulation</h2>

        <div className="field">
          <label>
            <span>solver slot</span>
            <span>{backendDisplayLabel(backend, currentOpts)} · N={nPerWire}</span>
          </label>
          <div className="backend-tabs" role="tablist">
            {SLOT_ORDER.map((s) => {
              const cfg = slots[s];
              return (
                <div key={s} className="backend-tab-cell">
                  <button
                    role="tab"
                    aria-selected={activeSlot === s}
                    aria-label={`Solver slot ${s}: ${backendDisplayLabel(cfg.backend, cfg.opts)}, N=${cfg.opts.nPerWire}`}
                    className={`backend-tab-btn ${activeSlot === s ? "active" : ""}`}
                    title={`${backendDisplayLabel(cfg.backend, cfg.opts)}, N=${cfg.opts.nPerWire}`}
                    onClick={() => setActiveSlot(s)}
                  >
                    <span className="slot-letter">{s}</span>
                    <span className="slot-sub">{backendDisplayLabel(cfg.backend, cfg.opts)}</span>
                  </button>
                  <button
                    className="backend-gear-btn"
                    title={`Slot ${s} options`}
                    aria-label={`Slot ${s} options`}
                    onClick={() => setGearOpen(s)}
                  >
                    ⚙
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {!backendSupportsGround(backend) && groundEnabled && (
          <div className="field" title="This backend doesn't model ground; ignored until you switch to one that does.">
            <em style={{ color: "var(--muted)", fontSize: "var(--text-sm)" }}>
              ground plane ignored for {BACKEND_LABEL[backend]}
            </em>
          </div>
        )}

        <div className="field">
          <label
            className="link-toggle"
            title="Ground plane at z=0; pick the ground model below"
          >
            <input
              type="checkbox"
              checked={groundEnabled}
              disabled={!backendSupportsGround(backend)}
              onChange={(e) => setGroundEnabled(e.target.checked)}
            />
            ground plane
          </label>
          {backendSupportsGround(backend) && groundEnabled && (
            <>
              <div role="radiogroup" aria-label="Ground type">
                {(
                  [
                    [
                      "finite",
                      "finite (εr=10, σ=0.002 S/m)",
                      "Finite ground — pick the solve method below (Sommerfeld-Norton or the reflection-coefficient approximation).",
                    ],
                    [
                      "pec",
                      "PEC",
                      backend === "pynec"
                        ? "Perfectly conducting ground (image method, NEC ITYPE=1) — matches every backend's model='PEC' for apples-to-apples engine comparison."
                        : "Perfectly conducting ground (image method) — matches PyNEC's PEC model for apples-to-apples engine comparison.",
                    ],
                  ] as [GroundType, string, string][]
                ).map(([value, label, title]) => (
                  <label key={value} className="link-toggle" title={title}>
                    <input
                      type="radio"
                      name="ground-type"
                      checked={groundType === value}
                      onChange={() => setGroundType(value)}
                    />
                    {label}
                  </label>
                ))}
              </div>
              {groundType === "finite" && (
                  <div
                    role="radiogroup"
                    aria-label="Finite-ground solve method"
                    style={{ marginLeft: "1.2em" }}
                  >
                    {(
                      [
                        [
                          "fast",
                          "refl-coef (fast)",
                          backend === "pynec"
                            ? "Reflection-coefficient approximation (NEC ITYPE=0), the default. ~2x faster per solve; impedance degrades below ~0.1λ height."
                            : "Reflection-coefficient model, the default. Fast; matches Sommerfeld above ~0.1λ heights.",
                        ],
                        [
                          "sommerfeld",
                          "Sommerfeld",
                          backend === "pynec"
                            ? "Sommerfeld-Norton (NEC ITYPE=2) — most accurate, slowest; the impedance sweep drops to half resolution to compensate."
                            : "True Sommerfeld ground — accurate at any height, on every momwire solver including the fast array paths (momwire ≥ 0.8.0). First solve at each frequency builds a grid (seconds); repeats are fast. The impedance sweep runs at half resolution.",
                        ],
                      ] as [FiniteGroundMethod, string, string][]
                    ).map(([value, label, title]) => (
                      <label key={value} className="link-toggle" title={title}>
                        <input
                          type="radio"
                          name="ground-method"
                          checked={finiteGroundMethod === value}
                          onChange={() => setFiniteGroundMethod(value)}
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                )}
            </>
          )}
        </div>

        {gearOpen && (
          <BackendConfigModal
            slot={gearOpen}
            backend={slots[gearOpen].backend}
            opts={slots[gearOpen].opts}
            onChangeBackend={(b) => {
              backendTouchedRef.current = true;
              setSlotBackend(gearOpen, b);
            }}
            onPatch={(patch) => updateSlotOpts(gearOpen, patch)}
            onReset={() => resetSlot(gearOpen)}
            onClose={() => setGearOpen(null)}
          />
        )}
    </>
  );

  const solveOverlays = (
    <>
        {/* Indeterminate progress bar: appears once a solve outlasts the dwell
            and lingers out its min-visible window (showBusy), so it never
            flashes — the dim/label (stale) clear earlier, when the result lands. */}
        <div className={`solve-bar${showBusy ? " active" : ""}`} aria-hidden />
        {showBusy && solving && (
          <button
            type="button"
            className="solve-cancel"
            onClick={cancelSolve}
            title="Stop waiting for this solve (the server still finishes it)"
          >
            Cancel solve
          </button>
        )}
        {solverWarning && (
          <div
            className="solver-suggest"
            role="alertdialog"
            aria-label="Solver mismatch"
          >
            <span className="solver-suggest-title">
              {BACKEND_LABEL[backend]} is a poor match for this design
            </span>
            <span className="solver-suggest-sub">
              {recommendedBackend === "sinusoidal"
                ? "This mesh is benchmark-sized — B-spline-family solvers take minutes per solve here (and concurrent solves can exhaust memory). The sinusoidal solver or PyNEC answers in seconds. "
                : backend === "arrayblock" || backend === "hmatrix"
                  ? "This accelerator is overkill on a single-element design — a dense solver (e.g. B-spline) is faster here. "
                  : "This is a large array — a dense solver can be very slow. Array-block is far faster. "}
              Change the solver in the gear menu, solve anyway, or pause to keep
              editing.
            </span>
            <div className="solver-suggest-actions">
              <button
                type="button"
                className="solver-suggest-primary"
                onClick={solveAnyway}
              >
                Solve anyway
              </button>
              <button
                type="button"
                className="solver-suggest-secondary"
                onClick={pauseSimulation}
                title="Stop auto-solving so you can keep editing; click Live to resume."
              >
                Pause simulation
              </button>
            </div>
          </div>
        )}
        {solveError && (
          <div className="solve-error" role="alert">
            <span className="solve-error-title">This design failed to solve</span>
            <code className="solve-error-message">{solveError}</code>
            <span className="solve-error-hint">
              Fix the design and adjust a control to retry. For user designs see
              CLAUDE.md in your designs folder.
            </span>
          </div>
        )}
    </>
  );

  // One output view: the per-view overlays plus the main <ViewPanel>. A
  // closure (not a component) so the ~30 captured locals need no props. The
  // solve-readout HUD stays OUT of it — mobile chart screens must not
  // inherit the floating readout.
  const renderOutput = (v: View, size: number, fill: boolean) => (
    <>
          {v === "antenna" && (
            <div className="antenna-overlay">
              <div className="projection-toggle">
                {PROJECTIONS.map((p) => (
                  <button
                    key={p.id}
                    className={p.id === cameraProjection ? "active" : ""}
                    onClick={() => setCameraProjection(p.id)}
                    title={`Project onto the ${p.id} plane`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              {/* Mobile drops the checkbox column — it doesn't scale with the
                  chart and covers it on a phone. The same toggles live in the
                  sidebar gear menu (shared state). The projection toggle above
                  stays: it's compact and it's how you turn the view. */}
              {!isMobile && (
                <>
                  <label
                    className="overlay-checkbox"
                    title="Color wire segments by current magnitude; modulate wire width"
                  >
                    <input
                      type="checkbox"
                      checked={showHeatmap}
                      onChange={(e) => setShowHeatmap(e.target.checked)}
                    />
                    heatmapped currents
                  </label>
                  <label
                    className="overlay-checkbox"
                    title="Draw the |I| envelope curve along each wire"
                  >
                    <input
                      type="checkbox"
                      checked={showEnvelope}
                      onChange={(e) => setShowEnvelope(e.target.checked)}
                    />
                    current waveforms
                  </label>
                  <label
                    className="overlay-checkbox"
                    title="Draw the per-wire labels (off to declutter dense geometries)"
                  >
                    <input
                      type="checkbox"
                      checked={showWireLabels}
                      onChange={(e) => setShowWireLabels(e.target.checked)}
                    />
                    wire labels
                  </label>
                  <label
                    className="overlay-checkbox"
                    title="Draw the 'feed' name beside each feedpoint marker"
                  >
                    <input
                      type="checkbox"
                      checked={showFeedNames}
                      onChange={(e) => setShowFeedNames(e.target.checked)}
                    />
                    feed labels
                  </label>
                </>
              )}
            </div>
          )}
          {/* Both smith-overlay children are checkboxes — nothing to keep on
              mobile (the toggles live in the gear menu there). */}
          {v === "smith" && !isMobile && (
            <div className="smith-overlay">
              <label
                className="overlay-checkbox"
                title="Sweep Z across measurement freq and plot the locus on the Smith chart"
              >
                <input
                  type="checkbox"
                  checked={sweepEnabled}
                  onChange={(e) => setSweepEnabled(e.target.checked)}
                />
                freq sweep
              </label>
              <label
                className="overlay-checkbox"
                title={`Re-solve at N = ${CONVERGE_N_VALUES.join(", ")} segments/wire and Richardson-extrapolate Z to N→∞`}
              >
                <input
                  type="checkbox"
                  checked={convergeEnabled}
                  onChange={(e) => setConvergeEnabled(e.target.checked)}
                />
                converge sweep
              </label>
            </div>
          )}
          {/* On mobile only the Δ readout survives (it's output, not a
              control, and it's one short span); the norm-check toggle lives in
              the gear menu. The container is skipped entirely when it would
              be empty. */}
          {(v === "azimuth" || v === "elevation") &&
            (!isMobile || (normCheckEnabled && normCheck)) && (
            <div className="farfield-overlay">
              {!isMobile && (
                <label
                  className="overlay-checkbox"
                  title="On dwell, renormalise the pattern by its own integrated radiated power (dotted) instead of the input power the solid line uses. Overlap ⇒ the solve conserves power; a visible gap is the solver's discretisation error (NEC's 'average gain' check)."
                >
                  <input
                    type="checkbox"
                    checked={normCheckEnabled}
                    onChange={(e) => setNormCheckEnabled(e.target.checked)}
                  />
                  norm check
                </label>
              )}
              {/* Over a finite ground the norm gap IS physics (structural
                  loss + real ground absorption), so show it in its honest
                  form — the radiated fraction, same number as the Info-pane
                  row. Free space / PEC keeps the raw Δ dB, where it is a
                  pure solver power-balance diagnostic. */}
              {normCheckEnabled && normCheck && (
                <span
                  className="overlay-readout"
                  title={
                    normCheck.method.startsWith("grid_")
                      ? `P_radiated/P_input from the pattern-integral norm (${normCheck.method}): the gap between the solid and dotted lobes as a fraction — structural loss plus real ground absorption (Δ ${normCheck.delta_db >= 0 ? "+" : ""}${normCheck.delta_db.toFixed(3)} dB, NEC average-gain style)`
                      : `input-power norm vs pattern-integral norm (${normCheck.method}); 0 dB = perfect power balance`
                  }
                >
                  {normCheck.method.startsWith("grid_") ? (
                    <>radiated {(normCheck.radiated_fraction * 100).toFixed(0)}%</>
                  ) : (
                    <>
                      Δ {normCheck.delta_db >= 0 ? "+" : ""}
                      {normCheck.delta_db.toFixed(3)} dB
                    </>
                  )}
                </span>
              )}
            </div>
          )}
          {/* The cut-angle knob lives on the plot it drives: the azimuth
              (xy) cut is taken at elevation azElevDeg; the elevation (yz) cut
              is taken at azimuth bearing elevAzDeg. CCW dials from 3 o'clock. */}
          {v === "azimuth" && (
            <div
              className="cut-overlay"
              title="elevation at which this azimuth cut is taken"
            >
              <span className="cut-overlay-label">elevation</span>
              <Knob
                knobId="ff_cut_elevation"
                value={azElevDeg}
                min={0}
                max={89}
                step={1}
                precision={0}
                unit="°"
                label="cut elevation"
                onChange={setAzElevDeg}
                startDeg={90}
                sweepDeg={-89}
              />
              <span className="cut-overlay-value">{azElevDeg}°</span>
            </div>
          )}
          {v === "elevation" && (
            <div
              className="cut-overlay"
              title="azimuth bearing at which this elevation cut is taken"
            >
              <span className="cut-overlay-label">azimuth</span>
              <Knob
                knobId="ff_cut_azimuth"
                value={elevAzDeg}
                min={0}
                max={359}
                step={1}
                precision={0}
                unit="°"
                label="cut azimuth"
                onChange={setElevAzDeg}
                startDeg={90}
                sweepDeg={-359}
              />
              <span className="cut-overlay-value">{elevAzDeg}°</span>
            </div>
          )}
          {(v === "azimuth" || v === "elevation") && (
            <div className="compare-overlay">
              <button
                type="button"
                className="pin-btn"
                onClick={() => {
                  pinCurrentPattern();
                  // Pinning always reveals the table so the new row is seen;
                  // it stays open until minimized (no auto-collapse timer).
                  setCompareCollapsed(false);
                }}
                disabled={!result}
                title="Pin the current pattern as a ghost overlay, to compare another antenna or tuning against it"
              >
                📌 Pin pattern
              </button>
              {pinnedPatterns.length > 0 &&
                (compareCollapsed ? (
                  <button
                    type="button"
                    className="pin-btn pin-chip"
                    onClick={() => setCompareCollapsed(false)}
                    title="Show the pinned-pattern comparison table"
                  >
                    {pinnedPatterns.length} pinned ▾
                  </button>
                ) : (
                  <>
                    <div className="pin-table-actions">
                      <button
                        type="button"
                        className="pin-clear"
                        onClick={clearPins}
                        title="Remove all pinned patterns"
                      >
                        clear
                      </button>
                      <button
                        type="button"
                        className="pin-clear"
                        onClick={() => setCompareCollapsed(true)}
                        title="Minimize the comparison table (pins and ghost overlays are kept)"
                      >
                        –
                      </button>
                    </div>
                    <PatternCompareTable
                      live={liveMetrics}
                      liveLabel={`${currentExample?.label ?? geometry} @ ${measFreq.toFixed(2)} MHz`}
                      pinned={pinnedPatterns}
                      onRemove={removePin}
                      onToggle={togglePin}
                    />
                  </>
                ))}
            </div>
          )}
          <ViewPanel
            view={v}
            size={size}
            fill={fill}
            result={result}
            preview={preview}
            sweep={sweep}
            converge={converge}
            pattern={pattern}
            pinnedPatterns={pinnedPatterns}
            measFreqMhz={measFreq}
            sweepRunning={sweepRunning}
            convergeRunning={convergeRunning}
            azElevDeg={azElevDeg}
            elevAzDeg={elevAzDeg}
            cameraProjection={cameraProjection}
            showHeatmap={showHeatmap}
            showEnvelope={showEnvelope}
            showWireLabels={showWireLabels}
            showFeedNames={showFeedNames}
            multiFeed={effectiveMultiFeed}
            fineNorm={normCheck?.pattern_norm ?? null}
          />
    </>
  );

  // Mobile: knobs pane + a 5-screen scroll-snap output carousel, instead of
  // the desktop thumbstrip/HUD stage. A distinct tree (not CSS-hiding the
  // desktop one) keeps both layouts honest; the shared pieces are exactly the
  // hoisted consts above. All hooks already ran, so branching here is safe.
  if (isMobile) {
    return (
      <div className="app app-mobile">
        <aside className="sidebar mobile-knobs">{controls}</aside>
        <section
          className="mobile-output"
          ref={mobRef}
          aria-label="Antenna output views"
        >
          {solveOverlays}
          <div
            className={`mobile-carousel${stale ? " stale" : ""}`}
            ref={mobileCarouselRef}
            onScroll={onMobileCarouselScroll}
          >
            {MOBILE_SCREENS.map((s) => (
              <div
                key={s.id}
                className={`mobile-screen${s.id === "info" ? " mobile-screen-info" : ""}`}
              >
                {s.id === "info" ? (
                  <>
                    <SolveReadout
                      className="mobile-readout"
                      result={result}
                      rttMs={rttMs}
                      currentExample={currentExample}
                      effectiveMultiFeed={effectiveMultiFeed}
                      normCheck={normCheck}
                      normCheckEnabled={normCheckEnabled}
                    />
                    {/* The ws status lives HERE, not floating over the
                        carousel — on a phone the desktop-style absolute
                        bottom-right .status covered chart content. Inside
                        the Info screen it's a normal flow row. */}
                    <div className="status">
                      ws: {status}
                      {stale && (
                        <span className="status-busy"> · solving…</span>
                      )}
                    </div>
                  </>
                ) : (
                  renderOutput(s.id as View, mobChartSize, s.id === "antenna")
                )}
              </div>
            ))}
          </div>
          <div className="mobile-dots" aria-label="Output screens">
            {MOBILE_SCREENS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                className={i === mobileIndex ? "active" : ""}
                aria-label={`Show ${s.label}`}
                title={s.label}
                onClick={() => goToMobileScreen(i)}
              />
            ))}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">{controls}</aside>

      <main className="stage" aria-label="Antenna output views">
        {solveOverlays}
        <div className="thumbstrip" ref={thumbStripRef}>
          {VIEWS.filter((v) => v.id !== view).map((v) => (
            <button
              key={v.id}
              className="thumb"
              onClick={() => setView(v.id)}
              title={`Switch to ${v.label}`}
            >
              <div
                className="thumb-canvas"
                style={{ width: thumbSize, height: thumbSize }}
              >
                <ViewPanel
                  view={v.id}
                  size={thumbSize}
                  fill={false}
                  result={result}
                  preview={preview}
                  sweep={sweep}
                  converge={converge}
                  pattern={pattern}
                  pinnedPatterns={[]}
                  measFreqMhz={measFreq}
                  sweepRunning={sweepRunning}
                  convergeRunning={convergeRunning}
                  azElevDeg={azElevDeg}
                  elevAzDeg={elevAzDeg}
                  cameraProjection={cameraProjection}
                  showHeatmap={showHeatmap}
                  showEnvelope={showEnvelope}
                  multiFeed={effectiveMultiFeed}
                />
              </div>
              <div className="thumb-label">{v.label}</div>
            </button>
          ))}
        </div>
        <div
          className={`carousel-slide${stale ? " stale" : ""}`}
          ref={slideRef}
        >
          {renderOutput(view, chartSize, view === "antenna")}
          {/* Solve readout, pinned to the lower-left of whichever view the
              carousel is centered on. Floats over the canvas as a HUD so the
              left input rail stays inputs-only. It sits INSIDE the slide, so
              the slide's stale dim already covers it — no own stale class, or
              the two opacities would compound. */}
          <SolveReadout
            className="stage-readout"
            result={result}
            rttMs={rttMs}
            currentExample={currentExample}
            effectiveMultiFeed={effectiveMultiFeed}
            normCheck={normCheck}
            normCheckEnabled={normCheckEnabled}
          />
        </div>
        <div className="status">
          ws: {status}
          {stale && <span className="status-busy"> · solving…</span>}
        </div>
      </main>
    </div>
  );
}

// App shell. Owns the two pieces of truly global state — the light/dark theme
// and the list of open design sessions — and nothing else. Every session is a
// mounted <DesignSession>; only the active one is shown (the rest are hidden
// with CSS so their inputs survive). Switching flips `active`, which suspends
// the outgoing session's socket/listeners/solves and resumes the incoming
// one's (see the `active` gates in DesignSession).
export function App() {
  // Theme is seeded from the <html data-theme> the no-flash script in
  // index.html set (localStorage || prefers-color-scheme). The 3 canvases read
  // their colors from CSS vars via getComputedStyle, so they consume
  // ThemeContext to repaint on toggle (see FarFieldChart/SmithChart/
  // CurrentCanvas). The toggle button itself lives in each session's sidebar
  // and writes back through ThemeControlContext.
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  // Apply the attribute SYNCHRONOUSLY here, not in a post-render effect: React
  // runs child effects before parent effects, so the canvases' draw effects
  // would re-read getComputedStyle while the attribute still held the previous
  // theme — lagging one toggle behind the (pure-CSS) chrome. Setting it eagerly
  // means the attribute is already current when those effects re-run.
  const applyTheme = useCallback((next: Theme) => {
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* storage disabled — in-memory toggle still works */
    }
    setTheme(next);
  }, []);

  // Open sessions. Ids are stable and monotonic (never reused), so React keys
  // each session to a fixed mount for its whole lifetime — the whole point:
  // a session's inputs live in its component instance, so it must never be
  // reconciled onto a different session's tree.
  const [sessions, setSessions] = useState<SessionMeta[]>([{ id: 1 }]);
  const [activeId, setActiveId] = useState(1);
  const nextIdRef = useRef(2);
  // Per-session tab-hover summaries, reported up from each session.
  const [summaries, setSummaries] = useState<Record<number, string>>({});

  const add = useCallback(() => {
    const id = nextIdRef.current++;
    setSessions((prev) => [...prev, { id }]);
    setActiveId(id);
  }, []);

  const close = useCallback((id: number) => {
    setSessions((prev) => {
      if (prev.length <= 1) return prev; // always keep one session open
      const idx = prev.findIndex((s) => s.id === id);
      const next = prev.filter((s) => s.id !== id);
      // If the closed session was active, activate its neighbour (prefer the
      // one to the left, matching browser-tab behaviour).
      setActiveId((cur) =>
        cur === id ? next[Math.max(0, idx - 1)].id : cur,
      );
      return next;
    });
    setSummaries((prev) => {
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const setActive = useCallback((id: number) => setActiveId(id), []);

  // Identity-guarded so a session re-reporting the same summary is a no-op
  // (avoids a render loop from the reporting effect).
  const reportSummary = useCallback((id: number, summary: string) => {
    setSummaries((prev) => (prev[id] === summary ? prev : { ...prev, [id]: summary }));
  }, []);

  const sessionsCtx = useMemo<SessionsCtx>(
    () => ({ sessions, activeId, add, close, setActive, summaries, reportSummary }),
    [sessions, activeId, add, close, setActive, summaries, reportSummary],
  );

  // Pinned patterns, shared across sessions. The counter is shell-level so
  // pin ids stay unique no matter which session mints them; a pin is a frozen
  // snapshot, so it deliberately outlives the session that created it.
  const [pins, setPins] = useState<PinnedPattern[]>([]);
  const pinSeq = useRef(0);

  // Append the snapshot immediately (the ghost overlay needs no metrics),
  // then patch the table metrics in when /pattern_metrics answers. The color
  // slot is the smallest one no current pin holds, so a freed color is reused
  // before the palette wraps — and never shifts an existing pin's color.
  const addPin = useCallback(
    (label: string, result: SolveResponse, req: SolveRequest) => {
      const id = `pin-${pinSeq.current++}`;
      setPins((ps) => {
        const used = new Set(ps.map((p) => p.colorIdx));
        let colorIdx = 0;
        while (used.has(colorIdx) && colorIdx < GHOST_COLOR_COUNT) colorIdx++;
        if (colorIdx >= GHOST_COLOR_COUNT) colorIdx = ps.length % GHOST_COLOR_COUNT;
        return [...ps, { id, label, result, metrics: null, enabled: true, colorIdx }];
      });
      fetchMetrics(req).then((m) =>
        setPins((ps) => ps.map((p) => (p.id === id ? { ...p, metrics: m } : p))),
      );
    },
    [],
  );

  const removePin = useCallback((id: string) => {
    setPins((ps) => ps.filter((p) => p.id !== id));
  }, []);

  const togglePin = useCallback((id: string) => {
    setPins((ps) =>
      ps.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p)),
    );
  }, []);

  const clearPins = useCallback(() => setPins([]), []);

  const pinsCtx = useMemo<PinsCtx>(
    () => ({ pins, addPin, removePin, togglePin, clearPins }),
    [pins, addPin, removePin, togglePin, clearPins],
  );

  return (
    <ThemeContext.Provider value={theme}>
      <ThemeControlContext.Provider value={applyTheme}>
        <SessionsContext.Provider value={sessionsCtx}>
          <PinsContext.Provider value={pinsCtx}>
            <div className="sessions">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className="session-mount"
                  // Hidden — not unmounted — so an inactive session keeps its
                  // inputs. `hidden` also removes it from the a11y tree and stops
                  // its canvases painting.
                  hidden={s.id !== activeId}
                >
                  <DesignSession id={s.id} active={s.id === activeId} />
                </div>
              ))}
            </div>
          </PinsContext.Provider>
        </SessionsContext.Provider>
      </ThemeControlContext.Provider>
    </ThemeContext.Provider>
  );
}

type BackendConfigProps = {
  slot: Slot;
  backend: Backend;
  opts: BackendOptsMap[Backend];
  onChangeBackend: (b: Backend) => void;
  onPatch: (patch: Partial<BackendOptsMap[Backend]>) => void;
  onReset: () => void;
  onClose: () => void;
};

function BackendConfigModal({
  slot,
  backend,
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
              {BACKEND_ORDER.map((b) => (
                <button
                  key={b}
                  role="tab"
                  aria-selected={backend === b}
                  className={backend === b ? "active" : ""}
                  onClick={() => onChangeBackend(b)}
                >
                  {BACKEND_LABEL[b]}
                </button>
              ))}
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

          {backend === "sinusoidal" && (
            <NumberField
              label="n_qp_const (GL pts)"
              value={(opts as SinusoidalOpts).nQpConst}
              min={2}
              max={32}
              step={1}
              onChange={(v) => onPatch({ nQpConst: v } as never)}
            />
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
      <div className="field">
        <label className="link-toggle" title="Add (u/h)·log(u/h) singular basis at K ≥ enrichment_min_k junctions; flips O(1/N) → ~O(1/N^(d+1)) on dominant-pair K=3 junctions (most current flowing through two of three wires).">
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

// Bare numeric input with the same clear-without-snapping-to-0 draft treatment
// as NumberField (which carries its own label/value chrome and doesn't fit the
// knob menu's grid rows).
function KnobMenuNumber({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);
  return (
    <input
      type="number"
      step="any"
      value={draft}
      onChange={(e) => {
        const text = e.target.value;
        setDraft(text); // allow "", partial, or leading-zero input while typing
        if (text.trim() === "") return; // empty: don't commit (no snap to 0)
        const v = Number(text);
        if (!Number.isNaN(v)) onChange(v);
      }}
      // Normalize on blur: drop any leading zeros / revert an empty field to
      // the last committed value.
      onBlur={() => setDraft(String(value))}
    />
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  // Local text draft so the field can be emptied mid-edit. Binding the input
  // straight to the number coerced "" → 0 on backspace (you couldn't clear it,
  // and the forced 0 left a leading zero when you typed again). The draft holds
  // raw text; a value is only committed when it parses, and re-syncs whenever
  // `value` changes from outside (backend swap, auto-seed, reset).
  const [draft, setDraft] = useState(String(value));
  useEffect(() => {
    setDraft(String(value));
  }, [value]);
  return (
    <div className="field">
      <label>
        <span>{label}</span>
        <span>{value}</span>
      </label>
      <input
        type="number"
        value={draft}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const text = e.target.value;
          setDraft(text); // allow "", partial, or leading-zero input while typing
          if (text.trim() === "") return; // empty: don't commit (no snap to 0)
          const v = Number(text);
          if (!Number.isNaN(v)) onChange(v);
        }}
        // Normalize on blur: drop any leading zeros / revert an empty field to
        // the last committed value.
        onBlur={() => setDraft(String(value))}
      />
    </div>
  );
}

function feedMag(r: SolveResponse): number {
  const w = r.wires[r.feed_wire_index];
  if (!w) return 0;
  const re = w.knot_currents_re[r.feed_knot_index];
  const im = w.knot_currents_im[r.feed_knot_index];
  return Math.hypot(re, im);
}

function reflectionCoefficient(r: number, x: number, z0: number) {
  // Γ = (Z - Z0) / (Z + Z0), with Z = r + jx (Z0 real).
  const denom = (r + z0) * (r + z0) + x * x;
  const gRe = (r * r - z0 * z0 + x * x) / denom;
  const gIm = (2 * x * z0) / denom;
  return { gRe, gIm, gMag: Math.hypot(gRe, gIm) };
}

// Display labels for SolveResponse.ground_model_applied — what the
// impedance solve actually ran, as reported by the server (see the type).
const GROUND_APPLIED_LABEL: Record<string, string> = {
  sommerfeld: "Sommerfeld",
  "refl-coef": "refl-coef",
  "pec-image": "PEC image",
  free: "free space",
};

function formatOhms(v: number): string {
  // The server clamps an open-circuited feed (e.g. a series matchbox
  // capacitor slider at 0 pF) to a 1e9 Ω sentinel — JSON has no Infinity.
  // Anything that large is physically an open, not a number worth printing.
  if (Math.abs(v) >= 1e8) return "∞ (open)";
  return `${v.toFixed(2)} Ω`;
}

function formatSwr(r: number, x: number, z0: number): string {
  const { gMag } = reflectionCoefficient(r, x, z0);
  if (gMag >= 0.9999) return "∞";
  const swr = (1 + gMag) / (1 - gMag);
  if (swr > 99) return swr.toFixed(0);
  return swr.toFixed(2);
}

// The R/X/SWR/rtt solve readout. The desktop stage floats it over the canvas
// as a HUD (className="stage-readout"); the mobile Info screen (Phase B)
// renders it as a normal block. Module scope so both trees share one
// implementation.
function SolveReadout({
  result,
  rttMs,
  currentExample,
  effectiveMultiFeed,
  normCheck,
  normCheckEnabled,
  className = "",
}: {
  result: SolveResponse | null;
  rttMs: number | null;
  currentExample: ExampleDescriptor | undefined;
  effectiveMultiFeed: boolean;
  normCheck: NormCheckData | null;
  normCheckEnabled: boolean;
  className?: string;
}) {
  return (
    <div className={`readout${className ? " " + className : ""}`}>
      <div className="row">
        <span>R</span>
        <span className="val">{result ? formatOhms(result.z_in_re) : "—"}</span>
      </div>
      <div className="row">
        <span>X</span>
        <span
          className={
            result && Math.abs(result.z_in_im) < 2 && Math.abs(result.z_in_re) < 1e8
              ? "val val-hot"
              : "val"
          }
        >
          {result
            ? Math.abs(result.z_in_re) >= 1e8
              ? "∞ (open)"
              : formatOhms(result.z_in_im)
            : "—"}
        </span>
      </div>
      {currentExample && (
        <ResultPanel
          schema={currentExample.result_schema}
          result={result as Record<string, unknown> | null}
        />
      )}
      {effectiveMultiFeed && result?.feeds && result.feeds.length > 1 && (
        <div className="feeds-table">
          <div className="feeds-table-header">per-feed Z (V/I)</div>
          {result.feeds.map((f, i) => (
            <div className="row" key={`feed-z-${i}`}>
              <span>
                feed {i} ∠{Math.round(Math.atan2(f.v_im, f.v_re) * 180 / Math.PI)}°
              </span>
              <span className="val">
                {f.z_re.toFixed(1)} {f.z_im >= 0 ? "+" : "−"} j
                {Math.abs(f.z_im).toFixed(1)} Ω
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="row">
        <span>|I_feed|</span>
        <span className="val">
          {result ? feedMag(result).toExponential(3) : "—"}
        </span>
      </div>
      {result?.ground && result.ground_model_applied && (
        <div
          className="row"
          title="Ground model the impedance solve actually used, as reported by the solver — may be an approximation of the requested ground."
        >
          <span>ground</span>
          <span className="val">
            {GROUND_APPLIED_LABEL[result.ground_model_applied] ??
              result.ground_model_applied}
          </span>
        </div>
      )}
      <div className="row">
        <span>SWR ({(result?.z0_ohms ?? 50).toFixed(0)} Ω)</span>
        <span className="val">
          {result
            ? formatSwr(result.z_in_re, result.z_in_im, result.z0_ohms ?? 50)
            : "—"}
        </span>
      </div>
      {(() => {
        // Power budget (issue #299): where the input watts go, per network
        // branch. Branch rows are hidden unless the network actually
        // dissipates something (lossless branches report float noise only).
        // The radiated row (issue #339) is the third efficiency ledger —
        // P_radiated/P_input INCLUDING far-field ground absorption, derived
        // from the dwell-triggered norm check — so it renders even for a
        // lossless design over real ground, greyed to "—" while knobs move.
        const budget = result?.power_budget;
        const pin = result?.input_power_w;
        const diss =
          budget && pin ? budget.reduce((s, b) => s + b.watts, 0) : 0;
        const showBudget =
          !!budget && budget.length > 0 && !!pin && pin > 0 &&
          diss >= 1e-6 * pin;
        if (!showBudget && !normCheckEnabled) return null;
        return (
          <div className="feeds-table">
            {showBudget && pin && (
              <div title="Fraction of the source input power dissipated in each network branch (from the MNA solve); the antenna row is the remainder that reaches the wires.">
                <div className="feeds-table-header">power budget</div>
                {budget.map((b, i) => (
                  <div className="row" key={`pb-${i}`}>
                    <span>{b.label}</span>
                    <span className="val">
                      {((b.watts / pin) * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
                <div className="row" key="pb-ant">
                  <span>antenna (accepted)</span>
                  <span className="val">
                    {(((pin - diss) / pin) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            )}
            {normCheckEnabled && (
              <div
                className="row"
                title="P_radiated / P_input from the dwell-triggered pattern integral (the norm check as a percentage): what actually leaves as far-field radiation after network, wire AND real ground absorption. Fills in once the knobs settle; over PEC ground or free space it collapses onto the structural efficiency. See the 'three ledgers' section of the docs."
              >
                <span>radiated (incl. ground)</span>
                <span className={normCheck ? "val" : "val val-pending"}>
                  {normCheck
                    ? `${(normCheck.radiated_fraction * 100).toFixed(0)}%`
                    : "—"}
                </span>
              </div>
            )}
          </div>
        );
      })()}
      {/* Engine timing grouped last: solve/rtt describe how fast the answer
          arrived, not what the antenna is doing, so they sit below the RF
          readout (and below the power budget when one is shown). The
          feeds-table wrapper is used only for its dashed separator rule —
          no header. */}
      <div className="feeds-table">
        <div className="row">
          <span>solve</span>
          <span className="val">
            {result ? `${result.solve_ms.toFixed(1)} ms` : "—"}
          </span>
        </div>
        <div className="row">
          <span>rtt</span>
          <span className="val">
            {rttMs != null ? `${rttMs.toFixed(1)} ms` : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

function ViewPanel({
  view,
  size,
  fill,
  result,
  preview,
  sweep,
  converge,
  pattern,
  pinnedPatterns,
  measFreqMhz,
  sweepRunning,
  convergeRunning,
  azElevDeg,
  elevAzDeg,
  cameraProjection,
  showHeatmap,
  showEnvelope,
  showWireLabels = false,
  showFeedNames = true,
  multiFeed,
  fineNorm,
}: {
  view: View;
  size: number;
  fill: boolean;
  result: SolveResponse | null;
  preview: SolveResponse | null;
  sweep: SweepData | null;
  converge: ConvergeData | null;
  pattern: PatternData | null;
  pinnedPatterns: PinnedPattern[];
  measFreqMhz: number;
  sweepRunning: boolean;
  convergeRunning: boolean;
  azElevDeg: number;
  elevAzDeg: number;
  cameraProjection: Projection;
  showHeatmap: boolean;
  showEnvelope: boolean;
  showWireLabels?: boolean;
  showFeedNames?: boolean;
  multiFeed: boolean;
  fineNorm?: number | null;
}) {
  if (view === "antenna") {
    // Fall back to the geometry-only preview while the real solve is in
    // flight, but with the current heatmap/waveform overlays forced off —
    // the preview has no currents, so only the bare wires + feed are drawn.
    const showingPreview = !result && !!preview;
    return (
      <div className={fill ? "antenna-fill" : "antenna-thumb"}
           style={fill ? undefined : { width: size, height: size }}>
        <CurrentCanvas
          result={result ?? preview}
          projection={cameraProjection}
          showHeatmap={showingPreview ? false : showHeatmap}
          showEnvelope={showingPreview ? false : showEnvelope}
          showWireLabels={showWireLabels}
          showFeedNames={showFeedNames}
          interactive={fill}
        />
      </div>
    );
  }
  if (view === "azimuth") {
    return (
      <FarFieldChart
        result={result}
        pattern={pattern}
        pinned={pinnedPatterns}
        size={size}
        cut="xy"
        azElevDeg={azElevDeg}
        elevAzDeg={elevAzDeg}
        fineNorm={fineNorm}
      />
    );
  }
  if (view === "elevation") {
    return (
      <FarFieldChart
        result={result}
        pattern={pattern}
        pinned={pinnedPatterns}
        size={size}
        cut="yz"
        azElevDeg={azElevDeg}
        elevAzDeg={elevAzDeg}
        fineNorm={fineNorm}
      />
    );
  }
  return (
    <SmithChart
      r={result?.z_in_re ?? 0}
      x={result?.z_in_im ?? 0}
      z0={result?.z0_ohms ?? 50}
      size={size}
      sweep={sweep}
      converge={converge}
      measFreqMhz={measFreqMhz}
      running={sweepRunning}
      convergeRunning={convergeRunning}
      feeds={result?.feeds}
      multiFeed={multiFeed}
    />
  );
}

type FarFieldCut = "xy" | "yz";

// Scalar far-field metrics from /pattern_metrics, shown in the compare table.
type PatternMetrics = {
  peak_gain_dbi: number;
  takeoff_deg: number;
  azimuth_deg: number;
  front_to_back_db: number;
  az_beamwidth_deg: number;
  el_beamwidth_deg: number;
  measurement_freq_mhz?: number;
};

// Fetch the scalar far-field metrics for a request (peak gain, takeoff, F/B,
// beamwidths). Returns null when the design can't be evaluated or on error.
async function fetchMetrics(req: SolveRequest): Promise<PatternMetrics | null> {
  try {
    const resp = await fetch("/pattern_metrics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    const data = await resp.json();
    return data.available ? (data.metrics as PatternMetrics) : null;
  } catch {
    return null;
  }
}

// A pinned far-field snapshot: the full solve response (so its cut traces
// recompute through the same math as the live one, in whatever cut the user is
// viewing) plus a label, and the metrics fetched for the table. Pins live in
// the shell and are shared across sessions (see PinsContext), so they survive
// design switches and tab closes — you can overlay one antenna's pattern on
// another's, including a design open in a different tab.
type PinnedPattern = {
  id: string;
  label: string;
  result: SolveResponse;
  metrics: PatternMetrics | null;
  // Whether the ghost overlay is drawn. A disabled pin keeps its table row
  // (dimmed, metrics still readable) — that's the point of disable vs delete.
  enabled: boolean;
  // Fixed GHOST_COLORS slot, assigned at pin time. Stored — not the array
  // index — because the chart draws a filtered (enabled-only) list while the
  // table draws all pins; positional colors would desynchronize the two, and
  // already shifted every later pin's color on delete.
  colorIdx: number;
};

function PatternCompareTable({
  live,
  liveLabel,
  pinned,
  onRemove,
  onToggle,
}: {
  live: PatternMetrics | null;
  liveLabel: string;
  pinned: PinnedPattern[];
  onRemove: (id: string) => void;
  onToggle: (id: string) => void;
}) {
  const fmt = (v: number | undefined, d: number) =>
    v === undefined || v === null ? "—" : v.toFixed(d);
  // Live row's swatch reads the lobe CSS var so it matches the orange lobe in
  // either theme; pinned rows use their fixed canvas ghost colors.
  const rows = [
    {
      key: "live",
      bg: "rgba(var(--plot-lobe-rgb), 0.95)",
      label: liveLabel,
      m: live,
      enabled: true,
      onToggle: undefined as undefined | (() => void),
      onX: undefined as undefined | (() => void),
    },
    ...pinned.map((p) => {
      const i = p.colorIdx % GHOST_COLOR_COUNT;
      return {
        key: p.id,
        // CSS var (like the live row) so the swatch rethemes without a render.
        bg: `rgba(var(--plot-ghost-${i}-rgb, ${GHOST_FALLBACK_RGB[i]}), 0.95)`,
        label: p.label,
        m: p.metrics,
        enabled: p.enabled,
        onToggle: () => onToggle(p.id),
        onX: () => onRemove(p.id),
      };
    }),
  ];
  return (
    <table className="compare-table">
      <thead>
        <tr>
          <th>design</th>
          <th>peak</th>
          <th>takeoff</th>
          <th>F/B</th>
          <th>az bw</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className={row.enabled ? undefined : "compare-off"}>
            <td className="compare-name">
              {/* The whole swatch+name is the show/hide toggle — a big-enough
                  touch target where the tiny swatch alone wouldn't be. The
                  metrics stay readable while hidden; that's disable vs delete. */}
              {row.onToggle ? (
                <button
                  type="button"
                  className="compare-toggle"
                  onClick={row.onToggle}
                  aria-pressed={row.enabled}
                  title={
                    row.enabled
                      ? "Hide this ghost overlay (keeps the pin)"
                      : "Show this ghost overlay"
                  }
                >
                  <span
                    className="compare-swatch"
                    style={{ background: row.bg }}
                  />
                  {row.label}
                </button>
              ) : (
                <>
                  <span
                    className="compare-swatch"
                    style={{ background: row.bg }}
                  />
                  {row.label}
                </>
              )}
            </td>
            <td>{fmt(row.m?.peak_gain_dbi, 1)}</td>
            <td>{row.m ? `${fmt(row.m.takeoff_deg, 0)}°` : "—"}</td>
            <td>{fmt(row.m?.front_to_back_db, 1)}</td>
            <td>{row.m ? `${fmt(row.m.az_beamwidth_deg, 0)}°` : "—"}</td>
            <td>
              {row.onX && (
                <button
                  type="button"
                  className="compare-x"
                  onClick={row.onX}
                  title="Remove this pinned pattern"
                >
                  ✕
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Directions sampled around each polar cut. Module-level so the trace helper
// and the chart agree.
const FARFIELD_N_DIR = 180;

// Compute the per-direction gain (dBi) of one solve response along a polar cut,
// reproducing the live lobe math (moment integral over all segments, PEC image
// + Fresnel reflection when ground is on). Returns the N_DIR-length dBi samples
// and the peak, or null when there's nothing to draw. Both the live trace and
// every pinned ghost go through this, so they're guaranteed consistent.
function computeCutDbi(
  result: SolveResponse,
  cut: FarFieldCut,
  azElevDeg: number,
  elevAzDeg: number,
): { dbi: number[]; peakDbi: number } | null {
  const azElevRad = (azElevDeg * Math.PI) / 180;
  const azSinT = Math.cos(azElevRad);
  const azCosT = Math.sin(azElevRad);
  const elevAzRad = (elevAzDeg * Math.PI) / 180;
  const elevAzCos = Math.cos(elevAzRad);
  const elevAzSin = Math.sin(elevAzRad);
  const groundOn = !!result.ground;
  const N_DIR = FARFIELD_N_DIR;
  const k = result.k_meas_m_inv ?? 0;
  const epsRe = result.ground_eps_r ?? 1;
  const epsIm = result.ground_eps_im ?? 0;

  let nSeg = 0;
  for (const w of result.wires) {
    const pts = w.sample_positions ?? w.knot_positions;
    nSeg += pts.length - 1;
  }
  if (nSeg === 0) return null;
  const dx = new Float64Array(nSeg);
  const dy = new Float64Array(nSeg);
  const dz = new Float64Array(nSeg);
  const midx = new Float64Array(nSeg);
  const midy = new Float64Array(nSeg);
  const midz = new Float64Array(nSeg);
  const Ire = new Float64Array(nSeg);
  const Iim = new Float64Array(nSeg);
  let off = 0;
  for (const w of result.wires) {
    const pts = w.sample_positions ?? w.knot_positions;
    const cre = w.sample_currents_re ?? w.knot_currents_re;
    const cim = w.sample_currents_im ?? w.knot_currents_im;
    for (let n = 0; n < pts.length - 1; n++) {
      const a = pts[n];
      const b = pts[n + 1];
      dx[off] = b[0] - a[0];
      dy[off] = b[1] - a[1];
      dz[off] = b[2] - a[2];
      midx[off] = 0.5 * (a[0] + b[0]);
      midy[off] = 0.5 * (a[1] + b[1]);
      midz[off] = 0.5 * (a[2] + b[2]);
      Ire[off] = 0.5 * (cre[n] + cre[n + 1]);
      Iim[off] = 0.5 * (cim[n] + cim[n + 1]);
      off++;
    }
  }

  const mag2s = new Array<number>(N_DIR);
  let maxMag2 = 0;
  for (let pi = 0; pi < N_DIR; pi++) {
    const t = (2 * Math.PI * pi) / N_DIR;
    const ct = Math.cos(t);
    const st = Math.sin(t);
    const rx = cut === "xy" ? azSinT * ct : elevAzCos * ct;
    const ry = cut === "xy" ? azSinT * st : elevAzSin * ct;
    const rz = cut === "xy" ? azCosT : st;
    if (groundOn && rz < 0) {
      mag2s[pi] = 0;
      continue;
    }
    let mxRe = 0, mxIm = 0, myRe = 0, myIm = 0, mzRe = 0, mzIm = 0;
    let ixRe = 0, ixIm = 0, iyRe = 0, iyIm = 0, izRe = 0, izIm = 0;
    for (let n = 0; n < nSeg; n++) {
      const phase = k * (rx * midx[n] + ry * midy[n] + rz * midz[n]);
      const cph = Math.cos(phase);
      const sph = Math.sin(phase);
      const ire = Ire[n] * cph - Iim[n] * sph;
      const iim = Ire[n] * sph + Iim[n] * cph;
      mxRe += ire * dx[n];
      mxIm += iim * dx[n];
      myRe += ire * dy[n];
      myIm += iim * dy[n];
      mzRe += ire * dz[n];
      mzIm += iim * dz[n];
      if (groundOn) {
        const phaseI = k * (rx * midx[n] + ry * midy[n] - rz * midz[n]);
        const cphI = Math.cos(phaseI);
        const sphI = Math.sin(phaseI);
        const ireI = Ire[n] * cphI - Iim[n] * sphI;
        const iimI = Ire[n] * sphI + Iim[n] * cphI;
        ixRe += ireI * -dx[n]; ixIm += iimI * -dx[n];
        iyRe += ireI * -dy[n]; iyIm += iimI * -dy[n];
        izRe += ireI *  dz[n]; izIm += iimI *  dz[n];
      }
    }
    const mDotRre = mxRe * rx + myRe * ry + mzRe * rz;
    const mDotRim = mxIm * rx + myIm * ry + mzIm * rz;
    let pxRe = mxRe - mDotRre * rx;
    let pxIm = mxIm - mDotRim * rx;
    let pyRe = myRe - mDotRre * ry;
    let pyIm = myIm - mDotRim * ry;
    let pzRe = mzRe - mDotRre * rz;
    let pzIm = mzIm - mDotRim * rz;
    if (groundOn) {
      const iDotRre = ixRe * rx + iyRe * ry + izRe * rz;
      const iDotRim = ixIm * rx + iyIm * ry + izIm * rz;
      const qxRe = ixRe - iDotRre * rx;
      const qxIm = ixIm - iDotRim * rx;
      const qyRe = iyRe - iDotRre * ry;
      const qyIm = iyIm - iDotRim * ry;
      const qzRe = izRe - iDotRre * rz;
      const qzIm = izIm - iDotRim * rz;
      const s = Math.sqrt(rx * rx + ry * ry);
      let hx: number, hy: number, hz: number;
      let vx: number, vy: number, vz: number;
      if (s > 1e-9) {
        hx = -ry / s; hy = rx / s; hz = 0;
        vx = -rx * rz / s; vy = -ry * rz / s; vz = s;
      } else {
        hx = 1; hy = 0; hz = 0;
        vx = 0; vy = 1; vz = 0;
      }
      const qhRe = qxRe * hx + qyRe * hy + qzRe * hz;
      const qhIm = qxIm * hx + qyIm * hy + qzIm * hz;
      const qvRe = qxRe * vx + qyRe * vy + qzRe * vz;
      const qvIm = qxIm * vx + qyIm * vy + qzIm * vz;
      const cosTi = rz;
      const sin2Ti = s * s;
      const aRe = epsRe - sin2Ti;
      const aIm = epsIm;
      const aMag = Math.hypot(aRe, aIm);
      const QRe = Math.sqrt(0.5 * (aMag + aRe));
      const QIm = Math.sign(aIm || 1) * Math.sqrt(Math.max(0, 0.5 * (aMag - aRe)));
      const numHRe = cosTi - QRe, numHIm = -QIm;
      const denHRe = cosTi + QRe, denHIm = QIm;
      const denH2 = denHRe * denHRe + denHIm * denHIm;
      const rhoHRe = (numHRe * denHRe + numHIm * denHIm) / denH2;
      const rhoHIm = (numHIm * denHRe - numHRe * denHIm) / denH2;
      const ecRe = epsRe * cosTi, ecIm = epsIm * cosTi;
      const numVRe = ecRe - QRe, numVIm = ecIm - QIm;
      const denVRe = ecRe + QRe, denVIm = ecIm + QIm;
      const denV2 = denVRe * denVRe + denVIm * denVIm;
      const rhoVRe = (numVRe * denVRe + numVIm * denVIm) / denV2;
      const rhoVIm = (numVIm * denVRe - numVRe * denVIm) / denV2;
      const rvqRe = rhoVRe * qvRe - rhoVIm * qvIm;
      const rvqIm = rhoVRe * qvIm + rhoVIm * qvRe;
      const rhqRe = rhoHRe * qhRe - rhoHIm * qhIm;
      const rhqIm = rhoHRe * qhIm + rhoHIm * qhRe;
      pxRe += rvqRe * vx - rhqRe * hx;
      pxIm += rvqIm * vx - rhqIm * hx;
      pyRe += rvqRe * vy - rhqRe * hy;
      pyIm += rvqIm * vy - rhqIm * hy;
      pzRe += rvqRe * vz - rhqRe * hz;
      pzIm += rvqIm * vz - rhqIm * hz;
    }
    const mag2 =
      pxRe * pxRe + pxIm * pxIm +
      pyRe * pyRe + pyIm * pyIm +
      pzRe * pzRe + pzIm * pzIm;
    mag2s[pi] = mag2;
    if (mag2 > maxMag2) maxMag2 = mag2;
  }
  if (maxMag2 <= 0) return null;
  // Absolute-dBi reference. Every solve carries its gain norm (an O(1)
  // input-power scalar server-side), so the only fallback is peak-normalizing
  // a response that somehow shipped without one (defensive).
  const norm =
    result.directivity_norm && result.directivity_norm > 0
      ? result.directivity_norm
      : 1 / maxMag2;
  const dbi = mag2s.map((m) => (norm * m > 0 ? 10 * Math.log10(norm * m) : -Infinity));
  return { dbi, peakDbi: 10 * Math.log10(norm * maxMag2) };
}

function FarFieldChart({
  result,
  pattern,
  pinned,
  size,
  cut,
  azElevDeg,
  elevAzDeg,
  fineNorm,
}: {
  result: SolveResponse | null;
  pattern: PatternData | null;
  pinned: PinnedPattern[];
  size: number;
  cut: FarFieldCut;
  azElevDeg: number;
  elevAzDeg: number;
  /** Field-side gain norm from the dwell-triggered norm check (the pattern
   *  renormalised by its own integrated radiated power instead of the input
   *  power the live norm uses). When set, that pattern is overlaid dotted —
   *  the norm is a scalar multiplier, so it is the live trace shifted
   *  radially by 10·log10(fineNorm/liveNorm). Overlap ⇒ the solve conserves
   *  power; a visible gap ⇒ the solver's discretisation error. */
  fineNorm?: number | null;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(size * dpr);
    canvas.height = Math.floor(size * dpr);
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const PC = plotColors();

    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, size, size);

    const cx = size / 2;
    const cy = size / 2;
    const R = size / 2 - 14;

    // Azimuth cut: cone above horizon at elevation azElevDeg. With ground
    // off, the conventional setting is 0° (the xy plane). With ground on,
    // 0° is grazing and Fresnel kills the pattern, so something like 15°
    // gives a useful view — the slider lets the user pick.
    const azElevRad = (azElevDeg * Math.PI) / 180;
    const azSinT = Math.cos(azElevRad); // sin(polar θ from +z) = cos(elevation)
    const azCosT = Math.sin(azElevRad); // cos(polar θ) = sin(elevation)
    // Elevation cut: vertical great circle through azimuth bearing elevAzDeg.
    // t=0 lies at +elevAz horizon; t=π/2 is zenith; t=π is at the opposite
    // horizon; t=3π/2 is nadir (below ground, zeroed when ground is on).
    const elevAzRad = (elevAzDeg * Math.PI) / 180;
    const elevAzCos = Math.cos(elevAzRad);
    const elevAzSin = Math.sin(elevAzRad);

    // Compute every trace (live + any pinned ghosts) up front, so the radial
    // scale below can expand to fit the highest-gain lobe on screen. Cheap —
    // each is computed once here and reused when drawing.
    const liveTrace = result
      ? computeCutDbi(result, cut, azElevDeg, elevAzDeg)
      : null;
    // Disabled pins draw no ghost and don't stretch the radial scale.
    const ghosts = pinned
      .filter((p) => p.enabled)
      .map((p) => ({
        colorIdx: p.colorIdx,
        trace: computeCutDbi(p.result, cut, azElevDeg, elevAzDeg),
      }));

    // Radial axis: absolute directivity in dBi. Origin is a fixed −20 dBi
    // floor. The outer edge is +10 dBi by default, but expands to fit the peak
    // of the highest-gain trace (plus 1 dB headroom) so a high-gain array's
    // lobe renders in full instead of drawing past the edge and clipping — the
    // thumbnails escaped this only because their tiny radius left slack inside
    // the margin. Labeled rings sit at +6/0/−6/−12/−18 (all inside any top).
    const DBI_FLOOR = -20;
    const peaks: number[] = [];
    if (liveTrace) peaks.push(liveTrace.peakDbi);
    for (const gh of ghosts) if (gh.trace) peaks.push(gh.trace.peakDbi);
    // Norm-check overlay: the norm scales the whole pattern, so switching to
    // the field-side norm shifts every dBi by this constant. null when the
    // check is off or the live result carries no norm to compare against.
    const liveNorm = result?.directivity_norm;
    const gridDeltaDb =
      fineNorm && fineNorm > 0 && liveNorm && liveNorm > 0
        ? 10 * Math.log10(fineNorm / liveNorm)
        : null;
    // Let the radial scale grow to fit the shifted overlay when it lands higher.
    if (liveTrace && gridDeltaDb != null) peaks.push(liveTrace.peakDbi + gridDeltaDb);
    const maxPeak = peaks.filter(Number.isFinite).reduce((a, b) => Math.max(a, b), 10);
    const DBI_TOP = Math.max(10, Math.ceil(maxPeak + 1));
    const DB_SPAN = DBI_TOP - DBI_FLOOR;
    // Clamp to [0, 1]: a lobe at/above the top sits on the rim instead of
    // drawing past R and clipping against the canvas edge.
    const dbiToFrac = (db: number) =>
      Math.max(0, Math.min(1, (db - DBI_FLOOR) / DB_SPAN));
    ctx.strokeStyle = PC.grid;
    ctx.lineWidth = 0.6;
    ctx.fillStyle = PC.labelDim;
    ctx.font = "9px ui-monospace, monospace";
    for (const db of [6, 0, -6, -12, -18]) {
      const f = dbiToFrac(db);
      ctx.beginPath();
      ctx.arc(cx, cy, R * f, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.fillText(`${db > 0 ? "+" : ""}${db}`, cx + 2, cy - R * f - 1);
    }
    ctx.beginPath();
    ctx.moveTo(cx - R, cy);
    ctx.lineTo(cx + R, cy);
    ctx.moveTo(cx, cy - R);
    ctx.lineTo(cx, cy + R);
    ctx.stroke();

    // Axis labels: xy cut uses world x/y around the rim; yz cut shows the
    // azimuth bearing on the horizontal pair and zenith/nadir on vertical.
    ctx.fillStyle = PC.labelDim;
    ctx.font = "10px ui-monospace, monospace";
    const cutLabel =
      cut === "xy"
        ? `az @ ${azElevDeg}° elev (dBi)`
        : `elev @ ${elevAzDeg}° az (dBi)`;
    ctx.fillText(cutLabel, 6, 14);
    ctx.fillStyle = PC.label;
    if (cut === "xy") {
      ctx.fillText("+x", cx + R - 14, cy + 11);
      ctx.fillText("−x", cx - R + 2, cy + 11);
      ctx.fillText("+y", cx - 8, cy - R + 12);
      ctx.fillText("−y", cx - 7, cy + R - 2);
    } else {
      ctx.fillText("zen", cx - 9, cy - R + 12);
      ctx.fillText("nad", cx - 9, cy + R - 2);
    }

    // Cross-reference: a single dashed spoke showing where the *other* cut
    // slices this plot. The opposite side is implied by symmetry.
    const markerStyle = PC.spoke;
    {
      const canvasAngleRad =
        cut === "xy"
          ? (elevAzDeg * Math.PI) / 180  // azimuth plot: elevation cut's bearing
          : (azElevDeg * Math.PI) / 180; // elevation plot: azimuth cut's elevation
      const cosA = Math.cos(canvasAngleRad);
      const sinA = Math.sin(canvasAngleRad);
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + cosA * R, cy - sinA * R);
      ctx.strokeStyle = markerStyle;
      ctx.lineWidth = 0.8;
      ctx.setLineDash([3, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    if (!result) return;

    const N_DIR = FARFIELD_N_DIR;

    // Draw one dBi trace around the polar cut. The live lobe closes + fills;
    // pinned ghosts are an open dashed stroke so the live trace reads on top.
    const strokeTrace = (
      dbi: number[],
      o: { stroke: string; fill?: string; width: number; dash?: number[] },
    ) => {
      ctx.beginPath();
      for (let pi = 0; pi <= N_DIR; pi++) {
        const t = (2 * Math.PI * pi) / N_DIR;
        const frac = dbiToFrac(dbi[pi % N_DIR]);
        const px = cx + Math.cos(t) * frac * R;
        // Canvas y flips: +y on canvas is down, so we negate to put +y at top.
        const py = cy - Math.sin(t) * frac * R;
        if (pi === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      if (o.fill) {
        ctx.fillStyle = o.fill;
        ctx.fill();
      }
      if (o.dash) ctx.setLineDash(o.dash);
      ctx.strokeStyle = o.stroke;
      ctx.lineWidth = o.width;
      ctx.stroke();
      if (o.dash) ctx.setLineDash([]);
    };

    // Pinned ghosts first (dimmed, dashed), so the live lobe sits on top. Each
    // shares the adaptive radial scale computed above, so it tracks the cut and
    // angle sliders just like the live trace.
    for (const gh of ghosts) {
      if (!gh.trace) continue;
      strokeTrace(gh.trace.dbi, {
        stroke: `rgba(${ghostRgb(gh.colorIdx)}, 0.8)`,
        width: 1,
        dash: [5, 3],
      });
    }

    // Live lobe (filled).
    if (!liveTrace) return;
    strokeTrace(liveTrace.dbi, {
      stroke: `rgba(${PC.lobeRgb}, 0.9)`,
      fill: `rgba(${PC.lobeRgb}, 0.12)`,
      width: 1.5,
    });

    // Fine-grid norm overlay (dotted, same lobe hue): the live trace shifted
    // radially by the constant dB offset. Sits exactly on the solid lobe when
    // the adaptive grid was fine enough; a visible gap is the grid error. Drawn
    // open (no fill) so the solid lobe still reads underneath.
    if (gridDeltaDb != null) {
      strokeTrace(
        liveTrace.dbi.map((d) => d + gridDeltaDb),
        { stroke: `rgba(${PC.lobeRgb}, 0.85)`, width: 1, dash: [2, 2] },
      );
    }

    // NEC exact-pattern overlay (dashed cyan line) when available. Bilinear
    // interpolation off the (θ, φ) grid; rays below horizon are skipped so
    // the line breaks at the ground rather than wrapping to the origin.
    if (pattern) {
      const nt = pattern.theta_deg.length;
      const np_ = pattern.phi_deg.length;
      const dTheta = pattern.theta_deg[1] - pattern.theta_deg[0];
      const dPhi = pattern.phi_deg[1] - pattern.phi_deg[0];
      const clip = (g: number) => (g < -100 ? -100 : g);

      ctx.beginPath();
      let started = false;
      for (let pi = 0; pi <= N_DIR; pi++) {
        const t = (2 * Math.PI * pi) / N_DIR;
        const ct = Math.cos(t);
        const st = Math.sin(t);
        const rx = cut === "xy" ? azSinT * ct : elevAzCos * ct;
        const ry = cut === "xy" ? azSinT * st : elevAzSin * ct;
        const rz = cut === "xy" ? azCosT : st;
        if (rz < -1e-9) { started = false; continue; }

        const thetaDeg = (Math.acos(Math.max(-1, Math.min(1, rz))) * 180) / Math.PI;
        let phiRad = Math.atan2(ry, rx);
        if (phiRad < 0) phiRad += 2 * Math.PI;
        const phiDeg = (phiRad * 180) / Math.PI;

        const tf = Math.max(0, Math.min(nt - 1, thetaDeg / dTheta));
        const pf = Math.max(0, Math.min(np_ - 1, phiDeg / dPhi));
        const t0 = Math.floor(tf), t1 = Math.min(nt - 1, t0 + 1);
        const p0 = Math.floor(pf), p1 = Math.min(np_ - 1, p0 + 1);
        const ft = tf - t0, fp = pf - p0;
        const g00 = clip(pattern.gain_dbi[t0][p0]);
        const g01 = clip(pattern.gain_dbi[t0][p1]);
        const g10 = clip(pattern.gain_dbi[t1][p0]);
        const g11 = clip(pattern.gain_dbi[t1][p1]);
        const dBi =
          g00 * (1 - ft) * (1 - fp) +
          g01 * (1 - ft) * fp +
          g10 * ft * (1 - fp) +
          g11 * ft * fp;

        const frac = dbiToFrac(dBi);
        const px = cx + Math.cos(t) * frac * R;
        const py = cy - Math.sin(t) * frac * R;
        if (!started) { ctx.moveTo(px, py); started = true; }
        else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = `rgba(${PC.necRgb}, 0.85)`;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Legend swatch + label, bottom-right.
      ctx.fillStyle = `rgba(${PC.necRgb}, 0.9)`;
      ctx.font = "10px ui-monospace, monospace";
      const necText = "NEC rp_card";
      const necTw = ctx.measureText(necText).width;
      ctx.fillText(necText, size - necTw - 6, size - 6);
    }

    // Peak dBi annotation (top-right corner).
    const peakDbi = liveTrace.peakDbi;
    ctx.fillStyle = PC.labelStrong;
    ctx.font = "10px ui-monospace, monospace";
    const peakText = `peak ${peakDbi >= 0 ? "+" : ""}${peakDbi.toFixed(1)} dBi`;
    const tw = ctx.measureText(peakText).width;
    ctx.fillText(peakText, size - tw - 6, 14);
  }, [result, pattern, pinned, size, cut, azElevDeg, elevAzDeg, fineNorm, theme]);

  return <canvas ref={canvasRef} className="farfield" />;
}

// Per-feed colors for multi-line Smith chart overlays. Feed 0 keeps the
// existing single-feed blue so single-feed geometries are visually
// unchanged; subsequent feeds use distinct hues that read well on the
// dark background. Indices beyond this list wrap, but that's only
// reachable on >4-feed geometries (none exist yet).
const FEED_COLORS: [number, number, number][] = [
  [118, 208, 255],  // blue (primary)
  [255, 196, 102],  // amber
  [140, 230, 140],  // green
  [255, 130, 200],  // pink
];

// Swatch colors for pinned far-field ghost overlays, themed via CSS vars —
// the dark theme's pastels are darker inks in light mode, where a 1px dashed
// pastel stroke vanishes on the white canvas. Distinct from the live lobe
// (orange) and the NEC overlay (cyan); they wrap past the 4th pin.
const GHOST_COLOR_COUNT = 4;
// Fallbacks match the dark-theme values in styles.css.
const GHOST_FALLBACK_RGB = [
  "140, 230, 140", // green
  "255, 130, 200", // pink
  "180, 160, 255", // violet
  "120, 220, 220", // teal
];
// "r, g, b" for a pin's color slot in the current theme, for canvas strokes.
// (The compare table instead inlines the CSS var so it rethemes live.)
function ghostRgb(colorIdx: number): string {
  const i = colorIdx % GHOST_COLOR_COUNT;
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(`--plot-ghost-${i}-rgb`)
    .trim();
  return v || GHOST_FALLBACK_RGB[i];
}

function feedColor(i: number, alpha = 0.85): string {
  const [r, g, b] = FEED_COLORS[i % FEED_COLORS.length];
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Sweep trail uses a darkened variant of each feed's primary color so the
// current-Z marker reads as "you are here" against a dimmer "trail". With
// two feeds at identical Z (e.g. the in-phase symmetric case) the two
// primary markers stack on top of each other but stay distinguishable from
// the sweep cloud underneath — without this they were indistinguishable.
function feedSweepColor(i: number, alpha = 0.85): string {
  const [r, g, b] = FEED_COLORS[i % FEED_COLORS.length];
  const f = 0.55; // darken factor — empirically readable on the #0d1015 bg
  return `rgba(${Math.round(r * f)}, ${Math.round(g * f)}, ${Math.round(b * f)}, ${alpha})`;
}

function SmithChart({
  r,
  x,
  z0,
  size,
  sweep,
  converge,
  measFreqMhz,
  running,
  convergeRunning,
  feeds,
  multiFeed,
}: {
  r: number;
  x: number;
  z0: number;
  size: number;
  sweep: SweepData | null;
  converge: ConvergeData | null;
  measFreqMhz: number;
  running: boolean;
  convergeRunning: boolean;
  /** Multi-feed geometries pass the per-feed Z list from the latest
   *  solve so the chart can also render N centre dots, one per port. */
  feeds?: FeedEntry[];
  /** From the example descriptor's `multi_feed` flag — drives the
   *  per-feed summary rows. Decoupled from feeds[].length so the chart
   *  reflects antenna type rather than guessing from response shape. */
  multiFeed: boolean;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(size * dpr);
    canvas.height = Math.floor(size * dpr);
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const PC = plotColors();

    const cx = size / 2;
    const cy = size / 2;
    const R = size / 2 - 10;

    ctx.fillStyle = PC.bg;
    ctx.fillRect(0, 0, size, size);

    // Constant-r circles in the Γ plane.
    // Each maps to a circle: center = (r/(r+1), 0), radius = 1/(r+1).
    const rCircles: { r: number; label?: string }[] = [
      { r: 0.2 },
      { r: 0.5, label: "0.5" },
      { r: 1, label: "1" },
      { r: 2, label: "2" },
      { r: 5 },
    ];
    ctx.strokeStyle = PC.grid;
    ctx.lineWidth = 0.6;
    for (const { r: rn } of rCircles) {
      const cxN = rn / (rn + 1);
      const radN = 1 / (rn + 1);
      ctx.beginPath();
      ctx.arc(cx + cxN * R, cy, radN * R, 0, 2 * Math.PI);
      ctx.stroke();
    }

    // Constant-x arcs: center = (1, 1/x), radius = 1/|x|. Clip to unit disk.
    const xArcs = [0.2, 0.5, 1, 2, 5];
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, 2 * Math.PI);
    ctx.clip();
    for (const xn of xArcs) {
      const arcCx = cx + R;
      const rad = (1 / xn) * R;
      // Inductive (X > 0)
      ctx.beginPath();
      ctx.arc(arcCx, cy - (1 / xn) * R, rad, 0, 2 * Math.PI);
      ctx.stroke();
      // Capacitive (X < 0)
      ctx.beginPath();
      ctx.arc(arcCx, cy + (1 / xn) * R, rad, 0, 2 * Math.PI);
      ctx.stroke();
    }
    ctx.restore();

    // Real axis
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(cx - R, cy);
    ctx.lineTo(cx + R, cy);
    ctx.stroke();

    // Outer boundary (|Γ| = 1)
    ctx.strokeStyle = PC.axis;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, 2 * Math.PI);
    ctx.stroke();

    // Z0 label at center
    ctx.fillStyle = PC.labelDim;
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(`Z₀ = ${z0}`, 6, 14);

    // Reactance sign labels.
    ctx.fillStyle = PC.labelDim;
    ctx.fillText("+jX", cx + R - 24, cy - R + 14);
    ctx.fillText("−jX", cx + R - 24, cy + R - 4);

    // Sweep locus: one colored trajectory per feed (or just the primary
    // for single-feed geometries). Multi-feed geometries (bowtie) ship
    // per-feed Z arrays via sweep.feeds_z_re / feeds_z_im; when present
    // we render one color-distinct trajectory per port instead of the
    // single legacy blue locus. No connecting line — sparse samples
    // make a piecewise polyline read as artificial kinks.
    if (sweep && sweep.freqs_mhz.length > 1) {
      const hasMulti =
        !!sweep.feeds_z_re &&
        !!sweep.feeds_z_im &&
        sweep.feeds_z_re.length === sweep.freqs_mhz.length &&
        sweep.feeds_z_re[0].length > 1;
      const nFeeds = hasMulti ? sweep.feeds_z_re![0].length : 1;

      // Z accessor per (feed index, sample index). Single-feed falls
      // back to the top-level z_re/z_im (same as before this change).
      const zAt = (fi: number, i: number) =>
        hasMulti
          ? { re: sweep.feeds_z_re![i][fi], im: sweep.feeds_z_im![i][fi] }
          : { re: sweep.z_re[i], im: sweep.z_im[i] };

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, 2 * Math.PI);
      ctx.clip();
      for (let fi = 0; fi < nFeeds; fi++) {
        // Darkened color so the sweep cloud reads as a trail underneath
        // the bright current-Z primary marker (drawn later, full color).
        // Same convention for single- and multi-feed so the chart's
        // visual grammar is uniform.
        ctx.fillStyle = feedSweepColor(fi);
        for (let i = 0; i < sweep.freqs_mhz.length; i++) {
          const z = zAt(fi, i);
          const g = reflectionCoefficient(z.re, z.im, z0);
          const px = cx + g.gRe * R;
          const py = cy - g.gIm * R;
          ctx.beginPath();
          ctx.arc(px, py, 1.5, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
      ctx.restore();

      // Endpoint markers per feed (low-freq filled, high-freq hollow) —
      // also drawn in the darkened sweep color so they stay part of the
      // trail and don't compete with the bright current-Z marker.
      const drawEndpoint = (fi: number, idx: number, filled: boolean) => {
        const z = zAt(fi, idx);
        const g = reflectionCoefficient(z.re, z.im, z0);
        const px = cx + g.gRe * R;
        const py = cy - g.gIm * R;
        const col = feedSweepColor(fi);
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = col;
        ctx.fillStyle = filled ? col : `rgba(${PC.bgRgb}, 0.95)`;
        ctx.beginPath();
        ctx.arc(px, py, 3, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      };
      for (let fi = 0; fi < nFeeds; fi++) {
        drawEndpoint(fi, 0, true);
        drawEndpoint(fi, sweep.freqs_mhz.length - 1, false);
      }

      // Freq range label across the bottom of the panel.
      ctx.fillStyle = PC.labelBright;
      ctx.font = "10px ui-monospace, monospace";
      const fLoTxt = sweep.freqs_mhz[0].toFixed(2);
      const fHiTxt = sweep.freqs_mhz[sweep.freqs_mhz.length - 1].toFixed(2);
      const txt = `${fLoTxt} → ${fHiTxt} MHz`;
      ctx.fillText(txt, size - 6 - ctx.measureText(txt).width, size - 6);

    }

    if (running) {
      ctx.fillStyle = PC.label;
      ctx.font = "10px ui-monospace, monospace";
      ctx.fillText("sweeping…", 6, size - 6);
    }

    // Convergence locus: Z(N) trajectory as N increases, drawn as a
    // connected polyline per feed so the sequence direction reads as
    // motion (vs. the freq sweep's unconnected scatter). Each feed gets
    // its own bright color from the feed palette — the line shape
    // distinguishes the convergence trail from the scattered freq-sweep
    // dots, and the bright-vs-dim brightness distinguishes the bright
    // current-Z marker from the trail's interior dots. Smallest-N point
    // gets a hollow ring; largest-N gets a filled disc; Richardson-
    // extrapolated Z* gets a diamond (primary feed only).
    if (converge && converge.n_values.length >= 1) {
      const cHasMulti =
        !!converge.feeds_z_re &&
        !!converge.feeds_z_im &&
        converge.feeds_z_re.length === converge.n_values.length &&
        converge.feeds_z_re[0].length > 1;
      const cNFeeds = cHasMulti ? converge.feeds_z_re![0].length : 1;
      const czAt = (fi: number, i: number) =>
        cHasMulti
          ? { re: converge.feeds_z_re![i][fi], im: converge.feeds_z_im![i][fi] }
          : { re: converge.z_re[i], im: converge.z_im[i] };

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, 2 * Math.PI);
      ctx.clip();
      for (let fi = 0; fi < cNFeeds; fi++) {
        ctx.strokeStyle = feedColor(fi);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        for (let i = 0; i < converge.n_values.length; i++) {
          const z = czAt(fi, i);
          const g = reflectionCoefficient(z.re, z.im, z0);
          const px = cx + g.gRe * R;
          const py = cy - g.gIm * R;
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();

        // Per-N dots along the trajectory.
        ctx.fillStyle = feedColor(fi);
        for (let i = 0; i < converge.n_values.length; i++) {
          const z = czAt(fi, i);
          const g = reflectionCoefficient(z.re, z.im, z0);
          const px = cx + g.gRe * R;
          const py = cy - g.gIm * R;
          ctx.beginPath();
          ctx.arc(px, py, 1.8, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
      ctx.restore();

      // Endpoint markers per feed: smallest-N hollow, largest-N filled.
      const drawNEndpoint = (fi: number, idx: number, filled: boolean) => {
        const z = czAt(fi, idx);
        const g = reflectionCoefficient(z.re, z.im, z0);
        const px = cx + g.gRe * R;
        const py = cy - g.gIm * R;
        const col = feedColor(fi);
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = col;
        ctx.fillStyle = filled ? col : `rgba(${PC.bgRgb}, 0.95)`;
        ctx.beginPath();
        ctx.arc(px, py, 3, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
      };
      for (let fi = 0; fi < cNFeeds; fi++) {
        drawNEndpoint(fi, 0, false);
        drawNEndpoint(fi, converge.n_values.length - 1, true);
      }

      // Richardson Z* markers — one diamond per feed, each in the
      // matching bright feed color so the user can tell which trail
      // extrapolates to which Z*. The diamond shape distinguishes the
      // extrapolated value from the actual sampled per-N dots (small
      // circles) and from the current-Z marker (larger outlined dot).
      const drawExtrap = (
        fi: number,
        zRe: number | null,
        zIm: number | null,
      ) => {
        if (zRe == null || zIm == null) return;
        const ge = reflectionCoefficient(zRe, zIm, z0);
        // Clip to the unit Smith disc — Richardson on a not-yet-converging
        // series can fly outside |Γ|=1 in early frames.
        const gMag = Math.hypot(ge.gRe, ge.gIm);
        const k = gMag > 0.98 ? 0.98 / gMag : 1;
        const px = cx + ge.gRe * R * k;
        const py = cy - ge.gIm * R * k;
        ctx.save();
        ctx.translate(px, py);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = feedColor(fi);
        ctx.strokeStyle = feedColor(fi, 1.0);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.rect(-4, -4, 8, 8);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      };
      if (cHasMulti && converge.feeds_z_re_extrap && converge.feeds_z_im_extrap) {
        for (let fi = 0; fi < cNFeeds; fi++) {
          drawExtrap(
            fi,
            converge.feeds_z_re_extrap[fi],
            converge.feeds_z_im_extrap[fi],
          );
        }
      } else {
        drawExtrap(0, converge.z_re_extrap, converge.z_im_extrap);
      }

    }
    if (convergeRunning) {
      ctx.fillStyle = PC.label;
      ctx.font = "10px ui-monospace, monospace";
      // Stack under the freq-sweep status if both are running.
      const yOff = running ? 18 : 6;
      ctx.fillText("converging…", 6, size - yOff);
    }

    // Current impedance marker(s). One bright dot per feed in the
    // matching feed color, with a thin dark outline for visibility on
    // top of the sweep cloud. Single- and multi-feed share this code
    // path so the chart's visual grammar is uniform: dim color = trail
    // (freq sweep), bright = "you are here." The previous golden +
    // glow + line-from-centre treatment for single-feed is gone —
    // single-feed and feed-0-of-multi-feed now look identical.
    const markerPoints: Array<{ re: number; im: number; fi: number }> =
      feeds && feeds.length > 0
        ? feeds.map((f, fi) => ({ re: f.z_re, im: f.z_im, fi }))
        : r > 0 || x !== 0
          ? [{ re: r, im: x, fi: 0 }]
          : [];
    for (const m of markerPoints) {
      if (m.re <= 0 && m.im === 0) continue;
      const { gRe, gIm } = reflectionCoefficient(m.re, m.im, z0);
      const px = cx + gRe * R;
      const py = cy - gIm * R;
      ctx.fillStyle = feedColor(m.fi);
      ctx.beginPath();
      ctx.arc(px, py, 4, 0, 2 * Math.PI);
      ctx.fill();
      ctx.strokeStyle = `rgba(${PC.bgRgb}, 0.85)`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Top-left summary: one row per feed (when multi-feed) or one row
    // total (single-feed). Each row gets:
    //   [dim swatch][bright swatch]  feed N  Z* ≈ R + jX Ω
    // Both swatches encode the per-feed color (dim = freq-sweep trail,
    // bright = current-Z marker / convergence trail). Z* tacks on
    // inline in the matching bright color when ≥3 converge samples
    // have come in, so each trail has its own visibly-colored Z*
    // readout next to its swatch — replacing the old single purple
    // Z* line that only tracked feeds[0].
    const summaryFeeds: Array<{
      fi: number;
      extrapRe: number | null;
      extrapIm: number | null;
    }> = [];
    if (multiFeed && feeds && feeds.length > 1) {
      for (let fi = 0; fi < feeds.length; fi++) {
        const re = converge?.feeds_z_re_extrap?.[fi] ?? null;
        const im = converge?.feeds_z_im_extrap?.[fi] ?? null;
        summaryFeeds.push({ fi, extrapRe: re, extrapIm: im });
      }
    } else if (converge && converge.n_values.length >= 1) {
      summaryFeeds.push({
        fi: 0,
        extrapRe: converge.z_re_extrap,
        extrapIm: converge.z_im_extrap,
      });
    } else if (feeds && feeds.length === 1) {
      // Sweep-only single-feed run: show the swatch row so the colors
      // on the chart are explained even without a converge.
      summaryFeeds.push({ fi: 0, extrapRe: null, extrapIm: null });
    }
    if (summaryFeeds.length > 0) {
      ctx.font = "10px ui-monospace, monospace";
      for (let row = 0; row < summaryFeeds.length; row++) {
        const { fi, extrapRe, extrapIm } = summaryFeeds[row];
        const ly = 12 + row * 14;
        // Dim swatch (sweep trail color).
        ctx.fillStyle = feedSweepColor(fi);
        ctx.beginPath();
        ctx.arc(12, ly, 3, 0, 2 * Math.PI);
        ctx.fill();
        // Bright swatch (current-Z / convergence-trail color).
        ctx.fillStyle = feedColor(fi);
        ctx.beginPath();
        ctx.arc(20, ly, 3, 0, 2 * Math.PI);
        ctx.fill();
        // Feed label + inline Z* (when extrap available). Text color
        // matches the bright feed color so the row's color identity
        // ties back to the chart trails for that feed.
        ctx.fillStyle = feedColor(fi);
        let txt =
          summaryFeeds.length > 1 ? `feed ${fi}` : "";
        if (extrapRe != null && extrapIm != null) {
          const sign = extrapIm >= 0 ? "+" : "−";
          const zText = `Z* ≈ ${extrapRe.toFixed(2)} ${sign} j${Math.abs(extrapIm).toFixed(2)} Ω`;
          txt = txt ? `${txt}  ${zText}` : zText;
        }
        if (txt) ctx.fillText(txt, 28, ly + 3);
      }
    }

    // Bottom-left: N-range stays neutral since it's per-converge not
    // per-feed. Sits above the converging / sweeping status indicators.
    if (converge && converge.n_values.length >= 1) {
      const nLo = converge.n_values[0];
      const nHi = converge.n_values[converge.n_values.length - 1];
      ctx.fillStyle = PC.labelBright;
      ctx.font = "10px ui-monospace, monospace";
      const baseY = running && convergeRunning ? size - 30
        : running || convergeRunning ? size - 18
        : size - 6;
      ctx.fillText(`N: ${nLo} → ${nHi}`, 6, baseY);
    }

    // Center match marker
    ctx.strokeStyle = PC.centerMark;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 4, cy);
    ctx.lineTo(cx + 4, cy);
    ctx.moveTo(cx, cy - 4);
    ctx.lineTo(cx, cy + 4);
    ctx.stroke();
    // multiFeed is captured in the closure; without it in the deps the
    // chart wouldn't redraw when the descriptor flag flips from its
    // initial false to the real /examples value (true for bowtie /
    // hexbeam_5band) — the user saw only one Z* annotation in the
    // legend because the closure stayed wedged on the single-feed branch.
  }, [r, x, z0, size, sweep, converge, measFreqMhz, running, convergeRunning, feeds, multiFeed, theme]);

  return <canvas ref={canvasRef} className="smith" />;
}

// Viewport zoom ceiling. The motivating case (elt_whip, #384) hides 6.35 mm
// of cage detail inside a 2.44 m extent — a 1:384 scale gap — so the ceiling
// leaves an order of magnitude of headroom past "inspect the finest catalog
// detail at canvas size".
const VIEWPORT_ZOOM_MAX = 10000;

function CurrentCanvas({
  result,
  projection,
  showHeatmap,
  showEnvelope,
  showWireLabels,
  showFeedNames,
  interactive = false,
}: {
  result: SolveResponse | null;
  projection: Projection;
  showHeatmap: boolean;
  showEnvelope: boolean;
  showWireLabels: boolean;
  showFeedNames: boolean;
  // Zoom/pan navigation — main stage only; thumbnails stay inert buttons.
  interactive?: boolean;
}) {
  const theme = useContext(ThemeContext); // repaint on theme toggle (dep below)
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Viewport navigation (map-style: cursor-anchored wheel/pinch zoom, drag
  // pan, double-click/tap or the Fit button to re-fit — survey in PR #384).
  // zoom=1, pan=0 IS the auto-fit view, so the fit framing keeps tracking
  // knob drags and re-solves; zoom composes on top as a pure multiplier.
  // Lives in a ref (mutated at pointer-event rate, drawn via rAF) with a
  // React mirror of the zoom level for the HUD chip / touch-action gate.
  const vpRef = useRef({ zoom: 1, panX: 0, panY: 0 });
  const [vpZoom, setVpZoom] = useState(1);
  const redrawRef = useRef<() => void>(() => {});
  const resetViewport = () => {
    vpRef.current = { zoom: 1, panX: 0, panY: 0 };
    setVpZoom(1);
  };

  // The fit frame of the last completed draw (projection + fit centre/scale).
  // A projection switch carries the viewport over through it — see draw() —
  // instead of resetting, so a feature under 400× inspection stays under
  // inspection when the view turns. Cleared on design switch: the previous
  // design's frame means nothing for the new geometry.
  const frameRef = useRef<{
    projection: Projection;
    hC: number;
    vC: number;
    scale: number;
  } | null>(null);

  // Switching DESIGNS re-fits: the viewport was aimed at the old geometry.
  // (Projection switches within a design carry the viewport — see draw().)
  const geometryName = result?.geometry ?? "";
  useEffect(() => {
    resetViewport();
    frameRef.current = null;
    // The main draw effect below re-runs on any new result, so the re-fit
    // paints without an explicit redraw.
  }, [geometryName]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const PC = plotColors();
    const onResize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    };

    function draw() {
      if (!canvas) return;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx!.clearRect(0, 0, w, h);

      // Vertical axis guide.
      ctx!.strokeStyle = PC.axisFaint;
      ctx!.lineWidth = 1;
      ctx!.beginPath();
      ctx!.moveTo(w / 2, 20);
      ctx!.lineTo(w / 2, h - 20);
      ctx!.stroke();

      if (!result) return;

      // Scale anchored to design wavelength. Worst-case extents (in λ):
      //   horizontal: hf_max × λ/2 ≈ 0.6 λ  (both V and Yagi)
      //   vertical:   max(V droop, Yagi spacing) ≈ 0.5 λ
      //
      // `s` proportionally shrinks every fixed pixel constant (padding,
      // strokes, envelope amplitude, label sizes) so the rendering looks
      // the same at thumbnail and main sizes. Floor keeps thumbnails
      // legible; cap prevents very-large canvases from over-inflating.
      const refSize = 600;
      const s = Math.max(0.3, Math.min(1.4, Math.min(w, h) / refSize));
      const lambdaDesign = result.lambda_design_m;
      const pad = 50 * s;
      const barReserveBottom = 40 * s;
      const FILL = 0.85;

      // Camera projection: an orthonormal screen basis (see PROJECTIONS) —
      // world point p lands at canvas (h·p, v·p); the camera ray is h×v.
      // App.tsx sets a per-geometry default (V/fan_dipole → "yz" side,
      // Yagi/moxon/hexbeam → "xy" top) but the user can override via the
      // projection toggle in the stage.
      const projSpec = PROJECTIONS.find((p) => p.id === projection)!;
      const hVec = projSpec.h;
      const vVec = projSpec.v;
      // True for the two elevation views (screen-up IS world z), which gates
      // the ground reference line below; the isometric's tilted up-vector
      // draws no line (z=0 doesn't project to a horizontal line there).
      const upIsZ = vVec[0] === 0 && vVec[1] === 0 && vVec[2] === 1;
      let hMin = Infinity, hMax = -Infinity;
      let vMin = Infinity, vMax = -Infinity;
      // Axis-aligned world bbox too — the projection-switch carry-over needs
      // a depth estimate along the old camera ray (see below).
      const bbMin = [Infinity, Infinity, Infinity];
      const bbMax = [-Infinity, -Infinity, -Infinity];
      for (const wire of result.wires) {
        for (const p of wire.knot_positions) {
          const ph = dot3(hVec, p);
          const pv = dot3(vVec, p);
          if (ph < hMin) hMin = ph;
          if (ph > hMax) hMax = ph;
          if (pv < vMin) vMin = pv;
          if (pv > vMax) vMax = pv;
          for (let a = 0; a < 3; a++) {
            if (p[a] < bbMin[a]) bbMin[a] = p[a];
            if (p[a] > bbMax[a]) bbMax[a] = p[a];
          }
        }
      }

      // When ground is enabled and screen-up is world z, expand the visible
      // vertical range to include z=0 so the ground reference line lands
      // inside the canvas. Without this, antennas sitting well above the
      // plane push the ground line off-screen.
      let vEffMin = vMin, vEffMax = vMax;
      if (result.ground && upIsZ) {
        vEffMin = Math.min(vMin, 0);
        vEffMax = Math.max(vMax, 0);
      }
      // Vertical span used to size the canvas. Floor at the wavelength
      // worst-case so small antennas don't render comically large; grow with
      // the ground-adjusted antenna span so high antennas zoom out enough
      // to fit the ground line.
      const vSpanEff = Math.max(vEffMax - vEffMin, 0.5 * lambdaDesign);
      // Horizontal span: same floor-with-actual-extent pattern as vertical.
      // The 0.6λ floor covers the typical V / Yagi worst case; wider
      // antennas (EDZ at ~1.5λ, fan-dipole 5-band, ...) grow the span
      // from their actual hMax-hMin so they fit on canvas.
      const hSpanEff = Math.max(hMax - hMin, 0.6 * lambdaDesign);
      const scale = FILL * Math.min(
        (w - 2 * pad) / hSpanEff,
        (h - pad - barReserveBottom) / vSpanEff,
      );

      const hC = (hMin + hMax) / 2;
      const vC = (vEffMin + vEffMax) / 2;
      const cx = w / 2;
      const cy = h / 2;
      const vp = vpRef.current;

      // Projection switch with an active zoom: carry the viewport over
      // instead of resetting. Reconstruct the world point at the old canvas
      // centre — its two screen coordinates from the old frame, its depth
      // along the old camera ray from the geometry point nearest that
      // centre ray (the wire actually under inspection; the bbox centre
      // would misplace anything off-centre in depth, e.g. an apex feed) —
      // then aim the new frame at that point, preserving the absolute px/m
      // scale so the feature keeps its on-screen size (each view has its
      // own fit scale, so the relative zoom factor is rescaled). If the
      // carried zoom clamps to 1, it degrades to a plain fit. Design
      // switches still hard-reset (frameRef is cleared by the effect above).
      const frame = frameRef.current;
      if (frame && frame.projection !== projection && vp.zoom > 1) {
        const old = PROJECTIONS.find((p) => p.id === frame.projection)!;
        const oldZscale = frame.scale * vp.zoom;
        const hCtr = frame.hC - vp.panX / oldZscale;
        const vCtr = frame.vC + vp.panY / oldZscale;
        const n = cross3(old.h, old.v);
        let depth = dot3(n, [
          (bbMin[0] + bbMax[0]) / 2,
          (bbMin[1] + bbMax[1]) / 2,
          (bbMin[2] + bbMax[2]) / 2,
        ]);
        let best = Infinity;
        for (const wire of result.wires) {
          for (const p of wire.knot_positions) {
            const dh = dot3(old.h, p) - hCtr;
            const dv = dot3(old.v, p) - vCtr;
            const d2 = dh * dh + dv * dv;
            if (d2 < best) {
              best = d2;
              depth = dot3(n, p);
            }
          }
        }
        const P: Vec3 = [
          old.h[0] * hCtr + old.v[0] * vCtr + n[0] * depth,
          old.h[1] * hCtr + old.v[1] * vCtr + n[1] * depth,
          old.h[2] * hCtr + old.v[2] * vCtr + n[2] * depth,
        ];
        const zoomNew = Math.min(
          VIEWPORT_ZOOM_MAX,
          Math.max(1, (vp.zoom * frame.scale) / scale),
        );
        vp.zoom = zoomNew;
        if (zoomNew > 1) {
          const zs = scale * zoomNew;
          vp.panX = (hC - dot3(hVec, P)) * zs;
          vp.panY = (dot3(vVec, P) - vC) * zs;
        } else {
          vp.panX = 0;
          vp.panY = 0;
        }
        setVpZoom(zoomNew);
      }
      frameRef.current = { projection, hC, vC, scale };

      // Compose the user viewport on top of the fit framing. Only geometry
      // goes through `zscale`; pixel-sized glyphs (strokes, labels, envelope
      // amplitude, feed dot) stay on `s`, so zooming magnifies the antenna
      // without ballooning its annotations.
      const zscale = scale * vp.zoom;
      const project = (p: [number, number, number]) => ({
        x: cx + (dot3(hVec, p) - hC) * zscale + vp.panX,
        y: cy + (vC - dot3(vVec, p)) * zscale + vp.panY, // higher vert value = higher on screen
      });

      // Ground reference line at world z=0, drawn only on the elevation
      // views (screen-up is world z) when the backend has ground enabled.
      // Cosmetic — the math is correct regardless; this just removes the
      // "where is the ground" guessing game from the side view. vC was
      // adjusted above to keep this on-canvas, so no bounds check needed
      // here.
      if (result.ground && upIsZ) {
        const groundY = cy + vC * zscale + vp.panY;
        ctx!.strokeStyle = `rgba(${PC.groundRgb}, 0.55)`;
        ctx!.lineWidth = 1;
        ctx!.setLineDash([6, 4]);
        ctx!.beginPath();
        ctx!.moveTo(0, groundY);
        ctx!.lineTo(w, groundY);
        ctx!.stroke();
        ctx!.setLineDash([]);
        ctx!.fillStyle = `rgba(${PC.groundRgb}, 0.85)`;
        ctx!.font = `${Math.max(8, Math.round(10 * s))}px ui-monospace, monospace`;
        ctx!.fillText("ground (z = 0)", 8 * s, groundY - 4 * s);
      }

      // Global current magnitude — use sample arrays when available so the
      // shared color scale catches mid-segment peaks (B-spline d=2 quadratic
      // curvature, sinusoidal three-term, B-spline enrichment dip). Falls
      // back to knot arrays for backends that don't ship samples (PyNEC).
      let magMaxGlobal = 1e-30;
      const perWirePts: [number, number, number][][] = [];
      const perWireMags: number[][] = [];
      for (const wire of result.wires) {
        const pts = wire.sample_positions ?? wire.knot_positions;
        const cre = wire.sample_currents_re ?? wire.knot_currents_re;
        const cim = wire.sample_currents_im ?? wire.knot_currents_im;
        const m = cre.map((r, i) => Math.hypot(r, cim[i]));
        perWirePts.push(pts);
        perWireMags.push(m);
        for (const v of m) if (v > magMaxGlobal) magMaxGlobal = v;
      }

      ctx!.lineCap = "round";
      ctx!.lineJoin = "round";

      // One wire at a time: wire stroke + envelope.
      const envScale = 60 * s;
      const labelFontPx = Math.max(8, Math.round(11 * s));
      const feedFontPx = Math.max(8, Math.round(12 * s));
      const feedWireIdx = result.feed_wire_index;
      for (let wi = 0; wi < result.wires.length; wi++) {
        const wire = result.wires[wi];
        const pts = perWirePts[wi];
        const mags = perWireMags[wi];

        for (let i = 0; i < pts.length - 1; i++) {
          const a = project(pts[i]);
          const b = project(pts[i + 1]);
          if (showHeatmap) {
            const m = (0.5 * (mags[i] + mags[i + 1])) / magMaxGlobal;
            ctx!.strokeStyle = currentColor(m);
            ctx!.lineWidth = (2 + 6 * m) * s;
          } else {
            // Plain wires: uniform color/width, no current-magnitude modulation.
            ctx!.strokeStyle = PC.labelBright;
            ctx!.lineWidth = 2 * s;
          }
          ctx!.beginPath();
          ctx!.moveTo(a.x, a.y);
          ctx!.lineTo(b.x, b.y);
          ctx!.stroke();
        }

        // Current-waveform envelope: if this is the feed wire (and the feed
        // isn't at an end), split at the feed knot so a V's per-arm tangent
        // flip is respected. Otherwise draw one continuous envelope.
        // feed_knot_index lives in knot-array space; in sample space (knots
        // interleaved with midpoints) it maps to 2*feed_knot_index.
        if (showEnvelope) {
          ctx!.strokeStyle = `rgba(${PC.envelopeRgb}, 0.7)`;
          ctx!.lineWidth = 1.5 * s;
          const lastIdx = pts.length - 1;
          const hasSamples = wire.sample_positions != null;
          const feedIdx = result.feed_knot_index * (hasSamples ? 2 : 1);
          if (wi === feedWireIdx && feedIdx > 0 && feedIdx < lastIdx) {
            drawArmEnvelope(ctx!, pts, mags, magMaxGlobal, project, 0, feedIdx, envScale);
            drawArmEnvelope(ctx!, pts, mags, magMaxGlobal, project, feedIdx, lastIdx, envScale);
          } else {
            drawArmEnvelope(ctx!, pts, mags, magMaxGlobal, project, 0, lastIdx, envScale);
          }
        }

        // Wire label near the leftmost knot for multi-wire geometries.
        if (showWireLabels && result.wires.length > 1) {
          const lp = project(wire.knot_positions[0]);
          ctx!.fillStyle = PC.label;
          ctx!.font = `${labelFontPx}px ui-monospace, monospace`;
          ctx!.fillText(wire.label, lp.x - 8 * s - ctx!.measureText(wire.label).width, lp.y + 3 * s);
        }
      }

      // Feed marker(s). Multi-feed geometries (bowtie 1×2 array) expose
      // a `feeds[]` array — render one yellow dot per feed and label with
      // the prescribed voltage phase. Single-feed geometries fall through
      // to the legacy feed_wire_index / feed_knot_index path.
      const feedList = result.feeds && result.feeds.length > 0
        ? result.feeds
        : [{
            wire_index: feedWireIdx,
            knot_index: result.feed_knot_index,
            feed_position: result.feed_position,
            v_re: 1, v_im: 0,
            z_re: result.z_in_re, z_im: result.z_in_im,
          }];
      for (let fi = 0; fi < feedList.length; fi++) {
        const f = feedList[fi];
        const w_ = result.wires[f.wire_index];
        // Prefer the exact feed point; fall back to the nearest knot.
        const pos3d = f.feed_position ?? (w_ ? w_.knot_positions[f.knot_index] : undefined);
        if (!pos3d) continue;
        const feed = project(pos3d);
        ctx!.fillStyle = PC.feed;
        ctx!.beginPath();
        ctx!.arc(feed.x, feed.y, 5 * s, 0, Math.PI * 2);
        ctx!.fill();
        if (showFeedNames) {
          ctx!.font = `${feedFontPx}px ui-monospace, monospace`;
          const label = feedList.length > 1
            ? `feed ${fi} ∠${Math.round(Math.atan2(f.v_im, f.v_re) * 180 / Math.PI)}°`
            : "feed";
          ctx!.fillText(label, feed.x + 8 * s, feed.y - 8 * s);
        }
      }

      // Scale bar, centered horizontally under the antenna. At fit zoom it
      // is the familiar λ/4 bar; once zoomed, λ/4 no longer fits on screen,
      // so it becomes a map-style bar: a nice round length (1/2/5 × 10^k m)
      // near a quarter of the canvas width, always true to `zscale`.
      let barWorld = lambdaDesign / 4;
      let barLabel = `λ/4 = ${(lambdaDesign / 4).toFixed(2)} m`;
      if (vp.zoom !== 1) {
        const target = (0.25 * w) / zscale;
        const pow = Math.pow(10, Math.floor(Math.log10(target)));
        const mant = target / pow;
        barWorld = (mant >= 5 ? 5 : mant >= 2 ? 2 : 1) * pow;
        barLabel = formatMetres(barWorld);
      }
      const barLenPx = barWorld * zscale;
      const barX0 = (w - barLenPx) / 2;
      const barY = h - 24 * s;
      ctx!.strokeStyle = PC.label;
      ctx!.lineWidth = 1;
      ctx!.beginPath();
      ctx!.moveTo(barX0, barY);
      ctx!.lineTo(barX0 + barLenPx, barY);
      ctx!.moveTo(barX0, barY - 4 * s);
      ctx!.lineTo(barX0, barY + 4 * s);
      ctx!.moveTo(barX0 + barLenPx, barY - 4 * s);
      ctx!.lineTo(barX0 + barLenPx, barY + 4 * s);
      ctx!.stroke();
      ctx!.fillStyle = PC.labelBright;
      ctx!.font = `${labelFontPx}px ui-monospace, monospace`;
      const labelW = ctx!.measureText(barLabel).width;
      ctx!.fillText(barLabel, (w - labelW) / 2, barY - 8 * s);
    }

    onResize();
    const obs = new ResizeObserver(onResize);
    obs.observe(canvas);
    redrawRef.current = draw;
    if (!interactive) return () => obs.disconnect();

    // ---- viewport navigation ------------------------------------------
    // Draws coalesce to one per frame: pointer/wheel events mutate vpRef
    // and schedule a rAF repaint.
    let raf = 0;
    const scheduleDraw = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        draw();
      });
    };

    // Zoom by `factor` keeping the canvas point (ax, ay) fixed — the world
    // point under the cursor/pinch centre stays under it. Zooming all the
    // way back out lands exactly on the fit view (pan snaps to 0).
    const applyZoom = (factor: number, ax: number, ay: number) => {
      const v = vpRef.current;
      const z = Math.min(VIEWPORT_ZOOM_MAX, Math.max(1, v.zoom * factor));
      const f = z / v.zoom;
      const cx = canvas.clientWidth / 2;
      const cy = canvas.clientHeight / 2;
      v.panX = ax - cx - (ax - cx - v.panX) * f;
      v.panY = ay - cy - (ay - cy - v.panY) * f;
      v.zoom = z;
      if (z === 1) {
        v.panX = 0;
        v.panY = 0;
      }
      setVpZoom(z);
      scheduleDraw();
    };

    // Wheel zoom, ~1.2× per detent, exponential so trackpads feel smooth.
    // Native non-passive listener for the same reason as the VFO dial:
    // React's onWheel can't preventDefault the page scroll.
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const dy = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY; // line-mode → px
      applyZoom(Math.exp(-dy * 0.002), e.clientX - rect.left, e.clientY - rect.top);
    };

    // Pointer state: one pointer drags (pan — only when zoomed, so at fit a
    // touch drag stays with the mobile carousel swipe), two pinch-zoom.
    const pointers = new Map<number, { x: number; y: number; downX: number; downY: number }>();
    let moved = false;
    let lastTap = { t: 0, x: 0, y: 0 };
    const posOf = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };

    const onPointerDown = (e: PointerEvent) => {
      if (e.pointerType === "mouse" && e.button !== 0 && e.button !== 1) return;
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        // Capture is best-effort: a drag that leaves the canvas just ends.
      }
      const p = posOf(e);
      pointers.set(e.pointerId, { ...p, downX: p.x, downY: p.y });
      moved = false;
      if (e.pointerType === "mouse") e.preventDefault(); // middle-click autoscroll
    };

    const onPointerMove = (e: PointerEvent) => {
      const prev = pointers.get(e.pointerId);
      if (!prev) return;
      const p = posOf(e);
      if (Math.hypot(p.x - prev.downX, p.y - prev.downY) > 4) moved = true;
      if (pointers.size === 2) {
        // Pinch: translate by the midpoint delta, zoom by the distance
        // ratio about the new midpoint.
        const other = [...pointers.entries()].find(([id]) => id !== e.pointerId)![1];
        const oldMid = { x: (prev.x + other.x) / 2, y: (prev.y + other.y) / 2 };
        const oldDist = Math.hypot(prev.x - other.x, prev.y - other.y) || 1;
        const newMid = { x: (p.x + other.x) / 2, y: (p.y + other.y) / 2 };
        const newDist = Math.hypot(p.x - other.x, p.y - other.y) || 1;
        const v = vpRef.current;
        v.panX += newMid.x - oldMid.x;
        v.panY += newMid.y - oldMid.y;
        applyZoom(newDist / oldDist, newMid.x, newMid.y);
      } else if (pointers.size === 1 && vpRef.current.zoom > 1) {
        const v = vpRef.current;
        v.panX += p.x - prev.x;
        v.panY += p.y - prev.y;
        scheduleDraw();
      }
      pointers.set(e.pointerId, { ...prev, x: p.x, y: p.y });
    };

    const onPointerUp = (e: PointerEvent) => {
      const had = pointers.delete(e.pointerId);
      try {
        canvas.releasePointerCapture(e.pointerId);
      } catch {
        // Never captured (see above) — nothing to release.
      }
      if (!had || moved || e.type === "pointercancel") return;
      // Clean tap/click: double within 350 ms & 30 px re-fits.
      const now = performance.now();
      const p = posOf(e);
      if (now - lastTap.t < 350 && Math.hypot(p.x - lastTap.x, p.y - lastTap.y) < 30) {
        resetViewport();
        scheduleDraw();
        lastTap = { t: 0, x: 0, y: 0 };
      } else {
        lastTap = { t: now, x: p.x, y: p.y };
      }
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    return () => {
      obs.disconnect();
      if (raf) cancelAnimationFrame(raf);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
    };
  }, [result, projection, showHeatmap, showEnvelope, showWireLabels, showFeedNames, theme, interactive]);

  const zoomed = vpZoom > 1.001;
  return (
    <div className="canvas-viewport">
      <canvas
        ref={canvasRef}
        style={
          interactive
            ? {
                // At fit, touch drags belong to the page (mobile carousel
                // swipe); pinch is never a browser gesture here, so a
                // two-finger zoom always reaches us. Once zoomed, the canvas
                // owns all touches for panning until re-fit.
                touchAction: zoomed ? "none" : "pan-x pan-y",
                cursor: zoomed ? "grab" : "zoom-in",
              }
            : undefined
        }
      />
      {interactive && (
        <div className="viewport-hud">
          {zoomed && (
            <span className="viewport-zoom">
              {vpZoom >= 10 ? Math.round(vpZoom) : vpZoom.toFixed(1)}×
            </span>
          )}
          <button
            className="viewport-fit"
            disabled={!zoomed}
            onClick={() => {
              resetViewport();
              redrawRef.current();
            }}
            title="Zoom to fit (or double-click the canvas)"
          >
            Fit
          </button>
        </div>
      )}
    </div>
  );
}

// Nice-number lengths for the zoomed scale bar: pick the readable unit and
// trim float dust (5×10⁻³ m × 1000 → "5 mm", not "5.000000000000001 mm").
function formatMetres(v: number): string {
  const fmt = (x: number, unit: string) => `${parseFloat(x.toPrecision(2))} ${unit}`;
  if (v >= 1) return fmt(v, "m");
  if (v >= 0.01) return fmt(v * 100, "cm");
  return fmt(v * 1000, "mm");
}

function drawArmEnvelope(
  ctx: CanvasRenderingContext2D,
  knots: [number, number, number][],
  mags: number[],
  magMax: number,
  project: (p: [number, number, number]) => { x: number; y: number },
  start: number,
  end: number,
  envScale: number,
) {
  if (end <= start) return;

  // Per-segment normal in canvas space, oriented toward screen-up so V-style
  // arms put their envelopes "above" the wire. For axis-aligned vertical
  // segments ny is exactly zero and the flip is a no-op; that's fine — what
  // matters is that the moxon's adjacent perpendicular segments get
  // *different* normals so the bend-break below catches the corner.
  const segN: { nx: number; ny: number }[] = [];
  for (let i = start; i < end; i++) {
    const p = project(knots[i]);
    const q = project(knots[i + 1]);
    const dx = q.x - p.x;
    const dy = q.y - p.y;
    const len = Math.hypot(dx, dy) || 1;
    let nx = -dy / len;
    let ny = dx / len;
    if (ny > 0) {
      nx = -nx;
      ny = -ny;
    }
    segN.push({ nx, ny });
  }

  // Walk runs of segments whose normals agree (within ~3°), and start a new
  // sub-path at each bend. Without this, a connected envelope at a 90°
  // corner zigzags across the corner since the two adjacent segments offset
  // their knots in perpendicular directions.
  const BEND_TOL = 0.9986;  // cos(3°)
  ctx.beginPath();
  let s = 0;
  while (s < segN.length) {
    let e = s;
    while (
      e + 1 < segN.length &&
      segN[e].nx * segN[e + 1].nx + segN[e].ny * segN[e + 1].ny >= BEND_TOL
    ) {
      e++;
    }
    const { nx, ny } = segN[s];
    for (let k = s; k <= e + 1; k++) {
      const ki = start + k;
      const p = project(knots[ki]);
      const offset = (mags[ki] / magMax) * envScale;
      const ex = p.x + nx * offset;
      const ey = p.y + ny * offset;
      if (k === s) ctx.moveTo(ex, ey);
      else ctx.lineTo(ex, ey);
    }
    s = e + 1;
  }
  ctx.stroke();
}

// Plot colors are pulled from CSS custom properties so the <canvas>
// views theme from the same tokens as the DOM chrome. Fallbacks
// reproduce the original dark palette, so missing vars are harmless.
function plotColors() {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, fb: string): string => {
    const val = cs.getPropertyValue(name).trim();
    return val || fb;
  };
  return {
    bg: v("--plot-bg", "#0d1015"),
    bgRgb: v("--plot-bg-rgb", "13, 16, 21"),
    grid: v("--plot-grid", "#2a313d"),
    axis: v("--plot-axis", "#3a4150"),
    axisFaint: v("--plot-axis-faint", "#23272f"),
    labelDim: v("--plot-label-dim", "#4a5160"),
    label: v("--plot-label", "#7b8493"),
    labelBright: v("--plot-label-bright", "#9aa3b2"),
    labelStrong: v("--plot-label-strong", "#cdd5e0"),
    centerMark: v("--plot-center-mark", "#5a6170"),
    spoke: v("--plot-spoke", "rgba(180, 140, 250, 0.7)"),
    lobeRgb: v("--plot-lobe-rgb", "255, 209, 102"),
    necRgb: v("--plot-nec-rgb", "110, 220, 255"),
    groundRgb: v("--plot-ground-rgb", "140, 110, 70"),
    envelopeRgb: v("--plot-envelope-rgb", "118, 208, 255"),
    feed: v("--plot-feed", "#ffd166"),
  };
}

// Current-magnitude heatmap ramp, also CSS-driven. Read once and cached
// (currentColor runs per wire segment, so getComputedStyle must not be
// called in the loop). Fallbacks are the original cool->warm stops.
let _currentRampCache: [number, [number, number, number]][] | null = null;
function currentRamp(): [number, [number, number, number]][] {
  if (_currentRampCache) return _currentRampCache;
  const cs = getComputedStyle(document.documentElement);
  const tri = (name: string, fb: [number, number, number]): [number, number, number] => {
    const s = cs.getPropertyValue(name).trim();
    if (!s) return fb;
    const p = s.split(",").map((n) => parseInt(n.trim(), 10));
    return p.length === 3 && p.every((n) => !Number.isNaN(n)) ? [p[0], p[1], p[2]] : fb;
  };
  _currentRampCache = [
    [0.0, tri("--plot-current-0", [40, 64, 96])],
    [0.25, tri("--plot-current-1", [60, 140, 200])],
    [0.5, tri("--plot-current-2", [118, 208, 255])],
    [0.75, tri("--plot-current-3", [255, 209, 102])],
    [1.0, tri("--plot-current-4", [255, 130, 80])],
  ];
  return _currentRampCache;
}

function currentColor(t: number): string {
  // Cool → warm ramp: dim blue → cyan → yellow → orange.
  const stops = currentRamp();
  for (let i = 1; i < stops.length; i++) {
    const [t0, c0] = stops[i - 1];
    const [t1, c1] = stops[i];
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0 || 1);
      const r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
      const g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
      const b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
      return `rgb(${r},${g},${b})`;
    }
  }
  return "rgb(255,130,80)";
}
