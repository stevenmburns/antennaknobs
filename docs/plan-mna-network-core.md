# Plan: reformulate `NetworkReducer` as Modified Nodal Analysis (MNA)

Status: **Implemented (2026-07-11).** Tracked by issue #285. The MNA core
landed via the staged migration below: built flag-gated next to the
admittance reducer, cross-checked to 1e-9 on every branch/BC combination,
default flipped with the full suite green, then the legacy Sherman-Morrison /
three-BC code and the `abs(Z) < 1e-15` guards were deleted. Implementation
notes that refined the plan during bring-up:

- `Driven` + `Load` on a port collapse into ONE Group-2 "termination branch"
  (EMF in series with Z_L, datum → node); its constitutive row
  `v_k + Z_L·j = E` is exactly the old Thevenin BC, and `j` is the delivered
  port current, so `Z = E/j`, the physical gap voltages, and the power
  bookkeeping all read off a single solve.
- Each Group-2 element picks the impedance- or admittance-form constitutive
  row (exact at the short z = 0 and the open y = 0 respectively), so no
  element value is ever inverted; a parallel-LC trap at exact resonance is
  now finite in the excited path too (it used to form Z_L = ∞).
- `resolve_voltages` now reports the PHYSICAL gap voltage at loaded ports
  (formerly a V = 0 bookkeeping pin), so PyNEC's reducer-path excited
  context gets the same load-shaped currents momwire's did.
- `skyloop_lmatch.build_network` stamps its sliders literally; the
  topology special-casing is gone. Degenerate coverage lives in
  `tests/test_network_mna.py`.

## Why

`NetworkReducer` builds a bare nodal **admittance** system over the network
nodes (`_augment_with_lines` stamps each branch's 2×2 / 1×1 admittance into a
`Y_full`) and then reduces it with a hand-rolled set of boundary conditions.
Two structural problems:

1. **No infinite-admittance elements.** An ideal short, `0 Ω`, or `0 H` series
   branch has `1/Z = ∞` — it cannot be a finite entry in an admittance matrix.
   Today `twoport_admittance_2x2` / `shunt_admittance` raise on `abs(Z) < 1e-15`.
   The interim `skyloop_lmatch` inert-matchbox case dodges this by expressing "no
   series element" as *topology* (drop the branch, drive the shared node), but a
   literal `0 H` slider value still can't be stamped.
2. **A boundary-condition zoo.** Three different BC regimes are hand-coded:
   - `resolve_voltages`: driven → pin `V`; loaded → `V = 0`; floating → `I_ext = 0`.
   - `excited_state`: a *separate* Thévenin BC `V_k + Z_L·(YV)_k = V_src`.
   - `apply_loads`: Sherman-Morrison rank-1 update folding `Load` into the real-port Y.
   This is where the #68 Load-BC bug lived, and why the impedance and far-field
   paths carry parallel logic.

MNA (the SPICE formulation) solves both: elements that constrain a voltage or
carry an independent current become **Group-2** unknowns — the branch current is
added to the solution vector with a constitutive row/column.

## Formulation

Solve `[[G, B], [Cᵀ, D]] · [v; j] = [i_ext; e]` where

- `v` — node voltages (one per network node), referenced to a chosen **datum**.
- `j` — Group-2 branch currents (voltage sources, ideal shorts, zero-Z elements).
- `i_ext` — external current injections (0 at all internal nodes here).
- `e` — Group-2 source values.

`G` is the node-admittance block; `B`/`Cᵀ`/`D` are the Group-2 incidence and
constitutive rows.

### Stamp set (maps every current branch)

| element | group | stamp |
|---|---|---|
| antenna multiport Y (dense, from MoM) | 1 | `G[nodes, nodes] += Y` — the short-circuit Y among the real feed nodes vs. datum |
| `Shunt(port, y)` | 1 | `G[k,k] += y` |
| `TwoPort` / `TL`, finite Z | 1 | `G[[a,b],[a,b]] += Y_2x2` (unchanged) |
| `TwoPort` / series element, **Z = 0** (short, 0 Ω, 0 H) | 2 | aux `j_x`: `B[a,x]=+1, B[b,x]=-1`, `Cᵀ[x,·]` = `v_a − v_b`, `D[x,x] = -R` (`= 0` for ideal short); constraint `v_a − v_b − R·j_x = 0` |
| `Load(port, Z_L)` (series impedance on a segment) | 2 | series impedance in the port branch: `v` split across the load, `D = -Z_L`; retires the Sherman-Morrison path |
| `Driven(port, E)` (voltage source) | 2 | `v_a − v_b = E`; **`j_x` is the source current** |
| ground / common | — | one node chosen as datum (row/col removed); the L-match's virtual ground is the natural datum |

### What the readouts become

- **Driven-point impedance:** `Z = V_src / j_src` — read straight off the
  solution vector. No `I = Y_full @ V` post-multiply, no `Driven(gnd, 0)` datum
  trick (the datum is explicit).
- **Far field / current distribution:** the same solve yields both node voltages
  and the source/Load branch currents, so `excited_state`'s separate Thévenin BC
  and efficiency accounting fall out of one system. No second formulation.

## Migration (behind the existing tests)

The public surface (`driven_impedance`, `excited_state`, `resolve_voltages`,
`impedance_from_y`) stays; only the internals change.

1. **Build the MNA assembler** next to the current reducer, gated by a flag, so
   both can run side by side during bring-up.
2. **Port the stamps** in order: antenna-Y block → `Shunt`/`TwoPort`/`TL`
   (Group 1) → `Driven` (Group 2, the big BC simplification) → `Load` (Group 2,
   retire Sherman-Morrison) → ideal shorts (Group 2, the new capability).
3. **Cross-check** every step against the current reducer on the oracle suite.
4. **Flip the default**, delete the Sherman-Morrison / three-BC code, remove the
   `abs(Z) < 1e-15` short-circuit guards (now handled by Group 2).

## Acceptance

Reproduce the current observable behavior — the suite is the harness:

- `test_tl_composition` — reducer vs native `tl_card` far field
- `TwoPort` `nt_card` oracle, `Load` series/parallel, the `Shunt` L-match,
  `delta_looparray` cross-engine impedance/gain

plus **new degenerate cases only MNA passes**:

- `0 Ω` resistor and `0 H` ideal-wire series element (finite result, no raise)
- ideal short between two nodes (node identification)
- **inert L-matchbox stamped literally** — `TwoPort(l=0)` + `Shunt(c=0)` ⇒
  `Z_in = Z_ant`, *without* the design-level topology special-casing that
  `skyloop_lmatch.build_network` uses today

## Relationship to other work

- **#283 (segment-averaging).** Both touch how the reducer defines its ports;
  the port/datum definition is shared, so sequencing them together avoids
  redefining the port convention twice.
- **PR #284.** Ships `Shunt` + the skyloop L-match on the current admittance
  reducer, with the interim inert matchbox done by topology and a `C=0`→open
  guard. This plan is the principled generalization, not a blocker for #284.
