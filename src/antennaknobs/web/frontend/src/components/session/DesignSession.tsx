import { useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  backendAllowed,
  backendDisplayLabel,
  backendSupportsGround,
  comboInappropriate,
  DEFAULT_BACKEND_OPTS,
  DEFAULT_SLOTS,
  isBSplineFamily,
  modelOptionsForRequest,
  normalizeBackend,
  resolveBackend,
  resolveSlotConfig,
  selectableBackends,
  type Backend,
  type BackendOptsMap,
  type Slot,
  type SlotConfig,
} from "../../lib/backends";
import {
  bandContaining as bandContainingIn,
  freqWindowCeiling as freqWindowCeilingFor,
} from "../../lib/bands";
import {
  groundSummaryLabel,
  resolveGroundModel,
  type FiniteGroundMethod,
  type GroundModel,
  type GroundType,
  type TerrainParams,
} from "../../lib/ground";
import { feedwiseRichardson, richardsonExtrap } from "../../lib/math";
import {
  defaultKnobOpt,
  findLinkedDesignFreq,
  groupExamplesForPicker,
  isGroup,
  linkedMeasFreqFor,
  overlaySchemaForVariant,
  seedDefaults,
  setValueAtPath,
  snapForExample,
  type BandSpec,
  type KnobOpt,
  type ParamValueBag,
  type SchemaItem,
  type SchemaParamSpec,
} from "../../lib/params";
import { planSweepFreqs } from "../../lib/sweep";
import {
  MOBILE_SCREENS,
  VIEWS,
  type Projection,
  type View,
} from "../../lib/view";
import type {
  ConvergeData,
  MeasuredData,
  NormCheckData,
  SolveRequest,
  SolveResponse,
  SweepData,
} from "../../lib/api";
import { BackendConfigModal } from "../backend/BackendConfigModal";
import { ParamForm } from "../params/ParamForm";
import {
  cutsWsSend,
  flushCutsWsPending,
  resolveCutsWsMessage,
  setCutsWsSend,
  type CutsWsMessage,
} from "../charts/cuts";
import type { PatternData, PatternMetrics } from "../charts/types";
import {
  ThemeContext,
  useFullscreen,
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
  SmithOverlayControls,
} from "../results/StageOverlays";
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
import { useDesignCatalog } from "./useDesignCatalog";
import { useMobileCarousel } from "./useMobileCarousel";
import {
  type OptimizeResult,
  type OptObjective,
  type OptPause,
  VfoPanel,
} from "./VfoPanel";

// Log-spaced segments-per-wire ladder for the convergence sweep. Hentenna's
// 8N+2 total segments at N=68 puts the dense LU at a ~550-cell matrix —
// still snappy at this N range on all backends, but enough span to see
// O(1/N) trajectories clearly. Same ladder across backends so the curves
// are directly comparable when the user switches slots.
const CONVERGE_N_VALUES: number[] = [8, 12, 17, 24, 34, 48, 68];

