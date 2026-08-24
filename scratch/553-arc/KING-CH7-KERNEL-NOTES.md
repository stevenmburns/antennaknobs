# King & Smith, *Antennas in Matter* (MIT Press 1981) — Ch. 7 kernel facts for #553 U1

Source: ~/antennas/references/king-smith-antennas-in-matter.pdf (scan, 892 pp).
Print page = PDF page − 20 (verified: printed 428 = PDF 448).
All equations below verified against page images 2026-08-22 (session lead).
PRIVATE note (copyrighted book) — cite publicly as "King & Smith (1981) Ch. 7"
by equation number only, never reproduce scans.

## Verified facts (U1 cross-check kit)

1. **Convention (eq. 3.1, p. 434 / PDF 454)**: k = β − jα is "the complex
   wave number characteristic of the medium in which the antenna is
   immersed"; kernel carries e^{−jkr} (3.5). With e^{+jωt} implied by
   (2.1a,b) ∇×E = −jωB, this is EXACTLY momwire's convention: Im k ≤ 0,
   |e^{−jkR}| decays. No translation needed between King's k and our k_m.
   Assumptions (3.1): a ≪ h, |ka| ≪ 1 — thin-wire validity is on |k|a
   (complex modulus), the same criterion U4's |n| meshing rule enforces.

2. **Exact vs reduced kernel (3.5)/(3.7), p. 435 / PDF 455**: exact kernel
   K(z,z′) = ∫_{−π}^{π} (e^{−jkr}/r) dθ′/2π over the tube circumference,
   r = √((z−z′)² + (2a sin(θ′/2))²); reduced kernel K ≐ e^{−jkR}/R with
   R = √((z−z′)² + a²). **Functional form is UNCHANGED at complex k** —
   the in-medium thin-wire kernel is the analytic continuation, no new
   terms appear. (The derivation (2.9)–(2.15) → (3.3) goes through the
   Helmholtz Green's function G(r) = e^{−jkr}/4πr with complex k from the
   start; Sommerfeld radiation condition imposed at infinity, p. 433.)

3. **Singularity structure at coincidence (§7.4, eqs. 4.1–4.5, p. 439 /
   PDF 459)**: the REAL part of the kernel peaks like e^{−αa}cos(βa)/(βa)·β
   ≈ 1/a — the 1/R static singularity, k-independent; the IMAGINARY part
   stays bounded at coincidence (K_I(z,z)/β ≐ −e^{−αa} sin(βa)/(βa) ≐ −1).
   ⇒ Static-moment extraction (1/R and polynomial-in-R moments integrated
   analytically) remains valid verbatim at complex k; what changes is only
   the SERIES COEFFICIENTS of the smooth remainder:
   e^{−jkR}/R = 1/R − jk − k²R/2 + jk³R²/6 + … with k complex.
   Any expansion coefficient set (−jk, −k²/2, …) in momwire that was typed
   real must become complex; no structural change.

4. **Real/imag split TRAP (3.20b,c), p. 438 / PDF 458**: King splits the
   difference kernel into e^{−αR}cos(βR)/R and e^{−αR}sin(βR)/R. This is
   the shape a lossy-medium kernel takes when someone insists on a
   real/imag split — i.e., a momwire code path that carries cos(kR),
   sin(kR) with REAL k does NOT generalize by substituting |k| or by
   keeping the trig split; it must be rewritten as the single complex
   exponential e^{−jkR} (or equivalently damped-trig with BOTH α and β,
   which is strictly worse numerically for our purposes). Flag every
   cos/sin(kR) occurrence in the fill path as a U1 review point.

5. **§7.5–7.6 (pp. 440–444)**: King's Ψ_dR / three-term-current machinery
   (5.1)–(5.13) — his ANALYTIC solution method, k_p = k + β/2,
   k_m = k − β/2, ε_p = α + jβ/2 etc. NOT applicable to MoM numerics;
   recorded only so nobody mistakes those k_p/k_m for our medium
   wavenumbers (name clash only — King's k_m is a shifted wavenumber, not
   a lower-medium k).

## For U2/U3 later

Ch. 11 "Antennas Near a Planar Interface" (printed 606 / PDF 626):
§11.6 subsurface transmission, §11.8 radiation into the air above a buried
horizontal dipole (printed 648 / PDF 668) — independent cross-check
material for the transmitted family. Not yet read; extract when U3's
review needs it.
