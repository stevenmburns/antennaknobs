export type View = "antenna" | "azimuth" | "elevation" | "smith" | "schematic" | "gamma" | "vswr";

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
};
export const VIEWS: ViewMeta[] = [
  { id: "antenna", label: "Antenna", defaultPinned: true },
  { id: "azimuth", label: "Azimuth (xy)", defaultPinned: true },
  { id: "elevation", label: "Elevation (yz)", defaultPinned: true },
  { id: "smith", label: "Smith", defaultPinned: true },
  { id: "schematic", label: "Schematic", defaultPinned: false },
  // Sweep-derived views (issue #700 unit 5, docs/plan-view-rail-scaling.md
  // items 6/7): the sweep data already flows to the Smith chart, so these
  // are a second and third presentation of it, not a new data path. Ship
  // unpinned like schematic — the founding four stay the only defaults.
  // "gamma" keeps its id (persisted pin sets store ids) but presents as S11
  // in dB — the VNA/NanoVNA log-magnitude convention, which is what this
  // audience reads; linear |Γ| only ever appears as a Smith-chart radius.
  { id: "gamma", label: "S11 (dB) vs freq", defaultPinned: false },
  { id: "vswr", label: "VSWR vs freq", defaultPinned: false },
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
export const dot3 = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross3 = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
