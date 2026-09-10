# A NEC-5 regression corpus from the public NEC-2 decks

`nec5_corpus.py` is one Python file, standard library only, Python 3.8 or
newer, Windows / macOS / Linux. Run it as `python nec5_corpus.py ...` (or
`python3` where that is the name); it carries no shebang on purpose, because
Windows' `py` launcher would follow one to the Store stub that a default
Windows 11 install leaves at `python3`. It does three things:

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
   did. A non-zero exit is reported as a crash with its code, whatever the
   printout says. Use `--jobs N` for parallel runs. Every report opens with
   a `_meta` row naming the tool version, step, executable and platform, so
   reports from different boxes can be compared knowing which instrument
   made each.

## Without Python: the Windows executable

The same file, frozen with PyInstaller and signed, is published as
[`nec5_corpus-windows.zip`](https://github.com/stevenmburns/antennaknobs/releases/tag/nec5-corpus-v1.4)
under the tool's own release tag, `nec5-corpus-v<VERSION>` — not with the
antennaknobs releases, and not inside the Windows workbench, because the
people who want a NEC-5 corpus do not all want an antenna modeller. Unzip,
and `nec5_corpus.exe translate ...` is `python nec5_corpus.py translate ...`:
the build's smoke gate runs both over momwire's 65-deck portal corpus and
requires every written deck byte-equal and the reports line-equal. It is
built on demand (`freeze-nec5-corpus` workflow, `publish: true`) when this
file changes, so the release tag's version and `VERSION` here agree.
The zip also carries `catalog-nec5/` — the 476 catalog decks below, written
from the same commit — with `export_catalog_nec5.py` and this README.
`SECURITY-REVIEW.md` beside this file ships in the zip and is linked from
the release notes with the checksums: what the program can and cannot do to
a machine, subcommand by subcommand, and how to verify the exe or skip it.
The review names the version it was written for and a test holds that equal
to `VERSION`, so bumping the version means re-reading the review.

Keeping the script standard-library only is what makes that build a 9 MB
file rather than a 160 MB one; the one function it shares with antennaknobs
(`_classify_sp_fields`, the SP sphere-or-patch rule) is a copy the test
suite pins equal to the importer's, token for token.

## What translate changes, and why

**Feed points move to knots.** NEC-2 puts a voltage source at the centre of
a segment; NEC-5 puts it at a segment end, a knot. The corpus is mostly
NEC-2 style: 72 % of the sources sit on the middle segment of a wire with an
odd segment count, where no knot exists. Such a wire gets one more segment,
so its centre is a knot, and the source goes there (`EX 0 tag seg 2`, end 2
of the segment ending at that knot). A wire with an even count already has a
centre knot and keeps its mesh. An off-centre feed gets the cheapest
segment count between N and 2N that puts it on a knot exactly: the centre
of segment k sits at (2k-1)/(2N) of the wire, so any count that is a
multiple of 2N/gcd(N, 2k-1) works, and the smallest one not below N is
taken. That is N+1 for a centre feed, 2N when k and N share no factor, and
less than doubling otherwise (segment 2 of 6 needs 8, not 12). Several
references on one wire are aligned together. Measured against nec2c on the
635 corpus decks where the choice matters, exact alignment reads closer than
a half-segment shift on 452 of them and farther on 169 (median 0.038 against
0.055 in 50 Ω reflection coefficient). `--offcenter shift` keeps the mesh and
moves an off-centre feed half a segment toward the centre instead, recording
the move; `--offcenter double` always doubles.
Discrete loads (LD 0/1/4) and TL/NT ports are addressed the same
way, because NEC-5 attaches those at knots too. Tags shared by several
wires, GM/GX/GR copies, and absolute (tag 0) segment numbers are all
resolved before the knot is chosen.

**The EX card's fourth field.** In NEC-2 it is a print flag (often `10`); in
NEC-5 it selects the segment end. It is rewritten, since a leftover `10`
makes NEC-5 stop with "node out of range".

**Dialect.** 4nec2 `SY` symbols are evaluated (its BASIC-style grammar:
`^`, trig in degrees, `sqr`, unit suffixes) and substituted; commas and tabs
become spaces, with spaced expressions inside a tab-delimited field or inside
parentheses kept whole; fused mnemonics (`GW1,8,...`) are split; `'`
comments, `#14`-style AWG gauges (also `#12/ft`, and inside expressions) and
Fortran `D` exponents are resolved; numbers longer than NEC-5's field parser
accepts (17-digit reprs) are shortened to 10 significant digits.

**Excitation types.** EX 0 stays a voltage source. 4nec2's EX 6 current
source becomes NEC-5's EX 4 knot current source. EX 5 becomes EX 0. EX 1-3
(plane waves) pass through. A NEC-2 EX 4 (elementary current source in
space) has no NEC-5 counterpart and the deck is refused.

**Ground.** GN -1 / GN 1 / GN 2 pass through. NEC-2's GN 0
(reflection-coefficient ground) becomes NEC-5's GN 0, which is a Sommerfeld
ground, and the deck says so. NEC-2's radial-screen and second-medium
fields on GN, and the GD card, are dropped with a note: NEC-5 has no
spelling for them and misreads the fields if they are left in.

**Catenary wires pass through.** NEC-5 has a CW card of its own, in the
structure-geometry section, and NEC-4.2 spells it the same way field for
field (`CW ITG NS X1 Y1 Z1 X2 Y2 Z2 RAD ICAT RHM ZM`, ICAT choosing height /
sag / total length), so a catenary deck is translated rather than refused and
the card earns no note. Its segments are addressed and remeshed like a
`GW`'s: a source or load on a CW moves to a knot the same way, which is the
only field of the card the translator writes.

**Cards NEC-5 does not have** are dropped with a note: EK, KH, CP, IS, JN,
VC, MX, PS, MP, and 4nec2's LD 6 / LD 7 (its insulated-wire load; NEC-5
crashes on them). The two NEC-4-only ones a NEC-4 deck is likeliest to carry
are MX, which sizes NEC-4's matrix memory, and PS, which asks it to print the
electrical lengths of the segments; NEC-5 allocates its own memory and has no
such print, so left in they read as an input error rather than as the model.

