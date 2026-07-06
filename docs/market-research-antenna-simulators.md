# Antenna Simulator Market Research & Competitive Comparison

**Date:** 2026-06-20
**Subject:** Advertised features of antenna simulation software available on the web, compared against `antenna_designer`.

> **Scope & method.** Capabilities for third-party tools are drawn from official vendor sites, product docs, GitHub, and reputable secondary sources (cited inline). They are **advertised / marketing claims**, not independently benchmarked. `antenna_designer` capabilities are taken from its own source code, docs, and tests (file-cited). Where a vendor gates pricing behind "contact sales," cost figures are flagged as third-party estimates.

---

## 1. Executive summary

The antenna-simulation market splits into three tiers:

1. **High-end commercial full-wave suites** — ANSYS HFSS, CST Studio Suite, Altair/Siemens FEKO, Remcom XFdtd, COMSOL RF, Keysight EMPro/ADS. Multi-solver (FEM/MoM/MLFMM/FDTD/asymptotic), GPU/HPC, multiphysics, CAD import, SAR/RCS/EMC. Quote-only licensing, commonly **$10K–$50K+/yr** (third-party estimates).
2. **Amateur-radio / affordable MoM tools** — EZNEC (now free), 4nec2 (free), MMANA-GAL (free/€139), AN-SOF ($999–$1,599), xnec2c (GPL), cocoaNEC (free). Almost all are **NEC-2 / MININEC thin-wire MoM**, single basis function, desktop-GUI, platform-locked. **This is `antenna_designer`'s direct competitive tier.**
3. **Open-source / Python EM ecosystem** — PyNEC/necpp/nec2c (wire MoM), openEMS (FDTD), gprMax (FDTD), Meep (FDTD, photonics-first), Sonnet Lite (planar MoM), scikit-rf (network analysis, *not* a solver), Antenna Magus (synthesis DB, *not* a solver).

**Where `antenna_designer` stands.** It occupies the same numerical niche as one solver inside the big suites (a wire MoM, comparable to FEKO's MoM, HFSS's IE solver, or ADS Momentum). Within its actual competitive tier (free/affordable amateur tools and the open Python ecosystem) it has **three differentiators with essentially no equivalent in the open peer group**:

- **Multiple basis functions** (triangular / sinusoidal / arbitrary-degree B-spline) vs. NEC's single fixed sinusoidal basis and AN-SOF's fixed triangular/pulse.
- **H-matrix / ACA acceleration + GMRES** for large-N scaling — no open MoM tool (PyNEC, nec2c, xnec2c) advertises fast-matrix/compression methods; they are all dense O(N²).
- **A modern web UI** (FastAPI + React, real-time Smith/pattern/3D/current plots) — every free peer is a native desktop app or a library/CLI with no GUI.

**Where it lags the field** (mostly vs. the commercial tier, expected for a focused tool): no FEM/FDTD/asymptotic solvers, no GPU/MPI, no multiphysics, no SAR/RCS/EMC, no CAD import, no automatic adaptive meshing, lossy/finite-ground impedance is approximate, and no `.nec` *import* yet (export now exists — see below — but round-tripping external decks back in does not).

---

## 2. `antenna_designer` capability baseline

*Source: codebase inventory of `/home/smburns/antennas/antenna_designer` + `pysim` submodule.*

