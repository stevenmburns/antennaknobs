# SimNEC's `nec2/Execute` printout grammar — the contract a momwire engine must meet

Status doc for issue #792 ("momwire as a SimNEC engine").  §1–§10 are unit
1's survey; §11 is what unit 2 resolved, §12 unit 3, §13 what was still open
after it, §14 what unit 4 resolved, §15 the `TL` layout issue #799 pinned, and
§16 the `MP` and `PT` layouts issue #800 pinned (§16.6 is the live open list).

This is the empirical contract later units are written against. Two independent
sources:

1. **The oracle.** `nec2c-ubuntu-x86` (banner `VERSION:5b4az.ae6ty.1.17`), the
   NEC-2 build SimNEC 2/3 ships under
   `~/.SimNEC/2/3/Examples/nec2c.ae6ty/bin/`. 36 deck/printout pairs captured
   by `scripts/nec_portal_capture.py` live in `tests/fixtures/nec_portal/`.
2. **The parser.** `nec2/Execute`, `nec2/NEC2Daemon`, `nec2/NEC5Daemon` and
   `nec2/NECSource` inside `~/SimNEC/SimNEC.jar`, decompiled with CFR
   (`java -jar cfr.jar <class> --extraclasspath SimNEC.jar`; `javap -c -p
   -constants` gives the same facts more slowly).

Every regex and column index quoted below is copied verbatim out of the
decompiled Java. Every sample line is copied verbatim out of a committed
fixture.

---

## 1. Process model

`nec2/NEC2Daemon` starts the engine once and keeps it:

```java
builder.command(new String[]{"sh", "-c", cmd});
builder.directory(new File(System.getProperty("user.home")));
this.process = builder.start();
```

The command is a plain path (`NEC2PortalDialog.safeNecCommand()`), run through
`sh -c`, with the user's home as cwd. Engine *identity* is decided by the
command's filename: `NEC2PortalDialog` lowercases the path and looks for the
substrings `nec2c`, `nec5`, `nec42`, refusing to run if none is found. **A
momwire replacement binary must therefore have `nec2c` in its filename** or
SimNEC will not accept it.

### Version probe

Before any deck, `Execute.testCommand()` runs `<cmd> -version`, requires
exit code 0, and matches the *first line of stdout, trimmed* against, in order:

```java
versionA     = Pattern.compile("nec2c\\.ae6ty\\.(.*)");
versionB     = Pattern.compile("5b4az\\.ae6ty\\.(.*)");   // <- what we ship
versionC     = Pattern.compile("necpp\\.nec2c\\.(.*)");
versionNECd  = Pattern.compile("(NEC\\d+\\D.*)");
```

If A/B/C matches, group(1) is parsed as a `Double` and compared against
`SimNEC.minimumNEC2CVersion`; too old ⇒ `"nec2c version too old:"`. So the
version tail must be a bare parseable number: `1.17` works, `1.17.2` would
throw and be reported as too old. The oracle's `-version` output is the same
string that opens every printout:

```
VERSION:5b4az.ae6ty.1.17
```

Note the banner line in the *printout* is prefixed `VERSION:` while the
`-version` probe emits the bare token — the regexes are `lookingAt()`, i.e.
anchored at the start, so the printout banner would *not* match. Only the
probe output is version-checked.

### Deck submission (the residency protocol)

`NEC2Daemon.submit(NECRun)`:

```java
deck = somnecPrefix + "CM FF 2\n" + necRun.necSource;
this.ps.println(deck);
this.ps.println("NX\n");
Execute.processResponse(this.ps, this.br, necRun);
```

where `somnecPrefix` is `"CM SOMNEC " + necRun.somnecFile + "\n"` when a
Sommerfeld cache file is in play, otherwise empty.

* Decks are delimited **on stdin by an `NX` card**. Nothing else frames them —
  no length prefix, no sentinel of our own choosing.
* The process is **never restarted between decks**. `destroy()` is the only
  teardown, and it just kills the process and closes the streams.
* The one-shot (non-daemon) path, `Execute.executeWorker`, appends `"EN\n"`
  instead of `NX` for the `NEC2C` engine — that terminates the engine (exit 0).
* `NEC5Daemon` is a *file*-based path (temp in/out files, `NX` between decks,
  `EN` after the last) and is not the model we are reimplementing.

`resident_two_decks.{deck,out}` pins the framing. Observed:

* One `DATA CARD No: n NX` echo per deck.
* **Card numbering restarts at 1 inside each deck** — deck one echoes
  `1 EX / 2 FR / 3 XQ / 4 NX`, deck two echoes exactly the same numbers.
* The engine **reprints its full banner immediately after consuming `NX`**, in
  anticipation of the next deck. Three banners for two decks. That trailing
  banner is left in the pipe for the *next* `processResponse` call, whose
  `SEEKING` state ignores it.
* Closing stdin after the last `NX` is what ends the process: it reprints the
  banner, writes `ERROR-NEC2C: nec2c: Error reading input file - aborting` to
  **both stdout and stderr**, and exits **253**.

## 2. End of run — the critical sentinel

`Execute.processResponse` reads lines until one of these `break`s fires. In
source order:

| Trigger | Test | Meaning |
|---|---|---|
| NX card echo | `partsMatch(parts, "DATA","CARD","No:","","NX")` | **the daemon sentinel** |
| NX input echo | `stringsInOrder(line, "INPUT","LINE","NX")` | other engines' echo style |
| `RUN TIME =` | `partsMatch(parts, "RUN","TIME","=")`, `runTime = parts[3]` | |
| `TOTAL RUN TIME:` | `partsMatch(parts, "TOTAL","RUN","TIME:")`, `runTime = parts[3]` | the `EN` path |
| end of stream | `getLine()` returns null | ⇒ `NECException("BAD NEC RESPONSE")` |

`partsMatch(parts, args…)` walks `args` against the whitespace-split line;
`""` is a wildcard for one field, and `parts` may be **longer** than `args`
(trailing fields are ignored). `stringsInOrder(line, args…)` requires the
uppercased substrings to appear in increasing index order.

So for a resident engine the sentinel is exactly the NEC-2 data-card echo of
the `NX` card:

```
  DATA CARD No:   4 NX   0     0     0     0  0.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00
```

A momwire engine **must emit that line, in that shape, after finishing each
deck**, or the Java side blocks forever on `readLine()`. Two spaces, the
literal `DATA CARD No:`, the card ordinal, the mnemonic, then the classic four
integer fields and six E-format reals. Only fields 0–4 are inspected.

The `EN` path additionally ends with:

```
  TOTAL RUN TIME: 0 msec
```

(field 3 is read as a `Double`; the trailing `msec` is ignored.)

## 3. Line handling common to every state

```java
line  = Execute.getLine(br).trim();
parts = Execute.splitLine(line);         // line.trim().split("\\s+")
if (necRun.necEngine != NECEngine.NEC2C) parts = checkNEC42Fields(parts);
```

The whole grammar is **whitespace-token based, not column based**, for the
NEC2C engine (`checkNEC42Fields` is skipped). Column layout still matters,
because run-together fields become one token — see `PROCESSINGCURRENT` below.

Unconditional per-line checks, before any state dispatch:

| Test | Effect |
|---|---|
| `partsMatch(parts, "ERROR:")` | warning frame `"NEC ERROR (1)"`, parse continues |
| `partsMatch(parts, "SOMNEC","ERROR")` | warning frame `"Saw SOMNEC ERROR:"` |
| `partsMatch(parts, "", "MATRIX","TIMING")` | ⇒ state `MATRIXTIMING` |
| `partsMatch(parts, "FILL=","","SEC.,","FACTOR=","","SEC.")` | `fill=parts[1]`, `factor=parts[4]` (an older layout; **this build does not use it**) |
| `partsMatch(parts, "Time","to","generate","Sommerfeld","ground","tables","=","","seconds")` | `somnecTime += parts[7]` |
| `partsMatch(parts, "Somnec","Computation","Time")` | `somnecTime += parts[3]` |
| `partsMatch(parts, "Radiation","Compute","Time")` | `radiation = parts[3]` |
| `partsMatch(parts, "MATRIX_LINE")` | `processMatrixLine` — pairs of reals from field 1 on, appended to `necRun.cmMatrix` |
| `partsMatch(parts, "-YY")` | `addYYLine(params, line)` — see §6 |

`ERROR:` is a substring-free equality test on token 0, so the oracle's
`ERROR-NEC2C: …` line does **not** trip it.

## 4. The section grammar, in printout order

This is the order the oracle actually emits (see
`tests/fixtures/nec_portal/dipole_rp_pattern.out`). Sections marked *(ignored)*
are consumed harmlessly by the `SEEKING` state.

### 4.1 Banner *(ignored)*

```
                               __________________________________________
                              |                                          |
                              |  NUMERICAL ELECTROMAGNETICS CODE (nec2c) |
                              |   Translated to 'C' in Double Precision  |
                              |__________________________________________|

VERSION:5b4az.ae6ty.1.17
```

### 4.2 `---------------- COMMENTS ----------------` *(ignored)*

Echoes the CM/CE text.

### 4.3 `-------- STRUCTURE SPECIFICATION --------` *(ignored)*

Wire table (`WIRE No: X1 Y1 Z1 X2 Y2 Z2 RADIUS SEG No: FIRST SEG LAST SEG TAG No:`)
then `TOTAL SEGMENTS USED: n   SEGMENTS IN A SYMMETRIC CELL: n   SYMMETRY FLAG: 0`.

### 4.4 `---------- SEGMENTATION DATA ----------` *(ignored, and optional)*

Per-segment centres, lengths, orientation angles, connection data.
**Suppressed entirely by the `QQ` comment directive — see §7.**

### 4.5 Data-card echoes *(only the NX one matters)*

```
  DATA CARD No:   1 EX   0     1     5     0  1.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00  0.00000E+00
```

Cards are echoed as they are read. Execute-type cards (`XQ`, `RP`) run first
and are echoed *after* their output; with an `RP` card present the ordering is
`EX / FR / RP` echoes, then the whole run, then the `XQ` echo, then `NX`.

### 4.6 `--------- FREQUENCY --------` *(ignored)*

```
                                FREQUENCY : 3.0000E+01 MHz
                                WAVELENGTH: 9.9933E+00 Mtr
```

One of these per frequency step of the `FR` card; an `FR` with `npoints > 1`
repeats §4.6–§4.11 per point inside a single `XQ`
(`dipole_fr_sweep.out` has three).

### 4.7 `------ STRUCTURE IMPEDANCE LOADING ------` *(ignored)*

Either `THIS STRUCTURE IS NOT LOADED` or the `LOCATION / RESISTANCE /
INDUCTANCE / CAPACITANCE / IMPEDANCE (OHMS) / CONDUCTIVITY / CIRCUIT` table
with a per-row `TYPE` of `SERIES`, `PARALLEL`, `FIXED IMPEDANCE` or `WIRE`.
Fixtures: `dipole_load_ld0`, `dipole_load_ld4`, `dipole_load_ld5_conductivity`,
`catalog_multiband_trap_dipole`, `catalog_broadband_t2fd`.

### 4.8 `-------- ANTENNA ENVIRONMENT --------` *(ignored)*

Observed bodies, one per ground model:

```
FREE SPACE
PERFECT GROUND
FINITE GROUND - REFLECTION COEFFICIENT APPROXIMATION
FINITE GROUND - SOMMERFELD SOLUTION
```

with, for the finite cases:

```
                            RELATIVE DIELECTRIC CONST: 13.000
                            CONDUCTIVITY:  5.000E-03 MHOS/METER
                            COMPLEX DIELECTRIC CONSTANT:  1.3000E+01-6.3745E+00j
```

The Sommerfeld case is preceded by a line **at column 0**:

```
Somnec Computation Time 30
```

