import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  backendAllowed,
  designRefusal,
  type DesignConstraintInputs,
  backendDisplayLabel,
  backendSupportsGround,
  comboInappropriate,
  modelOptionsForRequest,
  normalizeBackend,
  type BackendRoster,
  type ModelOptionSpecs,
} from "../../lib/backends";
import {
  bandContaining as bandContainingIn,
  freqWindowCeiling as freqWindowCeilingFor,
} from "../../lib/bands";
import {
  findLinkedDesignFreq,
  groupExamplesForPicker,
  isGroup,
  linkedMeasFreqFor,
  overlaySchemaForVariant,
  seedDefaults,
  setValueAtPath,
  snapForExample,
  type BandSpec,
  type ParamValueBag,
  type SchemaItem,
  type SchemaParamSpec,
} from "../../lib/params";
import { mobileScreens, VIEW_META, type View } from "../../lib/view";
import type {
  MeasuredData,
  SolveRequest,
  SolveResponse,
} from "../../lib/api";
import type { TerrainPresetSchema } from "../../lib/ground";
import { BackendConfigModal } from "../backend/BackendConfigModal";
import { ParamForm } from "../params/ParamForm";
import { setCutRefineEnabled } from "../charts/cuts";
import type { PatternMetrics } from "../charts/types";
import {
  ThemeContext,
  useFullscreen,
  useGridCellSize,
  useIsMobile,
  useSlideSize,
  useThumbColumnSize,
} from "../hooks";
import { SolveReadout } from "../results/SolveReadout";
import {
  AntennaOverlayControls,
  CompareOverlay,
  CutAngleOverlay,
  FarFieldOverlayControls,
  LayoutModeToggle,
  SmithOverlayControls,
} from "../results/StageOverlays";
import { ViewGrid } from "../results/ViewGrid";
import { ViewPanel } from "../results/ViewPanel";
import { fetchMetrics, PinsContext, SessionsContext, ThemeControlContext } from "./contexts";
import { CatalogPanel } from "./CatalogPanel";
import { DesignFreqRow } from "./DesignFreqRow";
import { GroundPanel } from "./GroundPanel";
import { KnobOptMenu } from "./KnobOptMenu";
import { copyParams, downloadNec, loadMeasured } from "./sessionActions";
import { SessionGearMenu } from "./SessionGearMenu";
import { SolveOverlays } from "./SolveOverlays";
import { SolverSlotTabs } from "./SolverSlotTabs";
import {
  CONVERGE_N_VALUES,
  useAnalysisRunners,
} from "./useAnalysisRunners";
import { useCapabilities } from "./useCapabilities";
import { useDesignCatalog } from "./useDesignCatalog";
import { useGroundConfig } from "./useGroundConfig";
import { MobileDots } from "./MobileDots";
import { useMobileCarousel } from "./useMobileCarousel";
import { useOptimizer } from "./useOptimizer";
import { useSchematic } from "./useSchematic";
import { useSolveChannel } from "./useSolveChannel";
import { useSolverSlots } from "./useSolverSlots";
import { gridCells, gridShape, useViewPrefs } from "./useViewPrefs";
import { useViewState } from "./useViewState";
import { ViewPicker } from "./ViewPicker";
import { VfoPanel } from "./VfoPanel";

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
export function DesignSession({ id, active }: { id: number; active: boolean }) {
  const { roster, terrainPresets, modelOptionSpecs, error } = useCapabilities();
  if (error !== null)
    return (
      <div className="app app-capabilities" role="alert">
        Could not load the server’s solver catalog ({error}). Reload once the
        server is reachable.
      </div>
    );
  if (roster === null)
    return <div className="app app-capabilities">loading solver catalog…</div>;
  return (
    <DesignSessionBody
      id={id}
      active={active}
      roster={roster}
      terrainPresets={terrainPresets}
      modelOptionSpecs={modelOptionSpecs}
    />
  );
}

