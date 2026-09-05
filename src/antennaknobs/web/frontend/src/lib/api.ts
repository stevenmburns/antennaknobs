import type { GroundModel, SoilParams } from "./ground";
import type { Projection } from "./view";

export type Wire = {
  label: string;
  knot_positions: [number, number, number][];
  knot_currents_re: number[];
  knot_currents_im: number[];
  // Optional finer-grained samples: knots interleaved with segment midpoints
  // (length 2*N_seg + 1). Present from momwire backends, absent from PyNEC.
  sample_positions?: [number, number, number][];
  sample_currents_re?: number[];
  sample_currents_im?: number[];
};

export type FeedEntry = {
  wire_index: number;
  knot_index: number;
  /** Exact 3D feed point; preferred over the knot lookup for the marker dot. */
  feed_position?: [number, number, number];
  z_re: number;
  z_im: number;
  v_re: number;
  v_im: number;
};

/** The two polar-chart traces, computed server-side (issue #547): the
 *  azimuth cut at elevation `az_elev_deg` and the vertical great-circle cut
 *  through azimuth `elev_az_deg`. Each is `n_dir` absolute-dBi samples with
 *  sample i at t = 2π·i/n_dir — the parameterisation FarFieldChart draws.
 *  Below-horizon samples clamp to `floor_dbi` (JSON can't carry -Infinity). */
export type PatternCuts = {
  az_elev_deg: number;
  elev_az_deg: number;
  n_dir: number;
  floor_dbi: number;
  azimuth: number[];
  elevation: number[];
  /** Explicit per-sample angles in degrees, present only when that cut was
   *  sampled NON-uniformly (adaptive refinement, issue #744). Absent means
   *  the uniform `t = 2π·i/n` parameterisation above — the contract every
   *  pre-#744 response and client relies on, so it must stay the default
   *  rather than become a required field. `n_dir` keeps reporting the
   *  uniform base resolution; a refined trace's own length governs. */
  az_angles_deg?: number[];
  elev_angles_deg?: number[];
};

/** One server-driven readout row (issue #712). Designs produce these from a
 *  duck-typed `readout_rows()` on the builder and the adapter validates them,
 *  so a NEW design feature — catalog or a user design in
 *  ~/.antennaknobs/designs — reaches the workbench readout with zero
 *  TypeScript. Nothing here may be interpreted per design:
 *   - `label`: display text, printed as-is.
 *   - `value`: a number (ReadoutsPanel formats it to fixed sig-figs), a short
 *     string (printed verbatim — the server already chose its wording), or
 *     null (an em-dash: a value that legitimately doesn't exist).
 *   - `unit`: appended after the value; the server owns the unit choice
 *     (mm vs m and so on), the client never converts.
 *   - `group`: small heading rows cluster under; null = ungrouped (first). */
export type ReadoutRow = {
  label: string;
  value: number | string | null;
  unit: string | null;
  group: string | null;
};

