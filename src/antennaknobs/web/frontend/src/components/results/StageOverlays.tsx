import type { Backend } from "../../lib/backends";
import type { MeasuredData, NormCheckData, SolveResponse } from "../../lib/api";
import type { GroundModel } from "../../lib/ground";
import type { ExampleDescriptor } from "../../lib/params";
import type { Projection, View } from "../../lib/view";
import { PROJECTIONS } from "../../lib/view";
import type { PatternMetrics, PinnedPattern } from "../charts/types";
import { Knob } from "../params/Knob";
import { PatternCompareTable } from "./PatternCompareTable";

export function AntennaOverlayControls({
  cameraProjection,
  setCameraProjection,
  isMobile,
  showHeatmap,
  setShowHeatmap,
  showEnvelope,
  setShowEnvelope,
  showWireLabels,
  setShowWireLabels,
  showFeedNames,
  setShowFeedNames,
}: {
  cameraProjection: Projection;
  setCameraProjection: (p: Projection) => void;
  isMobile: boolean;
  showHeatmap: boolean;
  setShowHeatmap: (v: boolean) => void;
  showEnvelope: boolean;
  setShowEnvelope: (v: boolean) => void;
  showWireLabels: boolean;
  setShowWireLabels: (v: boolean) => void;
  showFeedNames: boolean;
  setShowFeedNames: (v: boolean) => void;
}) {
  return (
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
  );
}

// Both smith-overlay children are checkboxes — nothing to keep on mobile
// (the toggles live in the gear menu there).
export function SmithOverlayControls({
  sweepEnabled,
  setSweepEnabled,
  convergeEnabled,
  setConvergeEnabled,
  convergeNValues,
  measured,
  onLoadMeasured,
  onClearMeasured,
}: {
  sweepEnabled: boolean;
  setSweepEnabled: (v: boolean) => void;
  convergeEnabled: boolean;
  setConvergeEnabled: (v: boolean) => void;
  convergeNValues: number[];
  measured: MeasuredData | null;
  onLoadMeasured: (f: File) => void;
  onClearMeasured: () => void;
}) {
  return (
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
        title={`Re-solve at N = ${convergeNValues.join(", ")} segments/wire and Richardson-extrapolate Z to N→∞`}
      >
        <input
          type="checkbox"
          checked={convergeEnabled}
          onChange={(e) => setConvergeEnabled(e.target.checked)}
        />
        converge sweep
      </label>
      <label
        className="overlay-file"
        title="Overlay a measured VNA sweep (one-port Touchstone .s1p, e.g. from a NanoVNA) against the modeled locus"
      >
        <input
          type="file"
          accept=".s1p,.S1P"
          onChange={(e) => {
            const f = e.target.files?.[0];
            // Reset the input so re-picking the same file (after a
            // re-measure) fires onChange again.
            e.target.value = "";
            if (f) onLoadMeasured(f);
          }}
        />
        {measured ? `measured: ${measured.label}` : "measured .s1p…"}
      </label>
      {measured && (
        <button
          type="button"
          className="overlay-clear"
          title="Remove the measured overlay"
          onClick={onClearMeasured}
        >
          clear
        </button>
      )}
    </div>
  );
}

// On mobile only the Δ readout survives (it's output, not a control, and
// it's one short span); the norm-check toggle lives in the gear menu. The
// caller skips this entirely when it would be empty (see the `!isMobile ||
// (normCheckEnabled && normCheck)` gate at the call site).
export function FarFieldOverlayControls({
  isMobile,
  normCheckEnabled,
  setNormCheckEnabled,
  normCheck,
  backend,
  groundModel,
  necOverlayEnabled,
  setNecOverlayEnabled,
}: {
  isMobile: boolean;
  normCheckEnabled: boolean;
  setNormCheckEnabled: (v: boolean) => void;
  normCheck: NormCheckData | null;
  backend: Backend;
  groundModel: GroundModel;
  necOverlayEnabled: boolean;
  setNecOverlayEnabled: (v: boolean) => void;
}) {
  return (
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
      {!isMobile && backend === "pynec" && (
        <label
          className="overlay-checkbox"
          style={
            groundModel === "terrain" ? { opacity: 0.45 } : undefined
          }
          title={
            groundModel === "terrain"
              ? "NEC's rp_card pattern is flat-ground only (no facet model), so the exact-pattern overlay is unavailable over terrain — the terrain traces come from the server's facet physics instead."
              : "Overlay NEC's own rp_card far-field pattern (dashed cyan) as an exact reference for this engine's ground model."
          }
        >
          <input
            type="checkbox"
            checked={necOverlayEnabled && groundModel !== "terrain"}
            disabled={groundModel === "terrain"}
            onChange={(e) => setNecOverlayEnabled(e.target.checked)}
          />
          NEC rp
        </label>
      )}
      {/* Over a finite ground the norm gap IS physics (structural
          loss + real ground absorption), so show it in its honest
          form — the radiated fraction, same number as the Info-pane
          row. Free space / PEC keeps the raw Δ dB, where it is a
          pure solver power-balance diagnostic. Over faceted TERRAIN
          the fraction is PEC-facet-referenced (the server integrates
          the same facet geometry with lossless media as the
          denominator, cancelling the hybrid ledger gap); the ledger
          Δ itself lives in the tooltip and the dotted overlay. */}
      {normCheckEnabled && normCheck && (
        <span
          className="overlay-readout"
          title={
            normCheck.method.startsWith("grid_terrain")
              ? `Share of accepted power leaving as sky wave over the faceted terrain (${normCheck.method}): the same facet geometry integrated with perfect-reflector media is the reference, so the ratio isolates real ground-media absorption. The dotted overlay shows the separate hybrid-model ledger gap (Δ ${normCheck.delta_db >= 0 ? "+" : ""}${normCheck.delta_db.toFixed(2)} dB — the facet far field vs the crest-referenced input power; either sign is normal, and absolute gains stay anchored to the input-power norm, the convention validated against NEC-2's cliff).`
              : normCheck.method.startsWith("grid_")
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
  );
}

// The cut-angle knob lives on the plot it drives: the azimuth (xy) cut is
// taken at elevation azElevDeg; the elevation (yz) cut is taken at azimuth
// bearing elevAzDeg. CCW dials from 3 o'clock.
export function CutAngleOverlay({
  v,
  azElevDeg,
  setAzElevDeg,
  elevAzDeg,
  setElevAzDeg,
}: {
  v: View;
  azElevDeg: number;
  setAzElevDeg: (v: number) => void;
  elevAzDeg: number;
  setElevAzDeg: (v: number) => void;
}) {
  return (
    <>
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
    </>
  );
}

export function CompareOverlay({
  pinCurrentPattern,
  setCompareCollapsed,
  result,
  pinnedPatterns,
  compareCollapsed,
  clearPins,
  liveMetrics,
  currentExample,
  geometry,
  measFreq,
  removePin,
  togglePin,
}: {
  pinCurrentPattern: () => void;
  setCompareCollapsed: (v: boolean) => void;
  result: SolveResponse | null;
  pinnedPatterns: PinnedPattern[];
  compareCollapsed: boolean;
  clearPins: () => void;
  liveMetrics: PatternMetrics | null;
  currentExample: ExampleDescriptor | undefined;
  geometry: string;
  measFreq: number;
  removePin: (id: string) => void;
  togglePin: (id: string) => void;
}) {
  return (
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
  );
}
