# AK#1523: which insulated-wire treatment matches a reference, and by how much

Registered 2026-09-15, **before any computation or solve**. Branch
`scratch/1523-insulated-wire`, off main cc87956; momwire at the pointer,
1ca8725 (0.55.0); NEC-5 `nec5cl-x13-static`, sha256 7ebf343d. Measure only, no
PR, and no engine changes.

A missed prediction is reported as a miss and is not re-registered.

## Step 1: the two paths, as read (momwire 1ca8725, antennaknobs cc87956)

**The same L′.** Both engines use momwire's `insulation_inductance(a, b, εr)`,
evaluated at the conductor radius a:

    L′ = μ₀/(2π) · (1 − 1/εr) · ln(b/a)      [H/m]

The number is identical on both paths.

### momwire (`_wire_loading.py`)

- **The loading.** Z′(ω) = jωL′ (plus the skin effect, when a conductivity is
  given) enters as a distributed series impedance per wire, through each
  solver's own testing rule:
  - **bs2 (`BSplineSolver._loading_gram`):** Galerkin. It adds
    Σ_w Z′_w ∫Φ_m Φ_n dl over same-wire basis overlaps.
  - **razor-2p (`RazorSolver._loading_stencil`):** the testing-path integral
    L[m, n] = ∫_{P_m} Z_s Λ_n dl. That is 3h/8 or h/8 per wing pair, and a row
    sums to Z′h.
  - **sinusoidal:** NEC's impedance condition at the match points.
- **The kernel radius** (`configure_loading`, since momwire#865). On every
  jacketed wire, and unconditionally, the kernel radius becomes the
  Popović–Nešić equivalent radius
  a′ = a · (b/a)^((εr − 1)/εr), with a < a′ < b. That is Popović & Nešić, IEE
  Proc. 131 pt. H no. 3, 153–158 (1984).
  - The docstring calls a′ and L′ a pair: a′ carries the jacket's effect on
    the charge (the capacitance), and L′ restores the inductance that enlarging
    the radius removes.
  - The identity ln(a′/a) = (1 − 1/εr) ln(b/a) makes the two forms of L′ the
    same number.
  - The skin effect and the conductor refusals keep a.

### The NEC-5 engine (`engines/nec5.py`, `_build_material_lines`)

- **GW cards carry the bare conductor radius a,** plus `LD 2 <tag> 0 0 0. L′ 0.`
  per tagged wire, or one global `LD 2 0 0 0 0. L′ 0.`.
- **At the documented level,** LD type 2 is a distributed series R, L, C given
  per unit length. Here R = 0 and L = L′, with no capacitor, applied along
  every segment of the tagged wire.
- **There is no equivalent radius,** because NEC-5 has no insulated-wire card.

**So the two paths differ in whether the kernel sees the jacket, not in L′.**
- **momwire:** the pair, a′ in the kernel plus L′.
- **NEC-5:** L′ only, on the bare radius.

## Step 2: the reference

### No dipole-level insulated-wire reference is openly in reach

- **Paywalled or inaccessible:**
  - Lamensdorf, "An experimental investigation of dielectric-coated antennas",
    IEEE TAP 15(6) 767–771 (1967): measured coated monopoles;
  - Richmond & Newman, "Dielectric coated wire antennas", Radio Science 11,
    13–20 (1976);
  - Popović & Nešić (1984);
  - Moore & West, IEE Proc. Microwaves, Antennas and Propagation 142(1), 14–18
    (1995);
  - "On the problem of dielectric-coated thin-wire antennas" (IEEE TAP), whose
    abstract says the series-impedance model of Richmond & Newman is "limited by
    assumptions concerning the dielectric insulation model".
- **King's full insulated-antenna theory does not apply here.** It holds only
  when the ambient wavenumber is large compared with the insulation's (antennas
  in water or tissue), and a jacketed wire in air is the opposite case. Only its
  quasi-static L′ is used by either engine.
- **The amateur literature is not quantitative.** "Insulation lowers resonance
  about 3 %" is a folk figure.

### The fallback: the exact TM₀ guided mode of a coated wire

This is an analytic model that can be evaluated, and it is independent of both
engines. The problem: a perfectly conducting wire of radius a, a lossless
dielectric coating to radius b with permittivity εr, in free space, with fields
∝ e^{−jβz}. This is the classical Goubau-line problem (G. Goubau, "Surface
waves and their application to transmission lines", J. Appl. Phys. 21,
1119–1128, 1950).

- **The fields:**
  - In the coating, E_z = F(pρ) = J₀(pρ)Y₀(pa) − Y₀(pρ)J₀(pa), which vanishes
    at ρ = a, with p² = εr k₀² − β².
  - Outside, E_z = C·K₀(qρ), with q² = β² − k₀².
- **The dispersion relation.** Continuity of E_z and H_φ at ρ = b gives
  εr F′(pb) / (p F(pb)) = K₁(qb) / (q K₀(qb)),
  where F′(x) = Y₁(x)J₀(pa) − J₁(x)Y₀(pa).