(`parts[3]`, accumulated into `necRun.timings`). This is one of the fields the
capture script canonicalises — see §9.

### 4.9 `---------- NETWORK DATA ----------` *(ignored)*

Present only with `NT`/`TL` cards, and followed by
`--------- STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS --------`,
whose table has the *same* `TAG SEG VOLTAGE… / No: No: REAL…` header and the
same 11-field row shape as the impedance table below. **It is not consumed**,
because the state machine only arms on the `ANTENNA INPUT PARAMETERS` banner
line. Fixtures: `dipole_nt_network.out` (the `NT` form), `dipole_tl_network.out`
and `dipole_tl_shunt_crossed.out` (the `TL` form and the two-form mix) — the
banner is one per run, but the *column header* under it depends on the row
kind. §15 has the whole layout.

### 4.10 `---------- MATRIX TIMING ----------`

```
                             ---------- MATRIX TIMING ----------
                               FILL: 0 msec  FACTOR: 0 msec
```

The banner matches `partsMatch(parts, "", "MATRIX","TIMING")` ⇒ state
`MATRIXTIMING`; the very next line is read as `fill = parts[1]`,
`factor = parts[4]`, then state returns to `SEEKING`. Timing only — nothing
downstream depends on the values.

### 4.11 `--------- ANTENNA INPUT PARAMETERS ---------` — **the Y matrix**

```
                        --------- ANTENNA INPUT PARAMETERS ---------
  TAG   SEG       VOLTAGE (VOLTS)         CURRENT (AMPS)         IMPEDANCE (OHMS)        ADMITTANCE (MHOS)     POWER
  No:   No:     REAL      IMAGINARY     REAL      IMAGINARY     REAL      IMAGINARY    REAL       IMAGINARY   (WATTS)
    1     5  1.0000E+00  0.0000E+00  5.0002E-03 -1.3608E-02  2.3790E+01  6.4745E+01  5.0002E-03 -1.3608E-02  2.5001E-03
    2    14  1.0000E-10  0.0000E+00  9.0738E-04  1.1767E-02  6.5146E-10 -8.4482E-09  9.0738E+06  1.1767E+08  4.5369E-14
```

Two entry paths, both leading to `WAITINGFORSENSORS`:

```java
partsMatch(parts, "-","-","-","ANTENNA","INPUT","PARAMETERS")  -> WAITINGFORSENSORSNONO  // then "NO." "NO."
partsMatch(parts, "---------","ANTENNA","INPUT","PARAMETERS")  -> WAITINGFORSENSORSNoNo  // then "No:" "No:"
```

This build takes the second (nine dashes, then the words). The header row
`No:   No:     REAL …` arms `WAITINGFORSENSORS`. Then, per data row:

```java
int expect   = necRun.necEngine.samplesWidth;   // NEC2C -> 11
int currentAt= necRun.necEngine.samplesOffset;  // NEC2C -> 4
if (parts.length != expect) { sensorYY.add(sensorCurrents); state = SEEKING; }
else sensorCurrents.add(new Complex(Double.valueOf(parts[currentAt]),
                                    Double.valueOf(parts[currentAt+1])));
```

(`NEC2PortalDialog.NECEngine`: `NEC2C(11, 4, false)`, `NEC42(11, 4, true)`,
`NEC5(12, 5, true)`.)

**SimNEC extracts exactly two numbers per row: the CURRENT real and imaginary
parts.** Voltage, impedance, admittance and power columns are *ignored* — the
drive is 1 V, so the current column already is the admittance. A row must be
exactly 11 whitespace tokens; anything else terminates the table.

**How the N×N Y matrix is assembled.** `nec2/NECSource.sensorLines` emits one
`EX` card **per port** in every `XQ` group — `1.0` V on the driven port,
`1.0e-10` V on all the others — so every port appears as a row of this table:

```
FR 0 1 0 0 30. 1
EX 0 1 5 0 1.000000e+00
EX 0 2 5 0 1.000000e-10
XQ
EX 0 1 5 0 1.000000e-10
EX 0 2 5 0 1.000000e+00
XQ
```

One `XQ` per port ⇒ one table per port ⇒ one `ComplexList` per port in
`sensorYY`, and `processResponse` sanity-checks `sensorYY.get(0).size() ==
sensorYY.size()` (square). A non-square result is the `"NO SENSORS"` failure
path (§8). Fixture: `two_source_sensor_lines`.

`processPatchDrives` then walks each row: the first `necRun.numLoads` entries
are surface-patch edge currents, and the remainder are consumed
`necRun.sources[src].width` at a time and **summed** into one entry per source.
For wire sources `width == 1` and `numLoads == 0`, so the row passes through
unchanged.

### 4.12 `-------- CURRENTS AND LOCATION --------`

```
                           -------- CURRENTS AND LOCATION --------
                                  DISTANCES IN WAVELENGTHS

   SEG  TAG    COORDINATES OF SEGM CENTER     SEGM    ------------- CURRENT (AMPS) -------------
   No:  No:       X         Y         Z      LENGTH     REAL      IMAGINARY    MAGN        PHASE
     1    1    0.0000    0.0000   -0.2224   0.05559  9.6735E-04 -2.7670E-03  2.9312E-03  -70.730
```

Entered from `SEEKING` on any of

```java
partsMatch(parts, "", "CURRENTS","AND","LOCATION")
partsMatch(parts, "","","","Wire","Currents")
partsMatch(parts, "-","-","-","CURRENTS","AND","LOCATION")
```

⇒ `WAITINGFORNoNo`, which arms on `No: No:` / `No. No.` / `NO. NO.`
⇒ `PROCESSINGCURRENT`, where per row:

* a row of **10** tokens is data; `tag = parts[1]`, current
  `= (parts[6], parts[7])` — i.e. **REAL and IMAGINARY, not MAGN/PHASE**;
* a row of **9** tokens whose `parts[0]` is longer than 6 characters is a
  run-together `SEG`+`TAG` column and is repaired by `repairRunTogether`
  (splits `parts[0]` at `len-6`) before the 10-token rule applies — so a
  replacement engine must keep the classic `%6d%5d` column widths for
  large segment counts;
* anything else ends the table (state ⇒ `SEEKING`).

Rows are grouped into `WireCurrents` runs by the tag in `parts[1]`, so **the
table must be ordered by tag**.

### 4.13 `---------- POWER BUDGET ---------` *(ignored)*

```
                               INPUT POWER   =  4.7524E-03 Watts
                               RADIATED POWER=  4.7524E-03 Watts
                               STRUCTURE LOSS=  0.0000E+00 Watts
                               NETWORK LOSS  =  0.0000E+00 Watts
                               EFFICIENCY    =  100.00 Percent
```

Not parsed. SimNEC recomputes efficiency itself.

### 4.14 `---------- RADIATION PATTERNS -----------`

```
                             ---------- RADIATION PATTERNS -----------

                             RANGE:  1.000000E+03 METERS
                             EXP(-JKR)/R:  1.00000E-03 AT PHASE:  -24.02 DEGREES

 ---- ANGLES -----     ----- POWER GAINS -----       ---- POLARIZATION ----   ---- E(THETA) ----    ----- E(PHI) ------
  THETA      PHI       VERTC    HORIZ    TOTAL       AXIAL      TILT  SENSE   MAGNITUDE    PHASE    MAGNITUDE     PHASE
 DEGREES   DEGREES        DB       DB       DB       RATIO   DEGREES            VOLTS/M   DEGREES     VOLTS/M   DEGREES
    0.00      0.00    -1e+03  -999.99  -999.99      0.0000      0.00         0.0000E+00    -24.02  0.0000E+00    -24.02
   30.00      0.00      -5.5  -999.99    -5.50      0.0000      0.00 LINEAR  2.8330E-04     34.44  0.0000E+00    -24.02
```

`SEEKING` arms on `partsMatch(parts,"-","-","-","RADIATION","PATTERNS")` **or**
`partsMatch(parts,"","RADIATION","PATTERNS")` ⇒ `WAITINGFORDEGREESDEGREES`,
which arms on `partsMatch(parts,"DEGREES","DEGREES")` ⇒ `PROCESSINGPATTERN`.
Then, per row:

```java
int ptr = 8;
if      (parts.length ==  6) ptr = 2;
else if (parts.length == 11) --ptr;          // ptr = 7
else if (parts.length != 12) { /* table ends */ }
theta = parts[0]; phi = parts[1];
Etheta = (parts[ptr], parts[ptr+1]);  Ephi = (parts[ptr+2], parts[ptr+3]);
```

**The `SENSE` column is what makes a row 12 tokens instead of 11**, and both
occur in the same table (`dipole_rp_pattern.out`: 63 rows with `LINEAR`,
25 without). A replacement engine must reproduce that blank-when-degenerate
behaviour, or half the pattern is read off by one column. **What decides it is
resolved in §12.1.**

`theta` and `phi` are parsed as `Double` then **cast to `int`** for the
`FieldStore` key, so fractional angles collapse.

### 4.15 `-------- NEAR ELECTRIC FIELDS --------` / `NEAR MAGNETIC FIELDS`

```
                             -------- NEAR ELECTRIC FIELDS --------
     ------- LOCATION -------     ------- EX ------    ------- EY ------    ------- EZ ------
      X         Y         Z       MAGNITUDE   PHASE    MAGNITUDE   PHASE    MAGNITUDE   PHASE
    METERS    METERS    METERS     VOLTS/M  DEGREES    VOLTS/M   DEGREES     VOLTS/M  DEGREES
   -1.0000    0.0000   -1.0000   3.1376E-01 -120.82   0.0000E+00    0.00   2.3980E-01  152.53
```

Armed by `partsMatch(parts,"-","-","-","NEAR","ELECTRIC","FIELDS")` /
`("","NEAR","ELECTRIC","FIELDS")` (and the `MAGNETIC` twins)
⇒ `WAITINGFORMETERSMETERSMETERS`, which arms on `METERS METERS METERS` **or**
`METERS DEGREES DEGREES` ⇒ `PROCESSINGNEARFIELD`. Rows are exactly **9**
tokens, all parsed via `tolerantDoubleValueOf` (which repairs Fortran
`1.2345-102` exponent-overflow using
`funkySci = ([+-]*[\d\.]+)([\+-][\d]*)` → mantissa + `"E"` + exponent).
Anything not 9 tokens ends the table.

## 5. Number formats

```java
numPattern = "([+-]?[\\d\\.]+[eE][+-]\\d\\d)(.+)";   // static Pattern oneNumber
funkySci   = "([+-]*[\\d\\.]+)([\\+-][\\d]*)";       // tolerantDoubleValueOf
```

`oneNumber` is compiled but unused in this build. `funkySci` is the only
tolerance in the parser, and it is applied **only in the near-field table**.
Everywhere else a token that `Double.valueOf` rejects logs `"bad numeric
format:"` / `"bad format conversion"` and the value is dropped or zeroed.
Practical consequence for a replacement engine: emit standard C `%E`
formatting; never let an exponent overflow its field.

## 6. The `YY` card and the `-YY` report

`YY` is Ward's extension, not NEC-2. The card names `(tag, segment)` report
points in pairs:

```
YY 1 4 2 4 5 4
```

= three report points: (tag 1, seg 4), (tag 2, seg 4), (tag 5, seg 4). The
engine echoes it as a data card, packing the first four values into the
integer fields and the rest into the reals:

```
  DATA CARD No:   1 YY   1     4     2     4  5.00000E+00  4.00000E+00  0.00000E+00 …
```

For each `XQ`, the engine prints one report line **as the first body line of
the `CURRENTS AND LOCATION` table**, immediately after the
`No: No: X Y Z LENGTH REAL IMAGINARY MAGN PHASE` header:

```
    -YY  2.2720E-04  1.3751E-04  1.3291E-04 -1.0910E-03  1.3291E-04 -1.0910E-03
```

