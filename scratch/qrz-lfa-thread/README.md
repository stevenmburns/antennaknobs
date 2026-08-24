# W7EL's NEC-2/NEC-4 coupled-loop pathology model

`NEC-4 coupled loop.ez` — EZNEC binary model, 1,877 bytes,
md5 `0659f9d0c7dcd9bb8c18022f421dec7c`.

Downloaded 2026-08-20 (with user permission) from Roy Lewallen W7EL's post #11
in QRZ forums thread 1000972, "Stability of NEC for Loop Fed Antenna (LFA)
Yagi-Uda topologies" — attachment id 1527471, posted there as
`NEC-4 coupled loop.ez.txt` ("remove the extra .txt extension").

Roy's claim: under an NEC-2 or NEC-4 engine, the source delivers < 1 A while
the small horizontal loop carries > 150 A, in free space; per Jerry Burke
(quoted in the post) the spurious loop current comes from quadrature error in
the line integral of grad(phi) around the loop, grows as 1/f, is worse over
ground, and NEC-5's basis is free of it.

## The model (all questions CLOSED by Windows sitting 4, 2026-08-20/21)

Title `NEC-4 Example`; metres; **500 Hz** (`FR 0,1,0,0,.0005` — not the
5 MHz the header float suggested; the low frequency is what makes the 1/f
pathology this large); `EX 0` voltage source at wire 1 segment 14, drive
−j404675.9 V; free space (`GN -1`); the binary's "radius 0.01" field was a
DIAMETER (decks write radius .005). Geometry as decoded here earlier: a
300 m vertical (15 segs) standing on the rim of a closed 80×80 m square
loop at z = 0 (4+4+4+3+1 segs), the base a three-wire junction.

**Pathology reproduced during the sitting, controlled**: same deck, same
machine, minutes apart — NEC-2 puts **162 A** in the loop on a sub-ampere
source; NEC-5 does not. CORRECTION to the sitting notes (2026-08-21): the
"loop 1.0e-6 A" figure was an EZNEC *display* reading; NEC-5's own printout
(capture 0122, this directory) shows the loop carrying ~0.48 A of legitimate
through-current — charge distribution onto the loop from the 404 kV drive —
element-max 4.79204E-01 A. Quote the printout, never the display figure.

**momwire result (2026-08-21, momwire 0.35.0 `momwire.eznec`, this box)**:
the same deck (launch spelling `GE 0,-1`) serves, and the printed current
table matches NEC-5's **element for element to ≤0.5 %** — source 1.0910 A
vs 1.0863 A; loop elements 16–31 all within a few parts per thousand
(e.g. 4.80727E-01 vs 4.79204E-01). The three-way table for the pitch:

| engine | source | max loop element |
| --- | --- | --- |
| NEC-2 (EZNEC internal) | 0.7325 A (display) | **162 A** — the pathology |
| NEC-5 (capture 0122 printout) | 1.0863 A | 0.4792 A |
| momwire 0.35.0 (`momwire.eznec`) | 1.0910 A | 0.4807 A |

**The 1/f falsification sweep (momwire, 2026-08-21)**: same deck at 50 kHz /
5 kHz / 500 Hz / 50 Hz / 5 Hz. Source current scales exactly ∝ f (a pure
858 pF capacitor charging off the fixed 404 kV drive) and the loop/source
ratio is **0.4406, frequency-independent to four digits across four
decades** (0.4413 at 50 kHz — retardation just beginning). The NEC-2 defect
grows as 1/f: had momwire carried any trace of it, the ratio would have
climbed ~100× per two decades downward. Flat to 5 Hz bounds any spurious
loop EMF at ≥9 orders of magnitude below NEC-2's on this model. This is a
discretization property, not source modeling: both engines ran the same
`EX 0` card; momwire's B-spline carries charge as the exact in-basis
derivative of the current, so the scalar-potential loop integral telescopes
to zero identically and there is no residual EMF for the loop to amplify —
the same class of fix as NEC-5's basis, arrived at independently.