- **The thin-coating check,** by hand. With Λ = ln(2/(q b e^γ)) and ℓ = ln(b/a),
  β²/k₀² → (Λ + ℓ)/(Λ + ℓ/εr).
  - That is exactly a line with C′ = 2πε₀/ln(R/a′) and L′ = μ₀/2π · ln(R/a),
    with ln(R/a) = Λ + ℓ: the pair.
  - L′ on the bare radius instead gives β²/k₀² = 1 + (1 − 1/εr) ℓ/(Λ + ℓ). That
    is the same to first order in x = (1 − 1/εr) ℓ/(Λ + ℓ), and different at
    second order.
- **The characteristic impedance.**
  - The mode's Z₀ = V/I, with V = ∫_a^∞ E_ρ dρ and I = 2πa·H_φ(a), fixes how
    C′ and L′ split: C′ = β/(ωZ₀) and L′ = βZ₀/ω.
  - The two treatments predict Z₀ about x apart, at first order, with the same
    Λ:
    - **the pair:** (η₀/2π) · √((Λ + ℓ)(Λ + ℓ/εr));
    - **L′ on the bare radius:** (η₀/2π) · √((Λ + 2ℓ − ℓ/εr)(Λ + ℓ)).
- **Validity:**
  - an infinite line, with no radiation and no ends;
  - thin wire and jacket, k₀b ≪ 1;
  - a lossless jacket and a perfect conductor.
- **What it adjudicates, and what it does not.** It tests the per-unit-length
  structure: which radius carries the capacitance, and which the inductance. It
  does not give a dipole's end effects, so the dipole ladder is compared with it
  through the treatments' structure, not as a resonant-length oracle.
- **The solver.** `tm0_mode.py` checks the εr → 1 limit and the thin-coating
  asymptote numerically before any number is used.

## Step 3: the dipole ladder

- **The deck:** a centre-fed straight dipole in free space, at 14.2 MHz, with a
  perfect conductor. Conductor loss is left out, because it is the same on both
  paths.
- **The jackets:**
  - a = 0.321 mm, with b/a ∈ {1.5, 2, 3} × εr ∈ {2.3, 3.5, 5};
  - the catalog's **22-awg-pvc** (a = 0.321 mm, b = 0.80 mm, εr = 3.5) and
    **18-awg-pvc** (a = 0.512 mm, b = 1.05 mm, εr = 3.5);
  - the bare wires at both radii.
- **The treatments,** a 2×2 with no engine changes:
  - **pair:**
    - momwire as it is;
    - NEC-5 with the GW radius a′ and `LD 2` L′ evaluated at a (the harness
      computes both).
  - **L-only:**
    - momwire with its a′ swap suppressed in the harness, so the kernel radius
      is a;
    - NEC-5 as it is.
- **The engines:** bs2, razor-2p and NEC-5, each at two meshes: nominal 41 and
  161 segments on the half-wave. Each engine applies its own parity, and the
  meshed counts are recorded.
- **The measures:**
  - **L_res:** the dipole length where X = 0, by secant from the bare resonant
    length.
  - **Z at a fixed length L₀,** bs2's bare resonant length at the finer mesh for
    that conductor.
  - **Relative differences** are \|Z₁ − Z₂\| / \|Z₂\|.

## Checks (a failure is a stop and a report, not a result)

| id | what | bar |
|---|---|---|
| **C1** | the mode solver is right | on every jacket, the closed-form V/I equals V/I by quadrature to 1e-6 relative. At εr = 1.001 on the 22-awg-pvc geometry the mode exists and \|β_pair/β_exact − 1\| ≤ 1e-6 |
| **P0** | the treatment reached the solve | every momwire row reads back the solver's kernel radius after the solve: a′ on the pair, a on L-only and bare, to 1e-12 relative. Every NEC-5 row reads back its deck: the GW radius a′ on the pair and a otherwise, and an `LD 2` value equal to L′ at a on both jacketed treatments, with none on bare |

## Predictions

**The reference (`tm0_mode.py`), on every jacket in the sweep.** Z₀ is V/I as
defined above. The power-based 2P/I² and V²/2P are recorded beside it but not
graded. The treatments' β and Z₀ use the exact mode's
Λ = K₀(qb)/(qb·K₁(qb)).

| id | what | bar | prediction |
|---|---|---|---|
| **R1** | the pair's β matches the exact mode's | \|β_pair/β_exact − 1\| ≤ 1e-4, and \|β_Lonly/β_exact − 1\| ≥ \|β_pair/β_exact − 1\| | hit |
| **R2** | the pair's Z₀ matches the exact mode's | \|Z₀,pair/Z₀,exact − 1\| ≤ 0.5 % everywhere. L-only's Z₀ is ≥ 1 % above the exact on 22-awg-pvc, and its excess ranks with (1 − 1/εr) ln(b/a) (Spearman ρ ≥ 0.9) | hit |

**The dipole ladder.** ΔZ_e,t = Z_e(jacket, t) − Z_e(bare), and
g_e = Z_e(pair) − Z_e(L-only). Both are taken at L₀, on one engine and one
mesh. The bare conductor is the jacket's own a.

