# NEC-5 capability audit: the full dialect vs the seam, feature by feature

The buried-wires finding (momwire#524) exposed a method gap: every prior
inventory was **deck-driven** — the capture corpus, the statement matrix,
the arcs — and a capability no sample deck exercises is invisible to that
method (EZNEC's bundled models never bury a wire). This audit is the
complement pass: enumerate the engine's capability surface from the top,
then probe what the seam does with each item, so feature-level blind spots
are a list rather than a sequence of surprises.

**Sources and firewall.** The engine's documentation was consulted under our
license to build the checklist; none of its content is reproduced here — no
field tables, no prose, no page references. Every status claim below rests
on (a) probe decks run against our own licensed `nec5cl` binary with the
printed output quoted, and (b) the momwire seam's own behavior
(`python -m momwire.eznec`, probe battery in the 2026-08-21 session
scratchpad; the two ground probes are also recorded on momwire#524). Card
mnemonics and their general purposes are observable from decks and are the
same public vocabulary the NEC-2/NEC-4 lineage documents.

## The verdict first

**Zero silent paths found.** Every capability outside the seam's serve set
refuses loudly, and all but two refuse *by name* with a sentence a reader
can act on. The EZNEC-launched audience never sees most of this surface at
all — EZNEC resolves its geometry to plain `GW` wires and emits only the
fifteen-mnemonic vocabulary the seam speaks — so these findings concern
hand-written decks and the honest-disclosure list, not the drop-in flow.

One capability family has real user demand behind it and is tracked:
**below-interface wires** (momwire#524) — buried radials, buried screens,
interface-crossing wires. The licensed engine serves all three (probed:
lone radial 92.13 − j70.14 Ω; four-radial screen 89.99 − j71.40 Ω;
crossing wire 74.76 − j57.73 Ω); the seam refuses each by name as of
momwire#525.

## Geometry surface

| capability | cards | seam today (probed 2026-08-21) |
| --- | --- | --- |
| straight wires | `GW` | **served** (the whole corpus) |
| tapered wire (continuation) | `GC` | refuses by name ("tapered wire continuation… not part of this dialect"). EZNEC emits stepped-radius `GW` runs instead, which serve; momwire's per-wire radii + the taper certification (momwire#447/#448) cover the physics. A `GC`-to-stepped-`GW` translation is a candidate work item, not a physics gap. |
| wire arc / helix / catenary | `GA` `GH` `CW` | refuse by name ("whose geometry is GW alone"). EZNEC pre-resolves curves to `GW` chains; a hand-written deck must do the same. |
| transforms / scaling | `GM` `GS` | refuse by name — same sentence family; EZNEC resolves transforms before writing. |
| symmetry generators | `GR` `GX` `SX` | refuse by name. momwire has no symmetry exploitation; decks must write the full structure. Performance item, not correctness. |
| surfaces (plates, cylinder/cone/disk, sphere, patches, edge transitions) | `CR` `CY` `QP` `RP`(geom) `SP` `ST` | refuse by name ("which models wires only"). A genuine engine-level capability momwire does not have; distinct from #524 and currently untracked — surfaces have no wire-modeling workaround for the decks that need them. |
| direct node/element input, deck parameters, tolerance overrides | `NL` `PA` `TL`(geom) | refuse loudly. Nit: `PA`'s letter-valued field trips the generic "NON-NUMERICAL CHARACTER IN FIELD" before the card-naming sentence — safe but unpolished. |

## Ground and media surface

| capability | spelling | seam today |
| --- | --- | --- |
| free space / PEC / Sommerfeld / MININEC-type | `GN -1` / `GN 1` / `GN 0`,`GN 2` / bare `GD` | **served**, byte-gated (the ground-rungs arc; scored matrix) |
| magnetic ground (μr ≠ 1) | `GN` trailing fields | refuses by name ("no magnetic ground; serves mu_r = 1 only — EZNEC writes 1.,0.") |
| Sommerfeld table cache file naming | `GN` optional trailing name | refuses loudly, but via the generic non-numeric-field error — the one *dialect-form* gap found: the field is legal in the engine's dialect and the seam's parser has no reading for it. Harmless for EZNEC launches (never written); polish candidate. |
| radial-screen parameters on the ground card | — | **no such spelling exists in this dialect** (screens are modeled as real wires) — a NEC-2-lineage habit with no NEC-5 counterpart, so no silent-drop risk. Verified by the four-radial probe: the screen is `GW` wires, and its refusal is #524/#525's, by name. |
| upper medium parameters | `UM` | refuses by name (vocabulary sentence). Untracked capability; no observed demand yet. |
| **wires below the interface** (buried radials, screens, crossing wires) | `GW` with z < 0 | **refuses by name** (momwire#525); the capability is **momwire#524** with probe evidence on the issue. The one audited gap with certain real-world demand. |
| wire lying IN the interface | `GW` at z = 0 | refuses by name as the degenerate case (momwire#525) |

## Excitation, loading, requests, runs

| capability | spelling | seam today |
| --- | --- | --- |
| voltage source at a node / current source | `EX 0` / `EX 4` (multi-`EX 4` incl.) | **served** |
| incident-wave and other source types | `EX 1`, `EX 5`, … | refuse by name ("serves EX 4 … and EX 0 …"). Plane-wave excitation is untracked; no EZNEC emission, RX-pattern decks would want it. |
| fixed-impedance loads, insulation | `LD 4`, `IS` | **served** |
| other load types (RLC, wire conductivity spelled as LD, …) | `LD 0/1/2/3/5/…` | refuse by name ("loading is LD 4 alone — 67 of 67 loads across the captures"). Note momwire itself has wire conductivity and RLC loading — this is dialect routing, not physics; work item when a deck shows up. |
| far field, charge/current printing | `RP`, `PQ`, `PT` | `RP`/`PQ` served (`RP` nonzero range refuses by name); `PT` is outside the emitted vocabulary and refuses by the vocabulary sentence |
| near fields on a grid | `NE` / `NH` | served over free space and PEC; refuse naming the ground over `GN 0`/`GD` (momwire#520 is the evaluator) |
| near fields along a line | `LE` / `LH` | refuse via the vocabulary sentence; same evaluator family as #520 |
| networks / transmission lines | `NT` / `TL` | **served** (node-addressed, mixed tables) |
| multi-structure runs | `NX` | refuses by name ("EN is the terminator EZNEC writes") |
| frequency stepping | `FR` forms | served as EZNEC drives it (one launch per point; the engine-side sweep forms are unexercised by EZNEC) |

## What this changes

1. **The honest-disclosure list** for the release gains named entries:
   below-interface wires (#524), surface modeling, incident-wave excitation,
   non-`LD 4` load types, magnetic grounds, `UM`, `LE`/`LH`, symmetry
   generators — every one a *named refusal*, none silent.
2. **#524 is confirmed as the priority capability gap** — the only audited
   item where the licensed engine serves decks a real user community writes
   today (buried screens are the documented workflow, now probed).
3. **Surfaces are the second engine-level gap** and deserve their own
   backlog issue if patch-modeling demand ever materializes; unlike #524
   there is no evidence of demand from this audience yet.
4. **Two polish nits** (the `PA` letter-field and the `GN` cache-file-name
   field falling to the generic non-numeric error) are the only places the
   refusal grammar drops to a raw parser message.
5. **Method rule, going forward**: a deck-driven inventory sees only what
   sample decks exercise; pair every corpus-based serve matrix with one
   top-down capability pass like this one.