**The engine study (2026-08-21, session scratchpad `engine-study/`)**: all
nine momwire formulations on Roy's geometry, 5 MHz → 5 Hz. momwire's own
point-matched sinusoidal solver — the NEC-2 twin — **reproduces the defect
quantitatively: loop/source 223.9 vs NEC-2's 221.2 (1.2 %)**, textbook
circulating mode, implied spurious loop EMF ≈ 400 V flat in frequency
(0.099 % of the drive) ⇒ I ∝ 1/f. Same sinusoidal basis under GALERKIN
testing: clean. Tent basis under Galerkin and razor-blade: clean to six
digits. Point-matched PULSE basis: also clean — its scalar term is an exact
endpoint difference. So the discriminator is neither "the sinusoidal basis"
nor "point testing" as such: it is whether the tested scalar-potential term
TELESCOPES around a closed loop (Galerkin, razor-blade and pulse all do;
NEC-2's midpoint sampling of ∇φ leaves the residual). Mesh refinement kills
the sinusoidal EMF 400 → 60.9 → 0.66 V at ×1/×2/×4 — it is quadrature error
exactly as Burke said, and it is why LFA folklore calls the designs
"segmentation sensitive". Sinusoidal-Galerkin loses the loop mode to
conditioning below ~1 kHz (noise, not pathology).

**The convergence ladder + Smith trajectories (2026-08-21; `coupled-loop-ladder.png`,
`coupled-loop-smith.png`, `results.json`, `referee2.py` here)**: uniform refinement
31→496 segments, five engines. The NEC-2 scheme never converges — its feedpoint
walks the whole Smith chart (−j412 k → −j507 k → **+j92 k inductive** → −j222 k
→ −j249 k) and its loop current swings 0.8–247 A non-monotonically. The clean
engines converge first-order — **to two different limits 1.9 % apart**
(NEC-5+razor ≈ −370.4 kΩ; bs1+bs2 ≈ −377.7 kΩ), with razor riding the licensed
engine at 0.006 % at every mesh. **An independent electrostatic referee
(two-conductor gap capacitance, pure Laplace) rules: 858.7 pF → −370.5 kΩ — the
NEC-5/razor limit to 0.05 %. NEC-5 is right; the B-spline family carries a real
~2 % capacitive-feed bias → filed as momwire#518.** Segmentation verdict: Roy's
mesh is perfectly uniform (20 m everywhere, junction-balanced) but ~6 % under-
converged on loop current (0.479 vs limit ≈ 0.512, first-order); and wire 6's
single segment cannot be hosted by tent-basis engines (razor refuses it; NEC-5's
knot machinery accepts it).

> **CORRECTION (2026-08-21, afternoon session): the ladder's "two clean limits
> 1.9 % apart" and the #518 bias claim above are OVERTURNED — a geometry bug
> in `ladder.py`'s `run_bspline`, not a solver defect.** Splitting wire 1 at
> the feed shifted every later wire's index by one, and the junction list was
> only partially re-indexed: wire 6 (the 20 m stub) landed in no junction
> group → both ends zeroed → zero dofs → electrically absent, plus two groups
> tied wire ends 60–100 m apart. `BSplineSolver` accepted all of it silently
> (validation gap filed as momwire#522). Verified four ways
> (`ladder_geometry_postmortem.py` here): the buggy spec reproduces
> `results.json`'s bs rows to all ten stored digits; a clean no-stub model
> matches the recorded ladder ≤ 0.05 % at every rung; the same spelling with
> the junction list FIXED converges onto the referee (bs1 −370.73 / bs2
> −370.65 kΩ at 496 segs; bs2 at Roy's own mesh −370.90 ≡ the seam's printed
> 1.0910 A; loop 0.5101 vs NEC-5's 0.5100 A); and the referee re-run on the
> stub-less geometry certifies the "biased" number (841.6 pF → −378.2 kΩ).
> Corrected data/figure: `results-corrected.json`, `figures_corrected.py`,
> `coupled-loop-smith-corrected.png` — **the original
> `coupled-loop-smith.png`/`coupled-loop-ladder.png` carry stale annotations;
> use the corrected Smith for anything outward-facing.** Also corrected: only
> RAZOR refuses a 1-segment both-ends-junctioned wire; bs1/bs2 host it fine —
> "tent-basis engines can't host wire 6" was an over-generalization. Net for
> the pitch: on Roy's model NEC-5, razor, bs1, bs2 AND the electrostatic
> referee agree at −370.5 kΩ; only the NEC-2 scheme diverges. Correction
> posted on momwire#518 (recommend close); N4PC (captures 0081–0084) is
> un-attributed again and needs its own investigation.

One seam wrinkle found on the way: EZNEC's File→export writes `GE 0`
(one field) where its engine-launch decks write `GE 0,-1`; the seam's
no-blank-defaulting refusal fires on the export form. Launch decks are the
protocol; noted for the docs.

(The spy captures 0122/0123 were excised from public PR #970 into this
directory — the deck follows the .ez's own pre-contact rule.)

## Files

| file | what |
| --- | --- |
| `NEC-4 coupled loop.ez` | Roy's original, byte-for-byte |
| `coupled-loop-nec2.nec` | EZNEC's export, NEC-2 format (= the forum audience's deck) |
| `coupled-loop-nec5.nec` | EZNEC's export, NEC-5 format (= what the momwire portal consumes) |
| `cardL-nec2.nec` / `cardL-nec5.nec` | the bundled Cardioid-L model exported BOTH ways — a two-dialect Rosetta pair (NEC-2 side: extra virtual wire, gyrator `NT`, `GN 1`+`GD 2`+`RP 3` MININEC idiom, `EX 0`; NEC-5 side: `EX 4` + bare `GD`, the deck the seam serves as capture 0000) |
| `ladder_geometry_postmortem.py` | the #518 postmortem repro: buggy-vs-fixed junction lists, referee ± wire 6 |
| `results-corrected.json` | bs1/bs2 ladder re-run with the junction list fixed (k = 1…16) |
| `figures_corrected.py` / `coupled-loop-smith-corrected.png` | the corrected Smith chart — four clean engines + referee, one mark (use THIS one outward) |
| `518-correction-draft.md` | the correction comment as posted on momwire#518 (2026-08-21) |

The two coupled-loop exports differ ONLY in the `CM` format-comment line —
"no special NEC-4-isms" confirmed exactly. (The Windows-transfer copies with
EZNEC's own filenames, `NEC-4/NEC-5 coupled loop.nec`, were byte-identical
duplicates and are not kept here.)

## Status

Held for the LFA/coupled-loop driving-example sequencing: the pathology
ledger and the seam demo both have everything they need in this directory.
Do not post publicly before the Ward → Roy → Arie contact sequence
(PITCH-EZNEC-4NEC2.local.md); the memory file `qrz-lfa-thread` tracks the
decision state. This directory is deliberately untracked.
