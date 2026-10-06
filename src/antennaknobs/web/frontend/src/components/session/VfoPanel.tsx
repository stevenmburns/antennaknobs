import { BandDropdown } from "../params/BandDropdown";
import { Knob } from "../params/Knob";
import { useEffect, useRef, useState } from "react";
import type { BandSpec } from "../../lib/params";
import type { SweepRange } from "../../lib/sweep";
import { parseZo } from "../../lib/zoOverride";
import {
  BandsEditor,
  BandsReadout,
  type KeptReadout,
  type OptBandRecord,
  type OptBandsControl,
} from "./OptBands";
import { NO_READING } from "../../lib/optBands";

// The optimise popover opens downward from the rail. With the Bands section
// (AK#1901) it can be taller than the space left below its button, and it is
// absolutely positioned, so the rows past the window's bottom edge were
// unreachable. Cap it at the room left in the viewport and scroll inside.
function fitOptMenuToViewport(el: HTMLDivElement | null): void {
  if (!el) return;
  const room = window.innerHeight - el.getBoundingClientRect().top - 12;
  el.style.maxHeight = `${Math.max(160, Math.floor(room))}px`;
}

// Response from POST /optimize.
//
// The first four keys are always present. The rest appear only on a bare
// multi-feed design, where feed 0's `z_in` stops speaking for the array:
// `swr` is then the WORST feed's, the number the objective drives (#785),
// and `feeds` is every port's Z so the chart can draw the whole array
// mid-run (#789). Optional because a single-feed payload still omits them —
// that shape is byte-compatible on purpose and pinned server-side.
export type OptFeedZ = { z_re: number; z_im: number };
export type OptMetrics = {
  z_in_re: number;
  z_in_im: number;
  z0_ohms: number;
  swr: number;
  worst_feed?: number;
  n_feeds?: number;
  feeds?: OptFeedZ[];
};
export type OptimizeResult = {
  objective: string;
  params: Record<string, number>;
  objective_before: number;
  objective_after: number;
  metrics_before: OptMetrics;
  metrics_after: OptMetrics;
  n_evals: number;
  /** Which path ran (#1202): "secant", "nelder-mead", or a fallback naming
   *  why the root path stood down (e.g. "nelder-mead (root: no-sign-change)"). */
  method?: string;
  /** What a root-finder drove to zero, before and after. `null` for
   *  objectives that are not roots, and on multi-feed responses. */
  residual_before?: number | null;
  residual_after?: number | null;
  improved: boolean;
  /** A band run's (AK#1901, `objective: "bands"`): every band read at the
   *  start and at the answer, and the two terms of what it minimised. */
  bands_before?: OptBandRecord[];
  bands_after?: OptBandRecord[];
  // null = no reading (a non-finite value; the server sends null for those).
  objective_worst_before?: number | null;
  objective_worst_after?: number | null;
  objective_mean_before?: number | null;
  objective_mean_after?: number | null;
  mean_weight?: number;
  worst_swr_before?: number | null;
  worst_swr_after?: number | null;
  worst_band_before?: number;
  worst_band_after?: number;
  /** "time": the hosted time budget ended the run, and the answer is the
   *  best point solved by then (AK 0.97.1). */
  stopped?: string | null;
  time_budget_s?: number | null;
  /** Knobs that ended at a bound of their range (AK#1909). */
  at_bound?: { name: string; bound: "min" | "max"; value: number }[];
  /** No band is near a match at the answer (AK#1909). */
  far_from_match?: boolean;
};
// One `event: progress` frame from the streamed /optimize (issue #773 unit
// 4) — a mid-run snapshot, not a final outcome; `objective` is the raw
// scalar being minimised, unlike OptimizeResult's before/after pair.
export type OptProgress = {
  n_evals: number;
  params: Record<string, number>;
  objective: number;
  metrics: OptMetrics;
  /** Where the run is (#1176). Both 0 outside the surrogate seed, so "am I
   *  seeding" is one comparison and not a phase machine on the client. */
  seed_index?: number;
  seed_total?: number;
  /** Which stage produced this frame (#1202). A root-finder's residual falls
   *  monotonically and a simplex's does not, so the readout has to say which
   *  it is showing rather than leaving the user to infer it. */
  phase?: string;
  /** What the root-finder is driving to zero. `null` whenever the objective
   *  is not a root problem, so this is never a second objective. */
  residual?: number | null;
  /** Cost of the last REAL solve in this run (#1007) — held across memo hits,
   *  which do no engine work and would otherwise read as an instant solve. */
  solve_ms?: number | null;
  /** Solves the run has actually paid for. From the SERVER's counter: progress
   *  events are state, not a ledger, and the stream drops superseded frames
   *  when its buffer fills, so a client-side tick undercounts exactly when the
   *  run is fastest. */
  n_solves?: number;
  /** A band run's (AK#1901): the bands this eval solved (each with its
   *  `index` in the request's list), and the worst / mean of their values. */
  bands?: (OptBandRecord & { index: number })[];
  /** null = no reading (a band the engine could not read). */
  objective_worst?: number | null;
  objective_mean?: number | null;
  worst_band?: number;
};
// Phases whose residual falls monotonically, and is therefore worth showing
// in place of the SWR. Nelder-Mead's is deliberately NOT here: its best-so-far
// jumps around, which is the thing #1176's seeding readout already had to
// stop looking like a fault.
const ROOT_PHASES = new Set(["secant", "bracket", "newton"]);
export type OptObjective = "swr" | "resonance" | "match_z0";
const OPT_OBJECTIVE_LABELS: Record<OptObjective, string> = {
  swr: "SWR",
  resonance: "Resonance",
  match_z0: "Match Z₀",
};
// The objectives offered in the compact control next to meas-freq, in the
// order they are shown. SWR stays FIRST and stays available: it is the
// any-knob-count, any-feed-count best-compromise scalar, and it is a
// minimisation rather than a root, so it is the only one of the three that
// works with three knobs or a multi-feed design. Match Z₀ is the exact
// two-component root (R − R₀, X) that #1208's Newton path and the #1220
// tracker hold — sharper, but only with exactly two optimise-marked knobs.
const OPT_OBJECTIVES: OptObjective[] = ["swr", "resonance", "match_z0"];
const OPT_OBJECTIVE_HINTS: Record<OptObjective, string> = {
  swr: "best compromise, any number of knobs",
  resonance: "X = 0 exactly, with one knob",
  match_z0: "exact match, with two knobs",
};

