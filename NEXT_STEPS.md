# Next steps — antenna_designer

Living roadmap of what's done and what's left on the multi-engine refactor. Updated as work lands.

## Where we are

`antenna_designer` exposes two simulation backends behind a common `SimulationEngine` interface:

- **`PyNECEngine`** — the original NEC2/PyNEC path. Default backend. Supports free space / PEC / finite-Sommerfeld ground via the `ground=` parameter, multi-element arrays, transmission-line cards (`tl_card`), and arbitrary segment counts. This is the production backend; nothing here is restricted relative to the historical behaviour.
- **`PysimEngine`** — the pure-Python MoM solvers from the vendored `pysim/` submodule, accessed through a flat-wire-to-polyline geometry translator (`antenna_designer/geometry.py`). Selectable solver (`TriangularPySim` default, `SinusoidalPySim`, `BSplinePySim`, plus the large-N accelerators `HMatrixPySim` and `ArrayBlockPySim`) via the engine's `solver=` kwarg. `impedance()`, `impedance_sweep()`, `current_distribution()`, and `far_field()` are all supported across the bases.

Selection is uniform across the Python API and the CLI: `compare_patterns([engine_instance, ...])` for ad-hoc comparisons; `engine=` factory kwarg on `sweep` / `sweep_freq` / `sweep_gain` / `sweep_patterns` / `optimize`; `--engine pynec|pysim --ground free|pec|finite|finite:eps,sigma` on every analysis subcommand.

Antenna topology and circuit elements both translate to pysim now: open chains with arbitrary junctions, pure closed loops (driven, parasitic, or terminated two-port), multi-feed arrays, and port-based networks (transmission lines + lumped R/L/C) via `build_network()`. Cross-validation at design freq, free space, against PyNEC: ≤ 0.1 dBi peak directivity agreement on the dipole; ≤ 0.005 dBi on PEC ground; ~1–3 % R / a few Ω X on closed loops and multi-feed arrays. Cross-validation tests live in `tests/test_pysim_engine.py`.

## Geometry & circuit support — current state

Everything the translator previously rejected now works through `PysimEngine`. PyNECEngine was always unaffected.

| topology / feature | status |
|---|---|
| open chains, arbitrary junctions (degree-2/3 tees) | **done** — junction walker + KCL in `flat_wires_to_polylines` |
| pure closed loops (driven) | **done** — cut-at-port-edge (`8cc7945` lineage) |
| **parasitic loops** (cycle with no excited/port edge) | **done** (`8cc7945`) — cut an arbitrary edge; it stays a passive polyline anchoring the two cut-node junctions |
| **terminated / multi-port loops** (feed + termination) | **done** (`bcd64c4`) — extra port edges register as feeds by arclength inside the long-way polyline |
| multiple excitations (`ex_card` on >1 segment) | **done** — translator emits a `feeds` list; `impedance()` returns per-port Z; `impedance_sweep` returns `(n_k, n_feeds)` |
| transmission-line cards (`tl_card`), `impedance()` **and** `impedance_sweep()` | **done** (`c3535d4`, `1f899dc`) — multi-port Y extraction + nodal reduction; batched swept-k with frequency-dependent βl |
| port-based network spec (`build_network`): TL + lumped R/L/C | **done** (`a09d548`, `6be1f5f`) — see "Landed" below |
| differential / common-mode 2-wire TL (`DiffTL`) | **done** (`96336f8`) — pysim only; PyNECEngine raises `NotImplementedError` |
| loaded-antenna far field (efficiency from resistive loads) | **done** (`bcd64c4`) — directivity → gain when loads present |

No topology in `designs/` is currently rejected by the translator.

## Known limitations (genuinely open)

