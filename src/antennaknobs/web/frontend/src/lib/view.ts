export type View =
  | "antenna"
  | "azimuth"
  | "elevation"
  | "smith"
  | "schematic"
  | "gamma"
  | "vswr"
  | "files";

// The view registry's metadata half. The render half — one function per id —
// lives in components/results/viewRegistry.tsx, keyed by these same ids:
// lib/ stays component-free, so the two halves cannot be one object here.
// Adding a view = one entry below + one render entry there (the render map is
// a Record<View, …>, so the compiler names the gap).
export type ViewMeta = {
  id: View;
  label: string;
  // Whether the view starts in the user's pinned set — the desktop rail is
  // `pinned \ {active}`, not the whole roster (docs/plan-view-rail-scaling.md).
  // Read once, by useViewPrefs, to seed a first run; after that the user's
  // stored set wins, so flipping this only affects new users.
  defaultPinned: boolean;
  // Whether this view goes STALE for the duration of an optimizer run (#773).
  //
  // A run never touches the knobs until it finishes, so anything drawn from
  // the last solve keeps describing the pre-run design while the readout
  // ticks through candidates — a screen of mixed provenance, where the number
  // and the picture disagree and nothing says so. Views that are entirely
  // pre-run dim (the same `.stale` treatment a slow solve already uses);
  // views carrying live or still-accurate content must not.
  //
  // Required, not defaulted: a new view's answer is never obviously false, so
  // the compiler should make someone decide.
  staleWhileOptimizing: boolean;
  // Whether the stage's solve readout starts minimized on this view, until the
  // viewer chooses otherwise (useViewPrefs remembers that per view). True only
  // where the view's own content already carries the numbers and the floating
  // card would cover it. Required, for the same reason as the field above.
  readoutStartsCollapsed: boolean;
};
export const VIEWS: ViewMeta[] = [
  // Geometry and currents are both drawn from the last solve, i.e. the knobs
  // as they stand — which is not the candidate being evaluated.
  { id: "antenna", label: "Antenna", defaultPinned: true, staleWhileOptimizing: true, readoutStartsCollapsed: false },
  { id: "azimuth", label: "Azimuth (xy)", defaultPinned: true, staleWhileOptimizing: true, readoutStartsCollapsed: false },
  { id: "elevation", label: "Elevation (yz)", defaultPinned: true, staleWhileOptimizing: true, readoutStartsCollapsed: false },
  // NOT stale: the dot follows the run's per-eval frames (ViewRenderProps'
  // liveZ), so this is the one view that is live. Its sweep locus is still
  // pre-run, which is why the live point draws as a hollow ring rather than
  // claiming to be a settled solve.
  { id: "smith", label: "Smith", defaultPinned: true, staleWhileOptimizing: false, readoutStartsCollapsed: false },
  // NOT stale: built from `build_network()` on the CURRENT knob values, and
  // an optimizer run leaves those alone until it applies its result — so the
  // drawing on screen stays accurate for the whole run.
  { id: "schematic", label: "Schematic", defaultPinned: false, staleWhileOptimizing: false, readoutStartsCollapsed: false },
  // Sweep-derived views (issue #700 unit 5, docs/plan-view-rail-scaling.md
  // items 6/7): the sweep data already flows to the Smith chart, so these
  // are a second and third presentation of it, not a new data path. Ship
  // unpinned like schematic — the founding four stay the only defaults.
  // "gamma" keeps its id (persisted pin sets store ids) but presents as S11
  // in dB — the VNA/NanoVNA log-magnitude convention, which is what this
  // audience reads; linear |Γ| only ever appears as a Smith-chart radius.
  // Frequency sweeps of the pre-run geometry: the whole curve is stale for
  // the duration, and unlike the Smith chart there is no live point on them.
  { id: "gamma", label: "S11 (dB) vs freq", defaultPinned: false, staleWhileOptimizing: true, readoutStartsCollapsed: false },
  { id: "vswr", label: "VSWR vs freq", defaultPinned: false, staleWhileOptimizing: true, readoutStartsCollapsed: false },
  // The Files view (AK#1428): the design's source file and, on a NEC-5 or
  // NEC-2 slot, the deck that engine ran plus its printout. Unpinned like
  // schematic. NOT stale: the source is the file as it stands, and a deck or
  // printout spells out its own inputs, so neither can be mistaken for the
  // candidate an optimizer run is evaluating.
  // Its readout starts minimized: the printout carries R and X itself, and the
  // floating card would sit on top of the text.
  {
    id: "files",
    label: "Files",
    defaultPinned: false,
    staleWhileOptimizing: false,
    readoutStartsCollapsed: true,
  },
];

