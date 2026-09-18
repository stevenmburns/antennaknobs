# AK#1576 fixtures — SimNEC export segment fidelity

`2segCtrExample3.nec` is Dan AC6LA's deck, attached verbatim to QRZ thread
1003328 post #99 (2026-09-17) and to antennaknobs issue #1576. `GW 2` is a
2-segment wire fed at 50% — the junction between its two segments, and the
NEC-5 idiom for a short centre-fed feed wire. Files > SimNEC used to re-mesh
it to 3 segments (and grow further on a round trip); Files > NEC-5 Deck
correctly keeps 2.

`odd_centre_feed.nec` and `even_offcentre_feed.nec` are small synthetic
decks written for this issue's test coverage (not from a third-party
source): the first is an already-odd centre-fed wire, which PyNEC's
odd-parity mesh coercion never bumps, so the SimNEC writer's AK#1576 fix is a
no-op on it; the second is an even wire fed off-centre, which the importer's
existing split-at-feed path (AK#1510/#1511) handles, and which this issue's
fix deliberately leaves alone. Both round-trip through SimNEC export as a
fixed point, same as the AC6LA deck.
