import { BandDropdown } from "../params/BandDropdown";
import { Knob } from "../params/Knob";
import { useState } from "react";
import type { BandSpec, ExampleDescriptor } from "../../lib/params";

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

// Why the optimizer auto-paused, for the transient cue. `knob` = the user grabbed
// a marked knob by hand; `load` = a new design/variant was loaded (its marks and
// ranges no longer apply).
export type OptPause = { kind: "knob"; name: string } | { kind: "load" };

// Live / Optimize: two matching push-button toggles (depressed = on), stacked
// at the left of the dial. Live gates auto-solving on knob turns; Optimize
// gates the reactive tuner. The objective ("optimise for") picker is the gear
// next to Optimize. optMenuOpen is local — nothing outside this subtree reads
// or writes it.
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
}) {
  const [optMenuOpen, setOptMenuOpen] = useState(false);
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
                  <span className="gear-menu-hint"> — {OPT_OBJECTIVE_HINTS[k]}</span>
                </button>
              ))}
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
      {optEnabled && optRunning && optProgress && (
        <span
          className="opt-readout opt-readout-progress"
          title={
            (optProgress.seed_total ?? 0) > 0
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
          {(optProgress.seed_total ?? 0) > 0
            ? `seeding ${optProgress.seed_index}/${optProgress.seed_total}`
            : ROOT_PHASES.has(optProgress.phase ?? "") &&
                optProgress.residual != null
              ? `#${optProgress.n_evals} ${optObjective === "resonance" ? "|X|" : "|Z−Z₀|"} ${optProgress.residual.toFixed(2)} Ω`
              : `#${optProgress.n_evals} SWR ${optProgress.metrics.swr.toFixed(2)}`}
        </span>
      )}
      {optEnabled && !optRunning && optResult && (
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
  );
}

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
  currentExample,
  measBandAnchor,
  freqWindowCeiling,
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
}: {
  currentBands: BandSpec[];
  measLocked: boolean;
  measFreq: number;
  bandContaining: (f: number) => string | null;
  measBand: string;
  selectMeasBand: (key: string) => void;
  currentExample: ExampleDescriptor | undefined;
  measBandAnchor: number;
  freqWindowCeiling: number;
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
}) {
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
          />

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
                  : Math.min(freqWindowCeiling, measBandAnchor * 1.25)
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
      </div>
    </>
  );
}