// The gear menu's reference impedance (AK#1735). `value` is the Zo this
// session measures against — the override when there is one, else the
// design's own `design` — and `set(null)` returns to the design's.
export type ZoControl = {
  value: number;
  design: number;
  set: (zo: number | null) => void;
};

const formatZo = (v: number) => String(Number(v.toPrecision(6)));

// The Zo field. Commits on Enter or blur; text that is not a positive, finite
// number of ohms is refused where it was typed (red, with the reason), and
// the reference stays what it was — never quietly 50. Typing the design's
// own value clears the override rather than storing a copy of it, so a
// design whose file later names another Zo is not pinned to the old one.
function ZoField({ zo }: { zo: ZoControl }) {
  const [text, setText] = useState(() => formatZo(zo.value));
  const [error, setError] = useState<string | null>(null);
  // Re-seed when the reference moves under the field (a design's own Zo
  // landing on its first response, or a reset) — the render-time reset
  // idiom, not an effect, so there is no second render with stale text.
  const [seededFrom, setSeededFrom] = useState(zo.value);
  if (seededFrom !== zo.value) {
    setSeededFrom(zo.value);
    setText(formatZo(zo.value));
    setError(null);
  }
  const overridden = zo.value !== zo.design;
  function commit() {
    const v = parseZo(text);
    if (v === null) {
      setError("Zo must be a number of ohms greater than 0");
      return;
    }
    setError(null);
    zo.set(v === zo.design ? null : v);
    setText(formatZo(v));
  }
  return (
    <div className="opt-zo" role="group" aria-label="Reference impedance">
      <label className="opt-zo-row">
        <span className="opt-zo-label">Z₀</span>
        <input
          className={`opt-zo-input${error ? " is-invalid" : ""}`}
          type="text"
          inputMode="decimal"
          aria-label="Reference impedance Zo, ohms"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "opt-zo-error" : undefined}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (error) setError(null);
          }}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            else if (e.key === "Escape") {
              setText(formatZo(zo.value));
              setError(null);
            }
          }}
        />
        <span className="opt-zo-unit">Ω</span>
        {overridden && (
          <button
            type="button"
            className="opt-zo-reset"
            title={`Back to the design's own ${formatZo(zo.design)} Ω`}
            onClick={() => zo.set(null)}
          >
            reset
          </button>
        )}
      </label>
      {error ? (
        <div id="opt-zo-error" className="opt-zo-error" role="alert">
          {error}
        </div>
      ) : (
        <div className="gear-menu-hint opt-zo-hint">
          {overridden
            ? `design: ${formatZo(zo.design)} Ω`
            : "the design's own"}
          {" — SWR and Match Z₀ are measured against it"}
        </div>
      )}
    </div>
  );
}