| Dimension | What `antenna_designer` does |
|---|---|
| **Solvers** | Two independent engines: **PyNEC** (NEC-2 via `necpp` wrapper) and **pysim** (pure-Python MoM). pysim offers 3 basis families: **TriangularPySim**, **SinusoidalPySim** (NEC2-style 3-term), **BSplinePySim** (degree 1–2, KCL junctions, ground via images). Large-N accelerator solvers, selectable and integrated into `PysimEngine` (impedance, sweep, current, and far-field all supported): **HMatrixPySim** (ACA + GMRES + near-field preconditioner), **ArrayBlockPySim** (block-low-rank for arrays; integrated via PR 103). C++ pybind11 accelerators (`_accelerators.cpp`, libmvec SIMD sincos) for Z-matrix fill. |
| **Geometry** | 69+ wire designs: dipoles, inverted-V, Yagis, loops (delta/diamond/horizontal), fan/trap dipoles, Moxon, hexbeam, Sterba, LPDA, hentenna, + 25 Cebik reference designs (bobtail, bruce, G5RV, half-square, J-pole, quad, rhombic, W8JK, Zepp…). Arrays (1×4, 2×2, 2×4, grouped). Junctions (KCL), closed loops (driven / parasitic / terminated two-port), bent wires, multi-feed, port-based networks (TL + lumped R/L/C via `build_network`). |
| **Outputs** | Impedance Z, Γ, SWR, current distribution (knot positions/currents), far-field directivity/gain (dBi), 2D pattern rings, elevation/azimuth cuts, radiation efficiency (loaded antennas), multi-port short-circuit Y. |
| **Ground** | Free space; PEC (image method, all pysim bases); finite ground (PyNEC full Sommerfeld; pysim = PEC image + Fresnel on reflected wave — **impedance still PEC, an approximation**). |
| **Sweeps / opt** | Frequency sweep (batched swept-k Y-matrix), parameter sweep, gain sweep, pattern sweep, `scipy.optimize` (SLSQP/L-BFGS-B) parameter optimization, cross-engine comparison. |
| **UI / viz** | React 18 + Vite web frontend: 3D WebGL geometry, current distribution (mag/phase), Smith chart w/ SWR circle, polar patterns (az/el), frequency-sweep plots, live parameter sliders, solver/ground selection. FastAPI backend, WebSocket sweeps. matplotlib for CLI plots. |
| **I/O** | Designs as Python builder classes; network spec (TL, DiffTL, Load, TwoPort, ports-at-edges). **`.nec` card export** via `nec_export` (CLI `export` subcommand + web gear-menu download; validated against `nec2c`); TL/DiffTL reducer designs excepted. NEC card *import* not yet (PyNEC consumes cards only for cross-validation). matplotlib PNG export. |
| **Performance** | OpenMP/BLAS threading, libmvec AVX2 sincos, K-independent geometry cache for sweeps, on-demand block eval for H-matrix. H-matrix tested on 100-director Yagi (2142 segments), O(N log N) vs dense O(N²). |
| **API / CLI** | Python API (`AntennaBuilder`, engines, `sweep*`, `optimize`, `pattern`, `compare_patterns`); CLI subcommands `draw / sweep / optimize / pattern / compare_patterns`; uniform `SimulationEngine` interface. |
| **Validation / limits** | Cross-validated against PyNEC (≤0.1 dBi directivity on dipole; ~1–3% R on loops and multi-feed arrays). **Genuine open limits:** pysim wires are PEC (no copper loss); pysim finite-ground impedance is approximate (PEC image + Fresnel); `DiffTL` is pysim-only (PyNEC raises `NotImplementedError`); strict `tl_card` numerical agreement with PyNEC is unmet on low-coupling geometries (a segment-vs-basis port-convention difference, not a bug). |
| **License / platform** | Open-source Python; cross-platform (web UI = browser-based). |

---

## 3. Tier 1 — High-end commercial full-wave suites

*All feature lists are vendor marketing claims. Pricing is quote-only everywhere; estimates are third-party.*

