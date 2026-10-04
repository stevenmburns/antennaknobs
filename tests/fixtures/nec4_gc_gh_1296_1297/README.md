# NEC-4 GC and GH layouts (AK#1296, AK#1297)

Each `.out` is the printout of the `.nec` beside it, written by the NEC-4.2
command-line build at commit 7768648 (`nec42cl-serial`, sha256 `be88e6ce…`),
run on the laptop as a black box: `nec42cl-serial deck.nec deck.out`. The
oracle is the printout's SEGMENTATION DATA table (every segment's centre,
length and radius to five decimals), which
`tests/test_nec4_gc_gh_1296_1297.py` compares with what `parse_nec(...,
dialect="nec4")` builds.

Every deck here is our own probe, written for these issues:

- `gc1_reversed_run`: `GC 1` (six fields: the first segment's length) on a
  wire running toward -y, beside a one-segment feed wire.
- `gc2_count_and_gm`: `GC 2` (seven fields) whose lengths imply 7 segments
  where the GW asks for 10, replicated by a `GM` over that tag's segments.
- `gc2_equal_ends`, `gc2_radius_taper`: `GC 2` with equal first and last
  lengths (where the manual's count formula is 0/0), and with a radius taper.
- `gc0_nine_fields`: NEC-2's ratio form written with nine fields (`IX = 0`
  and four trailing zeros), as `opensource/antenna-modeling/foo.nec` does.
- `gh_right_helix`, `gh_left_helix`: helices (ISPX = 0, HR1 = HR2) of either
  hand, the shape of Cebik's NEC-4 helix decks.
- `gh_archimedes_wire_taper`, `gh_flat_log_spiral`, `gh_left_log_spiral`,
  `gh_zero_hr2_wr2`: an Archimedes spiral with a tapered wire, a flat log
  spiral (ZLEN = 0), a left-handed log spiral (negative TURNS), and the
  "HR2 = 0 means HR1, WR2 = 0 means WR1" defaults.

Cebik's NEC-4 tutorial decks, the ones the issues were filed on (nec-wild
`community/cebik-w4rnl/`), carry no license, and a printout echoes its deck,
so neither is vendored. The test reads them from `~/antennas/nec-wild` and
their printouts from `scratch/nec4-gc-gh-cebik/`, which
`scratch/nec4-gc-gh-cebik/make_printouts.sh` writes locally (git ignores
its output), and skips without them.