// Why the optimizer auto-paused, for the transient cue. `knob` = the user grabbed
// a marked knob by hand; `load` = a new design/variant was loaded (its marks and
// ranges no longer apply).
export type OptPause = { kind: "knob"; name: string } | { kind: "load" };

/** What the session knows about the optimizer beyond its result (AK#1912),
 *  so the readout can always say what state it is in. Absent: a caller with
 *  no session behind it, and the panel keeps its own menu state. */
export type OptStateControl = {
  /** Knobs marked "Optimize this knob" on this design. */
  marked: number;
  /** The run in flight superseded one that had not finished. */
  restarted: boolean;
  /** The gear menu is open. Opening it pauses Optimize, and closing it
   *  resumes Optimize if it was on (useOptimizer). */
  menuOpen: boolean;
  /** The menu paused a running Optimize, which closing it resumes. */
  menuPaused: boolean;
  setMenuOpen: (open: boolean) => void;
};

// Live / Optimize: two matching push-button toggles (depressed = on), stacked
// at the left of the dial. Live gates auto-solving on knob turns; Optimize
// gates the reactive tuner. The objective ("optimise for") picker is the gear
// next to Optimize. optMenuOpen belongs to the session when it passes
// `optState` (opening the menu pauses Optimize), else it is local to this
// subtree.
function SimControls({
  autoSim,
  setAutoSim,
  optEnabled,
  setOptEnabled,
  setOptPausedBy,
  optRunning,
  optObjective,
  setOptObjective,
  optSeed,
  setOptSeed,
  trackEnabled,
  setTrackEnabled,
  trackRefusal,
  trackLatched,
  trackStatus,
  optResult,
  optProgress,
  optError,
  optPausedBy,
  zo,
  bands,
  optState,
}: {
  autoSim: boolean;
  setAutoSim: (fn: (v: boolean) => boolean) => void;
  optEnabled: boolean;
  setOptEnabled: (fn: (v: boolean) => boolean) => void;
  setOptPausedBy: (v: OptPause | null) => void;
  optRunning: boolean;
  optObjective: OptObjective;
  setOptObjective: (v: OptObjective) => void;
  optSeed: boolean;
  setOptSeed: (v: boolean) => void;
  /** #1220: the "keep the target while I drag" mode. */
  trackEnabled: boolean;
  setTrackEnabled: (v: boolean) => void;
  /** Why the mode cannot be entered, or null. Comes from the same rule the
   *  server enforces, so the switch never offers something that would be
   *  refused on arrival. */
  trackRefusal: string | null;
  /** Set while the tracker has latched: the target it was holding is gone. */
  trackLatched: string | null;
  /** The tracker's raw status, mirrored onto the controls as a data attribute
   *  so it can be read without depending on where the message renders. */
  trackStatus: string | null;
  optResult: OptimizeResult | null;
  optProgress: OptProgress | null;
  optError: string | null;
  optPausedBy: OptPause | null;
  /** AK#1735. Absent: no Zo field (a caller with no session behind it). */
  zo?: ZoControl | undefined;
  /** AK#1901. Absent: no Bands section. */
  bands?: OptBandsControl | undefined;
  /** AK#1912. Absent: no state line beyond the run's own readouts. */
  optState?: OptStateControl | undefined;
}) {
  const [ownMenuOpen, setOwnMenuOpen] = useState(false);
  const optMenuOpen = optState ? optState.menuOpen : ownMenuOpen;
  const setOptMenuOpen = (next: boolean | ((o: boolean) => boolean)) => {
    const v = typeof next === "function" ? next(optMenuOpen) : next;
    if (optState) optState.setMenuOpen(v);
    else setOwnMenuOpen(v);
  };
  // A band run's readouts (its per-band table, its refusals) live in the
  // full-width block under the dial; this narrow column keeps the one figure.
  const bandsOn = !!bands?.freqs;
  // AK#1912: Optimize on, and nothing visibly happening, always has a reason
  // the readout states — before any run's own figures are there to show.
  const marked = optState?.marked;
  const optState1912: { text: string; title: string } | null = !optState
    ? null
    : optState.menuOpen && optState.menuPaused
      ? {
          text: "paused while editing optimize settings",
          title: "Optimize is off while its settings change; closing this menu turns it back on and starts one run with them.",
        }
    : !optEnabled
      ? null
    : marked === 0
      ? {
          text: "mark a knob to optimize (right-click → Optimize this knob)",
          title: "Optimize varies only the knobs you mark: right-click a knob and choose Optimize this knob (or focus it and press o).",
        }
      : !autoSim
        ? {
            text: "needs Live",
            title: "Optimize runs the engine, which Paused holds. Turn Live on to run it.",
          }
        : optRunning && !optProgress
            ? {
                text: `${bands?.freqs ? `bands: ${bands.freqs.length}, ` : ""}knobs: ${marked}, ${optState.restarted ? "restarted" : "running"}…`,
                title: optState.restarted
                  ? "An input changed while the last run was still going, so it was stopped and this one started in its place."
                  : "The run has started; its progress shows here as each evaluation lands.",
              }
            : null;
  const optMarkedTitle =
    marked === undefined
      ? ""
      : ` Marked: ${marked === 0 ? "none" : `${marked} knob${marked === 1 ? "" : "s"}`}.`;
  return (
    <div className="sim-controls" data-track-status={trackStatus ?? undefined}>
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
          title={`Reactive optimiser: vary the knobs you mark (right-click a knob) to hit the objective whenever a fixed knob changes. Changing a marked knob by hand pauses it — turn it back on to resume.${optMarkedTitle}`}
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
            <div className="opt-menu" role="menu" ref={fitOptMenuToViewport}>
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
                  <span className="gear-menu-hint"> — {OPT_OBJECTIVE_HINTS[k]}</span>
                </button>
              ))}
              {/* AK#1735: the reference the SWR and Match Z₀ objectives
                  measure against — and the readout, the Smith chart and the
                  sweeps with them, so no two places disagree about it. */}
              {zo && (
                <>
                  <div className="opt-menu-title">Reference impedance</div>
                  <ZoField zo={zo} />
                </>
              )}
              {/* AK#1901: optimise across several bands at once. */}
              {bands && <BandsEditor bands={bands} />}
              {/* #1176. OFF by default and deliberately: measured
                  neutral-to-slightly-negative from a TUNED start, and
                  decisive from a poor one (moxon's plain run is stuck at
                  SWR 1.60 at every budget from a corner; seeded it reaches
                  1.0006). A default would slightly hurt the common case to
                  help the uncommon one, so the user says which they are in. */}
              <div className="opt-menu-title">Search</div>
              <button
                type="button"
                role="menuitemcheckbox"
                aria-checked={optSeed}
                className={`gear-menu-item${optSeed ? " is-active" : ""}`}
                title="Sample the whole knob box first and fit a surface to it, then hand the best point to the local search. Helps when the knobs start far from a good answer; costs a few evals when they do not."
                onClick={() => setOptSeed(!optSeed)}
              >
                Seed from a survey
              </button>
              {/* #1220. The tracker holds the objective while the user drags
                  some OTHER knob, by moving the optimise-marked ones. It is a
                  root problem, so it refuses rather than guesses: Resonance
                  needs exactly one marked knob and Match Z₀ exactly two, and
                  SWR is a minimisation with no root to hold at all. The
                  refusal carries the count, because "it did nothing" is the
                  failure this exists to avoid. */}
              <div className="opt-menu-title">While dragging</div>
              <button
                type="button"
                role="menuitemcheckbox"
                aria-checked={trackEnabled}
                disabled={!!trackRefusal}
                className={`gear-menu-item${trackEnabled ? " is-active" : ""}`}
                title={
                  trackRefusal ??
                  "While you drag any other knob, move the optimise-marked knobs to hold this target. Dragging a marked knob turns this off."
                }
                onClick={() => !trackRefusal && setTrackEnabled(!trackEnabled)}
              >
                Keep the target while I drag
                {trackRefusal && (
                  <span className="gear-menu-hint"> — {trackRefusal}</span>
                )}
              </button>
            </div>
          </>
        )}
      </div>
      {/* #1220: the tracker latched — the target it was holding is not
          reachable from here. Deliberately NOT worded as a knob hitting a
          limit: at the last good tick the held knob is usually nowhere near a
          bound, and it is the resonance/match itself that has gone. Nor is it
          worded as permanent: dragging back the way you came re-acquires. */}
      {optState1912 && (
        <span className="opt-readout opt-readout-state" role="status" title={optState1912.title}>
          {optState1912.text}
        </span>
      )}
      {trackEnabled && trackLatched && (
        <span className="opt-readout opt-readout-latched" title={trackLatched}>
          ⚠ {trackLatched}
        </span>
      )}
      {/* Live progress (#773 unit 4): while a run is in flight, the eval
          count/objective/Z-SWR readout tracks the latest `progress` frame
          instead of the previous run's settled result — optProgress is reset
          to null at the start of every run, so this only shows once the
          first frame lands. */}
      {optEnabled && optRunning && optProgress && optState?.restarted && (
        <span
          className="opt-readout opt-readout-restarted"
          title="An input changed while the last run was still going, so it was stopped and this one started in its place."
        >
          restarted
        </span>
      )}
      {optEnabled && optRunning && optProgress && (
        <span
          className="opt-readout opt-readout-progress"
          title={
            optProgress.bands
              ? `eval ${optProgress.n_evals} — each band's SWR is listed under the dial`
              : (optProgress.seed_total ?? 0) > 0
              ? `seeding the search: sampling the box before the fit (#1176), point ${optProgress.seed_index} of ${optProgress.seed_total}`
              : ROOT_PHASES.has(optProgress.phase ?? "") &&
                  optProgress.residual != null
                ? `${optProgress.phase} step — residual ${optProgress.residual.toFixed(4)} Ω, Z ${optProgress.metrics.z_in_re.toFixed(1)} ${optProgress.metrics.z_in_im >= 0 ? "+" : "−"} j${Math.abs(optProgress.metrics.z_in_im).toFixed(1)} Ω`
                : `eval ${optProgress.n_evals} — objective ${optProgress.objective.toFixed(4)}, Z ${optProgress.metrics.z_in_re.toFixed(1)} ${optProgress.metrics.z_in_im >= 0 ? "+" : "−"} j${Math.abs(optProgress.metrics.z_in_im).toFixed(1)} Ω`
          }
        >
          {/* The seed samples the whole box, so its objective jumps around
              and a plain "#n SWR x" reads as the optimiser going backwards.
              Naming the phase is what stops that looking like a fault. */}
          {optProgress.bands
            ? `#${optProgress.n_evals} worst SWR ${optProgress.objective_worst != null ? optProgress.objective_worst.toFixed(2) : NO_READING}`
            : (optProgress.seed_total ?? 0) > 0
            ? `seeding ${optProgress.seed_index}/${optProgress.seed_total}`
            : ROOT_PHASES.has(optProgress.phase ?? "") &&
                optProgress.residual != null
              ? `#${optProgress.n_evals} ${optObjective === "resonance" ? "|X|" : "|Z−Z₀|"} ${optProgress.residual.toFixed(2)} Ω`
              : `#${optProgress.n_evals} SWR ${optProgress.metrics.swr.toFixed(2)}`}
        </span>
      )}
      {optEnabled && !optRunning && optResult && (
        <span
          className="opt-readout"
          title={`SWR after optimisation, against ${formatZo(optResult.metrics_after.z0_ohms)} Ω`}
        >
          {optResult.objective === "bands" ? "worst SWR" : "SWR"}{" "}
          {/* A band run's worst can be "no reading" (null, AK#1901). */}
          {optResult.metrics_after.swr != null
            ? optResult.metrics_after.swr.toFixed(2)
            : NO_READING}
        </span>
      )}
      {optEnabled && optError && !bandsOn && (
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
              ? `You moved ${optPausedBy.name}, a knob marked for optimization, so Optimize paused. Turn it back on to resume.`
              : "Loading a design clears its optimize marks and pauses Optimize. Re-mark knobs and turn it back on to resume."
          }
        >
          {optPausedBy.kind === "knob"
            ? "paused: you moved a marked knob"
            : "Paused — loaded a new design"}
        </span>
      )}
    </div>
  );
}

