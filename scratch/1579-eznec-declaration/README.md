# AK#1579 — EZNEC's stamp is the NEC-5 declaration

What produced the numbers in AK#1579's PR. Two passes over momwire's EZNEC
capture corpus (the 75 captures that ship a licensed-NEC-5 printout), plus a
hash census of this repo's own `.nec` fixtures, run before and after the
change.

Nothing here is copied from momwire: `eznec_corpus_gate.py` reads
`<installed momwire>/tests/fixtures/eznec/` at the recorded submodule
pointer, the same route `tests/test_deck_nec2_corpus_1299.py` takes.

## How to re-run

```
W=/tmp/ak1579 && mkdir -p $W
# BEFORE: shadow HEAD~'s importer so only that module differs
cp -r src $W/base_src
git show <base>:src/antennaknobs/nec_import.py > $W/base_src/antennaknobs/nec_import.py

PYTHONPATH=$W/base_src NEC5_EXE=<licensed nec5cl> python scratch/1579-eznec-declaration/eznec_corpus_gate.py \
  --root $PWD --corpus <momwire>/tests/fixtures/eznec --out corpus_before.jsonl
PYTHONPATH=$PWD/src NEC5_EXE=<licensed nec5cl> python scratch/1579-eznec-declaration/eznec_corpus_gate.py \
  --root $PWD --corpus <momwire>/tests/fixtures/eznec --out corpus_after.jsonl
python scratch/1579-eznec-declaration/summarise.py
```

Each capture is imported through `builder_from_file` (the `@file` route the
CLI and workbench use — the deck's own segments, per-wire specs, the deck's
ground), solved on AK's NEC-5 engine and on momwire's `BSplineSolver`, and
compared row by row to the printout's ANTENNA INPUT PARAMETERS block.
`corpus_*.jsonl` is one JSON object per capture: the printout's rows, each
engine's Z, the relative error per driven port, and the refusal text where
there is one.

## Result

`table.md` is `summarise.py`'s output. Counts over 75 captures:

| lane | improved | unchanged | worsened | newly solve | lost | still refuse |
|---|---|---|---|---|---|---|
| AK NEC-5 engine | 0 | 59 | **0** | 5 | **0** | 11 |
| momwire bspline | 5 | 42 | 1 | 4 | **0** | 23 |

The NEC-5 lane is the gate and nothing on it worsens. Its 59 "unchanged" are
mostly exact (`0.00 %`): AK re-emits a deck for that engine, so when the
import lands the port where the deck put it the round trip is identity — the
lane measures placement, not arithmetic.

The one bspline mover in the wrong direction is `0017` (13.46 % → 15.36 %).
Its two `NT` ends — `NT 3,-1` and `NT 2,3` — name the SAME physical node from
two different wires (wire 2's end 2 IS wire 3's end 1), and the import mints a
separate vertex port for each instead of one. That is its own defect; before
the change the two ports simply sat at two different segment centres and the
error happened to be smaller. Reported, not gated (the issue asks for the
bspline column as a report).

Biggest wins: `0034` 78.65 % → 9.49 % and `0079`/`0080` 25.65 % → 1.50 % on
bspline, and all three go from refusing to exact on the NEC-5 engine — the
declaration also makes their `GN 0` Sommerfeld rather than the
reflection-coefficient approximation NEC-5 does not have.

## What still refuses, and why

Three classes, all of them outside this issue:

- **lone-end node gap** (21 captures on bspline, pre-existing): an `EX 4 …,-1`
  at the grounded base of a vertical. momwire hosts no series gap between a
  lone conductor end and its ground contact (`node_gaps` needs a two-member
  junction) and no shunt port at a grounded node (`junction_ports` refuses a
  node the ground image pins). `0120`/`0121` join this class — they now IMPORT
  (they refused before) and solve on the NEC-5 engine at 10.1 % / 12.3 %, but
  momwire still declines them.
