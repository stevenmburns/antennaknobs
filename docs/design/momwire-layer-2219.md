# The momwire layer (`antennaknobs.mw`, AK#2219)

`antennaknobs.mw` is antennaknobs' one boundary with momwire's internals.
Code that only antennaknobs needs from momwire lives here and ships on
antennaknobs' release cycle, not momwire's. The motivation is in the issue:
two pure-Python fixes in two days (the Johnson line, momwire#1855; razor's
swept port count, momwire#1861) each paid momwire's full release cycle,
which exists to protect its C++ kernels and signed executables, and neither
touched them.

## Rules

- The layer imports momwire, numpy and its own modules, and nothing else
  from antennaknobs. `tests/test_momwire_private_imports.py`
  (`test_the_momwire_layer_imports_nothing_else_from_antennaknobs`) holds
  that, so momwire's CI can import the layer without antennaknobs' web or
  engine dependencies.
- `antennaknobs.mw._private` is the only module in antennaknobs that
  imports a private momwire name (`test_every_private_import_is_in_the_momwire_layer`).
  Its import list is therefore the exact list of names momwire would need
  to publish to retire it (phase 2).
- The layer's tests (`tests/test_mw_layer_2219.py`) import only momwire,
  numpy and the layer, so momwire's CI can run them against a momwire PR.

## The contract with momwire core

What the layer relies on, and what core keeps:

| the layer uses | core's side | today |
|---|---|---|
| `swept_y(solver, k_array)` | a per-frequency `PortSolution` stream (`_port_solutions_swept`), each with its own `y` | private generator; phase 2 publishes it |
| `eps_tilde`, `lambda_medium`, `k_medium` | `momwire._ground_refl`, `momwire._sommerfeld_below` | private |
| `couplings()` | `momwire._couplings.COUPLINGS` (momwire#885) | private |
| `feature_registry()`, `feature_certified(name)` | `momwire._features` (momwire#1869) | private |

Core keeps everything its executables and portal run: the deck path, every
solver's fill and solve, its own network reducer (the NEC-5 drop-in stamps
its `TL`/`NT` cards through it), and the swept solution stream, since
batched swept fills are where the accelerated speed is. antennaknobs no
longer reduces on core's reducer at all; see the next section.

## `networks`: antennaknobs' general network reducer

`antennaknobs.mw.networks` is a copy of `momwire.networks` (the spec, the MNA
core and `NetworkReducer`, four modules) taken at momwire commit 03a2357e
(momwire 0.89.0), phase 3 stage 1 of AK#2219. From that commit on it is
antennaknobs' code. Its package docstring lists every difference from
upstream:
- `C_LIGHT` is the SI literal.
- `_lapack.matmul` is written `a @ b`, which is what that seam returns when
  no host process publishes a BLAS.
- AK's lint: B905 `strict=True` on seven zips, and SLOT001 noted on the
  two keyed tuple subclasses.

The copy imports nothing from momwire.

`antennaknobs.network` and `antennaknobs.network_reduce` re-export it, so
every design and engine reduces on it. No momwire function receives an
antennaknobs network: momwire's deck path builds its own from cards. The
four flattening and RLC helpers the layer used to re-export from momwire
privates (`series_rlc_impedance`, `parallel_rlc_admittance`,
`branch_port_refs`, `rewrite_branch`) are the copy's own now.

The gate is `tests/test_mw_networks_ab_2219.py`. It builds one description
from each namespace's classes and compares the two reductions by bytes:
- driven Z and Γ;
- `apply_branches`' system and solution;
- `excited_state`'s voltages, efficiency, input power and budget rows;
- refusals.

It covers every branch, port and source class, at four frequencies and both
c values. When the copy is meant to move a number (a fix, a new model), the
case that moves is updated there on purpose.

### Sparse MNA (AK#2241, stage 2)

The copy now differs from momwire by one path. At and above
`_reduce.SPARSE_MIN_UNKNOWNS` = 200 MNA unknowns (n node voltages + m Group-2
branch currents: the matrix dimension, which is what both solves' costs scale
with), the system is assembled sparse and solved by SuperLU; below it, it is
momwire's dense `zgesvx` path, bit for bit.
- Assembly: the node block is recorded (`_GStamps`) instead of written into a
  dense `G`, then either replayed onto zeros with the old in-place operations
  (dense), or emitted as COO triples (sparse). The antenna's `Y_real` and its
  floating-port congruence are dense only over the real ports and the
  floating ports' "-" nodes. Every Group-2 element, termination and coupling
  becomes triples (`_group2_triples`), summed into CSC.
- Solve: `zgesvx`'s steps, on CSC. Equilibration as `zgeequ` computes and
  `zlaqge` applies it (rows or columns only when they spread by more than
  10x; always scaling both reported rcond up to 7x off on the ladder).
  `splu`, then `zgerfs`-style iterative refinement. rcond as `zgecon`
  estimates it, with LAPACK's deterministic Hager iteration (`zlacn2`), not
  `onenormest`'s random starts. Same thresholds, message and `diagnose`.
- Nothing outside `solve` reads `system.A`, so every readout (`driven_impedance`,
  `reflection`, `excited_state` and its budget, probes, the engines' per-k
  `_reduce_at`) works unchanged on either path.
- Measured crossover: about 80 unknowns, on an RLCG ladder and on a chain of
  station networks. 200 is 2.5x that and 6x the catalog's largest network
  (34), so every shipped design stays dense. The A/B's cases are all below it,
  which is why that gate is still bit for bit.
- At N = 4000 ladder sections (16002 unknowns): ~0.1 s per frequency and
  ~30 MB, where a dense A alone is 3.8 GB. No symbolic reuse across a sweep:
  SuperLU's ordering and factor is under 10% of that, and the Python stamp
  loop most of it.
- Gate: `tests/test_sparse_mna_2241.py`, which forces both paths on the A/B
  cases, station chains, ladders and every catalog network.

Stage 3 trims core's reducer to the NEC-card subset; a cross-check then holds
this copy equal to it on card-only networks.

## `swept_y`

It stacks each frequency's `PortSolution.y` and takes the block's shape from
that solution, so there is no second copy of the port count to drift from the
first (momwire#1861 was exactly that). Measured on momwire 0.89.0, over a
wire with one or two node gaps and no gap feeds (#1861's case) and a wire
with two gap feeds:

| family | against core's `compute_y_matrix_swept` | against single-point `compute_y_matrix()` |
|---|---|---|
| razor-2p | bit for bit | bit for bit |
| B-spline | bit for bit | within 1.6e-14 relative |
| sinusoidal Galerkin | bit for bit | within 6.0e-14 relative |

The single-point difference on B-spline and sinusoidal is core's: its batched
sweep and its single-point solve differ at evaluation order. No assembly on
the AK side can make them agree bit for bit, so the test holds the layer to
core's swept Y exactly and to the single-point Y within 1e-12, momwire#1861's
own tolerance.

## Phases

1. **This slice (AK only).** The layer, the private names moved behind it,
   `swept_y` used by the engine's swept-Y cache (`engines/momwire.py`
   `_swept_y`). No numbers move: `swept_y` reads the stream core's swept Y
   reads.
2. **momwire.** Publish what `_private` imports (or a supported equivalent),
   publish the swept solution stream, and add a cheap CI job that installs
   momwire from the PR and runs this repo's `tests/test_mw_layer_2219.py`
   from `main`. That job must fail, not skip, when it collects no tests,
   and report how many it ran (the `tests/*_1299.py` lesson in CLAUDE.md).
3. **The general reducer moves into the layer** (plan and correction in
   AK#2219's comments). Stage 1, the copy and the switch with no number
   moving, is the `networks` section above. Stage 2 is sparse MNA in the copy
   (AK#2241). Stage 3 trims core to the NEC-card subset. Stage 4 puts
   AK-only branch models (the skin-effect line, Touchstone, baluns) in the
   layer for good.
