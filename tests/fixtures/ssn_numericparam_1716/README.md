# AK#1716 fixtures — the circuits that drive element-parameter knobs

Byte-exact copies of two circuits Dan Maguire (AC6LA) sent on 2026-09-24
(received as `DipoleVarLen.ssn.txt` / `DipoleVarLenSegs.ssn.txt`). Both were
saved by SimNEC 5.4a4 (`<XMLVersionControl>`). They are LF-only ASCII, so
unlike the AK#1714 fixtures they need no `-text` entry in `.gitattributes`.

| file | sha256 |
|---|---|
| `DipoleVarLen.ssn` | `792255daf9bec6833bbbfd343bd23c494ff82383e2d8b4d5fd1c29c9f3e60412` |
| `DipoleVarLenSegs.ssn` | `e262881e15155a8d27f8dfa7d84c421062b206e0c1d5bfd9cc6b9d78749ba2f9` |

Both are a one-wire dipole whose length is a bare name in the GW card. The
script names it in a statement of its own (`len;`), with no `dcl` and no
`$`, so SimNEC made it a parameter of the NETWORK element (SimNEC Manual,
"Adding a Parameter to the circuit Element") and saved its value on the
element: `<p><numericParam>len</numericParam><v>10.2</v>...</p>`.

What each one exercises:

- `DipoleVarLen.ssn` — `len;` above `NEC2`, `GW 1 11 0. 0. 9. 0. len 9.
  0.001`, `len` = 10.2 on the element, `$GW_1.JamSegments(30);`, and
  `NECOptions.mhosPerMeter = Conductivities.copper;`.
- `DipoleVarLenSegs.ssn` — the same plus `segs;`, `segs` = 30 on the element,
  and `$GW_1.JamSegments(segs);`: a parameter that reaches a directive (the
  wire's segment count) rather than a card.
