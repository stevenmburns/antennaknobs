# AK#1469 slice 2, part B — the importer stops cutting wires at attachments

DRAFT for registration, 2026-09-13 (Laptop-builder). To be committed under `scratch/1469-feed-position/` on the part-B branch BEFORE any source change, with the baseline captures.

## Where things stand
- A1 (#1480, merged): `PortOnWire(wire=, at=)` reaches every engine; the catalog is byte-identical.
- A2 (#1481): each engine picks a count so a positioned port is a site of its grid, up to 2×, and otherwise raises a `FeedPlacement` advisory; the catalog is byte-identical.
- The importer still cuts:
  - around every marked segment (`EX`/`LD`/`TL`/`NT`), leaving it on a 1-segment piece (#872);
  - at every interior NEC-5 knot source except the middle one (#824; slice 1 exempted the middle).

## Scope of part B (network mode only)
- **Marked segments.** A marked segment k of an n-segment wire becomes `PortOnWire(pname, wire=<piece>, at=(k − ½)/n)` on the uncut wire. Several marks on one wire share it.
- **Interior knot sources.** An interior knot source k (0 < k < n) becomes `PortOnWire(pname, wire=<piece>, at=k/n)`, a voltage source only.
- **Unchanged:**
  - junction cuts (`_junction_cuts`): they are NEC connectivity, so `at` is relative to the junction-cut piece;
  - virtual anchors;
  - knot 0/n sources (`PortAtVertex`, a genuine wire end);
  - EX 4 current sources at interior knots, which keep today's cut and `PortAtVertex` until an engine check covers `DrivenCurrent` on `PortOnWire`;
  - non-network mode (`ex` tuples cannot carry a position).
- **Naming.** Wires carrying ports are named after their NEC tag (`w<tag>`, or `w<tag>.<i>` for junction pieces). Ports keep today's names: `feed` / `feed<k>` / `load<k>` / `tl<k>a|b` / `nt<k>a|b`.
- **`refined(r)`** needs no change: an odd r keeps every fraction.

## Gates (predictions registered before the change)
- **G1, structure.**
  - Every catalog-nec5 and nec_portal deck imports with one tuple per junction-cut piece and no 1-segment attachment pieces.
  - Every port's `at` is (k − ½)/n or k/n on its piece, and the knot 0/n and EX 4 cases keep today's `PortAtVertex`.
- **G2, PyNEC Z identical.**
  - On every deck that serves on both runs, PyNEC Z before and after agrees to 1e-9 relative.
  - Why: cutting at segment boundaries is lossless for NEC-2 (NEC connects segment ends), and the centre rule keeps the authored count, since (k − ½)/n is already a centre at n.
  - Decks whose fed wire's count changes under the rule are listed separately. The expected count is zero, because a middle port forces odd only on a wire with no positioned port.
- **G3, NEC-2 export round trip.** For the nec_portal decks with off-middle sources (the six MININEC verticals, the two even-count feeds, the two dipole_load decks), `export_nec` reproduces the source's GW counts and EX/LD segment addresses on the uncut wires.
- **G4, NEC-5 deck.**
  - For catalog-nec5 decks with cut loads (22 multi-load, 4 short_dipole_loaded, 2 terminated_longwire refined), NEC-5's GW counts follow the knot rule. A segment-centre position needs 2n, within the cap. EX/LD address the knot at each attachment's physical point.
  - The deck count with a FeedPlacement advisory is expected to be 0.
- **G5, momwire Z direction.**
  - On catalog-nec5 decks whose momwire Z moves by more than 1e-3, the new spelling is closer to the catalog design solved directly (`native_reference.py`) on at least 80 % of them.
  - A miss is reported, not re-gated.
- **G6, AC6LA's decks.**
  - `dan2.nec` (`GW 1 20`, `EX 0 1 10 0`, no GN) imports as ONE wire, with the port at 19/40.
  - PyNEC keeps 20 segments and feeds segment 10.
  - NEC-5 goes to 40 segments with a knot at 19, and raises no advisory.
- **G7, no regression.** The fast lane, vitest, ruff and tsc stay green. Expected test re-pins: test_nec5_engine.py:1048, test_nec_import_dialects.py:113, test_middle_knot_source_1469.py:106/:111, test_nec_import.py:469-477/:697-711, test_nec_import_network.py:63-100.

## Captures
- **Baseline, on main after A2 merges; after, on the part-B branch.**
  - `catalog_nec5_z.py` (momwire Z, catalog-nec5)
  - the same over `momwire/tests/fixtures/nec_portal`
  - PyNEC Z on both sets
  - NEC-2 export and NEC-5 deck text, plus import structure
- The momwire captures are the heavy part (476 decks). Proposal: Skylake runs them; the laptop runs structure, decks and PyNEC.

## Amendment 1 (2026-09-13, before any LD change): NEC-5 discrete loads, AK#1483
Found by the part-B round-trip gate, and present on main too:
- On a NEC-5 deck, a discrete `LD` (type 0/1/4/6) is read as a NEC-2 segment range, so one load at a knot imports as one load per segment.
- The same 43 NEC-5 round-trip misses show on the baseline tree, and 35 of them carry discrete loads.
- Part B would turn the 4 `short_dipole_loaded` refusals into wrong imports. The fix therefore lands on this branch as its own commit.

Scope:
- The deck is NEC-5 (`NOFILE`, an EX end field, or `CM NEC-5`).
- A discrete LD with I3 ≠ 0 becomes ONE load at knot I3 − 1 (I4 = 1) or I3 (otherwise).
- The load shares a source's port on the same knot.
- It is placed like a knot source: `_site_plan` position, or `_vertex_plan` at a wire end or junction cut.
- An LD with I3 = 0 and LD 2/3/5/7 keep range semantics, and NEC-2 decks are untouched.
- 28 catalog-nec5 decks are NEC-5 with discrete loads; no nec_portal deck is.

Predictions:
- **G2'.**
  - PyNEC Z changes only on the 28 catalog-nec5 discrete-LD decks. Every other deck that solves on both runs matches the part-B after capture (09f752465) to 1e-9 relative.
  - The 4 `short_dipole_loaded` decks keep importing.
- **G4'.**
  - NEC-5 round-trip misses drop from 43 to 8. The 8 are the non-LD portal decks the gate already lists: 6 TL/NT decks whose NEC-5 deck re-imports with no voltage source, plus `dipole_nt_all_zero` and `dipole_rp_crossed_quadrature`.
  - NEC-2 round-trip misses stay at the same 2.
- **G8, direction.**
  - Reference: PyNEC Z of the catalog design itself, built as `native_reference.py` builds it (`cls()`, `nominal_nsegs` × {default 1, refined 2}, ground free or ("finite", 13, 0.005)).
  - Compared: PyNEC Z of the imported deck before this fix (09f752465) and after.
  - Prediction: after is closer on at least 80 % of the discrete-LD decks that solve on both runs. A miss is reported, not re-gated.
  - The 4 `short_dipole_loaded` decks have no before, so their after distance is reported alone.
- **G1 and G6** hold unchanged.

## Amendment 2 (2026-09-13, before any ladder solve): G9, part B's own momwire evidence
Why:
- G5 hit 19/19, but Skylake found that every mover carries a discrete LD. G5 therefore measures #1483, not part B's positioned-feed spelling; catalog NEC-5 decks put feeds on knots.

Observed before registering, and unregistered (scratchpad capture, default momwire engine, 5363bbbe5 against 9951ee368, momwire 495b6c9):
- On the 65 nec_portal decks, 52 are identical, 0 change status, and exactly the 10 decks with off-centre attachments move:
  - the 6 MININEC verticals, 1.772e-3
  - `dipole_load_ld4` 3.561e-3 and `dipole_load_ld0` 2.387e-3
  - `apex_pq_reversed_walk` 5.3e-4
  - `mininec_gp80_seam` 5.9e-5
- The 6 MININEC verticals share one geometry (identical Z), so the 10 decks are **5 distinct geometries**.

Reference: no catalog design exists for these decks, and a cross-basis reference is barred (never gate cross-basis agreement). The reference is therefore each deck's own refinement ladder, on the same engine:
- Solve Z_before(r) and Z_after(r) at r = 1, 3, 9 (`NecDeck.refined`, odd r) with `partB_portal_ladder.py`.
- Reference `Z_ref` = the midpoint of Z_before(9) and Z_after(9).

Predictions, scored per distinct geometry (5):
- **G9a, the spellings converge.** |Z_before(9) − Z_after(9)| < |Z_before(1) − Z_after(1)| / 3 on at least 4 of 5.
  - Reason: the cut's extra junctions sit at segment boundaries, and refinement shrinks the segment they isolate.
  - A geometry that misses G9a has no well-defined common limit, and its G9b row is reported but not scored.
- **G9b, direction.** |Z_after(1) − Z_ref| < |Z_before(1) − Z_ref| on at least 4 of the scored geometries (bar 80 %).
  - Reason: slice 1's whole-wire spelling moved catalog imports toward the design.
- A miss is reported, not re-gated.
