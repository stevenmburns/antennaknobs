# Plan: fix PyNEC native-path impedance readout (issue #283, re-scoped)

Status: **Investigated 2026-07-11 — root cause found, and it is our bug, not
a modeling-convention gap.** Issue #283's premise ("segment-level vs
basis-level port convention", fix by segment-averaging the Y extraction) is
refuted. NEC, EZNEC, and 4nec2 already report the same driving-point
impedance as our reducer; the divergent number came from `PyNECEngine`'s own
native-path readout. The fix is small and local.

## TL;DR

When a voltage source sits on a segment that also carries a network
connection (NT or TL card), the driving-point current is the current the
source delivers into the gap:

    I_delivered = I_wire + I_network        (KCL at the feed gap)

`PyNECEngine._impedances_at` computes native-path impedance as
`V / I_wire`, reading the raw structure current at the EX segment — it
misses the network share entirely. NEC itself does NOT make this mistake:
`network.c` (nec2c 1.3.1, lines ~555–576) adds the network correction to the
segment current before printing `IMPEDANCE` in ANTENNA INPUT PARAMETERS
(`ntsc != 0` branch: `cux = einc[isc1] + <network terms>`). PyNEC exposes
that corrected readout via `nec_context.get_input_parameters(idx)`.

Measured on `lumped_coupled_pair` (native `nt_card`) and the
`test_tl_composition` pair (native `tl_card`), free space:

| | our `_impedances_at` | NEC input params | shared reducer |
|---|---|---|---|
| nt_card pair | 94.79−80.54j | **70.25−17.98j** | **70.25−17.98j** |
| tl_card pair | 105.332+2.088j | **36.268−29.476j** | **36.268−29.476j** |

NEC's corrected current (13.360+3.420j mA on the nt pair) equals the
reducer's termination-branch current to every digit. The reducer was right
all along; every path that reads NEC's ANTENNA INPUT PARAMETERS —
**including EZNEC and 4nec2 — already agrees with the reducer**. There is no
externally visible discrepancy for users comparing against those tools.

## How the wrong hypothesis fell

1. **Density sweep.** If the gap were a segment-vs-basis sampling artifact it
   would shrink as O((kh)²). Measured on `lumped_coupled_pair`:
   54.31% / 54.02% / 53.85% / 53.73% at 11/21/41/81 segments per wire —
   density-independent. (Basis parity forcing also puts a segment center at
   every named-edge midpoint, so the "distinction" never existed.)
2. **KCL identity.** Predicting `V/I_wire` from the reducer's own solve —
   `E / (Y_antenna·v)[driven]` — reproduced our native readout to all digits
   on both branch types, proving the missing term was exactly the network
   current.
3. **Primary source.** nec2c's `network.c` shows NEC adds that term before
   printing; `get_input_parameters` confirmed it numerically on both cases.

This also retroactively explains the two old mysteries: the #63
`delta_looparray_with_tls` "native" value of −77−18255j was 1 V divided by a
nearly-decoupled stub's tiny wire current (all the real current leaves
through the TL ports), and the "unphysical negative R" sightings were the
same artifact — `V/I_wire` is not a driving-point quantity and isn't
passivity-constrained. Both were artifacts of our readout, not of NEC.

## Externally visible scope

- **Users comparing with EZNEC / 4nec2 / raw NEC output: no discrepancy.**
  Those tools print NEC's corrected input parameters, which match the
  reducer (and the web UI / CLI / optimizer, which are all reducer-sourced).
- The wrong number only ever surfaced in our own **native oracle paths**:
  `PyNECEngine(native_nt=True).impedance()` and the legacy `build_tls()` →
  native `tl_card` path, and only when a branch terminates on the driven
  segment. Consequences today: `native_nt` is documented as a
  "pattern reference, not an impedance one" (docstring, issue #283), and
  strict tl_card impedance cross-validation was dropped back in #63 — the
  oracle harness is weaker than it needs to be.

## Plan

1. **Fix the native readout.** In `PyNECEngine`, read native-path impedance
   from `nec_context.get_input_parameters` instead of dividing EX voltage by
   raw structure current. Covers both `nt_card` and `tl_card` paths in one
   change. Care points: index ordering over (frequency × source) in
   `impedance_sweep`, and preserving `sum_currents` semantics for multi-EX
   designs. For source segments with no network attached NEC's `cux` is the
   plain segment current, so plain designs are bit-identical — the change is
   a strict correction.
2. **Tighten the oracles.** `native_nt` becomes a genuine impedance oracle:
   assert reducer ≈ native Z on `lumped_coupled_pair` (cross-solve rtol, now
   that the 54% readout artifact is gone) and resurrect the strict
   reducer-vs-native-`tl_card` impedance cross-check that #63 dropped
   (`test_tl_composition` currently compares far field only).
3. **Docstring sweep.** Remove the "segment-vs-basis port convention
   (issue #63/#283)" language from `TwoPort`, the `PyNECEngine` constructor,
   and `lumped_coupled_pair`; state that native and reducer agree on
   impedance since the readout fix.
4. **Re-scope and close #283** — comment with these findings (the proposed
   segment-averaging fix is explicitly rejected; nothing changes in momwire
   or the reducer).

## Driving example (for the fix PR / tests)

`lumped_coupled_pair`, stock params: two parallel dipoles, only `front` fed
with 1 V; a series 20 Ω + 0.1 µH `TwoPort` bridges the two feed gaps. The
source delivers 13.79 mA ∠14.4°, which splits (as phasors) into
8.04 mA ∠40.4° flowing up the front wire and 7.45 mA ∠−13.9° leaving through
the coupling element to excite the rear dipole. Driving-point impedance =
1 V / 13.79 mA ∠14.4° = 70.25−17.98j Ω — reported identically by the
reducer, by NEC's ANTENNA INPUT PARAMETERS, and therefore by EZNEC/4nec2.
Our old native readout divided by the 8.04 mA wire share alone and got
94.79−80.54j Ω.