- **#824, one piece two attachments**: a wire whose only piece carries two
  vertex claims, one at knot 0 and one at its far end. `wire_tuples()` gives
  each vertex port the piece ending on its knot, so it cannot name both.
- **multiport Y not reciprocal**: AK's NEC-5 multiport route checks Y against
  its own transpose, and above 1e-2 it refuses. 5 captures sit there. It used
  to take `tests/fixtures/eznec_virtual_wire_1577/failEZN5.nec` with them
  (1.5e-02) because `_port_knot_current` read a vertex port's current from the
  named arm's last SEGMENT CENTRE when the arms are distinct wires — O(h) at a
  knot the current is not smooth through. Extrapolating that read to the knot
  fixed Dan's deck (2.3e-04, and 0.02 % of the printout) and moved no corpus
  deck at all: the 5 that remain are a different cause.

## The knot rule, measured

The sign rule the importer implements is NEC-5's, not an inference. Measured
on the licensed binary, capture 0183's Dipole1 with `GW 1` re-cut to 10
segments so the wire's centre IS a knot, `EX 4,1,<I3>,<I4>` spelled eight
ways and everything else identical:

```
printf 'model.nec\nmodel.out\n\n' | $NEC5_EXE    # cwd holds the edited deck
```

| spellings | the knot NEC-5 solves | Z |
|---|---|---|
| `5,0` ≡ `5,2` ≡ `-6,0` ≡ `6,1` | knot 5 — the wire's centre | 77.639 + 27.349j |
| `6,0` ≡ `6,2` ≡ `-5,0` ≡ `4,2` | knot 6 / knot 4, mirror images | 86.047 + 29.035j |

So: positive `I3` with `I4 = 0` is end 2 of that segment, a negative `I3` is
end 1, and `I4 = 1/2` names the end outright. There is no centre reading.
`_attach`'s `nec5` branch and the `EX` rule are that table.

On the 11-segment deck as captured, `6,0` / `6,2` / `6,1` / `-6,0` / `5,2` /
`-7,0` all return the printout's 79.948 + 29.919j, because knots 5 and 6 are
mirror images of each other there — which is why the capture cannot tell the
spellings apart and the 10-segment re-cut was needed.

A separate probe on a free-space dipole settled how to READ the printout: its
third column is NEC-5's own end index, `1` for what the card calls end 2 and
`2` for end 1. It is not `I4`, and a row saying `6 2` is the knot below
segment 6, not above it.

### What that means for Dipole1's three writers

`EX 4,1,6,0` on the 11-segment wire is knot 6 = 0.5454 of it. The NEC-2
export's `NT …,1,6` and the 4.2 deck's `EX 6,1,6,0` are both the CENTRE of
segment 6 = 0.5. The two NEC-2-reading decks agree with each other to
7.2e-13 on momwire:bspline; the NEC-5 one sits 3.18e-02 away, and that gap is
the half segment — the same shift the table above shows as 77.6 -> 86.0 on
the 10-segment re-cut, scaled to 11. EZNEC's NEC-5 writer places a
centre-fed odd-segment model half a segment off; the importer reads the card
exactly as NEC-5 does, and momwire's own EZNEC seam reads the same knot.
Recorded, not tuned.

## Fixture hash census

`fixture_hash_census.py` hashes `wire_tuples()` + `network()` for every `.nec`
under `tests/fixtures/`, in both parse modes. `fixture_hashes_before.json` vs
`fixture_hashes_after.json`: **24 fixtures, 6 changed, all 6 EZNEC-stamped.**
The 4nec2-dialect decks (`SY` symbols, percent positions) and the
hand-written NEC-2 decks are byte-identical.

Two of the six also stop importing in DEFAULT (non-network) mode, with the
#824 sentence "this is the NEC-5 edge-source form … parse with network=True".
That is AK#1476's established behaviour for a declared deck, now reaching the
decks that carry EZNEC's stamp; `tests/test_nec5_cm_marker_1476.py::
test_a_declared_deck_still_needs_the_network_path` is the same rule.