### ANSYS HFSS (Ansys Electronics Desktop)
- **Solvers:** 3D FEM w/ adaptive meshing (flagship); Integral Equation **MoM**; **SBR+** asymptotic (shooting-bouncing-rays) for electrically-large platforms; FEM Transient; hybrid FEM↔IE↔SBR+ and FE-BI; all built on Domain Decomposition Method (DDM) for HPC.
- **Antennas:** finite-array DDM (mutual coupling, scan impedance, array edge effects), phased/5G mmWave arrays, encrypted 3D Components, installed/placement on aircraft/vehicles, RCS.
- **Outputs:** S-params, impedance, gain/directivity, near/far field, scan impedance, RCS, co-site/EMI.
- **Scale/opt:** Optimetrics + optiSLang (AI/ML design exploration), GPU (CUDA), Mesh Fusion parallel meshing, multiphysics (thermal/structural/Maxwell), Twin Builder circuit co-sim.
- **Price:** quote-only; ~$10K–$50K+/yr (third-party).
- Source: [ansys.com/products/electronics/ansys-hfss](https://www.ansys.com/products/electronics/ansys-hfss)

### CST Studio Suite (Dassault SIMULIA)
- **Solvers:** Time-domain **FIT** + **TLM**; Frequency-domain **FEM** (MOR); Integral Equation **MoM + MLFMM** with **Characteristic Mode Analysis**; Asymptotic **SBR**; Multilayer planar MoM.
- **Antennas:** installed performance, small-antenna-on-large-structure (hybrid), planar/MMIC, scattering.
- **Outputs:** multi-port S-params, near/far field, characteristic modes, EMC, SI/PI, RCS.
- **Scale/opt:** built-in optimization, MPI cluster + GPU; multiphysics (thermal/mechanical/Lorentz); PCB SI/PI/EMC, cable-harness solver; Cadence/Zuken/Altium integration.
- **Price:** quote-only.
- Source: [3ds.com/.../cst-studio-suite](https://www.3ds.com/products/simulia/cst-studio-suite/electromagnetic-simulation-solvers)

### Altair / Siemens FEKO *(advertised "market leader for antenna placement")*
- **Solvers:** the broadest mix — **MoM**, **MLFMM**, **FEM**, **FDTD**, asymptotic **PO / LE-PO / RL-GO / UTD**, **Characteristic Mode Analysis**, true hybridization in one run.
- **Antennas:** arrays (periodic BC), reflectors/horns, installed performance on electrically-large platforms (flagship), integrated windscreen antennas, radar, EMC.
- **Outputs:** patterns/gain, near/far field, RCS, SAR, EMC/EMI, shielding, cable coupling, wireless coverage (WinProp).
- **Scale/opt:** genetic-algorithm + other optimizers, MPI + OpenMP + multi-GPU CUDA, out-of-core; SPICE circuit co-sim.
- **Price:** quote-only. *(Altair acquired by Siemens; now also under Simcenter branding.)*
- Source: [help.altair.com/feko/...overview](https://help.altair.com/feko/topics/feko/user_guide/introduction/overview_feko_c.htm)

### Remcom XFdtd
- **Solvers:** full-wave **FDTD**; XACT conformal sub-cell meshing; PrOGrid optimized gridding.
- **Antennas:** phased-array / **5G MIMO** w/ beam-steering optimization, mobile-device + hand-grip, biomedical/**SAR** w/ posable human models, placement/coupling.
- **Outputs:** S-params, VSWR, impedance, active impedance, far-field gain/realized gain/**axial ratio**, near-field E/H/currents, SAR + thermal, efficiency.
- **Scale/opt:** circuit/array optimizers, **XStream multi-GPU CUDA** + MPI; CAD import (STEP/IGES/STL/CATIA), Schematic Editor circuit solver, Optenni Lab matching.
- **Price:** quote-only.
- Source: [remcom.com/xfdtd-3d-em-simulation-software](https://www.remcom.com/xfdtd-3d-em-simulation-software)

### COMSOL Multiphysics — RF Module
- **Solvers:** **FEM** (order 1/2/3 vector elements) + **BEM** + hybrid FEM-BEM; frequency/transient/eigenfrequency; Model Order Reduction; PMLs; periodic/Floquet for arrays.
- **Antennas:** arrays + array factor, microstrip patch, horns, fractal monopole, automotive radar, MRI/biomedical.
- **Outputs:** S-params (Touchstone), impedance/matching, far-field patterns, directivity/gain, RCS, Smith plots, fields.
- **Scale/opt:** parametric sweeps, Optimization Module, cluster computing; **headline = multiphysics** (RF heating, thermal, structural/thermal stress); CAD Import, LiveLink, Application Builder.
- **Price:** quote-only (module add-on to base).
- Source: [comsol.com/rf-module](https://www.comsol.com/rf-module)

### Keysight EMPro / ADS (Momentum + RFPro) / Genesys
- **Solvers:** EMPro 3D **FEM** + 3D **FDTD**; ADS **Momentum** 3D-planar **MoM** (full-wave + quasi-static); RFPro unifies FEM + planar MoM; Genesys EM = Momentum.
- **Antennas:** planar antennas / far-field patterns, packaging/shielding/waveguide 3D effects, MMIC/RFIC/SI.
- **Outputs:** S-params, surface currents, planar patterns, **SAR** (EMPro option).
- **Scale/opt:** adaptive frequency sweep, GPU (EMPro); **headline = circuit-EM co-simulation** with no offline cleanup; Python scripting, CAD import.
- **Price:** quote-only (element/bundle within PathWave/ADS).
- Source: [keysight.com/.../empro-key-features](https://www.keysight.com/us/en/lib/resources/technical-specifications/empro-key-features-1741565.html)

**Tier-1 solver matrix**

| | HFSS | CST | FEKO | XFdtd | COMSOL | Keysight |
|---|---|---|---|---|---|---|
| FEM | ✓ | ✓ | ✓ | – | ✓ | ✓ |
| MoM / MLFMM | ✓ (IE) | ✓ | ✓ (flagship) | – | (BEM) | ✓ (Momentum) |
| FDTD / FIT / TLM | (transient) | ✓ | ✓ | ✓ (flagship) | (transient) | ✓ |
| Asymptotic (PO/GO/UTD/SBR) | ✓ | ✓ | ✓ | – | – | – |
| Characteristic Mode Analysis | – | ✓ | ✓ | – | – | – |
| GPU acceleration | ✓ | ✓ | ✓ | ✓ | (platform) | ✓ |
| Multiphysics | ✓ | ✓ | (limited) | (thermal) | ✓ (headline) | – |
| Circuit co-sim | ✓ | ✓ | ✓ | ✓ | (LiveLink) | ✓ (headline) |
| SAR / RCS | ✓ | ✓ | ✓ | ✓ | ✓ | (SAR) |

---

## 4. Tier 2 — Amateur-radio / affordable MoM tools *(direct competitors)*

### The underlying engines (NEC-2 / NEC-4 / MININEC)
- **NEC-2:** MoM solving EFIE (thin wires) + MFIE (surface patches). **Public domain, no license.** Ground: perfect + lossy/real (Sommerfeld-Norton) + radial-screen approximation. Limits: thin-wire kernel degrades for thick/closely-spaced wires; no insulated/buried wires.
- **NEC-4:** adds accuracy for electrically-small/thick wires, **insulated + buried wires**, current sources, large-model memory. **Proprietary** (LLNL/UC), paid license + **US export control**.
- **MININEC:** separate MoM lineage (used by MMANA-GAL); different ground/feedpoint behavior than NEC.
- Source: [en.wikipedia.org/wiki/Numerical_Electromagnetics_Code](https://en.wikipedia.org/wiki/Numerical_Electromagnetics_Code), [softwarelicensing.llnl.gov/product/nec-v42](https://softwarelicensing.llnl.gov/product/nec-v42)

### EZNEC / EZNEC Pro+ (W7EL) — **free since 2022, no support**
- Engine: internal NEC-2D (Pro/2+) or NEC-4.2 (Pro/4+, needs LLNL license); can call NEC-5.
- Ground: perfect, Real (Sommerfeld), High-Accuracy, MININEC-type.
- Outputs: Z, SWR (+plot), gain/directivity, 2D + 3D far-field, current distribution, charge, near field, F/B, takeoff angle, average-gain test.
- Loads/TL: traps + series/parallel R-L-C, transmission lines. `.NEC` import/export.
- Viz: wireframe geometry, 2D/3D patterns, SWR plots. No native Smith chart (AutoEZ add-on adds optimization + plots).
- Segments: historically 500 (std) / 1,500 (+) / up to 45,000 (Pro). **Windows only.**
- Source: [eznec.com](https://www.eznec.com/)

### 4nec2 (Arie Voors) — **free**
- Engine: NEC-2 (+ NEC-4 command support). ~11,000 segments (memory-limited in practice).
- Geometry: full NEC cards (GX/GM/GR/GA/GH transforms, surface patches), graphical structure editor + 3D preview, card text editor.
- Outputs: Z, SWR, gain, F/B, F/R, efficiency, far + **near field**, current distribution.
- **Optimizer:** built-in **genetic algorithm** (gain/resonance/SWR/efficiency/F/B/F/R/target-Z via SY variables). Frequency + variable sweeper.
- Loads/TL: LD + TL cards. Viz: state-of-the-art 3D far/near field, 2D patterns, **Smith chart**.
- I/O: `.nec`/`.txt` + **imports EZNEC `.ez`**. **Windows** (Linux/macOS via Wine).
- Source: [qsl.net/4nec2](https://www.qsl.net/4nec2/)

### MMANA-GAL (Basic free; Pro €139 / €699)
- Engine: modified **MININEC-3** MoM (C++). *Not NEC* — different ground/feedpoint behavior.
- Limits: Basic 512 wires / 8,192 segments; Pro 3,000 wires / 15,000 segments.
- Outputs: Z, SWR-vs-f, gain, F/B, current distribution (CSV export), efficiency, 2D + 3D patterns.
- Optimizer: element length/spacing optimization (min SWR / max gain). TL simulation, LC + Q-match, loads.
- I/O: native `.maa`. **Windows.** No Smith chart emphasis.
- Source: [gal-ana.de/basicmm/en](http://gal-ana.de/basicmm/en/)

### AN-SOF (Golden Engineering) — **$999 (Gold) / $1,599 (Platinum); free 50-seg trial**
- Engine: proprietary **Conformal MoM with Exact Kernel** — *only* tool advertising conformal MoM; models **curved wires natively** (helices/spirals/loops) without staircasing. Triangular basis + pulse testing.
- Wire/surface: tapered + insulated wires, **microstrip/patch on dielectric/PCB**. Real ground.
- Outputs: gain, efficiency, Z, **VSWR**, power, **RCS**, currents, near field 2D/3D color, far-field, **reflection on Smith charts**.
- Optimization: engine in Platinum (configurable cost functions) + script optimizer. TL modeling.
- **Windows.** Source: [antennasimulator.com/.../pricing](https://antennasimulator.com/index.php/pricing/)

### xnec2c (KJ7LNW) — **free, GPL**
- Engine: nec2c (NEC-2 in C), multi-threaded (`-j n`, near-linear); v4.3+ accelerated BLAS (ATLAS/OpenBLAS/MKL).
- Outputs: far + near field, **3D pattern**, gain/Z/VSWR vs f, current/charge (color), F/B, interactive frequency pick.
- Optimizer: built-in (SY symbolic vars, weighted fitness) + external GA (xnec2c-gao). `.nec` I/O.
- **Linux / UNIX** (Flatpak). No Smith chart emphasis. Source: [github.com/KJ7LNW/xnec2c](https://github.com/KJ7LNW/xnec2c)

### cocoaNEC (W7AY) — **free, macOS**
- NEC-2 (+ optional NEC-4); spreadsheet + programming-language input modes; `.nec` card decks; multi-core; standard NEC outputs. Source: [w7ay.net/.../cocoaNEC](http://www.w7ay.net/site/Applications/cocoaNEC/)

**Tier-2 comparison**

| | EZNEC Pro+ | 4nec2 | MMANA-GAL | AN-SOF | xnec2c | cocoaNEC | **antenna_designer** |
|---|---|---|---|---|---|---|---|
| Engine | NEC-2/4 | NEC-2 | MININEC-3 | Conformal MoM | nec2c | NEC-2/4 | **NEC-2 + own multi-basis MoM** |
| Basis functions | 1 (NEC) | 1 (NEC) | 1 (MININEC) | 1 (tri/pulse) | 1 (NEC) | 1 (NEC) | **3 (tri / sin / B-spline)** |
| Large-N acceleration | – | – | – | – | BLAS threads | – | **H-matrix / ACA + GMRES** |
| Platform | Windows | Windows | Windows | Windows | Linux | macOS | **Web (cross-platform)** |
| Price | Free (no support) | Free | Free / €139 | $999+ | Free | Free | **Free / open-source** |
| 3D pattern | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (WebGL geometry; pattern polar) |
| Smith chart | via AutoEZ | ✓ | – | ✓ | – | – | ✓ |
| Optimizer | via AutoEZ | ✓ (GA) | ✓ | ✓ (Platinum) | ✓ | – | ✓ (scipy) |
| `.nec` import/export | ✓ / ✓ | ✓ / ✓ | limited | own | ✓ / ✓ | ✓ / ✓ | **export ✓ / import ✗** |
| Real/Sommerfeld ground (impedance) | ✓ | ✓ | MININEC | ✓ | ✓ | ✓ | **PyNEC ✓; pysim approx** |

---

## 5. Tier 3 — Open-source / Python ecosystem *(closest peer group)*

- **PyNEC / necpp / nec2c** — the dominant Python **wire MoM** path (`pip install pynec`). NEC-2 physics, single sinusoidal basis, **dense matrix (no acceleration)**, library/CLI only (no GUI). Optimization via external scipy/GA (`antenna-optimizer` PyPI). GPL-2. **This is `antenna_designer`'s most direct peer** — and the one its multi-basis + H-matrix + web UI most clearly surpass. Source: [github.com/tmolteno/python-necpp](https://github.com/tmolteno/python-necpp)
- **openEMS** — open-source 3D **FDTD** (EC-FDTD), Python/Octave/MATLAB API, NF2FF far-field, S-params/impedance, patterns. MT/SIMD/MPI (no GPU). GPL-3. No built-in optimizer/GUI. Source: [openems.de](https://www.openems.de/)
- **gprMax** — Python/Cython **FDTD**, GPR-first but antenna-capable (transmission-line feed model, GPR antenna library). OpenMP + **CUDA GPU** + MPI. Source: [gprmax.com](https://www.gprmax.com/)
- **Meep (MIT)** — Python/Scheme/C++ **FDTD**, photonics-first but has near-to-far-field + antenna pattern examples. MPI (no first-class GPU). GPL. Source: [github.com/NanoComp/meep](https://github.com/NanoComp/meep)
- **Sonnet Lite** — free tier of commercial planar **MoM**; capped at 2 metal levels / 3 dielectrics / 4 ports / ~1,400 cells. S-params + current animation. GUI, Windows. Source: [sonnetsoftware.com/products/lite](https://www.sonnetsoftware.com/products/lite/)
- **scikit-rf** — **NOT a field solver**: Python network-parameter (S/Z/Y) analysis, VNA calibration, Touchstone, Smith charts. BSD. Complementary post-processing peer. Source: [scikit-rf.org](https://scikit-rf.org/)
- **Antenna Magus (Altair/SIMULIA)** — **NOT a solver**: 350+ design synthesis database, exports parametric models to FEKO/CST. Source: [3ds.com/.../antenna-magus](https://www.3ds.com/products/simulia/antenna-magus)

| Tool | Method | Type | Interface | Acceleration | License |
|---|---|---|---|---|---|
| **PyNEC/necpp/nec2c** | MoM (wire, 1 basis) | Field solver | Python/C lib | none (dense) | GPL-2 |
| openEMS | FDTD (3D vol.) | Field solver | Python/Octave + viewer | MT/SIMD/MPI | GPL-3 |
| gprMax | FDTD (3D vol.) | Field solver | Python/Cython | OpenMP/CUDA/MPI | GPL |
| Meep | FDTD (photonics) | Field solver | Python/Scheme/C++ | MPI | GPL |
| Sonnet Lite | MoM (planar) | Field solver | GUI (capped) | – | Free/proprietary |
| scikit-rf | network params | Analysis (not solver) | Python | – | BSD |
| Antenna Magus | synthesis | Design DB | GUI → FEKO/CST | – | Proprietary |
| **antenna_designer** | **MoM (wire, 3 bases)** | **Field solver** | **Web UI + Python/CLI** | **H-matrix/ACA + GMRES** | **Open-source** |

---

## 6. Positioning: differentiators, parity, and gaps

### Genuine differentiators (vs. free/affordable peers)
1. **Multi-basis MoM** — triangular / sinusoidal / B-spline in one engine. No free peer offers this; only commercial AN-SOF makes basis quality (conformal MoM) a selling point at $999+.
2. **H-matrix / ACA acceleration + GMRES** — unique among open MoM tools (PyNEC, nec2c, xnec2c are all dense O(N²)). Demonstrated O(N log N) on a 2142-segment Yagi.
3. **Web UI (FastAPI + React)** — cross-platform by default. Every free competitor is platform-locked desktop (Windows: EZNEC/4nec2/MMANA/AN-SOF, Linux: xnec2c, macOS: cocoaNEC) or GUI-less library (PyNEC, openEMS, Meep).
4. **Two cross-validating engines in one tool** (PyNEC reference + pysim) — a built-in accuracy check most tools lack.
5. **Open-source** while matching paid-tier modeling features (AN-SOF charges $999+; MMANA-GAL Pro €139).

### Parity (table-stakes the tool already meets)
Impedance / SWR / Γ, gain / directivity, far-field 2D patterns, current distribution, frequency sweeps, parameter optimization, Smith chart, 3D geometry view, transmission lines + loads, multi-port networks. These are expected across the whole amateur tier; `antenna_designer` has them. On far-field presentation: the solver produces full-sphere `(n_theta, n_phi)` data on every basis, and the UI presents it as calibrated az/el polar cuts — the numbers-first view you can actually read gain and beamwidth off — as its chosen presentation.

### Gaps worth noting
- **`.nec` import (round-trip) not yet** — export now exists (`nec_export`: CLI + web download, validated against `nec2c`, and round-tripped through xnec2c), closing the headline interoperability gap. What remains is *reading* external `.nec` decks back in; that's the lower-leverage half (most amateur-tier value is getting designs *out* to existing tools). PyNEC has no deck reader, so import would mean a small `.nec` parser driving the card API.
- **Finite-ground impedance on the triangular/sinusoidal bases folds to the PEC image** — the B-spline family solves it with momwire's reflection-coefficient model (validated within ~2 Ω of NEC over 0.1–0.5λ heights) and PyNEC offers full Sommerfeld–Norton, so real-ground work cross-checks across two independent engines; below ~0.1λ heights the Sommerfeld path is the reference.
- **No copper/conductor loss in pysim** (PEC wires); efficiency on lossy elements requires PyNEC + `ld_card`.
- **No FEM/FDTD/asymptotic, GPU/MPI, multiphysics, SAR/RCS/EMC, CAD import, auto-adaptive meshing** — Tier-1 features, out of scope for a focused wire-MoM tool, but worth stating explicitly so the positioning is honest.
- **Remaining solver caveats** (per `NEXT_STEPS.md`): pysim wires are PEC (no conductor loss); strict `tl_card` PyNEC numerical agreement is unmet on near-decoupled geometries (segment-vs-basis port convention).

### Suggested positioning statement
> *An open-source, browser-based wire-antenna MoM simulator for amateur/HF design that uniquely combines multiple basis functions, H-matrix acceleration for large arrays, and a NEC-2 cross-validation engine — delivering paid-tier (AN-SOF/MMANA-Pro) modeling quality for free, with no platform lock-in.*

The clearest roadmap item implied by the gap analysis is now **`.nec` import** for full round-trip interoperability. The former top item — `.nec` export — has shipped (`nec_export`, validated against `nec2c`); import is the remaining half, and PyNEC has no deck reader, so it would mean a small `.nec` parser driving the card API.

---

## 7. Sources

**Tier 1:** [HFSS](https://www.ansys.com/products/electronics/ansys-hfss) · [CST](https://www.3ds.com/products/simulia/cst-studio-suite/electromagnetic-simulation-solvers) · [FEKO](https://help.altair.com/feko/topics/feko/user_guide/introduction/overview_feko_c.htm) · [XFdtd](https://www.remcom.com/xfdtd-3d-em-simulation-software) · [COMSOL RF](https://www.comsol.com/rf-module) · [Keysight EMPro](https://www.keysight.com/us/en/lib/resources/technical-specifications/empro-key-features-1741565.html) · [Momentum](https://www.keysight.com/us/en/product/W3031E/pathwave-momentum.html)

**Tier 2:** [NEC (Wikipedia)](https://en.wikipedia.org/wiki/Numerical_Electromagnetics_Code) · [LLNL NEC v4.2](https://softwarelicensing.llnl.gov/product/nec-v42) · [EZNEC](https://www.eznec.com/) · [4nec2](https://www.qsl.net/4nec2/) · [MMANA-GAL Basic](http://gal-ana.de/basicmm/en/) · [MMANA-GAL Pro](http://gal-ana.de/promm/) · [AN-SOF pricing](https://antennasimulator.com/index.php/pricing/) · [xnec2c](https://github.com/KJ7LNW/xnec2c) · [cocoaNEC](http://www.w7ay.net/site/Applications/cocoaNEC/) · [Cebik: NEC modeling](https://antenna2.github.io/cebik/content/model/nec.html)

**Tier 3:** [PyNEC/necpp](https://github.com/tmolteno/python-necpp) · [pynec PyPI](https://pypi.org/project/pynec/1.7.3.6) · [openEMS](https://www.openems.de/) · [openEMS docs](https://docs.openems.de/intro.html) · [gprMax](https://www.gprmax.com/) · [Meep](https://github.com/NanoComp/meep) · [Sonnet Lite](https://www.sonnetsoftware.com/products/lite/) · [scikit-rf](https://scikit-rf.org/) · [Antenna Magus](https://www.3ds.com/products/simulia/antenna-magus) · [antenna-optimizer PyPI](https://pypi.org/project/antenna-optimizer/)

*Pricing context (third-party estimates):* [ITQlick HFSS pricing](https://www.itqlick.com/ansys-hfss/pricing) · [EpsilonForge commercial EM comparison](https://www.epsilonforge.com/post/commercial-electromagnetic-software/)

---

*Caveats: All third-party feature lists are vendor marketing claims, not independently benchmarked. Commercial pricing is quote-only; figures are third-party estimates. 4nec2's official ~11,000-segment figure conflicts with third-party "tens of thousands" claims. EZNEC per-tier segment limits are from the pre-free product line. `antenna_designer` capabilities are current as of the 2026-06-20 `main` (post-PR-103) and reflect admitted limitations in `NEXT_STEPS.md`.*
