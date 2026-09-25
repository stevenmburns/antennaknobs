
import { useEffect, useRef, useState } from "react";
import type { MeasuredData, NormCheckData, SolveResponse } from "../../lib/api";
import type { GroundModel } from "../../lib/ground";
import type { ExampleDescriptor } from "../../lib/params";
import type { CombinedFill, Projection, View } from "../../lib/view";
import { PROJECTIONS } from "../../lib/view";
import type { Layout } from "../session/useViewPrefs";
import type {
  FarFieldCaptions,
  PatternMetrics,
  PinnedPattern,
} from "../charts/types";
import { Knob } from "../params/Knob";
import { PatternCompareTable } from "./PatternCompareTable";
import { SolverAdvisories, type Advisory } from "./SolverAdvisories";

// How long the mouse must be still before the layout toggle fades. Long
// enough that it never flickers during normal pointer travel toward it,
// short enough that reading the chart under it is never blocked.
export const LAYOUT_TOGGLE_IDLE_MS = 1200;

// The rail/grid segmented control (unit 3, docs/plan-view-rail-scaling.md
// "Layout modes"): two presets over the same pinned set. Placed by the
// caller in the stage's top-right corner, desktop only — it lives in
// DesignSession's desktop return branch, which the mobile branch never
// reaches, so "hidden on mobile" needs no prop here.
//
// It sits ON TOP of chart content (the stage corner is not reserved), so it
// fades out after LAYOUT_TOGGLE_IDLE_MS without mouse activity and comes
// back on any movement — present while the user is driving, gone while they
// are reading. While faded it also drops pointer-events, so the data under
// it is hoverable, not just visible. Hover and keyboard focus hold it
// visible: a cursor resting on the control (or a Tab stop inside it) is
// intent, not idleness.
export function LayoutModeToggle({
  layout,
  setLayout,
}: {
  layout: Layout;
  setLayout: (l: Layout) => void;
}) {
  const [idle, setIdle] = useState(false);
  const holdRef = useRef(false); // hovered or focus-within: never fade
  const timerRef = useRef<number | null>(null);
  useEffect(() => {
    const arm = () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => {
        if (!holdRef.current) setIdle(true);
      }, LAYOUT_TOGGLE_IDLE_MS);
    };
    const wake = () => {
      setIdle(false);
      arm();
    };
    window.addEventListener("mousemove", wake);
    window.addEventListener("pointerdown", wake);
    arm();
    return () => {
      window.removeEventListener("mousemove", wake);
      window.removeEventListener("pointerdown", wake);
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);
  const hold = (v: boolean) => {
    holdRef.current = v;
    if (v) setIdle(false);
  };
  return (
    <div
      className={`layout-toggle${idle ? " layout-toggle-idle" : ""}`}
      role="group"
      aria-label="Stage layout"
      onMouseEnter={() => hold(true)}
      onMouseLeave={() => hold(false)}
      onFocus={() => hold(true)}
      onBlur={() => hold(false)}
    >
      <button
        type="button"
        className={layout === "rail" ? "active" : ""}
        aria-pressed={layout === "rail"}
        title="Rail: one primary view plus the pinned thumbnails"
        onClick={() => setLayout("rail")}
      >
        ▤
      </button>
      <button
        type="button"
        className={layout === "grid" ? "active" : ""}
        aria-pressed={layout === "grid"}
        title="Grid: equal cells over the first pinned views"
        onClick={() => setLayout("grid")}
      >
        ⊞
      </button>
    </div>
  );
}

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