export type SolveResponse = {
  geometry: string;
  /** Which backend actually produced this response ("momwire" | "pynec").
   *  Not a strict union — kept a plain string so a retired/renamed backend
   *  echoed from an older cached response never fails to type-check. */
  solver?: string;
  /** True when this response was served from the server's solve cache
   *  rather than freshly computed; solve_ms is still the real cost of this
   *  particular lookup (see server.solve's cache-hit path). */
  cache_hit?: boolean;
  wires: Wire[];
  feed_wire_index: number;
  feed_knot_index: number;
  /** Exact 3D feed point for the primary feed; the marker dot uses this so
   *  it stays on the true feed regardless of solver-basis parity. */
  feed_position?: [number, number, number];
  /** One marker per physical feed port (issue #571). Multi-feed antennas whose
   *  drive is routed through build_network() (e.g. a lazy-H fed through a
   *  phasing harness) declare ui_params["feed_ports"] and get one entry per
   *  element centre here; single-feed designs get a single "feed" entry. */
  feed_positions?: { name: string; position: [number, number, number] }[];
  z_in_re: number;
  z_in_im: number;
  /** Multi-feed geometries (bowtie 1×2 array) populate this; single-feed
   *  geometries omit it. Primary feed is feeds[0] when present. */
  feeds?: FeedEntry[];
  design_freq_mhz: number;
  measurement_freq_mhz: number;
  lambda_design_m: number;
  solve_ms: number;
  /** Echoed from the request. The latest-wins /ws protocol orders and prunes
   *  responses by this; a higher `_seq` implicitly acks every lower one.
   *  Absent from geometry-preview payloads (they never carry a request seq). */
  _seq?: number;
  /** Polar-chart cuts at the request's cut angles. Absent when the response
   *  can't support them (no wires / no gain norm) or from geometry previews;
   *  new angles are fetched from POST /cuts (see useCutTraces). */
  cuts?: PatternCuts;
  /** Advisory key into the server's cuts-source cache (issue #551). When
   *  present, cut refetches send this ~100-byte id (over /ws or POST /cuts)
   *  instead of re-uploading the full solve body; a server-side miss
   *  (restart, eviction) falls back to the stateless full-body POST, so
   *  pinned ghosts from dead sessions still work. */
  solve_id?: string;
  directivity_norm?: number;
  ground?: boolean;
  height_m?: number;
  ground_eps_r?: number;
  ground_sigma?: number;
  ground_eps_im?: number;
  /** Packed faceted-terrain description when the solve ran over a terrain
   *  ground (issue #534). The facet data is opaque to the frontend — it
   *  rides back to the server inside /cuts bodies, where the per-facet
   *  physics lives — but the optional `marker` orientation hint is drawn
   *  on the polar charts (the preset's characteristic bearing + labels for
   *  its two sides; absent for azimuth-symmetric terrains). */
  ground_terrain?: {
    sectors?: unknown;
    marker?: { bearing_deg: number; label: string; opposite: string };
  };
  /** What the impedance solve actually used. Momwire: "refl-coef" |
   *  "pec-image" | "free"; PyNEC adds "sommerfeld". Authoritative — the
   *  readout's ground row shows this rather than re-deriving it from
   *  backend + groundType state. */
  ground_model_applied?: string;
  /** Array Block solver diagnostics (issue #613): which coupling path the
   *  last solve actually used. Only the Array Block engine populates this —
   *  every other engine/model leaves it absent, and the Info panel omits
   *  the row in that case. `reason` names the specific unmet FFT-gate
   *  condition (e.g. a height split under ground, or fewer than 16
   *  elements) and is null when `lattice_fft` is true. This never reflects
   *  a refused solve — the engine always falls back to a slower-but-correct
   *  path instead of erroring. */
  solver_diag?: {
    operator: "LatticeArrayBlock" | "ArrayBlock" | "HMatrix";
    lattice_fft: boolean;
    n_elem: number | null;
    n_shapes: number | null;
    reason: string | null;
  };
  /** Per-branch network dissipation from the MNA solve (issue #299):
   *  one entry per TL / TwoPort / Shunt / Load branch, in watts for the
   *  canonical 1 V drive. Absent or all-~0 for plain and lossless
   *  designs; input_power_w is the 100% reference. */
  /** `label` is the display name (after ui_params["budget_labels"] renames);
   *  `key` is the raw structural label, echoed back to /schematic so the
   *  chain drawing can place each row's burn by its "<path>: ..." prefix
   *  (issue #652). */
  power_budget?: { label: string; watts: number; path?: string; key?: string }[];
  input_power_w?: number;
  /** Fraction of input power actually radiated (1.0 unless the design has
   *  resistive loads, e.g. a terminated rhombic / T2FD, or a lossy network
   *  branch) — current_distribution() populates this on the engine. */
  radiation_efficiency?: number;
  /** Measurement plane (issue #652 c): the port this solve's Z/SWR/chart are
   *  referenced to, and every port the picker may offer (natural plane
   *  first). Absent for designs with no network or a multi-feed drive. */
  plane?: string;
  planes?: string[];
  /** Generic design-supplied readout rows (issue #712), rendered by
   *  ReadoutsPanel. Absent for the designs (nearly all of them) that define
   *  no `readout_rows()`, and absent rather than empty when every row a
   *  design produced was malformed or its producer raised. */
  readouts?: ReadoutRow[];
  /** Bespoke pre-#712 rigging tension/sag readout (issue #698 unit 3),
   *  surfaced under "rig" for a design that defines `rig_report()` —
   *  currently only dipoles.invvee_catenary. Kept alongside `readouts` for
   *  compatibility; absent for every design without a `rig_report()`.
   *  `rope_sag_m`/`rope_length_m` are null under the "halyard" rig_model
   *  (there is no rope segment). */
  rig?: {
    rig_model: string;
    apex_tension_n: number;
    apex_tension_lbf: number;
    end_tension_n: number;
    end_tension_lbf: number;
    horizontal_tension_n: number;
    wire_sag_m: number;
    rope_sag_m: number | null;
    rope_length_m: number | null;
    wire_end_height_m: number;
  };
  /** Wire-material totals (issue #318): absent for a design that doesn't
   *  declare `build_wire_material()`. */
  wire_length_m?: number;
  wire_weight_g?: number;
  k_meas_m_inv?: number;
  // V-specific
  arm_len_m?: number;
  // Yagi-specific
  driver_length_m?: number;
  reflector_length_m?: number;
  spacing_m?: number;
  // Moxon-specific
  long_m?: number;
  short_m?: number;
  tipspacer_m?: number;
  t0_m?: number;
  halfdriver_m?: number;
  // Hexbeam-specific
  radius_m?: number;
  t1_m?: number;
  // Fan dipole-specific
  n_bands?: number;
  band_lengths_m?: number[];
  band_freqs_mhz?: number[];
  slope?: number;
  cone_radius_m?: number;
  // Hentenna-specific
  half_width_m?: number;
  top_height_m?: number;
  mid_offset_m?: number;
  // Bowtie-1×2-array-specific
  y_m?: number;
  z_m?: number;
  length_m?: number;
  del_y_m?: number;
  phase_lr_deg?: number;
  /** Per-geometry SWR / Smith chart reference impedance. Falls back to
   *  50 Ω when the server doesn't supply one. Bowtie array returns 100 Ω
   *  because each element is designed for a 100 Ω feedline. */
  z0_ohms?: number;
  /** Geometry-derived UI hints folded into the solve/geometry response.
   *  User designs defer these (the builder runs lazily on selection), so the
   *  authoritative values arrive here rather than on the /examples descriptor;
   *  prefer them over the example fields when present. */
  multi_feed?: boolean;
  default_view?: Projection;
  /** Recommended solver backend for this design (e.g. "arrayblock" for grid
   *  arrays). Carried on the geometry preview so the frontend can seed the
   *  backend from it and *then* fire the first solve, instead of the descriptor
   *  racing the preview. Absent / null = no recommendation. Plain string —
   *  may name a retired backend; normalizeBackend before use. */
  default_backend?: string | null;
  /** Set when the solve/geometry request failed — e.g. a user design's
   *  build_wires() raised. Carries a short, formatted message (type + file +
   *  line). Mutually exclusive with a normal result payload. */
  error?: string;
};

