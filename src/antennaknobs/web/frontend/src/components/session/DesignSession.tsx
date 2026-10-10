import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  backendAllowed,
  RESTRICTED_BACKEND_REASON,
  designRefusal,
  type DesignConstraintInputs,
  backendDisplayLabel,
  backendSupportsGround,
  comboInappropriate,
  defaultNPerWireFor,
  modelOptionsForRequest,
  SOLVER_SLOTS,
  type Slot,
  slotOrder,
  normalizeBackend,
  type BackendRoster,
  type ModelOptionSpecs,
  type ServedSlotSeed,
  type CompositionVocabulary,
} from "../../lib/backends";
import {
  bandContaining as bandContainingIn,
  customBandSpec,
  freqWindowCeiling as freqWindowCeilingFor,
  isCustomBand,
} from "../../lib/bands";
import {
  findLinkedDesignFreq,
  groupExamplesForPicker,
  findKnobSpec,
  isGroup,
  knobKey,
  linkedMeasFreqFor,
  overlaySchemaForVariant,
  seedDefaults,
  setValueAtPath,
  snapForExample,
  type BandSpec,
  type ExampleDescriptor,
  type ParamValueBag,
  type SchemaItem,
  type SchemaParamSpec,
} from "../../lib/params";
import {
  CHART_COPIES,
  CHART_VIEW_IDS,
  chartIndex,
  MAX_CHARTS,
  mobileScreens,
  prefView,
  VIEW_META,
  type View,
} from "../../lib/view";
import { useZoOverride } from "../../lib/zoOverride";
import {
  defaultSweepPoints,
  designSweepRange,
  resolveSweepRange,
  sweepGrid,
  type SweepRange,
  type SweepRangeInputs,
  SWEEP_TIME_LIMIT,
  sweepTimeLimitNote,
} from "../../lib/sweep";
import type {
  MeasuredData,
  SolveRequest,
  SolveResponse,
} from "../../lib/api";
import type {
  SoilPresetSchema,
  SoilRanges,
  TerrainPresetSchema,
} from "../../lib/ground";
import {
  designGround,
  GROUND_SLOTS,
  groundRefusal,
  groundSlotLabel,
  mixedGroundNote,
  solvePairLabel,
  sommerfeldSlotFor,
  type GroundSlotId,
} from "../../lib/groundSlots";
import {
  type CellState,
  type ChartCell,
  type ChartCross,
  checkedGrounds,
  checkedSlots,
  type CrossEnv,
  CURVE_CAP,
  type CrossPlan,
  crossPlan,
  engineRefusal,
  engineSpecHeld,
  groundSpecHeld,
  type KnobValue,
  type ScalarKnob,
  type ListedCross,
  pickNote,
  preselect,
  skippedNote,
  servedCell,
} from "../../lib/chartCells";
import { ChartScaleContext } from "../charts/chartScale";
import { cellColor, sweepPinColor } from "../charts/palette";
import { metricCaption, metricSeries } from "../../lib/metricPlot";
import type { ExtraCurve, PinCurve } from "../charts/curves";
import type { ChartLegendData, ChartLegendPin } from "../results/ChartLegend";
import {
  changedKnobs,
  type ChartX,
  FREQUENCY_X,
  knobX,
  pinCsv,
  pinCsvName,
  pinCurve,
  pinLabel,
  type PinnableCurve,
  pinsFromCurves,
  placePin,
  z0Note,
} from "../../lib/sweepPins";
import type { ChartChrome } from "../results/AnalysisChartControls";
import { BackendConfigModal } from "../backend/BackendConfigModal";
import { ParamForm } from "../params/ParamForm";
import { combinedPhoneChartSize, effectiveHighlight, toggleHighlight } from "../charts/combined";
import { setCutRefineEnabled } from "../charts/cuts";
import type {
  FarFieldCaptions,
  FarFieldCut,
  PatternMetrics,
} from "../charts/types";
import {
  ThemeContext,
  useFullscreen,
  useGridCellSize,
  useIsMobile,
  useSlideSize,
  useThumbColumnSize,
} from "../hooks";
import { SolveReadout } from "../results/SolveReadout";
import { groundEngineSignature } from "../../lib/solveSignature";
import {
  AntennaOverlayControls,
  CombinedLegend,
  CompareOverlay,
  CutAngleOverlay,
  FarFieldOverlayControls,
  LayoutModeToggle,
  SweepAdvisoryOverlay,
} from "../results/StageOverlays";
import { ViewGrid } from "../results/ViewGrid";
import { ViewPanel } from "../results/ViewPanel";
import type { ChartFrequencyRender, ChartMapRender } from "../results/viewRegistry";
import {
  fetchMetrics,
  PinsContext,
  SessionsContext,
  SweepPinsContext,
  ThemeControlContext,
} from "./contexts";
import { CatalogPanel } from "./CatalogPanel";
import { DesignFreqRow } from "./DesignFreqRow";
import { GroundNotices } from "./GroundPanel";
import { GroundConfigModal } from "./GroundConfigModal";
import { GroundSlotTabs } from "./GroundSlotTabs";
import { KnobOptMenu } from "./KnobOptMenu";
import { SweepRangeMenu } from "./SweepRangeMenu";
import { copyParams, downloadNec, loadMeasured, saveTextFile } from "./sessionActions";
import { SessionGearMenu } from "./SessionGearMenu";
import { SolveOverlays } from "./SolveOverlays";
import { SolverSlotTabs } from "./SolverSlotTabs";
import { type ChartCellRequest, NOT_APPROVED, patternSignature, useAnalysisRunners } from "./useAnalysisRunners";
import { type CellRun, type CellRunners, useChartCells } from "./useChartCells";
import { usePatternCell } from "./usePatternCell";
import { mapSignature, useMapRun } from "./useMapRun";
import { useDesignAnalyses } from "./useDesignAnalyses";
import {
  type DeepLink,
  linkHref,
  linkSearch,
  type LinkState,
  resolveAnalysis,
  resolveDesign,
  resolveVariant,
  resolveView,
} from "../../lib/deepLink";
import {
  analysisBlocked,
  analysisSpec,
  type AnalysisEntry,
  entryLabel,
  type Listed,
  listRange,
} from "../../lib/analyses";
import {
  keptAsResult,
  keptMarks,
  keptForm,
  keptValues,
  type KeptRun,
} from "../../lib/keptRun";
import { fmtFreq } from "../../lib/optBands";
import type { KeptReadout } from "./OptBands";
import type { SweepAxisChoice, SweepMode } from "../../lib/sweepAxis";
import {
  type AnalysisChartState,
  type ChartSeed,
  type KnobView,
  type ChartView,
  chartDwell,
  chartFamily,
  chartHold,
  chartForNewDesign,
  chartFrequencyRange,
  chartLinkCut,
  chartListed,
  chartMetric,
  chartPatternView,
  chartRunInputs,
  chartView,
  chartViews,
  cutAngle,
  cutAngleProblem,
  type DwellDefaults,
  editRange,
  FAMILY_FREQ,
  familyKnobList,
  familyListed,
  familyPatternViews,
  familySpec,
  frequencyRx,
  initialChart,
  patternViewLabel,
  pickedEdited,
  pickedName,
  pickFrequency,
  pickKnob,
  pickOwnFrequency,
  pickMap,
  pickPattern,
  pickRuns,
  editMapAxis,
  restoreMapAxes,
  setChartCut,
  setChartView,
  withListed,
} from "../../lib/analysisChart";
import {
  DEFAULT_DENSITY_SPEC,
  defaultKnobSpec,
  DENSITY,
  paramValues as paramLadder,
  type ParamSweepSpec,
  type RxAxisChoice,
  sameSpec,
  sweepableKnobs,
} from "../../lib/paramSweep";
import { FrequencyChartControls, PatternChartControls } from "../results/AnalysisChartControls";
import { MapChartControls, mapCostLine, mapOverLimit } from "../results/MapChartControls";
import { emptyGrid } from "../../lib/mapGrid";
import { ZParamControls } from "../results/ZParamControls";
import { ZParamStage } from "../results/ZParamStage";
import { KeepDialog, type KeepDialogProps } from "../results/KeepDialog";
import {
  type KeepBody,
  keepRequest,
  mapAxesKeep,
  patternPinsKeep,
  type SweepPinKeep,
  sweepPinsBlocked,
} from "../../lib/keep";
import { apiFetch } from "../../lib/pin";

// The Z-vs-parameter header's height on a phone (two wrapped rows plus its
// margin), which the chart below it gives up.
const ZPARAM_MOBILE_HEADER_PX = 96;

// A map pins nothing in v1 (docs/design/sweep-framework-map.md, decision
// 11: map pins as dashed contours are a later unit).
const MAP_PIN_BLOCKED = "A map has no pins yet: map pins (dashed contours) are a later step";
// ...and on a desktop stage, before ZParamStage has measured the real one
// (the first frame): one row above the chart.
const ZPARAM_DESKTOP_HEADER_PX = 48;
import { useCapabilities } from "./useCapabilities";
import {
  type RunOnPickKind,
  saveSettings,
  type SettingsSaveBody,
  type UiDefaults,
} from "../../lib/settings";
import { useDesignCatalog } from "./useDesignCatalog";
import { useGroundConfig } from "./useGroundConfig";
import { MobileDots } from "./MobileDots";
import { useMobileCarousel } from "./useMobileCarousel";
import { useOptimizer } from "./useOptimizer";
import { useEngineFiles } from "./useEngineFiles";
import { useSchematic } from "./useSchematic";
import { useSolveChannel } from "./useSolveChannel";
import { useSolverSlots } from "./useSolverSlots";
import { gridCells, gridShape, useViewPrefs, withChartCopies } from "./useViewPrefs";
import { useViewState } from "./useViewState";
import { ViewPicker } from "./ViewPicker";
import { VfoPanel, type OptimizeResult } from "./VfoPanel";
import { DeckNotice } from "./DeckNotice";
import { deckFor, isDeck, openDeck, openDeckFile, type Dialect } from "../../lib/decks";

// One antenna design session: the entire left sidebar + right stage plus all
// the state, effects, and the WebSocket that drive them. The shell (`App`,
// below) mounts one instance per tab and passes `active` — true only for the
// visible tab. An inactive session stays mounted, so its inputs survive, but
// suspends its WebSocket, global key listeners, and background solves via the
// `active` gates threaded through the effects below. Theme is global and lives
// in the shell; the canvases here read it through ThemeContext.
// Capabilities gate. The solver picker, the slot seeds and the ground panel
// are all rendered from server data now (#628/#560), and there is deliberately
// no hardcoded fallback roster to render from meanwhile — that duplication is
// the bug this closes. So the session tree mounts only once /capabilities has
// answered; this wrapper holds the one hook that decides, which keeps the
// body's own (large, order-sensitive) hook sequence untouched.
/** What `/ws` returns alongside a tracked solve (#1220). */
type TrackStatus = {
  status: "tracking" | "frozen" | "latched" | "refused";
  message: string | null;
  params: Record<string, number>;
  residual: number | null;
};

export function DesignSession({
  id,
  active,
  deepLink = null,
}: {
  id: number;
  active: boolean;
  /** The link the page was opened with (AK#1838), for the first tab only:
   *  what it opens on. Null: the session's own defaults. */
  deepLink?: DeepLink | null;
}) {
  const {
    roster,
    terrainPresets,
    soilPresets,
    soilRanges,
    modelOptionSpecs,
    backendAliases,
    defaultSlotSeeds,
    compositionVocab,
    uiDefaults,
    versionLabel,
    canSaveStudies,
    error,
  } = useCapabilities();
  if (error !== null)
    return (
      <div className="app app-capabilities" role="alert">
        Could not start the workbench: {error}. Reload once the server is
        reachable; if this persists, the page and its server do not match.
      </div>
    );
  // useCapabilities sets the roster and the startup settings together, or
  // neither and an error.
  if (roster === null || uiDefaults === null)
    return <div className="app app-capabilities">loading solver catalog…</div>;
  return (
    <DesignSessionBody
      id={id}
      active={active}
      roster={roster}
      terrainPresets={terrainPresets}
      soilPresets={soilPresets}
      soilRanges={soilRanges}
      modelOptionSpecs={modelOptionSpecs}
      backendAliases={backendAliases}
      defaultSlotSeeds={defaultSlotSeeds}
      compositionVocab={compositionVocab}
      uiDefaults={uiDefaults}
      versionLabel={versionLabel}
      canSaveStudies={canSaveStudies}
      deepLink={deepLink}
    />
  );
}

