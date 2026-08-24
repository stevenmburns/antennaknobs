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
};
export type OptObjective = "swr" | "resonance" | "match_z0";
const OPT_OBJECTIVE_LABELS: Record<OptObjective, string> = {
  swr: "SWR",
  resonance: "Resonance",
  match_z0: "Match Z₀",
};
// The two objectives offered in the compact control next to meas-freq.
const OPT_OBJECTIVES: OptObjective[] = ["swr", "resonance"];

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
  optResult: OptimizeResult | null;
  optProgress: OptProgress | null;
  optError: string | null;
  optPausedBy: OptPause | null;
}) {
  const [optMenuOpen, setOptMenuOpen] = useState(false);
  return (
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
      {/* Live progress (#773 unit 4): while a run is in flight, the eval
          count/objective/Z-SWR readout tracks the latest `progress` frame
          instead of the previous run's settled result — optProgress is reset
          to null at the start of every run, so this only shows once the
          first frame lands. */}
      {optEnabled && optRunning && optProgress && (
        <span
          className="opt-readout opt-readout-progress"
          title={`eval ${optProgress.n_evals} — objective ${optProgress.objective.toFixed(4)}, Z ${optProgress.metrics.z_in_re.toFixed(1)} ${optProgress.metrics.z_in_im >= 0 ? "+" : "−"} j${Math.abs(optProgress.metrics.z_in_im).toFixed(1)} Ω`}
        >
          #{optProgress.n_evals} SWR {optProgress.metrics.swr.toFixed(2)}
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
