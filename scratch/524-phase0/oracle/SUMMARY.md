# momwire#524 phase 0 — nec5cl oracle captures (2026-08-22)

Driver: `../run_captures.py`. Binary run output-only per the courtesy rule.
42 captures in `captures.json` (18 anchor-ladder rungs, 23 NE-matrix, 1
positive control), every one run A/B (stock vs `EZParam.txt` = `EZ5
0,0,0,-1.,-1.`). Raw `out_stock.txt` / `out_ezoff.txt` (full segment-current
tables included) preserved per capture directory.

## Anchors: reproduction status

| deck | anchor | reproduced (stock, x1) | note |
| --- | --- | --- | --- |
| four-radial | 89.985 - j71.401 | 89.985 - j71.401 EXACT | byte-exact deck from probe script |
| crossing | 74.761 - j57.730 | 74.761 - j57.730 EXACT | byte-exact deck from probe script |
| lone-radial | 92.13 - j70.14 | 92.130 - j70.141 EXACT after geometry search | see below |

Lone-radial (reconstructed deck) required a geometry search. The
sloping-from-origin radial `GW 2,10,0.,0.,0.,5.,0.,-0.15` gives
92.122 - j70.283 (X off by 0.14 ohm). The anchor is reproduced exactly by the
**flat detached radial at constant depth, starting directly below the
monopole base**: `GW 2,10,0.,0.,-0.15,5.,0.,-0.15,.001`. Variants tried
(slope-first-segment, 15/20-seg, flat-detached) are preserved in
`_lone-variants/`; flat-detached is the deck used for the ladder.

## A/B spread (the headline)

- **Every one of the 41 non-control captures is byte-identical between the
  stock and EZ5-off runs** apart from timing lines (FILL/RUN TIME seconds).
  |dZ| = 0 and max NE relative delta = 0 everywhere: max = median = 0.
- Mechanism verified before accepting that: a garbage `EZ5` parameter line
  aborts the run at the Sommerfeld stage (output truncates before the FINITE
  GROUND block — yet **exit code is still 0**), an unknown card name (`ZZ9`)
  is ignored, and a valid line is accepted silently. So the file IS parsed
  and the parameters ARE applied; the asymptotic branch simply never fires
  at these geometry scales.
- **Positive control (`control-bhd10-pair-130m`)**: bhd10 (d = 0.05, soil A,
  7 MHz) plus an identical parasitic twin at x-offset 130 m (beyond the
  ~3 lambda0 ~= 128.5 m table range). The toggle FIRES: max NE relative
  delta **1.86e-4** (M-line Ez at x = 5 m; T-line max 1.75e-4 at x = 20 m;
  T-vert <= 1.5e-5). Driven-wire currents unchanged at print precision;
  induced currents on the far parasitic (~1e-6 A) shift up to **123 %**
  relative. Verdict: the buried-buried asymptotic branch only engages for
  segment pairs beyond the Sommerfeld table range, and even then its effect
  on fields near the driven element is <= ~2e-4 — oracle uncertainty from
  this workaround is negligible for the phase-0 matrix, whose largest
  in-deck separation is ~30 m << 3 lambda0.

### CRITICAL harness trap discovered: SOMMPD.NEX caching

