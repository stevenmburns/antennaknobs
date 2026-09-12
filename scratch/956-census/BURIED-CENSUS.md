# momwire#956's crossing fix across every buried-wire case we have

**What this is.** momwire#1043 (the W terms: the ẑẑ kernel is `k²V + ∂z′W`, and the
test axis's ends carry `TW`) was derived on four decks. This measures it on every
buried-conductor case in the antennaknobs catalog and every one in the public NEC
corpus, against NEC-5.

**Three momwire columns, not two.** The shipped pointer and momwire main differ by
two separate changes, and the census isolates each:

| column | commit | what it adds | file that moves |
|---|---|---|---|
| pointer | `23d81e5` | v0.53.0, the submodule pointer antennaknobs ships | — |
| mid | `0e72ab4` | momwire#1004, separation-aware quadrature for the cross block | `_below_interface.py` |
| main | `ad3cb9f` | momwire#1043, the W terms | `_crossing_fill.py` |

`git diff` over `*.cpp *.hpp *.h setup.py` is **empty across both legs**, so one
set of compiled accelerators serves all three checkouts, and no meshing code
differs either — which is what makes the columns the same mesh by construction.
Each row records both files' hashes, so which change a row saw is checkable and
not merely asserted: `_below_interface.py` moves on the first leg only,
`_crossing_fill.py` on the second only.

**The rig check I did not design.** On the #956 deck itself the main column reads
**78.13206040785917 + 46.337676999832134j**, against the `78.13206+46.33768j`
momwire#956's own derivation comment published from a different box and a
different harness. Agreement to every printed digit, before any of the numbers
below were looked at.

## Population A — the catalog

Enumerated by `_has_buried_wire`'s own test (any conductor vertex at z < 0) over
every **(design, variant)** pair the catalog declares, not over designs at their
default params: `buried_radial_vertical` ships four junction conventions and its
own docstring calls them different conductors. Default soil (13.0, 0.005) — the
app's `DEFAULT_GROUND` and #956's soil A — at 7.1 MHz, at the catalog mesh and at
`nominal_nsegs` × 2. NEC-5 side: `NEC5Engine.deck()`, never a hand-written deck,
solved by `nec5cl-x13` (sha256 `2068ae67…`), the binary the #896 census page names.

**The classification is four classes, not two.** The brief's split was crossing
versus wholly buried; the catalog has four shapes, and lumping the middle two
with either end would have made a prediction look confirmed or falsified for the
wrong reason:

| class | meaning |
|---|---|
| crossing | a vertex at z = 0 with conductor **both** above and below it |
| contact+split | a vertex at z = 0, conductor above it, buried conductor elsewhere |
| split | conductor above and below, nothing touching z = 0 |
| wholly buried | no conductor above z = 0 at all |

### The rows (Ω, at 7.1 MHz)

| design | variant | class | nn | pointer | mid | main | NEC-5 |
|---|---|---|---:|---|---|---|---|
| `specialty.buried_dipole` | default | wholly buried | 21 | 146.7897+45.8227j | *identical* | *identical* | 146.3900+44.3820j |
| | | | 42 | 146.7791+45.7280j | *identical* | *identical* | 146.4800+44.3820j |
| `verticals.buried_radial_vertical` | default | **crossing** | 21 | 75.8482+40.4523j | *identical* | **78.1321+46.3377j** | 77.8050+44.4680j |
| | | | 42 | 75.8586+40.5009j | *identical* | **78.1425+46.3863j** | 77.9370+45.2030j |
| `verticals.buried_radial_vertical` | bundle | **crossing** | 21 | 75.8505+40.7600j | *identical* | **78.1344+46.6461j** | refused |
| | | | 42 | 75.8609+40.8087j | *identical* | **78.1447+46.6948j** | refused |
| `verticals.buried_radial_vertical` | detached | contact+split | 21, 42 | refused | refused | refused | refused |
| `verticals.elevated_buried_counterpoise` | default | split | 21 | 44.5602−73719.3196j | *identical* | *identical* | 30.6430−61604.0000j |
| | | | 42 | 42.7896−72708.6105j | *identical* | *identical* | 29.4170−61557.0000j |

