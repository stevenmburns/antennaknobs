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
| `series_rlc_impedance`, `parallel_rlc_admittance`, `branch_port_refs`, `rewrite_branch` | `momwire.networks._reduce` / `._spec` | private |
| `eps_tilde`, `lambda_medium`, `k_medium` | `momwire._ground_refl`, `momwire._sommerfeld_below` | private |
| `couplings()` | `momwire._couplings.COUPLINGS` (momwire#885) | private |
| `feature_registry()`, `feature_certified(name)` | `momwire._features` (momwire#1869) | private |

Core keeps everything its executables and portal run: the deck path, every
solver's fill and solve, the network reducer (the NEC-5 drop-in stamps its
`TL`/`NT` cards through it), and the swept solution stream, since batched
swept fills are where the accelerated speed is.

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
3. **AK-only pieces move into the layer** as they next need a change: the
   skin-effect line as a layer two-port on the reducer's `y_at(f)` protocol,
   and sparse elimination of circuit-only network nodes (AK#2241).