export type SolveRequest = {
  geometry: string;
  /** Which `<name>_params` dict on the Builder to seed from. Omitted
   *  → backend falls back to default_params. */
  variant?: string;
  solver: "momwire" | "pynec" | "nec5";
  /** A momwire model name from the served roster (#628) — a plain string,
   *  not a union: the server owns the registry and validates it, and a
   *  third copy of the roster here is exactly the drift #628 removes. */
  momwire_model?: string;
  model_options?: Record<string, unknown>;
  n_per_wire: number;
  design_freq_mhz: number;
  measurement_freq_mhz: number;
  wire_radius: number;
  ground: boolean;
  ground_fast: boolean;
  ground_model?: GroundModel;
  /** Terrain preset params when ground_model === "terrain" (issue #534);
   *  the server clamps every number, so raw knob state is fine to send. */
  terrain?: { preset: string; [key: string]: number | string };
  /** Soil constants for the finite ground models (issue #1173). Omitted
   *  entirely when ground is off or the model is pec/terrain — absence is
   *  what makes a pre-#1173 request and a default-soil request the same
   *  bytes, so neither invalidates the other's cached sweep. The server
   *  clamps both numbers, so raw knob state is fine to send. */
  soil?: SoilParams;
  /** Cut angles for the server-attached polar traces (issue #547). */
  az_elev_deg?: number;
  elev_az_deg?: number;
  /** Measurement plane to solve at (issue #652 c). Omitted = the design's
   *  natural source port. A non-natural plane re-solves with the upstream
   *  chain disconnected — a VNA clipped on at that port. */
  plane?: string;
  // V
  angle_deg?: number;
  halfdriver_factor?: number;
  // Yagi
  driver_length_factor?: number;
  reflector_length_factor?: number;
  spacing_wavelengths?: number;
  n_directors?: number;
  director_spacing_wavelengths?: number;
  director_size_factor?: number;
  // Moxon (+ hexbeam: hexbeam reuses tipspacer_factor and t0_factor too)
  aspect_ratio?: number;
  tipspacer_factor?: number;
  t0_factor?: number;
  // Fan dipole
  n_bands?: number;
  band_lengths_m?: number[];
  band_freqs_mhz?: number[];
  band_halfdriver_factors?: number[];
  slope?: number;
  cone_radius_m?: number;
  // Hentenna
  width_factor?: number;
  top_height_factor?: number;
  mid_height_factor?: number;
  // Bowtie 1×2 array (slope shared with fan_dipole tip-droop convention)
  length_factor?: number;
  del_y_m?: number;
  phase_lr_deg?: number;
  /** Monotonic per-tab sequence number for the latest-wins /ws protocol. The
   *  server echoes it back and keeps only the freshest queued request. */
  _seq?: number;
  /** Solve-lane session id (issue #382): one per workbench tab, minted at
   *  mount. The server serializes all of a session's solve-producing work
   *  (live solve, sweeps, converge, norm-check, pattern) on one lane. */
  _session?: string;
  /** Batch-request generation: the value of the `_seq` counter when the batch
   *  was issued, so a newer knob drag (higher live `_seq`) supersedes it. */
  _gen?: number;
  /** Set when the user clicked through the poor-match gate ("Solve anyway");
   *  the server refuses warned batches without it. */
  _approved?: boolean;
};