// How long a still touch on the measurement dial takes to open its range
// menu (AK#1682) — about the platforms' own long-press delay.
export const LONG_PRESS_MS = 550;

// Measurement freq = the rig's tuning control: a weighted VFO dial +
// frequency-counter readout. Top line: band select + the LCD. Below: the
// Live/Optimize toggles stacked at the left of the dial, with the lock
// pinned to the dial's lower-right corner ("lock to design freq" disables
// the dial).
export function VfoPanel({
  currentBands,
  measLocked,
  measFreq,
  bandContaining,
  measBand,
  selectMeasBand,
  onCustomMeasBand,
  sweepRange,
  onSweepMenu,
  setMeasFreq,
  measLockable,
  linkMeas,
  toggleLink,
  autoSim,
  setAutoSim,
  optEnabled,
  setOptEnabled,
  setOptPausedBy,
  optRunning,
  optObjective,
  setOptObjective,
  optSeed,
  setOptSeed,
  trackEnabled,
  setTrackEnabled,
  trackRefusal,
  trackLatched,
  trackStatus,
  optResult,
  optProgress,
  optError,
  optPausedBy,
  zo,
  bands,
  optState,
  optPaceMs,
  kept = null,
}: {
  currentBands: BandSpec[];
  measLocked: boolean;
  measFreq: number;
  bandContaining: (f: number) => string | null;
  measBand: string;
  selectMeasBand: (key: string) => void;
  /** "Custom…" in the measurement band picker (#1487). */
  onCustomMeasBand?: ((centerMhz: number, spanMhz: number) => void) | undefined;
  /** AK#1682: the one range — the dial travels exactly the sweep's
   *  [lo, hi] (resolved in DesignSession by lib/sweep.ts). */
  sweepRange: SweepRange;
  /** Open the range menu at a viewport point: right-click, or a long press
   *  on touch. `touch` says which. */
  onSweepMenu?: ((x: number, y: number, touch: boolean) => void) | undefined;
  setMeasFreq: (v: number) => void;
  measLockable: boolean;
  linkMeas: boolean;
  toggleLink: (next: boolean) => void;
  autoSim: boolean;
  setAutoSim: (fn: (v: boolean) => boolean) => void;
  optEnabled: boolean;
  setOptEnabled: (fn: (v: boolean) => boolean) => void;
  setOptPausedBy: (v: OptPause | null) => void;
  optRunning: boolean;
  optObjective: OptObjective;
  setOptObjective: (v: OptObjective) => void;
  optResult: OptimizeResult | null;
  optSeed: boolean;
  setOptSeed: (v: boolean) => void;
  /** #1220: the "keep the target while I drag" mode. */
  trackEnabled: boolean;
  setTrackEnabled: (v: boolean) => void;
  /** Why the mode cannot be entered, or null. Comes from the same rule the
   *  server enforces, so the switch never offers something that would be
   *  refused on arrival. */
  trackRefusal: string | null;
  /** Set while the tracker has latched: the target it was holding is gone. */
  trackLatched: string | null;
  /** The tracker's raw status, mirrored onto the controls as a data attribute
   *  so it can be read without depending on where the message renders. */
  trackStatus: string | null;
  optProgress: OptProgress | null;
  optError: string | null;
  optPausedBy: OptPause | null;
  /** The gear menu's Zo field (AK#1735). */
  zo?: ZoControl | undefined;
  /** The gear menu's band list (AK#1901). */
  bands?: OptBandsControl | undefined;
  /** The optimizer's state for its readout (AK#1912). */
  optState?: OptStateControl | undefined;
  /** A run's wall time per solved point, ms (AK 0.97.1); null before the
   *  first frame. */
  optPaceMs?: number | null | undefined;
  /** A kept band run jumped to, and keeping a fresh one (AK#1906). */
  kept?: KeptReadout | null | undefined;
}) {
  // Long press = the touch route to the range menu. The knobs have no touch
  // path of their own: their menu rides the browser's contextmenu event,
  // which Android's long press fires and iOS Safari never does. So the dial
  // times its own press — a touch or pen held still (≤ 8 px) for
  // LONG_PRESS_MS. Moving further is a drag of the dial, and cancels it.
  const pressRef = useRef<{ x: number; y: number; timer: number } | null>(null);
  const cancelPress = () => {
    if (pressRef.current) window.clearTimeout(pressRef.current.timer);
    pressRef.current = null;
  };
  useEffect(() => cancelPress, []);
  const onLock = (e: React.SyntheticEvent) =>
    (e.target as Element).closest?.(".vfo-lock") != null;
  return (
    <>
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
              onCustom={onCustomMeasBand}
              customSeedMhz={measFreq}
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
          <SimControls
            autoSim={autoSim}
            setAutoSim={setAutoSim}
            optEnabled={optEnabled}
            setOptEnabled={setOptEnabled}
            setOptPausedBy={setOptPausedBy}
            optRunning={optRunning}
            optObjective={optObjective}
            setOptObjective={setOptObjective}
            optSeed={optSeed}
            setOptSeed={setOptSeed}
            trackEnabled={trackEnabled}
            setTrackEnabled={setTrackEnabled}
            trackRefusal={trackRefusal}
            trackLatched={trackLatched}
            trackStatus={trackStatus}
            optResult={optResult}
            optProgress={optProgress}
            optError={optError}
            optPausedBy={optPausedBy}
            zo={zo}
            bands={bands}
            optState={optState}
          />

          <div
            className="vfo-dial"
            title="Right-click (long-press on touch) to set the sweep range"
            onContextMenu={
              onSweepMenu
                ? (e) => {
                    if (onLock(e)) return;
                    e.preventDefault();
                    cancelPress();
                    onSweepMenu(e.clientX, e.clientY, false);
                  }
                : undefined
            }
            onPointerDown={(e) => {
              if (!onSweepMenu || e.pointerType === "mouse" || onLock(e)) return;
              cancelPress();
              const { clientX: x, clientY: y } = e;
              pressRef.current = {
                x,
                y,
                timer: window.setTimeout(() => {
                  pressRef.current = null;
                  onSweepMenu(x, y, true);
                }, LONG_PRESS_MS),
              };
            }}
            onPointerMove={(e) => {
              const p = pressRef.current;
              if (p && Math.hypot(e.clientX - p.x, e.clientY - p.y) > 8) cancelPress();
            }}
            onPointerUp={cancelPress}
            onPointerCancel={cancelPress}
          >
            <Knob
              knobId="meas_freq"
              variant="vfo"
              value={measFreq}
              min={sweepRange.lo}
              max={sweepRange.hi}
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
                  {/* Shackle opens when unlocked (right leg lifts clear of
                      the body) so the state reads from shape, not just the
                      muted-vs-accent color. */}
                  <path
                    className="shackle"
                    d={
                      linkMeas
                        ? "M5.3 7.2V5a2.7 2.7 0 0 1 5.4 0v2.2"
                        : "M5.3 7.2V5a2.7 2.7 0 0 1 5.4 0v0.6"
                    }
                  />
                </svg>
              </button>
            )}
          </div>
        </div>
        {((optEnabled && bands?.freqs) || kept?.shown) && (
          <BandsReadout
            running={optRunning}
            progress={optProgress}
            result={optResult}
            error={optError}
            paceMs={optPaceMs ?? null}
            kept={kept ?? null}
          />
        )}
      </div>
    </>
  );
}
