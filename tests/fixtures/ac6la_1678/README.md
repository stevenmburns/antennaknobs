# AK#1678 fixtures — the two designs AC6LA switched to NEC-2

Both are Dan Maguire AC6LA's own files from QRZ thread 1003328, copied here
verbatim:

- `dan118-eznec-lnet.nec` — post #118. EZNEC/Pro+ 7.0's NEC-5-format deck of
  the back-yard dipole behind an L network, written as an `NT` on EZNEC's
  virtual-segment wire and driven by an `EX 4` current source on it. Imported,
  the L network is a two-port `Admittance` between the virtual port and the
  feed, which only the multiport-Y route solves.
- `snBydipole1-C1-L1.ssn` — post #140 (from `snBydipole1s-5.1a1.zip`). The
  same dipole behind SimNEC's C1 / L1 L-match (`731.9n` / `37.52p` / `2K`
  in SimNEC's suffixes). Imported, it is a series `TwoPort` from the rig to
  the feed and a `Shunt` at the feed.

Post #140 reported that switching the solver from NEC-5 to NEC-2 on either
design raised "a NEC-2 deck cannot express TL/virtual-driver networks ... The
NEC-5 deck cannot express them either", one click after NEC-5 had solved it.