// Id → metadata, for the consumers that hold a list of ids in the USER's
// order (the pinned set) rather than registry order and still need labels.
// The cast is the Record<View, …> exhaustiveness claim VIEWS already owes —
// viewRegistry.test.tsx pins one entry per union member.
export const VIEW_META = Object.fromEntries(
  VIEWS.map((v) => [v.id, v]),
) as Record<View, ViewMeta>;

export type MobileScreen = { id: View | "info"; label: string };

// The mobile output carousel's screens: the user's PINNED views, in pin order,
// plus a dedicated Info screen for the solve readout (which floats as a HUD on
// desktop but deserves its own page on a phone). "info" stays out of the
// `View` union on purpose — `view` (and every data effect keyed on it) only
// ever holds a chart view; the Info screen leaves `view` parked on the last
// chart.
//
// Pinned, not the registry (#700 unit 4, docs/plan-view-rail-scaling.md): the
// carousel index maps onto `pinned`, so an unpinned view has no page and no
// dot, and the roster can grow past what a thumb-swipe stack can carry. Info
// is always the TRAILING page, so its index moves with every pin — every
// index compare in useMobileCarousel is against pinned.length for that reason.
export function mobileScreens(pinned: View[]): MobileScreen[] {
  return [...pinned.map((id) => VIEW_META[id]), { id: "info", label: "Info" }];
}

// Antenna-canvas camera projections. Pick two world axes to map to canvas
// (horizontal, vertical) and project. The hidden axis is the camera ray.
export type Projection = "xy" | "xz" | "yz" | "iso";
export type Vec3 = readonly [number, number, number];
// Each projection is an orthonormal screen basis: `h` maps to canvas-right,
// `v` to canvas-up, and the camera ray (toward the viewer) is h×v. The three
// axis-aligned views keep their original semantics (h/v pick world axes);
// "iso" is the classic isometric from the (+1,+1,+1) corner — x recedes to
// the lower-left, y to the lower-right, z stays up — so ground-plane layout
// and vertical structure are readable in one view.
const ISO_S2 = Math.SQRT1_2; // 1/√2
const ISO_S6 = 1 / Math.sqrt(6);
export const PROJECTIONS: { id: Projection; label: string; h: Vec3; v: Vec3 }[] = [
  { id: "xy", label: "Top (xy)",   h: [1, 0, 0], v: [0, 1, 0] },
  { id: "xz", label: "Front (xz)", h: [1, 0, 0], v: [0, 0, 1] },
  { id: "yz", label: "Side (yz)",  h: [0, 1, 0], v: [0, 0, 1] },
  { id: "iso", label: "Iso", h: [-ISO_S2, ISO_S2, 0], v: [-ISO_S6, -ISO_S6, 2 * ISO_S6] },
];
// Where the antenna canvas is looking: the zoom/pan viewport (zoom = 1, pan =
// 0 IS the auto-fit view, so zoom composes on top of the fit as a multiplier),
// plus the design that framing was aimed at.
//
// A session holds one of these and lends it to the canvas (AK#1542). The
// canvas can hold its own, but only for as long as it is mounted, and the
// stage unmounts the view it is not showing: without a camera from outside,
// looking at the Smith chart and coming back put the antenna at fit again,
// after the work of finding the detail you were inspecting.
//
// `fitFor` is what still makes an antenna SWITCH re-fit. It records the
// geometry the numbers were aimed at, so the canvas can tell a design switch
// (re-fit — the old framing means nothing for new wires) from a remount of
// the same design (keep). "" before anything has been drawn.
export type CanvasCamera = {
  zoom: number;
  panX: number;
  panY: number;
  fitFor: string;
};

export const fitCamera = (): CanvasCamera => ({
  zoom: 1,
  panX: 0,
  panY: 0,
  fitFor: "",
});

export const dot3 = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross3 = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