*identical* means **bit-identical**, checked on the float and not on four
decimals.

### What the three columns say

**momwire#1004 moves nothing here.** Bit-identical to the pointer on all eight
solvable cells. Its target is a near-plane cross block, and no catalog buried
design presents one.

**The W terms move exactly the crossing decks, and nothing else.** Bit-identical
on wholly buried and on split; on both crossing variants, at both meshes:

| | ΔR | ΔX |
|---|---:|---:|
| `buried_radial_vertical` default, nn 21 | **+2.2839** | **+5.8854** |
| default, nn 42 | +2.2839 | +5.8855 |
| bundle, nn 21 | +2.2838 | +5.8861 |
| bundle, nn 42 | +2.2839 | +5.8861 |

The same shift to four decimals across two conventions and two meshes. A
discretisation error does not do that; a convention term does, which is what
momwire#956's rise ladder said before this fix existed.

**`split` does not move, and that is a measurement rather than a prediction.**
A split deck has no crossing node but DOES have an above × below block, and
momwire#956's own probe20/probe6 measure the fill against the transmitted grid on
non-crossing decks — so "no crossing node" did not obviously imply "does not
move". `elevated_buried_counterpoise` is bit-identical across all three commits,
so on this geometry the W-term change reaches only decks with a crossing junction.

### Against NEC-5: a 6× to 10× improvement, larger at the finer mesh

| design | nn | \|ΔR\| pointer | \|ΔR\| main | ×better | \|ΔX\| pointer | \|ΔX\| main | ×better |
|---|---:|---:|---:|---:|---:|---:|---:|
| `buried_radial_vertical` default | 21 | 1.9568 | **0.3271** | 6.0 | 4.0157 | **1.8697** | 2.1 |
| | 42 | 2.0784 | **0.2055** | 10.1 | 4.7021 | **1.1833** | 4.0 |
| `buried_dipole` | 21 | 0.3997 | 0.3997 | 1.0 | 1.4407 | 1.4407 | 1.0 |
| | 42 | 0.2991 | 0.2991 | 1.0 | 1.3460 | 1.3460 | 1.0 |
| `elevated_buried_counterpoise` | 21 | 13.9172 | 13.9172 | 1.0 | 12115.3196 | 12115.3196 | 1.0 |
| | 42 | 13.3726 | 13.3726 | 1.0 | 11151.6105 | 11151.6105 | 1.0 |

The improvement is **bigger at the refined rung** (6.0× → 10.1× in R, 2.1× → 4.0×
in X), which is the opposite of what a mesh artefact does. The brief's prediction
was +2 to +10 Ω in R toward NEC-5 on crossing decks: measured **+2.28**, the low
end of the band, on a 4-radial hub at 0.15 m — #956's own rods moved +1.86 to
+9.98 over L = 0.30 to 1.20 m, so the band is a length effect and this deck sits
where its geometry puts it.

### Two rows that are not about the fix

**`detached` (the stake convention) has no column at all.** Both engines refuse
it, each by name: momwire — *"wire 4 stands an END in the ground plane (ground
CONTACT) and wire 0 is buried below it: that COMBINATION is not served, though
each half is"*; our own NEC-5 engine — *"a conductor ends ON the ground plane at
(0, 0, 0) while this deck also has buried wires: NEC-5 has no documented spelling
for that combination"*. Four refusals, no data, and that is the state of the
convention rather than a gap in this census.

**`elevated_buried_counterpoise` disagrees with NEC-5 by 14 Ω in R and ~12 kΩ in
X, and no change here touches it.** On a |Z| near 70 kΩ that is ~20 %, the largest
disagreement in Population A by far, identical at both meshes and across all
three commits. It is a **split** deck, so the W terms leave it alone by the
measurement above. Worth its own look; it is not evidence about #1043 either way.

## Population B — the public NEC corpus

