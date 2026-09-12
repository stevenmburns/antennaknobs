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

Two passes at `--jobs 4`, **887 s** and **885 s**, against the first
publication's 891 / 889 / 889 s. Determinism: **0 of 3,066 rows differ** on
anything but `wall_s` — status, error text, impedance and advisory classes all
identical.

**`--jobs` matters, and only to the wall clock.** The script's default is 1; both
publications recorded `_meta.environment.jobs = 4`. A 1-way pass measured ~3x the
wall for **0.93x** the summed per-deck `wall_s` over the 1,634 decks it reached —
same work, same speed per deck, a wall figure that cannot be put beside 889 s.
The 1-way partial is kept as `census-1430-momwire-j1-partial.jsonl` so the
dispatch-width question can be answered from data rather than by assertion.

### What moved, and why

| group | decks | status transitions |
|---|---:|---|
| deck bytes unchanged | 2,896 | **none** |
| remeshed by #1416 | 170 | `error` -> `ok` on **158**; 12 unchanged |
| removed by #1430 | 10 | were 5 `ok`, 3 `error`, 2 `no-drive` |

All 158 flips carried the same refusal text: `LD 5 conductivity on a partial-wire
segment range is not supported by this engine`. That is the defect the published
page reported as **its own largest cost — 175 decks** — and #1416 retires 158 of
them. One more of the 175 left the corpus under #1430.

### The 16 that still refuse, split by measurement rather than by assumption

Reading the AUTHORS' raw decks, not the translated ones:

- **11** carry `LD 5` on a range that is already partial before any remesh.
  momwire's nec2 dialect has per-wire conductivity and no partial ranges, so
  those are its dialect limit and nothing to do with `translate`.
- **5** are still ours, in a form #1416 does not reach — `LD 5 0 1 N`, a **tag-0**
  load over absolute segment numbers where N is the whole structure's segment
  count:

  | deck | segments raw -> translated | `LD` range |
  |---|---|---|
  | `sokyrad/k8uy_yagi_10el/models/K8UY_yagi_2m_original.nec` | 211 -> 222 | `1 211` |
  | `sokyrad/unsorted/K8UY_yagi_2m_original.nec` | 211 -> 222 | `1 211` |
  | `sokyrad/unsorted/2m70cm_moxon_nested.nec` | 97 -> 99 | `1 97` |
  | `sokyrad/unsorted/2m70cm_moxon_nested_four_masted.nec` | 395 -> 403 | `1 395` |
  | `sokyrad/unsorted/6m_2m_70cm_moxon-yagi.nec` | 136 -> 139 | `1 136` |

  The remesh grows the structure and leaves the range where it was, so a
  whole-structure load becomes a partial one. #1416 made a whole-WIRE range stay
  whole-wire; this is the whole-STRUCTURE form, and it is the hole in **#1423**.

### `no-drive`

Six at first publication, **four** now. The two that left are
`necpp/patch_999.nec` and `necpp/patch_999_2.nec`, which #1430 refuses at
translation because each lists the same wire twice. They are out of the corpus,
not re-classified.

## Two page corrections that are not numbers

**The regeneration command was incomplete.** The Method section said
`census_report.py --nec5 <a> --momwire <b>`. Run exactly that way the script
prints the tail table with **25** rows; the page carries **20**. The flag
`--cases 20` is what the page was generated with, and with it the committed
script reproduces the page's generated half **byte for byte** from the committed
data — checked in both directions, on the old data and on the new. The claim was
true; the command recording it was not complete.

**The footer never named momwire.** `census_report.py` read
`environment.momwire_version`, a key the artifact has never written, so the
published page names its NEC-5 binary and prints `momwire: ?`. It now reads
`environment.momwire.{distribution,commit,dirty}` and prints
`0.53.0 @ 23d81e5 clean`. This matters beyond tidiness: the census runs momwire
at the submodule POINTER, which normally sits ahead of the released version, so
the version string alone does not identify the solver that answered.
