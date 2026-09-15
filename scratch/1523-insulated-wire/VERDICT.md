# AK#1523: which insulated-wire treatment matches, and by how much

- **Registration:** `PLAN.md` (1598ce5), plus Amendment 1 (bad2f92), which was
  committed before the analysis ran.
- **Records:** `reference.json`, `rows.jsonl`, `analysis.json`.
- **Generated tables:** `README.md`.
- **Inputs:** momwire 1ca8725 and NEC-5 `nec5cl-x13-static` (sha256 7ebf343d).

## Step 1: what each path does

- **Both paths apply the same L′.** Both call momwire's
  `insulation_inductance(a, b, εr)` = μ₀/2π · (1 − 1/εr) · ln(b/a) at the
  conductor radius a.
- **momwire also sets the kernel radius** on every jacketed wire to
  a′ = a (b/a)^((εr−1)/εr). That is the Popović–Nešić equivalent radius, added
  unconditionally since momwire#865. Each solver adds the L′ by its own testing
  rule:
  - bs2: the Galerkin loading Gram;
  - razor-2p: the testing-path stencil.
- **AK's NEC-5 engine writes GW cards at the bare radius a,** plus
  `LD 2 tag 0 0 0. L′ 0.`. At the documented level that is a distributed series
  inductance per unit length on every segment. It has no equivalent radius.
- **So the paths differ only in whether the kernel sees the jacket:**
  - **the pair** (momwire): a′ in the kernel, plus L′;
  - **L-only** (the NEC-5 spelling): L′ on the bare radius.

## Step 2: the reference

**No dipole-level insulated-wire reference was openly reachable.** Lamensdorf
1967, Richmond & Newman 1976, Popović & Nešić 1984 and Moore & West 1995 are all
paywalled. King's full insulated-antenna theory needs an ambient medium denser
than the jacket, so it does not apply in air.

**The reference used instead** is the exact TM₀ guided mode of a PEC wire with a
lossless dielectric coating in free space. This is the Goubau-line
boundary-value problem (G. Goubau, J. Appl. Phys. 21, 1119–1128, 1950), solved
from Maxwell's equations with Bessel functions in `tm0_mode.py`.

- **Validity:**
  - an infinite line, with no radiation and no ends;
  - k₀b ≪ 1 (here ≤ 3e-4);
  - a lossless jacket and a perfect conductor.
- **What it settles:** the per-unit-length structure, i.e. the phase constant β
  and the characteristic impedance (see caveat 3 for which Z₀).
- **What it does not settle:** a dipole's end effects.

## Results

**Every check and every registered prediction hit.** C1, P0, R1, R2 and D1–D5
all passed, with no misses. The detail per row is in `README.md`.

### The reference (R1, R2)

- **β, which does not depend on any definition.**
  - The pair reproduces the exact mode's β to ≤ 3.3e-9 on every jacket.
  - L-only's β is low by 2e-4 (b/a 1.5, εr 2.3) to 3.5e-3 (b/a 3, εr 5): right
    to first order, wrong at second.
- **Z₀ = V/I.**
  - The pair reproduces the exact mode to ≤ 1e-7.
  - L-only is high by 2.05 % to 8.69 % (22-awg-pvc 6.27 %, 18-awg-pvc 5.07 %).

R1 and R2 confirm numerically a thin-coating identity I derived before any solve.
In the thin limit the exact dispersion relation and V/I reduce to the pair's C′
and L′. They are exact Maxwell evidence for the per-unit-length structure, not an
independent measurement.

### The dipole ladder

The setup: 14.2 MHz, free space, a centre-fed straight wire, meshed at 161
segments. L₀ is bs2's bare resonant length, 10.284 m on 22 awg and 10.268 m on
18 awg.

The columns below:
- **shortening** = 1 − L_Lonly/L_bare;
- **split** = 1 − L_pair/L_Lonly, where positive means the pair resonates
  shorter;
- **g** = Z_pair − Z_Lonly at L₀, on bs2.

The engines agree on every figure shown. razor-2p and NEC-5 give splits
0.003–0.012 percentage points smaller than bs2's, and \|g\| within 2.2 % of
bs2's.

| jacket | x | Z₀,Lonly excess % (V/I) | shortening % | split % (cm) | split / shortening | g Ω (bs2) | \|g\|/\|Z_Lonly\| % |
|---|---:|---:|---:|---:|---:|---|---:|
| ba1.5-er2.3 | 0.0203 | 2.05 | 1.250 | 0.106 (1.1) | 0.085 | 0.19+1.24j | 1.64 |
| ba1.5-er3.5 | 0.0259 | 2.62 | 1.572 | 0.145 (1.5) | 0.092 | 0.26+1.58j | 2.04 |
| ba1.5-er5 | 0.0292 | 2.96 | 1.756 | 0.170 (1.7) | 0.097 | 0.30+1.78j | 2.26 |
| ba2-er2.3 | 0.0355 | 3.62 | 2.110 | 0.224 (2.3) | 0.106 | 0.39+2.18j | 2.67 |
| ba2-er3.5 | 0.0454 | 4.65 | 2.646 | 0.317 (3.2) | 0.120 | 0.55+2.82j | 3.25 |
| ba2-er5 | 0.0512 | 5.26 | 2.950 | 0.377 (3.8) | 0.128 | 0.66+3.20j | 3.55 |
| ba3-er2.3 | 0.0577 | 5.94 | 3.287 | 0.450 (4.5) | 0.137 | 0.78+3.64j | 3.88 |
| ba3-er3.5 | 0.0738 | 7.67 | 4.103 | 0.657 (6.5) | 0.160 | 1.15+4.81j | 4.60 |
| ba3-er5 | 0.0831 | 8.69 | 4.563 | 0.792 (7.8) | 0.174 | 1.40+5.54j | 4.99 |
| 22-awg-pvc | 0.0607 | 6.27 | 3.444 | 0.487 (4.8) | 0.141 | 0.85+3.85j | 4.02 |
| 18-awg-pvc | 0.0494 | 5.07 | 2.883 | 0.376 (3.7) | 0.130 | 0.67+3.14j | 3.59 |