Layout: the literal `"    -YY "` (four spaces, `-YY`, one space) then one
`%11.4E` field per number, single-space separated, no trailing space. Two
numbers (real, imaginary) per report point, in YY-card order — so a 3-point
card gives 6 numbers, and the three runs of a 3-source deck give the three rows
of a 3×3 Y matrix. Fixtures: `jar_testdeck`, `jar_testdeck_daemon_framed`
(3 ports), `two_source_yy_card` (2 ports).

Cross-checked in `tests/test_nec_portal_fixtures.py`: the `-YY` numbers for
`two_source_yy_card` agree, digit for digit at the printed precision, with
the CURRENT columns of the
`ANTENNA INPUT PARAMETERS` tables in `two_source_sensor_lines`, i.e. the two
mechanisms compute the same Y matrix.

Java side:

```java
static boolean addYYLine(ComplexListList yParams, String line) {
    String[] parts = line.trim().split("\\s+");
    if (parts.length < 3 || parts.length % 2 != 1 || !"-YY".equals(parts[0])) return false;
    // pairs from index 1 -> one Complex each, appended as a row
}
```

⚠️ **In this build (SimNEC.jar dated 2026-01-10) the `-YY` rows are parsed and
then discarded.** `addYYLine` appends to the local `ComplexListList params`,
but `processResponse` finishes with `necRun.yParams = sensorYY` — `params` is
never read. The companion `addNEC5YY(params)` returns early because the static
`Execute.yyValues` is *never assigned anywhere in the jar* (verified: the only
references are the `getstatic`s inside `addNEC5YY`). And `NECSource.buildYYLine`
— which would write the card — has **no caller**; the NEC2C deck writer emits
the multi-`EX` sensor lines instead.

**So the live Y-matrix path is §4.11, not the `YY` card.** A momwire engine
must get the multi-`EX` `ANTENNA INPUT PARAMETERS` table exactly right; `-YY`
support is optional today, cheap to add, and worth adding for forward
compatibility.

## 7. Comment-line directives (`processCMLine` in the oracle)

The oracle scans `CM`/`CE` bodies for three keywords (recovered from the
binary's `processCMLine`, `strncmp` against `.rodata` at 0x436dbd/0x436dc0/
0x436dc7):

| Directive | Parsed as | Effect |
|---|---|---|
| `QQ <n>` | `sscanf("%d")` into a global | quiet mode; **suppresses the whole `SEGMENTATION DATA` section** when `n > 0` |
| `SOMNEC <…>` | `sscanf("%d %s")`, needs 2 fields | Sommerfeld table cache file |
| `FF <n>` | `sscanf("%d")` into `reducedField` | reduced far-field detail; **writes `reducedField:2` to stderr** |

`NEC2Daemon.submit` always prepends `CM FF 2`, so **every** SimNEC deck emits
that stderr line. The jar's embedded test deck begins `CE QQ 1`, which is why
`jar_testdeck.out` has no `SEGMENTATION DATA` block.

`NECSource` can also insert `CM DM 1` (from the `DumpMatrix` env value), which
in some engine is meant to produce the `MATRIX_LINE` rows `processMatrixLine`
consumes. **This oracle build has no `MATRIX_LINE` string at all** and ignores
`DM` — see §10.

## 8. Error strings and exit codes

| Where | String | Trigger |
|---|---|---|
| `Execute.processResponse` | `"BAD NEC RESPONSE"` (NECException) | stdout hit EOF before a sentinel |
| `Execute.processResponse` | `"NO SENSORS"` (log) | `sensorYY` empty or non-square, then `writeBadSourceAndOut` |
| `Execute.writeBadSourceAndOut` | `"NEC ABORTED EARLY "` / `"NEC ABORTED EARLY but "` | dumps `badNEC.nec` + `badNEC.out` under the SimNEC locale dir |
| `Execute.closeAll` | `"BAD NEC EXIT CODE:"` (NECException, message `-exitCode`) | non-zero exit at teardown |
| `Execute.closeAll` | `"ERROR: Failure to Close Command exitCode:"` (log) | same |
| `Execute.execute` | `"NEC DAEMON" / "Failure to execute command"` | `executeWorker` returned false |
| `Execute.interpExitCode` | `"Probably segment too short in connected wires"` | exit code 157 |
| `NEC2PortalDialog` | `"NEC2C ERROR" / "NO NEC Command Available"` | no usable command configured |
| `Execute.processResponse` | `"NEC ERROR (1)"` warning | a line whose first token is exactly `ERROR:` |
| `Execute.processResponse` | `"Saw SOMNEC ERROR:"` warning | a line starting `SOMNEC ERROR` |

`closeAll` clamps `|exitCode| > 10000` to 0 before testing it. Since the
daemon path only calls `closeAll` at teardown, the 253 the oracle exits with
on stdin EOF *would* surface as `BAD NEC EXIT CODE: -253` — SimNEC avoids it
by calling `NEC2Daemon.destroy()` (a `Process.destroy()`), not `closeAll`.

Oracle-side error strings observed (both stdout and stderr):

```
ERROR-NEC2C: nec2c: Error reading input file - aborting
```

Other messages in the binary: `nec2c: Bad YY card format`,
`COMMAND DATA CARD ERROR:`, `CARD'S MNEMONIC CODE TOO SHORT OR MISSING.`,
`NON-NUMERICAL CHARACTER '%c' IN INTEGER FIELD AT CHAR. %d`,
`No convergence in gshank() - aborting`,
`NGF solution option not supported - aborting`.

## 9. The fixture corpus

`scripts/nec_portal_capture.py` regenerates
`tests/fixtures/nec_portal/` — 40 `<name>.deck` / `<name>.out` pairs plus
`manifest.json` (per-deck exit code, both SHA-256s, and the captured stderr).

* `jar_testdeck`, `jar_testdeck_daemon_framed` — the deck embedded in
  `nec2/NEC2Daemon`, raw and with the daemon's `CM FF 2` prefix.
* 27 hand-authored decks: free space, `FR` sweep, PEC / reflection-coefficient
  / Sommerfeld grounds, `LD 0` / `LD 4` / `LD 5`, `GS`, `GM`, `NT`, two `TL`
  decks (§15), two `MP` decks and two `PT` decks (§16), two `EK` decks (§17),
  two `GD` decks (§18), `RP`, `NE`, `NH`, the 2-port sensor-line probe and the
  2-port `YY` probe.
* 10 catalog designs through `antennaknobs.nec_export.export_nec`, massaged
  into the portal dialect (`EN` dropped, `NX` appended).
* `resident_two_decks` — two decks down one process, the residency pin.

`--check` regenerates into a temp dir and diffs; it exits non-zero on any
drift. The only non-determinism in the printout is wall-clock timing, which the
script canonicalises to zero:

```
FILL: <n> msec  FACTOR: <n> msec
FILL=<x> SEC., FACTOR=<x> SEC.
TOTAL RUN TIME: <n>
RUN TIME = <x>
Somnec Computation Time <x>
Radiation Compute Time <x>
Near Field Compute Time <x>
Time to generate Sommerfeld ground tables = <x> seconds
```

Nothing else is touched — fixtures are otherwise verbatim oracle output.

## 10. What we do NOT know yet

Later units must resolve these:

1. **How SimNEC recovers after a parse stall.** `processResponse` blocks in
   `readLine()` with no timeout. If a replacement engine fails to emit the `NX`
   echo, does anything on the Java side ever time out, or does the UI hang?
   `NECRun.waited` and `Task.Limits` exist but their role is unread.
2. **`MATRIX_LINE`.** `Execute.processMatrixLine` parses it, `NECSource` can
   emit `CM DM 1` to request it, but this oracle build contains no such string.
   Which engine produces it, and is `necRun.cmMatrix` used for anything a
   momwire engine must support?
3. **`checkNEC42Fields`.** Skipped for `NEC2C`. If we ever want the `NEC5`
   column layout (`samplesWidth 12`, `samplesOffset 5`, `thetaFirst true`) we
   need its exact semantics.
4. **The `-version` handshake for a non-`nec2c`-named binary.** We know the
   filename must contain `nec2c`/`nec5`/`nec42` and the banner must match one
   of the four regexes, but not what `SimNEC.minimumNEC2CVersion` currently is
   — so we do not know how low a version tail we may claim.
5. **Cards the portal emits that this corpus does not cover**: `PT` (print
   control, emitted around plane-wave excitation), `MP` (emitted once
   `segmentCount >= NEC2PortalDialog.getMPInfo()[0]`), `IS` (NEC-4.2
   insulation), and the plane-wave `EX i1 …` form with `PT -1` / `XQ` /
   `PT -2`. Their printout shape is unpinned.
6. **`processExcitation`.** A separate reader (`getParts` loop, `NO. NO.`
   headers, `Complex(parts[5], parts[6])`) used for receive patterns. It is
   never called from `processResponse` in the decompiled flow — who calls it,
   and does a momwire engine need to feed it?
7. **Patch/surface support.** `WAITINGFORPATCHNoNo` / `PROCESSINGPATCHCURRENT`
   (12-token rows, magnitude/angle pairs at fields 6..11) and
   `necRun.numLoads` edge currents assume `SP`/`SM` patches, which the portal
   emits via `task.necSurfaces.insertSurfaces`. Out of scope for wire-only
   momwire, but it means `numLoads > 0` decks exist in the wild.
8. **Whether the trailing eager banner is load-bearing.** The oracle prints its
   banner right after consuming `NX`. `SEEKING` ignores it, so a momwire engine
   probably need not — but "probably" is doing work there; unit 2 should test
   both.
9. **stderr discipline.** `NEC2Daemon` never reads the child's stderr (only
   `NEC5Daemon` drains it). A momwire engine that writes much to stderr could
   fill the pipe buffer and deadlock. The safe rule is: write nothing to stderr
   except what `CM FF` already produces.
10. **Blank lines around the `NX` echo after a multi-point `FR`.** Every
    single-point fixture puts three blank lines between the last
    `EFFICIENCY` line and the next data-card echo (`dipole_free_space`,
    `two_source_yy_card`, `jar_testdeck`). `dipole_fr_sweep` — the one deck
    with `nfrq > 1` — puts **zero** before its `NX` echo, while still putting
    two before each repeated `FREQUENCY` header. What in nec2c's frequency
    loop drops them is unread. Blank lines are invisible to `Execute`, so
    `nec_portal.py` emits the consistent three and accepts the mismatch.
11. **The engine name a replacement may claim.** Unresolved from item 4 above,
    but with a hard consequence found in unit 2: `versionA`'s `(.*)` is
    greedy, so a probe line of `nec2c.ae6ty.momwire.9.1` yields group(1) =
    `"momwire.9.1"`, `Double.valueOf` throws, and SimNEC reports "nec2c
    version too old". **The `-version` tail must be a bare one-dot number**,
    so `nec_portal.py` probes as `nec2c.ae6ty.9.1` and carries its real
    identity in the printout banner (`VERSION:nec2c.ae6ty.momwire.9.1`),
    which no regex is anchored to reach. Whether SimNEC has any other place
    to record an engine's name is still unknown.

## 11. Resolved by unit 2 (`src/antennaknobs/nec_portal.py`)

Empirical rules the fixture corpus carries that §4 did not state, all now
reproduced by the momwire engine and pinned in `tests/test_nec_portal.py`:

1. **The `EX` list is cleared at every `XQ`.** `jar_testdeck`'s second group
   prints one `ANTENNA INPUT PARAMETERS` row, not two, and
   `two_source_sensor_lines` drives the same segment at 1 V and then at
   1e-10 V without complaint. Sources accumulate within a group only.
