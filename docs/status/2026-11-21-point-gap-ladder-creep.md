# The slow tail of a refinement ladder: a zero-width feed gap, on every engine

**The question.** On a deck fed at a knot or by a delta gap, `antennaknobs ladder` often shows a last few steps that stop shrinking (step ratio about 1.1–1.3 where a discretisation error would give about 3 per tripling). Is that an engine failing to converge?

**The answer, measured.** No. It is the feed model. A zero-width gap has no limiting reactance: refining the mesh shrinks the fed segment, and the gap's susceptance grows by about **ΔB ≈ 4·ln3·ω·ε₀·a per tripling** of the segments (**6.85 µS** at a = 1 mm and 28 MHz). bs2, razor-2p and licensed NEC-5 all carry it. A gap of fixed physical width (antennaknobs' `PortAtEnd` pair, bspline `junction_ports`) has a limit and converges. The law is stated in momwire's `BSplineSolver` `exact_kernel` docstring; the diagnosis is momwire#2055's.

**The builds.** antennaknobs 0.123.2 (it includes AK#2338, which keeps a NEC-5 TL/NT end on its knot when a deck is refined; ladders on such decks before it compared different decks), momwire 0.96.0 from PyPI, licensed NEC-5 run as an executable and never inspected. Invented decks only.

## How big it looks depends on |Z|²

The step in ohms is about **dZ ≈ −j·Z²·ΔB** per tripling, so the same microsiemens are invisible at a low-impedance feed and dominant at a high one:

| feed | Z (Ω) | ΔB (a = 1 mm, 28 MHz) | predicted dZ per tripling |
|---|---|---|---|
| centre-fed half-wave dipole | 73 + j6 | 6.85 µS | 0.006 − j0.036 |
| 2 m straight wire, off-centre knot source (#2055) | \|Z\|² ≈ 1.2e6 | | several ohms in X |
| strongly reactive feed (#2055's bend-load deck) | \|Z\|² ≈ 1.7e5 | | about 1–2 ohms in X |

The ratio of segment length to radius decides when the tail takes over: momwire#2055 found the steps flat at h/a ≈ 3 and still shrinking at a ten or a hundred times thinner wire.

## Measured: the off-centre knot source (momwire#2055)

2 m straight wire, 8 segments, knot source at knot 3; X step in ohms per tripling:

| rung | NEC-5 | bs2 |
|---|---|---|
| 1→3 | 27.3 | 28.4 |
| 3→9 | 13.7 | 17.4 |
| 9→27 | 8.7 | 10.6 |
| 27→81 | 7.5 | 8.1 |

Both engines approach the same per-tripling floor, about 6.3–6.8 µS in admittance: the law above.

## Measured: a centre-fed dipole, where the gap term is negligible

Invented deck: `GW 1 21 0 0 -2.6 0 0 2.6 0.001`, `EX 0 1 11 0 1 0`, 28 MHz, free space. `antennaknobs ladder --refine 1 3 9 27`:

| segments | bs2 | razor-2p | NEC-5 |
|---|---|---|---|
| 21 | 72.863 + j5.278 | 71.661 − j1.494 | 71.663 − j1.494 |
| 63 | 72.962 + j5.531 | 72.560 + j3.154 | 72.562 + j3.153 |
| 189 | 73.021 + j5.714 | 72.852 + j4.695 | 72.853 + j4.692 |
| 567 | 73.061 + j5.855 | 72.982 + j5.374 | 72.981 + j5.360 |

* razor-2p and NEC-5 agree to about 1e-4 at every rung and converge as a discretisation error does (step ratio 3.0, 2.3).
* bs2 starts within 0.2 Ω and j0.5 Ω of where the other two are heading (about 73.05 + j5.7) and moves least.
* bs2's own small steps (+j0.25, +j0.18, +j0.14) are **not** the gap term: that predicts −j0.036 at this impedance, the other sign. They match momwire#2055's open follow-up 2 (bspline's answer near open wire ends still moving at high refinement), which is a separate, open question.

## What to do with a ladder

* When the last steps stop shrinking and the feed is a knot or delta gap, compare in **admittance** (the gap term is a constant ΔB per tripling there), or refine only to h/a ≳ 30, or use a fixed-width gap.
* Read "not yet asymptotic" in the ladder's Z∞ line as possibly this term, not as an engine fault.
* A ladder note that names the term when h/a < ~10 is momwire#2055's follow-up 1.

**Rerun.** The dipole deck above; `NEC5_EXE=<licensed nec5> antennaknobs ladder --builder @dipole.nec --refine 1 3 9 27 --engines momwire:bspline momwire:razor-2p nec5 --ground free`. The #2055 decks and probe: momwire branch `bspline-knot-load-creep-2055`, `scratch/2055-knot-gap-creep/` (598e7d14).
