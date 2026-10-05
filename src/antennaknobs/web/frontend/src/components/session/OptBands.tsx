// AK#1901, the baby step: optimise the marked knobs across several bands at
// once. The gear menu gets a band list (frequencies in MHz, SWR at each) and
// one balance control; the panel under the dial gets the per-band readout.
// Root / sequential / per-band objectives and feeds are server-side only for
// now.
import { useState } from "react";
import type { OptimizeResult, OptProgress } from "./VfoPanel";
import { fmtFreq, MAX_OPT_BANDS, parseBandFreq } from "../../lib/optBands";

/** One band as the server reads it at one solve (AK#1901). */
export type OptBandRecord = {
  freq_mhz: number;
  objective: string;
  feed: number;
  z0_ohms: number;
  z_re: number;
  z_im: number;
  swr: number;
  residual: number | null;
  value: number;
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

const fmtSwr = (v: number) =>
  Number.isNaN(v) ? "—" : Number.isFinite(v) ? v.toFixed(2) : "∞";

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

// Under the dial, full width: while a run is in flight, each band's SWR from
// the latest progress frame and the worst; once it settles, the before/after
// table; and a refusal's text, which is too long for the narrow column.
export function BandsReadout({
  running,
  progress,
  result,
  error,
}: {
  running: boolean;
  progress: OptProgress | null;
  result: OptimizeResult | null;
  error: string | null;
}) {
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
            {fmtFreq(b.freq_mhz)}: SWR {fmtSwr(b.swr)}
          </span>
        ))}
        {progress.objective_worst != null && (
          <span className="opt-bands-chip">
            worst {fmtSwr(progress.objective_worst)}
          </span>
        )}
      </div>
    );
  }
  if (!running && result?.objective === "bands" && result.bands_after) {
    const before = result.bands_before ?? [];
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
          {result.bands_after.map((b, i) => (
            <tr key={`${b.freq_mhz}:${b.feed}`}>
              <td>{fmtFreq(b.freq_mhz)}</td>
              <td>{before[i] ? fmtSwr(before[i].swr) : "—"}</td>
              <td>{fmtSwr(b.swr)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          {result.worst_swr_after != null && (
            <tr>
              <th scope="row">worst</th>
              <td>{fmtSwr(result.worst_swr_before ?? NaN)}</td>
              <td>{fmtSwr(result.worst_swr_after)}</td>
            </tr>
          )}
          {result.objective_mean_after != null && (
            <tr>
              <th scope="row">mean</th>
              <td>{fmtSwr(result.objective_mean_before ?? NaN)}</td>
              <td>{fmtSwr(result.objective_mean_after)}</td>
            </tr>
          )}
        </tfoot>
      </table>
    );
  }
  return null;
}
