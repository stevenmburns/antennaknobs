# SimNEC expression probes (AK#1714)

These probes measured how SimNEC evaluates `dcl` expressions in NEC card fields. `simnec_import._AnvilRules` and
`tests/test_ssn_dcl_knobs_1714.py` (`SIMNEC_MEASURED`) cite them.

Method: each probe circuit is a free-space 14 MHz dipole plus one isolated
probe wire per expression. Each probe wire's `y2` is the `dcl` value it names.
Steve opened each file in SimNEC 5.3 and solved once. `captured-*.nec` is
`~/.SimNEC/5/3/lastConstructedNEC.nec`, the deck SimNEC actually built
(engine: legacyNEC2C), snapshotted as it changed. SimNEC re-meshes the probe
wires (segmentsPerWavelength), so their segment counts don't matter here.

| probe | captured deck | settled (2026-09-24) |
|---|---|---|
| `probeA_trig.ssn` | `captured-141420.nec` | trig in RADIANS (Sin(30) = -0.9880316, Atan(1) = 0.7853982); Sqrt, Pi, mpf, fpm |
| `probeB_ops.ssn` | `captured-141434.nec` | -2^2 = +4; 2^3^2 = 64 (left); 10/4 = 2.5; Int(-2.7) = -2; `m` = milli; dcl->dcl and `$` temporaries |
| `probeC_case.ssn` | none: SimNEC refused the circuit | `sin(30)` and `SIN(30)`: "Missing Method Declaration (or inconsistent number of args) (maybe: 'Sin' ...Capitalization) <2 times>" -- names are case-sensitive |
| `probeD_more.ssn` | `captured-142722.nec` | % is fmod (-7%3 = -1, 7%-3 = 1, -7.5%2 = -1.5); Acos, Abs, 2*-3, 2^0.5 |
| `probeE_negexp.ssn` | `captured-142731.nec` | 2^-1 = 0.5 |
| `probeF_literal.ssn` | `captured-142738.nec` | a bare `500m` typed in a GW field reads as 0.5 |

## Where a card field ends (2026-09-24, second round)

Each `probeG*` file's GW 2 has `y2` set to one expression, with `dcl a = 12; dcl b = 2;`. If SimNEC reads the expression as one field, `y2` = 10.

| probe | field | SimNEC |
|---|---|---|
| G1 | `a-b` | one field, 10 (`captured-152608.nec`) |
| G2 | `12-b` | refused: "expected an end of line" |
| G3 | `a-2` | one field, 10 (`captured-152635.nec`) |
| G4 | `12-2` | refused |
| G5 | `8+b` | refused |
| G6 | `12-b`, tab-separated | refused |

Rule: a `+` or `-` directly after a number ends the field. After a name, the sign stays in the field, and parentheses keep a sum together (`scratch/dan-1714-examples/invvee3_parens.ssn` loads). `simnec_import._sim_field` implements this.