2. **The frequency preamble is printed only when the matrix is rebuilt.** A
   second `XQ` with no intervening `FR` card emits `ANTENNA INPUT PARAMETERS`
   straight away — no `FREQUENCY`, `STRUCTURE IMPEDANCE LOADING`,
   `ANTENNA ENVIRONMENT` or `MATRIX TIMING` (fixture:
   `two_source_sensor_lines`, two `XQ`s under one `FR`). With a fresh `FR`
   per group the preamble repeats (`two_source_yy_card`, `jar_testdeck`).
3. **`ANTENNA INPUT PARAMETERS` `SEG No:` is the GLOBAL segment number**, not
   the tag-local one on the `EX` card: `EX 0 2 4` on `jar_testdeck` prints
   `2    11`.
4. **`GROUND PLANE SPECIFIED.` comes from the `GE` flag alone.** The catalog
   decks carry `GE 0` + `GN 1` and the oracle prints no annotation; only
   `GE -1` / `GE 1` produces it.
5. **`---------- MULTIPLE WIRE JUNCTIONS ----------`** sits between
   `TOTAL SEGMENTS USED` and `SEGMENTATION DATA` whenever three or more
   segment ends meet at a node, listing signed segment numbers (− for end 1,
   + for end 2). One fixture has it: `catalog_verticals_vertical`.
6. **The `STRUCTURE SPECIFICATION` table echoes the geometry CARDS**, not the
   resolved wire list: a `GM`-doubled deck shows one `GW` row plus
   `THE STRUCTURE HAS BEEN MOVED, MOVE DATA CARD IS:`, and `TOTAL SEGMENTS
   USED` reports the post-transform count (`dipole_gm_translated_pair`:
   one row, 18 segments). `GS` likewise prints the pre-scale coordinates plus
   `STRUCTURE SCALED BY FACTOR:`.
7. **The oracle blanks a zero loading cell.** `LD 1 2 1 1 0.0 5e-6 6.46e-12`
   prints an empty RESISTANCE column, not `0.0000E+00`.
8. **`-YY` and `ANTENNA INPUT PARAMETERS` are the same measurement.** For the
   oracle they are trivially equal (a pulse basis makes the segment current
   and the driving-point current one number). A basis where they differ —
   momwire's — must print the port's Galerkin current in BOTH, or the two Y
   paths disagree; `nec_portal.py` reads a `YY` point that carries a gap from
   the port and one that does not from the segment.

## 12. Resolved by unit 3 (`RP`, `NE`/`NH`, `NT`, the differential harness)

Unit 3 implements the three cards unit 2 left on the error path and adds
`tests/test_nec_portal_differential.py`, which compares parsed VALUES between
the two engines. The corpus grew to **30** fixtures: `dipole_rp_crossed_quadrature`
and `dipole_nh_nearfield` were captured specifically to close items below.

### 12.1 The `SENSE` column — §4.14's 11-vs-12-token rule, resolved

`SENSE` is a **fixed-width field**, ` %-6s` followed by the `%12.4E` E(THETA)
magnitude, so a row is 19 columns wide either way and the token count is the
only visible difference. It holds:

| printed | when |
|---|---|
| `LINEAR` | the polarisation ellipse is degenerate (axial ratio ≈ 0) |
| `LEFT` / `RIGHT` | elliptical or circular |
| six blanks | **both** `\|E_theta\|²` and `\|E_phi\|²` are ≤ `1e-20` (V/m)² at the requested range |

The blank case is **the same test that produces the `-999.99` gain floor**, and
that is the part §4.14 could not see. The floor is *not* a log clamp:
`dipole_rp_pattern.out` prints `-999.99` for a direction whose E(THETA) is
`5.4196E-15` — a true gain near −220 dB, not −1000 — while printing a real
number one row away. Per column:

```
VERTC = -999.99 if |E_theta|^2 <= 1e-20 else 10*log10(G_theta)
HORIZ = -999.99 if |E_phi|^2   <= 1e-20 else 10*log10(G_phi)
TOTAL = -999.99 if BOTH are     <= 1e-20 else 10*log10(G_theta + G_phi)
SENSE = blank   if BOTH are     <= 1e-20
```

`dipole_rp_crossed_quadrature` (two orthogonal dipoles fed `EX … 1. 0.` and
`EX … 0. 1.`) is the deck that pins the rest. It shows all three facts the
linear fixture cannot:

* the circular form really is a word, `LEFT`, not a symbol — so 12 tokens
  either way and `Execute`'s `ptr = 8` branch is right for both;
* `δ = arg(E_phi) − arg(E_theta) = +90°` at the zenith prints
  `AXIAL RATIO 1.0000 … LEFT`, so **positive `sin δ` is LEFT** in this build;
* a row can have `VERTC = -999.99` and still carry a named sense
  (θ = 90°, where `E_theta = 2.7098E-15` but `E_phi` is large) — proving the
  two thresholds are per-component and per-row respectively, not one flag.

`nec_portal.py` reproduces all of it; `test_nec_portal_differential.py::
test_the_sense_column_is_what_makes_a_row_twelve_tokens` asserts the
blank↔floor equivalence on both sides of both pattern fixtures.

### 12.2 `RP`/`NE`/`NH` are execute cards, not report requests

nec2c **runs on reading them**. `dipole_rp_pattern` is `EX / FR / RP / XQ` and
the printout is: the `EX`, `FR`, `RP` echoes, then the entire run (frequency
preamble, `ANTENNA INPUT PARAMETERS`, `CURRENTS AND LOCATION`, `POWER BUDGET`,
`RADIATION PATTERNS`), then the `XQ` echo **immediately followed by the `NX`
echo** — the `XQ` produces nothing at all, not even the blank lines a real run
is wrapped in. The rule that reproduces every fixture: an execute card runs
only if something (`EX`, `FR`, `LD`, `GN`, `NT`, `YY`) has arrived since the
last execution. An engine that ran the trailing `XQ` too would hand SimNEC a
2×1 sensor matrix where it expects 1×1, i.e. the `"NO SENSORS"` path (§8).

Blank-line detail: the report block ends with **four** blank lines before the
next data-card echo, where a plain `XQ` block ends with three.

### 12.3 The pattern block's other numbers

* `RANGE:%14.6E METERS` and
  `EXP(-JKR)/R:%13.5E AT PHASE:%8.2f DEGREES` come straight off the card's
  `RFLD` field: the phase is `-k·r` reduced mod 360 (r = 1000 m at 30 MHz
  gives −24.02°).
* **VERTC is `%10.2g`, not `%.2f`.** This ae6ty build prints the vertical gain
  to two SIGNIFICANT figures, which is why the floor reads `-1e+03` while
  TOTAL on the same row reads `-999.99` and 2.15 dB reads `2.1`. Missing this
  keeps the row parseable and silently changes its column geometry.
* `AVERAGE POWER GAIN: %12.4E - SOLID ANGLE USED IN AVERAGING: (%+7.4f)*PI
  STERADIANS` is emitted when XNDA's `A` digit is 1. The quadrature was
  recovered from two fixtures: each theta sample owns the solid-angle band
  between its half-step neighbours, **clipped to the requested theta range**,
  and phi contributes `NPH − 1` columns (the last sample of a 0–360 sweep is
  the first one again). The bands then telescope to exactly
  `(cos θ_start − cos θ_end)·(NPH−1)·Δφ`, which is why a full sphere prints a
  round `(+4.0000)*PI` and a hemisphere `(+2.0000)*PI` — a plain midpoint sum
  gives 3.86 and 1.93 instead.
* The E-field phase convention is nec2c's:
  `E = -j·η·k/(4π)·e^(-jkr)/r·M_perp`. Verified rather than assumed — with it,
  our E(THETA) PHASE lands within 1.4° of the oracle's on
  `dipole_rp_pattern`; a missing `-j` would be 90° out.
  One residue: where a component is *exactly* zero we print phase `0.00` and
  nec2c prints the reference phase (`-24.02`), because its "zero" is a
  denormal that still carries `arg(e^(-jkr))`. Magnitude `0.0000E+00` either
  way, and nothing reads the column.

### 12.4 `NE`/`NH`

* Grid order is **X fastest, then Y, then Z** (`dipole_ne_nearfield.out`,
  `NE 0 3 1 3 …`).
* The magnetic banner is **not** the electric one with a word swapped:

```
                             -------- NEAR ELECTRIC FIELDS --------
                                   -------- NEAR MAGNETIC FIELDS ---------
```

  Different indent, different trailing dash run, and the units row changes
  `VOLTS/M` to `AMPS/M` on a different column pitch. `dipole_nh_nearfield` was
  captured for exactly this.
* Rows are `%10.4f`×3 then `(%13.4E, %8.2f)`×3 — nine tokens, which is what
  `Execute`'s `PROCESSINGNEARFIELD` state requires.

**Does momwire have a near-field API? No.** `BSplineSolver` exposes
`compute_impedance`, `compute_y_matrix`, `currents_at_knots` and
`wire_loss_power` and nothing else; the only field evaluator anywhere in the
library is `SinusoidalSolver._field_components_bcast`, which is private,
sinusoidal-basis-only, and cannot consume a B-spline coefficient vector. The
near field is therefore computed **in `nec_portal.py`, from the solved
current**, in mixed-potential form:

```
E = -j·ηk/(4π)·Σ_n p_n·G_n  -  j·η/(4πk)·Σ_m ΔI_m·(1 + jkR_m)/R_m²·G_m·R̂_m
H =        1/(4π)·Σ_n (p_n × R̂_n)·(jk/R_n + 1/R_n²)·G_n           G = e^(-jkR)/R
```

with `p = I·dl` at element midpoints (the `-jωA` term) and `ΔI = I_in − I_out`
at the mesh NODES as the discrete continuity charge `q = ΔI/(jω)` (the `-∇Φ`
term). Each momwire mesh segment is resampled into 8 elements through
`currents_at_knots(coeffs, s_array=…)`. In the radiation zone the pair
collapses to the same `-j·ηk/(4πr)·e^(-jkr)·M_perp` the RP table is normalised
against, so the two tables are one physics.

**Why not a chain of Hertzian point dipoles.** That form is simpler and agrees
with this one everywhere off the structure, but each element carries its own
±q pair separated by `dl`; a sample point a fraction of an element away sees
that pair's 1/R³ term with nothing to cancel it. Measured on
`dipole_ne_nearfield`: a grid point lying **on** the wire came out at
`1.7E+05 V/m` against nec2c's `1.2E-02`. Splitting current and charge puts the
charge where it physically is and makes `ΔI` small wherever the current is
smooth, so adjacent nodes cancel the way the continuous integral does.

Accuracy, measured against the oracle fixtures:

| where | agreement |
|---|---|
| off the conductor (1 m from a 5 m dipole) | **0.7 % magnitude, 0.4° phase** (E); 0.3 % / 0.5° (H) |
| on the driven segment | `1.14 V/m ∠-176.9°` against nec2c's `1.80 V/m ∠-180°` |
| on a non-driven segment | `1.0E+01` against nec2c's `1.2E-02` — **not a field** |

