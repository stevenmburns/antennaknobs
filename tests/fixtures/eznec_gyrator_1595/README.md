# EZNEC's NT gyrator current source (AK#1595)

NEC-2 has no current-source `EX` card. EZNEC writes one anyway, by parking a
phantom wire ~100 λ away (the AK#1577 virtual wire) and tying its segments to
the real feed segments with `NT` GYRATORS — Y11 = Y22 = 0, Y12 = Y21 = j — each
driven by an `EX 0` voltage source. The deck names the construction itself:

    CM ! Wire #3 for I srcs, shorted/open TL, and/or parallel loads.
    CM ! NT #1-2 are EZNEC current sources

4nec2 builds the same thing from the other side; `scripts/bench_nec_corpus.py`'s
`gyrator_reference` (AK#475) is that construction and states the readout rule.

A gyrator inverts impedance (Z_in = 1/(B²·Z_load)), so a source read where it
SITS reports the reciprocal of the antenna's driving point. The three decks here
are one antenna in three dialects, which is what turns that into a measurement.

## Provenance

One model — Dan AC6LA's Cardioid — saved by EZNEC/Pro+ v. 7.0 in three NEC
dialects and reported by Dan (AK#1595). Two λ/4 verticals 0.25 m apart at
299.7925 MHz over perfect ground, 18 Ω loads, driven in quadrature.

| file | how it spells the drive |
|---|---|
| `Cardioidmodnec4.nec` | NEC-4.2: native `EX 6` current sources. The ORACLE — the drive it asks for is what the other two must deliver. |
| `Cardioidmodnec2.nec` | NEC-2: the phantom wire, `EX 0` voltage sources and the two `NT` gyrators. The subject. |
| `Cardioidmodnec5.nec` | NEC-5: native `EX 4` current sources. Shipped as the third dialect; not gated here, because its own defect is AK#1594. |

## The numbers

Momwire's default solver on the deck as written, through the `@file` route:

| deck | port 1 | port 2 |
|---|---|---|
| NEC-4.2 (oracle) | 36.43472 − 18.98820j | 67.76509 + 19.99761j |
| NEC-2, before AK#1595 | 0.0215840 + 0.0112487j | 0.0135747 − 0.0040059j |
| 1 / NEC-4.2 | 0.0215840 + 0.0112487j | 0.0135747 − 0.0040059j |
| NEC-2, after | 36.43472 − 18.98820j | 67.76509 + 19.99761j |

Reciprocal to every digit the solve prints, on both ports, and the far-field
patterns were already identical — so the SOLVE was right and only the readout
port was wrong. After the collapse the two decks agree bitwise: the imported
networks are the same circuit, port for port.

## What pins the sign

Impedance, input power and a dBi pattern are all invariant under flipping
BOTH forced currents, so this deck alone cannot tell `I = −Y12·V` from
`+Y12·V`. Two things do:

- **EZNEC's own two spellings.** `Y12 = +j` with `V = 1.414214j` gives
  `I = 1.414214`, which is exactly what the NEC-4.2 deck's `EX 6` asks for —
  and on port 2, `V = 1.414214` gives `−1.414214j`, again the `EX 6` value.
  Both phases, both ports.
- **A mixed deck.** `test_a_mixed_voltage_and_gyrator_deck_agrees_with_nec4`
  keeps one gyrator and drives the other element with an ordinary `EX 0` on
  real geometry, in both dialects. A sign flip then moves port 2 from
  −1.147 − 0.976j to +1.130 + 0.894j, because the relative phase between the
  two sources is no longer arbitrary.
