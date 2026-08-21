# EZNEC -> NEC-5 capture corpus

- captures: **124**
- decks emitting `TL`: **47** / 124
- decks emitting `NT`: **18** / 124

## Headline verdict (momwire#390)

**TL/NT ride the deck.** EZNEC hands NEC-5 the transmission lines and networks as cards rather than solving them itself, so a momwire drop-in would have to solve networks -- against the antenna-only stance (#388).

## Card vocabulary

| card | occurrences | decks |
| --- | --- | --- |
| `GW` | 737 | 124 |
| `TL` | 160 | 47 |
| `EX` | 154 | 124 |
| `LD` | 149 | 41 |
| `EN` | 124 | 124 |
| `FR` | 124 | 124 |
| `GE` | 124 | 124 |
| `PQ` | 124 | 124 |
| `GN` | 74 | 74 |
| `RP` | 60 | 60 |
| `XQ` | 55 | 55 |
| `GD` | 50 | 50 |
| `NT` | 29 | 18 |
| `NE` | 8 | 8 |
| `NH` | 1 | 1 |

## Per-run

A frequency sweep is one engine launch per point, so consecutive captures that differ only in the `FR` frequency are collapsed into a single row.

| captures | model | freq (MHz) | TL | NT | cards | exit |
| --- | --- | --- | --- | --- | --- | --- |
| 0000 | Cardioid - L Network Feed | 7.15 | YES | YES | EN EX FR GD GE GWx3 LDx4 NT PQ RP TLx2 | (unobserved) |
| 0001 | 4-square array w/feed system | 7.15 | YES |  | EN EX FR GD GE GWx5 LDx3 PQ RP TLx6 | 0 |
| 0002–0009 (8×) | 4-square array w/feed system | 7.15–7.5 | YES |  | EN EX FR GD GE GWx5 LDx3 PQ TLx6 XQ | 0 |
| 0010 | Dipole in free space | 299.7925 |  |  | EN EX FR GE GN GW PQ RP | 0 |
| 0011 | Dipole with coax feedline | 14. | YES |  | EN EX FR GE GN GWx5 PQ RP TL | 0 |
| 0012 | Network Connection Test | 299.7925 |  | YES | EN EX FR GE GN GWx4 LDx2 NTx2 PQ RP | 0 |
| 0013 | VHF Ground Plane | 146. |  |  | EN EX FR GE GN GWx5 PQ RP | 0 |
| 0014 | Network Connection Test | 299.7925 |  | YES | EN EX FR GE GN GWx4 LDx2 NTx2 PQ XQ | 0 |
| 0015 | Vertical over real ground | 7. |  |  | EN EX FR GD GE GW PQ RP | 0 |
| 0016 | Network Connection Test | 299.7925 |  | YES | EN EX FR GE GN GWx4 LDx2 NTx2 PQ RP | 0 |
| 0017–0018 (2×) | Network Connection Test | 299.7925 |  | YES | EN EX FR GE GN GWx4 LDx2 NTx2 PQ XQ | 0 |
| 0019 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW PQ XQ | 0 |
| 0020 | Vertical over real ground | 7. |  |  | EN EX FR GD GE GW PQ RP | 0 |
| 0021 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW PQ RP | 0 |
| 0022 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW NE PQ | 0 |
| 0023 | 4-Square Array - L Ntwk Feed | 7.15 | YES | YES | EN EX FR GD GE GWx5 LDx6 NT PQ RP TLx4 | 0 |
| 0024 | 4-square array w/feed system | 7.15 | YES |  | EN EX FR GD GE GWx5 LDx7 PQ RP TLx6 | 0 |
| 0025 | 4 Sq - L Ntwrk & Z Match | 7.15 | YES | YES | EN EX FR GD GE GWx5 LDx8 NTx3 PQ RP TLx4 | 0 |
| 0026 | Cardioid with feed system | 7.15 | YES |  | EN EX FR GD GE GWx3 LDx3 PQ RP TLx2 | 0 |
| 0027 | Cardioid with feed system | 299.7925 | YES |  | EN EX FR GE GN GWx3 LD PQ RP TLx2 | 0 |
| 0028 | 17-10m Log Per - ARRL Ant Book | 21. | YES |  | EN EX FR GE GN GWx6 LD PQ RP TLx5 | 0 |
| 0029 | Dipole with coax feedline | 14. | YES |  | EN EX FR GD GE GWx5 PQ RP TL | 0 |
| 0030 | Dipole with coax feedline | 14. | YES |  | EN EX FR GE GN GWx5 PQ RP TL | 0 |
| 0031 | 40-meter four-square array | 7.15 |  |  | EN EXx4 FR GD GE GWx4 PQ RP | 0 |
| 0032 | Cardioid | 299.7925 |  |  | EN EXx2 FR GE GN GWx2 PQ RP | 0 |
| 0033 | Elevated radial system | 1.832 |  |  | EN EX FR GE GN GWx5 PQ RP | 0 |
| 0034 | Elevated radial system | 1.832 |  |  | EN EX FR GE GN GWx44 PQ RP | 0 |
| 0035 | Five-element Yagi | 14.2 |  |  | EN EX FR GE GN GWx55 PQ RP | 0 |
| 0036–0042 (7×) | Dipole in free space | 299.793–299.8 |  |  | EN EX FR GE GN GW PQ XQ | 0,1 |
| 0043 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW PQ XQ | 0 |
| 0044 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW PQ RP | 0 |
| 0045 | Vertical over real ground | 7. |  |  | EN EX FR GD GE GW PQ RP | 0 |
| 0046 | Vertical over real ground | 7.01 |  |  | EN EX FR GD GE GW PQ XQ | 0 |
| 0047 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW PQ RP | 0 |
| 0048 | Vertical over real ground | 7.02 |  |  | EN EX FR GE GN GW PQ XQ | 0 |
| 0049 | 4-square array w/feed system | 7.15 | YES |  | EN EX FR GD GE GWx5 LDx7 PQ TLx6 XQ | 0 |
| 0050 | 4-square array w/feed system | 7.15 | YES |  | EN EX FR GD GE GWx5 LDx7 PQ RP TLx6 | 0 |
| 0051 | Cardioid with feed system | 7.15 | YES |  | EN EX FR GD GE GWx3 LDx3 PQ TLx2 XQ | 0 |
| 0052 | Cardioid with feed system | 7.15 | YES |  | EN EX FR GD GE GWx3 LDx3 PQ RP TLx2 | 0 |
| 0053 | Dipole with coax feedline | 14. | YES |  | EN EX FR GD GE GWx5 PQ TL XQ | 0 |
| 0054 | Dipole with coax feedline | 14. | YES |  | EN EX FR GD GE GWx5 PQ RP TL | 0 |
| 0055 | Dipole with coax feedline | 14. | YES |  | EN EX FR GE GN GWx5 PQ TL XQ | 0 |
| 0056 | Dipole with coax feedline | 14. | YES |  | EN EX FR GE GN GWx5 PQ RP TL | 0 |
| 0057 | Back yard dipole | 14. |  |  | EN EX FR GE GN GW PQ XQ | 0 |
| 0058 | Back yard dipole | 14. |  |  | EN EX FR GE GN GW PQ RP | 0 |
| 0059 | Back yard inverted vee | 14. |  |  | EN EX FR GE GN GWx2 PQ XQ | 0 |
| 0060 | Back yard inverted vee | 14. |  |  | EN EX FR GE GN GWx2 PQ RP | 0 |
| 0061 | Back yard dipole | 14. |  |  | EN EX FR GD GE GW PQ XQ | 0 |
| 0062 | Back yard dipole | 14. |  |  | EN EX FR GD GE GW PQ RP | 0 |
| 0063 | 15m Quad (Ant Book p. 12-2) | 21.2 |  |  | EN EX FR GE GN GWx8 PQ XQ | 0 |
| 0064 | 15m Quad (Ant Book p. 12-2) | 21.2 |  |  | EN EX FR GE GN GWx8 PQ RP | 0 |
| 0065 | Five-element Yagi | 14.2 |  |  | EN EX FR GE GN GWx55 PQ XQ | 0 |
| 0066 | Five-element Yagi | 14.2 |  |  | EN EX FR GE GN GWx55 PQ RP | 0 |
| 0067 | NBS Yagi (ANT. BOOK p. 18-7) | 50.1 |  |  | EN EX FR GE GN GWx3 PQ XQ | 0 |
| 0068 | NBS Yagi (ANT. BOOK p. 18-7) | 50.1 |  |  | EN EX FR GE GN GWx3 PQ RP | 0 |
| 0069 | W8JK with 0.1 - wavelength sp. | 21.2 |  |  | EN EXx2 FR GE GN GWx2 PQ XQ | 0 |
| 0070 | W8JK with 0.1 - wavelength sp. | 21.2 |  |  | EN EXx2 FR GE GN GWx2 PQ RP | 0 |
| 0071 | 17-10m Log Per - ARRL Ant Book | 21. |  |  | EN EX FR GE GN GWx24 PQ XQ | 0 |
| 0072 | 17-10m Log Per - ARRL Ant Book | 21. |  |  | EN EX FR GE GN GWx24 PQ RP | 0 |
| 0073 | 17-10m Log Per - ARRL Ant Book | 21. | YES |  | EN EX FR GE GN GWx6 LD PQ TLx5 XQ | 0 |
| 0074 | 17-10m Log Per - ARRL Ant Book | 21. | YES |  | EN EX FR GE GN GWx6 LD PQ RP TLx5 | 0 |
| 0075 | Field Day Special (Jun 84 QST) | 14.1 |  |  | EN EXx2 FR GE GN GWx2 PQ XQ | 0 |
| 0076 | Field Day Special (Jun 84 QST) | 14.1 |  |  | EN EXx2 FR GE GN GWx2 PQ RP | 0 |
| 0077 | Field Day Special (Jun 84 QST) | 14.1 |  |  | EN EXx2 FR GD GE GWx2 PQ XQ | 0 |
| 0078 | Field Day Special (Jun 84 QST) | 14.1 |  |  | EN EXx2 FR GD GE GWx2 PQ RP | 0 |
| 0079 | K5RP | 7. |  |  | EN EX FR GE GN GWx8 PQ XQ | 0 |
| 0080 | K5RP | 7. |  |  | EN EX FR GE GN GWx8 PQ RP | 0 |
| 0081 | N4PC Loop (CQ, Dec. 1990) | 14.1 |  |  | EN EXx2 FR GE GN GWx4 PQ XQ | 0 |
| 0082 | N4PC Loop (CQ, Dec. 1990) | 14.1 |  |  | EN EXx2 FR GE GN GWx4 PQ RP | 0 |
| 0083 | N4PC Loop (CQ, Dec. 1990) | 14.1 |  |  | EN EXx2 FR GD GE GWx4 PQ XQ | 0 |
| 0084 | N4PC Loop (CQ, Dec. 1990) | 14.1 |  |  | EN EXx2 FR GD GE GWx4 PQ RP | 0 |
| 0085 | VHF Ground Plane | 146. |  |  | EN EX FR GE GN GWx5 PQ XQ | 0 |
| 0086 | VHF Ground Plane | 146. |  |  | EN EX FR GE GN GWx5 PQ RP | 0 |
| 0087 | 4-Square Array - L Ntwk Feed | 7.15 | YES | YES | EN EX FR GD GE GWx5 LDx6 NT PQ TLx4 XQ | 0 |
| 0088 | 4-Square Array - L Ntwk Feed | 7.15 | YES | YES | EN EX FR GD GE GWx5 LDx6 NT PQ RP TLx4 | 0 |
| 0089 | 4 Sq - L Ntwrk & Z Match | 7.15 | YES | YES | EN EX FR GD GE GWx5 LDx8 NTx3 PQ TLx4 XQ | 0 |
| 0090 | 4 Sq - L Ntwrk & Z Match | 7.15 | YES | YES | EN EX FR GD GE GWx5 LDx8 NTx3 PQ RP TLx4 | 0 |
| 0091 | 40-meter four-square array | 7.15 |  |  | EN EXx4 FR GD GE GWx4 PQ XQ | 0 |
| 0092 | 40-meter four-square array | 7.15 |  |  | EN EXx4 FR GD GE GWx4 PQ RP | 0 |
| 0093 | Cardioid | 299.7925 |  |  | EN EXx2 FR GE GN GWx2 PQ XQ | 0 |
| 0094 | Cardioid | 299.7925 |  |  | EN EXx2 FR GE GN GWx2 PQ RP | 0 |
| 0095 | Cardioid - L Network Feed | 7.15 | YES | YES | EN EX FR GD GE GWx3 LDx4 NT PQ TLx2 XQ | 0 |
| 0096 | Cardioid - L Network Feed | 7.15 | YES | YES | EN EX FR GD GE GWx3 LDx4 NT PQ RP TLx2 | 0 |
| 0097 | 4-square array w/feed system | 7.15 | YES |  | EN EX FR GD GE GWx5 LDx3 PQ TLx6 XQ | 0 |
| 0098 | 4-square array w/feed system | 7.15 | YES |  | EN EX FR GD GE GWx5 LDx3 PQ RP TLx6 | 0 |
| 0099 | Cardioid with feed system | 299.7925 | YES |  | EN EX FR GE GN GWx3 LD PQ TLx2 XQ | 0 |
| 0100 | Cardioid with feed system | 299.7925 | YES |  | EN EX FR GE GN GWx3 LD PQ RP TLx2 | 0 |
| 0101 | Dipole with coax feedline | 14. | YES |  | EN EX FR GE GN GWx5 PQ TL XQ | 0 |
| 0102 | Dipole with coax feedline | 14. | YES |  | EN EX FR GE GN GWx5 PQ RP TL | 0 |
| 0103 | Elevated radial system | 1.832 |  |  | EN EX FR GE GN GWx5 PQ XQ | 0 |
| 0104 | Elevated radial system | 1.832 |  |  | EN EX FR GE GN GWx5 PQ RP | 0 |
| 0105 | Elevated radial system | 1.832 |  |  | EN EX FR GE GN GWx44 PQ XQ | 0 |
| 0106 | Elevated radial system | 1.832 |  |  | EN EX FR GE GN GWx44 PQ RP | 0 |
| 0107–0108 (2×) | Vertical over real ground | 7. |  |  | EN EX FR GD GE GW NE PQ | 0 |
| 0109–0110 (2×) | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW NE PQ | 0 |
| 0111 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW NH PQ | 0 |
| 0112 | Vertical over real ground | 7. |  |  | EN EX FR GE GN GW NE PQ | 0 |
| 0113 | Back yard dipole | 14. |  |  | EN EX FR GE GN GW NE PQ | 0 |
| 0114 | Back yard dipole | 14. |  |  | EN EX FR GE GN GW PQ RP | 0 |
| 0115 | Back yard dipole | 14. |  |  | EN EX FR GE GN GW NE PQ | 0 |
| 0116 | 40-meter four-square array | 7.15 | YES |  | EN EXx4 FR GD GE GWx4 PQ TL XQ | 0 |
| 0117 | 40-meter four-square array | 7.15 | YES |  | EN EXx4 FR GD GE GWx4 PQ RP TL | 0 |
| 0118 | Cardioid - L Network Feed | 7.15 | YES | YES | EN EX FR GD GE GWx3 LDx4 NT PQ TLx2 XQ | 0 |
| 0119 | Cardioid - L Network Feed | 7.15 | YES | YES | EN EX FR GD GE GWx3 LDx4 NT PQ RP TLx2 | 0 |
| 0120 | Cardioid - L Network Feed | 7.15 | YES | YES | EN EXx2 FR GD GE GWx3 LDx4 NT PQ TLx2 XQ | 0 |
| 0121 | Cardioid - L Network Feed | 7.15 | YES | YES | EN EXx2 FR GD GE GWx3 LDx4 NT PQ RP TLx2 | 0 |
| 0122 | NEC-4 Example | .0005 |  |  | EN EX FR GE GN GWx6 PQ XQ | 0 |
| 0123 | NEC-4 Example | .0005 |  |  | EN EX FR GE GN GWx6 PQ RP | 0 |

## Invocation

Observed command lines (the protocol a drop-in must accept):

- `"C:\EZNEC 7.0\Docs\NEC5CL_x13.exe" "EZN5.NEC" "NEC5.OUT"`
- `(unobserved) C:\EZNEC 7.0\Docs\NEC5CL_x13.exe`

- cwd: `(unobserved)`
- cwd: `C:\EZNEC 7.0\Docs`