The last row is the honest limit and is pinned as such rather than hidden: `R`
is regularised as `sqrt(|R|² + a²)` (the thin-wire convention — the sample is
taken on the conductor surface, matching momwire's own `rho_eval`), and a
point-source quadrature evaluated inside its own source is not a field
anybody should read. nec2c sidesteps the question entirely: on a driven
segment it prints the **impressed source field**, `1 V / 0.5559 m = 1.8 V/m`,
which is a different quantity from the one the rest of its table reports.

`NE`/`NH` over a finite (reflection-coefficient or Sommerfeld) ground takes the
error path — the near field of a lossy half-space is not an image. PEC ground
is supported (image current mirrored, image charge negated).

### 12.5 `NT`

The card gives `Y11`, `Y12`, `Y22` and takes `Y21 = Y12`. The branch hangs
across the two segments' gaps, in parallel with the structure, and
`dipole_nt_network.out` pins the consequence exactly:

* **`ANTENNA INPUT PARAMETERS` reports the SOURCE current — segment plus
  network — not the segment current.** For the fixture, `I_source =
  1.1534E-02 + 1.0275E-03j`, `I_segment = -2.7287E-03 - 4.3690E-03j` (which is
  what `CURRENTS AND LOCATION` prints for segment 5), and the difference is
  exactly `Y·V` at that port. Reading the segment current into the impedance
  table gives a *negative* driving-point resistance.
* An undriven network port is **not** a shorted gap: its row is KCL
  (`(Y_antenna + Y_network)·V = 0`), so its voltage floats. In the fixture the
  parasitic dipole's gap sits at `7.3017E-01 + 7.1313E-01j` V.
* `NETWORK LOSS` in the power budget is `½·Σ Re(V·conj(I_network))`, which is
  identically zero for the fixture's purely reactive branch.
* Row order in `STRUCTURE EXCITATION DATA AT NETWORK CONNECTION POINTS` is the
  far end first: `NT 1 5 2 5` prints `(2, 14)` then `(1, 5)`.
* `NETWORK DATA` rows are padded to 106 columns with nine trailing spaces.
* Both network sections are *(ignored)* by `Execute` — its state machine arms
  on the `ANTENNA INPUT PARAMETERS` banner alone, and the excitation table
  repeats the `No: No: REAL` header with the same 11-token rows without ever
  being reached. They are emitted because the layout is the contract.

`TL` remained on the error path after unit 3 — no fixture pinned how nec2c
lays a transmission line out inside `NETWORK DATA`, and guessing a layout is
worse than refusing the card. **Issue #799 captured it; see §15.**

### 12.6 The `GN` long tail

Probed directly against the oracle rather than left as a question:

* **`GN 2` + a radial screen is refused by NEC-2 itself.** `GN 2 16 0 0 13.
  0.005 5.0` makes the oracle print

  ```
    RADIAL WIRE G.S. APPROXIMATION MAY NOT BE USED WITH SOMMERFELD GROUND OPTION
  ```

  and stop — **no `NX` echo**, which is precisely the `readLine()` stall §10.1
  worries about, arriving from the oracle rather than from a replacement.
  There is no long tail to implement here.
* **`GN 0` + a radial screen** does work and prints an extra
  `RADIAL WIRE GROUND SCREEN / n WIRES / WIRE LENGTH: / WIRE RADIUS: /
  MEDIUM UNDER SCREEN -` block ahead of the usual medium description. momwire
  has no screen model, so `nec_portal.py` **rejects `NRADL ≠ 0` by name**
  rather than silently dropping the screen and reporting a different antenna.
* **`GN 2`'s second-medium fields are silently ignored by this build.**
  `GN 2 0 0 0 13. 0.005 80. 5.0 50. -2.` prints the primary medium only, with
  no second-medium block and no warning. Our engine may — and does — ignore
  them too and stay byte-identical.

No fixture was committed for any of these: two of the three produce printouts
that violate corpus invariants every other fixture upholds (an abort with no
`ANTENNA INPUT PARAMETERS` and no sentinel), and the third would pin a section
we deliberately refuse. The error paths are tested from synthesised decks in
`test_nec_portal_differential.py::test_unsupported_cards_take_the_documented_error_path`.

### 12.7 A defect the differential harness found

`_segment_currents` mapped each NEC segment to the nearest momwire element by
**position alone**. Two wires that cross share a segment midpoint *exactly*, so
the crossed-quadrature deck printed wire 1's port current on wire 2's segment
14 — a 90° error behind a perfectly plausible magnitude, invisible to every
layout test and to every single-wire fixture. The match now requires the
element to run along the segment as well, falling back to pure distance if
nothing does. This is the class of bug a differential harness exists to catch:
no self-consistency check could have seen it.

### 12.8 Cross-engine agreement, measured

Worst case over every row of every table, momwire 0.23.0 against
nec2c 5b4az.ae6ty.1.17; the full per-fixture table is the module docstring of
`tests/test_nec_portal_differential.py`.

| quantity | bar | corpus worst | notes |
|---|---|---|---|
| `ANTENNA INPUT PARAMETERS` Z and I | 5 % | 2.83 % | plus three justified outliers |
| `-YY` report currents | 5 % | 2.83 % | 12.02 % on `jar_testdeck`'s near-open port |
| current distribution (peak-normalised) | 8 % | 6.00 % | |
| `RADIATION PATTERNS` TOTAL gain | 0.5 dB | **0.12 dB** | |
| peak-gain direction | 1 step | **0 steps** | |
| near field, off the conductor | — | 0.7 % / 0.4° | |

The three fixtures over 5 % are all the same phenomenon — a small residual
between two large, nearly cancelling numbers — and each carries a test
asserting the identity that makes it benign:
`catalog_dipoles_short_dipole_loaded` (a +818 Ω coil cancelling the antenna's
reactance; `Re(Z)` agrees to 1.8 % and the reactance gap is 1.0 % of the coil),
`jar_testdeck` port 1 (the centre gap of a full-wave split dipole at
`|Z| ≈ 3.5 kΩ` — the known high-|Z| basis-sensitive class, antennaknobs #459;
the other two ports agree to 0.4 %), and `dipole_nt_network`'s network-table
segment current (12 %, while the source current SimNEC actually reads agrees
to 1.3 %).

## 13. Still unknown after unit 3

From §10, still open: items 1 (`processResponse` has no timeout — what, if
anything, on the Java side notices a stalled engine), 2 (`MATRIX_LINE`),
3 (`checkNEC42Fields`), 6 (`processExcitation`'s caller), 7 (patch/surface
support), and 10 (what drops the blank lines around a multi-point `FR`'s `NX`
echo). Items 4/11 closed in unit 4 — see §14.

Item 5 shrank but did not close: `RP`, `NE`, `NH` and `NT` are now pinned; `PT`
(and the plane-wave `EX i1 …` / `PT -1` / `XQ` / `PT -2` sequence), `MP` and
`IS` are not. `TL` joined them here — the portal emits it, `nec_import` can
translate it, and only the printout layout was missing. **Closed by issue #799,
§15.** `PT` and `MP` **closed by issue #800, §16** — and `PT` turned out not to
be entangled with the plane-wave sequence at all; only `IS` and the plane-wave
`EX` itself are left of item 5.

New for unit 4:

1. **`RP` modes 1–6 and the `RFLD = 0` gain-only form.** `nec2/NECSource` only
   ever writes `RP 0 … 1000`, so refusing the rest costs nothing today, but
   their tables are a different shape and nobody has looked.
2. **Spherical `NE`/`NH` (`I1 = 1`).** The header switches to
   `METERS DEGREES DEGREES`, which `Execute`'s
   `WAITINGFORMETERSMETERSMETERS` state explicitly accepts (§4.15) — so SimNEC
   expects to see it, and we refuse it.
3. **Whether SimNEC ever reads a near-field or pattern table at all.**
   `PROCESSINGPATTERN` and `PROCESSINGNEARFIELD` fill `FieldStore`, but who
   consumes `FieldStore` — and with what convention — is unread. Our pattern
   is normalised by source input power, which is the antennaknobs convention;
   if SimNEC assumes directivity instead, the plots will differ by the
   efficiency even though every number here is self-consistent.

## 14. Resolved by unit 4 (packaging, and two reads of the installed jar)

### 14.1 `SimNEC.minimumNEC2CVersion` = **1.23** (§10 item 4, closed)

Read straight out of the installed jar's static initialiser:

```
$ javap -p -c -constants -classpath ~/SimNEC/SimNEC.jar ae6ty.SimNEC
  public static double minimumNEC2CVersion;
  ...
      13: ldc2_w   #49    // double 1.23d
      16: putstatic #51   // Field minimumNEC2CVersion:D
```

`Execute.testCommand` parses group(1) of whichever of `versionA`/`versionB`/
`versionC` matches, and accepts iff `value >= minimumNEC2CVersion`; below it,
`NEC2PortalDialog.setVersion("<none>")` and the user is told "nec2c version too
old". `nec_portal.PROBE_VERSION`'s tail is `9.1`, which clears it with room.

The floor is not arbitrary: **it is exactly the version of the nec2c SimNEC
currently ships**. This machine has two locale trees — the stale
`~/.SimNEC/2/3` the corpus was captured from (`5b4az.ae6ty.1.17`) and the live
`~/.SimNEC/5/1` belonging to SimNEC 5.1a0 (`5b4az.ae6ty.1.23`). So the floor
moves with the shipped oracle, and a future SimNEC could in principle raise it
past 9.1 — one more reason to ask Ward for a blessed convention rather than to
squat on a number (see `2026-08-08-ward-simnec-momwire-notes.md`).

### 14.2 There is still nowhere to put an engine's *name* (§10 item 11, closed)

`testCommand` ends with `NEC2PortalDialog.setVersion(line)` — the **whole
trimmed first line**, not group(1) — so SimNEC does record and display the
probe string verbatim. That is the only such place. It does not help: the line
still has to satisfy a regex whose greedy `(.*)` runs to end-of-line and is
then handed to `Double.valueOf`, so any name anywhere after `nec2c.ae6ty.`
fails the parse. The printout banner (`VERSION:nec2c.ae6ty.momwire.9.1`)
remains the only place we can say who we are.

### 14.3 The corpus is portable across the oracle's own versions

Re-capturing all 30 fixtures with the live 1.23 oracle
(`NEC_PORTAL_ORACLE=~/.SimNEC/5/1/Examples/nec2c.ae6ty/bin/nec2c-ubuntu-x86
python scripts/nec_portal_capture.py`) and diffing against the committed 1.17
set gives, over the whole corpus, **only**:

* the `VERSION:` banner line itself;
* signed zero on three `CURRENTS AND LOCATION` coordinate cells
  (`-0.0000` → `0.0000`, `jar_testdeck` and its daemon-framed twin);
* one denormal (`NETWORK LOSS = 0.0000E+00` → `-2.6021E-18`,
  `dipole_nt_network`).

No section, column, header or token count moves. The fixtures were therefore
left as captured — re-capturing would churn 30 files to buy nothing, and the
1.17 set is now known to be layout-representative of at least 1.17 through
1.23.

### 14.4 Packaging

The daemon ships as the `momwire-nec2c` console script
(`[project.scripts]` → `antennaknobs.nec_portal:main`). The name is contract:
`NEC2PortalDialog` picks the engine dialect off the lowercased **filename**,
and the sibling substrings `nec5`/`nec42` would select a different column
layout. `NEC2Daemon` launches it via `sh -c` with cwd=`$HOME`, so the entry
point is working-directory independent; both properties are pinned in
`tests/test_nec_portal.py` (the cwd test is the file's one subprocess).
`scripts/nec_portal_smoke.sh` is the hand check for the process contract —
three decks down one resident process from an unrelated cwd, PASS/FAIL.

### 14.5 Still open after unit 4

Unchanged from §13 bar items 4/11: `processResponse`'s missing timeout,
`MATRIX_LINE`, `checkNEC42Fields`, `processExcitation`'s caller, patch/surface
support, the multi-point-`FR` blank lines, `TL`/`PT`/`MP`/`IS` printout
layouts, `RP` modes 1-6, spherical `NE`/`NH`, and the `FieldStore`
gain-vs-directivity convention. The last four are asks on Ward's desk.
(`TL` came off this list in §15; the live open list is §15.6.)

## 15. Resolved by issue #799 — the `TL` printout layout

`TL` was the last card the portal dialect could carry that this engine refused.
Two captures close it: `dipole_tl_network` (a 600 Ω, 2.5 m — 0.2502 λ at
30 MHz — line between two dipoles) and `dipole_tl_shunt_crossed` (a crossed
450 Ω line with complex shunt ends, chained through an `NT` onto a third
dipole).

### 15.1 nec2c prints a `TL` as an **equivalent network**

Same `---------- NETWORK DATA ----------` banner an `NT` gets — one per run,
at the same indent, arming nothing on the Java side. What changes is the
three-line **column header** under it, and it describes the *card*, not a Y
matrix:

```
                                            ---------- NETWORK DATA ----------
  -- FROM -  --- TO --      TRANSMISSION LINE        --------- SHUNT ADMITTANCES (MHOS) ---------   LINE
  TAG   SEG  TAG   SEG    IMPEDANCE      LENGTH     ----- END ONE -----      ----- END TWO -----   TYPE
  No:   No:  No:   No:         OHMS      METERS      REAL      IMAGINARY      REAL      IMAGINARY
    1     5    2    14   6.0000E+02  2.5000E+00   0.0000E+00  0.0000E+00   0.0000E+00  0.0000E+00 STRAIGHT
```

(`dipole_tl_network.out`, verbatim.) The **row layout is identical to an `NT`
row** — ` %4d %5d %4d %5d` then six alternating `%12.4E`/`%11.4E` fields — and
only the *meaning* of the six differs:

| column pair | `NT` row | `TL` row |
| --- | --- | --- |
| 1–2 | `Re/Im(Y11)` | `\|z0\|` (Ω), resolved `length` (m) |
| 3–4 | `Re/Im(Y12)` | `Re/Im` of the END ONE shunt admittance |
| 5–6 | `Re/Im(Y22)` | `Re/Im` of the END TWO shunt admittance |
| tail | nine blanks (pad to col 106) | `STRAIGHT` / `CROSSED`, right-aligned in the same nine |

An `NT` row's nine trailing spaces and a `TL` row's ` STRAIGHT` occupy exactly
the same nine columns, so one `%9s` serves both. There is **no** separate
"LINE LENGTH" or impedance echo line anywhere else in the printout: the card's
`DATA CARD No:` echo (which prints the *signed* z0 and the *unresolved*
length) and this row are the only places a `TL`'s numbers appear.

### 15.2 The three card rules the row exposes

* **A crossed line is a NEGATIVE `z0`.** The row echoes `|z0|` and says
  `CROSSED`; `-450.` prints as `4.5000E+02`. Right-aligned in the same nine
  columns, so the row is ` …  CROSSED` (two spaces) against ` … STRAIGHT`
  (one). Physically it is port B's polarity inverted — the off-diagonal
  transfer terms change sign, the diagonal self terms do not — which is
  `network.TL(transposed=True)` and `nec_import.NecTL.transposed`.
* **Length `0` means the straight-line distance between the connection
  points** (the segment CENTRES), and the row echoes the RESOLVED number.
  Probed directly: `TL 1 5 2 5 600. 0. …` between wires 1 m apart prints
  `6.0000E+02  1.0000E+00`.
* **The end admittances shunt onto the diagonal** (`Y11 += y_end1`,
  `Y22 += y_end2`), which is the only way a `TL` contributes `NETWORK LOSS`.
  An ideal line is a pure reactance chain: `dipole_tl_network` reports
  `NETWORK LOSS = -6.0715E-18 Watts` and 100 % efficiency, while
  `dipole_tl_shunt_crossed`'s conductive ends take `9.0220E-04` of `4.2873E-03`
  W (78.96 %).

### 15.3 One banner, a header block **per row kind**

nec2c carries the previous row's kind and re-prints the matching column header
whenever it changes, so a deck mixing the two shows two header blocks under one
banner, interleaved in **card order**. Straight and crossed lines are one kind
and share a block. From `dipole_tl_shunt_crossed.out` (`TL` then `NT`):

```
                                            ---------- NETWORK DATA ----------
  -- FROM -  --- TO --      TRANSMISSION LINE        --------- SHUNT ADMITTANCES (MHOS) ---------   LINE
  TAG   SEG  TAG   SEG    IMPEDANCE      LENGTH     ----- END ONE -----      ----- END TWO -----   TYPE
  No:   No:  No:   No:         OHMS      METERS      REAL      IMAGINARY      REAL      IMAGINARY
    1     5    2    14   4.5000E+02  3.0000E+00   1.0000E-03  2.0000E-03   3.0000E-03 -4.0000E-03  CROSSED
  -- FROM -  --- TO --            -------- ADMITTANCE MATRIX ELEMENTS (MHOS) ---------
  TAG   SEG  TAG   SEG   ----- (ONE,ONE) ------   ----- (ONE,TWO) -----   ----- (TWO,TWO) -------
  No:   No:  No:   No:      REAL      IMAGINARY      REAL     IMAGINARY       REAL      IMAGINARY
    2    14    3    23   0.0000E+00  5.0000E-03   0.0000E+00 -5.0000E-03   0.0000E+00  5.0000E-03
```

Writing the same two cards the other way round emits the `NT` header first.
There is **no** blank line between the blocks.

### 15.4 `STRUCTURE EXCITATION DATA` row order, generalised

§12.5 recorded "the far end first" from the one `NT` fixture. The real rule
(nec2c's `netwk()`) is a two-list sort done while walking the cards: a
connection point that is **not** also an excitation segment goes on one list,
one that **is** goes on the other, and the first list prints before the second.
Within each, order is discovery — card by card, end one before end two.

That reproduces `dipole_nt_network` unchanged (`NT 1 5 2 5` driven at 1/5 →
`(2,14)` then `(1,5)`) and is the only reading that gets a mixed deck right:
`dipole_tl_shunt_crossed` prints `(2,14)`, `(3,23)`, `(1,5)` — the `TL`'s far
end, then both `NT` ends, then the driven `TL` end last. The list is
per-execute-group, because the excitation set is.

### 15.5 What the engine does with it

`src/antennaknobs/nec_portal.py` stamps each `TL` as
`network_reduce.tl_admittance_2x2(|z0|, length, λ, transposed=crossed)` plus
the end admittances on the diagonal — antennaknobs' own TL branch, the closed
form its composition oracles are written against — rebuilt **per frequency**,
because unlike an `NT` the card's admittance depends on βl. Everything else is
the `NT` path unchanged: the endpoints become gaps, an undriven one floats on a
KCL row, and `ANTENNA INPUT PARAMETERS` reports segment + branch current.

The one refusal left inside `TL`: an exactly-lossless **k·λ/2** line has no
admittance matrix at all (`sinh γl = 0` — it is a through-connection the nodal
description cannot spell), and nec2c's `netwk()` divides by the same `sinh`.
That is named on the error path rather than printed as infinities. A line a
part in 10⁷ off length is large but finite and prints normally.

Cross-engine agreement (`tests/test_nec_portal_differential.py`):
`dipole_tl_network` 0.27 % on Z and port current, `dipole_tl_shunt_crossed`
1.14 % — both inside the ordinary 5 % bar, no widening. One trap is worth
carrying forward: a quarter-wave line is an impedance INVERTER, and two
branches across the *same* pair of gaps make a loop whose port admittance is a
residual. The first draft of `dipole_tl_shunt_crossed` hung its `NT` back
across the `TL`'s own pair and measured 6.6 % for a printout that looks
identical; chaining the `NT` onto a third dipole dropped it to 1.14 %.

### 15.6 Still open after #799

§14.5 minus `TL`: `processResponse`'s missing timeout, `MATRIX_LINE`,
`checkNEC42Fields`, `processExcitation`'s caller, patch/surface support, the
multi-point-`FR` blank lines, `PT`/`MP`/`IS` printout layouts, `RP` modes 1-6,
spherical `NE`/`NH`, and the `FieldStore` gain-vs-directivity convention.
(`PT` and `MP` came off this list in §16; the live open list is §16.6.)

## 16. Resolved by issue #800 — the `MP` and `PT` printout layouts

Two of the three cards left on §15.6's list. `IS` stays deferred (§16.6).

### 16.1 `MP` is an ae6ty extension, and SimNEC emits it by itself

`MP` is not a stock NEC-2 card. `nec2/NECSource.constructNECFile` writes it
from the format string

```
MP %d %d\n
```

with the two integers taken from `NEC2PortalDialog.getMPInfo()[1]` and `[2]` —
the last two fields of the `necMP #segs #Proc blockSize` preference, whose
default is `256 16 32`. So the card is **`MP <#Proc> <blockSize>`**, two
integer fields and nothing else. Fractional fields are refused by the oracle:

```
  COMMAND DATA CARD "MP" ERROR:
  NON-NUMERICAL CHARACTER '.' IN INTEGER FIELD AT CHAR. 5
```

The emission condition, read off the same method's bytecode, is the important
part:

```java
totalSegments += wire.numSegments;        // over Task.allWiresForNEC()
...
if (necEngine == NECEngine.NEC2C && totalSegments >= getMPInfo()[0])
    deck.append(String.format("MP %d %d\n", info[1], info[2]));
deck.append(String.format("FR 0 1 0 0 %s 1\n", freq));
```

**Nobody asks for it.** It arrives on structure SIZE — 256 segments by
default — and it arrives immediately before the `FR` card. Any array past that
threshold therefore reaches the engine carrying one in ordinary use, which is
why refusing the card refused exactly the decks worth running.

It is also a *data* card, not a geometry one: `MP` before `GE` is a
`GEOMETRY DATA CARD ERROR(3)`.

### 16.2 What `MP` changes in the printout: one line

`dipole_mp_multiprocessor` is `dipole_free_space`'s deck with `MP 16 32`
inserted. The entire diff:

```diff
-  DATA CARD No:   2 FR   0     1     0     0  3.00000E+01  ...
-  DATA CARD No:   3 XQ   0     0     0     0  0.00000E+00  ...
+  DATA CARD No:   2 MP  16    32     0     0  0.00000E+00  ...
+  DATA CARD No:   3 FR   0     1     0     0  3.00000E+01  ...
+  DATA CARD No:   4 XQ   0     0     0     0  0.00000E+00  ...
                             -------- ANTENNA ENVIRONMENT --------
                             FREE SPACE
+MP: multiProcessor 16 32
+
-  DATA CARD No:   4 NX   0     0     0     0  0.00000E+00  ...
+  DATA CARD No:   5 NX   0     0     0     0  0.00000E+00  ...
```

That is all of it: the ordinary four-integer/six-real card echo, and one line
at **column 0** immediately after the whole `ANTENNA ENVIRONMENT` block —
after the `COMPLEX DIELECTRIC CONSTANT` row over a finite ground, checked
separately — carrying **one blank line of its own**, so a multiprocessing run
shows three blanks before `MATRIX TIMING` where a plain one shows two. Every
number in the run is byte identical. (`FILL`/`FACTOR` differ run to run and are
canonicalised by the capture script, as always.)

The line reprints in **every block that rebuilds the matrix**, so a three-point
`FR` sweep shows it three times, and a second `XQ` under the same `FR` — which
prints no preamble at all — shows it zero more times.

`MP` does **not** arm an execute card: `… XQ / MP 4 8 / XQ` runs once.

### 16.3 The advisory's threshold is an unsigned comparison

Measured, holding `blockSize` irrelevant throughout:

| card | `MP: multiProcessor` line |
| --- | --- |
| `MP 0 32`, `MP 0 0`, bare `MP` | no |
| `MP 1 32`, `MP 1 0` | no |
| `MP 2 0`, `MP 2 1`, `MP 16 32` | yes |
| `MP -1 32`, `MP -2 32`, `MP -3 -9` | **yes** |

So it is not `#Proc >= 2`. `{0, 1}` are silent and everything else prints,
which is what a C `if (nproc > 1)` on an **unsigned** field does — and the same
unsigned reading is the likeliest cause of the other measured fact:

> **A negative `#Proc` hangs the oracle.** `MP -1 32` and `MP -3 -9` print
> their advisory line and then spin forever; both runs had to be killed
> (SIGTERM at 12 s and 25 s). Since `Execute.processResponse` blocks in
> `readLine()` with no timeout (§2, §10.1), a deck with a mistyped `MP` would
> hang the SimNEC UI outright.

### 16.4 What this engine does with `MP`

Parses it, echoes it, reproduces the advisory line and its blank, and **ignores
`#Proc` and `blockSize`**.

That is not a shortcut, it is the faithful reading. The card describes how the
oracle fills and factors its matrix; it is not physics, and the fixtures prove
it — both `MP` captures reproduce `dipole_free_space`'s numbers to the digit,
on the oracle's side and ours (asserted in
`test_nec_portal_differential.py::test_mp_moves_no_number_on_either_engine`).
momwire's parallelism is decided elsewhere and earlier: the BLAS/OpenMP pools
behind numpy, scipy and pynec_accel are configured once per process at import
time through `threadpoolctl` (see `web/server.py`'s thread-policy block and
issue #377 — environment pins applied after the package `__init__` are already
too late, because every pool snapshots its environment at load). A per-deck
card arriving on stdin cannot reach back into that decision, and honouring it
would mean re-limiting live pools mid-solve for a hint the sender never meant
as a request.

A hostile field is harmless here for the same reason: `MP -3 -9` is echoed,
annotated, and solved through.

### 16.5 `PT` is a toggle on one table — and nothing else

`PT` looked entangled with an excitation this engine does not model, because
SimNEC only ever emits it inside the `planeWaveExcitation` branch of
`constructNECFile`:

```
EX 1 …          (plane wave)
PT -1
XQ
PT -2
```

It is not entangled at all. Diffed against the same deck carrying no `PT`, the
card touches `CURRENTS AND LOCATION` and leaves every other section — the data
card echoes aside — byte identical.

**`PT -1`** removes the *whole section*: banner, `DISTANCES IN WAVELENGTHS`
note, blank, both column-header lines and every row. What is left in its place
is Ward's `-YY` report, printed immediately after the last
`ANTENNA INPUT PARAMETERS` row with **no blank between them**:

```
    1     5  1.0000E+00  0.0000E+00  9.5048E-03 -5.4414E-03  …
    -YY  9.5048E-03 -5.4414E-03


                               ---------- POWER BUDGET ---------
```

That the `-YY` line survives is the load-bearing detail: it is the row
`addYYLine` parses (§6), so a suppression that swallowed it would break the Y
path on exactly the decks SimNEC suppresses.

**`PT -2`** restores the table, and it is a *state change*, not a per-run flag:
`dipole_pt_toggle` suppresses its first run and restores its second from one
deck. Like `MP`, `PT` does not arm an execute card.

**`PT 0 <tag> <first> <last>`** keeps the table and prints only those segments,
addressed exactly as an `EX` card addresses one — tag-relative, `tag = 0`
meaning absolute segment numbers:

| card (two 9-segment wires) | rows printed (seg/tag) |
| --- | --- |
| `PT 0 2 1 3` | `10/2 11/2 12/2` |
| `PT 0 0 3 5` | `3/1 4/1 5/1` |
| `PT 0 1 0 0`, `PT 0 2 0 0` | all 18 |

So an all-zero range is "no restriction", not "no rows".

**`PT 1`, `PT 2`, `PT 3`** are stock NEC-2's receiving-pattern and
normalised-current formats. This ae6ty build prints the ordinary full table for
all three (and for `PT -2`), diffed byte for byte against the card-free deck —
so the whole card reduces to one boolean and one segment range.

Two fixtures pin it: `dipole_pt_toggle` (both halves of the toggle, with a `YY`
card so the surviving `-YY` row is visible) and `dipole_pt_segment_range`
(`PT 0 2 1 3`).

### 16.6 Still open after #800

§15.6 minus `PT` and `MP`: `processResponse`'s missing timeout, `MATRIX_LINE`,
`checkNEC42Fields`, `processExcitation`'s caller, patch/surface support, the
multi-point-`FR` blank lines, `IS`, `RP` modes 1-6, spherical `NE`/`NH`, and
the `FieldStore` gain-vs-directivity convention.

`IS` stays deferred on purpose rather than for want of a capture. The card is
`IS 0 <tag> <first> <last> <eps_r> <thickness>` (`NECSource` writes it as
`"IS 0 %d %d %d  %e %e %e\n"` out of `Wire.getInsulation`), and it is NEC-4.2
insulated-wire semantics — a distributed sheath changing the propagation
constant along the wire, which momwire has no model for. Running such a deck as
a bare wire would be a wrong answer rather than a refusal, so it keeps the error
path. It is now the only card the portal dialect can carry that this engine
declines; it is also the live example in
`test_an_unsupported_card_still_emits_the_sentinel`.

The plane-wave `EX 1 …` excitation `PT` used to be lumped with remains
unsupported and unchanged: `EX` type != 0 is refused by name.

## §17 — EK, found the hard way (the first live-session failure)

The live `NECSource` path ALWAYS emits a bare `EK` (format string `"EK\n"`,
confirmed in the jar) — a card in none of the PDF's lists and none of the
first 36 fixtures, so the daemon refused every live deck and SimNEC
fabricated readouts from the failures (Windows session, 2026-08-08:
"NEC Failure Code 1", rig Z read 4−j280 vs the real ~40−j5.7).

Pinned behaviour (fixtures `dipole_ek_extended`, `dipole_ek_rearm`):

- The card's one field is tested for `-1` and for nothing else: `EK`, `EK 0`,
  `EK 1`, `EK 2` and even `EK -2` all turn the extended thin-wire kernel ON,
  and only `EK -1` turns it off (re-measured on 5b4az.ae6ty.1.23, 2026-08-10;
  it is NEC-2's own card reader — `nec2dx.f` sets `IEXK = 1` on an EK card and
  clears it for `ITMP1 = -1` alone). Echoed as a normal DATA CARD line.
  This engine refused anything outside `{0, -1}` until issue #849 — the same
  failure class as #814, a deck the reference engine runs turned into a
  fabricated SimNEC readout by our refusal.
- When on at a full (FR-driven) preamble: one extra line, 24-space indent,
  `THE EXTENDED THIN WIRE KERNEL WILL BE USED`, directly after the
  APPROXIMATE INTEGRATION note.
- A kernel CHANGE between execute cards arms a re-execution with a PARTIAL
  refill preamble: LOADING / ENVIRONMENT / MATRIX TIMING but no FREQUENCY
  block and no announcement.
- That re-execution also corrected a §11 rule: NEC RETAINS excitation
  across an execute card — `dipole_ek_rearm`'s second AIP repeats the
  retained source. The first EX after an execution replaces the set;
  §11's "cleared at every XQ" described decks that always supplied
  fresh EX cards, not the engine.
- ~~For momwire the kernel choice is advisory (our kernel is our own);
  layout is reproduced exactly, values are ours.~~ **Superseded by issue
  #849 (momwire 0.26.0).** The card is HONOURED: the solver an execute group
  is answered from is built with `extended_kernel=True`, momwire's own O(a²)
  on-axis tube expansion (momwire#249/#259/#269/#270). Consequences worth
  writing down:
  - It is per EXECUTE GROUP, not per deck, and the per-deck fill cache is
    keyed on `(frequency, kernel)` accordingly — `dipole_ek_rearm` is one
    deck, one frequency, two operators.
  - Magnitude: nothing, on any deck in the fixture corpus. Every committed
    EK deck is `Δ/a ≈ 500`, where the correction measures 0.017 %. On a
    `Δ/a = 2.27` wire both engines move ~8 %, and momwire's reduced answer
    is 0.5 % from nec2c's while its extended answer is 3.1 % from nec2c's.
  - **The two Galerkin portal entries cannot serve a live SimNEC session.**
    momwire#246 leaves the extended kernel unimplemented on the Galerkin
    fill, and `NECSource` sends `EK` on every deck, so `--basis
    sinusoidal-galerkin[-converged]` now refuses every live deck with a
    named `ERROR:` frame (and its NX sentinel). That is deliberate — the
    alternative is serving a reduced-kernel answer under an extended-kernel
    request — but it means those two dialog entries are bench instruments
    rather than session engines until momwire#246 lands. `--basis
    sinusoidal` is the point-matched sibling that does carry EK.
- Build note: the 1.17 corpus oracle aborts noisily at EOF after the last
  NX ("Error reading input file") — post-sentinel noise, also present in
  pre-EK fixtures, harmless to `Execute` which stops at the sentinel.

## §18 — GD, the second-medium card SimNEC's EZNEC examples carry

The second live-session refusal, and the same shape as §17: SimNEC's
EZNEC-derived examples — `Cardioid (EZNEC).ssn`, `4-square (EZNEC).ssn` —
carry a `GD` card, `NECSource` forwards it verbatim, and a daemon that
refused it failed every one of those decks with fabricated R = 0 / X = 0
readouts.

The live line is comma-delimited: `GD 2,0,0,0,13.,.005,0.,0.`, alongside
`GN 1`, `NT` cards and an `RP 3`.

### The fields, read off the oracle rather than a manual

`GD` is `GD <i1> <i2> <i3> <i4> <EPSR2> <SIG2> <CLT> <CHT>`. The four
integer columns are echoed and used by nothing (the Cardioid writes `2` in
the first, mirroring `GN`'s type field; a bare `GD` echoes four zeros and
runs identically). The four reals are:

| field | name    | meaning                                              |
| ----- | ------- | ---------------------------------------------------- |
| `F1`  | `EPSR2` | relative dielectric constant of the SECOND medium     |
| `F2`  | `SIG2`  | conductivity of the second medium, mhos/metre         |
| `F3`  | `CLT`   | distance from the origin to the edge joining the media |
| `F4`  | `CHT`   | height of medium 2's surface relative to medium 1's, signed |

That mapping is the oracle's own naming, recovered by running
`GD 0 0 0 0 5. .001 20. -2.` under `RP 2`, which prints:

```
                               ------ FAR FIELD GROUND PARAMETERS ------


                               --- LINEAR CLIFF ---
                               EDGE DISTANCE=     20.00 METERS
                                      HEIGHT=     -2.00 METERS
                               --- SECOND MEDIUM ---
                               RELATIVE DIELECTRIC CONST=      5.000
                                     GROUND CONDUCTIVITY=      0.001 MHOS
```

### What the card changes in the printout: its own echo, and nothing else

- One ordinary `DATA CARD No:` line, four integers then six `%13.5E` reals,
  the generic layout every data card gets. Comma- and space-delimited forms
  produce byte-identical output (measured).
- **No line anywhere in the `ANTENNA ENVIRONMENT` block.** Probed for
  explicitly under `GN 1` and under `GN 2`, where a "second medium"
  announcement was the likeliest place one would appear. There is none.
- **No change to any number.** Fixtures `dipole_gd_second_medium` and
  `dipole_gd_cliff_sommerfeld` are `dipole_pec_ground` and
  `dipole_sommerfeld_ground` plus one card; each printout differs from its
  base only in the echo and the card ordinals it shifts.
- **Not an arming card.** Measured: `... XQ / GD 2 0 0 0 13. .005 0. 0. /
  XQ` prints one block, not two — the same rule `MP` and `PT` follow (§16).
- A non-numeric field is where this engine deliberately parts company with
  the oracle: nec2c's free-format reader SKIPS the bad token and shifts the
  remaining fields left (`GD 2 0 0 0 marsh .005 0. 0.` echoes `.005` as
  EPSR2), which is a wrong answer dressed as a right one. This engine names
  the token on the ordinary error path and still emits the sentinel (§8).

### Fidelity — where the second medium WOULD matter

NEC-2 uses `GD` in the FAR FIELD alone; the moment method never sees it,
which is why every impedance and segment current is unchanged. In the far
field it is reached only through `RP`'s cliff and ground-screen modes.
Measured both ways with the cliff card above:

- `RP 0` — the only mode `nec2/NECSource` ever writes, and the only one this
  engine computes — the `RADIATION PATTERNS` table is **byte-identical** with
  and without the card;
- `RP 2` (linear cliff) — the `FAR FIELD GROUND PARAMETERS` block above
  appears and every gain moves.

So the deck shapes in which `GD` is inert are exactly the deck shapes this
engine runs, and the shapes in which it is not are already refused by name at
the `RP` card (`RP mode <n> is not supported`, issue #802). Accepting `GD`
therefore cannot make this engine answer a cliff question as if the ground
were flat — it never gets asked one. A `GD` deck whose `RP` is mode 3, like
the Cardioid's, still refuses on the `RP`, which is correct until #802 lands.

Corpus 38 -> 40; layout gate 40/40.

---

## Addendum 2026-08-09 — the versionNECd path, traced (issue #828)

Ward's reply (2026-08-08) sanctioned probing as `NEC2text#.#`; a full bytecode
trace of the 5.1a0 jar (CFR + `javap -c -p`, plus executing the four verbatim
patterns under Java 21) settled the questions §1 and item 11 left open. The
portal now probes as `NEC2momwire.<major>.<minor>` (`--legacy-probe` restores
the old versionA masquerade).

**The versionNECd branch sets no state.** `Execute.testCommand`'s NECd match
is `setVersion(line); return null` — `Matcher.group` is never invoked
(offset 436–460: no `group`, no `Double`), so nothing is Double-parsed and
`minimumNEC2CVersion` (1.23) is read only inside the shared A/B/C branch.
Case-sensitive, `lookingAt()`-anchored; the character after the digit run
must be a non-digit (`NEC\d+\D.*`).

**The engine enum comes from the filename alone.** The jar's only
`putstatic necEngine` is in `NEC2PortalDialog.safeNecCommand()`:
`indexOf("nec2c")` → `NEC2C`, else `nec5` → `NEC5`, else `nec42` → `NEC42`,
else the *NO NEC Command Available* refusal. Every daemon choice
(`Workforce.eval`, `manageCrew`, `NewLocalConsumer.run`) tests
`necEngine == NECEngine.NEC2C` → `NEC2Daemon` (stdin/stdout NX residency);
anything else → the file-based `NEC5Daemon`. The probe response cannot reach
any of it. Enum ctor args decoded: `samplesWidth` (sensor-row token count,
11 for NEC2C), `samplesOffset` (index of Re(I), 4), `thetaFirst` (NEC4/5
near-field angular convention, false).

**One consumer parses the stored version text**: `Options.getEngine()`
(`[a-zA-Z]*([0-9])+?(.*)`) — group(1) must be `"2"` or the scripting layer
reclassifies the engine (`Insulation`'s `W7EL` gate requires `Complex.TWO`;
NEC5-only source placements test for 5). `NEC2momwire.…` and
`nec2c.ae6ty.9.1` both yield `"2"`.

**Where the text surfaces**: the portal dialog's `NECVersion` row, a
`CM version <text>` comment card `NECSource` prepends to every deck, and the
saved-circuit XML via `toXMLLikeWorker`.

**Corrections to the body above**:
- §1's `versionB // <- what we ship` annotation described the *oracle*;
  `nec_portal.py` shipped versionA's shape (`nec2c.ae6ty.9.1`) through
  v0.46, and rides versionNECd from #828 on.
- A first line matching *no* regex is not an error: `testCommand` falls
  through to `setVersion(rawCommand); return null` — the probe was never
  load-bearing for acceptance, only a matching-but-unparseable A/B/C tail
  can refuse.
- Item 11 (the engine name a replacement may claim) is resolved by the
  above; the printout banner remains unparsed by the live protocol (the only
  `NUMERICAL ELECTROMAGNETICS CODE (nec2c)` regex in the jar is
  `ae6ty/FileStuff`, the offline `.out` import), so `BANNER_VERSION` stays
  fixture-pinned on purpose.
- One more filename trap found beside the `nec2c` rule: `testCommand`
  refuses any command whose full path contains the substring `out`
  ("Can't execute 'out' file:").

---

## Addendum 2026-08-09 — the `RP` cliff modes, measured (issue #802)

§12.6's fidelity note closes with "the shapes in which it is not are already
refused by name at the `RP` card... which is correct until #802 lands". It has
landed. Nothing measured above is retracted; this extends it. The pressure was
Ward's: the notes doc sent 2026-08-08 named "`RP 3` — where those examples'
cliff parameters actually land" as the remaining gap, and user-pasted decks
reach the portal even though the dialog itself only ever writes `RP 0`.

Captured against the same binary as the rest of the corpus
(`/home/smburns/.SimNEC/2/3/…/nec2c-ubuntu-x86`, `VERSION:5b4az.ae6ty.1.17`).
A newer build ships under SimNEC 5/1 (`5b4az.ae6ty.1.23`); it was deliberately
NOT used, because a corpus captured against two vintages cannot be diffed.

### The mode field, from NEC-2's own source

The cliff is not inferred from the printout. It is read out of the original
NEC-2 FORTRAN — a US government work in the public domain — specifically
`nec2dx.f` (NEC-2D, Lawrence Livermore National Laboratory, "FILE CREATED
4/11/80", double-precision revision 6/4/85), `SUBROUTINE FFLD`, cross-checked
against the single-precision `nec2-1.2.1.2.f` of the same lineage (the two
agree statement for statement across this block). `IFAR` in `COMMON /GND/` is
the `RP` card's `I1`, assigned at label 36 of the main program's card reader:

| `I1` | what it does in `FFLD` | here |
| --- | --- | --- |
| 0 | one reflection coefficient for the whole image sum | runs |
| 1 | `GFLD` instead of `FFLD` — a different banner and row shape | refused |
| 2 | linear cliff: medium chosen per segment against `x = CLT` | **runs** |
| 3 | circular cliff: same, against `r = CLT` | **runs** |
| 4 | radial screen: surface impedance `T1*D*LOG(D/T2)` | refused |
| 5 | screen, then a LINEAR cliff beyond `SCRWL` | refused |
| 6 | screen, then a CIRCULAR cliff beyond `SCRWL` | refused |

The screen's surface impedance is theory-manual `Z_g(ρ) = jμ₀ωρ/N·ln(ρ/NC₀)`
(Part I §IV.3, p. 59); the Fresnel pair `FFLD` builds `RRV`/`RRH` from is
eqs. 179–180 with `ZRATI = 1./SQRT(EPSC)` the `Z_R` of eq. 179, composed onto
the image by eq. 181.

### What the cliff actually is

Per SEGMENT and per DIRECTION, not per antenna. For a segment at height `z`,
`FFLD`'s own statements (`TTHET=TAN(THET)`, `PHX=-SIN(PHI)`, `PHY=COS(PHI)`,
`ROZ=COS(THET)` are set at the head of the routine):

```fortran
   11 DR= Z(I)* TTHET                         specular distance along the ray
      D= DR* PHY+ X(I)                        RP 2 — the abscissa alone
      IF( IFAR.EQ.2) GOTO 13
      D= SQRT( D* D+( Y(I)- DR* PHX)**2)      RP 3 — the radius
   13 IF(( CL- D).LE.0.) GOTO 15               beyond the edge?
   14 RRV= RRV1                                medium 1
      RRH= RRH1
      GOTO 16
   15 RRV= RRV2                                medium 2 ...
      RRH= RRH2
      ARG= ARG+ DARG                           ... and the extra path
```

with `DARG=-TP*2.*CH*ROZ` set once per direction (`TP` = 2π, `CH = CHT/WLAM`),
i.e. `-2k·CHT·cos(theta)`, and `CL = CLT/WLAM` set in `RDPAT`. `PHX = -sin(phi)`
is why the circular radius reads `Y(I) - DR*PHX` rather than a plus.

Three consequences worth recording:

1. **The medium switch is a discrete per-element choice**, so the two engines
   partition different meshes near the crossing angle. This was the expected
   source of a several-dB grazing error and it did not materialise: over both
   cliff fixtures every row at theta >= 50 agrees to a constant **-0.070 dB**,
   the same offset as the rows where no element crosses at all.
2. **`GN` carries a second medium too.** The main program's `GN` branch
   (label 23) writes `EPSR2`/`SIG2`/`CLT`/`CHT` in `COMMON /FPAT/` from
   `F3`-`F6` whenever `NRADL` is zero — the same four slots the `GD` branch
   (label 34) writes, and it reaches them only because `IF (NRADL.EQ.0) GO TO
   23` skips the screen assignment. A deck can therefore state a whole cliff
   without ever sending a `GD`, and an engine watching only for `GD` would
   answer it as flat ground. Fixture `dipole_rp2_cliff_on_the_gn_card`.
3. **The block prints on the MODE, not on the card.** `RDPAT` emits
   `FAR FIELD GROUND PARAMETERS` on `IF (IFAR.LT.2) GO TO 2` alone, so a cliff
   mode with no second medium anywhere in the deck prints it with four zeros
   in it — and then divides by them:
   `ZRATI2=SQRT(1./DCMPLX(EPSR2,-SIG2*WLAM*59.96))` is infinite and the oracle's
   whole pattern table comes out `nan`. Measured, recorded, not reproduced;
   nothing here rescues a deck that asks for a cliff into vacuum.

### `RFLD = 0` — the gain-only form

Two shape changes, both in `RDPAT`, both hanging off the same guard
`IF (RFLD.LT.1.D-20)`:

- the `RANGE:` / `EXP(-JKR)/R:` pair (and the blank above it — three lines)
  sits behind the first one and simply is not printed;
- at label 26 the second one skips `ETHM=ETHM*EXRM` / `ETHA=ETHA+EXRA` (and
  the `EPH` pair), so the E columns carry `|E|*WLAM` rather than the field at
  a range. Measured ratio between the two forms of one deck: exactly `RFLD`.

### The two thresholds NEC-2 spells `1e-20`

They are different tests, and only an `RFLD = 0` deck separates them. §4.14
read the gain floor off `dipole_rp_pattern` and described both as one test on
the field at the requested range; `FUNCTION DB10` and `SUBROUTINE RDPAT` say
otherwise:

- `DB10(X)` — `IF (X.LT.1.D-20) ... DB10=-999.99` — is applied to the LINEAR
  POWER GAIN (`GNMJ=DB10(GCON*EMAJR2)` and its four siblings), which never
  depended on the range. The gain columns of an `RFLD = 0` table are identical
  to the same deck's at 1000 m.
- the polarisation block's
  `IF (ETHM2.GT.1.D-20.OR.EPHM2.GT.1.D-20) GO TO 11` — whose fall-through sets
  `ISENS=HBLK`, blanking `SENSE` and making a row 11 tokens instead of 12 — is
  applied to the field as `FFLD` returns it, at label 10, before the `*WLAM`
  and the `*EXRM` at label 26.

(`RDPAT` in fact spells `1e-20` four times: the two above, the `RFLD` guard of
the previous section, and `IF (ABS(GNOR).GT.1.D-20)` on the normalisation
factor. Only the first two decide row shape, which is why §4.14 conflated
exactly those.)

At one range and one wavelength the two coincide, which is why 40 fixtures did
not notice. §4.14's 11-vs-12-token rule is unaffected; only its stated
threshold basis is corrected.

Corpus 40 -> 45; layout gate 45/45. New fixtures:
`dipole_rp2_linear_cliff`, `dipole_rp3_circular_cliff`,
`dipole_rp3_cliff_sommerfeld`, `dipole_rp2_cliff_on_the_gn_card`,
`dipole_rp_gain_only`. The existing 40 re-captured byte-identical.