// The sweep's own advisories (AK#1682), on the three views that draw the
// sweep. Rendered by the same SolverAdvisories a solve's notes use, so a
// sweep off a deck's NT frequency reads exactly like the live solve's note
// about the same cards — muted and labelled "Advisory", not an error.
// Bottom-left, the one stage corner no control claims (the view controls
// sit top-right, the grid's maximize glyph top-left, the ws status
// bottom-right). Nothing at all when the closing record had no key.
export function SweepAdvisoryOverlay({
  advisories,
}: {
  advisories: Advisory[] | null | undefined;
}) {
  if (!advisories || advisories.length === 0) return null;
  return (
    <div className="sweep-advisory-overlay" role="note" aria-label="Sweep advisories">
      <SolverAdvisories advisories={advisories} />
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
        title={`Re-solve at N = ${convergeNValues.join(", ")} segments per λ/4 and Richardson-extrapolate Z to N→∞`}
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
function signed(x: number, digits: number): string {
  return `${x >= 0 ? "+" : ""}${x.toFixed(digits)}`;
}

// The far-field chart's own corner captions, shown in the stage's overlay
// stack rather than printed on the canvas, where a control could cover them
// (AC6LA, QRZ #115), plus where the maximum is (AK#1632). The slice max is the
// peak of the trace on screen and costs nothing; the 3-D max needs a full
// far-field solve, so it is shown when the pattern metrics are already in hand
// and fetched on a click otherwise. Clicking it aims both cut knobs there.
function SlicePeak({ captions }: { captions: FarFieldCaptions }) {
  if (captions.peakDbi == null || captions.peakAngleDeg == null) return null;
  const where = captions.cut === "xy" ? "az" : "el";
  return (
    <span
      className="overlay-readout overlay-peak"
      title={`The maximum of this ${captions.cut === "xy" ? "azimuth" : "elevation"} cut and where it is on the cut (EZNEC's "Slice Max Gain"). Over the far side of the zenith an elevation reads past 90°.`}
    >
      peak {signed(captions.peakDbi, 1)} dBi @ {where}{" "}
      {Math.round(captions.peakAngleDeg)}°
    </span>
  );
}

function PeakReadout({
  captions,
  alsoPeak,
  maxMetrics,
  maxPending,
  canFindMax,
  onFindMax,
  onAimAtMax,
  onDismissMax,
}: {
  captions: FarFieldCaptions;
  /** The combined view's second cut (AK#1730): its slice peak, under the
   *  first. The 3-D max and the captions below it are the solve's, shown once. */
  alsoPeak?: FarFieldCaptions | null | undefined;
  maxMetrics: PatternMetrics | null;
  maxPending: boolean;
  canFindMax: boolean;
  onFindMax: () => void;
  onAimAtMax: (m: PatternMetrics) => void;
  onDismissMax: () => void;
}) {
  return (
    <>
      <SlicePeak captions={captions} />
      {alsoPeak && <SlicePeak captions={alsoPeak} />}
      {maxMetrics ? (
        <span className="overlay-max-row">
          <button
            type="button"
            className="overlay-readout overlay-max"
            onClick={() => onAimAtMax(maxMetrics)}
            title="The whole pattern's maximum, and where it is. Click to aim both cuts through it."
          >
            3-D max {signed(maxMetrics.peak_gain_dbi, 1)} dBi{" "}
            {/* Two lines, so the readout stays narrow on a small stage. */}
            <span className="overlay-max-where">
              @ az {Math.round(maxMetrics.azimuth_deg) % 360}°, el{" "}
              {Math.round(maxMetrics.takeoff_deg)}°
            </span>
          </button>
          <button
            type="button"
            className="overlay-dismiss"
            onClick={onDismissMax}
            aria-label="Dismiss the 3-D max"
            title="Dismiss the 3-D max (find it again to bring it back)"
          >
            ×
          </button>
        </span>
      ) : (
        <button
          type="button"
          className="overlay-readout overlay-max"
          onClick={onFindMax}
          disabled={maxPending || !canFindMax || captions.peakDbi == null}
          title="Find the whole pattern's maximum (a full far-field solve), then click it to aim both cuts through it."
        >
          {maxPending ? "finding 3-D max…" : "find 3-D max"}
        </button>
      )}
      {captions.field && (
        <span
          className={`overlay-caption${captions.field === "with diffraction" ? " overlay-caption-strong" : ""}`}
        >
          {captions.field}
        </span>
      )}
      {captions.belowGroundPct != null && (
        <span className="overlay-caption">
          {captions.belowGroundPct}% of current below ground
        </span>
      )}
    </>
  );
}

export function FarFieldOverlayControls({
  isMobile,
  normCheckEnabled,
  setNormCheckEnabled,
  normCheck,
  backend,
  groundModel,
  necOverlayEnabled,
  setNecOverlayEnabled,
  captions,
  alsoPeak,
  overlayToggles = true,
  maxMetrics,
  maxPending,
  canFindMax,
  onFindMax,
  onAimAtMax,
  onDismissMax,
}: {
  isMobile: boolean;
  normCheckEnabled: boolean;
  setNormCheckEnabled: (v: boolean) => void;
  normCheck: NormCheckData | null;
  /** Backend NAME; the NEC-overlay switch is PyNEC-only. */
  backend: string;
  groundModel: GroundModel;
  necOverlayEnabled: boolean;
  setNecOverlayEnabled: (v: boolean) => void;
  captions: FarFieldCaptions | null;
  /** See PeakReadout's `alsoPeak` (the combined view). */
  alsoPeak?: FarFieldCaptions | null;
  /** The norm-check and NEC-rp switches. The combined view draws neither
   *  overlay, so it hides them (the norm readout still shows while on). */
  overlayToggles?: boolean;
  maxMetrics: PatternMetrics | null;
  maxPending: boolean;
  canFindMax: boolean;
  onFindMax: () => void;
  onAimAtMax: (m: PatternMetrics) => void;
  onDismissMax: () => void;
}) {
  return (
    <div className="farfield-overlay">
      {captions && (
        <PeakReadout
          captions={captions}
          alsoPeak={alsoPeak}
          maxMetrics={maxMetrics}
          maxPending={maxPending}
          canFindMax={canFindMax}
          onFindMax={onFindMax}
          onAimAtMax={onAimAtMax}
          onDismissMax={onDismissMax}
        />
      )}
      {!isMobile && overlayToggles && (
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
      {!isMobile && overlayToggles && (backend === "pynec" || backend === "nec5") && (
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
          {/* The legend the chart used to print in its corner. */}
          {captions?.necOverlay && (
            <span className="nec-swatch" aria-label="dashed cyan line" />
          )}
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
  const elevationKnob = (
    <div
      className="cut-overlay-knob"
      title="elevation at which the azimuth cut is taken"
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
  );
  const azimuthKnob = (
    <div
      className="cut-overlay-knob"
      title="azimuth bearing at which the elevation cut is taken"
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
  );
  if (v === "azimuth") return <div className="cut-overlay">{elevationKnob}</div>;
  if (v === "elevation") return <div className="cut-overlay">{azimuthKnob}</div>;
  // The combined view (AK#1730) draws both cuts, so it carries both knobs.
  if (v === "combined") {
    return (
      <div className="cut-overlay cut-overlay-pair">
        {elevationKnob}
        {azimuthKnob}
      </div>
    );
  }
  return null;
}

// The combined view's key and fill switch (AK#1730), small, over the stage's
// lower-left corner above the solve readout. Colour says which CUT a trace is;
// which DESIGN is the compare table's job, whose rows highlight designs.
export function CombinedLegend({
  fill,
  setFill,
}: {
  fill: CombinedFill;
  setFill: (f: CombinedFill) => void;
}) {
  return (
    <div className="combined-legend" aria-label="Combined pattern key">
      <span>
        <span className="combined-legend-line combined-az" aria-hidden="true" />
        az
      </span>
      <span>
        <span className="combined-legend-line combined-el" aria-hidden="true" />
        el
      </span>
      <span
        className="combined-fill"
        role="group"
        aria-label="Fill"
        title="Fill the live elevation half-lobe, for reading the low angles"
      >
        fill
        {(["none", "elevation"] as const).map((f) => (
          <button
            key={f}
            type="button"
            className={`combined-fill-btn${fill === f ? " is-active" : ""}`}
            aria-pressed={fill === f}
            onClick={() => setFill(f)}
          >
            {f === "none" ? "none" : "el"}
          </button>
        ))}
      </span>
    </div>
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
  cutLabel,
  highlight,
  onToggleHighlight,
  onClearHighlight,
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
  /** The chart's cut caption, shown above the Pin button (see PeakReadout). */
  cutLabel: string | null;
  /** The combined view's row highlight (AK#1730; see PatternCompareTable).
   *  Omitted on the one-cut views, whose table is unchanged. */
  highlight?: readonly string[];
  onToggleHighlight?: (id: string) => void;
  onClearHighlight?: () => void;
}) {
  // "all": back to no highlight, every trace at full strength. Shown only
  // while something is highlighted, beside the table or its collapsed chip, so
  // the way back is on screen whenever there is somewhere to come back from.
  const allButton =
    onClearHighlight && highlight && highlight.length > 0 ? (
      <button
        type="button"
        className="pin-clear"
        onClick={onClearHighlight}
        title="Un-highlight every design: all traces at full strength"
      >
        all
      </button>
    ) : null;
  return (
    <div className="compare-overlay">
      {cutLabel && <span className="overlay-caption">{cutLabel}</span>}
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
          <>
            <button
              type="button"
              className="pin-btn pin-chip"
              onClick={() => setCompareCollapsed(false)}
              title="Show the pinned-pattern comparison table"
            >
              {pinnedPatterns.length} pinned ▾
            </button>
            {allButton}
          </>
        ) : (
          <>
            <div className="pin-table-actions">
              {allButton}
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
              {...(onToggleHighlight
                ? { highlight: highlight ?? [], onToggleHighlight }
                : {})}
            />
          </>
        ))}
    </div>
  );
}