// Match the page's scheme: a wss:// upgrade is required on HTTPS pages (e.g. the
// deployed site behind Fly's force_https), where browsers block insecure ws://
// as mixed content. Plain ws:// only works on http:// (local dev).
const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`;

// One antenna design session: the entire left sidebar + right stage plus all
// the state, effects, and the WebSocket that drive them. The shell (`App`,
// below) mounts one instance per tab and passes `active` — true only for the
// visible tab. An inactive session stays mounted, so its inputs survive, but
// suspends its WebSocket, global key listeners, and background solves via the
// `active` gates threaded through the effects below. Theme is global and lives
// in the shell; the canvases here read it through ThemeContext.
export function DesignSession({ id, active }: { id: number; active: boolean }) {
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

  // --- Reactive knob optimiser (POST /optimize) ---
  // Live simulation: when on, knob/freq changes auto-solve (and the optimiser
  // runs). When off ("Paused"), edits update the geometry but the engine is held
  // — the user keeps changing the design, then clicks Live to resume and solve.
  // This replaces the old fire-and-forget "Cancel" on the solver-mismatch prompt,
  // which left the plots blank with no obvious way back. Defaults on.
  const [autoSim, setAutoSim] = useState(true);

  // Master enable + objective live in the compact control by meas-freq; per-knob
  // "vary" + extents + step live in each knob's right-click menu (knobOpt).
  const [optEnabled, setOptEnabled] = useState(false);
  const [optObjective, setOptObjective] = useState<OptObjective>("swr");
  const [knobOpt, setKnobOpt] = useState<Record<string, Record<string, KnobOpt>>>({});
  // Open knob context menu: which param + anchor position.
  const [knobMenu, setKnobMenu] = useState<{ name: string; x: number; y: number } | null>(
    null,
  );
  const [optRunning, setOptRunning] = useState(false);
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null);
  const [optError, setOptError] = useState<string | null>(null);
  // When something auto-pauses the optimizer, this holds *why* for a brief cue
  // (cleared on re-enable / after a few seconds): grabbing a knob marked for
  // optimization by hand ("changing X by hand"), or loading a new design/variant
  // ("loaded a new design").
  const [optPausedBy, setOptPausedBy] = useState<OptPause | null>(null);
  const optAbortRef = useRef<AbortController | null>(null);
  // Latest optEnabled mirrored into a ref so the design-load reset (effects keyed
  // on geometry, and selectVariant) can tell whether the optimizer was actually
  // running — to show the pause cue only then — without taking optEnabled as a
  // dep (which would re-run the reset on every toggle).
  const optEnabledRef = useRef(false);
  optEnabledRef.current = optEnabled; // mirror latest for the design-load reset
  // Per-knob settings persist per geometry (knobOpt is keyed by geometry); just
  // close any open menu / clear the last result / abort any in-flight run when
  // the antenna changes. The optimizer also *pauses* on a design switch — its
  // objective and marks belong to the design you left — but this design's marks
  // are kept (they're keyed by geometry), so returning restores them; only the
  // running toggle is switched off. Show the cue only if it was actually on.
  useEffect(() => {
    optAbortRef.current?.abort();
    setKnobMenu(null);
    setOptResult(null);
    setOptError(null);
    if (optEnabledRef.current) {
      setOptEnabled(false);
      setOptPausedBy({ kind: "load" });
    }
    // optEnabledRef is read (not a dep) on purpose — see its declaration.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry]);

  const {
    examples,
    examplesError,
    havePynec,
    terrainPresets,
    loadErrors,
    trustBusy,
    trustDesign,
  } = useDesignCatalog({ geometry, setGeometry, setParamValues });

  const currentExample = examples.find((e) => e.name === geometry);
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
  // Solver slots A / B / C — each one holds its own backend + options so
  // the user can switch between configured solvers with a single click
  // and tune each one independently from its gear menu.
  const [activeSlot, setActiveSlot] = useState<Slot>("A");
  const [slots, setSlots] = useState<Record<Slot, SlotConfig>>(DEFAULT_SLOTS);
  // Set once the user picks a backend by hand; after that we stop auto-seeding
  // the per-antenna recommended solver so their choice sticks.
  const backendTouchedRef = useRef(false);
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
  const [gearOpen, setGearOpen] = useState<Slot | null>(null);
  const activeConfig = slots[activeSlot];
  const backend = activeConfig.backend;
  const currentOpts = activeConfig.opts;
  const nPerWire = currentOpts.nPerWire;
  const wireRadius = currentOpts.wireRadius;
  // Stable hash of the active slot's config so useEffect can depend on it.
  const backendOptsKey = JSON.stringify(activeConfig);
  function updateSlotOpts(slot: Slot, patch: Partial<BackendOptsMap[Backend]>) {
    setSlots((prev) => ({
      ...prev,
      [slot]: {
        ...prev[slot],
        opts: { ...prev[slot].opts, ...patch } as BackendOptsMap[Backend],
      },
    }));
  }
  function setSlotBackend(slot: Slot, newBackend: Backend) {
    // Preserve segments-per-wire and wire-radius across the swap so the
    // user keeps their geometry-sizing choices when comparing models;
    // model-specific kwargs revert to that backend's defaults.
    setSlots((prev) => {
      const prevOpts = prev[slot].opts;
      const defaults = DEFAULT_BACKEND_OPTS[newBackend];
      return {
        ...prev,
        [slot]: {
          backend: newBackend,
          opts: {
            ...defaults,
            nPerWire: prevOpts.nPerWire,
            wireRadius: prevOpts.wireRadius,
          } as BackendOptsMap[Backend],
        },
      };
    });
  }
  function resetSlot(slot: Slot) {
    setSlots((prev) => ({
      ...prev,
      [slot]: resolveSlotConfig(DEFAULT_SLOTS[slot], havePynec),
    }));
  }
  // When the server reports no pynec-accel (#429), remap any slot still on
  // PyNEC — the default slot C, or a saved/URL slot — to the fallback backend,
  // so the panel never holds a backend the picker no longer offers (which the
  // /ws solve would silently run as momwire).
  useEffect(() => {
    if (havePynec) return;
    setSlots((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const s of Object.keys(prev) as Slot[]) {
        const resolved = resolveSlotConfig(prev[s], havePynec);
        if (resolved !== prev[s]) {
          next[s] = resolved;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [havePynec]);
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
  // Ground plane at z = 0 (model per backend; see groundType). ON by
  // default: this is an HF wire-antenna workbench, and the over-ground
  // picture (takeoff angle, ground-lobed elevation pattern, shifted Z)
  // is the decision-relevant one — free space is the idealization you
  // opt into. The whole catalog solves grounded (75/75 audit, all
  // designs above z=0) on the default B-spline refl-coef path.
  const [groundEnabled, setGroundEnabled] = useState(true);
  // Shared ground choice — one selector describing the GROUND (finite vs
  // PEC); every backend solves it as best it can (see the GroundType note).
  const [groundType, setGroundType] = useState<GroundType>("finite");
  // Finite-ground method; hidden (and inert) on backends with a single
  // finite model, but kept in state so it survives backend flips during
  // engine comparison. Defaults to "fast" — Sommerfeld is opt-in (it costs
  // seconds per solve on the B-spline backend).
  const [finiteGroundMethod, setFiniteGroundMethod] =
    useState<FiniteGroundMethod>("fast");
  // Terrain preset + knobs (groundType === "terrain"; momwire only). One
  // flat params object for both presets so values survive preset flips.
  const [terrainPreset, setTerrainPreset] = useState<string>("levee");
  const [terrainParams, setTerrainParams] = useState<TerrainParams>({});
  // Wire value derived for the server protocol (see GroundModel). A
  // terrain selection quietly degrades to the finite method on any future
  // backend without terrain support (all current ground-capable backends
  // have it — PyNEC via the #553 hybrid).
  const groundModel: GroundModel = resolveGroundModel(
    groundType,
    backend,
    finiteGroundMethod,
  );

  // Solve-effect dep for the terrain knobs: only bites while terrain is
  // the active model, so parked levee state never re-solves a flat-ground
  // setup (and vice versa).
  const terrainKey =
    groundModel === "terrain"
      ? JSON.stringify([terrainPreset, terrainParams])
      : "";

  // One-line tab-hover summary: design · solver N=segs · ground model.
  // Every backend honours the selected method (momwire >= 0.8.0), so the
  // wording is uniform; "free space" when ground is off or unsupported.
  const groundSummary = groundSummaryLabel(
    groundEnabled,
    backend,
    groundModel,
    terrainPreset,
  );
  const tabSummary = `${(currentExample?.label ?? geometry) || "new design"} · ${backendDisplayLabel(backend, currentOpts)} N=${nPerWire} · ${groundSummary}`;
  useEffect(() => {
    reportSummary(id, tabSummary);
  }, [id, tabSummary, reportSummary]);
  // Far-field cut angles. The azimuth plot slices the pattern at elevation
  // `azElevDeg`; the elevation plot slices the vertical plane at azimuth
  // bearing `elevAzDeg` (0° = +x). Defaults give the conventional views.
  const [azElevDeg, setAzElevDeg] = useState(15);
  // Default elevation-cut azimuth is 0° (+x) for every geometry: Yagi,
  // moxon, and hexbeam beam +x; the inverted V now runs its arms along
  // ±y so its broadside lobe also peaks at ±x.
  const [elevAzDeg, setElevAzDeg] = useState(0);

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
    const rec = normalizeBackend(
      preview?.default_backend ?? currentExample?.default_backend,
    );
    // Never surface a PyNEC recommendation the server can't honor (#429).
    return rec ? resolveBackend(rec, havePynec) : null;
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
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [rttMs, setRttMs] = useState<number | null>(null);
  // True whenever a main solve is outstanding (in flight or queued) — i.e. the
  // displayed analysis isn't current yet. `showBusy` is the *debounced* view of
  // it: the progress bar / panel dimming only appear once a solve outlasts
  // ~300 ms, so fast updates (cache hits, small designs) snap in cleanly
  // without a flash of busy chrome.
  const [solving, setSolving] = useState(false);
  const [showBusy, setShowBusy] = useState(false);
  const [sweep, setSweep] = useState<SweepData | null>(null);
  const [sweepRunning, setSweepRunning] = useState(false);
  // Smith-chart overlay toggles. Both are debounced sweeps that re-fire
  // whenever any antenna/backend parameter changes; gating them with these
  // checkboxes lets the user pause an expensive sweep (e.g. BSpline d=2
  // convergence on slow geometries) without leaving the Smith view.
  const [sweepEnabled, setSweepEnabled] = useState(true);
  const [convergeEnabled, setConvergeEnabled] = useState(false);
  // Measured overlay (issue #595): a VNA .s1p the user picks from their own
  // machine, drawn against the modeled locus. Deliberately client-side state —
  // the file is posted once to be parsed and is never stored server-side, which
  // also means the overlay survives nothing but this tab, by design.
  const [measured, setMeasured] = useState<MeasuredData | null>(null);
  const [converge, setConverge] = useState<ConvergeData | null>(null);
  const [convergeRunning, setConvergeRunning] = useState(false);
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
  const [normCheck, setNormCheck] = useState<NormCheckData | null>(null);
  // NEC's rp_card pattern, fetched on a debounce so we don't fire one per
  // slider tick. Overlaid on the cuts as a comparison line.
  const [pattern, setPattern] = useState<PatternData | null>(null);
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
  const [view, setView] = useState<View>("antenna");
  const [cameraProjection, setCameraProjection] = useState<Projection>("xy");
  // When the user switches antennas, reset the camera to that example's
  // natural starting view (declared on the backend via default_view).
  // Explicit user override sticks until the next geometry change.
  //
  // A deferred (user) design reports default_view === null — its real view is
  // auto-detected and arrives with the first geometry preview (handled where
  // the preview lands, below). Holding the current camera until then avoids
  // snapping to a wrong provisional view and flipping when the preview arrives.
  useEffect(() => {
    if (currentExample?.default_view) {
      setCameraProjection(currentExample.default_view);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentExample?.name]);

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
  // Cancel an IN-FLIGHT solve: stop waiting and discard its result. The server
  // keeps computing (its /ws loop is sequential and a running MoM solve can't be
  // interrupted), so this cancels the wait, not the computation.
  function cancelSolve() {
    if (lastSentSeqRef.current <= lastReceivedSeqRef.current) return; // nothing in flight
    // Mark every seq sent so far as cancelled: onmessage will advance the
    // received watermark for these but drop their results. A newer knob change
    // bumps lastSentSeq past this and solves again.
    canceledThroughSeqRef.current = lastSentSeqRef.current;
    syncSolving();
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkedDesignFreq, linkMeas]);
  // Antenna-canvas current visualization is split into two independent
  // toggles: the per-segment current-magnitude heatmap (wire color/width)
  // and the |I| envelope curve overlay. Either or both can be turned off;
  // the wires and feed marker are always drawn.
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [showEnvelope, setShowEnvelope] = useState(false);
  // Wire labels and feed names can crowd dense geometries (and PyNEC returns
  // many more wires than the momwire engines), so let them be toggled. Wire
  // labels default OFF — they're the noisiest, especially on PyNEC.
  const [showWireLabels, setShowWireLabels] = useState(false);
  const [showFeedNames, setShowFeedNames] = useState(true);
  // Layout branch. Desktop never reads isMobile except as the sizing hooks'
  // reattach key, so no desktop viewport is affected; the key makes both
  // hooks re-measure if the window is resized across the breakpoint.
  const { isMobile, orientation } = useIsMobile();
  const { ref: slideRef, size: chartSize } = useSlideSize(720, isMobile);
  const thumbStripRef = useRef<HTMLDivElement>(null);
  const thumbSize = useThumbColumnSize(thumbStripRef, 280, isMobile);

  const {
    mobileIndex,
    mobileCarouselRef,
    mobRef,
    mobChartSize,
    onMobileCarouselScroll,
    goToMobileScreen,
  } = useMobileCarousel({ isMobile, orientation, view, setView });
  // The pinned-pattern comparison table minimizes to a "{n} pinned" chip so
  // it can get off the chart — it grows a row per pin and swallows a phone
  // screen. Starts collapsed on mobile, expanded on desktop (the pre-existing
  // behavior); pinning always expands it so the new row is seen.
  const [compareCollapsed, setCompareCollapsed] = useState(isMobile);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      // Don't hijack arrows while a knob (e.g. the cut-angle dials) or a real
      // field is focused — those consume arrows to turn/edit their own value.
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.isContentEditable ||
          t.classList.contains("knob"))
      ) {
        return;
      }
      const idx = VIEWS.findIndex((v) => v.id === view);
      const next = e.key === "ArrowDown" ? (idx + 1) % VIEWS.length : (idx - 1 + VIEWS.length) % VIEWS.length;
      setView(VIEWS[next].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, active]);

  const sweepTimerRef = useRef<number | null>(null);
  const sweepAbortRef = useRef<AbortController | null>(null);
  const patternTimerRef = useRef<number | null>(null);
  const patternAbortRef = useRef<AbortController | null>(null);
  const convergeTimerRef = useRef<number | null>(null);
  const convergeAbortRef = useRef<AbortController | null>(null);
  const normCheckTimerRef = useRef<number | null>(null);
  const normCheckAbortRef = useRef<AbortController | null>(null);
  const previewAbortRef = useRef<AbortController | null>(null);
  // JSON of the request the currently-displayed preview wireframe was built
  // from. When Live is off no solve redraws the geometry, so the solve effect
  // refetches the preview itself on a param/variant/freq change — but only when
  // this signature actually changed, so it skips the redundant refetch right
  // after an antenna switch (whose preview the switch effect already built).
  const previewSigRef = useRef<string | null>(null);
  // Timestamp (performance.now) when the busy chrome last became visible, so
  // the reveal effect can enforce a minimum-visible window. null = not shown.
  const shownAtRef = useRef<number | null>(null);
  // Latest selected antenna, mirrored into a ref so the (mount-once) WebSocket
  // onmessage handler can drop responses for an antenna the user already
  // switched away from. Updated every render — cheap and always current.
  const geometryRef = useRef(geometry);
  geometryRef.current = geometry;

  const wsRef = useRef<WebSocket | null>(null);
  // Latest-wins /ws protocol counters. Every knob change is sent eagerly with a
  // monotonic `_seq`; the server keeps only the freshest queued request and may
  // skip-send superseded results, so the client orders and prunes by `_seq`. A
  // solve is outstanding iff more has been sent than received. These live in
  // refs so they survive StrictMode/HMR socket teardown — the counter must
  // never rewind below what's already been received.
  const seqRef = useRef(0); // last _seq assigned (monotonic, never reset)
  // Solve-lane session id (issue #382): one per workbench tab (A/B compare
  // tabs are separate App instances, hence separate sessions). The server
  // keys its single-lane scheduler on this — everything this tab asks for
  // runs one-at-a-time server-side, live solve first.
  const sessionIdRef = useRef<string>(
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `s-${Math.random().toString(36).slice(2)}`,
  );
  const lastSentSeqRef = useRef(0); // highest _seq put on the wire
  const lastReceivedSeqRef = useRef(0); // highest _seq received or implicitly acked
  const canceledThroughSeqRef = useRef(0); // drop rendering for _seq <= this
  const sentAtRef = useRef<Map<number, number>>(new Map()); // _seq → send time (RTT)
  const solveRafRef = useRef<number | null>(null); // trailing-edge rAF throttle handle

  function buildRequest(): SolveRequest {
    // ground_model is shared across backends (εr=10, σ=0.002 for the finite
    // models): PyNEC honours it directly; momwire's B-spline family solves
    // the finite models with its reflection-coefficient ground, while
    // Sinusoidal folds them to the PEC image solve (the server
    // ships the real εr/σ for the pattern either way).
    const groundActive = groundEnabled && backendSupportsGround(backend);
    const base: SolveRequest = {
      _session: sessionIdRef.current,
      geometry,
      variant: currentVariant,
      solver: backend === "pynec" ? "pynec" : "momwire",
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
    if (backend !== "pynec") {
      base.momwire_model = backend;
      const opts = modelOptionsForRequest(backend, currentOpts);
      // Enrichment now solves over ground (momwire #167: PEC image reaction,
      // refl-coef, and Sommerfeld), so this is no longer an error guard — it is
      // a UX choice. Enrichment is a validation-only knob that is redundant for
      // the d=2 basis (issue #565), so we keep it off when ground is active
      // rather than surface a control that can only match or worsen the grounded
      // production solve; the gear shows the validation note.
      if (isBSplineFamily(backend) && groundActive) {
        opts.use_singular_enrichment = false;
      }
      base.model_options = opts;
    }
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

  // Run the optimiser once: POST the current solve request + the free knobs
  // (from each knob's menu) and objective, then apply the returned params to the
  // knobs (re-solving via the normal onChange path). Warm-started from the
  // current values; a newer run aborts the previous so stale results are
  // dropped. Always uses the momwire engine server-side.
  async function runOptimize() {
    const settings = knobOpt[geometry] ?? {};
    const free = Object.entries(settings)
      .filter(([, o]) => o.vary)
      .map(([name, o]) => ({ name, min: o.optMin, max: o.optMax }));
    if (free.length === 0) return;
    optAbortRef.current?.abort();
    const ctrl = new AbortController();
    optAbortRef.current = ctrl;
    setOptRunning(true);
    setOptError(null);
    try {
      const resp = await fetch("/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
        body: JSON.stringify({
          ...buildRequest(),
          // Reactive runs are warm-started, so a modest eval cap keeps them snappy.
          optimize: { free, objective: optObjective, max_evals: 40 },
        }),
      });
      const data = await resp.json();
      if (ctrl.signal.aborted) return; // superseded by a newer run
      if (data.error) {
        setOptError(String(data.error));
      } else {
        setOptResult(data as OptimizeResult);
        for (const [name, val] of Object.entries((data as OptimizeResult).params)) {
          setParamAtPath([name], val);
        }
      }
    } catch (e) {
      if (!ctrl.signal.aborted) setOptError(String(e));
    } finally {
      if (optAbortRef.current === ctrl) {
        optAbortRef.current = null;
        setOptRunning(false);
      }
    }
  }

  // Reactive optimisation. When enabled with >=1 free knob, re-tune shortly
  // after the user pauses on any *fixed* input. The trigger is a signature of
  // everything the optimiser depends on EXCEPT the free knobs' values — the
  // optimiser writes those, so including them would loop. Turning it on produces
  // a fresh signature, so it also tunes immediately on enable.
  const optFixedSig = useMemo(() => {
    if (!optEnabled) return "";
    const settings = knobOpt[geometry] ?? {};
    const free = Object.entries(settings).filter(([, o]) => o.vary);
    if (free.length === 0) return "";
    const freeSet = new Set(free.map(([n]) => n));
    const fixed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(currentValues)) {
      if (!freeSet.has(k)) fixed[k] = v;
    }
    return JSON.stringify({
      geometry,
      objective: optObjective,
      backend,
      designFreq,
      measFreq,
      bounds: free.map(([n, o]) => [n, o.optMin, o.optMax]),
      fixed,
    });
    // currentValuesKey stands in for currentValues' contents in the deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    optEnabled,
    knobOpt,
    geometry,
    optObjective,
    backend,
    designFreq,
    measFreq,
    currentValuesKey,
  ]);

  useEffect(() => {
    // Paused (Live off) holds the optimiser too — it drives engine solves, so it
    // must respect the same gate as the main solve. Resuming re-runs this effect
    // (autoSim is a dep) and re-tunes.
    if (!optFixedSig || !autoSim || !active) return;
    const t = setTimeout(() => {
      runOptimize();
    }, 400);
    return () => clearTimeout(t);
    // runOptimize captured here reflects the state at this signature; re-running
    // only when the signature changes is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optFixedSig, autoSim, active]);

  // The "paused — changing X by hand" cue is a brief flash: clear it a few
  // seconds after it appears so it doesn't linger while Optimize stays off.
  useEffect(() => {
    if (!optPausedBy) return;
    const t = setTimeout(() => setOptPausedBy(null), 5000);
    return () => clearTimeout(t);
  }, [optPausedBy]);

  // The effective per-knob optimiser settings: the stored entry, or seeded from
  // the schema (extents = slider bounds, step = schema step, not varying).
  function knobOptFor(name: string): KnobOpt {
    const existing = knobOpt[geometry]?.[name];
    if (existing) return existing;
    return defaultKnobOpt(currentSchema, name);
  }
  function updateKnobOpt(name: string, patch: Partial<KnobOpt>) {
    const base = knobOptFor(name);
    setKnobOpt((prev) => ({
      ...prev,
      [geometry]: { ...(prev[geometry] ?? {}), [name]: { ...base, ...patch } },
    }));
  }

  // Close the knob menu on Escape.
  useEffect(() => {
    if (!knobMenu || !active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setKnobMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [knobMenu, active]);

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
  const controlsRef = useRef<SolveRequest>(buildRequest());

  // --- Pattern compare (pin / ghost overlay) --------------------------------
  // Pin the current pattern: snapshot the solve response (for the ghost trace)
  // into the shared cross-session pin list. The snapshot is frozen — it won't
  // change as the live knobs move, which is the whole point of comparing.
  function pinCurrentPattern() {
    if (!result) return;
    const label = `${currentExample?.label ?? geometry} @ ${measFreq.toFixed(2)} MHz`;
    addPin(label, result, controlsRef.current);
  }

  // Keep the live antenna's metrics fresh for the table, but only while a
  // comparison is actually on screen (≥1 pin and a pattern view) — the metrics
  // need a full far-field solve, so don't pay for it otherwise. Debounced so it
  // doesn't fire on every knob tick.
  const pinCount = pinnedPatterns.length;
  const comparing = pinCount > 0 && (view === "azimuth" || view === "elevation");
  useEffect(() => {
    if (!comparing || !result || !active) {
      setLiveMetrics(null);
      return;
    }
    let cancelled = false;
    const h = window.setTimeout(() => {
      fetchMetrics(controlsRef.current).then((m) => {
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
    setComboApproved(false);
  }, [geometry, backend, backendOptsKey]);

  useEffect(() => {
    if (!active) return;
    // Hold the first solve after an antenna switch until that antenna's preview
    // has landed (previewReady === geometry). Param/freq tweaks on the *same*
    // antenna keep solving freely — previewReady stays equal to geometry until
    // the next switch resets it to null.
    if (previewReady !== geometry) return;
    controlsRef.current = buildRequest();
    // Paused: keep controlsRef fresh (so resuming sends the latest design) but
    // don't solve, and suppress the combo warning — nothing is running to warn
    // about. Toggling Live back on re-runs this effect (autoSim is a dep) and
    // solves the current state.
    if (!autoSim) {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    active,
    autoSim,
    geometry, previewReady, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
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
    setResult(null);
    setPreview(null);
    setSolveError(null);
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
          // here, once per selection (this effect is keyed on `geometry`).
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry]);

  // Debounced sweep across measurement freq. Re-runs whenever any antenna
  // parameter changes. Single-band geometries sweep around designFreq, so
  // moving the measFreq slider doesn't re-sweep (the existing data already
  // covers the new slider position). Fan dipole sweeps around measFreq,
  // so measFreq is part of the deps there to re-anchor.
  useEffect(() => {
    // Cancel any in-flight sweep fetch immediately. Without this the
    // previous sweep keeps streaming for hundreds of ms (PyNEC ground at
    // 100 ms/point × 41 points = ~4 s) and starves the live /ws solve of
    // CPU — the user moves a slider but the next impedance update is
    // delayed behind the now-stale sweep finishing.
    sweepAbortRef.current?.abort();
    if (sweepTimerRef.current) {
      window.clearTimeout(sweepTimerRef.current);
    }
    setSweep(null);
    setSweepRunning(false);
    // Paused (Live off) holds the engine (issue #612): an enabled sweep must
    // not keep solving while the user edits. Clearing above + returning here
    // blanks the overlay while paused; resuming Live re-runs this effect
    // (autoSim is a dep) and restarts the sweep from the current design.
    if (!autoSim || !sweepEnabled || !active) {
      return;
    }
    // The 500 ms dwell only debounces network churn; ordering against the
    // live solve is the server lane's job now (live outranks sweeps).
    sweepTimerRef.current = window.setTimeout(runSweep, 500);
    return () => {
      if (sweepTimerRef.current) window.clearTimeout(sweepTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq,
    groundEnabled, groundModel,
    sweepEnabled,
    autoSim,
    active,
    // measFreq/measLocked drive the anchor now (meas_freq policy, or any
    // unlocked design — incl. fixed-geometry designs whose lock is inert),
    // so a meas-band change or dial turn re-runs the sweep.
    measFreq, measLocked,
    // A variant can override sweep_policy (variant_ui) without changing any
    // param — e.g. a band-locked variant. currentValuesKey wouldn't move then,
    // so depend on currentVariant directly to re-run the sweep on switch.
    currentVariant,
    // The poor-match gate: while it withholds, runSweep declines to issue the
    // batch; approving ("Solve anyway") or a new recommendation re-fires this
    // effect (issue #382 — replaces the old 200 ms re-poll loop).
    comboApproved, recommendedBackend,
  ]);

  // Debounced convergence sweep over segments-per-wire. Independent of the
  // freq sweep above: re-runs on any antenna/backend change, gated by its
  // own overlay checkbox. The active slot's `nPerWire` is *overridden* by
  // the ladder values for the duration of the sweep — the per-slot opts
  // stay untouched, so the live /ws solve keeps using the user's setting.
  useEffect(() => {
    convergeAbortRef.current?.abort();
    if (convergeTimerRef.current) {
      window.clearTimeout(convergeTimerRef.current);
    }
    setConverge(null);
    setConvergeRunning(false);
    // Held when Paused (issue #612) — see the sweep effect. autoSim is a dep so
    // resuming Live restarts the convergence sweep.
    if (!autoSim || !convergeEnabled || !active) {
      return;
    }
    // Debounce only; the server lane orders it behind the live solve.
    convergeTimerRef.current = window.setTimeout(runConverge, 500);
    return () => {
      if (convergeTimerRef.current) window.clearTimeout(convergeTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    convergeEnabled,
    autoSim,
    active,
    // Poor-match gate (see the sweep effect).
    comboApproved, recommendedBackend,
  ]);

  // Debounced far-field norm consistency check. Same shape as the converge
  // sweep: re-runs on any antenna/param change (which invalidates the norm),
  // gated by its own overlay checkbox. The server lane runs it after the
  // live solve (priority ordering), so it lands on that solve's cached
  // currents rather than forcing a re-solve.
  useEffect(() => {
    normCheckAbortRef.current?.abort();
    if (normCheckTimerRef.current) {
      window.clearTimeout(normCheckTimerRef.current);
    }
    setNormCheck(null);
    // Held when Paused (issue #612): the norm check re-solves, so it must not
    // run while the engine is held. autoSim is a dep — resuming Live re-runs it.
    if (!autoSim || !normCheckEnabled || !active) {
      return;
    }
    normCheckTimerRef.current = window.setTimeout(runNormCheck, 500);
    return () => {
      if (normCheckTimerRef.current) window.clearTimeout(normCheckTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    // The pattern integral runs over the facets, so terrain knob changes
    // invalidate it (unlike the impedance-only sweep/converge effects,
    // which are legitimately terrain-param-independent — every preset
    // shares the crest medium the impedance solve uses).
    terrainKey,
    normCheckEnabled,
    autoSim,
    active,
    // Poor-match gate (see the sweep effect).
    comboApproved, recommendedBackend,
  ]);

  // Debounced NEC pattern fetch. PyNEC only — for momwire there's no rp_card
  // equivalent. Tracks measurement freq too (unlike the impedance sweep).
  // Held off entirely over terrain (the rp pattern is flat-ground only) and
  // when the user switches the overlay off.
  useEffect(() => {
    if (patternTimerRef.current) window.clearTimeout(patternTimerRef.current);
    setPattern(null);
    if (
      !autoSim || // Paused holds the engine (issue #612) — no NEC re-solve.
      backend !== "pynec" ||
      !active ||
      !necOverlayEnabled ||
      groundModel === "terrain"
    ) {
      return;
    }
    patternTimerRef.current = window.setTimeout(() => {
      runPattern();
      patternTimerRef.current = null;
    }, 500);
    return () => {
      if (patternTimerRef.current) window.clearTimeout(patternTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    geometry, backend, backendOptsKey,
    currentValuesKey,
    designFreq, measFreq,
    groundEnabled, groundModel,
    necOverlayEnabled,
    autoSim,
    active,
  ]);

  async function runSweep() {
    // No competition with the live solve to time around anymore: the server's
    // per-session solve lane (issue #382) runs everything one-at-a-time with
    // the live solve first, so this just sends. While the poor-match gate is
    // withholding, don't issue batches of the very solves it's blocking — the
    // effect re-fires on approval (comboApproved is a dependency).
    if (solveWithheld()) return;
    sweepTimerRef.current = null;
    sweepAbortRef.current?.abort();
    const controller = new AbortController();
    sweepAbortRef.current = controller;

    // Sweep range, log-spaced — see planSweepFreqs for the resolution,
    // anchor, and band-lock policy this applies.
    const freqs = planSweepFreqs({
      backend,
      groundEnabled,
      groundModel,
      currentExample,
      currentVariant,
      measLocked,
      measFreq,
      designFreq,
      currentBands,
      freqWindowCeiling,
    });

    const body = {
      ...buildRequest(),
      freqs_mhz: freqs,
      // Lane metadata (issue #382): issued-at generation (a newer knob drag
      // supersedes this batch server-side) + the gate's approval, which the
      // server requires for a warned batch (poor-match combo backstop).
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setSweepRunning(true);
    const acc: SweepData = {
      freqs_mhz: [],
      z_re: [],
      z_im: [],
      feeds_z_re: undefined,
      feeds_z_im: undefined,
    };
    try {
      const resp = await fetch("/sweep", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`sweep failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const pt = JSON.parse(line);
          if (pt.done) continue;
          // A failed point/chunk ends the stream with {error} instead of
          // tearing the connection down (e.g. an approved poor-match combo
          // whose dense fill can't allocate). Keep whatever points landed.
          if (pt.error) {
            console.error("sweep error", pt.error);
            continue;
          }
          acc.freqs_mhz.push(pt.freq_mhz);
          acc.z_re.push(pt.z_re);
          acc.z_im.push(pt.z_im);
          // Multi-feed sweep records (bowtie) ship per-feed Z alongside
          // the primary. Allocate the per-feed buffers lazily on first
          // sight so single-feed sweeps stay on the original code path.
          if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
            if (!acc.feeds_z_re) acc.feeds_z_re = [];
            if (!acc.feeds_z_im) acc.feeds_z_im = [];
            acc.feeds_z_re.push(pt.feeds_z_re);
            acc.feeds_z_im.push(pt.feeds_z_im);
          }
          if (!controller.signal.aborted) {
            // New object so React re-renders the Smith chart per point.
            setSweep({
              freqs_mhz: acc.freqs_mhz.slice(),
              z_re: acc.z_re.slice(),
              z_im: acc.z_im.slice(),
              feeds_z_re: acc.feeds_z_re
                ? acc.feeds_z_re.map((row) => row.slice())
                : undefined,
              feeds_z_im: acc.feeds_z_im
                ? acc.feeds_z_im.map((row) => row.slice())
                : undefined,
            });
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("sweep error", e);
    } finally {
      if (sweepAbortRef.current === controller) {
        sweepAbortRef.current = null;
        setSweepRunning(false);
      }
    }
  }

  async function runConverge() {
    // Same as runSweep: the server lane serializes and prioritizes; only the
    // poor-match gate holds this back (effect re-fires on approval).
    if (solveWithheld()) return;
    convergeTimerRef.current = null;
    convergeAbortRef.current?.abort();
    const controller = new AbortController();
    convergeAbortRef.current = controller;

    // The active slot's nPerWire is irrelevant during a converge sweep —
    // n_values overrides it on the server. We strip `n_per_wire` from the
    // request anyway to make that explicit.
    const body = {
      ...buildRequest(),
      n_values: CONVERGE_N_VALUES,
      _gen: seqRef.current,
      _approved: approvedComboRef.current,
    };
    setConvergeRunning(true);
    const acc: ConvergeData = {
      n_values: [],
      z_re: [],
      z_im: [],
      z_re_extrap: null,
      z_im_extrap: null,
      feeds_z_re: undefined,
      feeds_z_im: undefined,
      feeds_z_re_extrap: undefined,
      feeds_z_im_extrap: undefined,
    };
    try {
      const resp = await fetch("/converge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) throw new Error(`converge failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const pt = JSON.parse(line);
          if (pt.done) continue;
          // A solver failure for one N (rare — degenerate small-N geometry)
          // is reported by the backend as {n_per_wire, error}; skip rather
          // than poisoning the trajectory.
          if (pt.error) continue;
          acc.n_values.push(pt.n_per_wire);
          acc.z_re.push(pt.z_re);
          acc.z_im.push(pt.z_im);
          // Multi-feed convergence records ship per-feed Z alongside the
          // primary; allocate the buffers lazily on first sight.
          if (Array.isArray(pt.feeds_z_re) && Array.isArray(pt.feeds_z_im)) {
            if (!acc.feeds_z_re) acc.feeds_z_re = [];
            if (!acc.feeds_z_im) acc.feeds_z_im = [];
            acc.feeds_z_re.push(pt.feeds_z_re);
            acc.feeds_z_im.push(pt.feeds_z_im);
          }
          const invN = acc.n_values.map((n) => 1 / n);
          acc.z_re_extrap = richardsonExtrap(invN, acc.z_re);
          acc.z_im_extrap = richardsonExtrap(invN, acc.z_im);
          // Per-feed Richardson Z* — see feedwiseRichardson.
          if (acc.feeds_z_re && acc.feeds_z_im) {
            const { feedsRe, feedsIm } = feedwiseRichardson(
              invN,
              acc.feeds_z_re,
              acc.feeds_z_im,
            );
            acc.feeds_z_re_extrap = feedsRe;
            acc.feeds_z_im_extrap = feedsIm;
          }
          if (!controller.signal.aborted) {
            setConverge({
              n_values: acc.n_values.slice(),
              z_re: acc.z_re.slice(),
              z_im: acc.z_im.slice(),
              z_re_extrap: acc.z_re_extrap,
              z_im_extrap: acc.z_im_extrap,
              feeds_z_re: acc.feeds_z_re
                ? acc.feeds_z_re.map((row) => row.slice())
                : undefined,
              feeds_z_im: acc.feeds_z_im
                ? acc.feeds_z_im.map((row) => row.slice())
                : undefined,
              feeds_z_re_extrap: acc.feeds_z_re_extrap
                ? acc.feeds_z_re_extrap.slice()
                : undefined,
              feeds_z_im_extrap: acc.feeds_z_im_extrap
                ? acc.feeds_z_im_extrap.slice()
                : undefined,
            });
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("converge error", e);
    } finally {
      if (convergeAbortRef.current === controller) {
        convergeAbortRef.current = null;
        setConvergeRunning(false);
      }
    }
  }

  async function runNormCheck() {
    // The pattern norm reuses the settled live solve (a server cache hit):
    // the lane's live-first priority guarantees that ordering now, no
    // client-side timing needed. Only the poor-match gate holds this back.
    if (solveWithheld()) return;
    normCheckTimerRef.current = null;
    normCheckAbortRef.current?.abort();
    const controller = new AbortController();
    normCheckAbortRef.current = controller;
    try {
      const resp = await fetch("/norm_check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...buildRequest(),
          _gen: seqRef.current,
          _approved: approvedComboRef.current,
        }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`norm check failed: ${resp.status}`);
      const data = await resp.json();
      if (controller.signal.aborted) return;
      if (!data.available) {
        setNormCheck(null);
        return;
      }
      const delta = 10 * Math.log10(data.pattern_norm / data.directivity_norm);
      setNormCheck({
        directivity_norm: data.directivity_norm,
        pattern_norm: data.pattern_norm,
        method: data.method,
        delta_db: delta,
        radiated_fraction: data.radiated_fraction ?? 0,
        radiation_efficiency: data.radiation_efficiency ?? 1,
      });
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("norm check error", e);
    } finally {
      if (normCheckAbortRef.current === controller) {
        normCheckAbortRef.current = null;
      }
    }
  }

  async function runPattern() {
    patternAbortRef.current?.abort();
    const controller = new AbortController();
    patternAbortRef.current = controller;
    try {
      const resp = await fetch("/pattern", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...buildRequest(), _gen: seqRef.current }),
        signal: controller.signal,
      });
      if (!resp.ok) throw new Error(`pattern failed: ${resp.status}`);
      const data = await resp.json();
      if (!data.available) {
        setPattern(null);
        return;
      }
      if (!controller.signal.aborted) setPattern(data as PatternData);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      console.error("pattern error", e);
    } finally {
      if (patternAbortRef.current === controller) patternAbortRef.current = null;
    }
  }

  // Mirror the seq counters into `solving` state so the UI can react. Called
  // wherever the sent / received / cancel watermarks move. A solve reads as
  // running when more has been sent than received — unless everything
  // outstanding was cancelled (lastSentSeq hasn't advanced past the cancel
  // watermark), in which case the wait is over even though a doomed response
  // is still coming.
  function syncSolving() {
    setSolving(
      lastSentSeqRef.current > lastReceivedSeqRef.current &&
        lastSentSeqRef.current > canceledThroughSeqRef.current,
    );
  }

  // Busy-chrome reveal with two guards:
  //  - dwell: only show once a solve has been outstanding >BUSY_DWELL_MS. 1 s
  //    is the classic "flow of thought" threshold — below it users tolerate the
  //    wait without feedback; at/above it the bar reassures them it's working.
  //    A solve that finishes sooner clears the timer in cleanup, so the bar
  //    never flips on for quick updates.
  //  - min-visible: once shown, keep it up at least BUSY_MIN_VISIBLE_MS so a
  //    solve that lands just past the dwell can't make it sub-perceptibly
  //    flash.
  const BUSY_DWELL_MS = 1000;
  const BUSY_MIN_VISIBLE_MS = 400;
  useEffect(() => {
    if (solving) {
      const t = window.setTimeout(() => {
        shownAtRef.current = performance.now();
        setShowBusy(true);
      }, BUSY_DWELL_MS);
      return () => window.clearTimeout(t);
    }
    // Solve finished. If the bar never showed (fast solve), hide immediately;
    // otherwise hold it for the remainder of the minimum-visible window.
    if (shownAtRef.current === null) {
      setShowBusy(false);
      return;
    }
    const remaining =
      BUSY_MIN_VISIBLE_MS - (performance.now() - shownAtRef.current);
    if (remaining <= 0) {
      shownAtRef.current = null;
      setShowBusy(false);
      return;
    }
    const t = window.setTimeout(() => {
      shownAtRef.current = null;
      setShowBusy(false);
    }, remaining);
    return () => window.clearTimeout(t);
  }, [solving]);

  // The progress bar (`showBusy`) honors the min-visible window so it can't
  // flash, but the *dimming* and the "solving…" label mean "what you're
  // looking at is stale" — so they must clear the instant the result lands,
  // even while the bar lingers out its minimum. `solving` flips false
  // immediately on result-land, so `showBusy && solving` is exactly that: dim
  // only after the dwell (showBusy) AND while genuinely still solving.
  const stale = showBusy && solving;

  function requestSolve() {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Can't send now. onopen resends controlsRef.current on (re)connect, so
      // the latest state is solved as soon as the socket comes up.
      return;
    }
    // Trailing-edge rAF throttle: coalesce a burst of knob changes within one
    // animation frame to a single send of the latest controls. Bounds upload to
    // ≤~60 msg/s during a drag and keeps localhost message churn near what the
    // old one-in-flight gate produced; the server's latest-wins mailbox squashes
    // whatever still piles up. The freshest value always wins within the frame.
    if (solveRafRef.current !== null) return;
    solveRafRef.current = requestAnimationFrame(() => {
      solveRafRef.current = null;
      const sock = wsRef.current;
      if (!sock || sock.readyState !== WebSocket.OPEN) return;
      const seq = ++seqRef.current;
      lastSentSeqRef.current = seq;
      sentAtRef.current.set(seq, performance.now());
      sock.send(JSON.stringify({ ...controlsRef.current, _seq: seq }));
      // Keep the preview signature current so that toggling Live *off* right
      // after a solve doesn't see a stale signature and needlessly refetch the
      // wireframe / drop the just-solved result — the solved geometry already
      // matches these controls.
      previewSigRef.current = JSON.stringify(controlsRef.current);
      syncSolving();
    });
  }

  useEffect(() => {
    if (!active) return;
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    // This socket's cuts sender (issue #551). A stable identity per socket
    // so the close/cleanup handlers only deregister their OWN sender — a
    // stale socket's late onclose must not tear down the transport a newer
    // socket just registered.
    const cutsSender = (msg: string): boolean => {
      if (ws.readyState !== WebSocket.OPEN) return false;
      ws.send(msg);
      return true;
    };
    const dropCutsSender = () => {
      if (cutsWsSend === cutsSender) setCutsWsSend(null);
      flushCutsWsPending();
    };
    ws.onopen = () => {
      setStatus("open");
      setCutsWsSend(cutsSender);
      // A prior socket's in-flight responses can never arrive on this new one.
      // Treat everything sent so far as received so `solving` can't stick true,
      // drop stale RTT timers, then send fresh current state. StrictMode and HMR
      // both tear the socket down + recreate it; the seq counters survive in
      // refs, so they must never rewind below what's already been received.
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      sentAtRef.current.clear();
      requestSolve();
    };
    ws.onclose = () => {
      setStatus("closed");
      dropCutsSender();
      // No solve can progress while disconnected — collapse the outstanding
      // count so the busy bar can't spin under a "closed" status (reconnect
      // re-arms it via onopen).
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      setSolving(false);
    };
    ws.onerror = () => {
      setStatus("closed");
      dropCutsSender();
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      setSolving(false);
    };
    ws.onmessage = (ev) => {
      const data: SolveResponse & Partial<CutsWsMessage> = JSON.parse(ev.data);
      if (data._kind === "cuts") {
        // Cuts sidecar response (issue #551) — never a solve; route it
        // before any _seq/solving bookkeeping.
        resolveCutsWsMessage(data as CutsWsMessage);
        return;
      }
      const seq = data._seq ?? 0;
      // One socket delivers in order, and the server may skip-send superseded
      // results — so a higher `_seq` implicitly acknowledges every lower one.
      // Ignore a straggler/duplicate at or below the received watermark.
      if (seq <= lastReceivedSeqRef.current) {
        syncSolving();
        return;
      }
      lastReceivedSeqRef.current = seq;
      // RTT from this seq's send; prune every acked entry (≤ seq) from the map —
      // seqs skipped server-side never get their own response, so a single
      // higher-seq arrival clears the whole run of them.
      const sentAt = sentAtRef.current;
      const t0 = sentAt.get(seq);
      if (t0 !== undefined) setRttMs(performance.now() - t0);
      for (const k of sentAt.keys()) {
        if (k <= seq) sentAt.delete(k);
      }
      // Cancelled through this seq: the user bailed on it (and everything
      // before). The watermark advanced above so `solving` can clear; just drop
      // the result rather than rendering it.
      if (seq <= canceledThroughSeqRef.current) {
        syncSolving();
        return;
      }
      // Drop a response for an antenna the user already switched away from: a
      // slow in-flight solve for the previous selection must not stomp the new
      // antenna's geometry preview (and briefly show the wrong antenna).
      const staleGeom = !!data.geometry && data.geometry !== geometryRef.current;
      if (!staleGeom) {
        if (data.error) {
          // A solve that raised (e.g. a user design's build_wires) — show the
          // message and clear stale plot data rather than rendering an empty
          // result on top of the last antenna.
          setSolveError(data.error);
          setResult(null);
        } else {
          setSolveError(null);
          setResult(data);
        }
      }
      syncSolving();
    };
    return () => {
      if (solveRafRef.current !== null) {
        cancelAnimationFrame(solveRafRef.current);
        solveRafRef.current = null;
      }
      dropCutsSender(); // ws.close() fires onclose async; don't leave a dead sender up
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

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
        />

        {gearOpen && (
          <BackendConfigModal
            slot={gearOpen}
            backend={slots[gearOpen].backend}
            backends={selectableBackends(havePynec)}
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
      requiredBackends={requiredBackends}
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
              backend={backend}
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
          />
    </>
  );

  // Mobile: knobs pane + a 5-screen scroll-snap output carousel, instead of
  // the desktop thumbstrip/HUD stage. A distinct tree (not CSS-hiding the
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
            className={`mobile-carousel${stale ? " stale" : ""}`}
            ref={mobileCarouselRef}
            onScroll={onMobileCarouselScroll}
          >
            {MOBILE_SCREENS.map((s) => (
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
          <div className="mobile-dots" aria-label="Output screens">
            {MOBILE_SCREENS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                className={i === mobileIndex ? "active" : ""}
                aria-label={`Show ${s.label}`}
                title={s.label}
                onClick={() => goToMobileScreen(i)}
              />
            ))}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">{controls}</aside>

      <main className="stage" aria-label="Antenna output views">
        {solveOverlays}
        <div className="thumbstrip" ref={thumbStripRef}>
          {VIEWS.filter((v) => v.id !== view).map((v) => (
            <button
              key={v.id}
              className="thumb"
              onClick={() => setView(v.id)}
              title={`Switch to ${v.label}`}
            >
              <div
                className="thumb-canvas"
                style={{ width: thumbSize, height: thumbSize }}
              >
                <ViewPanel
                  view={v.id}
                  size={thumbSize}
                  fill={false}
                  result={result}
                  preview={preview}
                  sweep={sweep}
                  converge={converge}
                  measured={measured}
                  pattern={pattern}
                  pinnedPatterns={[]}
                  measFreqMhz={measFreq}
                  sweepRunning={sweepRunning}
                  convergeRunning={convergeRunning}
                  azElevDeg={azElevDeg}
                  elevAzDeg={elevAzDeg}
                  cameraProjection={cameraProjection}
                  showHeatmap={showHeatmap}
                  showEnvelope={showEnvelope}
                  multiFeed={effectiveMultiFeed}
                />
              </div>
              <div className="thumb-label">{v.label}</div>
            </button>
          ))}
        </div>
        <div
          className={`carousel-slide${stale ? " stale" : ""}`}
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
          />
        </div>
        <div className="status">
          ws: {status}
          {stale && <span className="status-busy"> · solving…</span>}
        </div>
      </main>
    </div>
  );
}