**The corpus cannot exercise this fix.** Eight decks qualify, and all eight are
refused by momwire at all three commits. The interesting part is why, because the
first two reasons are ours.

### Selecting the population: two traps, both of which bit

**`GN 2` does not appear in the translated corpus at all.** It is the NEC-2
spelling. Filtering on it — as the brief asked — returns **zero decks**, which is
exactly the shape of an empty result that reads as a finding. In NEC-5, `GN 0` and
`GN 2` are the same Sommerfeld ground, and the translated tree carries GN 0
(1,176 decks), −1 (701), 1 (205) and 3 (42).

**The geometry has to come from a parser.** 384 candidates carry a transform card,
and `GS 0 0 .3048` — feet to metres — is everywhere in the 4nec2 collections. A
first cut read the `GW` columns directly, mis-indexed them, and classified
`4nec2-models/HFbeams/2lyagi20.nec` as **wholly buried at "zmin −8.67"** — that
was its *y* offset, and the deck is a Yagi at 70 ft. It reported **681 members**
where there are 8. Geometry now comes from `antennaknobs.nec_import.parse_nec`,
whose `NecWire` is "one straight wire after all geometry transforms", on the RAW
deck (the importer is a NEC-2 reader and declines the NEC-5 dialect's `EX`
edge-source form on 1,175 of 1,176 translated decks). The same deck now reads
21.3360 m = 70 ft × 0.3048.

### The eight decks

| deck | class | zmin (m) | wires | NEC-5 Z | momwire, all three commits |
|---|---|---:|---:|---|---|
| `cebik …/Tutorial-2/ch-1/1-3.nec` | crossing | −0.1638 | 32 | 41.8150+4.6753j | refused |
| `cebik …/Tutorial-2/ch-3/3-2.nec` | crossing | −0.1638 | 32 | 41.8150+4.6753j | refused |
| `cebik …/Tutorial-2/ch-11/11-4a-nec4.nec` | crossing | −0.0040 | 10 | 37.4470−3.7412j | refused |
| `cebik …/LPDAs/nec/lpma3r5-4-6el86ft75o-buriedradials.nec` | crossing | −0.6858 | 976 | 50.5850−4.1415j | refused |
| `cebik …/Phased-Arrays/nec/1r5-bc3elendfire-burrad.nec` | crossing | −0.1928 | 70 | 0.0209−0.0304j | refused |
| `cebik …/Phased-Arrays/nec/1r8-4el-endfire-burrad.nec` | crossing | −0.1640 | 93 | 0.0035−0.0172j | refused |
| `4nec2-models/HFActiveFeed/2lsloper.nec` | split | −68.0000 | 2 | 24.3570−19.2450j | refused |
| `icecube-dbesson/2lsloper.nec` | split | −68.0000 | 2 | 24.3570−19.2450j | refused |