| id | what | bar | prediction |
|---|---|---|---|
| **D1** | the engines agree on the jacket's effect and on the treatment gap | at the finer mesh, pairwise among bs2, razor-2p and NEC-5, on every jacket: \|ΔZ_e,t − ΔZ_e′,t\| ≤ 10 % of \|ΔZ_bs2,t\| for t ∈ {pair, L-only}, and \|g_e − g_e′\| ≤ 25 % of \|g_bs2\| | hit |
| **D2** | the treatment gap is real and grows with the jacket | on each engine at the finer mesh, \|g_e\| / \|Z_e(L-only)\| ≥ 1 % on 22-awg-pvc, and \|g_e\| ranks with (1 − 1/εr) ln(b/a) over the 11 jackets (Spearman ρ ≥ 0.9) | hit |
| **D3** | the treatments tune alike, with the pair a little shorter, and the jacket still shortens | on each engine at the finer mesh and on every jacket, L_res,pair < L_res,Lonly and 1 − L_res,pair/L_res,Lonly ≤ 25 % of 1 − L_res,Lonly/L_res,bare; and 1 − L_res,Lonly/L_res,bare ≥ 1 % on 22-awg-pvc | hit |
| **D4** | the meshes agree | L_res changes between the two meshes by ≤ 0.2 % on bs2, and by ≤ 1 % on razor-2p and NEC-5, on every row | hit |
| **D5** | the dipole shortens as the mode's velocity says | on bs2 at the finer mesh, s_dip / s_mode ∈ [0.9, 1.5] on every jacket, where s_dip = 1 − L_res,pair/L_res,bare and s_mode = 1 − k₀/β_exact | hit |

**The estimates behind the bars,** from the line model and not from any solve:

- **The treatment gap at L₀.** On 22-awg-pvc the coated dipole sits about 3 %
  electrically long at L₀, so X ≈ +40 Ω. Z₀ differs by ≈ 6 % between the
  treatments, so \|g\| ≈ 3–5 Ω on \|Z\| ≈ 90 Ω, which is D2's ≥ 1 %.
- **Why the pair resonates shorter (D3's sign).** Its phase constant is higher
  at second order, ≈ 0.2 % on 22-awg-pvc. On top of that, a kernel at a′ adds
  end shortening that L-only's kernel at a lacks, about half the bare wire's
  resonant-length shift for ln(a′/a). Together that is ≈ 10–15 % of the
  jacket's own shortening at the heaviest jacket, so the bar is 25 %.
- **Why D5's band sits above 1.** A thin dipole's effective log term,
  ≈ ln(2h/a) − 1, is smaller than the infinite line's Λ, so s_dip should run
  ≈ 1.1–1.25 × s_mode.

## The verdict rule

1. **If C1 or P0 fails:** stop and report. Nothing else is read.
2. **If R2 and D1 hit:** "the pair (momwire's path) matches the exact coated-line
   physics; `LD 2` on the bare radius has the right velocity to first order but
   overstates the line impedance by ≈ x". The dipole-level size is D2's gap and
   D3's resonant-length split, reported per jacket.
3. **If R2 misses on the pair but hits on L-only:** "L-only (the NEC-5 spelling)
   matches".
4. **If D1 misses:** "the engines disagree within a treatment", and the gap is
   not only the treatment.
5. **Otherwise:** "unexplained".

## Order

1. Commit this registration, with `tm0_mode.py`, the harness, the analysis and a
   mesh-only probe, and push.
2. The reference numbers, then the ladder solves, under `systemd-run` with
   MemoryMax=24G.
3. `README.md` with the tables; the report follows.

## Amendment 1 (2026-09-15, after the ladder ran, before any analysis)

Written from the convergence records alone: no bar has been computed and
`analyze_1523.py` has not run.

**What happened.**

- All 144 rows solved (status ok). All 96 momwire rows converged at the
  registered stop, \|X\| ≤ 1e-4 Ω.
- **25 of the 48 NEC-5 rows did not.** On each of them, NEC-5's X sits on a grid
  of about 3.3e-4 Ω, and the secant alternates between two adjacent levels (for
  example −1.21e-4 and +2.06e-4 Ω) at lengths that agree to 1e-6 m. The best
  \|X\| reached on those rows is 1.0e-4 to 2.3e-4 Ω.
- **So the registered stop cannot be reached on NEC-5.** The analysis would have
  dropped those rows as incomplete for a reason that has nothing to do with the
  physics.

**The change.** For NEC-5 rows only, the resonance counts as converged when both
hold:

- its best \|X\| is ≤ 5e-4 Ω, about 1.5 × the observed step;
- the search's last two lengths agree to 1e-5 m.

L_res stays the length with the smallest \|X\|, as recorded. That fixes L_res to
about 1e-5 m, against the finest bar at about 2 cm (D4's 0.2 %).

**Not changed:** momwire rows, Z at L₀, and every bar and prediction.
