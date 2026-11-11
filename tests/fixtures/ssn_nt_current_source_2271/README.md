# AK#2271 fixture — a station chain on EZNEC's current-source idiom

`dipole-nt-isrc-line.ssn` is SYNTHETIC, written by hand in SimNEC's element
shape (only the tags the importer reads). Every value is invented.

- NETWORK `A`: a NEC-2 block with a 20.4 m, 11-segment dipole 12 m over
  `SommerfeldGround(0.005, 13)` at 7.1 MHz, and EZNEC's NEC-2 current-source
  idiom: a one-segment wire 2 parked 1800 m out carries `EX 0,2,1,0,0.,1.`,
  and `NT 2,1,1,6,0.,0.,0.,1.,0.,0.` is the gyrator (Y11 = Y22 = 0,
  Y12 = j) from it to the dipole's centre segment.
- SERIES_TLINE `T1`: 15 m, 50 ohm, VF 0.66, `k0k1k2` with all three zero
  (lossless), so the test's oracle is the textbook line equation.
- GENERATOR `G`: 7.1 MHz, Zo 50.

`tests/test_simnec_nt_current_source_2271.py` derives the control (the EX
directly on segment 6, no parked wire, no NT) and the two-source refusal
from this text.
