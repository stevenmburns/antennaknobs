// AK#1901, the baby step: optimise the marked knobs across several bands at
// once. The gear menu gets a band list (frequencies in MHz, SWR at each) and
// one balance control; the panel under the dial gets the per-band readout.
// Root / sequential / per-band objectives and feeds are server-side only for
// now.
import { useState } from "react";
import type { OptimizeResult, OptProgress } from "./VfoPanel";
import { fmtFreq, MAX_OPT_BANDS, NO_READING, parseBandFreq } from "../../lib/optBands";
import { feedColor } from "../charts/palette";

// The band's colour, as its marker on the Smith chart draws it (AK 0.97.1).
function Swatch({ index }: { index: number }) {
  return (
    <span className="opt-bands-swatch" aria-hidden="true" style={{ background: feedColor(index) }} />
  );
}

/** One band as the server reads it at one solve (AK#1901). A reading the
 *  engine could not make (an infinite SWR, a NaN Z) arrives as null. */
export type OptBandRecord = {
  /** The band's place in the request's list. Always on progress frames; on
   *  result records from the backend that sends it (older ones: by position). */
  index?: number;
  freq_mhz: number;
  objective: string;
  feed: number;
  z0_ohms: number;
  z_re: number | null;
  z_im: number | null;
  swr: number | null;
  residual: number | null;
  value: number | null;
};

/** The band list's state, handed to the panel the way the Zo field's is. */
export type OptBandsControl = {
  /** null = off: the run is the single-frequency one, unchanged. */
  freqs: number[] | null;
  setFreqs: (f: number[] | null) => void;
  /** The balance w in J = (1 - w) * worst + w * mean. */
  meanWeight: number;
  setMeanWeight: (w: number) => void;
  /** The first band when the list is switched on: the measurement freq. */
  defaultFreq: number;
};

// null is the server's "no reading" (a non-finite value, AK#1901); undefined
// is a field this response does not carry at all.
const fmtSwr = (v: number | null | undefined) =>
  v === undefined ? "—" : v === null || !Number.isFinite(v) ? NO_READING : v.toFixed(2);

/** A run's pace: "0.15 s/eval", "5.2 s/eval", "12 s/eval". */
export const fmtPace = (ms: number) => {
  const s = ms / 1000;
  return `${s < 1 ? s.toFixed(2) : s < 10 ? s.toFixed(1) : s.toFixed(0)} s/eval`;
};

