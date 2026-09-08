# A NEC-5 regression corpus from the public NEC-2 decks

`nec5_corpus.py` is one Python file, standard library only, Python 3.8 or
newer, Windows / macOS / Linux. It does three things:

```
python nec5_corpus.py fetch     --out raw
python nec5_corpus.py translate --src raw --out nec5
python nec5_corpus.py check     --exe NEC5CL.exe --src nec5 --keep-dir failed
```

1. **fetch** downloads about 4,000 NEC-2 / 4nec2 decks from the places that
   publish them (GitHub repositories, the ARRL and Cebik archives, a few
   personal sites) into `raw/<source>/`, keeping their file names, and
   writes `raw/LICENSES.md` saying where each set came from and under what
   terms. The script redistributes nothing; every deck comes to you from its
   own source. `python nec5_corpus.py list` prints the sources.
2. **translate** rewrites each deck into a form NEC-5 reads, and records
   every change it made as a `CM nec5_corpus:` line in the deck and in
   `nec5/translate-report.jsonl`.
3. **check** runs each translated deck through your NEC-5 executable (file
   names on stdin, as NEC5CL asks for them), classifies the result, keeps the
   printout of anything that did not solve cleanly, and writes
   `check-report.jsonl` with the driving-point impedance of every deck that
   did. Use `--jobs N` for parallel runs.

## What translate changes, and why

**Feed points move to knots.** NEC-2 puts a voltage source at the centre of
a segment; NEC-5 puts it at a segment end, a knot. The corpus is mostly
NEC-2 style: 72 % of the sources sit on the middle segment of a wire with an
odd segment count, where no knot exists. Such a wire gets one more segment,
so its centre is a knot, and the source goes there (`EX 0 tag seg 2`, end 2
of the segment ending at that knot). A wire with an even count already has a
centre knot and keeps its mesh. An off-centre feed moves half a segment
toward the wire's centre and the move is written into the deck; pass
`--offcenter double` to double that wire's mesh instead so the old centre is
a knot exactly. Discrete loads (LD 0/1/4) and TL/NT ports are addressed the
same way, because NEC-5 attaches those at knots too. Tags shared by several
wires, GM/GX/GR copies, and absolute (tag 0) segment numbers are all
resolved before the knot is chosen.

**The EX card's fourth field.** In NEC-2 it is a print flag (often `10`); in
NEC-5 it selects the segment end. It is rewritten, since a leftover `10`
makes NEC-5 stop with "node out of range".

**Dialect.** 4nec2 `SY` symbols are evaluated (its BASIC-style grammar:
`^`, trig in degrees, `sqr`, unit suffixes) and substituted; commas and tabs
become spaces; fused mnemonics (`GW1,8,...`) are split; `'` comments,
`#14`-style AWG gauges and Fortran `D` exponents are resolved; numbers
longer than NEC-5's field parser accepts (17-digit reprs) are shortened to
10 significant digits.

**Excitation types.** EX 0 stays a voltage source. 4nec2's EX 6 current
source becomes NEC-5's EX 4 knot current source. EX 5 becomes EX 0. EX 1-3
(plane waves) pass through. A NEC-2 EX 4 (elementary current source in
space) has no NEC-5 counterpart and the deck is refused.

**Ground.** GN -1 / GN 1 / GN 2 pass through. NEC-2's GN 0
(reflection-coefficient ground) becomes NEC-5's GN 0, which is a Sommerfeld
ground, and the deck says so. NEC-2's radial-screen and second-medium
fields on GN, and the GD card, are dropped with a note: NEC-5 has no
spelling for them and misreads the fields if they are left in.

**Cards NEC-5 does not have** are dropped with a note: EK, KH, CP, IS, JN,
and 4nec2's LD 6 / LD 7 (its insulated-wire load; NEC-5 crashes on them).
SM patch surfaces are refused (NEC-5 rejects the card). NX multi-structure
decks are split into one deck per structure. A deck with no execution
request (4nec2 adds XQ itself) gets `XQ 0`. A 4nec2 flat loop spelled as a
one-turn helix with 1e-300 pitch is written as straight pieces, because
NEC-5's GH computes zero wire length from it.

Every one of these conventions was verified by running probe decks through
a NEC-5 executable and reading the printout, not taken from its source.

## What to expect from check

On the 3,146 unique decks the tool was developed against (2026-09-08,
NEC-5 x13 Linux build), a 1-in-13 sample of the translated decks gave:

| result | decks | meaning |
|---|--:|---|
| ok | 290 | impedance printed, no error |
| ok-no-source | 3 | plane-wave or geometry-only deck: nothing to print |
| timeout | 3 | over 120 s (large wire grids) |
| error | 7 | see below |

The seven errors are NEC-5's, not the translator's: `free(): invalid
pointer` and a segmentation fault on the same family of verticals whenever
a Sommerfeld ground is present (the identical deck solves in free space),
`DATAGN` on two patch decks (SP/SC) and on a parallel-RLC load with zero R
and L, and a singular matrix on one deck with coincident copies. The kept
printouts under `--keep-dir` show each one. Those crash decks are worth
keeping: they reproduce.

## The antennaknobs catalog

`export_catalog_nec5.py` (needs antennaknobs installed) writes our own 100+
catalog designs as NEC-5 decks at two mesh densities, in free space and over
a Sommerfeld ground, using the same deck writer the app's NEC-5 lane is
validated with. Those decks are MIT and ship with this package.

## Rights

The translator and this package are MIT (Steven Burns, 2026). The decks it
fetches keep their own terms; `raw/LICENSES.md` lists them per source. Most
GitHub sources are GPL or MIT; the 4nec2 bundled models and several personal
collections state no licence; the Cebik course models are copyright L. B.
Cebik (W4RNL, SK), distributed free on his site and mirrored, with no
redistribution grant stated. That is why the tool fetches rather than ships
them.
