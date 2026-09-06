import { Fragment, useEffect, useRef, useState } from "react";
import type { NormCheckData, SolveResponse } from "../../lib/api";
import { formatOhms, formatSwr } from "../../lib/format";
import type { ExampleDescriptor } from "../../lib/params";
import { ReadoutsPanel } from "./ReadoutsPanel";
import { ResultPanel } from "./ResultPanel";

function feedMag(r: SolveResponse): number {
  const w = r.wires[r.feed_wire_index];
  if (!w) return 0;
  const re = w.knot_currents_re[r.feed_knot_index];
  const im = w.knot_currents_im[r.feed_knot_index];
  return Math.hypot(re, im);
}

// Display labels for SolveResponse.ground_model_applied — what the
// impedance solve actually ran, as reported by the server (see the type).
const GROUND_APPLIED_LABEL: Record<string, string> = {
  sommerfeld: "Sommerfeld",
  "refl-coef": "refl-coef",
  "pec-image": "PEC image",
  free: "free space",
  // Faceted terrain: impedance ran crest-medium Sommerfeld; the far field
  // reflects per-direction off the facets (issue #534).
  terrain: "terrain (crest Somm.)",
};

// The R/X/SWR/rtt solve readout. The desktop stage floats it over the canvas
// as a HUD (className="stage-readout"); the mobile Info screen (Phase B)
// renders it as a normal block. Module scope so both trees share one
// implementation.
export function SolveReadout({
  result,
  rttMs,
  live,
  currentExample,
  effectiveMultiFeed,
  normCheck,
  normCheckEnabled,
  onPlaneChange,
  className = "",
}: {
  result: SolveResponse | null;
  rttMs: number | null;
  /** Engine timing while an optimiser run is in flight (#1007). The run POSTs
   *  /optimize and reads an SSE stream, so it never touches the /ws channel
   *  `rttMs` is measured on — the two fields below froze for the whole run,
   *  which is exactly when the engine is busiest.
   *
   *  `intervalMs` is NOT the same quantity as `rttMs`: the interactive number
   *  is one request/response pair, this is the gap between progress frames.
   *  It is what the user is actually waiting through and carries the same
   *  network and queueing, so it earns the slot — under its own label. */
  live?: {
    solveMs: number | null;
    intervalMs: number | null;
    nSolves: number | null;
  } | null;
  currentExample: ExampleDescriptor | undefined;
  effectiveMultiFeed: boolean;
  normCheck: NormCheckData | null;
  normCheckEnabled: boolean;
  /** Measurement-plane pick (issue #652 c). Absent = picker never shown. */
  onPlaneChange?: ((plane: string) => void) | undefined;
  className?: string;
}) {
  const planes = result?.planes;
  // Overflow guard for the floating stage HUD: with enough content (a
  // multi-feed Z table plus a design's own readout rows), the card can
  // outgrow the stage. CSS caps its height; this effect detects that the
  // cap actually bit (scrollHeight > clientHeight) and flips a class that
  // makes the card scrollable — which also requires giving it back the
  // pointer-events the passive HUD normally renounces, so drag-through is
  // sacrificed only when there is hidden content worth scrolling to.
  // Watched with a ResizeObserver rather than computed per render: the
  // readout grows on solve responses and dwell results, not renders.
  const rootRef = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  const check = () => {
    const el = rootRef.current;
    if (el) setOverflowing(el.scrollHeight > el.clientHeight + 1);
  };
  // Re-measure on every render (content changes arrive as renders)…
  useEffect(check);
  // …and on container resizes, which happen with no render at all.
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `check` reads
    // only refs/setState; recreating the observer per render buys nothing.
  }, []);
  return (
    <div
      ref={rootRef}
      className={`readout${className ? " " + className : ""}${overflowing ? " readout-overflowing" : ""}`}
    >
      {onPlaneChange && planes && planes.length > 1 && (
        <div
          className="row"
          title="Measurement plane: the port every number and chart here is referenced to. Picking another port re-solves as a VNA clipped on there — the chain upstream of it disconnected."
        >
          <span>plane</span>
          <select
            className="val plane-select"
            aria-label="measurement plane"
            value={result?.plane ?? planes[0]}
            onChange={(e) => onPlaneChange(e.target.value)}
          >
            {planes.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      )}
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
                {budget.map((b, i) => {
                  // Hierarchical rows (issue #489): rows carry the instance
                  // path of the composite they came from. Start a group
                  // header whenever the path changes, and indent members
                  // one step per hierarchy level ("sta.tuner" = depth 2).
                  const path = b.path ?? "";
                  const prev = i > 0 ? budget[i - 1].path ?? "" : "";
                  const depth = path ? path.split(".").length : 0;
                  return (
                    <Fragment key={`pb-${i}`}>
                      {path && path !== prev && (
                        <div
                          className="row pb-group"
                          style={{ paddingLeft: `${(depth - 1) * 12}px` }}
                        >
                          <span>{path}</span>
                        </div>
                      )}
                      <div
                        className="row"
                        style={
                          depth ? { paddingLeft: `${depth * 12}px` } : undefined
                        }
                      >
                        <span>{b.label}</span>
                        <span className="val">
                          {((b.watts / pin) * 100).toFixed(1)}%
                        </span>
                      </div>
                    </Fragment>
                  );
                })}
                <div className="row" key="pb-ant">
                  <span>antenna (accepted)</span>
                  <span className="val">
                    {(((pin - diss) / pin) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            )}
            {normCheckEnabled &&
              (() => {
                // Over faceted terrain the same row reads the PEC-facet-
                // referenced fraction (the tooltip explains the different
                // denominator); the plain finite ground keeps its P_in-
                // referenced number.
                const isTerrain = !!normCheck?.method.startsWith("grid_terrain");
                return (
                  <div
                    className="row"
                    title={
                      isTerrain
                        ? "Share of accepted power leaving as sky wave over the faceted terrain: referenced against the same facet geometry with perfect-reflector media, so the ratio isolates real ground-media absorption (the hybrid model's separate field-vs-circuit ledger gap cancels; it is shown on the chart as the dotted overlay)."
                        : "P_radiated / P_input from the dwell-triggered pattern integral (the norm check as a percentage): what actually leaves as far-field radiation after network, wire AND real ground absorption. Fills in once the knobs settle; over PEC ground or free space it collapses onto the structural efficiency. See the 'three ledgers' section of the docs."
                    }
                  >
                    <span>radiated (incl. ground)</span>
                    <span className={normCheck ? "val" : "val val-pending"}>
                      {normCheck
                        ? `${(normCheck.radiated_fraction * 100).toFixed(0)}%`
                        : "—"}
                    </span>
                  </div>
                );
              })()}
          </div>
        );
      })()}
      {/* Design-supplied readouts (issue #712): whatever rows the geometry's
          own readout_rows() produced, rendered generically. They sit with
          the antenna's other physical numbers, above the engine timing.
          Mounted HERE rather than at DesignSession's three call sites so
          every layout (mobile Info screen, desktop rail slide, grid stage
          HUD) gets them with no layout-specific code. */}
      <ReadoutsPanel rows={result?.readouts} />
      {/* Engine timing grouped last: solve/rtt describe how fast the answer
          arrived, not what the antenna is doing, so they sit below the RF
          readout (and below the power budget when one is shown). The
          feeds-table wrapper is used only for its dashed separator rule —
          no header. */}
      <div className="feeds-table">
        {result?.solver_diag && (
          <div
            className="row"
            title={
              result.solver_diag.reason
                ? `Array Block solve did not use the fast lattice-FFT coupling path: ${result.solver_diag.reason}. Correctness is unaffected — only speed.`
                : "Array Block solve used the fast lattice-FFT coupling path (a regular same-height lattice of 16+ identical elements)."
            }
          >
            <span>array path</span>
            <span className="val">
              {result.solver_diag.lattice_fft
                ? "FFT lattice"
                : result.solver_diag.operator === "HMatrix"
                  ? "H-matrix"
                  : "per-pair"}
            </span>
          </div>
        )}
        <div className="row">
          <span>solve</span>
          <span
            className="val"
            title={
              live?.solveMs != null
                ? "the last full solve inside the running optimisation"
                : undefined
            }
          >
            {live?.solveMs != null
              ? `${live.solveMs.toFixed(1)} ms`
              : result
                ? `${result.solve_ms.toFixed(1)} ms`
                : "—"}
          </span>
        </div>
        <div className="row">
          <span>{live?.intervalMs != null ? "per eval" : "rtt"}</span>
          <span
            className="val"
            title={
              live?.intervalMs != null
                ? "gap between progress frames — not the interactive round trip, which the optimiser's own request never makes"
                : undefined
            }
          >
            {live?.intervalMs != null
              ? `${live.intervalMs.toFixed(1)} ms`
              : rttMs != null
                ? `${rttMs.toFixed(1)} ms`
                : "—"}
          </span>
        </div>
        {live?.nSolves != null && (
          <div className="row">
            <span>solves</span>
            <span
              className="val"
              title="full solves this run has paid for, counted by the server — a run of forty looks like one otherwise"
            >
              {live.nSolves}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
