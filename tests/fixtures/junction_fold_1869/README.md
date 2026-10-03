# AK#1869 junction-fold decks

Three decks from the momwire#1300 investigation (`scratch/i1300-junction-series/`,
written by its `gen_decks.py`, 2026-10-03). Each keeps EZNEC's
"Written by ... in NEC-5 format" comment line, without which the importer reads
`EX 0,1,10,0` as NEC-2 (segment centre) addressing. Node addresses are
EZNEC-style: `tag,-1` is end 1, `tag,N` is end 2 of segment N.

| deck | what sits at the two-wire node | licensed NEC-5 Z (black box, printed) |
|---|---|---|
| `k2_fs_2ld.nec` | λ/2 dipole at 299.7925 MHz split into two GWs at its centre; EX at 1,5; LD 50 Ω at 1,10 and LD j100 Ω at 2,-1 | 508.53 + 183.66j (= one 50+j100 load at 1,10) |
| `k2_fs_ex2_ld50w1.nec` | the same dipole; EX at 2,-1 and LD 50 Ω at 1,10 | 130.87 + 37.992j (no load: 80.865 + 37.992j) |
| `bur_2ld.nec` | Dan's #182 buried-radial screen; EX at 1,1, LD 50 Ω at 1,-1 and LD j100 Ω at 6,-1 (the z = 0 node) | 125.36 + 102.36j (= one 50+j100 load at 1,-1) |
