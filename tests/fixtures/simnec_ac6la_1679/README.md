# AK#1679 fixtures — AC6LA's SimNEC circuits

Both files are Dan Maguire AC6LA's own SimNEC 5.1a1 circuits, attached to QRZ
thread 1003328 and copied here verbatim (only the first was renamed, from the
`.ssn.txt` the forum attachment needed back to `.ssn`):

- `snBydipole1-LC1.ssn` — post #142 (2026-09-22). The back-yard dipole behind
  a self-tuning XMATCH (`LC1`, low-pass, match at 14.175 MHz), with a
  Generator sweep given as the expression `14 : 14.35 : 0.025`.
- `Bydipole-TL-Xfmr-CLC.ssn` — post #143 (2026-09-23, from
  `Bydipole-TL-Xfmr-CLC.zip`). The same dipole with copper loss, fed through
  100 ft of 50 Ω line in SimNEC's `simplified` model (0.5 dB/100 ft at
  14.175 MHz), a compensating `SERIES_Z` (`R1`), an ideal 1:4 transformer
  (`N = 2`) and a CLC high-pass T. Post #144 reported that it failed to
  import because of `R1`.

Dan's unused terminating `LOAD` (`NotUsed`, 0 Ω) is in both files, as in
every SimNEC NEC-portal circuit.