function DesignSessionBody({
  id,
  active,
  deepLink,
  roster,
  terrainPresets,
  soilPresets,
  soilRanges,
  modelOptionSpecs,
  backendAliases,
  defaultSlotSeeds,
  compositionVocab,
  uiDefaults,
  versionLabel,
  canSaveStudies,
}: {
  id: number;
  active: boolean;
  deepLink: DeepLink | null;
  roster: BackendRoster;
  terrainPresets: TerrainPresetSchema[];
  /** Served soil catalog + knob bounds (#1173). */
  soilPresets: SoilPresetSchema[];
  soilRanges: SoilRanges | null;
  /** The served solver-knob catalogue (#1006 G2-6). */
  modelOptionSpecs: ModelOptionSpecs;
  backendAliases: Record<string, string>;
  defaultSlotSeeds: ServedSlotSeed[];
  compositionVocab: CompositionVocabulary;
  /** Where the session starts (AK#1492): switches and ground from settings.toml. */
  uiDefaults: UiDefaults;
  /** "v0.77.0 · momwire v0.55.0" (AK#1517), rendered under the brand as-is;
   *  null from a server predating it. */
  versionLabel: string | null;
  /** "Save as study" may write a file (AK#1757 step 7 unit 4). */
  canSaveStudies: boolean;
}) {
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

  // Free-text filter for the antenna selector — matches name / label /
  // family / keywords so users can find a design without knowing its family.
  const [geomFilter, setGeomFilter] = useState<string>("");
  // Multi-band antennas (fan_dipole) get a nested shape for groups —
  // `paramValues[name].bands` is an array of per-instance bags,
  // pre-allocated to ParamGroupSpec.max_repeats so dialing the
  // repeat-count down and back up preserves the values.
  const [paramValues, setParamValues] = useState<Record<string, ParamValueBag>>({});
  // Per-geometry variant selection (which `<name>_params` dict on the
  // Builder to seed from). Falls back to the example's variants[0]
  // when this map has no entry — `default` for designs that declare
  // it, otherwise whatever the example shipped first.
  const [variantByGeom, setVariantByGeom] = useState<Record<string, string>>({});

  // Live simulation: when on, knob/freq changes auto-solve (and the optimiser
  // runs). When off ("Paused"), edits update the geometry but the engine is held
  // — the user keeps changing the design, then clicks Live to resume and solve.
  // This replaces the old fire-and-forget "Cancel" on the solver-mismatch prompt,
  // which left the plots blank with no obvious way back. Defaults on.
  const [autoSim, setAutoSim] = useState(uiDefaults.switches.live);
  // Does picking an analysis start it, per kind (AC6LA, QRZ 1003328 #179):
  // settings.toml's [workbench.run_on_pick], flipped in the gear menu for
  // this session and written by "save as my defaults".
  const [runOnPick, setRunOnPick] = useState<Record<RunOnPickKind, boolean>>(uiDefaults.runOnPick);

  const {
    examples,
    examplesError,
    loadErrors,
    trustBusy,
    trustDesign,
    reloadCatalog,
  } = useDesignCatalog({
    geometry,
    setGeometry,
    setParamValues,
    // A deep link's design, when the catalog holds it (AK#1838): the
    // session opens on it rather than on invvee.
    preferred: (list) => {
      if (!deepLink?.design) return null;
      const r = resolveDesign(deepLink.design, list);
      return r.ok ? r.value : null;
    },
  });

  // Reload the selected user design from disk (issue #867). Re-fetching
  // /examples makes the server re-register user designs; bumping the nonce
  // re-runs the preview effect below for the SAME geometry, and its
  // previewReady release then re-fires the live solve — exactly the design-
  // switch path, minus the selection change. Load errors and awaiting-trust
  // states ride along on the same fetch, so a broken edit surfaces in the
  // usual panels.
  const [reloadNonce, setReloadNonce] = useState(0);
  // "Copy as analysis" / "keep as study" (AK#1757 step 7 unit 4): the open
  // dialog's title, what it keeps and its starting name, or null; and a
  // generation bumped by a save, so the tab re-reads its analyses and the
  // new study appears in its picker's Studies group.
  const [keeping, setKeeping] = useState<Pick<KeepDialogProps, "title" | "body" | "initialName"> | null>(
    null,
  );
  const [studiesNonce, setStudiesNonce] = useState(0);
  const [reloadBusy, setReloadBusy] = useState(false);
  // The catalog button: a re-fetch always (the server rescans the user-design
  // folder on every GET /examples). Only a selected USER design is also
  // re-previewed and re-solved — its file may have changed; a built-in one
  // has not, so rescanning for new files does not cost it a solve.
  const reloadDesigns = useCallback(async () => {
    setReloadBusy(true);
    try {
      await reloadCatalog();
      if (geometry.startsWith("user.")) setReloadNonce((n) => n + 1);
    } finally {
      setReloadBusy(false);
    }
  }, [reloadCatalog, geometry]);

  const currentExample = examples.find((e) => e.name === geometry);
  // What the loaded design tells a solver slot (#1006 G2-5, AK#1891): its
  // geometry's refusal inputs and its kernel default, from the descriptor.
  const designConstraintInputs: DesignConstraintInputs = useMemo(
    () => ({
      has_stepped_radius_junction:
        currentExample?.has_stepped_radius_junction ?? false,
      buried: currentExample?.has_buried_wire ?? false,
      extended_kernel_default: currentExample?.extended_kernel_default ?? false,
    }),
    [currentExample],
  );
  // currentValues is deliberately a fresh reference whenever paramValues[geometry]
  // is unset (the `?? {}` fallback) — currentValuesKey (below) is the stable
  // primitive signature every downstream effect/memo actually keys off, so the
  // useMemo at currentValuesKey re-running every render here costs a
  // JSON.stringify, not correctness: its *output* is a string, compared by
  // value everywhere it's used as a dep, not by the identity of this object.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const currentValues = paramValues[geometry] ?? {};

  // Selector contents: filter by the search box (always keeping the current
  // selection visible so the <select> value stays valid), then group by
  // family in FAMILY_ORDER.
  const geomQuery = geomFilter.trim().toLowerCase();
  const geomGroups = groupExamplesForPicker(examples, geometry, geomQuery);
  const currentVariant =
    variantByGeom[geometry] ?? currentExample?.variants?.[0] ?? "default";

  // param_schema with the active variant's explicit presentation
  // overrides (variant_ui[variant].params) overlaid per param — e.g.
  // invvee's long-wire variants carry their own length_factor slider
  // range. Feeds the knob rail and the per-knob optimiser menu so both
  // see variant-correct bounds; value seeding stays on the raw schema
  // (defaults/values are variant_values' job).
  const currentSchema = useMemo<SchemaItem[]>(
    () => overlaySchemaForVariant(currentExample, currentVariant),
    [currentExample, currentVariant],
  );

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
      // A variant's stock design_freq wins when it carries one — freq is
      // the OPERATING freq, and off-band variants keep the two apart
      // (see snapForExample).
      const vd =
        typeof vv.design_freq === "number" ? vv.design_freq : vv.freq;
      setDesignFreq(vd);
      if (vd !== vv.freq) {
        setLinkMeas(false);
        setMeasFreq(vv.freq);
      } else if (linkMeas || !currentExample.has_design_freq) {
        // Fixed-geometry designs re-anchor unconditionally: their lock is
        // inert (measLockable), so only the variant freq is meaningful.
        setMeasFreq(vv.freq);
      }
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
    followMeas = true,
  ) {
    // Compute the new geometry bag eagerly (outside the setter) so the
    // meas-freq follow logic below can read newRoot reliably. React's
    // useState eager-bailout optimization runs the updater synchronously
    // only when no updates are queued; rapid slider drags batch
    // multiple updates, so a `newRoot` captured inside the updater
    // closure is null on the fast path — which manifests as the linked
    // measFreq snap working on slow drags but not on fast ones.
    const newRoot = setValueAtPath(paramValues[geometry] ?? {}, path, value) as ParamValueBag;
    setParamValues((prev) => ({
      ...prev,
      [geometry]: setValueAtPath(prev[geometry] ?? {}, path, value) as ParamValueBag,
    }));

    // Schema-driven meas-freq follow — see linkedMeasFreqFor for the two
    // variants (group leaf vs. flat scalar `link_meas_freq_to_param`).
    if (!linkMeas || !followMeas) return;
    const freqValue = linkedMeasFreqFor(currentExample, path, newRoot);
    if (freqValue != null) setMeasFreq(freqValue);
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
    // Keyed the way the marks are: a flat knob by its name, a group leaf by
    // its dotted path (AK#1901).
    if (optEnabled) {
      const key = knobKey(path);
      const ko = (knobOpt[geometry] ?? {})[key];
      if (ko?.vary) {
        optAbortRef.current?.abort();
        setOptEnabled(false);
        setOptPausedBy({ kind: "knob", name: key });
      }
    }
    // #1220 rule 1: ownership is unchanged. A marked knob belongs to the
    // optimiser/tracker, so grabbing one by hand switches tracking OFF, exactly
    // as it already switches Optimize off above. The dragged knob is NOT
    // promoted to an independent variable.
    if (path.length === 1 && typeof path[0] === "string") {
      const name = path[0];
      const ko = (knobOpt[geometry] ?? {})[name];
      if (ko?.vary) {
        setTrackEnabled(false);
        trackDragRef.current = null;
      } else if (typeof value === "number") {
        trackDragRef.current = { name, value, span: trackSpanFor(name) };
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
  // Solver slots A / B / C, D / E when added (#642 seam 5b-3). Called at the cluster's own
  // position, so its PyNEC-remap effect keeps its global order.
  const {
    activeSlot,
    setActiveSlot,
    slots,
    backendTouchedRef,
    gearOpen,
    setGearOpen,
    backend,
    currentOpts,
    nPerWire,
    densityNotes,
    backendOptsKey,
    updateSlotOpts,
    setSlotBackend,
    resetSlot,
    nextSlot,
    addSlot,
    removalRefusal: slotRemovalRefusal,
    removeSlot,
  } = useSolverSlots({
    roster,
    specs: modelOptionSpecs,
    seeds: defaultSlotSeeds,
  });
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
  // Bands the user typed in for frequencies the design's table does not cover
  // (#1487), appended to both pickers for this session, newest last.
  const [customBands, setCustomBands] = useState<BandSpec[]>([]);
  const [designFreq, setDesignFreq] = useState(14.3);
  // AK#1682: the user's own sweep range for this session — level 1 of the
  // range precedence in lib/sweep.ts, edited from the measurement dial's
  // right-click menu. Session-only (never written to settings.toml); a design
  // switch or a band pick clears it, and "↺ design range" sets it back to
  // null. `sweepMenu` is where that menu is open, or null.
  const [sweepRangeEdit, setSweepRangeEdit] = useState<SweepRange | null>(null);
  const [sweepMenu, setSweepMenu] = useState<{
    x: number;
    y: number;
    touch: boolean;
  } | null>(null);
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
  // Ground / terrain selection and its derived protocol values (#642 seam
  // 5b-3). Pure state + derivations, so it adds no effects here.
  const {
    groundSlots,
    groundRequestFor,
    groundSlotSettings,
    servedDefaultSoil,
    activeGroundSlot,
    designGroundSlot,
    setActiveGroundSlot,
    nextGroundSlot,
    addGroundSlot,
    groundSlotRemovalRefusal,
    removeGroundSlot,
    applyDesignGround,
    groundEnabled,
    groundModel,
    terrainKey,
    groundSummary,
    soilKey,
  } = useGroundConfig({
    backend,
    soilRanges,
    soilPresets,
    slots: uiDefaults.grounds,
  });
  const onDesignGround = activeGroundSlot === designGroundSlot;
  // The active pair's ground refusal (AK#1856), in the roster's served words:
  // NEC-5 on a refl-coef slot. The solve is withheld like the option refusal
  // below (the server would refuse it), and the way out is one click: the
  // first Sommerfeld slot this solver serves, else the active slot's own
  // method set to Sommerfeld when no slot holds one.
  const activeGround = groundSlots.find((g) => g.id === activeGroundSlot) ?? groundSlots[0];
  const pairRefusal = groundRefusal(activeGround, backend);
  const groundWayOut: { label: string; go: () => void } | null = (() => {
    if (pairRefusal === null) return null;
    const target = sommerfeldSlotFor(groundSlots, backend);
    if (target !== null) {
      return { label: `Switch to ground ${target} (Sommerfeld)`, go: () => setActiveGroundSlot(target) };
    }
    return {
      label: `Solve ground ${activeGround.id} as Sommerfeld`,
      go: () => groundSlotSettings(activeGround.id)?.setFiniteGroundMethod("sommerfeld"),
    };
  })();
  // The ground slot whose ⚙ settings are open (AK#1801), or null. Any slot,
  // not only the active one.
  const [groundGearOpen, setGroundGearOpen] = useState<GroundSlotId | null>(null);
  const nLabel = currentExample?.fixed_segment_counts ? "deck's own" : String(nPerWire);
  const tabSummary = `${(currentExample?.label ?? geometry) || "new design"} · ${backendDisplayLabel(backend, currentOpts, designConstraintInputs)} N=${nLabel} · ${groundSummary}`;
  useEffect(() => {
    reportSummary(id, tabSummary);
  }, [id, tabSummary, reportSummary]);
  // Which views are resident in the desktop rail (global, persisted) — read
  // before useViewState because the arrow-key cycler walks the pinned set.
  // (`togglePin` is renamed: the pattern-pin context below owns that name.)
  const {
    pinned,
    newIds,
    togglePin: toggleViewPin,
    movePin,
    markRosterSeen,
    layout,
    setLayout,
    isReadoutCollapsed,
    setReadoutCollapsed,
    combinedFill,
    setCombinedFill,
    sweepAxes,
    setSweepAxis,
    swrThreshold,
    setSwrThreshold,
    chartView: seededChartView,
    smithYGrid,
    setSmithYGrid,
  } = useViewPrefs();
  // The combined view's highlighted designs (AK#1730): the live design and/or
  // pin ids, toggled per row in the compare table; while any is highlighted
  // the rest dim. Session-only: a reading aid, not a preference.
  const [combinedHighlight, setCombinedHighlight] = useState<string[]>([]);

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

  const [trackEnabled, setTrackEnabled] = useState(false);
  // The values key produced by the tracker's own write-back, so the auto-solve
  // effect does not re-solve a tick whose display solve already arrived.
  const answeredKeyRef = useRef<string | null>(null);
  // Bumped every time the switch turns ON. It rides in `_track` and is part of
  // the server's staleness signature, which is what makes re-enabling the mode
  // a FRESH ROOT FIND from the current point (rule 4) rather than a silent
  // continuation of the tracker that was latched when it was switched off.
  const trackEpochRef = useRef(0);
  // What the user last dragged, for the tick the tracker is answering. `span`
  // is the knob's DISPLAY range, which is what the server's demote stage
  // measures its rate limit against — a fraction of travel, never a tick
  // count, because every per-tick quantity in the #1202 study failed to
  // survive a change of drag resolution.
  const trackDragRef = useRef<{
    name: string;
    value: number;
    span?: number | undefined;
  } | null>(null);
  // The dragged knob's full travel, which is what the server's demote stage
  // measures its rate limit against — a fraction of TRAVEL, never a tick count.
  //
  // There is deliberately NO numeric fallback. A knob the user has never
  // right-clicked has no KnobOpt entry at all, which is every dragged knob in
  // the normal flow, and `defaultKnobOpt` invents 0..1 for a missing spec — so
  // a `?? 1` fallback silently reported a 60° knob as spanning 1°, the demote
  // rate limit was then always due, and the scalar path demoted and latched on
  // the first tick of every drag. Undefined means "travel unknown", and the
  // server keeps demote OFF rather than mis-scaling it.
  function trackSpanFor(name: string): number | undefined {
    const stored = (knobOpt[geometry] ?? {})[name];
    if (stored && stored.dispMax > stored.dispMin)
      return stored.dispMax - stored.dispMin;
    const spec = currentSchema.find(
      (x): x is SchemaParamSpec => !isGroup(x) && x.name === name,
    );
    if (spec && spec.min != null && spec.max != null && spec.max > spec.min)
      return spec.max - spec.min;
    return undefined;
  }

  function toggleTrack(on: boolean) {
    if (on) trackEpochRef.current += 1;
    setTrackEnabled(on);
  }
  const [result, setResult] = useState<SolveResponse | null>(null);
  // The ground and engine the shown result was solved for (AK#1796), as
  // groundEngineSignature of the request that produced it; null when that
  // request is unknown. The readout shows impedance only while this matches
  // what the controls ask for now (`readoutResult`).
  const [resultSolvedFor, setResultSolvedFor] = useState<string | null>(null);
  // #1220: the solve response carries the knob values the tracker moved, so
  // they are written here, on arrival, rather than mirrored in by an effect
  // watching `result` — that would be a setState inside an effect and a second
  // render per drag tick. Written with setParamAtPath and NOT
  // handleUserParamChange: these are the tracker's OWN knobs, and routing them
  // through the user path would trip rule 1 and switch the mode off on its own
  // output.
  function applyResult(next: SolveResponse | null, req?: SolveRequest) {
    setResult(next);
    setResultSolvedFor(next && req ? groundEngineSignature(req) : null);
    const tk = (next as { _track?: TrackStatus } | null)?._track;
    if (!tk) return;
    if (tk.status === "refused") {
      setTrackEnabled(false);
      return;
    }
    const bag = paramValues[geometry] ?? {};
    let after = bag;
    for (const [name, v] of Object.entries(tk.params ?? {})) {
      if (typeof v === "number" && bag[name] !== v) {
        after = setValueAtPath(after, [name], v) as ParamValueBag;
        setParamAtPath([name], v);
      }
    }
    // The key those writes will produce, so the auto-solve effect can tell its
    // own echo from a real change (see the comment there).
    answeredKeyRef.current = after === bag ? null : JSON.stringify(after);
  }
  // Measurement plane (issue #652 c): null = the design's natural source
  // port (the field is then omitted from requests). A picked plane
  // re-solves everything — readout, charts, sweeps, pattern — with the
  // chain upstream of it disconnected, and the schematic marks the cut.
  const [plane, setPlane] = useState<string | null>(null);
  // Geometry-only snapshot of the just-selected antenna (wires + feed marker,
  // no currents), fetched fast so a large design's shape renders immediately
  // instead of waiting tens of seconds for the full solve. Superseded by
  // `result` the moment the real solve lands; only consulted while result is
  // null (i.e. right after an antenna switch).
  const [preview, setPreview] = useState<SolveResponse | null>(null);
  // The server's per-design solver recommendation ("arrayblock" for grid
  // arrays, "sinusoidal" for benchmark-sized meshes, null otherwise) — used
  // by the withhold gate and to pick the right warning copy.
  const recommendedBackend = (() => {
    // normalizeBackend resolves against the SERVED roster, so a
    // recommendation this server can't honour (PyNEC without pynec-accel,
    // #429) comes back null instead of seeding an unofferable solver.
    return normalizeBackend(
      preview?.default_backend ?? currentExample?.default_backend,
      roster,
      backendAliases,
    );
  })();
  // The active design's backend allowlist (null = unrestricted). Only
  // catalog designs carry it — user designs defer their hints, so a
  // restricted user design surfaces the solver's hard error through the
  // normal solve-error banner instead.
  const requiredBackends = currentExample?.requires_backends ?? null;
  // Hard incompatibility: the active backend cannot run this design at all
  // (the solver raises). Distinct from comboInappropriate, which is a
  // performance mismatch the user may override.
  const backendDisallowed = !backendAllowed(backend, requiredBackends);
  // The design-dependent refusal (#1006 G2-5): this backend, with these
  // options, on THIS design. Recomputed every render from the live descriptor,
  // so switching design re-answers it — the property `requires_backends` has
  // and a check made when the engine was picked would not.
  //
  // The inputs come from the descriptor rather than being re-derived here:
  // whether the deck has a stepped-radius junction is a fact about geometry
  // the server already computed while building it (`designConstraintInputs`,
  // declared beside `currentExample`).
  const optionRefusal = designRefusal(
    backend,
    currentOpts,
    designConstraintInputs,
  );
  // True while the live solve is being withheld by the solver-mismatch gate.
  // The batch runners (sweep / converge / norm-check) decline to fire on
  // this: they are batches of the same solves the gate is protecting the
  // machine from (a dense sweep on a benchmark mesh is 41 multi-GiB solves).
  // Their effects depend on `comboApproved`, so "Solve anyway" re-fires them;
  // the server's cost model refuses warned batches without the approval flag
  // anyway (issue #382) — this gate is UX, not the enforcement. A
  // backend-disallowed design withholds unconditionally: there is no
  // approval path around a solver that raises.
  // Withhold, and DROP THE PENDING REQUEST.
  //
  // `controlsRef.current` is filled earlier in the solve effect, before these
  // guards run — deliberately, so a PAUSED session resumes with the latest
  // design. But paused and refused are different: a paused request is valid
  // and waiting, a refused one must never be sent. The channel resends
  // whatever is in that ref on (re)connect, with no gate of its own
  // (useSolveChannel's onopen, #768), so leaving a refused request there is a
  // solve waiting for a socket event to fire it.
  function withhold() {
    controlsRef.current = null;
    withheldRef.current = true;
    setSolverWarning(true);
  }

  function solveWithheld(): boolean {
    return (
      backendDisallowed ||
      // No approval path around this one either: momwire RAISES on the
      // combination, so "Solve anyway" would buy an error dialog. The user's
      // way out is the option, not an override — which is why the overlay
      // names the option rather than offering a button.
      optionRefusal !== null ||
      // NEC-5 on refl-coef (AK#1856): refused by name, no override either.
      pairRefusal !== null ||
      (comboInappropriate(backend, recommendedBackend) &&
        !approvedComboRef.current)
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
  // The reload generation (reloadNonce) the released preview was for.
  const [previewNonce, setPreviewNonce] = useState(-1);
  // The design + reload generation whose released preview the solve effect
  // has acted on (below): the last step of the load path.
  const [loadSettledFor, setLoadSettledFor] = useState("");
  // Whether to render the per-feed (multi-feed) UI. Prefer the value the
  // server folds into the live solve / geometry response — authoritative for
  // user designs, which derive it lazily — and fall back to the example
  // descriptor (eager built-ins) before the first response lands.
  const effectiveMultiFeed =
    result?.multi_feed ??
    preview?.multi_feed ??
    currentExample?.multi_feed ??
    false;
  // The reference impedance (AK#1735). The design's own comes on every solve
  // and preview response (`design_z0_ohms`; an older server's `z0_ohms` is
  // the same number), and the gear menu's Zo field overrides it per design.
  // `z0` is THE reference this session measures against: it rides every
  // request as `z0_ohms` when overridden, and every display of SWR / Γ reads
  // it — through `shownResult` below — rather than the last response's echo,
  // so a Zo edit re-draws at once instead of waiting on a solve.
  const [zoOverride, setZoOverride] = useZoOverride(geometry);
  const ownResponse =
    result?.geometry === geometry
      ? result
      : preview?.geometry === geometry
        ? preview
        : null;
  const designZ0 =
    ownResponse?.design_z0_ohms ?? ownResponse?.z0_ohms ?? 50;
  const z0 = zoOverride ?? designZ0;
  // `result` with the session's reference stamped in, for the views and the
  // readout. Same object when they already agree (every response after the
  // first at a new Zo echoes it), so nothing keyed on identity re-runs.
  const shownResult = useMemo(
    () =>
      result && result.z0_ohms !== z0 ? { ...result, z0_ohms: z0 } : result,
    [result, z0],
  );
  // The last solve that was computed, not served from the cache (whose
  // solve_ms is the lookup's): the map's cost line times a grid at its pace.
  // State adjusted during render, React's pattern for derived state.
  const [freshSolveMs, setFreshSolveMs] = useState<number | null>(null);
  const freshNow =
    shownResult && !shownResult.cache_hit && Number.isFinite(shownResult.solve_ms)
      ? shownResult.solve_ms
      : null;
  if (freshNow !== null && freshNow !== freshSolveMs) setFreshSolveMs(freshNow);
  // The analysis chart (AK#1757, sweep-framework step 5 units 2 and 3): the
  // Z-vs-parameter view grown into THE sweep view, which the standalone
  // Smith, VSWR and S11 views folded into. Its pick, dwell switch, knob spec
  // and axes, or its frequency sweep's range, view and scales
  // (lib/analysisChart). Session state, per tab, and never persisted (Steve,
  // 2026-09-28: only the .py is remembered). One per open chart (unit 4):
  // index 0 is the `zparam` view, and a duplicate takes the first free index
  // of the four (lib/view.ts CHART_VIEW_IDS); a closed duplicate's index is
  // null. `chart` below is the first chart's, which the knob menu's "Sweep
  // this knob…" drives.
  //
  // A new chart is the design's own frequency sweep on the Smith chart, or
  // on the view a migrated pin named (useViewPrefs' chartView), with the
  // viewer's Swr / S11 scales and threshold.
  const chartSeed: ChartSeed = { view: seededChartView, axes: sweepAxes, threshold: swrThreshold };
  const [charts, setCharts] = useState<(AnalysisChartState | null)[]>(() => [
    initialChart(chartSeed),
    ...Array.from({ length: MAX_CHARTS - 1 }, () => null),
  ]);
  // The views this session shows: the stored pins plus its open chart
  // copies (unit 4), which the rail, the grid, the carousel and residency
  // all read; the stored pins stay the viewer's preference and never hold a
  // copy (useViewPrefs' withChartCopies).
  const chartCopiesKey = charts.map((c) => (c ? "1" : "0")).join("");
  const shownViews = useMemo(
    () =>
      withChartCopies(
        pinned,
        CHART_COPIES.filter((_, k) => chartCopiesKey[k + 1] === "1"),
      ),
    [pinned, chartCopiesKey],
  );
  const setChartAt = (i: number, f: (c: AnalysisChartState) => AnalysisChartState) =>
    setCharts((cs) => cs.map((c, k) => (k === i && c ? f(c) : c)));
  const chart = charts[0]!;
  // The dwell switch's default per kind (unit 3): settings.toml's
  // [switches] freq_sweep and convergence_sweep, the two checkboxes it
  // replaced, now seed a chart's switch for a frequency and for a knob or
  // density sweep. Read, never written: a flip of the switch is the
  // chart's, session-only, and a settings save passes the file's own
  // values through (saveDefaults).
  const dwellDefaults: DwellDefaults = {
    frequency: uiDefaults.switches.freq_sweep,
    knob: uiDefaults.switches.convergence_sweep,
  };
  // A knob spec edit. On a knob's family of patterns (AK#1935) it edits the
  // family's knob and range in place (its values capped), and the chart
  // stays the family.
  const setZparamSpecAt = (i: number, spec: ParamSweepSpec) =>
    setChartAt(i, (c) =>
      chartFamily(c)
        ? { ...c, knob: { ...c.knob, spec: familySpec(spec) } }
        : { ...c, kind: "knob", knob: { ...c.knob, spec } },
    );
  const setZparamXLogAt = (i: number, xLog: boolean | null) =>
    setChartAt(i, (c) => ({ ...c, knob: { ...c.knob, xLog } }));
  const setZparamAxisAt = (i: number, axis: "r" | "x", choice: RxAxisChoice) =>
    setChartAt(i, (c) => ({ ...c, knob: { ...c.knob, axes: { ...c.knob.axes, [axis]: choice } } }));
  // A design switch (another example, variant or user design — not a knob
  // change, not a reload of the same design) starts the chart over on the
  // design's own frequency sweep, keeping only how the viewer looks at it:
  // the frequency view, the scales and a flipped dwell switch
  // (chartForNewDesign). Steve (2026-09-26): a length_factor sweep must not
  // follow him onto the next design. State adjusted during render, React's
  // pattern for state derived from a prop.
  const zparamDesignKey = `${geometry}::${currentVariant}`;
  const [zparamDesignFor, setZparamDesignFor] = useState(zparamDesignKey);
  if (zparamDesignFor !== zparamDesignKey) {
    setZparamDesignFor(zparamDesignKey);
    setCharts((cs) => cs.map((c) => (c ? chartForNewDesign(c, chartSeed) : c)));
  }
  // Adaptive resolution (issue #744): dwell-triggered display-space
  // refinement of the sweep and cut plots. Persisted, unlike the overlay
  // checkboxes above: turning it off is a per-machine capacity decision
  // ("this laptop, that 4k-segment design"), not a per-session view choice,
  // and it should survive a reload the same way the theme does.
  //
  // A settings.toml that names `refine` wins over the browser's memory: the
  // packaged workbench opens on a fresh port each launch, and browser storage
  // is per origin, so only the file survives there (AK#1492).
  const [refineEnabled, setRefineEnabled] = useState(() => {
    if (uiDefaults.switchesSet.includes("refine")) return uiDefaults.switches.refine;
    const stored = localStorage.getItem("antennaknobs.refineEnabled");
    return stored === null ? uiDefaults.switches.refine : stored !== "0";
  });
  useEffect(() => {
    localStorage.setItem("antennaknobs.refineEnabled", refineEnabled ? "1" : "0");
    // The cuts side reads a module flag (charts/cuts.ts) rather than a prop
    // — same setting, kept in lockstep here.
    setCutRefineEnabled(refineEnabled);
  }, [refineEnabled]);
  // Measured overlay (issue #595): a VNA .s1p the user picks from their own
  // machine, drawn against the modeled locus. Deliberately client-side state —
  // the file is posted once to be parsed and is never stored server-side, which
  // also means the overlay survives nothing but this tab, by design.
  const [measured, setMeasured] = useState<MeasuredData | null>(null);
  // Far-field norm consistency check: on dwell, recompute the gain norm from
  // the pattern integral (field side) and overlay the resulting pattern
  // (dotted) against the live input-power norm (circuit side). The gap is the
  // solver's power-balance error. Cheap (closed form), so on by default;
  // the checkbox hides the overlay. `normCheck` is null while off or pending.
  const [normCheckEnabled, setNormCheckEnabled] = useState(
    uiDefaults.switches.pattern_renorm,
  );
  // NEC rp_card exact-pattern overlay (PyNEC backend only). User-switchable;
  // forced off (and the switch greyed) over a terrain ground, where NEC's
  // flat-ground rp pattern would silently disagree with the facet traces.
  const [necOverlayEnabled, setNecOverlayEnabled] = useState(true);
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
  // Pinned sweeps (AK#1757 item 1): the shell's too, shared across sessions
  // as the pattern pins are, so a pin outlives the tab that made it.
  const {
    pins: sweepPins,
    addPins: addSweepPins,
    removePin: removeSweepPin,
    togglePin: toggleSweepPin,
  } = useContext(SweepPinsContext);
  // The live antenna's metrics for the compare table, held WITH the solve
  // they describe: a re-solve must not keep showing the previous design's
  // numbers while the new ones are fetched (AK#1632).
  const [liveMetricsFor, setLiveMetricsFor] = useState<{
    result: SolveResponse;
    metrics: PatternMetrics | null;
  } | null>(null);
  // The stage's far-field captions, per cut (a grid can show both), handed up
  // by the charts so the overlay stacks can show them (see FarFieldCaptions).
  const [ffCaptions, setFfCaptions] = useState<
    Partial<Record<FarFieldCut, FarFieldCaptions>>
  >({});
  const onFarFieldCaptions = useCallback((c: FarFieldCaptions) => {
    setFfCaptions((prev) => ({ ...prev, [c.cut]: c }));
  }, []);
  // The whole pattern's maximum, fetched on demand (AK#1632): it needs a full
  // far-field solve, which the compare table already pays for while pins are
  // on screen and nothing else should pay for unasked. Held with the solve it
  // describes, so a later solve shows "find" again rather than a stale max.
  const [maxFetch, setMaxFetch] = useState<{
    result: SolveResponse;
    metrics: PatternMetrics | null;
    pending: boolean;
  } | null>(null);
  // The app never switches solvers on its own. When the current design+solver
  // combo is a poor match the solve is withheld and a warning is shown; these
  // handle its two buttons. (To change solver, the user uses the gear menu.)

  // "Solve anyway": approve this combo so re-solves don't re-warn, then solve.
  function solveAnyway() {
    approvedComboRef.current = true;
    setComboApproved(true);
    setSolverWarning(false);
    controlsRef.current = buildRequest();
    // Belt and braces: approving the COMBO does not approve a refusal. This
    // used to call `requestSolve()` unconditionally, so approving a soft
    // mismatch asked the solver for a combination momwire raises on.
    //
    // DELIBERATELY NOT COVERED BY A TEST, and that is worth stating rather
    // than hiding behind one. The button that calls this no longer renders
    // while a refusal stands (SolveOverlays excludes `optionRefusal`), so
    // there is no path through the UI that reaches here in that state —
    // mutating this line back to an unconditional `requestSolve()` leaves the
    // whole suite green. A test that cannot fail is not a test; this is a
    // second lock behind a first one that IS tested, and it earns its place
    // by being cheap rather than by being verified.
    if (!solveWithheld()) requestSolve();
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
  }, [linkedDesignFreq, linkMeas]);
  // Layout branch. Desktop never reads isMobile except as the sizing hooks'
  // reattach key, so no desktop viewport is affected; the key makes both
  // hooks re-measure if the window is resized across the breakpoint.
  const { isMobile, orientation } = useIsMobile();
  // Grid mode is desktop-only (the segmented control never renders on
  // mobile, so `setLayout("grid")` is never reachable there) — but `layout`
  // itself is a global persisted flag, so a phone can still load a value of
  // "grid" left over from a desktop session. Forcing "rail" here keeps the
  // mobile carousel's arrow-key cycling (pinned ∪ active, unit 2) exactly as
  // it was; nothing below the mobile branch ever sees "grid".
  const effectiveLayout = isMobile ? "rail" : layout;
  // Output view, camera and canvas display toggles (#642 seam 5b-3); the
  // grid-mode off-grid snap (unit 3) lives inside this hook too, since it
  // already owns `view` and now needs `layout`/`setLayout` alongside it.
  const {
    azElevDeg,
    setAzElevDeg,
    elevAzDeg,
    setElevAzDeg,
    view,
    setView,
    cameraProjection,
    setCameraProjection,
    // Renamed here: `orientation` in this component is the screen's
    // (portrait / landscape).
    orientation: antennaOrientation,
    setOrientation: setAntennaOrientation,
    snapToDesignView,
    canvasCamera,
    showHeatmap,
    setShowHeatmap,
    showEnvelope,
    setShowEnvelope,
    showWireLabels,
    setShowWireLabels,
    showFeedNames,
    setShowFeedNames,
  } = useViewState({
    currentExample,
    active,
    pinned: shownViews,
    layout: effectiveLayout,
    setLayout,
    overlays: {
      heatmap: uiDefaults.switches.heatmap_currents,
      envelope: uiDefaults.switches.current_waveforms,
      wireLabels: uiDefaults.switches.wire_labels,
      feedNames: uiDefaults.switches.feed_labels,
    },
    orientation: uiDefaults.orientation,
  });

  // "Save as my defaults" (AK#1492): the session's switches, ground and slots
  // as the startup settings file, then a one-line note saying where it went.
  // The settings-file problems the server reported show once, dismissibly.
  const [settingsProblemsDismissed, setSettingsProblemsDismissed] = useState(false);
  const [settingsNote, setSettingsNote] = useState<string | null>(null);
  async function saveDefaults() {
    const slot = (s: Slot) => ({
      backend: slots[s].backend.name,
      n_per_wire: slots[s].opts.nPerWire,
      model: modelOptionsForRequest(slots[s].backend, slots[s].opts, modelOptionSpecs),
    });
    const body: SettingsSaveBody = {
      switches: {
        live: autoSim,
        // The two switches the analysis chart's dwell switch replaced (unit
        // 3): no longer on screen, so what the file said passes through. A
        // chart's own switch is session-only and never written here.
        freq_sweep: uiDefaults.switches.freq_sweep,
        convergence_sweep: uiDefaults.switches.convergence_sweep,
        pattern_renorm: normCheckEnabled,
        refine: refineEnabled,
        heatmap_currents: showHeatmap,
        current_waveforms: showEnvelope,
        wire_labels: showWireLabels,
        feed_labels: showFeedNames,
      },
      antenna_view: { orientation: antennaOrientation },
      // Every ground slot, written as [grounds.X] (AK#1794).
      grounds: Object.fromEntries(
        groundSlots.map((g) => [
          g.id,
          {
            enabled: g.enabled,
            type: g.type,
            method: g.method,
            ...(g.soil ? { eps_r: g.soil.eps_r, sigma: g.soil.sigma } : {}),
            terrain_preset: g.terrainPreset,
          },
        ]),
      ),
      // Every solver slot, written as [slots.A] ...; one added this session
      // (D, E: AK#1801) is written even when it changes nothing.
      slots: Object.fromEntries(slotOrder(slots).map((s) => [s, slot(s)])),
      // Every kind, `map` included (not in the menu until the workbench
      // draws a map): the server writes only what differs from its defaults.
      workbench: { run_on_pick: runOnPick },
    };
    const outcome = await saveSettings(body);
    setSettingsNote(
      outcome.ok
        ? `Saved as your defaults: ${outcome.path ?? "settings.toml"}`
        : `Not saved: ${outcome.problems.join(" · ")}`,
    );
  }
  // The rail's slide and thumbstrip unmount in grid mode and mount fresh on
  // the way back, so the layout is part of the reattach key: without it the
  // observers stayed on the detached boxes, which measure 0, and every rail
  // chart came back at the 160 px floor after one trip to grid (AC6LA).
  const railKey = `${isMobile}:${effectiveLayout}`;
  const { ref: slideRef, size: chartSize } = useSlideSize(720, railKey);
  const thumbStripRef = useRef<HTMLDivElement>(null);
  // The rail is the pinned set minus whatever is on the stage; peeking an
  // unpinned view subtracts nothing, so the count the sizer needs varies.
  const rail = shownViews.filter((id) => id !== view).map((id) => VIEW_META[id]);
  const thumbSize = useThumbColumnSize(thumbStripRef, rail.length, 280, railKey);
  // Grid mode's displayed cells (unit 3): the first ≤4 pins, in pin order.
  // gridCells/gridShape are pure (useViewPrefs.ts) so this and useViewState's
  // internal cycling can never disagree about "what's on screen".
  const gridViewIds = gridCells(shownViews);
  const gridViews = gridViewIds.map((id) => VIEW_META[id]);
  const { rows: gridRows, cols: gridCols } = gridShape(gridViewIds.length);
  const { ref: gridRef, size: gridCellSize } = useGridCellSize(
    gridRows,
    gridCols,
    560,
    effectiveLayout,
  );
  // Maximize (glyph or double-click, Blender's cell↔full toggle): jump to
  // rail mode with this view primary. The segmented control's rail button
  // returns to grid.
  const maximizeView = (v: View) => {
    setView(v);
    setLayout("rail");
  };

  const {
    mobileIndex,
    mobileCarouselRef,
    mobRef,
    mobChartSize,
    mobPaneWidth,
    onMobileCarouselScroll,
    goToMobileScreen,
  } = useMobileCarousel({ isMobile, orientation, pinned: shownViews, view, setView });
  // The carousel's pages: the pinned views in pin order plus the trailing Info
  // screen. The dots row renders the SAME list, so a page can never exist
  // without a dot (or the reverse) — see MobileDots.
  const screens = useMemo(() => mobileScreens(shownViews), [shownViews]);
  // The pinned-pattern comparison table minimizes to a "{n} pinned" chip so
  // it can get off the chart — it grows a row per pin and swallows a phone
  // screen. Starts collapsed on mobile, expanded on desktop (the pre-existing
  // behavior); pinning always expands it so the new row is seen.
  const [compareCollapsed, setCompareCollapsed] = useState(isMobile);

  const previewAbortRef = useRef<AbortController | null>(null);
  // JSON of the request the currently-displayed preview wireframe was built
  // from. When Live is off no solve redraws the geometry, so the solve effect
  // refetches the preview itself on a param/variant/freq change — but only when
  // this signature actually changed, so it skips the redundant refetch right
  // after an antenna switch (whose preview the switch effect already built).
  const previewSigRef = useRef<string | null>(null);
  // Latest selected antenna, mirrored into a ref so the (mount-once) WebSocket
  // onmessage handler can drop responses for an antenna the user already
  // switched away from. Updated every render — cheap and always current.
  const geometryRef = useRef(geometry);
  // geometry mirrored for the mount-once WebSocket handler, which must drop
  // responses for an antenna the user has already switched away from (#768).
  // eslint-disable-next-line react-hooks/refs
  geometryRef.current = geometry;

  // Solve-lane session id (issue #382): one per workbench tab (A/B compare
  // tabs are separate App instances, hence separate sessions). The server
  // keys its single-lane scheduler on this — everything this tab asks for
  // runs one-at-a-time server-side, live solve first.
  //
  // useState's LAZY initializer, not useRef(makeSessionId()): a bare
  // useRef argument is evaluated on every render and discarded after the
  // first, so that spelling minted — and threw away — a fresh UUID on every
  // knob frame. The lazy form runs the impure call exactly once (issue #768).
  const [sessionId] = useState(() =>
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `s-${Math.random().toString(36).slice(2)}`,
  );

  // The session's solve request: the active solver slot's engine and the
  // active ground slot's ground (buildRequestFor).
  function buildRequest(): SolveRequest {
    return buildRequestFor(activeSlot, activeGroundSlot);
  }

  // An analysis chart curve's request (unit 4): its cell's slot and ground,
  // and its plane, design and family step (unit 4b), through
  // buildRequestFor, on the lane stream the curve runs on.
  function buildCellRequest(cell: ChartCellRequest): SolveRequest {
    const r = buildRequestFor(cell.slot as Slot, cell.ground, {
      ...(cell.plane !== undefined ? { plane: cell.plane } : {}),
      ...(cell.design !== undefined ? { design: cell.design } : {}),
      ...(cell.state !== undefined ? { state: cell.state } : {}),
      ...(cell.step !== undefined ? { step: cell.step } : {}),
    });
    return cell.stream ? { ...r, _stream: cell.stream } : r;
  }

  // A design cell's design as a fresh session loads it (unit 4b), which is
  // how `antennaknobs analyze` builds a design cell: at that design's own
  // defaults (the CLI's registry builder), whatever this session has done
  // to its knobs. Its first variant and its schema's defaults, as the
  // catalog seeds them (useDesignCatalog); its design and measurement
  // frequencies where a design switch snaps them (applyDesignResets, then
  // a knob linked to the design frequency). Null when this session's
  // catalog does not hold it. `variant` (a state on the loaded design, AK#1757
  // step 7) takes that variant's defaults instead, as knobDefaults does.
  function designAtDefaults(name: string, variant?: string) {
    const ex = examples.find((e) => e.name === name);
    if (!ex) return null;
    const values = seedDefaults(ex.param_schema);
    const vv = variant !== undefined ? ex.variant_values?.[variant] : undefined;
    if (vv) for (const k of Object.keys(values)) if (k in vv) values[k] = vv[k] as (typeof values)[string];
    const snap = snapForExample(ex);
    const linked = findLinkedDesignFreq(ex.param_schema, values);
    return {
      geometry: ex.name,
      variant: variant ?? ex.variants?.[0] ?? "default",
      values,
      designFreq: linked ?? snap?.freq ?? designFreq,
      measFreq: linked ?? snap?.measFreq ?? measFreq,
    };
  }

  // The solve request on solver slot `slotId`'s engine and ground slot
  // `groundId`'s ground, with everything else the session's: what an
  // analysis chart's curve for that cell sends (AK#1757 step 5 unit 4), and
  // for the active pair exactly the session's own request, so a cell on
  // (B, 2) is the request the session would send with B and 2 active. No
  // slot is touched.
  //
  // `over` is a chart cell's own (unit 4b): a measurement plane (the
  // natural one is the field's absence, as pickPlane makes it), a design
  // at its own defaults (designAtDefaults: its geometry, variant, knobs and
  // frequencies replace the session's, and the session's plane, Zo
  // override and tracker, which belong to the session's design, are left
  // out), and a family's knob set to its step value on top of the knobs.
  // A state (AK#1757 step 7) is a design at its defaults too, the loaded one
  // at its variant's when the state names no design, never at the live
  // knobs, so a state is the same curve every session; its knobs are set
  // over those defaults (a frequency knob through the request's own field).
  function buildRequestFor(
    slotId: Slot,
    groundId: string,
    over: {
      plane?: string;
      design?: string;
      state?: CellState;
      step?: { knob: string; value: number };
    } = {},
  ): SolveRequest {
    const design =
      over.design !== undefined
        ? designAtDefaults(over.design, over.state?.variant)
        : over.state !== undefined
          ? designAtDefaults(geometry, currentVariant)
          : null;
    const cfg = slots[slotId] ?? slots[activeSlot];
    const backend = cfg.backend;
    const g = groundRequestFor(groundId, backend);
    const groundModel = g.model;
    // ground_model is shared across backends (εr=10, σ=0.002 for the finite
    // models): PyNEC honours it directly; momwire's B-spline family solves
    // the finite models with its reflection-coefficient ground, while
    // Sinusoidal folds them to the PEC image solve (the server
    // ships the real εr/σ for the pattern either way).
    const groundActive = g.enabled && backendSupportsGround(backend);
    const base: SolveRequest = {
      _session: sessionId,
      geometry: design?.geometry ?? geometry,
      variant: design?.variant ?? currentVariant,
      solver: backend.kind === "momwire" ? "momwire" : backend.kind,
      n_per_wire: cfg.opts.nPerWire,
      design_freq_mhz: design?.designFreq ?? designFreq,
      measurement_freq_mhz: design?.measFreq ?? measFreq,
      wire_radius: cfg.opts.wireRadius,
      ground: groundActive,
      // ground_fast is the legacy boolean; ground_model is authoritative
      // server-side when present. Send both so either server version agrees.
      ground_fast: groundActive && groundModel === "fast",
      ground_model: groundModel,
      // Cut angles ride along so each solve response arrives with its polar
      // traces attached (server-side, issue #547). Deliberately NOT solve-
      // effect deps: angle drags refresh traces via POST /cuts instead of
      // re-solving; the next real solve just bakes in the current angles.
      az_elev_deg: azElevDeg,
      elev_az_deg: elevAzDeg,
    };
    if (base.ground_model === "terrain") {
      base.terrain = { preset: g.terrainPreset, ...g.terrainParams };
    }
    // Soil constants (#1173). The slot's soil is already undefined for pec /
    // terrain and for a default soil, so a request that carries no soil is
    // byte-identical to a pre-#1173 one.
    if (g.soil) {
      base.soil = g.soil;
    }
    if (backend.kind === "momwire") {
      base.momwire_model = backend.name;
      const opts = modelOptionsForRequest(
        backend,
        cfg.opts,
        modelOptionSpecs,
        designConstraintInputs,
      );
      // Enrichment now solves over ground (momwire #167: PEC image reaction,
      // refl-coef, and Sommerfeld), so this is no longer an error guard — it is
      // a UX choice. Enrichment is a validation-only knob that is redundant for
      // the d=2 basis (issue #565), so we keep it off when ground is active
      // rather than surface a control that can only match or worsen the grounded
      // production solve; the gear shows the validation note.
      if (groundActive && "use_singular_enrichment" in opts) {
        opts.use_singular_enrichment = false;
      }
      base.model_options = opts;
    } else {
      // An engine that exposes kwargs (the NEC-4.2 slot's Sommerfeld card)
      // carries them the same way; one that exposes none sends no field, so
      // PyNEC, NEC-2 and NEC-5 requests are unchanged.
      const opts = modelOptionsForRequest(backend, cfg.opts, modelOptionSpecs);
      if (Object.keys(opts).length > 0) base.model_options = opts;
    }
    // Measurement plane (issue #652 c): only ever sent when picked — the
    // natural plane is the absence of the field, so designs with no
    // network never see it.
    // A plane cell's plane (unit 4b) the same way: the natural plane, as
    // pickPlane leaves it, is the field's absence.
    const cellPlane =
      over.plane !== undefined
        ? over.plane === (design ? undefined : result?.planes?.[0])
          ? null
          : over.plane
        : design
          ? null
          : plane;
    if (cellPlane) base.plane = cellPlane;
    // Schema-driven antennas (all of them now): merge the active
    // paramValues straight in. For fan_dipole this includes a nested
    // `bands: [{band_id, freq, length_factor}, ...]` array; the backend
    // unpacks it in _bands_from_request().
    Object.assign(base, design?.values ?? currentValues);
    // A state cell's knobs, over its design's defaults. The request carries
    // the measurement and design frequencies in fields of their own, which
    // the server sets over the knobs, so a state setting one sets that too.
    if (over.state) {
      for (const [k, v] of Object.entries(over.state.knobs)) {
        (base as Record<string, unknown>)[k] = v;
        if (k === "freq" && typeof v === "number") base.measurement_freq_mhz = v;
        if (k === "design_freq" && typeof v === "number") base.design_freq_mhz = v;
      }
    }
    // A family cell's step (unit 4b): its knob at its value. A family over
    // the measurement frequency (AK#1935) sets the request's own field too,
    // which the server reads the measurement frequency from, as a state's
    // `freq` does above.
    if (over.step) {
      (base as Record<string, unknown>)[over.step.knob] = over.step.value;
      if (over.step.knob === FAMILY_FREQ) base.measurement_freq_mhz = over.step.value;
    }
    // hexbeam_5band's daisy_chain (single common feed) is now modelled with
    // build_network(), which the shared NetworkReducer solves on momwire and
    // PyNEC alike — so it is no longer greyed out or forced off on momwire.
    // #1220: when the mode is on and the user has moved a knob the tracker is
    // NOT holding, ask the server to hold the target across this tick. Absent
    // otherwise, so an ordinary solve stays an ordinary solve — which is also
    // what invalidates the tracker's tangent server-side.
    // AK#1735: only an override travels — no override is the same bytes as
    // before, and the server answers with the design's own.
    if (zoOverride !== null && !design) base.z0_ohms = zoOverride;
    if (trackOn && trackDragRef.current && !design) {
      (base as SolveRequest & { _track?: unknown })._track = {
        objective: optObjective,
        free: trackFree,
        drag: trackDragRef.current,
        epoch: trackEpochRef.current,
      };
    }
    return base;
  }

  // Reactive knob optimiser (#642 seam 5b-3). Called here, at the fixed-input
  // signature's old position, so the cluster's three trailing effects keep
  // their global order; the design-load reset rides along with them.
  const {
    optEnabled,
    setOptEnabled,
    optObjective,
    optSeed,
    setOptSeed,
    optBands,
    setOptBands,
    optMeanWeight,
    setOptMeanWeight,
    optForm,
    setOptBandForm,
    setOptObjective,
    knobOpt,
    setKnobOpt,
    knobMenu,
    setKnobMenu,
    optRunning,
    optResult,
    optProgress,
    optFrameMs,
    optError,
    optPausedBy,
    setOptPausedBy,
    optAbortRef,
    optEnabledRef,
    knobOptFor,
    updateKnobOpt,
    optMarked,
    optRestarted,
    optBandMarks,
    optPaceMs,
    optMenuOpen,
    optMenuPaused,
    setOptMenuOpen,
  } = useOptimizer({
    geometry,
    currentValues,
    currentValuesKey,
    currentSchema,
    backend: backend.name,
    designFreq,
    measFreq,
    autoSim,
    active,
    buildRequest,
    // The optimiser's write-back of a group leaf (AK#1901) must not move the
    // dial the way a hand on that band's knob does: the dial is one of the
    // run's inputs, so moving it would re-tune at another frequency. A flat
    // knob's write-back follows exactly as before.
    setParamAtPath: (path, value) => setParamAtPath(path, value, path.length === 1),
    zoOverride,
  });

  // The tab's variant defaults: what a state, a pin's changed knobs and a
  // kept run's start are set over.
  const knobDefaults = (): Record<string, unknown> => {
    if (!currentExample) return {};
    const base: Record<string, unknown> = seedDefaults(currentExample.param_schema);
    const vv = currentExample.variant_values?.[currentVariant];
    if (vv) for (const k of Object.keys(base)) if (k in vv) base[k] = vv[k];
    return base;
  };

  // A kept band run (AK#1906, lib/keptRun.ts): the one the tab jumped to,
  // shown in the band readout until a run answers (`seen`: the result on
  // screen when it jumped). It belongs to the tab it was picked on.
  const [keptAt, setKeptAt] = useState<{
    geometry: string;
    name: string;
    run: KeptRun;
    seen: OptimizeResult | null;
  } | null>(null);
  const kept = keptAt && keptAt.geometry === geometry ? keptAt : null;
  // Jump to a kept run: the tab's knobs at its stored answer (or, `start`,
  // where it began), its knobs marked over its ranges and every other mark
  // cleared, and its bands, balance and form (mode, and each band's
  // objective, feed and Z0: #1921) set, so a run is the run it kept.
  // A jump to the answer stops Optimize, which would re-tune it at once; a
  // run from the start turns it on, which is the run.
  function jumpToKept(name: string, run: KeptRun, at: "result" | "start") {
    optAbortRef.current?.abort();
    const bag = keptValues(knobDefaults() as ParamValueBag, run, at);
    setParamValues((prev) => ({ ...prev, [geometry]: bag }));
    setKnobOpt((prev) => ({ ...prev, [geometry]: keptMarks(run, currentSchema) }));
    setOptBands(run.bands.map((b) => b.freq));
    setOptMeanWeight(run.meanWeight);
    setOptBandForm(keptForm(run));
    setKeptAt({ geometry, name, run, seen: optResult });
    setOptEnabled(at === "start");
  }
  // The band readout's part (VfoPanel): the kept run's stored table, and
  // Keep on a fresh band result.
  const keptShown = kept && optResult === kept.seen ? kept : null;
  const freeNow = Object.entries(knobOpt[geometry] ?? {})
    .filter(([, o]) => o.vary)
    .map(([name, o]) => ({ name, min: o.optMin, max: o.optMax }));
  const keptReadout: KeptReadout = {
    shown: keptShown ? { name: keptShown.name, result: keptAsResult(keptShown.run) } : null,
    onRun: keptShown ? () => jumpToKept(keptShown.name, keptShown.run, "start") : null,
    onKeep:
      optResult?.objective === "bands" && optBands && freeNow.length > 0
        ? () =>
            setKeeping({
              title: "Keep band run as study",
              body: {
                origin: "optimize",
                form: "study",
                tab: keepRequest(buildRequest()),
                free: freeNow,
                // A run in a kept form keeps that form (#1921).
                bands: optForm ? optForm.bands : optBands.map((freq) => ({ freq })),
                ...(optForm ? { mode: optForm.mode } : {}),
                mean_weight: optMeanWeight,
                result: optResult,
              },
              initialName: `${geometry} across ${optBands.map((f) => fmtFreq(f)).join("/")} MHz`,
            })
        : null,
  };

  // #1007: the engine-timing fields froze for the whole of an optimiser run,
  // because `rttMs` belongs to the /ws channel and the run POSTs /optimize with
  // its own fetch. While a run is in flight these come off the progress frames
  // instead; `null` outside a run puts the readout straight back on the /ws
  // numbers with no second code path.
  // The run's live Z for the charts. A band run's worst band can be one the
  // engine could not read, which the server sends as null (AK#1901): no point
  // to draw, rather than a NaN one.
  const optLiveZ =
    optRunning &&
    optProgress &&
    optProgress.metrics.z_in_re != null &&
    optProgress.metrics.z_in_im != null
      ? optProgress.metrics
      : null;
  const liveSolve = optRunning && optProgress
    ? {
        solveMs: optProgress.solve_ms ?? null,
        intervalMs: optFrameMs,
        nSolves: optProgress.n_solves ?? null,
      }
    : null;

  // --- #1220: "keep the target while I drag" -------------------------------
  // The tracker moves the OPTIMIZE-MARKED knobs to hold the objective while the
  // user drags some other knob. It is a root problem, not a minimisation, so it
  // refuses rather than guesses when the marks do not suit it.
  // Plain expressions, not useMemo: this is a handful of knobs per render, and
  // the React compiler cannot preserve a useMemo across these reads anyway.
  const trackFree = Object.entries(knobOpt[geometry] ?? {})
    .filter(([, o]) => o.vary)
    .map(([name, o]) => ({ name, min: o.optMin, max: o.optMax }));
  // The same rule the server enforces, so the switch never offers something
  // that would be refused on arrival. The message carries the COUNT: "it did
  // nothing" is the failure this exists to avoid.
  const trackRefusal = ((): string | null => {
    if (optObjective === "swr")
      return "SWR is a best compromise, not a target to hold";
    const want = optObjective === "resonance" ? 1 : 2;
    const n = trackFree.length;
    if (n !== want)
      return `needs exactly ${want} optimise-marked knob${want === 1 ? "" : "s"}; ${n} marked`;
    return null;
  })();
  // A mode that has become impossible is simply not ON — DERIVED, never synced.
  // Storing it and correcting it in an effect would be a setState in an effect,
  // and one cascading render, to represent what the render already knows.
  const trackOn = trackEnabled && !trackRefusal;
  // Same for the status: the tracker's state IS the last response's, so
  // mirroring it into React state could only ever disagree with it.
  const trackStatus =
    (result as { _track?: TrackStatus } | null)?._track ?? null;
  const trackLatched =
    trackOn && trackStatus?.status === "latched"
      ? (trackStatus.message ?? null)
      : null;


  // The feed-network schematic (issue #652): fifth view in the carousel.
  // Keyed on what can change the drawing — knobs, variant, freqs — not on
  // solver/backend state: the network is the design's, not the solver's.
  // The one piece of solver output that DOES ride along is the power budget,
  // echoed as structural (key, watts) rows so each block draws its burn.
  // Gated on the result being THIS design's: two station designs share
  // instance paths ("sta."), so a stale budget from the previous design
  // would annotate the new chain with the old antenna's watts.
  const schematicBudget = useMemo(
    () =>
      result?.geometry === geometry && result.power_budget
        ? result.power_budget
            .filter((b) => b.key !== undefined)
            .map((b) => [b.key as string, b.watts] as [string, number])
        : null,
    [result, geometry],
  );
  // View residency (issue #715): an analysis only runs while some view that
  // RENDERS it can be on screen — pinned (rail thumbs / grid cells / mobile
  // carousel pages are all mounted from `pinned`) or the active view (which
  // covers a picker peek at an unpinned view). Derived HERE, in the one
  // component that already owns both the layout state and the analysis
  // cluster, and handed down as plain booleans so useAnalysisRunners stays
  // layout-agnostic. The norm check is deliberately NOT residency-gated:
  // its consumer is the HUD readout, resident in every layout. Consumer
  // census + semantics: docs/plan-view-residency-gating.md.
  const isResident = (v: View) => shownViews.includes(v) || view === v;
  // An analysis chart's view (the zparam id and its duplicates', AK#1757
  // step 5): the one view either sweep draws in since unit 3 folded the
  // Smith / VSWR / S11 views into it. Which of its views is on screen (and
  // so which projection refinement plans against, issue #744) is the
  // chart's own (chartRunInputs, in deriveChart).
  const patternResident = isResident("azimuth") || isResident("elevation");

  const { schematicSvg, schematicUnavailable } = useSchematic({
    // Composed at the call site (the hook has a single gate): fetch the
    // schematic only while the workbench tab is active AND the schematic
    // view is somewhere on screen (issue #715).
    active: active && isResident("schematic"),
    geometry,
    requestKey: JSON.stringify([
      currentValuesKey,
      currentVariant,
      designFreq,
      measFreq,
      plane, // the picked plane draws as a marker + dimmed upstream
    ]),
    buildRequest,
    budget: schematicBudget,
    inputPowerW: result?.input_power_w ?? null,
  });


  // The design's band table plus the session's custom bands (#1487). A design
  // that suppresses the band row (bands === []) stays suppressed.
  const currentBands: BandSpec[] = useMemo(() => {
    const own = currentExample?.bands ?? [];
    if (own.length === 0) return own;
    const extra = customBands.filter((c) => !own.some((b) => b.key === c.key));
    return extra.length ? [...own, ...extra] : own;
  }, [currentExample, customBands]);

  // Anchor for the measurement-freq VFO window: the snap-freq of the *selected*
  // measurement band (`measBand`), falling back to designFreq before one is
  // chosen. Anchoring on the selected band — not on bandContaining(measFreq) —
  // keeps the window stable as the dial roams measFreq within (or a touch
  // outside) a narrow ham band; deriving it from measFreq would collapse the
  // window back to the design band the instant measFreq left the band edge.
  const measBandAnchor =
    currentBands.find((b) => b.key === measBand)?.freq_mhz ?? designFreq;

  // Ceiling for anchor-derived frequency windows (the unlocked meas-freq
  // VFO and un-band-locked sweeps). Historically a hardcoded 60 MHz — an
  // HF-era bound that survived the 2m/70cm band additions (#497) and
  // then INVERTED the VFO range on VHF designs (anchor 146: min 116.8 >
  // max 60, so touching the knob clamped it to 60 MHz). Derive it from
  // the design's own band table instead, keeping 60 as the floor so
  // bandless/HF-only designs behave exactly as before.
  const freqWindowCeiling = freqWindowCeilingFor(currentBands);

  // The ONE range (AK#1682): resolved once, here, and handed as the same
  // object to the measurement dial (its travel) and to the sweep runner (its
  // span and grid). lib/sweep.ts has the precedence.
  const measBandIsCustom = !measLocked && isCustomBand(measBand);
  const sweepRangeInputs: SweepRangeInputs = {
    currentExample,
    currentVariant,
    measLocked,
    measFreq,
    designFreq,
    currentBands,
    freqWindowCeiling,
    measBandAnchor,
    measBandIsCustom,
    sweepRangeEdit,
  };
  const resolvedSweepRange = resolveSweepRange(sweepRangeInputs);
  // A menu edit or "↺ design range" (AK#1682). The dial cannot show a
  // measurement frequency outside its travel — the needle pins at the end
  // stop while the LCD, the solve and the pattern sit somewhere the dial can
  // no longer reach — so an unlocked measFreq is clamped into the new range.
  // A LOCKED one is left alone: the lock ties it to the design frequency,
  // and an edited sweep range is not a reason to measure elsewhere.
  function applySweepRangeEdit(next: SweepRange | null) {
    setSweepRangeEdit(next);
    if (measLocked) return;
    const r = next ?? designSweepRange(sweepRangeInputs).range;
    setMeasFreq((f) => Math.min(r.hi, Math.max(r.lo, f)));
  }
  // Close the range menu on Escape, as the knob menu closes.
  useEffect(() => {
    if (!sweepMenu || !active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSweepMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sweepMenu, active]);

  // The design-load resets below run DURING RENDER, keyed on the design
  // (currentExample's identity: a switch, or a reload's refreshed catalog),
  // not in effects (AK#1762). An effect runs a Scheduler task after the
  // commit that shows the new design, and the first interaction landing in
  // that gap was overwritten by the late reset — reproduced for the ground
  // switch and the camera pick (a click there was lost every time). Adjusting
  // state during render, React's pattern for state derived from a changing
  // input, puts each reset in the same render as the design it belongs to.
  // `null` = never applied, so a session that mounts on a known design still
  // gets them on its first render, as the effects did on mount.
  const [designResetFor, setDesignResetFor] = useState<ExampleDescriptor | undefined | null>(
    null,
  );
  if (designResetFor !== currentExample) {
    setDesignResetFor(currentExample);
    if (currentExample) applyDesignResets(currentExample);
  }

  function applyDesignResets(ex: ExampleDescriptor) {
    // When the active example changes (or first loads), snap band /
    // designFreq / measFreq to the band whose [min, max] window contains
    // the design's native freq (from the schema's freq ParamSpec). If
    // there's no freq param or it falls outside every band, fall back
    // to the first band so the snap is still well-defined. Skipped
    // entirely for examples that suppress the row (bands === []) —
    // those own their design freq via their own schema controls.
    //
    // A new design starts on its own sweep range (AK#1682): the last
    // design's edit is in the wrong place for this one.
    setSweepRangeEdit(null);
    snapBand: {
      if (currentBands.length === 0) {
        if (band !== "") setBand("");
        break snapBand;
      }
      // Always re-snap on geometry switch — every HF example shares the
      // DEFAULT_AMATEUR_BANDS list, so a sticky band key (e.g. "10m" from the
      // previous 28 MHz design) would otherwise survive a switch into a
      // 14 MHz design and keep the slider parked on the wrong band.
      // (The containing-band / native-freq logic lives in snapForExample,
      // shared with the antenna-switch preview fetch — see there.)
      const snap = snapForExample(ex)!;
      setBand(snap.bandKey);
      setDesignFreq(snap.freq);
      // Off-band designs open with the measurement dial deliberately away
      // from the design freq (that's the design's premise), so the
      // follow-design lock must disengage or it would immediately drag the
      // dial back.
      if (snap.offBand) {
        setLinkMeas(false);
        setMeasFreq(snap.measFreq);
        setMeasBand(snap.measBandKey);
      } else if (linkMeas || !ex.has_design_freq) {
        // Re-anchor the dial too: always when locked, and also for
        // fixed-geometry designs — their lock is inert (see measLockable),
        // so a measFreq left over from the previous design would strand the
        // measurement outside this design's window entirely.
        setMeasFreq(snap.measFreq);
        setMeasBand(snap.measBandKey);
      }
    }

    // The design's own ground goes in ground slot X (AK#1794), which becomes
    // the active slot; see withDesignGround for a design without one.
    //
    // Ground-requirement seed: the buried-wire designs declare
    // ground_requirement="sommerfeld" (conductors below z=0 only exist under
    // a Sommerfeld half-space — the refl-coef method refuses them by name),
    // so seed finite + Sommerfeld on selection instead of letting the first
    // solve hit the refusal wall. The user can still flip anything
    // afterwards, and the solver's by-name refusal remains the enforcement.
    // GroundPanel shows the one-line notice whenever the requirement is
    // present.
    //
    // Ground SEED (AK#1432): a file design's deck says what ground it models
    // (GE 0 = free space, GE 1 / GN 1 = perfect, GN 0 / GN 2 = finite with
    // the card's medium, a NEC-5 bare GD = MININEC-type, AK#1655), so the
    // switch starts where the deck is instead of at the app's default finite
    // ground — which had NEC-5 refusing a free-space dipole at z = 0 until
    // the user unticked ground by hand. Same contract as the requirement seed
    // above: on the design switch only, and the user can change anything
    // afterwards.
    applyDesignGround(designGround(ex));
  }

  function selectBand(nextKey: string) {
    const nb = currentBands.find((b) => b.key === nextKey);
    if (!nb) return;
    applyDesignBand(nb);
  }

  // A custom band (#1487) is built here and applied in the same click, before
  // the state update that lists it lands. The session keeps the four most
  // recent, so either picker can return to one.
  function addCustomBand(centerMhz: number, spanMhz: number): BandSpec {
    const nb = customBandSpec(centerMhz, spanMhz);
    setCustomBands((prev) =>
      [...prev.filter((b) => b.key !== nb.key), nb].slice(-4),
    );
    return nb;
  }
  function selectCustomDesignBand(centerMhz: number, spanMhz: number) {
    const nb = addCustomBand(centerMhz, spanMhz);
    applyDesignBand(nb);
    // The measurement comes along (#1487): the dial re-locks to the design
    // frequency, so a design moved to 300 MHz is measured at 300 MHz rather
    // than wherever an unlocked dial was left. Unlocking again works as usual.
    setLinkMeas(true);
    setMeasFreq(nb.freq_mhz);
    setMeasBand(nb.key);
  }

  function applyDesignBand(nb: BandSpec) {
    // Picking a band sets the range, as it sets the dial (AK#1682).
    setSweepRangeEdit(null);
    setBand(nb.key);
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
    applyMeasBand(nb);
  }
  function selectCustomMeasBand(centerMhz: number, spanMhz: number) {
    applyMeasBand(addCustomBand(centerMhz, spanMhz));
  }
  function applyMeasBand(nb: BandSpec) {
    // Only a *live* lock needs breaking; an inert one (fixed-geometry
    // design) is the user's global preference — leave it for the next
    // design_freq-scaled design.
    if (measLocked) setLinkMeas(false);
    setMeasBand(nb.key);
    setMeasFreq(nb.freq_mhz);
    // Picking a band sets the range, as it sets the dial (AK#1682).
    setSweepRangeEdit(null);
  }

  // Which band (if any) currently contains the measurement freq — drives
  // the active-tab highlight on the meas-band selector. Falls outside any
  // band → no tab highlighted.
  function bandContaining(f: number): string | null {
    return bandContainingIn(currentBands, f);
  }

  // The latest control values, used to send a new request when the prior one
  // completes (drops intermediate values rather than queuing them all up).
  //
  // Starts null rather than seeded with buildRequest(): a useRef argument is
  // evaluated every render and discarded after the first, so seeding it here
  // rebuilt a whole 59-line SolveRequest per knob frame to throw it away
  // (issue #768). Null means "nothing decided to solve yet" — every writer
  // (the solve effect, solveAnyway) fills it before asking to send, and
  // useSolveChannel defers a send it cannot fill, exactly as it already
  // defers one it cannot deliver down a closed socket.
  const controlsRef = useRef<SolveRequest | null>(null);
  // Mirrors "a solve is currently refused", for the channel to check at SEND
  // time. Kept as a ref because the channel's senders are per-socket closures
  // and a value would be whichever render created them.
  const withheldRef = useRef(false);

  // The /ws solve channel (#642 seam 5b-3): the socket, the latest-wins `_seq`
  // protocol and the busy-chrome dwell. Called right after controlsRef — the
  // channel reads that ref on every send, and the solve effect below reaches
  // for requestSolve.
  const {
    status,
    rttMs,
    solving,
    showBusy,
    stale,
    waiting,
    requestSolve,
    cancelSolve,
    seqRef,
  } = useSolveChannel({
    active,
    controlsRef,
    withheldRef,
    geometryRef,
    previewSigRef,
    setResult: applyResult,
    setSolveError,
  });

  // --- Pattern compare (pin / ghost overlay) --------------------------------
  // Pin the current pattern: snapshot the solve response (for the ghost trace)
  // into the shared cross-session pin list. The snapshot is frozen — it won't
  // change as the live knobs move, which is the whole point of comparing.
  // Measurement-plane pick (issue #652 c). Choosing the natural (first)
  // plane clears the override entirely, so the request field disappears
  // rather than pinning the default by name.
  function pickPlane(p: string) {
    setPlane(p === result?.planes?.[0] ? null : p);
  }

  // "Keep as study" for the shown pinned patterns (AK#1757 step 7 unit 4):
  // each the request its pattern was solved with (lib/keep.ts).
  const patternKeep = patternPinsKeep(pinnedPatterns, CURVE_CAP);
  const keepPatternPinsBlocked = patternKeep.blocked;
  const keepPatternPins = () =>
    setKeeping({
      title: "Keep pinned patterns as study",
      body: { origin: "pattern pins", form: "study", pins: patternKeep.pins },
      initialName: "pinned patterns",
    });

  function pinCurrentPattern() {
    // A result exists only because a solve was sent, which fills controlsRef —
    // so the second test never fires in practice. It is here because the pin
    // stores the request that PRODUCED this result; pinning a result against
    // a missing request would silently mislabel the ghost trace (issue #768).
    const controls = controlsRef.current;
    if (!result || !controls) return;
    const label = `${currentExample?.label ?? geometry} @ ${measFreq.toFixed(2)} MHz`;
    addPin(label, result, controls);
  }

  // Keep the live antenna's metrics fresh for the table, but only while a
  // comparison is actually on screen (≥1 pin and a pattern view) — the metrics
  // need a full far-field solve, so don't pay for it otherwise. Debounced so it
  // doesn't fire on every knob tick.
  const pinCount = pinnedPatterns.length;
  const comparing =
    pinCount > 0 &&
    (view === "azimuth" || view === "elevation" || view === "combined");
  useEffect(() => {
    if (!comparing || !result || !active) {
      // Derived state cleared when its inputs change — the reset IS the
      // effect's purpose, not a sync that could be computed during render
      // (#768).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLiveMetricsFor(null);
      return;
    }
    // A solve in flight means the knobs already describe a design `result`
    // does not: wait for it, or the metrics would be filed under the wrong
    // solve. Its arrival re-runs this effect.
    if (stale) return;
    // The same, after a CANCELLED solve (AK#1712): `stale` clears at the
    // cancel, but the knobs still describe the design the user just stopped,
    // not `result`. Fetching here would restart that very solve on the server
    // 300 ms after the cancel. A result older than the channel's generation
    // is exactly that case; the next solve's arrival re-runs this effect.
    if (typeof result._seq === "number" && result._seq < seqRef.current) return;
    const r = result;
    let cancelled = false;
    // Aborted on cleanup, not just ignored (AK#1712): the fetch is a full
    // server-side solve, and a result that moved on must stop it rather than
    // leave it grinding. The generation lets the lane supersede it too.
    const controller = new AbortController();
    const h = window.setTimeout(() => {
      // Read at fire time, not at schedule time: the dwell is 300 ms and the
      // metrics must describe the design as it now stands. Null only before
      // the first solve, which `result` above already excludes (issue #768).
      const controls = controlsRef.current;
      if (!controls) return;
      fetchMetrics(controls, {
        gen: seqRef.current,
        signal: controller.signal,
      }).then((m) => {
        if (!cancelled) setLiveMetricsFor({ result: r, metrics: m });
      });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(h);
      controller.abort();
    };
    // result identity changes per solve; that's the cue to refresh. seqRef is
    // the channel's stable ref (read at run time, never a trigger).
  }, [comparing, result, active, stale, seqRef]);
  // Only ever the CURRENT solve's metrics: null (the table's "…") while the
  // new ones are on their way.
  const liveMetrics =
    liveMetricsFor?.result === result ? liveMetricsFor.metrics : null;

  // The 3-D maximum for the peak readout (AK#1632): the compare table's
  // metrics when pins are up, else the on-demand fetch for THIS solve. Each is
  // tied to the solve it describes, so neither can show a previous design's
  // maximum. The × dismisses it until "find 3-D max" is clicked again, across
  // re-solves too, so pins do not bring it back uninvited.
  const [maxDismissed, setMaxDismissed] = useState(false);
  const ownMax = maxFetch?.result === result ? maxFetch.metrics : null;
  const maxMetrics = maxDismissed ? null : (liveMetrics ?? ownMax);
  const maxPending =
    !maxDismissed &&
    !maxMetrics &&
    ((comparing && liveMetricsFor?.result !== result) ||
      !!(maxFetch?.result === result && maxFetch.pending));
  function findMax() {
    setMaxDismissed(false);
    // Already in hand (dismissed, or fetched by the pin table): just show it.
    // With pins up the table's fetch is on its way; don't pay twice.
    if (liveMetrics || ownMax || comparing) return;
    const controls = controlsRef.current;
    const r = result;
    // Not while a solve is in flight: the knobs would describe a design the
    // on-screen `result` does not, and the answer would be filed under it.
    if (!controls || !r || stale) return;
    setMaxFetch({ result: r, metrics: null, pending: true });
    // The live design: a newer solve supersedes it on the lane (AK#1712).
    fetchMetrics(controls, { gen: seqRef.current }).then((m) => {
      setMaxFetch((prev) =>
        prev?.result === r ? { result: r, metrics: m, pending: false } : prev,
      );
    });
  }
  // The live design's 3-D maximum for a family's "at peak" cut (AK#1950):
  // the one in hand (the compare table's, or "find 3-D max"'s, for THIS
  // solve), else /pattern_metrics on the design as the knobs now set it,
  // the fetch "find 3-D max" makes. Not filed as that readout's, so the
  // stage does not grow a readout nobody asked for. Null before a solve,
  // or while one is in flight (the knobs would describe another design).
  const peakNow = (): Promise<PatternMetrics | null> => {
    const inHand = liveMetrics ?? ownMax;
    if (inHand) return Promise.resolve(inHand);
    const controls = controlsRef.current;
    if (!controls || !result || stale) return Promise.resolve(null);
    return fetchMetrics(controls, { gen: seqRef.current });
  };
  const peakBlocked = !result
    ? "Solve the design first: the peak is the live design's"
    : stale
      ? "The design is solving: its peak is the new solve's"
      : null;

  // Aim both cuts through the maximum: the elevation cut at its bearing, the
  // azimuth cut at its elevation (the knob's own 0-89° range).
  function aimAtMax(m: PatternMetrics) {
    setElevAzDeg(Math.round(m.azimuth_deg) % 360);
    setAzElevDeg(Math.min(89, Math.max(0, Math.round(m.takeoff_deg))));
  }

  // Reset the "solve anyway" approval whenever the design or solver changes, so
  // an inappropriate combo is re-evaluated (and re-warned) rather than riding a
  // stale approval. Defined before the solve effect so it runs first.
  useEffect(() => {
    approvedComboRef.current = false;
    // Derived state cleared when its inputs change — the reset IS the effect's
    // purpose, not a sync that could be computed during render (#768).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setComboApproved(false);
  }, [geometry, backend, backendOptsKey]);

  useEffect(() => {
    if (!active) return;
    // Hold the first solve after an antenna switch until that antenna's preview
    // has landed (previewReady === geometry). Param/freq tweaks on the *same*
    // antenna keep solving freely — previewReady stays equal to geometry until
    // the next switch resets it to null.
    if (previewReady !== geometry) return;
    // The readiness signal (sessionReady, AK#1762): this run decides what the
    // released design does first (solve, withhold behind a gate, or warn),
    // and every branch below sets its state in this same effect, so the
    // render that publishes data-ready also shows that decision. Unchanged
    // on later runs (a knob change), so React skips the update.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadSettledFor(`${geometry}#${previewNonce}`);
    // Writing the latest request into controlsRef is this effect's whole job;
    // the channel reads it on send (#768).
    // eslint-disable-next-line react-hooks/immutability
    controlsRef.current = buildRequest();
    // Paused: keep controlsRef fresh (so resuming sends the latest design) but
    // don't solve, and suppress the combo warning — nothing is running to warn
    // about. Toggling Live back on re-runs this effect (autoSim is a dep) and
    // solves the current state.
    if (!autoSim) {
      // Derived state cleared when its inputs change — the reset IS the
      // effect's purpose, not a sync that could be computed during render
      // (#768).
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
        apiFetch("/geometry", {
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
    // Hard gate first: the active backend cannot run this design at all
    // (e.g. junction-port designs on anything but B-spline — the solver
    // raises). Same withhold UI, but the banner offers "switch", never
    // "solve anyway". The app still never switches the solver itself.
    if (backendDisallowed) {
      withhold();
      return;
    }
    // The design-dependent OPTION refusal (#1006 G2-5). Same withhold UI as
    // the hard gate above and for the same reason — momwire raises on the
    // combination — but the banner names the option rather than offering a
    // solver switch, because the solver is not the problem here.
    //
    // Not in the dep list, on the same grounds as `backendDisallowed`: it
    // derives from `backend`, the slot's options and `currentExample`, and
    // `backend`, `backendOptsKey` and `geometry` are all already deps. Adding
    // the object itself would re-run this effect every render, since it is
    // rebuilt each time.
    if (optionRefusal !== null) {
      withhold();
      return;
    }
    // The ground refusal (AK#1856): the same withhold, and the banner offers
    // the ground slot that solves rather than an override. Its inputs,
    // `backend` and the active slot's ground model, are deps already.
    if (pairRefusal !== null) {
      withhold();
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
    withheldRef.current = false;
    setSolverWarning(false);
    // #1220: the tracker's write-back moved `currentValuesKey`, and the
    // response that carried it IS this tick's display solve — re-solving here
    // would be a second solve per drag tick, doubling a per-tick cost the
    // #1202 study priced at ~0.05 extra solves.
    //
    // Keyed on the ANSWERED key rather than a skip-one-run flag, deliberately:
    // a flag assumes this effect fires on the write-back, and if it ever did
    // not it would swallow the next LEGITIMATE solve instead — a worse bug,
    // invisible in the same way. Any user change moves the key away from the
    // answered one, so this can only ever suppress the echo.
    if (currentValuesKey === answeredKeyRef.current) return;
    requestSolve();
    // backendDisallowed/recommendedBackend derive from currentExample/preview/
    // roster, not listed directly — geometry (which tracks currentExample) and
    // previewReady (which tracks preview) are already deps, so those inputs
    // are covered without duplicating them here; roster only changes once per
    // session. buildRequest/requestSolve are plain closures over this same
    // render's state, not memoized — calling them just reads whatever this
    // effect's own already-listed deps last set, so they add nothing as deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    active,
    autoSim,
    geometry, previewReady, backend, backendOptsKey,
    // A reload's release (AK#1762): its null → geometry flip can batch into
    // one render when the preview answers at once, leaving previewReady
    // unchanged; the generation is what says a new release happened.
    previewNonce,
    currentValuesKey,
    designFreq, measFreq, plane,
    groundEnabled, groundModel, terrainKey, soilKey,
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
    // Derived state cleared when its inputs change — the reset IS the effect's
    // purpose, not a sync that could be computed during render (#768).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setResult(null);
    setPreview(null);
    setSolveError(null);
    setPlane(null); // plane names belong to a design; never carry one over
    setPreviewReady(null); // close the solve gate until this antenna's preview lands
    setSolverWarning(false); // drop any combo warning from the prior design
    previewAbortRef.current?.abort();
    const controller = new AbortController();
    previewAbortRef.current = controller;
    // Capture the geometry this run is for, so the gate is released for the
    // right antenna even if `geometry` changed by the time the fetch resolves.
    const forGeometry = geometry;
    // ...and the reload generation, for the readiness signal (a reload keeps
    // the geometry, so the geometry alone cannot tell the old preview's
    // release from the new one's).
    const forNonce = reloadNonce;
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
      if (snap.offBand || linkMeas || !currentExample!.has_design_freq) {
        req.measurement_freq_mhz = snap.measFreq;
      }
    }
    previewSigRef.current = JSON.stringify(req);
    apiFetch("/geometry", {
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
          // here, once per selection or user-design reload (this effect is
          // keyed on `geometry` + `reloadNonce`). A fixed orientation setting
          // wins over the guess (AK#1737); snapToDesignView decides.
          snapToDesignView((data as SolveResponse).default_view);
        }
        // Release the gate. The solve effect then either solves or — if the
        // design/solver combo is a poor match — withholds and warns.
        setPreviewReady(forGeometry);
        setPreviewNonce(forNonce);
      })
      .catch(() => {
        // Aborted or offline. If this run wasn't superseded, still release the
        // gate so the live solve renders the antenna (its own error path
        // surfaces anything that goes wrong there).
        if (!controller.signal.aborted) {
          setPreviewReady(forGeometry);
          setPreviewNonce(forNonce);
        }
      });
    return () => controller.abort();
    // reloadNonce (issue #867): a user-design reload re-runs this full
    // switch path for the same geometry — fresh preview from the re-loaded
    // builder, gate reset, then the live solve re-fires on release.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, reloadNonce]);

  // The parameter sweep (docs/design/z-vs-param-view.md): the knobs a chart
  // can sweep. A knob the design no longer has (a design or variant switch)
  // falls back to density, so a chart's spec never names a knob the request
  // does not carry (deriveChart).
  const zparamKnobs = sweepableKnobs(currentSchema);
  // What a knob's family of patterns can step (AK#1935): every knob the
  // knob sweep can, and the measurement frequency (patterns across the
  // band), which a pattern cell sets on its own request.
  const { knobs: familyKnobs, skipped: familySkipped } = familyKnobList(zparamKnobs);
  // A knob's default spec from its own range and value; density's is the
  // literal ladder.
  const zparamDefaultFor = (param: string): ParamSweepSpec => {
    if (param === DENSITY) return DEFAULT_DENSITY_SPEC;
    // A family over the measurement frequency (AK#1935): the band the
    // measurement frequency is in, its bottom, middle and top, the three
    // patterns a beam is judged by; with no band there, the chart's own
    // frequency range.
    if (param === FAMILY_FREQ) {
      const band = currentBands.find((b) => measFreq >= b.min_mhz && measFreq <= b.max_mhz);
      const r = band ? { lo: band.min_mhz, hi: band.max_mhz } : chartBaseRange;
      return { param, lo: r.lo, hi: r.hi, points: 3, log: false };
    }
    const knob = zparamKnobs.find((k) => k.name === param);
    const cur = currentValues[param];
    return knob ? defaultKnobSpec(knob, typeof cur === "number" ? cur : 1) : DEFAULT_DENSITY_SPEC;
  };
  // The design's own range, for what a frequency analysis's pick counts as
  // its own; and the range a chart with no range of its own sweeps: the
  // session's, the measurement dial's travel with its range-menu edit, as
  // the standalone sweep views did (AK#1682).
  const chartDesignRange = designSweepRange(sweepRangeInputs).range;
  const chartBaseRange = resolvedSweepRange.range;

  // What a chart's engine and ground crosses draw from (unit 4,
  // lib/chartCells.ts): the solver slots and ground slots as the session
  // holds them, by whatever ids it has. A slot that cannot draw this design
  // is a refused cell with the reason the session's own gate would give:
  // the design's backend allowlist, a design-dependent option refusal, or
  // (for any slot but the active one, which the session's gate governs) a
  // poor match, whose "Solve anyway" belongs to the active slot.
  const slotIds = (Object.keys(slots) as Slot[]).sort();
  const slotRefusal = (id: Slot): string | null => {
    const cfg = slots[id];
    if (!backendAllowed(cfg.backend, requiredBackends)) return RESTRICTED_BACKEND_REASON;
    const refused = designRefusal(cfg.backend, cfg.opts, designConstraintInputs);
    if (refused) return refused.reason;
    if (id !== activeSlot && comboInappropriate(cfg.backend, recommendedBackend)) {
      return `a poor match for this design: make ${id} the active slot and Solve anyway to draw it`;
    }
    return null;
  };
  const crossEnv: CrossEnv = {
    slots: slotIds.map((id) => ({
      id,
      label: `${id}: ${backendDisplayLabel(slots[id].backend, slots[id].opts, designConstraintInputs)}`,
      holds: (spec: string) =>
        engineSpecHeld(
          spec,
          slots[id].backend,
          slots[id].opts.model.degree as number | null | undefined,
        ),
      refusal: slotRefusal(id),
    })),
    activeSlot,
    grounds: groundSlots.map((g) => ({
      id: g.id,
      label: `${g.id}: ${groundSlotLabel(g, soilPresets ?? [])}`,
      holds: (spec: string) => groundSpecHeld(spec, g, servedDefaultSoil),
    })),
    activeGround: activeGroundSlot,
    design: geometry,
    soilPresets: soilPresets ?? [],
    groundRefusal: (slotId: string, groundId: string) => {
      const g = groundSlots.find((x) => x.id === groundId);
      const cfg = slots[slotId as Slot];
      return g && cfg ? groundRefusal(g, cfg.backend) : null;
    },
  };
  // A chart's cells (lib/chartCells.ts crossPlan), with a design cell this
  // session's catalog does not hold refused by name: its defaults are the
  // catalog's (designAtDefaults), so there is nothing to build it from.
  const planOf = (cross: ChartCross, listed: ListedCross): CrossPlan => {
    const plan = crossPlan(cross, listed, crossEnv);
    return {
      ...plan,
      cells: plan.cells.map((c) =>
        c.design !== undefined && !c.refused && !examples.some((e) => e.name === c.design)
          ? { ...c, refused: `no design ${c.design} in this session's catalog` }
          : c,
      ),
    };
  };
  const drawable = (c: ChartCell) => !c.refused && c.slot !== null && c.ground !== null;
  // One curve's solve inputs: that cell's slot and ground slot on the
  // session's request (buildRequestFor), with its plane, design and family
  // step (unit 4b), on a lane stream of its own so the curves do not
  // supersede one another server-side. The first chart's first curve takes
  // no stream, the request the chart always sent. Only a cell on the active
  // slot carries the session's "Solve anyway" approval.
  const cellRequest = (
    i: number,
    k: number,
    slot: Slot,
    ground: string,
    cell?: Pick<ChartCell, "plane" | "design" | "state" | "step">,
  ): ChartCellRequest => {
    const cfg = slots[slot];
    const g = groundRequestFor(ground, cfg.backend);
    return {
      slot,
      ground,
      ...(cell?.plane !== undefined ? { plane: cell.plane } : {}),
      ...(cell?.design !== undefined ? { design: cell.design } : {}),
      ...(cell?.state !== undefined ? { state: cell.state } : {}),
      ...(cell?.step !== undefined ? { step: cell.step } : {}),
      stream: i === 0 && k === 0 ? null : `c${i}r${k}`,
      backend: cfg.backend,
      groundEnabled: g.enabled,
      groundModel: g.model,
      onActiveSlot: slot === activeSlot,
    };
  };

  // One chart as it runs: its knob spec resolved against this design's
  // knobs, what each runner is asked for (chartRunInputs: the knob sweep's
  // request, whose `auto` is the chart's dwell switch, and the frequency
  // sweep's range and switch), and its cross: the cells, the runnable ones
  // in order, and one runner input per runnable cell.
  // What a chart's cells come from: the picked analysis's crosses
  // (chartListed), or a knob's family of patterns' step cross (AK#1935),
  // over the values its knob spec makes (`values`: the chart's own ladder).
  const listedFor = (c: AnalysisChartState, values?: readonly number[]): ListedCross =>
    familyListed(c, values ?? knobLadder(c.knob.spec)) ?? chartListed(c);
  // A knob spec's values, as the chart solves them: an int knob (and the
  // density ladder) rounded to whole values; a family's frequency never.
  const knobLadder = (spec: ParamSweepSpec): number[] =>
    paramLadder(
      spec,
      spec.param === DENSITY || zparamKnobs.find((k) => k.name === spec.param)?.kind === "int",
    );
  const deriveChart = (i: number, state: AnalysisChartState) => {
    const knob = zparamKnobs.find((k) => k.name === state.knob.spec.param) ?? null;
    // A family over the measurement frequency (AK#1935) steps `freq`, which
    // no knob sweep sweeps; only a family keeps it.
    const freqFamily = chartFamily(state) && state.knob.spec.param === FAMILY_FREQ;
    const spec =
      state.knob.spec.param === DENSITY || knob || freqFamily ? state.knob.spec : DEFAULT_DENSITY_SPEC;
    const isDensity = spec.param === DENSITY;
    const values = paramLadder(spec, isDensity || knob?.kind === "int");
    const label = isDensity ? "N" : freqFamily ? "frequency (MHz)" : (knob?.label ?? spec.param);
    const now: AnalysisChartState = { ...state, knob: { ...state.knob, spec } };
    const viewId = CHART_VIEW_IDS[i];
    const resident = isResident(viewId);
    const inputs = chartRunInputs(now, {
      resident,
      dwellDefaults,
      designRange: chartBaseRange,
      values,
      label,
    });
    const listedNow = listedFor(now, values);
    const plan = planOf(now.cross, listedNow);
    const drawn = plan.cells.filter(drawable);
    // A design cell of a knob sweep sweeps that design's own parameter and
    // values, as /analyses resolved them on it (a role may name another
    // knob there, and a range left to the knob is that design's).
    // A range / points / spacing edit of the picked analysis moves the
    // session design's cells with it (as a frequency range edit does), and
    // leaves the other designs on what the server served.
    // A state cell (step 7) sweeps what /analyses served for it, on its
    // design at its defaults with its knobs set; one on the loaded design is
    // the session design's for an edit, as that design's own cell is.
    const edited = pickedEdited(now);
    const sessionDesign = (c: ChartCell) => c.design === geometry || (c.design === undefined && !!c.state);
    const ownSweep = (c: ChartCell) => {
      if (edited && sessionDesign(c)) return null;
      const d = servedCell(c, listedNow);
      return d?.param && d.values ? { param: d.param, values: d.values } : null;
    };
    // A design cell of a frequency sweep sweeps that design's own band, on
    // exactly the grid `antennaknobs analyze` sweeps there (served by
    // /analyses), so two designs on different bands each stay on theirs. A
    // range edit on the chart moves only the session design's curves: its
    // own cell in the cross, and every cell without one.
    const ownBand = (c: ChartCell): SweepRange | null => {
      if (c.design === undefined && !c.state) return null;
      if (sessionDesign(c) && now.frequency?.rangeEdit) return null;
      const d = servedCell(c, listedNow);
      const f = d?.freqs;
      if (!f || f.length === 0) return null;
      // An explicit frequency list is swept exactly on every design, as
      // the session design's own is (listRange, step 5 unit 5).
      if (now.frequency?.analysisRange?.exact) return listRange(f);
      return { lo: f[0], hi: f[f.length - 1], spacing: d.spacing ?? "lin", freqs: f };
    };
    const runs: CellRun[] = drawn.map((c, k) => {
      const own = now.kind === "knob" ? ownSweep(c) : null;
      const band = now.kind === "frequency" ? ownBand(c) : null;
      let paramReq = own ? { ...inputs.param.req, ...own } : inputs.param.req;
      // A MetricPlot's FIXED reference (AK#1828) is solved once at its own
      // setting, its knobs its own: never held (AK#1757 step 6), as
      // `antennaknobs analyze` solves it.
      if (paramReq.hold && servedCell(c, listedNow)?.fixed) {
        const { hold: _hold, ...unheld } = paramReq;
        void _hold;
        paramReq = unheld;
      }
      return {
        cell: cellRequest(i, k, c.slot as Slot, c.ground as string, c),
        // A chart of one cell names no curve, so its curve is "solo"
        // whatever cell it is on (CellRun.cellKey).
        cellKey: plan.cells.length === 1 ? "solo" : c.key,
        freq: band ? { ...inputs.freq, range: band } : inputs.freq,
        param: paramReq === inputs.param.req ? inputs.param : { ...inputs.param, req: paramReq },
        // A pattern cell is one solve (step 7): its request is the cell's.
        pattern: inputs.pattern,
        // A map draws one grid (decision 9): its first cell only.
        map: k === 0 ? inputs.map : { ...inputs.map, wanted: false },
      };
    });
    const currentRaw = isDensity ? nPerWire : currentValues[spec.param];
    return {
      i,
      viewId,
      state,
      now,
      spec,
      knob,
      isDensity,
      values,
      label,
      current: typeof currentRaw === "number" ? currentRaw : null,
      dwellOn: chartDwell(now, dwellDefaults),
      resident,
      inputs,
      plan,
      drawn,
      runs,
    };
  };
  type ChartModel = ReturnType<typeof deriveChart>;
  const chartModels: (ChartModel | null)[] = charts.map((c, i) => (c ? deriveChart(i, c) : null));
  const m0 = chartModels[0]!;
  // The first chart's run inputs: its first curve is the session's runner
  // pair (useAnalysisRunners, below).
  const chartInputs = m0.inputs;
  // Choosing what to sweep is a pick, and a pick runs it (Steve's phone,
  // 2026-09-29: he chose length_factor in the header, got "no sweep yet"
  // and a small "run" among the wrapped controls, and never saw a curve).
  // Unit 2 left a knob choice waiting for Run; the rulings say a pick runs.
  const selectZparamParam = (i: number, param: string) => {
    if (param !== DENSITY) setLastKnob(param);
    chartControl(i).armParam();
    setZparamSpecAt(i, zparamDefaultFor(param));
    setZparamXLogAt(i, null);
    // Another knob leaves the picked analysis (and its crosses); the same
    // knob (Reset) is an edit of it and keeps it.
    setChartAt(i, (c) =>
      c.picked?.kind === "knob" && c.picked.spec?.param !== param ? { ...c, picked: null } : c,
    );
  };
  // The knob the picker's "Sweep a knob" runs (Steve, 2026-09-29): the one
  // in the chart's parameter list when that is a knob, else the last knob
  // swept this session, else the design's first sweepable knob.
  const [lastKnob, setLastKnob] = useState<string | null>(null);
  const knobToSweep = (m: ChartModel) =>
    zparamKnobs.find((k) => k.name === m.spec.param)?.name ??
    zparamKnobs.find((k) => k.name === lastKnob)?.name ??
    zparamKnobs[0]?.name ??
    DENSITY;
  // "Sweep this knob": that knob, its default range, and the chart's view
  // on the stage (a peek when it is not pinned). The knob menu's drives the
  // first chart; a chart's own picker drives that chart.
  const sweepKnob = (param: string, i = 0) => {
    const m = chartModels[i];
    if (!m) return;
    setLastKnob(param);
    const next = zparamDefaultFor(param);
    setKnobMenu(null);
    if (m.state.kind === "knob" && sameSpec(next, m.spec) && m.resident) {
      // Already this sweep on screen: nothing will change to arm, so run it.
      // "Sweep a knob" still leaves a picked analysis, its crosses with it,
      // even when the analysis swept this very knob and range.
      if (m.state.picked) setChartAt(i, (c) => ({ ...c, picked: null }));
      chartControl(i).runParamNow();
    } else {
      chartControl(i).armParam();
      setChartAt(i, (c) => pickKnob(c, null, next));
    }
    // The knob sweep as R/X against the knob, what "Sweep this knob…" asks
    // to see.
    setChartAt(i, (c) => setChartView(c, "Rx"));
    setView(m.viewId);
  };
  // The design's analyses (AK#1757): every chart's own picker. Picking one
  // runs it IN that chart, whatever it sweeps (step 5 unit 2): a knob
  // analysis sets the chart's spec to its parameter and values and runs it;
  // a frequency analysis runs the chart's own frequency sweep over its range
  // and draws its first view. Either preselects the slots its listed engines
  // and grounds name (unit 4). Neither touches another chart, the session's
  // sweep range or the viewer's saved chart preferences. What the chart
  // cannot run yet is listed with why, and picking it does nothing.
  const { entries: zparamAnalyses, loaded: zparamAnalysesLoaded } = useDesignAnalyses({
    designKey: `${zparamDesignKey}#${reloadNonce}#${studiesNonce}`,
    // Not before the session has a design: the first render has none.
    enabled: chartModels.some((m) => m?.resident) && !!geometry,
    request: buildRequest,
  });
  const zparamSweepable = new Set(zparamKnobs.map((k) => k.name));
  // A kept band run is jumped to, never drawn (AK#1906): it is never blocked
  // here (a run on another variant is served unrunnable, with why).
  const zparamAnalysisBlocked = (a: AnalysisEntry) =>
    a.kept ? null : analysisBlocked(a.workbench, zparamSweepable);
  const knobAnalysisSpec = (w: { param: string; values: number[]; log: boolean }) =>
    analysisSpec(
      { runs: true, kind: "knob", note: null, ...w },
      zparamKnobs.find((k) => k.name === w.param)?.kind === "int",
    );
  // What a pick lists, and the slots it preselects (lib/chartCells.ts).
  const pickCross = (c: AnalysisChartState, w: Listed) => {
    const listed: ListedCross = {
      engines: w.engines ?? null,
      grounds: w.grounds ?? null,
      axes: w.axes ?? [],
      planes: w.planes ?? null,
      designs: w.designs ?? null,
      states: w.states ?? null,
      cells: w.cells ?? null,
      step: w.step ?? null,
    };
    return withListed(c, listed, preselect(listed, crossEnv));
  };
  // A pick runs what it picked, curve by curve: a curve whose cell and
  // inputs the pick leaves as they were has nothing to arm (its runner
  // would never see a change), so it runs now; every other curve (a new or
  // moved cell, a new range or spec) is armed for the change the pick
  // makes. `same` says the pick keeps the chart's range or spec.
  const runPicked = (
    i: number,
    kind: "freq" | "param" | "pattern" | "map",
    next: AnalysisChartState,
    same: boolean,
  ) => {
    const m = chartModels[i];
    if (!m) return;
    const nextCells = planOf(next.cross, listedFor(next)).cells.filter(drawable);
    allRunnersOf[i].forEach((r, k) => {
      const runner =
        kind === "freq" ? r.freq : kind === "param" ? r.param : kind === "map" ? r.map : r.pattern;
      if (same && m.resident && k < nextCells.length && m.drawn[k]?.key === nextCells[k].key) {
        runner.runNow();
      } else {
        runner.arm();
      }
    });
  };
  // A pick that only selects: every curve the pick changes waits for Run,
  // even on a chart whose dwell switch is on (the switch governs what
  // happens AFTER the pick). A curve the pick leaves as it was sees no
  // change, so there is nothing to hold, and holding it would swallow the
  // next real change instead.
  const holdPicked = (
    i: number,
    kind: "freq" | "param" | "pattern" | "map",
    next: AnalysisChartState,
    same: boolean,
  ) => {
    const m = chartModels[i];
    if (!m) return;
    const nextCells = planOf(next.cross, listedFor(next)).cells.filter(drawable);
    allRunnersOf[i].forEach((r, k) => {
      if (same && m.resident && k < nextCells.length && m.drawn[k]?.key === nextCells[k].key) return;
      (kind === "freq" ? r.freq : kind === "param" ? r.param : kind === "map" ? r.map : r.pattern).hold();
    });
  };
  // `run` says whether the pick starts the analysis: absent (the picker),
  // settings.toml's [workbench.run_on_pick] for its kind (AC6LA #179); a
  // deep link's run=1 passes true, whatever the setting (AK#1838). False
  // only selects: the chart shows the analysis, ready, and waits for Run.
  const pickAnalysis = (i: number, entry: AnalysisEntry, runArg?: boolean) => {
    if (entry.kept) {
      jumpToKept(entryLabel(entry), entry.kept, "result");
      return;
    }
    const m = chartModels[i];
    const w = entry.workbench;
    if (!m || !w.runs || zparamAnalysisBlocked(entry)) return;
    const run = runArg ?? pickRuns(w, runOnPick);
    const start = (kind: "freq" | "param" | "pattern" | "map", next: AnalysisChartState, same: boolean) =>
      (run ? runPicked : holdPicked)(i, kind, next, same);
    if (w.kind === "map") {
      // A map (docs/design/sweep-framework-map.md): one grid, on Run unless
      // [workbench.run_on_pick] says a pick runs it. Already this map: run
      // it (nothing will change to arm).
      const integer = (k: string) => zparamKnobs.find((z) => z.name === k)?.kind === "int";
      const picked = pickCross(
        pickMap(m.state, entry.name, w, { x: integer(w.x.param), y: integer(w.y.param) }),
        w,
      );
      // One solver slot and one ground slot (decision 15): slots ticked for
      // an earlier pick keep only their first.
      const one = (ids: string[] | null) => (ids && ids.length > 1 ? [ids[0]] : ids);
      const next: AnalysisChartState = {
        ...picked,
        cross: { slots: one(picked.cross.slots), grounds: one(picked.cross.grounds) },
      };
      start("map", next, m.state.kind === "map" && pickedName(m.now) === entry.name && !pickedEdited(m.now));
      setChartAt(i, () => next);
      return;
    }
    if (w.kind === "pattern") {
      // A pattern (step 7): one solve per cell, drawn on its first view.
      // Already this pattern (the cells it keeps): nothing will change to
      // arm, so run it.
      const next = pickCross(pickPattern(m.state, entry.name, w), w);
      start("pattern", next, m.state.kind === "pattern" && pickedName(m.now) === entry.name);
      setChartAt(i, () => next);
      return;
    }
    if (w.kind === "frequency") {
      const next = pickCross(
        pickFrequency(m.state, entry.name, w, chartDesignRange, {
          axes: sweepAxes,
          threshold: swrThreshold,
        }),
        w,
      );
      const range = (c: AnalysisChartState) =>
        c.frequency ? JSON.stringify(chartFrequencyRange(c.frequency, chartBaseRange)) : "";
      // Already this sweep (the curves it keeps): nothing will change to
      // arm, so run it.
      start("freq", next, m.state.kind === "frequency" && range(m.state) === range(next));
      setChartAt(i, () => next);
      return;
    }
    const next = knobAnalysisSpec(w);
    if (w.param !== DENSITY) setLastKnob(w.param);
    // A held analysis (step 6) carries its hold onto the chart: every curve
    // re-solves the hold's knobs at each point, on Run.
    const picked = pickCross(
      pickKnob(m.state, entry.name, next, w.views, w.metric, w.hold ?? null),
      w,
    );
    start("param", picked, m.state.kind === "knob" && sameSpec(next, m.spec));
    setChartAt(i, () => picked);
  };
  // The picker's current entry: the analysis picked while the chart still
  // runs it, else (a knob sweep nobody picked, as the chart opens) the first
  // analysis that sweeps exactly the chart's spec, so a design whose own
  // default is its convergence analysis opens with it named.
  const pickedNameOf = (m: ChartModel) =>
    pickedName(m.now) ??
    (m.state.kind === "knob"
      ? (zparamAnalyses.find(
          (a) =>
            a.workbench.runs &&
            a.workbench.kind === "knob" &&
            // Never one whose own crosses draw curves (planes, designs, a
            // family): an unpicked chart draws none of them, so naming it
            // after one would label curves it does not draw. An engine or
            // ground cross is fine (the design default "convergence").
            !(a.workbench.axes ?? []).some((k) => k === "planes" || k === "designs" || k === "step") &&
            !zparamAnalysisBlocked(a) &&
            sameSpec(knobAnalysisSpec(a.workbench), m.spec),
        )?.name ?? null)
      : null);
  // The knob sweep's end-value boxes (Steve's phone, 2026-09-29: four boxes
  // on a phone-sized plot covered it). Off to start on a phone, on on a
  // desktop as before; the chart's "values" toggle flips them. Session-only,
  // like everything a chart shows: never in the browser's storage or in
  // settings.toml.
  const [calloutsFlip, setCalloutsFlip] = useState<boolean | null>(null);
  const chartCallouts = calloutsFlip ?? !isMobile;
  const zparamSettingsOf = (m: ChartModel) => ({
    param: m.spec.param,
    label: m.label,
    unit: m.isDensity ? "segments per λ/4" : (m.knob?.unit ?? null),
    total: m.values.length,
    currentValue: m.current,
    xLog: m.state.knob.xLog ?? m.spec.log,
    rAxis: m.state.knob.axes.r,
    xAxis: m.state.knob.axes.x,
    // The session's reference (the design's Zo, or the Zo field's override,
    // AK#1735): what the VSWR chart measures against.
    z0,
    // A held pick's knobs (AK#1757 step 6): what its Knobs view draws.
    ...(chartHold(m.now) ? { heldKnobs: chartHold(m.now)!.knobs } : {}),
  });
  // A word on cost (docs/design/z-vs-param-view.md): a density sweep whose
  // top N is past twice the slot's own default density solves the fine end
  // on meshes several times what the engine needs, and the dense solve grows
  // about as N³. Cheap: two numbers the session already holds.
  const engineN = defaultNPerWireFor(backend, currentOpts.model.degree);
  const costHintOf = (m: ChartModel) => {
    const topN = m.isDensity && m.values.length ? Math.max(...m.values) : 0;
    return m.isDensity && topN > 2 * engineN
      ? `N up to ${topN}: ${(topN / engineN).toFixed(topN / engineN >= 10 ? 0 : 1)}× this engine's default N = ${engineN}, so the fine end is slow`
      : null;
  };

  // The four background analyses (#642 seam 5b-3): freq sweep, convergence
  // sweep, far-field norm check and the NEC rp_card pattern. Called here, at
  // the debounce effects' old position, so all four keep their global order
  // behind the solve and preview effects above. Its frequency and parameter
  // sweeps are the first chart's first curve (unit 4: on that cell's slot
  // and ground, `chartCell`).
  const primaryRun = m0.runs[0];
  // The analyses wait on the design the way the live solve does (AK#1806):
  // the catalog has resolved it and its preview has landed (the solve
  // effect's `previewReady === geometry` gate). Before that `geometry` is ""
  // on a cold load, and a sweep sent while /examples is still out names no
  // design the server knows (the #1343 unknown-design 400). Every runner
  // below reads it as its `active`.
  const analysesActive = active && geometry !== "" && previewReady === geometry;
  const {
    normCheck,
    pattern,
    abortInFlight,
    freq: primaryFreq,
    param: primaryParam,
  } = useAnalysisRunners({
      backend,
      currentVariant,
      currentExample,
      currentBands,
      freqWindowCeiling,
      designFreq,
      measFreq,
      measLocked,
      // The analysis chart's frequency sweep (AK#1757 step 5 unit 3): the
      // session's one frequency runner IS the first chart's first curve,
      // over the chart's range, wanted while the chart shows a frequency
      // sweep on screen, and re-run after the dwell only while its switch
      // is on. One runner, so a default chart sends exactly the /sweep
      // traffic the standalone Smith view with its freq-sweep switch on did,
      // and never a second sweep.
      sweepRange: primaryRun?.freq.range ?? chartInputs.freq.range,
      groundEnabled,
      groundModel,
      sweepEnabled: chartInputs.freq.wanted && !!primaryRun,
      sweepAuto: chartInputs.freq.auto,
      normCheckEnabled,
      necOverlayEnabled,
      sweepResident: chartInputs.freq.wanted && !!primaryRun,
      // The chart's knob sweep, on its R/X or Smith view.
      paramViewResident: chartInputs.param.wanted && !!primaryRun,
      // The first curve's own (a design cell sweeps its design's values).
      paramSweep: primaryRun?.param.req ?? chartInputs.param.req,
      patternResident,
      autoSim,
      active: analysesActive,
      comboApproved,
      recommendedBackend,
      // Same reference the sweep/Smith charts plot against (the session's
      // `z0`, AK#1735), so refinement judges curvature on the curve the user
      // is actually looking at.
      z0,
      refineEnabled,
      // Only the chart's view on screen: refinement buys solves per
      // projection (issue #744).
      residentSweepViews: chartInputs.freq.views,
      // The chart's VSWR / S11 ranges (AK#1738), for the same reason.
      sweepAxes: chart.frequency?.axes ?? sweepAxes,
      swrThreshold: chart.frequency?.threshold ?? swrThreshold,
      buildRequest,
      solveWithheld,
      seqRef,
      approvedComboRef,
      ...(primaryRun
        ? { chartCell: primaryRun.cell, chartCellKey: primaryRun.cellKey, buildCellRequest }
        : {}),
    });
  // The first chart's first pattern cell (AK#1757 step 7): the chart's
  // other runners for that cell live in useAnalysisRunners, and this one
  // beside them, on the same cell request (the session's own when there is
  // no cell) and the same approval rule.
  const primaryPatternBuild = primaryRun ? () => buildCellRequest(primaryRun.cell) : buildRequest;
  const primaryPattern = usePatternCell({
    sig: primaryRun ? patternSignature(primaryPatternBuild()) : "",
    wanted: !!primaryRun && chartInputs.pattern.wanted,
    auto: chartInputs.pattern.auto,
    elevAzDeg: chartInputs.pattern.elevAzDeg,
    azElevDeg: chartInputs.pattern.azElevDeg,
    autoSim,
    active: analysesActive,
    comboApproved,
    recommendedBackend,
    buildRequest: primaryPatternBuild,
    solveWithheld,
    seqRef,
    approvedComboRef: primaryRun && !primaryRun.cell.onActiveSlot ? NOT_APPROVED : approvedComboRef,
    cell: primaryRun?.cellKey,
  });
  // The first chart's map (docs/design/sweep-framework-map.md), beside its
  // first pattern cell, on the same cell request and approval rule.
  const primaryMap = useMapRun({
    sig: primaryRun ? mapSignature(primaryPatternBuild(), chartInputs.map.x, chartInputs.map.y) : "",
    x: chartInputs.map.x,
    y: chartInputs.map.y,
    wanted: !!primaryRun && chartInputs.map.wanted,
    auto: chartInputs.map.auto,
    autoSim,
    active: analysesActive,
    comboApproved,
    recommendedBackend,
    buildRequest: primaryPatternBuild,
    solveWithheld,
    approvedComboRef: primaryRun && !primaryRun.cell.onActiveSlot ? NOT_APPROVED : approvedComboRef,
  });
  // Every other curve (unit 4): the first chart's second to sixth, and each
  // duplicate's six, a fixed set of runner pairs per chart (useChartCells)
  // of which a chart's cells use the first few. The refinement ranges are
  // each chart's own.
  const idleRun: CellRun = {
    cell: cellRequest(0, 0, activeSlot, activeGroundSlot),
    freq: { ...chartInputs.freq, wanted: false },
    param: { ...chartInputs.param, wanted: false },
    pattern: { ...chartInputs.pattern, wanted: false },
    map: { ...chartInputs.map, wanted: false },
  };
  const chartAxes = (m: ChartModel | null) => ({
    sweepAxes: m?.state.frequency?.axes ?? sweepAxes,
    swrThreshold: m?.state.frequency?.threshold ?? swrThreshold,
  });
  const firstChartRest = useChartCells({
    runs: m0.runs.slice(1),
    idle: idleRun,
    build: buildCellRequest,
    refineEnabled,
    z0,
    ...chartAxes(m0),
    autoSim,
    active: analysesActive,
    comboApproved,
    recommendedBackend,
    solveWithheld,
    seqRef,
    approvedComboRef,
  });
  const chart1Cells = useChartCells({
    runs: chartModels[1]?.runs ?? [],
    idle: idleRun,
    build: buildCellRequest,
    refineEnabled,
    z0,
    ...chartAxes(chartModels[1]),
    autoSim,
    active: analysesActive,
    comboApproved,
    recommendedBackend,
    solveWithheld,
    seqRef,
    approvedComboRef,
  });
  const chart2Cells = useChartCells({
    runs: chartModels[2]?.runs ?? [],
    idle: idleRun,
    build: buildCellRequest,
    refineEnabled,
    z0,
    ...chartAxes(chartModels[2]),
    autoSim,
    active: analysesActive,
    comboApproved,
    recommendedBackend,
    solveWithheld,
    seqRef,
    approvedComboRef,
  });
  const chart3Cells = useChartCells({
    runs: chartModels[3]?.runs ?? [],
    idle: idleRun,
    build: buildCellRequest,
    refineEnabled,
    z0,
    ...chartAxes(chartModels[3]),
    autoSim,
    active: analysesActive,
    comboApproved,
    recommendedBackend,
    solveWithheld,
    seqRef,
    approvedComboRef,
  });
  // Each chart's runner pairs, all of them (for arming a pick), and the
  // ones its runnable cells use, in cell order.
  const allRunnersOf: CellRunners[][] = [
    [{ freq: primaryFreq, param: primaryParam, pattern: primaryPattern, map: primaryMap }, ...firstChartRest],
    chart1Cells,
    chart2Cells,
    chart3Cells,
  ];
  const runnersOf = (m: ChartModel): CellRunners[] => allRunnersOf[m.i].slice(0, m.runs.length);
  // A chart's Run, Stop and arming, over all its curves.
  const chartControl = (i: number) => {
    const all = allRunnersOf[i];
    const live = chartModels[i] ? all.slice(0, chartModels[i]!.runs.length) : [];
    return {
      armFreq: () => all.forEach((r) => r.freq.arm()),
      runFreqNow: () => live.forEach((r) => r.freq.runNow()),
      stopFreq: () => live.forEach((r) => r.freq.abort()),
      armParam: () => all.forEach((r) => r.param.arm()),
      runParamNow: () => live.forEach((r) => r.param.runNow()),
      stopParam: () => live.forEach((r) => r.param.stop()),
      armPattern: () => all.forEach((r) => r.pattern.arm()),
      runPatternNow: () => live.forEach((r) => r.pattern.runNow()),
      stopPattern: () => live.forEach((r) => r.pattern.stop()),
      armMap: () => all.forEach((r) => r.map.arm()),
      runMapNow: () => live.slice(0, 1).forEach((r) => r.map.runNow()),
      stopMap: () => live.forEach((r) => r.map.stop()),
    };
  };
  // The deep link (AK#1838): the page's ?design=…&analysis=…&view=…&run=1,
  // which the first tab opens on. It is applied in stages, each waiting on
  // what the one before it set: the design (picked by the catalog's first
  // pick, useDesignCatalog's `preferred`), its variant once that design is
  // the current one, the analysis once /analyses has answered for that
  // design and variant, and the chart's view once the pick has landed. A
  // name that resolves to nothing is reported by name in the notice below
  // and otherwise ignored; an unknown design ends the link there, since its
  // analysis and view were for that design.
  type LinkStage = "design" | "variant" | "analysis" | "view" | "done";
  const [linkStage, setLinkStage] = useState<LinkStage>(deepLink ? "design" : "done");
  // Seeded with the shell's report when the link's deck did not open.
  const [linkProblems, setLinkProblems] = useState<string[]>(() =>
    [deepLink?.problem, deepLink?.familyProblem, deepLink?.cutProblem].filter((p): p is string => !!p),
  );
  const linkProblem = (p: string) => setLinkProblems((ps) => [...ps, p]);
  // Opening the user's own deck (lib/decks.ts): read here, opened on the
  // server, and then simply the design this tab is on. Its refusal (over a
  // limit, a card the importer cannot model) is the server's own sentence.
  const [deckError, setDeckError] = useState<string | null>(null);
  const openDeckFromFile = (file: File) => {
    setDeckError(null);
    openDeckFile(file).then(
      (d) => setGeometry(d.key),
      (e: unknown) => setDeckError(e instanceof Error ? e.message : String(e)),
    );
  };
  // The dialect control (DeckNotice): the same deck, re-opened read in the
  // chosen dialect, is another design (its key carries the choice) and the
  // link follows it (`&dialect=`).
  const reopenDeckAs = (dialect: Dialect | null) => {
    const d = isDeck(geometry) ? deckFor(geometry) : undefined;
    if (!d) return;
    setDeckError(null);
    openDeck({ name: d.name, z: d.z, ...(dialect ? { dialect } : {}) }).then(
      (o) => setGeometry(o.key),
      (e: unknown) => setDeckError(e instanceof Error ? e.message : String(e)),
    );
  };
  // The chart is where an analysis or a view lands, and listing the
  // design's analyses waits for it to be on screen (useDesignAnalyses).
  useEffect(() => {
    if (deepLink && (deepLink.analysis || deepLink.view || deepLink.family)) setView("zparam");
    // On mount: the link is the page's, and never changes.
  }, [deepLink, setView]);
  useEffect(() => {
    if (!deepLink || linkStage !== "design" || examples.length === 0) return;
    if (deepLink.design) {
      const r = resolveDesign(deepLink.design, examples);
      if (!r.ok) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        linkProblem(r.problem);
        setLinkStage("done");
        return;
      }
    }
    setLinkStage("variant");
  }, [deepLink, linkStage, examples]);
  // The design the link named (resolved), else whichever the session opened.
  const linkDesign = (() => {
    if (!deepLink?.design || examples.length === 0) return geometry;
    const r = resolveDesign(deepLink.design, examples);
    return r.ok ? r.value : geometry;
  })();
  useEffect(() => {
    if (!deepLink || linkStage !== "variant") return;
    if (!currentExample || currentExample.name !== linkDesign) return;
    if (deepLink.variant) {
      const r = resolveVariant(deepLink.variant, currentExample);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (!r.ok) linkProblem(r.problem);
      else if (r.value !== currentVariant) selectVariant(r.value);
    }
    setLinkStage(deepLink.analysis || deepLink.view || deepLink.family ? "analysis" : "done");
    // Runs when the stage or the design changes; the rest is read as it
    // stands then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLink, linkStage, currentExample, linkDesign]);
  useEffect(() => {
    if (!deepLink || linkStage !== "analysis") return;
    if (!deepLink.analysis) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLinkStage(deepLink.view || deepLink.family ? "view" : "done");
      return;
    }
    if (!zparamAnalysesLoaded || currentExample?.name !== linkDesign) return;
    const r = resolveAnalysis(deepLink.analysis, zparamAnalyses);
    if (!r.ok) {
      linkProblem(r.problem);
      // Its view was for that analysis: the chart's own stays.
      setLinkStage("done");
      return;
    }
    const why = zparamAnalysisBlocked(r.value);
    if (why !== null) {
      linkProblem(`analysis "${r.value.name}" cannot run here: ${why}`);
      setLinkStage("done");
      return;
    }
    // run=1 starts it (exactly one run), whatever [workbench.run_on_pick]
    // says; without it the link picks as the picker does, by that setting.
    pickAnalysis(0, r.value, deepLink.run ? true : undefined);
    setLinkStage(deepLink.view ? "view" : "done");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLink, linkStage, zparamAnalysesLoaded, zparamAnalyses, currentExample, linkDesign]);
  useEffect(() => {
    if (!deepLink || linkStage !== "view") return;
    if (deepLink.family) {
      // A pattern family (AK#1935): the knob chart on the family's knob and
      // range, then its view, which turns it into the family. Run as a pick
      // does ([workbench.run_on_pick]'s `pattern`; run=1 whatever it says).
      const f = deepLink.family;
      const next0 = pickKnob(chart, null, f);
      if (f.param !== FAMILY_FREQ && !zparamKnobs.some((k) => k.name === f.param)) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        linkProblem(`family: this design has no sweepable knob "${f.param}"`);
      } else if (!deepLink.view) {
        setChartAt(0, (c) => pickKnob(c, null, f));
      } else {
        const r = resolveView(deepLink.view, chartViews(next0));
        if (!r.ok) {
          linkProblem(r.problem);
        } else {
          let next = setChartView(next0, r.value);
          // The family's cut angle (AK#1950), on the cut it opened on.
          const v = chartPatternView(next);
          if (deepLink.cut !== undefined && deepLink.cut !== null && v) {
            const why = cutAngleProblem(v, deepLink.cut);
            if (why === null) next = setChartCut(next, deepLink.cut);
            else linkProblem(`cut ${deepLink.cut}°: the ${patternViewLabel(v)} view takes ${why}`);
          }
          if (r.value.startsWith("pattern:")) {
            (deepLink.run || runOnPick.pattern ? runPicked : holdPicked)(0, "pattern", next, false);
          }
          setChartAt(0, () => next);
        }
      }
    } else if (deepLink.view) {
      const r = resolveView(deepLink.view, chartViews(chart));
      if (!r.ok) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        linkProblem(r.problem);
      } else {
        setChartAt(0, (c) => setChartView(c, r.value));
      }
      // A cut angle is a family's alone (AK#1950): an analysis's views are
      // its own.
      if (deepLink.cut !== undefined && deepLink.cut !== null) {
        linkProblem(`cut ${deepLink.cut}°: only a pattern family (family=) takes a cut angle`);
      }
    }
    setLinkStage("done");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLink, linkStage]);
  // What the URL records of this tab (AK#1838): its design and variant
  // (the design's first left out), and the first chart's analysis and view.
  const linkStateOf = (m: ChartModel | null): LinkState => ({
    design: geometry,
    // An opened deck: the link carries the deck itself (when it fits).
    deck: isDeck(geometry) ? (deckFor(geometry) ?? null) : null,
    variant: currentVariant === (currentExample?.variants?.[0] ?? "default") ? null : currentVariant,
    analysis: m ? pickedNameOf(m) : null,
    // A knob's family of patterns (AK#1935) is no analysis a link can name:
    // it rides as its own knob and range (`family`) beside its pattern view.
    // Its range only: an explicit ladder is an analysis's, and a family's
    // values are its range's.
    family:
      m && chartFamily(m.state)
        ? {
            param: m.state.knob.spec.param,
            lo: m.state.knob.spec.lo,
            hi: m.state.knob.spec.hi,
            points: m.state.knob.spec.points,
            log: m.state.knob.spec.log,
          }
        : null,
    view: m ? chartView(m.state) : null,
    // The family's cut angle, where it is not the view's own (AK#1950).
    cut: m ? chartLinkCut(m.state) : null,
  });
  const urlState = linkStateOf(chartModels[0]);
  const urlSearch =
    currentExample && currentExample.name === geometry ? linkSearch(window.location.search, urlState) : null;
  // The URL follows the active tab, by replaceState (no history entry per
  // change), once its link has been applied: until then the address bar
  // keeps the link as it was given.
  useEffect(() => {
    if (!active || linkStage !== "done" || urlSearch === null) return;
    if (urlSearch === window.location.search) return;
    const { pathname, hash } = window.location;
    window.history.replaceState(window.history.state, "", `${pathname}${urlSearch}${hash}`);
  }, [active, linkStage, urlSearch]);
  // The chart's "link" button: this tab's design with the chart's analysis
  // and view, at this page's address.
  const copyChartLink = (m: ChartModel) =>
    navigator.clipboard?.writeText(linkHref(window.location, linkStateOf(m)));

  // The app's Cancel (AK#1712) stops every curve of every chart, as it
  // stops the session's own batches.
  const abortAllInFlight = () => {
    abortInFlight();
    primaryPattern.abort();
    primaryMap.abort();
    for (const rs of allRunnersOf.slice(1)) for (const r of rs) { r.freq.abort(); r.param.abort(); r.pattern.abort(); r.map.abort(); }
    for (const r of firstChartRest) { r.freq.abort(); r.param.abort(); r.pattern.abort(); r.map.abort(); }
  };

  // The Files view (AK#1428): the design's source file, plus the deck and
  // printout behind the solve on screen when an external engine produced it.
  // Same this-design gate as the budget above: another design's solve_id
  // would fetch another antenna's deck.
  const ownResult = result?.geometry === geometry ? result : null;
  const files = useEngineFiles({
    // Opt-in by focus, not residency. A Files thumbnail pinned in the rail
    // shows no text, so fetching per solve for it pays for nothing, and a solve
    // whose texts were evicted makes /engine_io re-run the whole engine deck on
    // the session's lane. Nothing is asked until Files is the view on the stage
    // (the focused cell in grid mode), and then only for the solve on screen.
    active: active && view === "files",
    geometry,
    solveId: ownResult?.solve_id ?? null,
    engineLabel: ownResult?.engine_io_label ?? null,
    // The NEC overlay's pattern run (AK#1506) lands under the solve it
    // belongs to; when it is this solve's, the texts are asked for again.
    patternSolveId: pattern?.solve_id ?? null,
    buildRequest,
    reloadNonce,
  });
  // Hoisted JSX shared between the desktop tree below and the mobile tree
  // (Phase B). These close over the session's locals, so they are consts /
  // a closure rather than components — zero prop surface, identical DOM.
  // (The former inline sub-blocks now live as prop-driven components in
  // components/session/ and results/StageOverlays.tsx — #642 seam 5b-2.)
  const controls = (
    <>
        <SessionGearMenu
          versionLabel={versionLabel}
          gearMenuOpen={gearMenuOpen}
          setGearMenuOpen={setGearMenuOpen}
          copiedParams={copiedParams}
          onCopyParams={() => copyParams({ buildRequest, setCopiedParams })}
          onDownloadNec={() =>
            downloadNec({ setGearMenuOpen, buildRequest, geometry })
          }
          onDownloadNec4={() =>
            downloadNec({
              setGearMenuOpen,
              // The deck is the NEC-4.2 slot's, so it carries that slot's
              // options (its Sommerfeld card) even when a momwire slot is the
              // active one: the active slot's own request when it is NEC-4.2,
              // else the first slot that holds it, else the active request.
              buildRequest: () => {
                const req = buildRequest();
                if (req.model_options?.sommerfeld !== undefined) return req;
                const holder = slotOrder(slots).find(
                  (s) => slots[s].backend.kind === "nec42",
                );
                if (holder === undefined) return req;
                const opts = modelOptionsForRequest(
                  slots[holder].backend,
                  slots[holder].opts,
                  modelOptionSpecs,
                );
                return { ...req, model_options: { ...req.model_options, ...opts } };
              },
              geometry,
              dialect: "nec4",
            })
          }
          onDownloadNec5={() =>
            downloadNec({
              setGearMenuOpen,
              buildRequest,
              geometry,
              dialect: "nec5",
            })
          }
          isMobile={isMobile}
          fullscreen={fullscreen}
          showHeatmap={showHeatmap}
          setShowHeatmap={setShowHeatmap}
          showEnvelope={showEnvelope}
          setShowEnvelope={setShowEnvelope}
          showWireLabels={showWireLabels}
          setShowWireLabels={setShowWireLabels}
          showFeedNames={showFeedNames}
          setShowFeedNames={setShowFeedNames}
          orientation={antennaOrientation}
          setOrientation={setAntennaOrientation}
          measured={measured}
          onLoadMeasured={(f) =>
            loadMeasured(f, { setGearMenuOpen, setMeasured })
          }
          onClearMeasured={() => setMeasured(null)}
          normCheckEnabled={normCheckEnabled}
          setNormCheckEnabled={setNormCheckEnabled}
          refineEnabled={refineEnabled}
          setRefineEnabled={setRefineEnabled}
          runOnPick={runOnPick}
          setRunOnPick={(kind, v) => setRunOnPick((t) => ({ ...t, [kind]: v }))}
          canSaveDefaults={uiDefaults.writable}
          onSaveDefaults={() => {
            setGearMenuOpen(false);
            void saveDefaults();
          }}
          theme={theme}
          applyTheme={applyTheme}
        />

        {!settingsProblemsDismissed && uiDefaults.problems.length > 0 && (
          <div className="settings-notice" role="alert">
            <span>
              <strong>settings.toml:</strong> {uiDefaults.problems.join(" · ")}
            </span>
            <button
              type="button"
              aria-label="Dismiss the settings notice"
              onClick={() => setSettingsProblemsDismissed(true)}
            >
              ×
            </button>
          </div>
        )}
        {linkProblems.length > 0 && (
          <div className="settings-notice" role="alert" aria-label="Link problems">
            <span>
              <strong>link:</strong> {linkProblems.join(" · ")}
            </span>
            <button
              type="button"
              aria-label="Dismiss the link notice"
              onClick={() => setLinkProblems([])}
            >
              ×
            </button>
          </div>
        )}
        <DeckNotice
          deck={isDeck(geometry) ? (deckFor(geometry) ?? null) : null}
          error={deckError}
          onDismissError={() => setDeckError(null)}
          onReadAs={reopenDeckAs}
        />
        {settingsNote && (
          <div className="settings-notice" role="status">
            <span>{settingsNote}</span>
            <button
              type="button"
              aria-label="Dismiss the save note"
              onClick={() => setSettingsNote(null)}
            >
              ×
            </button>
          </div>
        )}

        <CatalogPanel
          advisories={result?.advisories}
          geomGroups={geomGroups}
          geometry={geometry}
          currentExample={currentExample}
          geomFilter={geomFilter}
          setGeomFilter={setGeomFilter}
          setGeometry={setGeometry}
          currentVariant={currentVariant}
          selectVariant={selectVariant}
          examplesError={examplesError}
          loadErrors={loadErrors}
          trustBusy={trustBusy}
          trustDesign={trustDesign}
          onReloadDesign={reloadDesigns}
          reloadBusy={reloadBusy}
          onOpenDeck={openDeckFromFile}
        />

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

        {currentBands.length > 0 && currentExample?.has_design_freq && (
          <DesignFreqRow
            bands={currentBands}
            designFreq={designFreq}
            // The picked band wins while designFreq is inside it, so a custom
            // band that overlaps a served one still shows as picked (#1487).
            activeKey={
              currentBands.some(
                (b) =>
                  b.key === band &&
                  designFreq >= b.min_mhz &&
                  designFreq <= b.max_mhz,
              )
                ? band
                : bandContaining(designFreq)
            }
            onSelectBand={selectBand}
            onSetFreq={updateDesignFreq}
            onCustomBand={selectCustomDesignBand}
          />
        )}

        {/* Per-knob optimiser menu (right-click a knob): vary toggle + extents +
            turn step. Position-fixed at the click point. */}
        {knobMenu && currentExample && (
          <KnobOptMenu
            menu={knobMenu}
            spec={findKnobSpec(currentSchema, knobMenu.name)}
            ko={knobOptFor(knobMenu.name)}
            onPatch={(patch) => updateKnobOpt(knobMenu.name, patch)}
            onClose={() => setKnobMenu(null)}
            {...(zparamKnobs.some((k) => k.name === knobMenu.name)
              ? { onSweep: () => sweepKnob(knobMenu.name) }
              : {})}
          />
        )}

        {/* The measurement dial's range menu (AK#1682): right-click (or
            long-press) the dial. Its travel is the sweep range. */}
        {sweepMenu && (
          <SweepRangeMenu
            menu={sweepMenu}
            resolved={resolvedSweepRange}
            design={designSweepRange(sweepRangeInputs)}
            grid={sweepGrid(
              resolvedSweepRange.range,
              defaultSweepPoints({ backend, groundEnabled, groundModel, refineEnabled }),
            )}
            refineEnabled={refineEnabled}
            onEdit={applySweepRangeEdit}
            onRevert={() => applySweepRangeEdit(null)}
            onClose={() => setSweepMenu(null)}
          />
        )}

        {/* Measurement freq = the rig's tuning control: a weighted VFO dial +
            frequency-counter readout. Top line: band select + the LCD. Below:
            the Live/Optimize toggles stacked at the left of the dial, with the
            lock pinned to the dial's lower-right corner ("lock to design freq"
            disables the dial). */}
        <VfoPanel
          trackEnabled={trackOn}
          setTrackEnabled={toggleTrack}
          trackRefusal={trackRefusal}
          trackLatched={trackLatched}
          trackStatus={trackStatus?.status ?? null}
          currentBands={currentBands}
          // Until a design is loaded the dial and its range belong to no
          // design: the load's band snap would replace any edit made there
          // (AK#1762, reproduced), so both are inert until then.
          measLocked={measLocked || !currentExample}
          measFreq={measFreq}
          bandContaining={bandContaining}
          measBand={measBand}
          selectMeasBand={selectMeasBand}
          onCustomMeasBand={selectCustomMeasBand}
          sweepRange={resolvedSweepRange.range}
          {...(currentExample
            ? { onSweepMenu: (x: number, y: number, touch: boolean) => setSweepMenu({ x, y, touch }) }
            : {})}
          setMeasFreq={setMeasFreq}
          measLockable={measLockable}
          linkMeas={linkMeas}
          toggleLink={toggleLink}
          autoSim={autoSim}
          setAutoSim={setAutoSim}
          optEnabled={optEnabled}
          setOptEnabled={setOptEnabled}
          setOptPausedBy={setOptPausedBy}
          optRunning={optRunning}
          optObjective={optObjective}
          optSeed={optSeed}
          setOptSeed={setOptSeed}
          setOptObjective={setOptObjective}
          optResult={optResult}
          optProgress={optProgress}
          optError={optError}
          optPausedBy={optPausedBy}
          zo={{ value: z0, design: designZ0, set: setZoOverride }}
          bands={{
            freqs: optBands,
            setFreqs: setOptBands,
            meanWeight: optMeanWeight,
            setMeanWeight: setOptMeanWeight,
            defaultFreq: measFreq,
          }}
          optPaceMs={optPaceMs}
          kept={keptReadout}
          optState={{
            marked: optMarked,
            restarted: optRestarted,
            menuOpen: optMenuOpen,
            menuPaused: optMenuPaused,
            setMenuOpen: setOptMenuOpen,
          }}
        />


        <h2 className="group-label">simulation</h2>

        {/* The pair every solve and chart runs on (AK#1854): the solver and
            ground strips below are chosen independently, never by column. */}
        <p className="solve-pair" data-testid="solve-pair">
          {solvePairLabel(
            activeSlot,
            backend,
            currentOpts,
            activeGround,
            soilPresets,
          )}
        </p>
        {pairRefusal && groundWayOut && (
          <p className="solve-pair-refusal" role="alert" data-testid="solve-pair-refusal">
            {pairRefusal}
            <button type="button" onClick={groundWayOut.go}>
              {groundWayOut.label}
            </button>
          </p>
        )}

        <SolverSlotTabs
          slots={slots}
          activeSlot={activeSlot}
          onSelect={setActiveSlot}
          onOpenGear={setGearOpen}
          backend={backend}
          currentOpts={currentOpts}
          nPerWire={nPerWire}
          fixedSegmentCounts={currentExample?.fixed_segment_counts ?? false}
          nextSlot={nextSlot}
          onAdd={addSlot}
          design={designConstraintInputs}
        />

        <GroundSlotTabs
          slots={groundSlots}
          activeSlot={activeGroundSlot}
          onSelect={setActiveGroundSlot}
          onOpenGear={setGroundGearOpen}
          soilPresets={soilPresets}
          backend={backend}
          nextSlot={nextGroundSlot}
          onAdd={() => {
            // The new slot opens its settings, as a new solver slot does
            // (AK#1801): a copy is the start of "one change".
            if (nextGroundSlot === null) return;
            addGroundSlot();
            setGroundGearOpen(nextGroundSlot);
          }}
        >
          {/* The notices stay in view with the settings closed (AK#1801):
              they explain a ground the user did not choose. The design's own
              ground is ground slot X's (AK#1794), so its notices belong to
              that slot, not to free space in slot Y. */}
          <GroundNotices
            compact
            backend={backend}
            groundEnabled={groundEnabled}
            groundRequirement={
              onDesignGround ? (currentExample?.ground_requirement ?? null) : null
            }
            groundSeed={onDesignGround ? (currentExample?.ground_seed ?? null) : null}
            groundMedium={currentExample?.ground_medium ?? null}
            groundCard={currentExample?.ground_card ?? null}
          />
        </GroundSlotTabs>

        {keeping && (
          <KeepDialog
            {...keeping}
            canSave={canSaveStudies}
            onClose={() => setKeeping(null)}
            onSaved={() => setStudiesNonce((n) => n + 1)}
          />
        )}
        {(() => {
          // The open ⚙'s slot: its own values and setters, whichever slot
          // is active (AK#1801).
          const g = groundGearOpen === null ? null : groundSlotSettings(groundGearOpen);
          if (!g) return null;
          const onDesign = g.slot.id === designGroundSlot;
          return (
            <GroundConfigModal
              slotId={g.slot.id}
              label={groundSlotLabel(g.slot, soilPresets, backend)}
              onClose={() => setGroundGearOpen(null)}
              backend={backend}
              groundEnabled={g.slot.enabled}
              setGroundEnabled={g.setGroundEnabled}
              groundType={g.slot.type}
              setGroundType={g.setGroundType}
              finiteGroundMethod={g.slot.method}
              setFiniteGroundMethod={g.setFiniteGroundMethod}
              terrainPresets={terrainPresets}
              terrainPreset={g.slot.terrainPreset}
              setTerrainPreset={g.setTerrainPreset}
              terrainParams={g.slot.terrainParams}
              setTerrainParams={g.setTerrainParams}
              soil={g.slot.soil}
              setSoil={g.setSoil}
              soilPresets={soilPresets}
              soilRanges={soilRanges}
              groundRequirement={
                onDesign ? (currentExample?.ground_requirement ?? null) : null
              }
              groundSeed={onDesign ? (currentExample?.ground_seed ?? null) : null}
              groundMedium={currentExample?.ground_medium ?? null}
              groundCard={currentExample?.ground_card ?? null}
              // The active slot's notices are already on screen, under
              // the tab strip.
              notices={g.slot.id !== activeGroundSlot}
              remove={
                GROUND_SLOTS.ids.indexOf(g.slot.id) < GROUND_SLOTS.stock
                  ? undefined
                  : {
                      refusal: groundSlotRemovalRefusal(g.slot.id),
                      onRemove: () => {
                        removeGroundSlot(g.slot.id);
                        setGroundGearOpen(null);
                      },
                    }
              }
            />
          );
        })()}

        {gearOpen && (
          <BackendConfigModal
            slot={gearOpen}
            backend={slots[gearOpen].backend}
            backends={roster}
            requiredBackends={requiredBackends}
            design={designConstraintInputs}
            restrictionReason={
              currentExample?.backend_restriction?.reason ?? null
            }
            backendCoverage={currentExample?.backend_coverage ?? null}
            specs={modelOptionSpecs}
            vocab={compositionVocab}
            designRefusalNote={optionRefusal}
            fixedSegmentCounts={currentExample?.fixed_segment_counts ?? false}
            suggestConvergedFeed={
              currentExample?.converged_feed_suggested ?? false
            }
            densityNote={densityNotes[gearOpen]}
            opts={slots[gearOpen].opts}
            onChangeBackend={(b) => {
              backendTouchedRef.current = true;
              setSlotBackend(gearOpen, b);
            }}
            onPatch={(patch) => updateSlotOpts(gearOpen, patch)}
            onReset={() => resetSlot(gearOpen)}
            onClose={() => setGearOpen(null)}
            remove={
              SOLVER_SLOTS.ids.indexOf(gearOpen) < SOLVER_SLOTS.stock
                ? undefined
                : {
                    refusal: slotRemovalRefusal(gearOpen),
                    onRemove: () => removeSlot(gearOpen),
                  }
            }
          />
        )}
    </>
  );

  const solveOverlays = (
    <SolveOverlays
      showBusy={showBusy}
      solving={solving}
      onCancelSolve={() => {
        // AK#1712: the server stops the live solve and every batch on this
        // session's lane; the client drops its batch streams and dwells too.
        cancelSolve();
        abortAllInFlight();
      }}
      solverWarning={solverWarning}
      backendDisallowed={backendDisallowed}
      backend={backend}
      roster={roster}
      requiredBackends={requiredBackends}
      aliases={backendAliases}
      optionRefusal={optionRefusal}
      groundRefusal={
        pairRefusal && groundWayOut
          ? { reason: pairRefusal, wayOut: groundWayOut.label, onWayOut: groundWayOut.go }
          : null
      }
      onSwitchBackend={(target) => {
        backendTouchedRef.current = true;
        setSlotBackend(activeSlot, target);
      }}
      onPause={pauseSimulation}
      recommendedBackend={recommendedBackend}
      onSolveAnyway={solveAnyway}
      solveError={solveError}
    />
  );

  // Is what's on the stage describing something other than what the numbers
  // say? Two independent causes, same honest answer — dim it (#773).
  //
  //  - a solve is in flight (`stale` from the channel): the old answer is
  //    still up while a new one computes;
  //  - an optimizer run is in flight: the knobs are untouched until it
  //    finishes, so every pre-run view keeps describing the pre-run design
  //    while the readout ticks through candidates. Per view, because the
  //    Smith chart follows the run live and the schematic stays accurate —
  //    dimming those would be the same lie in the other direction.
  // The session's readiness, as a DOM signal tests wait on (the harness's
  // sessionReady): the design's load path has settled — the catalog holds
  // it, its design-load resets have run, its preview has landed and released
  // the solve gate, and the solve effect has acted on that release (solved,
  // withheld behind a gate, or warned) — for this reload generation. ""
  // until then.
  // Read from the same state the product gates on, so a wait on it is a wait
  // on the cause, not on a clock.
  const sessionReadyKey =
    currentExample &&
    previewReady === geometry &&
    previewNonce === reloadNonce &&
    loadSettledFor === `${geometry}#${reloadNonce}`
      ? `${geometry}#${reloadNonce}`
      : "";

  // What the readout shows (AK#1796): the result, but only while it was
  // solved for the ground and engine the controls ask for now. A ground or
  // engine change re-solves, and until that solve lands the result on
  // screen is the previous ground's: its R, X and SWR beside the current
  // ground's radiated % (the norm check follows the controls) read as
  // current and are not. So the readout shows "—" for that window instead,
  // whichever view is the main one. The views themselves keep drawing the
  // last result (dimmed by the busy chrome) — a pattern that morphs is
  // readable; a number next to another ground's number is not.
  const readoutResult =
    shownResult && resultSolvedFor === groundEngineSignature(buildRequest())
      ? shownResult
      : null;

  // The analysis chart a view is (the first chart's `zparam`, or a
  // duplicate's), or null.
  const chartOfView = (v: View): ChartModel | null => {
    const i = chartIndex(v);
    return i >= 0 ? chartModels[i] : null;
  };
  // A chart's knob sweep on its R/X plot has no trace-only dimming, so
  // while an optimizer run proposes points it dims whole, as the
  // Z-vs-parameter view did; every other view of a chart dims only its
  // swept curves (chartUi's trace stale rule) and keeps the live point bright.
  const rxShown = (m: ChartModel | null) =>
    !!m && m.state.kind === "knob" && m.state.knob.view === "Rx";
  // An R/X plot of either kind (R solid and X dashed per curve, the left
  // axis a readout would cover), or the Table (step 5 unit 5), which a
  // floating readout would cover too.
  const rxPlot = (m: ChartModel | null) => !!m && chartView(m.state) === "Rx";
  const coveredByReadout = (m: ChartModel | null) =>
    rxPlot(m) || (!!m && chartView(m.state) === "Table");
  const staleWhileOptimizing = (v: View) =>
    VIEW_META[v].staleWhileOptimizing || rxShown(chartOfView(v));
  const outputStale = stale || (optRunning && staleWhileOptimizing(view));
  // The stage readout's minimized default: a chart's depends on its view
  // (open on the Smith / Swr / S11 views as on the old Smith view, minimized
  // on the R/X plot, whose left axis it would cover). A duplicate reads and
  // writes the chart's own preference (lib/view.ts prefView): nothing about
  // a duplicate is stored.
  const readoutFallback = (v: View) =>
    chartIndex(v) >= 0 ? coveredByReadout(chartOfView(v)) : undefined;

  // Views that take the whole stage rather than a size×size square: the
  // antenna canvas, the Files view's text pane (AK#1428), which a square
  // would crop to a narrow column of a wide printout, and the schematic
  // (AK#1682) — a feed chain is wide and short, and fitting one into the
  // square shrank its labels to a few pixels.
  const fillsStage = (v: View) =>
    v === "antenna" || v === "files" || v === "schematic";

  // One output view: the per-view overlays plus the main <ViewPanel>. A
  // closure (not a component) so the ~30 captured locals need no props. The
  // solve-readout HUD is passed IN only by the rail's slide — mobile chart
  // screens must not inherit the floating readout, and the grid floats one
  // over the whole stage.
  // The combined view's highlight as drawn: stale ids (a pin since removed or
  // hidden) dropped, so neither the chart nor the table can show a highlight
  // that no row can switch off.
  const shownPins = pinnedPatterns.filter((p) => p.enabled);
  const shownHighlight = effectiveHighlight(combinedHighlight, shownPins);

  // Duplicate a chart (unit 4): the first free place of the four gets a
  // copy of it, pick, switch, ranges, views and cross, with runners of its
  // own, which are asked for what it shows (as a pick asks). It goes on
  // the stage, and in the grid the charts take the cells first
  // (useViewPrefs' gridCells). Session-only, like everything a chart holds.
  const duplicateChart = (i: number) => {
    const free = charts.findIndex((c) => c === null);
    const src = charts[i];
    if (free < 0 || !src) return;
    setCharts((cs) => cs.map((c, k) => (k === free ? src : c)));
    const ctl = chartControl(free);
    ctl.armFreq();
    ctl.armParam();
    ctl.armPattern();
    setView(CHART_VIEW_IDS[free]);
  };
  // A view left on a closed duplicate (a click that closed it can bubble to
  // its grid cell, which focuses it again) moves to the first chart.
  // State adjusted during render, React's pattern for state derived from
  // other state.
  if (chartIndex(view) > 0 && !charts[chartIndex(view)]) setView("zparam");
  // Close a duplicate: its curves stop and its place is free again.
  const closeChart = (i: number) => {
    if (i === 0) return;
    const ctl = chartControl(i);
    ctl.stopFreq();
    ctl.stopParam();
    ctl.stopPattern();
    setCharts((cs) => cs.map((c, k) => (k === i ? null : c)));
    if (view === CHART_VIEW_IDS[i]) setView("zparam");
  };

  // A pinned sweep's context label (AK#1757 item 1, lib/sweepPins.ts
  // pinLabel): the cell's design and variant, its slot's engine, its ground
  // slot, the knobs that differ from the design's defaults (not the one the
  // chart sweeps; a family step's value), and its plane. Another design's
  // cell is solved at that design's defaults (designAtDefaults), so it has
  // no changed knobs but its step.
  const pinContext = (c: ChartCell, swept: string | null): string => {
    const other = c.design !== undefined && c.design !== geometry;
    const cfg = c.slot !== null ? slots[c.slot as Slot] : undefined;
    const g = groundSlots.find((x) => x.id === c.ground);
    // A state cell's knobs are the state's, over the defaults (step 7); a
    // group knob's value (unit 4) reads as "set", having no one word.
    const knobs: [string, ScalarKnob][] = c.state
      ? Object.entries(c.state.knobs)
          .filter(([k]) => k !== swept)
          .map(([k, v]: [string, KnobValue]): [string, ScalarKnob] => [k, Array.isArray(v) ? "set" : v])
      : other
        ? []
        : changedKnobs(currentValues, knobDefaults(), swept);
    if (c.step && c.step.knob !== swept) {
      const at = knobs.findIndex(([k]) => k === c.step!.knob);
      if (at >= 0) knobs[at] = [c.step.knob, c.step.value];
      else knobs.push([c.step.knob, c.step.value]);
    }
    return pinLabel({
      design: c.design ?? geometry,
      variant:
        c.state?.variant ??
        (other ? (examples.find((e) => e.name === c.design)?.variants?.[0] ?? null) : currentVariant),
      engine: cfg ? backendDisplayLabel(cfg.backend, cfg.opts) : "",
      ground: g ? groundSlotLabel(g, soilPresets ?? []) : "",
      knobs,
      plane: c.plane ?? (other ? null : plane),
    });
  };

  // Everything one chart shows and does (AK#1757 step 5 units 2 to 4): its
  // header (the picker, Run and the dwell switch on every kind, the engine
  // and ground checkboxes, duplicate / close, and the kind's own inputs — a
  // knob sweep's parameter, range and points, or a frequency analysis's view
  // and range), its advisory overlays, and the props its view draws from:
  // its first curve as the chart always drew it, the other curves beside
  // it, and the legend naming every cell.
  const chartUi = (m: ChartModel) => {
    const i = m.i;
    const runners = runnersOf(m);
    const own = runners[0] ?? null;
    const ctl = chartControl(i);
    const setAt = (f: (c: AnalysisChartState) => AnalysisChartState) => setChartAt(i, f);
    const pickedNow = pickedNameOf(m);
    // The picked knob analysis's own range, while the chart still runs it
    // (what ↺ goes back to), else null.
    const pickedSpec =
      pickedName(m.now) !== null && m.now.picked?.kind === "knob" ? (m.now.picked.spec ?? null) : null;
    const analyses = {
      entries: zparamAnalyses,
      current: pickedNow,
      edited: pickedEdited(m.now),
      blocked: zparamAnalysisBlocked,
      onPick: (e: AnalysisEntry) => pickAnalysis(i, e),
      // The picker's first entry: the design's own frequency sweep (a new
      // chart's), and its "Sweep a knob" group, which runs the knob as the
      // knob menu's "Sweep this knob…" does (the same path, sweepKnob).
      own: m.state.kind === "frequency" && m.state.picked === null,
      onPickOwn: () => {
        ctl.armFreq();
        setAt((c) => pickOwnFrequency(c, chartSeed));
      },
      ...(zparamKnobs.length > 0 ? { onSweepKnob: () => sweepKnob(knobToSweep(m), i) } : {}),
      // A knob's family of patterns (AK#1935) is still "Sweep a knob".
      sweepingKnob: (m.state.kind === "knob" || chartFamily(m.state)) && pickedNow === null && !m.isDensity,
    };
    // A tick is asking for the curves it adds or moves: arm the runners
    // whose cell changes, and only those, so an unchanged curve neither
    // re-runs nor carries an ask over to some later change.
    const setCross = (cross: ChartCross) => {
      const next: AnalysisChartState = { ...m.now, cross };
      const cells = planOf(cross, listedFor(next)).cells.filter(drawable);
      const all = allRunnersOf[i];
      cells.forEach((c, k) => {
        if (m.drawn[k]?.key !== c.key) {
          all[k]?.freq.arm();
          all[k]?.param.arm();
          all[k]?.pattern.arm();
          all[k]?.map.arm();
        }
      });
      setAt((c) => ({ ...c, cross }));
    };
    // Pinned sweeps (AK#1757 item 1). What this chart sweeps (null on the
    // Table, which draws against no x), the reference its SWR and S11 are
    // drawn at (ChartFrequency's live point's), and its drawn curves as
    // pins would hold them: one per curve (ruling 1).
    const isFreq = m.state.kind === "frequency";
    // A pattern (AK#1757 step 7) draws against no x: no sweep pin places on
    // it, and its own cells are not sweep pins (keeping them is unit 4's
    // "keep as study").
    const isPattern = m.state.kind === "pattern";
    // A map (docs/design/sweep-framework-map.md) draws no curve either: no
    // sweep pin places on it, and it pins nothing in v1 (decision 11).
    const isMap = m.state.kind === "map";
    const knobUnit = m.isDensity ? null : (m.knob?.unit ?? null);
    const chartX: ChartX | null =
      chartView(m.state) === "Table" || chartView(m.state) === "Metric" || isPattern || isMap
        ? null
        : isFreq
          ? { x: FREQUENCY_X, lo: m.inputs.freq.range.lo, hi: m.inputs.freq.range.hi }
          : {
              x: knobX(m.spec.param, m.label, knobUnit),
              lo: Math.min(...m.values),
              hi: Math.max(...m.values),
            };
    const chartZ0 = shownResult?.z0_ohms ?? z0;
    const pinnable: PinnableCurve[] = m.drawn.flatMap((c, k) => {
      const r = runners[k];
      if (!r || isPattern || isMap) return [];
      const cell = m.drawn.length > 1 ? c.label : "";
      const design = c.design ?? geometry;
      // The request the curve was solved with: what "keep as study" keeps
      // (AK#1757 step 7 unit 4, lib/keep.ts).
      const req = keepRequest(buildCellRequest(m.runs[k].cell));
      if (isFreq) {
        const sw = r.freq.sweep;
        return sw && sw.freqs_mhz.length > 0
          ? [{ xs: sw.freqs_mhz, zRe: sw.z_re, zIm: sw.z_im, x: FREQUENCY_X, label: pinContext(c, null), cell, design, req }]
          : [];
      }
      const d = r.param.data;
      if (!d || d.error || d.param !== m.runs[k].param.req.param || d.values.length === 0) return [];
      const x = d.param === m.spec.param ? knobX(d.param, m.label, knobUnit) : knobX(d.param, d.label, null);
      // A held curve's pin carries its hold (step 6): its Z at each x is the
      // optimum's, which a study keeping it must re-solve the same way.
      const held = m.runs[k].param.req.hold;
      const pinReq = held ? { ...req, hold: held.spec } : req;
      return [{ xs: d.values, zRe: d.z_re, zIm: d.z_im, x, label: pinContext(c, d.param), cell, design, req: pinReq }];
    });
    // Pin snapshots the curves as they stand, so not while any is still
    // moving (a run, a refinement, or a dwell about to re-run), refused, or
    // of inputs since changed (its label would name the knobs as they are
    // now, not as the curve was solved).
    const pinBlocked: string | null = runners.some((r) =>
      isFreq ? r.freq.running || r.freq.phase !== "idle" : r.param.running || r.param.phase !== "idle",
    )
      ? "A run is in flight: pin once it has finished"
      : m.plan.capRefusal !== null ||
          m.plan.cells.some((c) => c.refused) ||
          runners.some((r) => (isFreq ? r.freq.error : r.param.data?.error))
        ? "A curve is refused: only a chart whose every curve draws can be pinned"
        : runners.some((r) => (isFreq ? r.freq.stale : !!r.param.data?.stale))
          ? "The curves are stale: run them again, then pin"
          : pinnable.length === 0
            ? "Nothing drawn yet to pin"
            : pinnable.length < m.drawn.length
              ? "Not every curve has landed yet"
              : null;
    // Every pin in the session is listed; the enabled ones whose x matches
    // this chart's draw here, cut to its range (placePin).
    const pinRows: ChartLegendPin[] = sweepPins.map((p) => {
      const at = placePin(p, chartX);
      return {
        id: p.id,
        label: p.label,
        cell: p.cell,
        color: sweepPinColor(p.colorIdx),
        enabled: p.enabled,
        reason: at.drawable ? null : at.reason,
        z0Note: z0Note(p.z0, chartZ0),
        onToggle: () => toggleSweepPin(p.id),
        onDelete: () => removeSweepPin(p.id),
        onCsv: () => saveTextFile(pinCsv(p), pinCsvName(p, p.id)),
      };
    });
    // "Keep as study" for the pins shown here (AK#1757 step 7 unit 4): the
    // enabled pins this chart draws, each the request its curve was solved
    // with, what it sweeps and at which x (lib/keep.ts).
    const drawnPins = sweepPins.filter((p) => p.enabled && placePin(p, chartX).drawable);
    const pinKeeps: SweepPinKeep[] = drawnPins.flatMap((p) =>
      p.req ? [{ req: p.req, x: { kind: p.x.kind, name: p.x.name }, xs: [...p.xs], label: p.label }] : [],
    );
    const keepPinsBlocked =
      drawnPins.length === 0
        ? "No shown pin draws on this chart: show one to keep it"
        : pinKeeps.length < drawnPins.length
          ? "A shown pin has no solve request to keep: pin it again"
          : sweepPinsBlocked(pinKeeps, CURVE_CAP);
    const keepPins = () =>
      setKeeping({
        title: "Keep pins as study",
        body: { origin: "sweep pins", form: "study", pins: pinKeeps },
        initialName: "pinned sweeps",
      });
    const chartPins: PinCurve[] = sweepPins.flatMap((p) => {
      if (!p.enabled) return [];
      const at = placePin(p, chartX);
      return at.drawable ? [pinCurve(p, at.idx, sweepPinColor(p.colorIdx))] : [];
    });
    // Keeping this chart (AK#1757 step 7 unit 4, lib/keep.ts): the picked
    // analysis as /analyses served it, the tab's own request, the requests
    // its curves were solved with (the engines and grounds it draws: always
    // for a study, which should re-solve what is drawn; for a copy only when
    // the viewer ticked slots, so an analysis naming no engine stays so), and
    // its x values when the viewer edited the range.
    const keepPicked = pickedNow !== null ? (zparamAnalyses.find((a) => a.name === pickedNow) ?? null) : null;
    // A knob's family of patterns (AK#1935) is no picked analysis: it keeps
    // as the family it draws, `an.patterns(cross=an.Cross(step=an.Sweep(
    // knob, lo, hi, points=n)))` (keep.analysis_from_family), with the
    // values it solved so an int knob's rounded ladder is kept exactly.
    const familyNow = chartFamily(m.now);
    const noPick =
      "Pick an analysis first: the chart's own sweep is not one (pin its curves to keep them)";
    const copyBlocked =
      keepPicked?.study || (keepPicked?.workbench.runs && keepPicked.workbench.axes?.includes("designs"))
        ? "This chart compares named designs: keep it as a study"
        : null;
    // An edited map writes each edited axis back as a range (decision 12),
    // never as a list of the values it solved.
    const mapNow = isMap ? (m.now.map ?? null) : null;
    const mapAxes =
      mapNow && pickedEdited(m.now)
        ? mapAxesKeep({
            x: mapNow.x,
            y: mapNow.y,
            edited: { x: !sameSpec(mapNow.x, mapNow.served.x), y: !sameSpec(mapNow.y, mapNow.served.y) },
          })
        : null;
    const editedValues: number[] | null = !pickedEdited(m.now) || isMap
      ? null
      : m.state.kind === "knob"
        ? [...m.inputs.param.req.values]
        : (own?.freq.sweep?.freqs_mhz.slice() ?? []);
    const keepValuesBlocked =
      editedValues !== null && editedValues.length === 0
        ? "Run the edited range first: a study keeps the points it solved"
        : null;
    const openChartKeep = (form: "analysis" | "study") => {
      const ticked = m.now.cross.slots !== null || m.now.cross.grounds !== null;
      if (familyNow) {
        setKeeping({
          title: form === "analysis" ? "Copy as analysis" : "Keep as study",
          body: {
            origin: "chart",
            form,
            spec: null,
            family: {
              knob: m.spec.param,
              lo: m.spec.lo,
              hi: m.spec.hi,
              points: m.spec.points,
              spacing: m.spec.log ? "log" : "lin",
              values: [...m.values],
              // The cuts it draws at (AK#1950): a kept family writes the
              // angles the chart drew, not an.patterns()'s own.
              views: [...familyPatternViews(m.now)],
            },
            tab: keepRequest(buildRequest()),
            ...(form === "study" || ticked
              ? { cells: m.runs.map((r) => keepRequest(buildCellRequest(r.cell))) }
              : {}),
          },
          initialName: `patterns over ${m.spec.param === FAMILY_FREQ ? "frequency" : m.spec.param}`,
        });
        return;
      }
      if (!keepPicked) return;
      const body: KeepBody = {
        origin: "chart",
        form,
        spec: keepPicked.spec ?? null,
        tab: keepRequest(buildRequest()),
        ...(form === "study" || ticked
          ? { cells: m.runs.map((r) => keepRequest(buildCellRequest(r.cell))) }
          : {}),
        ...(editedValues ? { values: editedValues } : {}),
        ...(mapAxes ? { axes: mapAxes } : {}),
      };
      setKeeping({
        title: form === "analysis" ? "Copy as analysis" : "Keep as study",
        body,
        initialName: keepPicked.study?.name ?? keepPicked.name,
      });
    };
    const chrome: ChartChrome = {
      dwell: m.dwellOn,
      onDwell: (on: boolean) => setAt((c) => ({ ...c, dwell: on })),
      cross: {
        slots: crossEnv.slots.map(({ id, label }) => ({ id, label })),
        grounds: crossEnv.grounds.map(({ id, label }) => ({ id, label })),
        checkedSlots: checkedSlots(m.now.cross, crossEnv),
        checkedGrounds: checkedGrounds(m.now.cross, crossEnv),
        onSlots: (ids: string[]) => setCross({ ...m.now.cross, slots: ids }),
        onGrounds: (ids: string[]) => setCross({ ...m.now.cross, grounds: ids }),
        refusal: m.plan.capRefusal,
      },
      ...(isPattern
        ? {}
        : isMap
          ? { pin: { onPin: () => {}, blocked: MAP_PIN_BLOCKED } }
          : { pin: { onPin: () => addSweepPins(pinsFromCurves(pinnable, chartZ0)), blocked: pinBlocked } }),
      keep: {
        onCopy: () => openChartKeep("analysis"),
        copyBlocked: familyNow ? m.plan.capRefusal : keepPicked ? copyBlocked : noPick,
        onKeep: () => openChartKeep("study"),
        keepBlocked: familyNow ? m.plan.capRefusal : keepPicked ? keepValuesBlocked : noPick,
      },
      onCopyLink: () => copyChartLink(m),
      ...(charts.some((c) => c === null) ? { onDuplicate: () => duplicateChart(i) } : {}),
      ...(i > 0 ? { onClose: () => closeChart(i) } : {}),
    };
    const freqState = m.state.kind === "frequency" ? m.state.frequency : null;
    const f0 = own?.freq ?? null;
    const p0 = own?.param ?? null;
    // A swept curve is of inputs since changed: the dwell switch off and the
    // knobs moved, or (on the SWR and S11 views, which dimmed whole while an
    // optimizer run proposed points, #773) a run the curve predates. Only
    // the curves dim (unit 3); the live point follows either way. The Smith
    // view never dimmed during a run, and still does not.
    const runStale = optRunning && freqState?.view !== "Smith";
    // The first curve, on the chart's view, with its own scales
    // (viewRegistry's chart entry).
    const freqRender: ChartFrequencyRender | null = freqState && {
      view: freqState.view,
      sweep: f0?.sweep ?? null,
      running: runners.some((r) => r.freq.running),
      phase: f0?.phase ?? "idle",
      progress: f0?.progress ?? null,
      settled: f0?.settled ?? true,
      stale: (f0?.stale ?? false) || runStale,
      axes: freqState.axes,
      threshold: freqState.threshold,
      rx: {
        r: frequencyRx(freqState).r,
        x: frequencyRx(freqState).x,
        // Follow the range's spacing until the viewer flips it.
        xLog: frequencyRx(freqState).xLog ?? m.inputs.freq.range.spacing === "log",
      },
    };
    // A knob analysis's MetricPlot (AK#1828), and each cell's caption: a
    // reference of a relative plot named as one (AK#1867) in the legend,
    // the Table's column groups and the plot's own curves alike.
    const metricSpec = chartMetric(m.now);
    const listedHere = listedFor(m.now, m.values);
    const caption = (c: ChartCell) =>
      metricCaption(c.label, metricSpec, !!servedCell(c, listedHere)?.reference);
    // The other curves, in their legend colours.
    const curves: ExtraCurve[] = runners.slice(1).map((r, k) => ({
      key: m.drawn[k + 1].key,
      color: cellColor(k + 1),
      sweep: freqState ? r.freq.sweep : null,
      settled: r.freq.settled,
      stale: freqState ? r.freq.stale || runStale : !!r.param.data?.stale,
      paramSweep:
        m.state.kind === "knob" && r.param.data?.param === m.runs[k + 1].param.req.param
          ? r.param.data
          : null,
    }));
    // Every cell by name, in the cross's order; a refused one with why.
    const legend: ChartLegendData = {
      entries: m.plan.cells.map((c) => {
        if (c.refused) return { key: c.key, label: caption(c), color: null, refused: c.refused };
        const k = m.drawn.indexOf(c);
        const r = runners[k];
        const error = isPattern
          ? (r?.pattern.data?.error ?? null)
          : freqState
            ? r?.freq.error
            : (r?.param.data?.error ?? null);
        // The engine declining this cell's design (NEC-2 and a vertex feed)
        // is a refused cell, in the server's words, as the CLI names it.
        const declined = engineRefusal(error);
        if (declined) return { key: c.key, label: caption(c), color: null, refused: declined };
        return { key: c.key, label: caption(c), color: cellColor(k), refused: null, error: error ?? null };
      }),
      capRefusal: m.plan.capRefusal,
      // The listed engines no slot holds, skipped rather than refused
      // (Steve, 2026-10-01), named in a muted note.
      // ...and, when one ground slot is solved as different ground models
      // across the curves' engines (NEC-5 has no refl-coef), says so (AK#1854).
      // ...and, while the ticks are still the ones a pick made, which slots
      // the analysis ticked and why (AC6LA, QRZ: "how is it that free space
      // got added as a ground type?").
      note:
        [
          skippedNote(m.plan),
          pickNote(m.now.cross, listedHere, crossEnv),
          mixedGroundNote(
            m.plan.cells.filter((c) => !c.refused),
            (id) => slots[id]?.backend,
            (id) => groundSlots.find((g) => g.id === id),
          ),
        ]
          .filter(Boolean)
          .join(" ") || null,
      // A map draws no pin (decision 11): its legend lists none over it.
      ...(pinRows.length > 0 && !isMap
        ? { pins: pinRows, pinsRx: rxPlot(m), onKeepPins: keepPins, keepPinsBlocked }
        : {}),
      // R solid and X dashed per curve holds only with more than one live
      // curve; one draws R red and X blue (ZParamChart), and a pin can now
      // show the legend over a one-curve chart.
      rx: rxPlot(m) && m.drawn.length > 1,
      // Collapsed to its chip on a phone until the viewer opens it, open on
      // a desktop (Steve's phone review of unit 4a), as the knob sweep's
      // value boxes are (chartCallouts); per chart, session-only, and a
      // duplicate starts from its source's.
      open: m.state.legendOpen ?? !isMobile,
      onOpen: (open: boolean) => setAt((c) => ({ ...c, legendOpen: open })),
    };
    const setFrequency = (patch: Partial<NonNullable<AnalysisChartState["frequency"]>>) =>
      setAt((c) => (c.frequency ? { ...c, frequency: { ...c.frequency, ...patch } } : c));
    // A view pick. A pattern view on a knob chart turns it into that knob's
    // family of patterns (AK#1935): a pick, which runs as
    // [workbench.run_on_pick]'s `pattern` says (off: it waits for Run). Off
    // a family over the frequency onto a knob view, the knob sweep cannot
    // sweep the frequency: it sweeps the last knob swept (else the first).
    const onChartView = (v: ChartView) => {
      const pattern = v.startsWith("pattern:");
      if (pattern && m.state.kind === "knob") {
        const next = setChartView(m.state, v);
        if (next === m.state) return;
        (runOnPick.pattern ? runPicked : holdPicked)(i, "pattern", next, false);
        setAt(() => next);
        return;
      }
      if (!pattern && chartFamily(m.state) && m.state.knob.spec.param === FAMILY_FREQ) {
        const k = zparamKnobs.find((z) => z.name === lastKnob)?.name ?? zparamKnobs[0]?.name ?? DENSITY;
        setAt((c) => setChartView(c, v));
        setZparamSpecAt(i, zparamDefaultFor(k));
        return;
      }
      setAt((c) => setChartView(c, v));
    };
    // The chart's view (Rx / Swr / S11 / Smith, as many as its kind can
    // draw), and on the Smith chart the measured .s1p overlay the Smith view
    // carried (issue #595): chart controls, on the chart (unit 3).
    const viewPick = {
      views: chartViews(m.state),
      view: chartView(m.state),
      onView: (v: ChartView) => onChartView(v),
      // A knob chart offers its family's pattern views (AK#1935) before it
      // holds any pattern of its own.
      ...(m.state.pattern && m.state.kind === "pattern"
        ? { patternViews: m.state.pattern.views }
        : { patternViews: familyPatternViews(m.state) }),
      measured:
        chartView(m.state) === "Smith"
          ? {
              data: measured,
              onLoad: (f: File) => loadMeasured(f, { setGearMenuOpen, setMeasured }),
              onClear: () => setMeasured(null),
            }
          : null,
    };
    // Scale and threshold edits on the chart are the viewer's preference as
    // well, as they were on the standalone VSWR / S11 views (AK#1738): they
    // seed the next chart. A pick's own scale is not (pickFrequency).
    const onAxisChange = (mode: SweepMode, c: SweepAxisChoice) => {
      if (!freqState) return;
      setFrequency({ axes: { ...freqState.axes, [mode]: c } });
      setSweepAxis(mode, c);
    };
    const onThresholdChange = (t: number) => {
      setFrequency({ threshold: t });
      setSwrThreshold(t);
    };
    // The R/X view's ranges and x axis: the chart's own (never stored).
    const onRxAxisChange = (axis: "r" | "x", c: RxAxisChoice) => {
      if (!freqState) return;
      setFrequency({ rx: { ...frequencyRx(freqState), [axis]: c } });
    };
    const onRxXLogChange = (log: boolean) => {
      if (!freqState) return;
      setFrequency({ rx: { ...frequencyRx(freqState), xLog: log } });
    };
    const range = m.inputs.freq.range;
    const patternRunning = runners.some((r) => r.pattern.running);
    // A family's cut on screen (AK#1950), which its angle box edits.
    const familyCut = chartFamily(m.state) ? chartPatternView(m.state) : null;
    // The map (docs/design/sweep-framework-map.md, unit 3): its one grid is
    // the first cell's, on the slot and ground the radios pick.
    const mapState = isMap ? (m.state.map ?? null) : null;
    const mapRun = isMap ? (runners[0]?.map ?? null) : null;
    const mapData = mapRun?.data ?? null;
    const mapTotal = m.inputs.map.x.values.length * m.inputs.map.y.values.length;
    const knobLabel = (k: string) => zparamKnobs.find((z) => z.name === k)?.label ?? k;
    const mapStatus = !mapState
      ? null
      : mapData?.error
        ? "map refused — see the note"
        : mapData?.stale
          ? "stale — the design, solver or ground changed; re-run?"
          : mapData && mapData.timeLimitS !== undefined
            ? `${sweepTimeLimitNote({ stopped: "time", time_budget_s: mapData.timeLimitS })} — ${mapData.received}/${mapTotal}`
            : mapData?.partial
              ? `stopped at ${mapData.received}/${mapTotal} — partial`
              : mapRun?.running
                ? `solving ${mapData?.received ?? 0}/${mapTotal}…`
                : !mapData
                  ? "no map yet — run"
                  : null;
    const chartMap: ChartMapRender | null = mapState && {
      grid: mapData?.grid ?? emptyGrid(m.inputs.map.x.values, m.inputs.map.y.values),
      xLabel: knobLabel(mapData?.x.param ?? mapState.x.param),
      yLabel: knobLabel(mapData?.y.param ?? mapState.y.param),
      xLog: mapState.x.log,
      yLog: mapState.y.log,
      z0,
      refs: mapState.refs,
      quantity: mapState.quantity,
      live: (() => {
        const lx = currentValues[mapState.x.param];
        const ly = currentValues[mapState.y.param];
        if (typeof lx !== "number" || typeof ly !== "number") return null;
        return {
          x: lx,
          y: ly,
          re: optLiveZ?.z_in_re ?? shownResult?.z_in_re ?? null,
          im: optLiveZ?.z_in_im ?? shownResult?.z_in_im ?? null,
        };
      })(),
      status: mapStatus,
      stale: !!mapData?.stale,
    };
    const controls = isMap && mapState ? (
      <MapChartControls
        analyses={analyses}
        x={{ label: knobLabel(mapState.x.param), spec: mapState.x, values: m.inputs.map.x.values }}
        y={{ label: knobLabel(mapState.y.param), spec: mapState.y, values: m.inputs.map.y.values }}
        // An axis edit is asking for that map: arm it.
        onAxis={(axis, next) => {
          ctl.armMap();
          setAt((c) => editMapAxis(c, axis, next));
        }}
        onRestore={() => {
          ctl.armMap();
          setAt(restoreMapAxes);
        }}
        edited={pickedEdited(m.now)}
        quantity={mapState.quantity}
        // Z is z0-free: a new colouring re-colours, never re-solves.
        onQuantity={(q) => setAt((c) => (c.map ? { ...c, map: { ...c.map, quantity: q } } : c))}
        slots={{
          items: crossEnv.slots.map(({ id, label }) => ({ id, label })),
          checked: checkedSlots(m.now.cross, crossEnv)[0] ?? null,
          onPick: (id) => setCross({ ...m.now.cross, slots: [id] }),
        }}
        grounds={{
          items: crossEnv.grounds.map(({ id, label }) => ({ id, label })),
          checked: checkedGrounds(m.now.cross, crossEnv)[0] ?? null,
          onPick: (id) => setCross({ ...m.now.cross, grounds: [id] }),
        }}
        cost={{
          line: mapCostLine(mapTotal, freshSolveMs),
          refused: mapOverLimit(mapTotal, mapState.limit),
        }}
        run={{
          running: !!mapRun?.running,
          received: mapData?.received ?? 0,
          total: mapTotal,
          done: !!mapData?.done && !mapData.stale,
          partial: !!mapData?.partial,
          stale: !!mapData?.stale,
          onStop: ctl.stopMap,
          onRun: ctl.runMapNow,
        }}
        chrome={chrome}
      />
    ) : isPattern ? (
      <PatternChartControls
        analyses={analyses}
        viewPick={viewPick}
        run={{
          running: patternRunning,
          solved: runners.filter((r) => !!r.pattern.data?.result).length,
          total: runners.length,
          stale: runners.some((r) => !!r.pattern.data?.stale),
          // Over the curve cap nothing is drawn: Run says why (the legend
          // carries the same refusal).
          blocked: m.plan.capRefusal,
          onStop: ctl.stopPattern,
          onRun: ctl.runPatternNow,
        }}
        chrome={chrome}
        cut={
          // A family's cut angle (AK#1950), on its Elevation / Azimuth view.
          // A change re-cuts the solves in hand (the angles are exempt from
          // a cell's signature) and rides every later cell request.
          familyCut && cutAngle(familyCut) !== null
            ? {
                view: familyCut,
                onCut: (deg) => setAt((c) => setChartCut(c, deg)),
                peak: {
                  blocked: peakBlocked,
                  // The cut through the peak: its bearing for an elevation
                  // cut, its take-off angle (an.Azimuth's 1-89) for an
                  // azimuth cut. Applied to the view that asked, should the
                  // viewer have moved on while it was fetched.
                  onPeak: () => {
                    const asked = familyCut.view;
                    void peakNow().then((pk) => {
                      if (!pk) return;
                      const deg =
                        asked === "Elevation"
                          ? Math.round(pk.azimuth_deg)
                          : Math.min(89, Math.max(1, Math.round(pk.takeoff_deg)));
                      setAt((c) => (chartPatternView(c)?.view === asked ? setChartCut(c, deg) : c));
                    });
                  },
                },
              }
            : null
        }
        family={
          chartFamily(m.state)
            ? {
                spec: m.spec,
                knobs: familyKnobs,
                skipped: familySkipped,
                values: m.values,
                // An edit of the family's range is asking for it: arm it.
                onSpec: (next) => {
                  ctl.armPattern();
                  setZparamSpecAt(i, next);
                },
                onParam: (param) => {
                  if (param !== DENSITY && param !== FAMILY_FREQ) setLastKnob(param);
                  ctl.armPattern();
                  setZparamSpecAt(i, zparamDefaultFor(param));
                  setZparamXLogAt(i, null);
                },
                onReset: () => {
                  ctl.armPattern();
                  setZparamSpecAt(i, zparamDefaultFor(m.spec.param));
                },
                isDefault: sameSpec(m.spec, familySpec(zparamDefaultFor(m.spec.param))),
              }
            : null
        }
      />
    ) : freqState ? (
      <FrequencyChartControls
        analyses={analyses}
        viewPick={viewPick}
        range={range}
        // An edit to the chart's own range is asking for it: arm it.
        onRange={(lo, hi) => {
          const next = editRange(range, lo, hi);
          if (!next) return;
          ctl.armFreq();
          setFrequency({ rangeEdit: next });
        }}
        onResetRange={() => {
          ctl.armFreq();
          setFrequency({ rangeEdit: null });
        }}
        rangeIsOwn={freqState.rangeEdit === null}
        run={{
          running: runners.some((r) => r.freq.running),
          received: f0?.sweep?.freqs_mhz.length ?? 0,
          stale: runners.some((r) => r.freq.stale),
          onStop: ctl.stopFreq,
          onRun: ctl.runFreqNow,
        }}
        chrome={chrome}
      />
    ) : (
      <ZParamControls
        spec={m.spec}
        knobs={zparamKnobs}
        densityLabel="density (N per λ/4)"
        // An edit to the sweep's own range is asking for it: arm it.
        // Picking another parameter is not (a knob sweep waits for Run).
        onSpec={(next) => {
          ctl.armParam();
          setZparamSpecAt(i, next);
        }}
        onParam={(param) => selectZparamParam(i, param)}
        // ↺ goes back to the picked analysis's own range while one is
        // picked (pickedEdited: "the chart's ↺ restores the range"), not to
        // the knob's: from "height" it read "height (edited)" over base's
        // own 1–16 m with height's three grounds still ticked (AC6LA, QRZ).
        onReset={() => {
          ctl.armParam();
          if (pickedSpec) {
            setZparamSpecAt(i, pickedSpec);
            setZparamXLogAt(i, null);
          } else {
            selectZparamParam(i, m.spec.param);
          }
        }}
        isDefault={sameSpec(m.spec, pickedSpec ?? zparamDefaultFor(m.spec.param))}
        resetTitle={pickedSpec ? "Back to this analysis's own range" : undefined}
        values={m.values}
        run={{
          running: runners.some((r) => r.param.running),
          received: p0?.data?.param === m.spec.param ? p0.data.values.length : 0,
          partial: !!p0?.data?.partial,
          stale:
            runners.some((r) => !!r.param.data?.stale && r.param.data.param === m.spec.param),
          done:
            !!p0 &&
            !runners.some((r) => r.param.running) &&
            !!p0.data &&
            !p0.data.partial &&
            !p0.data.stale &&
            !p0.data.error &&
            p0.data.param === m.spec.param &&
            p0.data.values.length > 0,
          onStop: ctl.stopParam,
          onRun: ctl.runParamNow,
        }}
        costHint={costHintOf(m)}
        analyses={analyses}
        viewPick={viewPick}
        chrome={chrome}
      />
    );
    // The chart's sweep advisory and refusal: over the stage's lower-left on
    // a phone, over the plot's (above the readout) on a desktop.
    const p0data = p0?.data ?? null;
    // A pattern cell the poor-match gate withheld (the server's 403, as for
    // a sweep): its words, and the approval that re-runs it.
    const withheld = isPattern
      ? (runners.find((r) => r.pattern.data?.errorStatus === 403)?.pattern.data ?? null)
      : null;
    const mapNotes = mapData
      ? [
          ...(mapData.timeLimitS !== undefined
            ? [{ category: SWEEP_TIME_LIMIT, text: sweepTimeLimitNote({ stopped: "time", time_budget_s: mapData.timeLimitS })! }]
            : []),
          ...(mapData.failed > 0
            ? [
                {
                  category: "MapNodesFailed",
                  text: `${mapData.failed} node${mapData.failed === 1 ? "" : "s"} did not solve: ${mapData.firstError ?? ""}`,
                },
              ]
            : []),
        ]
      : [];
    const overlays = isMap ? (
      <>
        <SweepAdvisoryOverlay advisories={mapNotes} />
        {mapData?.error && (
          <div className="sweep-advisory-overlay zparam-refusal" role="alert">
            {mapData.error}
            {mapData.errorStatus === 403 && (
              <button type="button" className="zparam-approve" onClick={solveAnyway}>
                Solve anyway
              </button>
            )}
          </div>
        )}
      </>
    ) : isPattern ? (
      withheld && (
        <div className="sweep-advisory-overlay zparam-refusal" role="alert">
          {withheld.error}
          <button type="button" className="zparam-approve" onClick={solveAnyway}>
            Solve anyway
          </button>
        </div>
      )
    ) : freqState ? (
      <SweepAdvisoryOverlay advisories={f0?.advisories ?? []} />
    ) : (
      <>
        {p0data?.param === m.spec.param && (
          <SweepAdvisoryOverlay advisories={p0data.advisories} />
        )}
        {p0data?.error && (
          // The server's refusal (the hosted point cap, the poor-match
          // gate), in its own words: the header does not clamp to it.
          <div className="sweep-advisory-overlay zparam-refusal" role="alert">
            {p0data.error}
            {/* The poor-match gate's 403 is approvable, as for the live
                solve: the approval re-runs the sweep (comboApproved is
                one of its inputs). */}
            {p0data.errorStatus === 403 && (
              <button type="button" className="zparam-approve" onClick={solveAnyway}>
                Solve anyway
              </button>
            )}
          </div>
        )}
      </>
    );
    const zparam = {
      ...zparamSettingsOf(m),
      phase: p0?.phase ?? "idle",
      // The knob view on screen; the Metric view only while the analysis
      // that has a MetricPlot is still picked, the Knobs view only while its
      // hold is (lib/analysisChart chartView).
      view: m.state.kind === "knob" ? (chartView(m.now) as KnobView) : m.state.knob.view,
      callouts: chartCallouts,
    };
    // A knob analysis's MetricPlot (AK#1828): each drawn cell's curve, off
    // its own knob sweep, paired with its reference as /analyses marks it.
    const chartMetricRender = metricSpec && {
      metric: metricSpec,
      series: metricSeries(
        m.drawn.map((c, k) => {
          const served = servedCell(c, listedHere);
          return {
            key: c.key,
            label: caption(c),
            color: cellColor(k),
            reference: !!served?.reference,
            fixed: !!served?.fixed,
            slot: c.slot,
            ground: c.ground,
            ...(c.plane !== undefined ? { plane: c.plane } : {}),
            ...(c.step !== undefined ? { step: c.step } : {}),
          };
        }),
        m.drawn.map((_, k) => runners[k]?.param.data ?? null),
        metricSpec.relativeTo !== null,
      ),
    };
    const chartCurves = curves.length > 0 ? curves : undefined;
    // A pattern's cells as its view draws them (AK#1757 step 7): a trace per
    // drawn cell in its legend colour, and a table row per cell, a refused
    // one (or one whose solve the server refused) by name.
    const pv = chartPatternView(m.state);
    const chartPattern = pv && {
      view: pv,
      azElevDeg: m.inputs.pattern.azElevDeg,
      elevAzDeg: m.inputs.pattern.elevAzDeg,
      running: patternRunning,
      cells: m.drawn.map((c, k) => ({
        key: c.key,
        label: c.label,
        color: cellColor(k),
        result: runners[k]?.pattern.data?.result ?? null,
        stale: !!runners[k]?.pattern.data?.stale,
      })),
      rows: m.plan.cells.map((c) => {
        const k = m.drawn.indexOf(c);
        const d = k >= 0 ? runners[k]?.pattern.data : null;
        const refused = c.refused ?? d?.error ?? null;
        return {
          key: c.key,
          label: c.label,
          color: refused ? null : cellColor(k),
          metrics: d?.metrics ?? null,
          refused,
          stale: !!d?.stale,
        };
      }),
    };
    // What the chart's view draws from: the stage's bag, with its edit
    // callbacks and the legend, and the thumbnail's, without either.
    const panel = {
      paramSweep: p0data,
      paramSweepRunning: runners.some((r) => r.param.running),
      zparam: { ...zparam, onCalloutsChange: setCalloutsFlip },
      onZparamXLogChange: (log: boolean) => setZparamXLogAt(i, log),
      onZparamAxisChange: (axis: "r" | "x", c: RxAxisChoice) => setZparamAxisAt(i, axis, c),
      chartFrequency: freqRender && {
        ...freqRender,
        onAxisChange,
        onThresholdChange,
        onRxAxisChange,
        onRxXLogChange,
      },
      chartPattern,
      chartMap: chartMap && {
        ...chartMap,
        // "Set knobs here" (decision 6): an explicit act, the same path as
        // a drag of each knob (so a knob the optimizer owns is handed back).
        onSetKnobs: (x: number, y: number) => {
          handleUserParamChange([mapState!.x.param], x);
          handleUserParamChange([mapState!.y.param], y);
        },
      },
      chartMetric: chartMetricRender,
      ...(chartCurves ? { chartCurves } : {}),
      chartLegend: legend,
      chartCellLabels: m.drawn.map(caption),
      chartDesign: geometry,
      ...(chartPins.length > 0 ? { chartPins } : {}),
    };
    const thumb = {
      paramSweep: p0data,
      paramSweepRunning: runners.some((r) => r.param.running),
      zparam,
      chartFrequency: freqRender,
      chartPattern,
      chartMap,
      chartMetric: chartMetricRender,
      ...(chartCurves ? { chartCurves } : {}),
      chartCellLabels: m.drawn.map(caption),
      ...(chartPins.length > 0 ? { chartPins } : {}),
    };
    return { controls, overlays, panel, thumb };
  };
  const chartUis = chartModels.map((m) => (m ? chartUi(m) : null));
  // A view's chart props, or none (only a chart's view draws a sweep).
  const NO_CHART = { paramSweep: null, paramSweepRunning: false } as const;
  const chartPanelOf = (v: View) => chartUis[chartIndex(v)]?.panel ?? NO_CHART;
  const chartThumbOf = (v: View) => chartUis[chartIndex(v)]?.thumb ?? NO_CHART;
  const viewPanel = (v: View, size: number, fill: boolean) => (
    <ViewPanel
      view={v}
      // On a desktop the Z-vs-parameter view's size comes from
      // ZParamStage, which takes the sweep bar's measured height off
      // it; a phone stacks the bar instead, sized at the carousel's
      // call site.
      size={size}
      fill={fill}
      result={shownResult}
      // An optimizer run never touches the knobs until it finishes, so
      // `result` holds the pre-run solve for its whole duration and the
      // Smith dot would sit frozen while the readout ticks (#773). The
      // per-eval frames carry the trial Z, so hand it to the chart.
      liveZ={optLiveZ}
      liveBands={optBandMarks}
      preview={preview}
      measured={measured}
      pattern={pattern}
      pinnedPatterns={pinnedPatterns}
      measFreqMhz={measFreq}
      // The chart this view is, if it is one (unit 4: each chart its own).
      {...chartPanelOf(v)}
      azElevDeg={azElevDeg}
      elevAzDeg={elevAzDeg}
      cameraProjection={cameraProjection}
      // The session's camera, so the antenna view is where you left it
      // when you come back to it (AK#1542). This bag serves the rail's
      // primary view, the grid cells and the mobile pages — one antenna
      // canvas at a time in any of them. The thumbnail bag below passes
      // none, and thumbnails stay fitted.
      canvasCamera={canvasCamera}
      // Same bag, same reasoning: the Smith chart zooms here and not in
      // the thumbnail strip, whose bag omits it.
      chartZoom
      smithYGrid={smithYGrid}
      onSmithYGridChange={setSmithYGrid}
      showHeatmap={showHeatmap}
      showEnvelope={showEnvelope}
      showWireLabels={showWireLabels}
      showFeedNames={showFeedNames}
      multiFeed={effectiveMultiFeed}
      fineNorm={normCheck?.pattern_norm ?? null}
      onFarFieldCaptions={onFarFieldCaptions}
      combinedFill={combinedFill}
      combinedHighlight={shownHighlight}
      refineEnabled={refineEnabled}
      schematicSvg={schematicSvg}
      schematicUnavailable={schematicUnavailable}
      files={files}
    />
  );
  // `readout` is the floating solve readout when this is the rail's primary
  // view: rendered last, in the slide, as before — except on the desktop
  // Z-vs-parameter view, whose stage pins it inside the chart (ZParamStage).
  const renderOutput = (v: View, size: number, fill: boolean, readout?: ReactNode) => {
    const ui = chartUis[chartIndex(v)] ?? null;
    return ui && !isMobile ? (
      <ZParamStage
        size={size}
        fallbackHead={Math.round(Math.min(2 * ZPARAM_DESKTOP_HEADER_PX, 0.1 * size))}
        header={ui.controls}
        overlays={ui.overlays}
        readout={readout}
        chart={(s) => viewPanel(v, s, fill)}
      />
    ) : (
    <>
          {ui?.controls}
          {ui?.overlays}
          {v === "antenna" && (
            <AntennaOverlayControls
              cameraProjection={cameraProjection}
              setCameraProjection={setCameraProjection}
              isMobile={isMobile}
              showHeatmap={showHeatmap}
              setShowHeatmap={setShowHeatmap}
              showEnvelope={showEnvelope}
              setShowEnvelope={setShowEnvelope}
              showWireLabels={showWireLabels}
              setShowWireLabels={setShowWireLabels}
              showFeedNames={showFeedNames}
              setShowFeedNames={setShowFeedNames}
            />
          )}
          {/* Always there on a pattern view now: it carries the chart's
              captions and the peak readout, on mobile too. */}
          {(v === "azimuth" || v === "elevation") && (
            <FarFieldOverlayControls
              isMobile={isMobile}
              normCheckEnabled={normCheckEnabled}
              setNormCheckEnabled={setNormCheckEnabled}
              normCheck={normCheck}
              backend={backend.name}
              groundModel={groundModel}
              necOverlayEnabled={necOverlayEnabled}
              setNecOverlayEnabled={setNecOverlayEnabled}
              captions={ffCaptions[v === "azimuth" ? "xy" : "yz"] ?? null}
              maxMetrics={maxMetrics}
              maxPending={maxPending}
              canFindMax={!!result && !stale}
              onFindMax={findMax}
              onAimAtMax={aimAtMax}
              onDismissMax={() => setMaxDismissed(true)}
            />
          )}
          {/* The combined view (AK#1730): both cuts' slice peaks, and none of
              the one-cut overlays' switches, since it draws neither overlay. */}
          {v === "combined" && (
            <FarFieldOverlayControls
              isMobile={isMobile}
              normCheckEnabled={normCheckEnabled}
              setNormCheckEnabled={setNormCheckEnabled}
              normCheck={normCheck}
              backend={backend.name}
              groundModel={groundModel}
              necOverlayEnabled={necOverlayEnabled}
              setNecOverlayEnabled={setNecOverlayEnabled}
              captions={ffCaptions.xy ?? null}
              alsoPeak={ffCaptions.yz ?? null}
              overlayToggles={false}
              maxMetrics={maxMetrics}
              maxPending={maxPending}
              canFindMax={!!result && !stale}
              onFindMax={findMax}
              onAimAtMax={aimAtMax}
              onDismissMax={() => setMaxDismissed(true)}
            />
          )}
          {v === "combined" && (
            <CombinedLegend fill={combinedFill} setFill={setCombinedFill} />
          )}
          <CutAngleOverlay
            v={v}
            azElevDeg={azElevDeg}
            setAzElevDeg={setAzElevDeg}
            elevAzDeg={elevAzDeg}
            setElevAzDeg={setElevAzDeg}
          />
          {(v === "azimuth" || v === "elevation" || v === "combined") && (
            <CompareOverlay
              pinCurrentPattern={pinCurrentPattern}
              setCompareCollapsed={setCompareCollapsed}
              result={result}
              pinnedPatterns={pinnedPatterns}
              compareCollapsed={compareCollapsed}
              clearPins={clearPins}
              liveMetrics={liveMetrics}
              currentExample={currentExample}
              geometry={geometry}
              measFreq={measFreq}
              removePin={removePin}
              togglePin={togglePin}
              onKeepPins={keepPatternPins}
              keepPinsBlocked={keepPatternPinsBlocked}
              cutLabel={
                v === "combined"
                  ? `az @ ${azElevDeg}° elev · el @ ${elevAzDeg}° az (dBi)`
                  : (ffCaptions[v === "azimuth" ? "xy" : "yz"]?.cutLabel ??
                    null)
              }
              // The row highlight is the combined view's alone (AK#1730): the
              // one-cut views tell pins apart by colour and keep their table.
              {...(v === "combined"
                ? {
                    highlight: shownHighlight,
                    onToggleHighlight: (id: string) =>
                      setCombinedHighlight((cur) =>
                        toggleHighlight(cur, id, shownPins),
                      ),
                    onClearHighlight: () => setCombinedHighlight([]),
                  }
                : {})}
            />
          )}
          {viewPanel(v, size, fill)}
          {readout}
    </>
  );
  };

  // Mobile: knobs pane + a scroll-snap output carousel over the PINNED views
  // plus Info (#700 unit 4 — the roster lives behind the dots row's "⋯" sheet,
  // as the rail's picker does on desktop), instead of the desktop
  // thumbstrip/HUD stage. A distinct tree (not CSS-hiding the
  // desktop one) keeps both layouts honest; the shared pieces are exactly the
  // hoisted consts above. All hooks already ran, so branching here is safe.
  if (isMobile) {
    return (
      <div className="app app-mobile" data-ready={sessionReadyKey}>
        <aside className="sidebar mobile-knobs">{controls}</aside>
        <section
          className="mobile-output"
          ref={mobRef}
          aria-label="Antenna output views"
        >
          {solveOverlays}
          <div
            className={`mobile-carousel${outputStale ? " stale" : ""}`}
            ref={mobileCarouselRef}
            onScroll={onMobileCarouselScroll}
          >
            {screens.map((s) => (
              <div
                key={s.id}
                className={`mobile-screen${s.id === "info" ? " mobile-screen-info" : ""}${
                  s.id === "combined" ? " mobile-screen-combined" : ""
                }`}
              >
                {s.id === "info" ? (
                  <>
                    <SolveReadout
                      z0={z0}
                      live={liveSolve}
                      className="mobile-readout"
                      result={readoutResult}
                      rttMs={rttMs}
                      currentExample={currentExample}
                      effectiveMultiFeed={effectiveMultiFeed}
                      normCheck={normCheck}
                      normCheckEnabled={normCheckEnabled}
                      onPlaneChange={pickPlane}
                    />
                    {/* The ws status lives HERE, not floating over the
                        carousel — on a phone the desktop-style absolute
                        bottom-right .status covered chart content. Inside
                        the Info screen it's a normal flow row. */}
                    <div className="status">
                      ws: {status}
                      {stale && (
                        <span className="status-busy">
                          {waiting ? " · not solved: reconnecting…" : " · solving…"}
                        </span>
                      )}
                    </div>
                  </>
                ) : (
                  renderOutput(
                    s.id as View,
                    // The Z-vs-parameter view stacks its header above the
                    // chart on a phone: the chart gives up the header's
                    // height so the pair fits the screen.
                    chartIndex(s.id) >= 0
                      ? Math.max(160, mobChartSize - ZPARAM_MOBILE_HEADER_PX)
                      : // The combined view's two cut knobs stand beside its
                        // plot on a phone, not over it (AK#1732).
                        s.id === "combined"
                        ? combinedPhoneChartSize(mobChartSize, mobPaneWidth)
                        : mobChartSize,
                    fillsStage(s.id as View),
                  )
                )}
              </div>
            ))}
          </div>
          <MobileDots
            screens={screens}
            index={mobileIndex}
            goToScreen={goToMobileScreen}
            view={view}
            pinned={pinned}
            newIds={newIds}
            togglePin={toggleViewPin}
            movePin={movePin}
            markRosterSeen={markRosterSeen}
          />
        </section>
      </div>
    );
  }

  return (
    <div className="app" data-ready={sessionReadyKey}>
      <aside className="sidebar">{controls}</aside>

      <main className="stage" aria-label="Antenna output views">
        {solveOverlays}
        {/* Rail/grid presets over the same pinned set (unit 3) — visible in
            both modes so either one can switch to the other. Desktop-only by
            placement: this branch is never reached while isMobile. */}
        <LayoutModeToggle layout={effectiveLayout} setLayout={setLayout} />
        {effectiveLayout === "grid" ? (
          <>
            <ViewGrid
              gridRef={gridRef}
              cells={gridViews}
              view={view}
              setView={setView}
              onMaximize={maximizeView}
              cellSize={gridCellSize}
              rows={gridRows}
              cols={gridCols}
              renderCell={(v, size) => renderOutput(v, size, fillsStage(v))}
            />
            {/* Grid mode has no single primary slide to float the HUD over
                (unit 3), so it anchors to the STAGE itself instead of one
                cell — same look (stage-readout family), one instance rather
                than per-cell. `.stage` is the positioned ancestor here, same
                role `.carousel-slide` plays in rail mode below. */}
            <SolveReadout
              z0={z0}
              live={liveSolve}
              className="stage-readout"
              // One card for the whole grid, so it minimizes per the focused
              // cell's view, as the rail's card does per its primary view.
              collapsed={isReadoutCollapsed(prefView(view), readoutFallback(view))}
              onCollapsedChange={(c) => setReadoutCollapsed(prefView(view), c, readoutFallback(view))}
              result={readoutResult}
              rttMs={rttMs}
              currentExample={currentExample}
              effectiveMultiFeed={effectiveMultiFeed}
              normCheck={normCheck}
              normCheckEnabled={normCheckEnabled}
              onPlaneChange={pickPlane}
            />
          </>
        ) : (
          <>
            <div className="thumbstrip" ref={thumbStripRef}>
              {rail.map((v) => (
                <button
                  key={v.id}
                  className="thumb"
                  onClick={() => setView(v.id)}
                  title={`Switch to ${v.label}`}
                >
                  <div
                    className="thumb-canvas"
                    style={{ width: thumbSize.width, height: thumbSize.height }}
                  >
                    {/* The chart draws at the column's full (3-thumb-era) width
                        — where its fixed-px labels fit — and scales down
                        uniformly into the shorter rectangle, a true miniature
                        (issue #652; see useThumbColumnSize). */}
                    <div
                      className="thumb-scale"
                      style={{
                        width: thumbSize.width,
                        height: thumbSize.width,
                        transform: `translate(-50%, -50%) scale(${
                          thumbSize.height / thumbSize.width
                        })`,
                      }}
                    >
                    {/* A thumbnail draws at chart scale 1 (./charts/chartScale):
                        the miniature is a button, and the laptop's larger
                        chart ramp would only crowd it. */}
                    <ChartScaleContext.Provider value={1}>
                    <ViewPanel
                      view={v.id}
                      size={thumbSize.width}
                      fill={false}
                      result={shownResult}
                      // Same live trial point as the primary stage: the
                      // thumbnail is the same chart, so a frozen dot there
                      // would be the same defect at a smaller size.
                      liveZ={optLiveZ}
                      liveBands={optBandMarks}
                      preview={preview}
                      measured={measured}
                      pattern={pattern}
                      pinnedPatterns={[]}
                      measFreqMhz={measFreq}
                      // The stage connects the Smith sweep when adaptive
                      // resolution is on; without this the thumbnail drew
                      // dots until its chart took the stage.
                      refineEnabled={refineEnabled}
                      {...chartThumbOf(v.id)}
                      azElevDeg={azElevDeg}
                      elevAzDeg={elevAzDeg}
                      cameraProjection={cameraProjection}
                      showHeatmap={showHeatmap}
                      showEnvelope={showEnvelope}
                      multiFeed={effectiveMultiFeed}
                      schematicSvg={schematicSvg}
                      schematicUnavailable={schematicUnavailable}
                      combinedFill={combinedFill}
                      smithYGrid={smithYGrid}
                    />
                    </ChartScaleContext.Provider>
                    </div>
                  </div>
                  <div className="thumb-label">{v.label}</div>
                </button>
              ))}
              {/* Everything not pinned lives behind here. Fixed height by design:
                  useThumbColumnSize subtracts exactly this slot. */}
              <ViewPicker
                view={view}
                setView={setView}
                pinned={pinned}
                newIds={newIds}
                togglePin={toggleViewPin}
                movePin={movePin}
                markRosterSeen={markRosterSeen}
              />
            </div>
            <div
              className={`carousel-slide${outputStale ? " stale" : ""}`}
              ref={slideRef}
            >
              {/* Solve readout, pinned to the lower-left of whichever view the
                  carousel is centered on. Floats over the canvas as a HUD so the
                  left input rail stays inputs-only. It sits INSIDE the slide, so
                  the slide's stale dim already covers it — no own stale class, or
                  the two opacities would compound. renderOutput places it: last
                  in the slide, or inside the chart on the Z-vs-parameter view
                  (ZParamStage). */}
              {renderOutput(
                view,
                chartSize,
                fillsStage(view),
                <SolveReadout
                  z0={z0}
                  live={liveSolve}
                  className="stage-readout"
                  collapsed={isReadoutCollapsed(prefView(view), readoutFallback(view))}
                  onCollapsedChange={(c) => setReadoutCollapsed(prefView(view), c, readoutFallback(view))}
                  result={readoutResult}
                  rttMs={rttMs}
                  currentExample={currentExample}
                  effectiveMultiFeed={effectiveMultiFeed}
                  normCheck={normCheck}
                  normCheckEnabled={normCheckEnabled}
                  onPlaneChange={pickPlane}
                />,
              )}
            </div>
          </>
        )}
        <div className="status">
          ws: {status}
          {stale && (
            <span className="status-busy">
              {waiting ? " · not solved: reconnecting…" : " · solving…"}
            </span>
          )}
        </div>
      </main>
    </div>
  );
}