export type SweepData = {
  freqs_mhz: number[];
  z_re: number[];
  z_im: number[];
  /** Multi-feed geometries (bowtie 1×2 array) populate these; each row is a
   *  per-feed Z array of length n_feeds. Index alignment with freqs_mhz.
   *  Single-feed geometries omit them and the Smith chart falls back to
   *  the legacy single-trajectory render driven by z_re/z_im. */
  feeds_z_re?: number[][];
  feeds_z_im?: number[][];
};

/** A measured VNA sweep uploaded for the measured-vs-modeled overlay
 *  (issue #595). Parsed server-side by /measured — the browser never reads
 *  Touchstone itself, so there is exactly one parser to disagree with.
 *  Carried as impedance (like every other Z on this chart) so the chart
 *  re-references it to its own z0; `z0_file` is kept only to report the
 *  calibration the file declared. */
export type MeasuredData = {
  label: string;
  z0_file: number;
  freqs_mhz: number[];
  z_re: number[];
  z_im: number[];
};

export type ConvergeData = {
  n_values: number[];
  z_re: number[];
  z_im: number[];
  // Richardson extrapolation Z(1/N) → Z(0). Filled once ≥3 points are in.
  z_re_extrap: number | null;
  z_im_extrap: number | null;
  /** Multi-feed convergence — per-N per-feed Z. Outer index aligns with
   *  n_values; inner index aligns with feed order. Single-feed
   *  geometries omit these and the chart falls back to the legacy
   *  single-trail render driven by z_re/z_im. */
  feeds_z_re?: number[][];
  feeds_z_im?: number[][];
  /** Per-feed Richardson Z*. Indexed by feed order, same length as a row
   *  of feeds_z_re. Entries are null until ≥3 sample points are in. */
  feeds_z_re_extrap?: (number | null)[];
  feeds_z_im_extrap?: (number | null)[];
};

// Result of the far-field norm consistency check: the live gain norm comes
// from the circuit side (input power); `pattern_norm` recomputes it from the
// field side (closed-form pattern integral). `delta_db` is the gap between
// them — the solver's power-balance error (NEC's "average gain" diagnostic),
// rendered as the offset between the solid and dotted lobes. Over a finite
// ground the same ratio, with the structural efficiency folded back out,
// is the third efficiency ledger: `radiated_fraction` = P_radiated/P_input
// including real ground absorption (issue #339) — the norm check restated
// as a percentage.
export type NormCheckData = {
  directivity_norm: number;
  pattern_norm: number;
  method: string;
  delta_db: number;
  radiated_fraction: number;
  radiation_efficiency: number;
};