// The gear menu's Bands section: a switch, the list (each row removable), an
// add field, and the balance slider.
export function BandsEditor({ bands }: { bands: OptBandsControl }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const on = bands.freqs !== null;
  const freqs = bands.freqs ?? [];
  function add() {
    const r = parseBandFreq(text, freqs);
    if ("error" in r) {
      setError(r.error);
      return;
    }
    setError(null);
    setText("");
    bands.setFreqs([...freqs, r.freq]);
  }
  return (
    <div className="opt-bands" role="group" aria-label="Bands">
      <div className="opt-menu-title">Bands</div>
      <button
        type="button"
        role="menuitemcheckbox"
        aria-checked={on}
        className={`gear-menu-item${on ? " is-active" : ""}`}
        onClick={() => {
          setError(null);
          bands.setFreqs(on ? null : [bands.defaultFreq]);
        }}
      >
        Several bands at once
        <span className="gear-menu-hint">
          {" "}
          — SWR at each band below, instead of at the measurement freq
        </span>
      </button>
      {on && (
        <div className="opt-bands-body">
          <ul className="opt-bands-list" aria-label="Band frequencies">
            {freqs.map((f, i) => (
              <li key={f} className="opt-bands-row">
                <span className="opt-bands-freq">{fmtFreq(f)} MHz</span>
                <button
                  type="button"
                  className="opt-bands-remove"
                  aria-label={`Remove the ${fmtFreq(f)} MHz band`}
                  disabled={freqs.length <= 1}
                  title={
                    freqs.length <= 1
                      ? "A band run needs at least one band — switch Bands off instead"
                      : undefined
                  }
                  onClick={() => bands.setFreqs(freqs.filter((_, j) => j !== i))}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <div className="opt-bands-add">
            <input
              className={`opt-zo-input${error ? " is-invalid" : ""}`}
              type="text"
              inputMode="decimal"
              aria-label="Add a band, MHz"
              aria-invalid={error ? true : undefined}
              placeholder="MHz"
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                if (error) setError(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") add();
              }}
            />
            <button
              type="button"
              className="opt-zo-reset"
              disabled={freqs.length >= MAX_OPT_BANDS}
              onClick={add}
            >
              add
            </button>
          </div>
          {error && (
            <div className="opt-zo-error" role="alert">
              {error}
            </div>
          )}
          <label className="opt-bands-balance">
            <span>
              Balance {bands.meanWeight.toFixed(2)}
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              aria-label="Balance between the worst band and the average"
              value={bands.meanWeight}
              onChange={(e) => bands.setMeanWeight(Number(e.target.value))}
            />
          </label>
          <div className="gear-menu-hint">
            0 = improve the worst band only; 1 = the average of the bands only
          </div>
        </div>
      )}
    </div>
  );
}

/** The readout's part in keeping band runs (AK#1906): a kept run the tab
 *  jumped to (`shown`: its stored table instead of a run's, until a run
 *  answers), and the Keep action on a fresh run's result. */
export type KeptReadout = {
  /** The kept run's name and stored table, while it is what the tab shows. */
  shown: { name: string; result: OptimizeResult | null } | null;
  /** Run it again from its start; null with `runBlocked` saying why not. */
  onRun: (() => void) | null;
  runBlocked: string | null;
  /** Keep the fresh result as a study; null: nothing to keep. */
  onKeep: (() => void) | null;
};

// Under the dial, full width: while a run is in flight, each band's SWR from
// the latest progress frame and the worst; once it settles, the before/after
// table; and a refusal's text, which is too long for the narrow column.
export function BandsReadout({
  running,
  progress,
  result,
  error,
  paceMs = null,
  kept = null,
}: {
  running: boolean;
  progress: OptProgress | null;
  result: OptimizeResult | null;
  error: string | null;
  /** Wall time per solved point so far, ms: how fast this run is going
   *  (a hosted run is far slower than a local one). */
  paceMs?: number | null;
  kept?: KeptReadout | null;
}) {
  if (kept?.shown && !running && !error) {
    const r = kept.shown.result;
    return (
      <div className="opt-bands-kept" role="group" aria-label="Kept run">
        <div className="opt-bands-kept-head">
          Kept run <strong>{kept.shown.name}</strong>: its stored answer
        </div>
        {r ? (
          <BandTable result={r} />
        ) : (
          <div className="gear-menu-hint">No stored result: run it to see one.</div>
        )}
        <button
          type="button"
          className="opt-zo-reset"
          disabled={kept.onRun === null}
          title={kept.runBlocked ?? "Put the knobs back at the run's start and optimise again"}
          onClick={() => kept.onRun?.()}
        >
          Run again from its start
        </button>
        {kept.runBlocked && <div className="gear-menu-hint">{kept.runBlocked}</div>}
      </div>
    );
  }
  if (error) {
    return (
      <div className="opt-bands-readout opt-readout-err" role="alert">
        {error}
      </div>
    );
  }
  if (running && progress?.bands) {
    return (
      <div className="opt-bands-readout opt-readout-progress" aria-label="Band progress">
        <span>#{progress.n_evals}</span>
        {progress.bands.map((b) => (
          <span key={b.index} className="opt-bands-chip">
            <Swatch index={b.index} />
            {fmtFreq(b.freq_mhz)}: SWR {fmtSwr(b.swr)}
          </span>
        ))}
        {progress.objective_worst !== undefined && (
          <span className="opt-bands-chip">
            worst {fmtSwr(progress.objective_worst)}
          </span>
        )}
        {paceMs != null && (
          <span
            className="opt-bands-chip opt-bands-pace"
            title="Wall time per solved point so far. How many points a run needs depends on when it converges, so this is a pace, not a countdown."
          >
            {fmtPace(paceMs)}
          </span>
        )}
      </div>
    );
  }
  if (!running && result?.objective === "bands" && result.bands_after) {
    const notes = bandResultNotes(result);
    return (
      <>
      <BandTable result={result} />
      {notes.length > 0 && (
        <ul className="opt-bands-readout opt-bands-notes" aria-label="Band run notes">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {kept?.onKeep && (
        <button
          type="button"
          className="opt-zo-reset opt-bands-keep"
          title="Keep this run as a study: its start, knobs, ranges, bands and answer, which `antennaknobs analyze --study` runs again"
          onClick={() => kept.onKeep?.()}
        >
          Keep…
        </button>
      )}
      </>
    );
  }
  return null;
}

// A band run's before/after table: each band's SWR at the start and at the
// answer, the worst and the mean under them.
function BandTable({ result }: { result: OptimizeResult }) {
  const before = result.bands_before ?? [];
  // Each after row's own start: matched by `index` when both carry it,
  // else by position (a backend that predates the field).
  const startOf = (b: OptBandRecord, i: number): OptBandRecord | undefined =>
    (b.index != null ? before.find((r) => r.index === b.index) : undefined) ??
    before[i];
  return (
      <table className="opt-bands-readout opt-bands-table" aria-label="Band results">
        <thead>
          <tr>
            <th scope="col">MHz</th>
            <th scope="col">SWR before</th>
            <th scope="col">after</th>
          </tr>
        </thead>
        <tbody>
          {(result.bands_after ?? []).map((b, i) => (
            <tr key={`${b.freq_mhz}:${b.feed}`}>
              <td>
                <Swatch index={b.index ?? i} />
                {fmtFreq(b.freq_mhz)}
              </td>
              <td>{fmtSwr(startOf(b, i)?.swr)}</td>
              <td>{fmtSwr(b.swr)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          {result.worst_swr_after !== undefined && (
            <tr>
              <th scope="row">worst</th>
              <td>{fmtSwr(result.worst_swr_before)}</td>
              <td>{fmtSwr(result.worst_swr_after)}</td>
            </tr>
          )}
          {result.objective_mean_after !== undefined && (
            <tr>
              <th scope="row">mean</th>
              <td>{fmtSwr(result.objective_mean_before)}</td>
              <td>{fmtSwr(result.objective_mean_after)}</td>
            </tr>
          )}
        </tfoot>
      </table>
  );
}

/** What the result table alone does not say (AK 0.97.1, AK#1909): the run
 *  stopped at the hosted time limit, a knob ended pinned at its range, or no
 *  band is anywhere near a match. */
export function bandResultNotes(result: OptimizeResult): string[] {
  const out: string[] = [];
  if (result.stopped === "time") {
    const s = result.time_budget_s;
    out.push(
      `Stopped at the time limit${s ? ` (${s} s)` : ""}: this is the best point found so far.`,
    );
  }
  for (const b of result.at_bound ?? []) {
    out.push(
      `${b.name} ended at its ${b.bound === "min" ? "minimum" : "maximum"}: the best value may lie outside its range. Widen it and run again.`,
    );
  }
  if (result.far_from_match) {
    out.push("No band is near a match: check the knobs' ranges before trusting this result.");
  }
  return out;
}
