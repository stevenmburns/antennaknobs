#!/bin/sh
# AK#1296/#1297: NEC-4.2 printouts of Cebik's NEC-4 tutorial decks, for
# tests/test_nec4_gc_gh_1296_1297.py's corpus check. The decks carry no
# license (nec-wild community/cebik-w4rnl), and a printout echoes the deck,
# so both stay LOCAL: this writes <stem>.nec (the deck with its RP cards
# removed, which only shortens the printout) and <stem>.out here, and
# .gitignore keeps them out of git. The test skips without them.
#
#   sh scratch/nec4-gc-gh-cebik/make_printouts.sh
#
# NEC42 defaults to the laptop's licensed serial build; NEC_WILD to the corpus.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
NEC42=${NEC42:-$HOME/antennas/nec42-build/out/release-7768648/nec42cl-serial}
T2=${NEC_WILD:-$HOME/antennas/nec-wild}/community/cebik-w4rnl/tutorial-models/Tutorial-2
for deck in ch-3/3-1a-nec4 ch-3/3-1d-nec4 ch-3/3-2a-nec4 ch-11/11-11 \
    ch-4/4-6 ch-4/4-6a ch-4/4-9a ch-17/17-11-nec4; do
    stem=$(basename "$deck")
    grep -v '^RP' "$T2/$deck.nec" > "$HERE/$stem.nec"
    (cd "$HERE" && timeout 120 "$NEC42" "$stem.nec" "$stem.out" > /dev/null)
    echo "$stem.out"
done