(The two phased-array decks' NEC-5 impedances are ~0.02 Ω and ~0.003 Ω, which
`compare`'s own degeneracy rule would exclude anyway.)

### Why, in three layers

**Layer 1, ours: the `GE` flag.** Six decks carry `GE -1`, and momwire says
*"GE -1 declares the ground plane without the ground-contact current expansion …
this engine serves the interpolated (GE 1) contact only"*.

**Layer 2, also ours: the ground model.** Rewrite `GE -1` → `GE 1` and all six
refuse again, now with the same sentence as the two `2lsloper` decks: *"ground
CONTACT under ground_model='refl-coef' is refused"*. momwire is solving these
under the **reflection-coefficient approximation** — because `translate` rewrote
their `GN 2` to `GN 0`, and momwire honours the NEC-2 meaning of that card.

**Layer 3, momwire's declared scope.** Lift both (`GN 0` → `GN 2`, `GE -1` → `GE 1`)
and the refusals become substantive, one scope limit per deck, identical at all
three commits:

| decks | refusal |
|---:|---|
| 4 | *"crossing serve with per-wire radii: the radius rule ρ_eff = √(ρ²+a²) regularizes the corner with ONE wire radius, and a mixed-radius convention is not pinned"* (momwire#524 phase 2) |
| 3 | *"below/below pair separation of R1 = 135.583 m (8.93 in-medium wavelengths), past the … 4 in-medium wavelengths the below/below remainder is tabulated to"* |
| 1 | *"RP asks for the far field of a deck with a wire below the ground plane, and a buried deck's radiation pattern is not served"* |

NEC-5 solves all eight on that tree. So the honest statement about Population B is
not "the fix does not help there" but **"no public deck in this corpus is inside
momwire's crossing scope, and the four that come closest are stopped by the
mixed-radius corner rather than by anything #1043 touches"**. Population A is the
whole evidence base, which raises rather than lowers the value of #956's rod
ladders.

## A defect found on the way, and the conclusion it does NOT support

`translate` rewrites **`GN 2` → `GN 0` on 1,104 of the 1,105** raw decks carrying
it, against the corpus tool's own documented contract ("GN -1 / GN 1 / GN 2
pass"). The consequence is not cosmetic: the two engines read `GN 0` differently
and both are self-consistent — NEC-5 has no reflection-coefficient option, so
there `GN 0` IS Sommerfeld, while momwire's portal reads `GN 0` as refl-coef and
`GN 2` as Sommerfeld. Measured by running one deck under each spelling and reading
the portal's own ENVIRONMENT block:

```
GN 0 0 0 0 13 .005   ->  FINITE GROUND - REFLECTION COEFFICIENT APPROXIMATION
GN 2 0 0 0 13 .005   ->  FINITE GROUND - SOMMERFELD SOLUTION
```

So on **930 of the #896 census's comparable decks** the published comparison is
momwire refl-coef against NEC-5 Sommerfeld: two ground models, not two
formulations of one problem.

**And the conclusion that invites is wrong.** Re-solving a seeded 120-deck sample
under `GN 2`:

| momwire ground model | median \|ΔZ\|/max | p75 | p90 | > 1 % | > 10 % |
|---|---:|---:|---:|---:|---:|
| refl-coef (`GN 0`, as censused) | 0.0994 | 0.2932 | 0.9534 | 110 | 59 |
| Sommerfeld (`GN 2`) | **0.0907** | 0.2584 | 0.9534 | 108 | 55 |

Sommerfeld is closer on **63 of 118** — a coin flip — and the **reactance-sign
disagreement count does not move at all: 28 → 28**. A real defect with a small
effect, which is worth knowing precisely because "the census compares two
different ground models" sounds like it should explain the census's headline and
#1417's sign group, and it explains neither.

## Provenance

- **NEC-5**: `nec5cl-x13`, sha256 `2068ae67a7fb1225…`, 1,265,856 bytes — byte-identical
  to the binary the #896 census page's own metadata names. Decks from
  `NEC5Engine.deck()` (Population A) and the translated corpus tree (Population B);
  every row records the deck's sha256.
- **momwire**: three checkouts of the same repository, selected per child process
  by `PYTHONPATH`, each row carrying the commit, `_crossing_fill.py`'s hash,
  `_below_interface.py`'s hash and the `dzpW` / `TW` token counts — because all
  three report version `0.53.0` and a version string cannot tell them apart.
- **Threads** pinned to 1 (`OMP`, `OPENBLAS`, `MKL`) for every momwire cell.
- **The antennaknobs submodule pointer is untouched**; the two extra checkouts are
  git worktrees outside the repo.

## Reproducing

```
python scratch/956-census/enumerate_population_a.py
NEC5_EXE=~/nec5-timing/nec5cl-x13 \
MOMWIRE_MID=~/momwire-0e72ab4/src MOMWIRE_MAIN=~/momwire-ad3cb9f/src \
    python scratch/956-census/popa_run.py
python scratch/956-census/popb_select.py --src ~/nec5-timing/nec5-1430 --raw ~/nec5-timing/raw
python scratch/956-census/popb_table.py
python scratch/956-census/gn_ground_probe.py
```
