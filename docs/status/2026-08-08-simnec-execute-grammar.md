# SimNEC's `nec2/Execute` printout grammar — the contract a momwire engine must meet

Status doc for issue #792 ("momwire as a SimNEC engine"), unit 1.

This is the empirical contract later units are written against. Two independent
sources:

1. **The oracle.** `nec2c-ubuntu-x86` (banner `VERSION:5b4az.ae6ty.1.17`), the
   NEC-2 build SimNEC 2/3 ships under
   `~/.SimNEC/2/3/Examples/nec2c.ae6ty/bin/`. 28 deck/printout pairs captured
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
line. Fixture: `dipole_nt_network.out`.

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
behaviour, or half the pattern is read off by one column.

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
`tests/fixtures/nec_portal/` — 28 `<name>.deck` / `<name>.out` pairs plus
`manifest.json` (per-deck exit code, both SHA-256s, and the captured stderr).

* `jar_testdeck`, `jar_testdeck_daemon_framed` — the deck embedded in
  `nec2/NEC2Daemon`, raw and with the daemon's `CM FF 2` prefix.
* 15 hand-authored decks: free space, `FR` sweep, PEC / reflection-coefficient
  / Sommerfeld grounds, `LD 0` / `LD 4` / `LD 5`, `GS`, `GM`, `NT`, `RP`, `NE`,
  the 2-port sensor-line probe and the 2-port `YY` probe.
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
