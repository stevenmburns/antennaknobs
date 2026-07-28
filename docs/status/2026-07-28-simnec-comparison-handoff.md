# Handoff: SimNEC ↔ AntennaKNoBs full-tool comparison — status + next steps

**Date:** 2026-07-28
**Predecessor:** the original "SimNEC ↔ AntennaKNoBs full-tool comparison experiment"
handoff (a doc that lived in the requester's Downloads, not the repo). This
supersedes it with (a) verified results, (b) three corrections to its plan, and
(c) a clean two-track structure. Read this instead.

**One-line goal:** compare the *whole* SimNEC tool (NEC2 antenna + its MNA
circuit solver) against AntennaKNoBs (momwire/PyNEC antenna + network reducer)
on a coupled antenna + feedline + tuner → rig system, and locate where they
agree and where they diverge (common-mode).

---

## TL;DR status

- **Track 1 — agreement (`wire.doublet_ladder_tuner`, 7.1 MHz): DONE, tools agree.**
  - Scenario 1 (antenna): SimNEC `nec2c` == PyNEC to <0.1 Ω on an identical mesh.
  - Scenario 2 (coupled rig): **SimNEC 40 − j5.7 (SWR 1.29) vs AntennaKNoBs 41.9 − j5.8 (SWR 1.24)** — ~2 Ω, identical reactance.
- **Track 2 — divergence (`wire.doublet_balanced_tuner`, 14.1 MHz): DONE.** The common-mode "money shot". Compared with a matched (center-fed) feed: AntennaKNoBs symmetric **28.75 + j27.03 (SWR 2.41)** vs SimNEC **28.95 + j25.18 (SWR 2.31)** — agree to ~2 Ω; break symmetry and AntennaKNoBs fans SWR 5.0→5.7 across `line_zcomm` while SimNEC (no zcomm knob) holds one value.
- **Bonus delivered:** a validated AntennaKNoBs → SimNEC `.ssn` exporter prototype (issue #600).
- Reproduce everything: `scratch/simnec/*.py` (see [Reproducing](#reproducing)).

---

## Three corrections to the original plan (important)

1. **The original showcase design is a bad choice for the *agreement* scenarios.**
   `wire.doublet_balanced_tuner` feeds the doublet at its **arm-ends** across a
   0.04 λ gap (`PortAtEnd`), which (a) is **momwire/BSpline-only** — `PortAtEnd`
   is not supported on the Sinusoidal basis (the closest-to-NEC one) yet — and
   (b) presents a feedpoint ~100 Ω off the center-fed NEC value, which the stiff
   reactive point amplifies into a large rig-level disagreement. Built exactly
   per the original doc (center-fed 342+j962 → single-ended L-net) the rig lands
   ~28 − j25 / SWR 2.34, **not** the promised 51.8 / 1.04. → **Use a center-fed,
   single-ended design for agreement.** We switched to `wire.doublet_ladder_tuner`.

2. **Scenario 3's headline test as written produces a NULL result.** Sweeping
   `line_zcomm` on the *symmetric* balanced doublet gives a **bit-identical** rig
   answer (no common mode is excited under symmetry). You **must break symmetry**
   (one arm longer, or one side lowered) for AntennaKNoBs to move and the
   SimNEC-can't-follow contrast to appear. The original doc buried this in an
   optional parenthetical.

3. **The antenna feedpoint is delta-gap mesh-sensitive and converges slowly.**
   Both tools *under-converge* at default mesh (SimNEC ~76 seg → 188+j583) — the
   Richardson-extrapolated truth is **192.9 + j589.8**. Both tools sit on the
   same convergence curve, so they agree with *each other* at matched mesh; just
   don't call any single default-mesh feedpoint "the answer".

---

## Environment (fresh clone)

```bash
python -m venv .venv && . .venv/Scripts/activate   # (Windows: .venv/Scripts/python.exe)
pip install -e .            # antennaknobs + momwire submodule + PyNEC
```
Sanity: `python -c "import antennaknobs, PyNEC, momwire; print('ok')"`.
Windows console + non-ASCII: prefix runs with `PYTHONIOENCODING=utf-8`.

**SimNEC** (proprietary freeware, Windows/Java): download "windows64 with JRE"
from https://www.ae6ty.com/smith_charts/. Version used here: **5.1a1**. It stores
working files under `~/.SimNEC/<maj>/<min>/` — notably `lastConstructedNEC.nec`
(the deck it actually solved, post re-mesh) and `lastCircuit.ssn` (the live
circuit, XML). Reading those two files is the fastest way to see what SimNEC did.

---

## Track 1 — agreement (DONE)

Design: `wire.doublet_ladder_tuner` — 88 ft center-fed doublet → 100 ft of 600 Ω
open-wire line → T-network tuner → 50 Ω rig, at **7.1 MHz**, free space. Runs on
**Sinusoidal** (≡ PyNEC ≡ SimNEC `nec2c`). Single-ended, maps 1:1 to SimNEC.

### Scenario 1 — antenna only
Paste into SimNEC's N block, and **set `NECOptions.segmentsPerWavelength` high**
(the deck's segment counts are ignored — see gotcha 1):
```
NEC2
GW 1 55 0 -13.40030 10 0 13.40030 10 0.0005
FR 0 1 0 0 7.1 0
EX 0 1 28 0 1 0
NECEND
```
Target (matched mesh): ~**189 + j579** at ~76 seg; converged **192.9 + j589.8**.
Verified: PyNEC on SimNEC's *own* constructed mesh reproduced SimNEC's reading to
**0.07 Ω** → same engine, mesh-only differences.

### Scenario 2 — coupled cascade (SimNEC, right→left)
`GENERATOR(50Ω,7.1MHz)` ← `series C 81.2 pF` ← `shunt L 4.218 µH (Q=200)` ←
`series C 500 pF` ← `SERIES_TLINE(Zo=600, vf=0.95, 100 ft)` ← `N block (antenna)`.

Checkpoints (looking toward antenna, from Za=188+j583):
`line-in 162 − j496` → `+500pF 162 − j541` → `+shuntL 40 + j270` → `+81.2pF ≈ 40 − j6`.

**Result: SimNEC 40 − j5.7 (SWR 1.29) == AntennaKNoBs momwire/Sin 41.9 − j5.8
(SWR 1.24).** Agree to ~2 Ω. (Over finite ground εr=10 σ=0.002, AntennaKNoBs
gives ~49.7 − j0.1, SWR 1.01 — a documented variant, not yet built in SimNEC.)

---

## Track 2 — common-mode divergence (TODO — the money shot)

Design: `wire.doublet_balanced_tuner` — 0.72 λ doublet on 450 Ω line → balanced
L-tuner → 1:1 balun → 50 Ω rig, **14.1 MHz**, momwire/**BSpline** (PortAtEnd).

**Feed definition drives the baseline — compare tools with the SAME feed.**
SimNEC's NEC can only **center-feed** (a delta-gap on the middle segment). The
stock design's 0.04 λ **arm-end** `PortAtEnd` gap is a *different* feedpoint
(51.8 / SWR 1.04 — momwire-only, and **not** what SimNEC solves). Shrinking the
AntennaKNoBs feed gap toward 0 converges the symmetric rig answer onto SimNEC's
(the residual is the delta-gap convergence caveat, correction 3):

**Center-fed (0.004 λ gap ≈ SimNEC delta-gap) — the apples-to-apples column:**

| `line_zcomm` | symmetric | asymmetric (R arm +15%) |
|---|---|---|
| 25  | 28.75 + j27.03 (SWR 2.407) | 18.06 + j43.27 (SWR 5.004) |
| 100 | 28.75 + j27.03 (SWR 2.407) | 17.43 + j44.81 (SWR 5.333) |
| 250 | 28.75 + j27.03 (SWR 2.407) | 17.03 + j46.06 (SWR 5.591) |
| 400 | 28.75 + j27.03 (SWR 2.407) | 16.88 + j46.61 (SWR 5.699) |

SimNEC (center-fed, tuned 14.1 MHz cascade): **28.95 + j25.18 (SWR 2.31)** —
**captured** (rig readout of the cascade below, lossless line, coil Q=200) —
matches the center-fed symmetric row to ~2 Ω (same order as Tracks 1–2).

**Arm-end (0.04 λ `PortAtEnd`, momwire-only) — for reference, not SimNEC-matched:**

| `line_zcomm` | symmetric | asymmetric (R arm +15%) |
|---|---|---|
| 25  | 51.80 + j0.01 (SWR 1.036) | 26.50 + j26.77 (SWR 2.568) |
| 100 | 51.80 + j0.01 (SWR 1.036) | 25.09 + j29.43 (SWR 2.832) |
| 250 | 51.80 + j0.01 (SWR 1.036) | 24.23 + j31.38 (SWR 3.031) |
| 400 | 51.80 + j0.01 (SWR 1.036) | 23.93 + j32.17 (SWR 3.112) |

**SimNEC side (captured):** the differential cascade — `Generator(50Ω) ←
Transformer(1:1 ideal) ← series L 2.8 µH (Q=200) ← shunt C 74 pF ← TLine(450Ω,
vf 0.91, 0.40λ=8.5048 m=27.90 ft, `0/100f` lossless) ← NEC(center-fed doublet)`
at 14.1 MHz — reads **28.95 + j25.18 (SWR 2.31)** at the rig. SimNEC's TLine is purely differential
("no common-mode conduction"), so it has **no `zcomm` knob**: one fixed number vs
the AntennaKNoBs spread above. In **either** feed definition the symmetric row is
flat across `zcomm` (no common mode excited — the honest "both tools agree" null
case); only the asymmetric case diverges, and that spread-vs-point contrast **is**
the result. Both columns reproducible via `GAP_CENTER` / `GAP_ARMEND` in the script.

Doublet deck for SimNEC's N block (14.1 MHz, free space), and the anchor
feedpoint ≈ 342 + j962 (center-fed; note the arm-end vs center-fed caveat from
correction 1):
```
NEC2
GW 1 31 0 -7.65430 0 0 7.65430 0 0.0005
FR 0 1 0 0 14.1 0
EX 0 1 16 0 1 0
NECEND
```

---

## SimNEC gotchas (all "it silently changed your model" — good writeup material)

1. **Silent re-meshing.** SimNEC ignores the `GW` segment counts and applies its
   own graded taper toward the feed (+ adds the `EK` extended kernel). Control it
   with `NECOptions.segmentsPerWavelength = N` in the N-block script. (Diagnosed
   by reading `~/.SimNEC/5/1/lastConstructedNEC.nec`.)
2. **`VFnom` ≠ effective vf.** The `SERIES_TLINE` "simplified" model *displays*
   `VFnom=0.95` but computes an effective vf (~0.911 here) from its dielectric
   params, making the line 11.6° too long — this threw the rig to 52.8 instead of
   ~40. Check the reported `~deg`, not the label. (Diagnosed by reading
   `lastCircuit.ssn`.)
3. **Everything is lossy by default** — `SERIES_TLINE` `/100f` line loss, finite
   coil `Q`. Match or zero it deliberately per element.

---

## The AntennaKNoBs → SimNEC `.ssn` bridge (issue #600)

Validated: a generated `.ssn` loaded in SimNEC 5.1a1 and tracked the
AntennaKNoBs/PyNEC convergence curve exactly (segPerWl 40 → 181+j573, 120 →
188+j583). A `.ssn` is XML with LOAD / NETWORK / GENERATOR `<element>`s; the
antenna lives in the NETWORK element's escape-hatch `<equ>` script between `NEC2`
and `NECEND`. Recipe + prototype: `scratch/simnec/export_ssn.py`. #600 promotes
it to `antennaknobs.simnec_export` with a **clean bundled template** (the
prototype currently reuses a SimNEC-saved `.ssn` as its template — not in the
repo) and a CLI. Phase-2 (full networked export) needs the `SERIES_CAP`/
`SHUNT_CAP` element schemas confirmed (`SERIES_TLINE`, `SHUNT_IND` already known).

---

## Reproducing

```bash
python scratch/simnec/track1_agreement.py   # antenna deck, feedpoint, rig (both bases/grounds), checkpoints
python scratch/simnec/convergence.py         # Richardson mutual-limit -> 192.9 + j589.8
python scratch/simnec/track2_commonmode.py   # symmetric (flat) vs asymmetric (moves) zcomm sweep
python scratch/simnec/export_ssn.py          # .ssn exporter prototype (needs a template .ssn; see #600)
```

**Footgun in the Track-2 script:** `AntennaBuilder` routes instance attribute
assignment through a custom `__setattr__`/`__getattr__`. A **class-attribute**
default (`_asym = 1.0`) shadows that routing so `b._asym = 1.15` is silently
ignored (you get the symmetric geometry back). Use `getattr(self, "_asym", 1.0)`
with **no** class default, and set `b._asym` on the instance.

---

## Deliverables checklist (original doc's §11, updated)

- [x] Table 1 (antenna): PyNEC/Sin/nec2c agree; converged 192.9 + j589.8.
- [x] Table 2 (coupled rig, free space): SimNEC 40 − j5.7 vs AntennaKNoBs 41.9 − j5.8.
- [ ] Table 2 over real ground (variant): AntennaKNoBs 49.7 − j0.1 computed; SimNEC TODO.
- [x] Table 3 (common-mode sweep): AntennaKNoBs center-fed + arm-end columns done; SimNEC single value captured (28.95 + j25.18, SWR 2.31) and matches the center-fed symmetric baseline to ~2 Ω.
- [x] SimNEC gotchas documented.
- [x] `.ssn` bridge (#600 filed).
- [ ] SimNEC `.ssn` files + screenshots for the writeup.

Related issues: #593 (s1p/s2p import), #594 (auto-transformer), #595 (VNA
overlay), #596 (ladder-line-from-geometry), #599 (ferrite loss), **#600
(simnec_export)**. Memory files (auto-recalled by a Claude Code agent on this
repo): `simnec-comparison-positioning`, `simnec-comparison-scenario3-needs-asymmetry`,
`simnec-comparison-results`.
