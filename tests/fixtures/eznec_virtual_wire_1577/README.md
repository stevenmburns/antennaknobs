# EZNEC's virtual wire (AK#1577)

EZNEC spells a source that sits behind a transformer or a transmission line by
parking one extra wire ~100 λ away and using its **segments as circuit nodes**:
the `NT`/`TL` cards and the `EX` address those segments, and each segment it
uses is pinned open with `LD 4 … 1.E+10` so it carries no antenna current. The
deck says so itself, in a comment EZNEC writes: `! *Wire #3 for virtual
segments.`

Before AK#1577 the importer modeled that wire as real geometry, and a source on
it collided with the network ports:

    ValueError: wire 3: piece between knots 1 and 2 is claimed by more than
    one attachment (a knot source needs its own wire end, #824)

## Provenance

NEC-5 printouts captured as End-User Reports; NEC-5 is (c) LLNL,
LLNL-CODE-746721. The binary is user-licensed and never distributed with
antennaknobs.

| file | what it is |
|---|---|
| `failEZN5.nec` | Mike WA7ARK's OCF dipole with an EZNEC transformer and lossy line, **current** source (`EX 4`) on the virtual wire, and the `1.E+10` pins. Reported by Dan AC6LA, QRZ 1003328 post #104 (2026-09-18), attached there under this name. Written by AutoEZ / EZNEC Pro/4+ v. 7.0.4 in NEC-5 format. The reproducer. |
| `failEZN5.out` | its NEC5CL printout (session capture `notes/mw1116-fixtures.local/failEZN5.NEC5.OUT`). |
| `WA7ARK-OCF-Load-Xfmr-TL.nec` | the same model with a **voltage** source (`EX 0`) on the virtual wire and **no pins** — Mike's earlier deck, and the AK#1577 gate for `Driven` instead of `DrivenCurrent`. Its `GE 0` carries one field, which this importer's NEC-2-style parser accepts. |
| `WA7ARK-OCF-Load-Xfmr-TL.out` | its NEC5CL printout (captured as `NEC5_WA7ARK-OCF-Load-Xfmr-TL.OUT`). |
| `WA7ARK-OCF-LoadOnly.nec` | the control: the same antenna and the same `LD 0` capacitor, no virtual wire, no network — driven straight at the OCF point. It is what turns a difference at the source into a statement about the antenna or about the circuit. |
| `WA7ARK-OCF-LoadOnly.out` | its NEC5CL printout (captured as `NEC5_WA7ARK-OCF-LoadOnly.OUT`). |

All three run at 1.8 MHz in free space (`GN -1`).

## The numbers, as the printouts give them

| deck | port | NEC-5 |
|---|---|---|
| `failEZN5` | source (tag 3, virtual segment 2) | **48.919 + 103.89j Ω**, I = 1.414214 A forced |
| `failEZN5` | 1e-10 V probe (tag 1, segment 189) | I = **0.52288 − 0.39562j A** |
| `WA7ARK-OCF-Load-Xfmr-TL` | source (tag 3, virtual segment 2) | **49.307 + 104.23j Ω** |
| `WA7ARK-OCF-LoadOnly` | source (tag 1, segment 378) | **275.53 − 1441.0j Ω** |

The momwire 0.59.0 EZNEC drop-in reads `failEZN5.nec` literally (virtual wire
and all) and answers 49.482 + 104.52j Ω at the source with a probe current of
0.52486 − 0.39938j A — 1.15 % and 0.61 % from NEC-5. That printout is not
shipped here; it is quoted in AK#1577.

## Two facts these fixtures exist to hold

**The pins are load-bearing.** Feed NEC-5's own control-deck impedance
(275.53 − 1441.0j, the antenna with its capacitor, seen at the transformer's
port) through the network AK imports from `failEZN5.nec`, and the driven-port
impedance comes back 48.9173 + 103.889j — NEC-5's printed 48.919 + 103.89j to
**1.8e-05** relative. The same arithmetic against the unpinned
`WA7ARK-OCF-Load-Xfmr-TL` deck lands 4.5e-03 away from ITS printout, because
without the pins those virtual segments still carry their own (small, but not
zero) admittance in NEC and the import models them as ideal opens. EZNEC's
newer decks write the pins; that is what makes the ideal open exact.

**End to end, the residual is where the attachment sits, not the circuit.** AK
reads an `NT`/`TL`/`EX` segment field as a segment and puts the port at its
CENTRE; NEC-5 addresses a knot. On `WA7ARK-OCF-LoadOnly` that is one knot out
of 378 and costs 2.15 % of X (bspline 275.111 − 1409.989j against the printout
above) — and re-spelling the deck's source as `EX 0,1,378,2`, a knot, makes AK's
own NEC-5 engine reproduce the printout's 275.53 − 1441.0j to every printed
digit. The transformer and lossy line then amplify that 2.15 % into ~4 % of R
at the source. Node-addressed `NT`/`TL` reading is a separate contract
(momwire#456's ws3 oracle, `tests/fixtures/eznec_nec5/`), not AK#1577.