- **Strict `tl_card` PyNEC cross-validation.** `PysimEngine.impedance()` runs cleanly on `delta_looparray_with_tls`, but the numerical answer doesn't match PyNEC (PyNEC: −77 −18255j; pysim: +55 −3j). Both engines are self-consistent across frequency and TL-length sweeps — this is a genuine modeling-convention difference, not numerical noise. Root cause: NEC2's `tl_card` treats TL endpoints as **segment-level** ports while pysim's post-processing treats them as **basis-level** ports (delta-gap at the wire midpoint). On this design the central driver is a 10 cm gap effectively decoupled from the loops (`Y[loop, driver] ≈ 3e-7`), so the TL transformation dominates and the segment-vs-basis distinction blows up the result. The Y reduction itself is verified clean (Y symmetric, passive-port `I_ext=0` exact, `coeffs[m] = 1/Z` for single-port). Two optional follow-ups: (a) add a TL design where loop↔driver coupling is non-negligible and re-compare — agreement should tighten; (b) implement segment-averaging at TL endpoints to match NEC2's convention.
- **`PyNECEngine` does not implement `DiffTL`** — differential/common-mode TL is a pysim-only feature.
- **`finite` ground in pysim is basis-dependent** — the B-spline family solves finite-ground impedance with momwire's reflection-coefficient model (within ~2 Ω of NEC over 0.1–0.5λ heights); triangular/sinusoidal impedance still folds to the PEC image. The far field applies image + Fresnel with the real εr/σ on every basis. Use PyNECEngine for full Sommerfeld–Norton finite-ground impedance, especially below ~0.1λ heights.
- **No conductor loss in pysim** — wires are PEC; lossy-element efficiency needs PyNECEngine + `ld_card`.

## Landed (condensed changelog)

Historical branches, newest first. Each was a "next branch" entry; the engineering notes worth keeping are folded in.

- **Array-block solver** (`d136d68`) — `ArrayBlockPySim` integrated into `PysimEngine` (block-low-rank for phased arrays); shares BSpline segment parity (`a97f488`).
- **Port-based network spec** (`a09d548`, `6be1f5f`, `5bbfecc`, `4dff155`, `6e024bc`) — `build_network()` returns named logical ports (`PortAtEdge`, `PortVirtual`, `Driven`) and 2-port branches (`TL`, `DiffTL`, `Load`, `TwoPort`); every branch stamps a frequency-dependent 2×2 admittance into Y. `Load` (series/parallel R/L/C, incl. LC traps at exact resonance) lands via a Sherman-Morrison Y stamp. ~15 designs use it (G5RV, Zepp, rhombic, LPDA, T2FD, HB9CV, trap dipole/fan, Sterba variants, etc.). This unblocked lumped-element designs (matching networks, traps, bandpass filters) that previously couldn't be modeled at all. `build_tls()` retained as the legacy path; `NetworkReducer` extracted engine-agnostic (`93b5883`).
- **Differential TL** (`96336f8`, `14223c0`) — `DiffTL` 2-wire element with `transposed` flag (#89).
- **`tl_card` in PysimEngine** (`c3535d4`, `6ba7e37`, `1f899dc`, `6c3ddb2`) — multi-port Y extraction + nodal reduction for `impedance()`, then batched swept-k for `impedance_sweep()` (matches per-k `impedance()` to ~1e-11). Junction support in pysim's `compute_y_matrix`/`compute_y_matrix_swept` landed upstream (stevenmburns/pysim#78), replacing the N-solves workaround.
- **Closed-loop translator** — pure cycles open by cutting at the port edge (driven) or an arbitrary edge (parasitic); cut nodes become 2-entry junctions so pysim's KCL closes the loop. Surprise: bowtie is a single 10-edge cycle (shared corners stay degree-2), not a degree-3 case — falls out of the same path with no special handling.
- **Multi-feed PysimEngine** — translator emits `feeds: list[(polyline_idx, arclength, voltage)]`; `impedance()` returns per-port Z. Validated against PyNEC on invveearray/moxonarray/yagiarray (≤ ~4 Ω ΔR).
- **Cross-engine `compare_patterns` CLI** — `--engines pynec|pysim|pysim:triangular|sinusoidal|bspline`; builders × engines combine via numpy-style broadcasting (`broadcast_pairs`), not Cartesian product, so `--builders A B C --engines E1 E2 E3` zips into 3 chosen pairs. Covered by `tests/test_engine_spec.py`.
- **Named parameter variants** — Builder classes expose variants as `*_params` class attributes (`MappingProxyType`); CLI selector `builder[:variant]`; `default_params` is the unnamed default.
- **Engine infra** — `segment_parity` infra + parity coercion (`0d5c385`).

## Next branches (rough priority order)

1. **Far-field validation tests for network/loop designs.** `far_field()` works across all bases and loaded-antenna gain is correct (`bcd64c4`); what's missing is a directivity cross-check + regression tests on the tee-junction and network designs (hentenna, fandipole, trap_fan_dipole). Largely a "run `compare_patterns` and write the test" task.
2. **Strict `tl_card` PyNEC cross-validation** — see Known limitations. Optional; needs either a better-coupled TL test design or segment-averaging at TL endpoints.
3. **Variant compositing with per-flag overrides** (`--set length=5.2`) — deferred. Ad-hoc parameter sweeping still goes through `sweep` / `optimize`.