SP in its NEC-2/NEC-4 patch form (NEC-5 spells a *different* card as SP, a
sphere, which is kept when the fields read as one), SC and SM patch cards and
GF/WG Green's-function files are refused. NX multi-structure decks are split
into one deck per structure. A deck with no execution request (4nec2 adds XQ
itself) gets `XQ 0`. A 4nec2 flat loop spelled as a one-turn helix with 1e-300
pitch is written as straight pieces, because NEC-5's GH computes zero wire
length from it.

Every one of these conventions was verified by running probe decks through
a NEC-5 executable and reading the printout, not taken from its source. CW
included, as of 1.4: 4nec2's NEC-4 catenary card (`CW 1 39 -19.64 0 20
19.64 0 20 0.001 2 19.64 1`, a 39.28 m span at 20 m with ICAT 2 and ZM 1),
translated to 40 segments with the feed on a knot, runs in NEC-5, is echoed
as a CW, and the printout reports "Catenary length = 39.3478" — the 39.28 m
span plus 8h²/3L for a 1 m sag, so ICAT 2 / ZM read as "sag" in both
dialects — and the impedance differs from a straight GW of the same span
(4365+2181j against 4266+2235j at 7 MHz) the way a longer, sagged wire
should. If a catenary deck fails at the engine, the printout says why.

## What to expect from check

On the corpus the tool was developed against (4,009 files, 3,146 unique
decks; 2026-09-08; NEC-5 x13, Linux build), translate wrote 3,946 decks
(56 refused, 13 unreadable, all listed in the report) and check gave:

| result | decks | meaning |
|---|--:|---|
| ok | 3,773 | impedance printed, no error |
| ok-no-source | 68 | plane-wave or geometry-only deck: nothing to print |
| error | 79 | NEC-5 stopped or crashed (below) |
| no-impedance | 7 | a source, but no impedance table (a Cebik NT idiom) |
| timeout | 18 | over 120 s (large wire grids) |

The 79 errors are NEC-5's, not the translator's, and are worth keeping as
regression decks because they reproduce:

- **43 crashes** (`free(): invalid pointer`, segmentation faults) on a
  family of G1OJS verticals and helices whenever a Sommerfeld ground is
  present. The identical deck solves in free space.
- 15 `DATAGN: Input data error`: SP/SC patch decks, and a parallel RLC load
  (LD 1) with zero R and L.
- 9 singular matrices (coincident copies), 6 `ISEGNO` errors on the NEC-2
  manual's patch-plus-wire examples, and a handful of allocation failures.

**Impedance against nec2c.** For 2,695 decks with a nec2c result on the
untranslated deck, the median difference in 50 Ω reflection coefficient is
0.070; 6 % of free-space decks and 16 % of finite-ground decks differ by
more than 0.5. Knot placement moves resonant matches (gamma sections),
NEC-2's reflection-coefficient ground is not NEC-5's Sommerfeld ground,
and stepped-diameter Yagis are a known NEC-2 weakness, so a large
difference is a formulation difference to look at, not a translation
error.

## The antennaknobs catalog

`export_catalog_nec5.py` (needs antennaknobs installed, no engine) writes our own
catalog as NEC-5 decks at two mesh densities, in free space and over a
Sommerfeld ground, through the same deck writer the app's NEC-5 lane is
validated with: 476 decks, of which 168 are the per-port decks the app
sends for the 26 network designs (one deck per driven port; the network is
solved outside NEC-5 from the multiport Y). All 476 solve. Those decks are
MIT and ship with this package.

## Rights

The translator and this package are MIT (Steven Burns, 2026). The decks it
fetches keep their own terms; `raw/LICENSES.md` lists them per source. Most
GitHub sources are GPL or MIT; the 4nec2 bundled models and several personal
collections state no licence; the Cebik course models are copyright L. B.
Cebik (W4RNL, SK), distributed free on his site and mirrored, with no
redistribution grant stated. That is why the tool fetches rather than ships
them.

## Comparing two `check` reports

Since 1.2 every `check` report's `_meta` row records the environment that
produced it: the OpenMP / MKL / OpenBLAS thread variables (present or
explicitly absent), the interpreter, the platform, the job count, and the
size and sha256 of the engine and every DLL beside it. Two runs of one binary
on one box gave different crash-versus-hang splits on 38 decks a day apart
(2026-09-08 / 09-09) and the older report could not say why, so:

```
python nec5_corpus.py compare check-a.jsonl check-b.jsonl
```

diffs the two deck by deck — and refuses, naming the field, when their
recorded environments differ or one carries none. `--ignore-env` compares
anyway after printing the differences.