The engine writes its Sommerfeld interpolation tables to `SOMMPD.NEX` in the
run cwd and **silently reads them back on any subsequent run there**
("Sommerfeld integral tables read:" replaces "Will compute Sommerfeld-ground
tables"). The first A/B pass was therefore invalid — every B run reused
tables built under stock settings. Fix: scrub `*.NEX` before every run
(now in `run_once`); the entire campaign was re-run clean. Any future
harness driving this binary must do the same.

## Convergence ladders (stock Z, ohms)

| mult | lone-radial | four-radial | crossing |
| --- | --- | --- | --- |
| x1 | 92.13 - j70.14 | 89.99 - j71.40 | 74.76 - j57.73 |
| x2 | 102.99 - j75.25 | 100.50 - j76.83 | 69.11 - j50.83 |
| x3 | 99.45 - j71.06 | 97.03 - j72.68 | 70.86 - j51.68 |
| x4 | 103.21 - j73.47 | 100.68 - j75.18 | 69.02 - j50.02 |
| x5 | 101.00 - j71.30 | 98.52 - j73.01 | 70.04 - j50.72 |
| x8 | 103.30 - j72.55 | 100.74 - j74.33 | 68.88 - j49.73 |

- **The x1 anchors are strongly under-converged**: R moves ~ +11 ohm
  (radial decks) / -6 ohm (crossing) from x1 to x8. Expected — at x1 the
  buried radial has 0.5 m segments at 0.15 m depth.
- **Feed-segment quantization confound**: the probe decks feed seg 7 of 15
  (center at 0.4333 of the wire), which no even multiplier preserves. At x2
  the two bracketing choices differ by ~10 ohm (lone-radial fed 13 ->
  102.99, fed 14 -> 92.64; diagnostic runs in `_diag-fedseg/`). Even rungs
  use fed = round(0.4333*N) (13/26/52); **odd rungs x3, x5 preserve the
  feed center exactly** (segs 20, 33) and were added for a clean read: they
  form a smooth monotone sequence (92.13 -> 99.45 -> 101.00 -> ~103)
  confirming the trend is real convergence, not feed drift. Even and odd
  rungs sit ~2 ohm apart as two feed-position families.
- A/B spread identically zero on every rung.

## NE matrix

All 23 planned captures landed (bhd10/bhd1 x d in {0.02, 0.05, 0.10, 0.15}
and bvd1 x {0.05, 0.10, 0.15} at soil A / 7 MHz; bhd10+bhd1 at d in {0.05,
0.15} for soil B / 7, soil C / 7, soil A / 21 MHz). Every deck produced all
7 near-field blocks (T-line 15 pts, T-vert 5 x 1 pt, M-line 10 pts = 30 pts)
with zero engine errors, first try, using deck order CM/CE, GW, GE, FR, GN,
EX, PQ, NE..., XQ, EN — **multiple NE cards before a single XQ are all
honored** (7 cards -> 7 blocks).

Anomaly: **bvd1 reports small negative input resistance** at all three
depths (R = -0.0034 ... -0.0025 ohm, |X| ~= 3.47 ohm) — nonphysical but tiny
(|R|/|Z| ~= 1e-3); treat bvd1 drive-point R as below the oracle's noise
floor. bhd1 R is likewise milliohm-scale (0.004-0.085 ohm across the matrix)
— kernel comparisons should lean on the NE fields and printed currents, not
these tiny resistances.

## Deck-dialect / output-format notes

- `GE 1,-1` accepted without complaint for fully-buried wires (all dipoles)
  and for the interface-crossing wire.
- NE card `NE 0,NX,NY,NZ,X,Y,Z,DX,DY,DZ` works as in NEC-2; output is
  MAGNITUDE/PHASE(deg) per component (Ex, Ey, Ez), V/m.
- The "Wire Currents" table normalizes coordinates and segment lengths by
  2*pi/|k| **of the medium containing the segment** (header says "Lengths
  normalized by wavelength (or 2.*pi/CABS(k))"): buried segments at soil A /
  7 MHz print coords in units of 10.02 m, not free-space lambda. Parsers
  must rescale.
- Exit code is 0 even when the run aborts on a bad EZParam line — detect
  refusals by scanning the output, never by return code.
- `EZParam.txt` is read by relative name from the cwd (confirmed).

## Files

- `captures.json` — id -> {kind, deck, Z_stock, Z_ezoff, spread_dZ, parsed
  NE blocks both runs, spread_ne_maxrel, errors}; `_meta` holds the
  mechanism and positive-control findings.
- `<capture-id>/deck.nec`, `out_stock.txt`, `out_ezoff.txt`, `EZParam.txt`.
- Side studies: `_lone-variants/`, `_diag-fedseg/`, `_ne-iter/`,
  `_ezparam-mechanism/` (the four-variant mechanism probe).