**The engines agree on the treatment effects.** At the finer mesh, the three
engines disagree by at most:

- **0.24 %** of \|ΔZ\| on each treatment's jacket effect;
- **2.2 %** of \|g\| on the treatment gap.

Their raw bare-wire Z differs by about 1 Ω (razor-2p and NEC-5 against bs2, the
feed model), and that difference cancels in both deltas.

**Mesh (D4):** from 41 to 161 segments, L_res moves ≤ 0.011 % on bs2 and
0.14–0.16 % on razor-2p and NEC-5.

**Resonance against the mode (D5):** s_dip / s_mode = 1.25–1.33 on bs2. The
dipole shortens about 25–33 % more than the infinite line's velocity alone
predicts.

### Against the estimates written beside the bars

All of these are inside their bars.

| quantity | estimate | observed |
|---|---|---|
| s_dip / s_mode | 1.1–1.25 | 1.25–1.33, above the estimate |
| X at L₀, 22-awg-pvc | ≈ +40 Ω | +62 to +66 Ω; I underestimated the reactance slope |
| \|g\| at L₀, 22-awg-pvc | 3–5 Ω | 3.95 Ω |
| split / shortening | 10–15 % | 8.5–17.4 % |

## Verdict

**The pair (momwire's path: kernel a′ plus L′) matches the exact coated-line
physics.**

- **β** agrees to ≤ 3.3e-9, with no dependence on any definition.
- **Z₀ = V/I** agrees to ≤ 1e-7. V/I is the one definition that reproduces the
  bare line as εr → 1 (caveat 3).
- **The range covered:** b/a 1.5–3, εr 2.3–5, thin jackets (k₀b ≤ 3e-4), a
  lossless jacket, a PEC conductor, free space.

**L-only (AK's NEC-5 spelling: bare radius plus `LD 2`)** has the right velocity
to first order, but its β is off at second order (0.02–0.35 %) and it overstates
the V/I line impedance by 2–9 % (≈ x). On a 20 m dipole that shows up as:

- **Resonant length:** 0.10–0.79 % longer than the pair's. That is 22-awg-pvc
  0.49 % (4.8 cm) and 18-awg-pvc 0.37 % (3.7 cm), or 8.5–17 % of the jacket's
  own shortening.
- **Z at fixed length:** 1.6–5.0 % of \|Z\| (22-awg-pvc 4.0 %), mostly
  reactance: +3.85 Ω of +66 Ω on 22-awg-pvc.

**The gap is the treatment, not the engine.** bs2, razor-2p and NEC-5 agree on it
to ≤ 2.2 % of its own size. So a momwire-versus-NEC-5 difference on jacketed wire
of this size is expected from the emulation. Giving NEC-5 the pair (GW radius a′
plus `LD 2` at L′) closes it.

## Caveats

1. **The adjudication is at the line level, not the antenna level.** No measured
   or full-wave insulated dipole was reachable, so the dipole-level sizes are what
   the pair and L-only predict, not a validation of either against a measurement.
2. **R1 and R2 check an analytic identity numerically.** Their strength is that
   the identity is exact Maxwell, not that it is independent of the derivation.
3. **Z₀ is not unique for this non-TEM surface-wave mode, and R2's
   discrimination rests on V/I.** This is unregistered, computed from
   `reference.json` after the analysis ran.
   - **The facts.** V/I is identically the geometric mean of 2P/I² and V²/2P.
     The two power-based values sit about 4.5–5.2 % below and above V/I on every
     jacket, tracking ≈ 1/(2Λ) (the guided wave's field extent). At εr = 1.001
     they are still 3.5 % off, where both treatments reduce to the bare
     quasi-TEM line and V/I agrees with it to 1e-11.
   - **What that means.** The power-based definitions miss the bare line itself,
     so they cannot be what a telegrapher-equivalent treatment's L′/C′
     corresponds to.
   - **But the closer treatment depends on the choice.** Under 2P/I², the pair is
     still the closer one on all 11 jackets (4.7–5.4 % against L-only's
     6.9–14.6 %). Under V²/2P, L-only is closer on all 11.
   - **So the definition-free part of the reference is β alone.** There the pair
     is exact and L-only is off at second order.
4. **Not covered:**
   - one frequency;
   - lossy jackets;
   - a wire near or on ground (for example the momwire#865 surface deck, where
     the stand-off also matters);
   - thick jackets outside k₀b ≪ 1.
5. **Amendment 1:** NEC-5's X is quantised at about 3.3e-4 Ω. Its resonances
   were accepted at best \|X\| ≤ 5e-4 Ω with the last two lengths within 1e-5 m
   (25 rows). This was recorded before the analysis ran, and no bar changed.