function DesignSessionBody({
  id,
  active,
  roster,
  terrainPresets,
  modelOptionSpecs,
}: {
  id: number;
  active: boolean;
  roster: BackendRoster;
  terrainPresets: TerrainPresetSchema[];
  /** The served solver-knob catalogue (#1006 G2-6). */
  modelOptionSpecs: ModelOptionSpecs;
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
  const [autoSim, setAutoSim] = useState(true);

  const {
    examples,
    examplesError,
    loadErrors,
    trustBusy,
    trustDesign,
    reloadCatalog,
  } = useDesignCatalog({ geometry, setGeometry, setParamValues });

  // Reload the selected user design from disk (issue #867). Re-fetching
  // /examples makes the server re-register user designs; bumping the nonce
  // re-runs the preview effect below for the SAME geometry, and its
  // previewReady release then re-fires the live solve — exactly the design-
  // switch path, minus the selection change. Load errors and awaiting-trust
  // states ride along on the same fetch, so a broken edit surfaces in the
  // usual panels.
  const [reloadNonce, setReloadNonce] = useState(0);
  const [reloadBusy, setReloadBusy] = useState(false);
  const reloadDesigns = useCallback(async () => {
    setReloadBusy(true);
    try {
      await reloadCatalog();
      setReloadNonce((n) => n + 1);
    } finally {
      setReloadBusy(false);
    }
  }, [reloadCatalog]);

  const currentExample = examples.find((e) => e.name === geometry);
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
    if (!linkMeas) return;
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
  // Solver slots A / B / C (#642 seam 5b-3). Called at the cluster's own
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
    wireRadius,
    backendOptsKey,
    updateSlotOpts,
    setSlotBackend,
    resetSlot,
  } = useSolverSlots({ roster, specs: modelOptionSpecs });
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
  // Ground / terrain selection and its derived protocol values (#642 seam
  // 5b-3). Pure state + derivations, so it adds no effects here.
  const {
    groundEnabled,
    setGroundEnabled,
    groundType,
    setGroundType,
    finiteGroundMethod,
    setFiniteGroundMethod,
    terrainPreset,
    setTerrainPreset,
    terrainParams,
    setTerrainParams,
    groundModel,
    terrainKey,
    groundSummary,
  } = useGroundConfig({ backend });
  const tabSummary = `${(currentExample?.label ?? geometry) || "new design"} · ${backendDisplayLabel(backend, currentOpts)} N=${nPerWire} · ${groundSummary}`;
  useEffect(() => {
    reportSummary(id, tabSummary);
  }, [id, tabSummary, reportSummary]);
  // Which views are resident in the desktop rail (global, persisted) — read
  // before useViewState because the arrow-key cycler walks the pinned set.
  // (`togglePin` is renamed: the pattern-pin context below owns that name.)
  const {
    pinned,
    newIds,
    railViews,
    togglePin: toggleViewPin,
    movePin,
    markRosterSeen,
    layout,
    setLayout,
  } = useViewPrefs();

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
  // the server already computed while building it.
  const designConstraintInputs: DesignConstraintInputs = {
    has_stepped_radius_junction:
      currentExample?.has_stepped_radius_junction ?? false,
    buried: currentExample?.has_buried_wire ?? false,
  };
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
  function solveWithheld(): boolean {
    return (
      backendDisallowed ||
      // No approval path around this one either: momwire RAISES on the
      // combination, so "Solve anyway" would buy an error dialog. The user's
      // way out is the option, not an override — which is why the overlay
      // names the option rather than offering a button.
      optionRefusal !== null ||
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
  // Whether to render the per-feed (multi-feed) UI. Prefer the value the
  // server folds into the live solve / geometry response — authoritative for
  // user designs, which derive it lazily — and fall back to the example
  // descriptor (eager built-ins) before the first response lands.
  const effectiveMultiFeed =
    result?.multi_feed ??
    preview?.multi_feed ??
    currentExample?.multi_feed ??
    false;
  // Smith-chart overlay toggles. Both are debounced sweeps that re-fire
  // whenever any antenna/backend parameter changes; gating them with these
  // checkboxes lets the user pause an expensive sweep (e.g. BSpline d=2
  // convergence on slow geometries) without leaving the Smith view.
  const [sweepEnabled, setSweepEnabled] = useState(true);
  const [convergeEnabled, setConvergeEnabled] = useState(false);
  // Adaptive resolution (issue #744): dwell-triggered display-space
  // refinement of the sweep and cut plots. Persisted, unlike the overlay
  // checkboxes above: turning it off is a per-machine capacity decision
  // ("this laptop, that 4k-segment design"), not a per-session view choice,
  // and it should survive a reload the same way the theme does.
  const [refineEnabled, setRefineEnabled] = useState(
    () => localStorage.getItem("antennaknobs.refineEnabled") !== "0",
  );
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
  const [normCheckEnabled, setNormCheckEnabled] = useState(true);
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
  const [liveMetrics, setLiveMetrics] = useState<PatternMetrics | null>(null);
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
    pinned,
    layout: effectiveLayout,
    setLayout,
  });
  const { ref: slideRef, size: chartSize } = useSlideSize(720, isMobile);
  const thumbStripRef = useRef<HTMLDivElement>(null);
  // The rail is the pinned set minus whatever is on the stage; peeking an
  // unpinned view subtracts nothing, so the count the sizer needs varies.
  const rail = railViews(view);
  const thumbSize = useThumbColumnSize(thumbStripRef, rail.length, 280, isMobile);
  // Grid mode's displayed cells (unit 3): the first ≤4 pins, in pin order.
  // gridCells/gridShape are pure (useViewPrefs.ts) so this and useViewState's
  // internal cycling can never disagree about "what's on screen".
  const gridViewIds = gridCells(pinned);
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
    onMobileCarouselScroll,
    goToMobileScreen,
  } = useMobileCarousel({ isMobile, orientation, pinned, view, setView });
  // The carousel's pages: the pinned views in pin order plus the trailing Info
  // screen. The dots row renders the SAME list, so a page can never exist
  // without a dot (or the reverse) — see MobileDots.
  const screens = useMemo(() => mobileScreens(pinned), [pinned]);
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

  function buildRequest(): SolveRequest {
    // ground_model is shared across backends (εr=10, σ=0.002 for the finite
    // models): PyNEC honours it directly; momwire's B-spline family solves
    // the finite models with its reflection-coefficient ground, while
    // Sinusoidal folds them to the PEC image solve (the server
    // ships the real εr/σ for the pattern either way).
    const groundActive = groundEnabled && backendSupportsGround(backend);
    const base: SolveRequest = {
      _session: sessionId,
      geometry,
      variant: currentVariant,
      solver: backend.kind === "momwire" ? "momwire" : backend.kind,
      n_per_wire: nPerWire,
      design_freq_mhz: designFreq,
      measurement_freq_mhz: measFreq,
      wire_radius: wireRadius,
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
      base.terrain = { preset: terrainPreset, ...terrainParams };
    }
    if (backend.kind === "momwire") {
      base.momwire_model = backend.name;
      const opts = modelOptionsForRequest(backend, currentOpts, modelOptionSpecs);
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
    }
    // Measurement plane (issue #652 c): only ever sent when picked — the
    // natural plane is the absence of the field, so designs with no
    // network never see it.
    if (plane) base.plane = plane;
    // Schema-driven antennas (all of them now): merge the active
    // paramValues straight in. For fan_dipole this includes a nested
    // `bands: [{band_id, freq, length_factor}, ...]` array; the backend
    // unpacks it in _bands_from_request().
    Object.assign(base, currentValues);
    // hexbeam_5band's daisy_chain (single common feed) is now modelled with
    // build_network(), which the shared NetworkReducer solves on momwire and
    // PyNEC alike — so it is no longer greyed out or forced off on momwire.
    return base;
  }

  // Reactive knob optimiser (#642 seam 5b-3). Called here, at the fixed-input
  // signature's old position, so the cluster's three trailing effects keep
  // their global order; the design-load reset rides along with them.
  const {
    optEnabled,
    setOptEnabled,
    optObjective,
    setOptObjective,
    knobOpt,
    setKnobOpt,
    knobMenu,
    setKnobMenu,
    optRunning,
    optResult,
    optProgress,
    optError,
    optPausedBy,
    setOptPausedBy,
    optAbortRef,
    optEnabledRef,
    knobOptFor,
    updateKnobOpt,
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
    setParamAtPath,
  });

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
  const isResident = (v: View) => pinned.includes(v) || view === v;
  const sweepResident =
    isResident("smith") || isResident("gamma") || isResident("vswr");
  // Per-view split of sweepResident, for refinement only (issue #744): the
  // BASE sweep serves all three charts from one array, but refinement buys
  // extra solves per PROJECTION, so it needs to know which of the three is
  // actually on screen rather than merely "any".
  const residentSweepViews = {
    vswr: isResident("vswr"),
    gamma: isResident("gamma"),
    smith: isResident("smith"),
  };
  const convergeResident = isResident("smith");
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

  const currentBands: BandSpec[] = currentExample?.bands ?? [];

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
      // Derived state cleared when its inputs change — the reset IS the
      // effect's purpose, not a sync that could be computed during render
      // (#768).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (band !== "") setBand("");
      return;
    }
    // Always re-snap on geometry switch — every HF example shares the
    // DEFAULT_AMATEUR_BANDS list, so a sticky band key (e.g. "10m" from the
    // previous 28 MHz design) would otherwise survive a switch into a
    // 14 MHz design and keep the slider parked on the wrong band.
    // (The containing-band / native-freq logic lives in snapForExample,
    // shared with the antenna-switch preview fetch — see there.)
    const snap = snapForExample(currentExample)!;
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
    } else if (linkMeas || !currentExample.has_design_freq) {
      // Re-anchor the dial too: always when locked, and also for
      // fixed-geometry designs — their lock is inert (see measLockable),
      // so a measFreq left over from the previous design would strand the
      // measurement outside this design's window entirely.
      setMeasFreq(snap.measFreq);
      setMeasBand(snap.measBandKey);
    }
    // band/currentBands.length/linkMeas are read, not listed: this effect's
    // whole point is re-snapping only "on geometry switch" (see above) — band
    // and linkMeas are the very state the user can change by hand between
    // switches, and listing them would re-fire the snap on every band pick or
    // lock toggle instead of only on a new currentExample. currentBands.length
    // is itself derived from currentExample, already covered.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentExample]);

  // Ground-requirement seed: the buried-wire designs declare
  // ground_requirement="sommerfeld" (conductors below z=0 only exist under
  // a Sommerfeld half-space — the refl-coef default refuses them by name),
  // so seed finite + Sommerfeld on selection instead of letting the first
  // solve hit the refusal wall. Keyed on the example switch, like the
  // band-snap above: the user can still flip anything afterwards, and the
  // solver's by-name refusal remains the enforcement. GroundPanel shows the
  // one-line notice whenever the requirement is present.
  useEffect(() => {
    if (currentExample?.ground_requirement !== "sommerfeld") return;
    setGroundEnabled(true);
    setGroundType("finite");
    setFiniteGroundMethod("sommerfeld");
    // Setters are stable useState setters; currentExample is the switch key.
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
    requestSolve,
    cancelSolve,
    seqRef,
  } = useSolveChannel({
    active,
    controlsRef,
    geometryRef,
    previewSigRef,
    setResult,
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
  const comparing = pinCount > 0 && (view === "azimuth" || view === "elevation");
  useEffect(() => {
    if (!comparing || !result || !active) {
      // Derived state cleared when its inputs change — the reset IS the
      // effect's purpose, not a sync that could be computed during render
      // (#768).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLiveMetrics(null);
      return;
    }
    let cancelled = false;
    const h = window.setTimeout(() => {
      // Read at fire time, not at schedule time: the dwell is 300 ms and the
      // metrics must describe the design as it now stands. Null only before
      // the first solve, which `result` above already excludes (issue #768).
      const controls = controlsRef.current;
      if (!controls) return;
      fetchMetrics(controls).then((m) => {
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
    // Hard gate first: the active backend cannot run this design at all
    // (e.g. junction-port designs on anything but B-spline — the solver
    // raises). Same withhold UI, but the banner offers "switch", never
    // "solve anyway". The app still never switches the solver itself.
    if (backendDisallowed) {
      setSolverWarning(true);
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
      setSolverWarning(true);
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
    currentValuesKey,
    designFreq, measFreq, plane,
    groundEnabled, groundModel, terrainKey,
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
          // here, once per selection or user-design reload (this effect is
          // keyed on `geometry` + `reloadNonce`).
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
    // reloadNonce (issue #867): a user-design reload re-runs this full
    // switch path for the same geometry — fresh preview from the re-loaded
    // builder, gate reset, then the live solve re-fires on release.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, reloadNonce]);

  // The four background analyses (#642 seam 5b-3): freq sweep, convergence
  // sweep, far-field norm check and the NEC rp_card pattern. Called here, at
  // the debounce effects' old position, so all four keep their global order
  // behind the solve and preview effects above.
  const {
    sweep,
    sweepRunning,
    sweepSettled,
    converge,
    convergeRunning,
    normCheck,
    pattern,
  } = useAnalysisRunners({
      backend,
      currentVariant,
      currentExample,
      currentBands,
      freqWindowCeiling,
      designFreq,
      measFreq,
      measLocked,
      groundEnabled,
      groundModel,
      sweepEnabled,
      convergeEnabled,
      normCheckEnabled,
      necOverlayEnabled,
      sweepResident,
      convergeResident,
      patternResident,
      autoSim,
      active,
      comboApproved,
      recommendedBackend,
      // Same reference the sweep/Smith charts plot against (viewRegistry's
      // `result?.z0_ohms ?? 50`), so refinement judges curvature on the
      // curve the user is actually looking at.
      z0: result?.z0_ohms ?? 50,
      refineEnabled,
      residentSweepViews,
      buildRequest,
      solveWithheld,
      seqRef,
      approvedComboRef,
    });
  // Hoisted JSX shared between the desktop tree below and the mobile tree
  // (Phase B). These close over the session's locals, so they are consts /
  // a closure rather than components — zero prop surface, identical DOM.
  // (The former inline sub-blocks now live as prop-driven components in
  // components/session/ and results/StageOverlays.tsx — #642 seam 5b-2.)
  const controls = (
    <>
        <SessionGearMenu
          gearMenuOpen={gearMenuOpen}
          setGearMenuOpen={setGearMenuOpen}
          copiedParams={copiedParams}
          onCopyParams={() => copyParams({ buildRequest, setCopiedParams })}
          onDownloadNec={() =>
            downloadNec({ setGearMenuOpen, buildRequest, geometry })
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
          sweepEnabled={sweepEnabled}
          setSweepEnabled={setSweepEnabled}
          convergeEnabled={convergeEnabled}
          setConvergeEnabled={setConvergeEnabled}
          convergeNValues={CONVERGE_N_VALUES}
          measured={measured}
          onLoadMeasured={(f) =>
            loadMeasured(f, { setGearMenuOpen, setMeasured })
          }
          onClearMeasured={() => setMeasured(null)}
          normCheckEnabled={normCheckEnabled}
          setNormCheckEnabled={setNormCheckEnabled}
          refineEnabled={refineEnabled}
          setRefineEnabled={setRefineEnabled}
          theme={theme}
          applyTheme={applyTheme}
        />

        <CatalogPanel
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
            activeKey={bandContaining(designFreq)}
            onSelectBand={selectBand}
            onSetFreq={updateDesignFreq}
          />
        )}

        {/* Per-knob optimiser menu (right-click a knob): vary toggle + extents +
            turn step. Position-fixed at the click point. */}
        {knobMenu && currentExample && (
          <KnobOptMenu
            menu={knobMenu}
            spec={currentSchema.find(
              (x): x is SchemaParamSpec => !isGroup(x) && x.name === knobMenu.name,
            )}
            ko={knobOptFor(knobMenu.name)}
            onPatch={(patch) => updateKnobOpt(knobMenu.name, patch)}
            onClose={() => setKnobMenu(null)}
          />
        )}

        {/* Measurement freq = the rig's tuning control: a weighted VFO dial +
            frequency-counter readout. Top line: band select + the LCD. Below:
            the Live/Optimize toggles stacked at the left of the dial, with the
            lock pinned to the dial's lower-right corner ("lock to design freq"
            disables the dial). */}
        <VfoPanel
          currentBands={currentBands}
          measLocked={measLocked}
          measFreq={measFreq}
          bandContaining={bandContaining}
          measBand={measBand}
          selectMeasBand={selectMeasBand}
          currentExample={currentExample}
          measBandAnchor={measBandAnchor}
          freqWindowCeiling={freqWindowCeiling}
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
          setOptObjective={setOptObjective}
          optResult={optResult}
          optProgress={optProgress}
          optError={optError}
          optPausedBy={optPausedBy}
        />


        <h2 className="group-label">simulation</h2>

        <SolverSlotTabs
          slots={slots}
          activeSlot={activeSlot}
          onSelect={setActiveSlot}
          onOpenGear={setGearOpen}
          backend={backend}
          currentOpts={currentOpts}
          nPerWire={nPerWire}
        />

        <GroundPanel
          backend={backend}
          groundEnabled={groundEnabled}
          setGroundEnabled={setGroundEnabled}
          groundType={groundType}
          setGroundType={setGroundType}
          finiteGroundMethod={finiteGroundMethod}
          setFiniteGroundMethod={setFiniteGroundMethod}
          terrainPresets={terrainPresets}
          terrainPreset={terrainPreset}
          setTerrainPreset={setTerrainPreset}
          terrainParams={terrainParams}
          setTerrainParams={setTerrainParams}
          groundRequirement={currentExample?.ground_requirement ?? null}
        />

        {gearOpen && (
          <BackendConfigModal
            slot={gearOpen}
            backend={slots[gearOpen].backend}
            backends={roster}
            requiredBackends={requiredBackends}
            suggestConvergedFeed={
              currentExample?.converged_feed_suggested ?? false
            }
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
    <SolveOverlays
      showBusy={showBusy}
      solving={solving}
      onCancelSolve={cancelSolve}
      solverWarning={solverWarning}
      backendDisallowed={backendDisallowed}
      backend={backend}
      roster={roster}
      requiredBackends={requiredBackends}
      optionRefusal={optionRefusal}
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
  const outputStale =
    stale || (optRunning && VIEW_META[view].staleWhileOptimizing);

  // One output view: the per-view overlays plus the main <ViewPanel>. A
  // closure (not a component) so the ~30 captured locals need no props. The
  // solve-readout HUD stays OUT of it — mobile chart screens must not
  // inherit the floating readout.
  const renderOutput = (v: View, size: number, fill: boolean) => (
    <>
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
          {v === "smith" && !isMobile && (
            <SmithOverlayControls
              sweepEnabled={sweepEnabled}
              setSweepEnabled={setSweepEnabled}
              convergeEnabled={convergeEnabled}
              setConvergeEnabled={setConvergeEnabled}
              convergeNValues={CONVERGE_N_VALUES}
              measured={measured}
              onLoadMeasured={(f) =>
                loadMeasured(f, { setGearMenuOpen, setMeasured })
              }
              onClearMeasured={() => setMeasured(null)}
            />
          )}
          {/* The container is skipped entirely when it would be empty. */}
          {(v === "azimuth" || v === "elevation") &&
            (!isMobile || (normCheckEnabled && normCheck)) && (
            <FarFieldOverlayControls
              isMobile={isMobile}
              normCheckEnabled={normCheckEnabled}
              setNormCheckEnabled={setNormCheckEnabled}
              normCheck={normCheck}
              backend={backend.name}
              groundModel={groundModel}
              necOverlayEnabled={necOverlayEnabled}
              setNecOverlayEnabled={setNecOverlayEnabled}
            />
          )}
          <CutAngleOverlay
            v={v}
            azElevDeg={azElevDeg}
            setAzElevDeg={setAzElevDeg}
            elevAzDeg={elevAzDeg}
            setElevAzDeg={setElevAzDeg}
          />
          {(v === "azimuth" || v === "elevation") && (
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
            />
          )}
          <ViewPanel
            view={v}
            size={size}
            fill={fill}
            result={result}
            // An optimizer run never touches the knobs until it finishes, so
            // `result` holds the pre-run solve for its whole duration and the
            // Smith dot would sit frozen while the readout ticks (#773). The
            // per-eval frames carry the trial Z, so hand it to the chart.
            liveZ={optRunning && optProgress ? optProgress.metrics : null}
            preview={preview}
            sweep={sweep}
            converge={converge}
            measured={measured}
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
            refineEnabled={refineEnabled}
            sweepSettled={sweepSettled}
            schematicSvg={schematicSvg}
            schematicUnavailable={schematicUnavailable}
          />
    </>
  );

  // Mobile: knobs pane + a scroll-snap output carousel over the PINNED views
  // plus Info (#700 unit 4 — the roster lives behind the dots row's "⋯" sheet,
  // as the rail's picker does on desktop), instead of the desktop
  // thumbstrip/HUD stage. A distinct tree (not CSS-hiding the
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
            className={`mobile-carousel${outputStale ? " stale" : ""}`}
            ref={mobileCarouselRef}
            onScroll={onMobileCarouselScroll}
          >
            {screens.map((s) => (
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
                      onPlaneChange={pickPlane}
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
    <div className="app">
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
              renderCell={(v, size) => renderOutput(v, size, v === "antenna")}
            />
            {/* Grid mode has no single primary slide to float the HUD over
                (unit 3), so it anchors to the STAGE itself instead of one
                cell — same look (stage-readout family), one instance rather
                than per-cell. `.stage` is the positioned ancestor here, same
                role `.carousel-slide` plays in rail mode below. */}
            <SolveReadout
              className="stage-readout"
              result={result}
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
                    <ViewPanel
                      view={v.id}
                      size={thumbSize.width}
                      fill={false}
                      result={result}
                      // Same live trial point as the primary stage: the
                      // thumbnail is the same chart, so a frozen dot there
                      // would be the same defect at a smaller size.
                      liveZ={optRunning && optProgress ? optProgress.metrics : null}
                      preview={preview}
                      sweep={sweep}
                      converge={converge}
                      measured={measured}
                      pattern={pattern}
                      pinnedPatterns={[]}
                      measFreqMhz={measFreq}
                      sweepRunning={sweepRunning}
                      sweepSettled={sweepSettled}
                      convergeRunning={convergeRunning}
                      azElevDeg={azElevDeg}
                      elevAzDeg={elevAzDeg}
                      cameraProjection={cameraProjection}
                      showHeatmap={showHeatmap}
                      showEnvelope={showEnvelope}
                      multiFeed={effectiveMultiFeed}
                      schematicSvg={schematicSvg}
                      schematicUnavailable={schematicUnavailable}
                    />
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
                onPlaneChange={pickPlane}
              />
            </div>
          </>
        )}
        <div className="status">
          ws: {status}
          {stale && <span className="status-busy"> · solving…</span>}
        </div>
      </main>
    </div>
  );
}
