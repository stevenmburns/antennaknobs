# Re-rendering the #896 census on the fixed tool — the record

The published census page (`docs/status/2026-09-11-corpus-census-momwire-nec5.md`)
was produced with corpus tool **1.6**. Two corpus fixes have landed or are in
review since: **#1416** (a whole-wire `LD` segment range must stay whole-wire,
PR #1422, merged) and **#1430** (a deck listing the same wire twice is invalid,
PR #1431, open). This is the record of re-rendering the page on **1.9**, which
carries both.

Commands: `scratch/896-census/rerender_1430.sh`. Outputs under `~/nec5-timing/`.

## What the two fixes do to the corpus

| | published (1.6) | re-render (1.9) |
|---|---:|---:|
| source files seen | 3,168 | 3,168 |
| translated | 3,070 | 3,060 |
| refused | 75 | 75 |
| **invalid** | **14** | **24** |
| unreadable | 9 | 9 |
| **`written` in the report** | **3,077** | **3,067** |
| **deck files on disk** | **3,076** | **3,066** |

Both counts are given because they disagree, in both columns, by one. That is
**#1435**: `translate` maps `foo.inp` and `foo.nec` onto the same output path and
the second write wins silently. The live pair is
`cebik-w4rnl/Moxon-Rectangle-Notes-Models/mox10-1al.{inp,nec}`, they are
genuinely different models — the Moxon rectangle in a different plane — and the
`.inp` one is the deck that is lost. Left alone here: a fix changes deck paths,
which are the join key of every existing report.

The ten decks #1430 newly refuses, all of them `the same wire is listed twice
(GW tag i (line m) / GW tag j (line n)), which makes the moment matrix singular`:

```
cebik-w4rnl/Basic-Intermediate-Tutorial-Models/Tutorial-1/21-2-1.NEC
icecube-dbesson/RICE-dipole.nec
icecube-dbesson/RICE-dipole0.nec
necpp/patch_999.nec
necpp/patch_999_2.nec
necpp/plane.nec
necpp/plet_helixumts.nec
qantenna/adrian.nec
qantenna/airplane.nec
qantenna/tower.nec
```

## Translate is deterministic on 1.9

Two full passes into separate trees: **3,066 decks byte-for-byte identical**, and
the two reports are equal as data once `_meta.started` is dropped (3,169 rows
each). The tool has no timestamp in the deck text, which is what makes the
byte-for-byte comparison possible at all.

## #1430 is purely subtractive, measured rather than assumed

Comparing the new tree against the **#1416** tree, ignoring the one
`CM nec5_corpus 1.x:` provenance line:

- survivors compared: **3,066**
- bodies differing beyond that line: **0**

So the only thing #1430 changes is which decks exist. Against the **published**
tree the same comparison finds **170 of 3,066** remeshed — that is #1416's
footprint, and it is why the re-render moves numbers for two separate reasons.

## The NEC-5 side is the published page's own binary

The published report's `_meta.exe` is `~/nec5-timing/nec5-src/nec5cl`, which no
longer exists on this box. `nec5cl-x13` is **byte-identical** to it:

```
recorded in check-base.jsonl   sha256 2068ae67a7fb1225…  1,265,856 bytes
nec5cl-x13                     sha256 2068ae67a7fb1225…  1,265,856 bytes
```

and `compare` between the published run and an x13 run over the **same**
published tree reports `decks: 3076 vs 3076; moved: 0; impedance moved
(> 1e-09): 0`. Same build, not a similar one.

Re-run over the new tree: **918 s**, 3,066 rows, same environment (OMP and
OPENBLAS 4, `PYTHONUTF8=1`, `--timeout 300`, `--jobs` default 4).

| status | published | re-render |
|---|---:|---:|
| `ok` | 2,946 | 2,942 |
| `ok-no-source` | 67 | 66 |
| `crash` | 43 | 43 |
| `error` | 10 | 6 |
| `no-impedance` | 8 | 7 |
| `timeout` | 2 | 2 |

The drops sum to exactly the ten removed decks (4 `ok`, 4 `error`, 1
`no-impedance`, 1 `ok-no-source`), and **no survivor changed status**.

### The gate that says the re-render moved only what the fixes touch

Splitting the 3,066 survivors by whether their deck bytes changed at all, and
comparing NEC-5's first impedance exactly (not to a tolerance):

| group | decks | comparable | impedances that moved |
|---|---:|---:|---:|
| deck bytes unchanged | 2,896 | 2,772 | **0** |
| remeshed by #1416 | 170 | 170 | **95** |

Zero drift on 2,772 unchanged decks is the check on the instrument: whatever
moves in the re-rendered tables is #1416's remesh or #1430's removals, and
nothing else. (75 of the 170 remeshed decks answer identically anyway — a
remesh that changes the mesh need not change the impedance.)

## The momwire side

Running: two passes at `--jobs 4`. **`--jobs` matters, and only to the wall
clock.** The script's default is 1; the published run recorded
`_meta.environment.jobs = 4`. A 1-way pass measured ~3x the wall for **0.93x**
the summed per-deck `wall_s` over the 1,634 decks it reached — same work, same
speed per deck, a wall figure that cannot be put beside the published 889 s. The
1-way partial is kept as `census-1430-momwire-j1-partial.jsonl` so the
dispatch-width question can be answered from data rather than by assertion.

## One page correction that is not about the numbers

The page's Method section says it regenerates with
`census_report.py --nec5 <a> --momwire <b>`. Run exactly that way the script
prints the tail table with **25** rows; the page carries **20**. The flag
`--cases 20` is what the page was actually generated with, and with it the
committed script reproduces the page's generated half **byte for byte** from the
committed data — checked. The claim was true; the command recording it was
incomplete, and the re-render states the flag.
