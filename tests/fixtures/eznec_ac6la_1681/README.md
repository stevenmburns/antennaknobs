# AC6LA's feed-system deck: EZNEC's transformer and fixed-frequency NTs (AK#1681)

## Provenance

| file | what it is |
|---|---|
| `Bydpole-TL-Xfmr-CLC.nec` | Dan AC6LA's AutoEZ feed-system model, QRZ thread 1003328 post #143 (2026-09-23), written by EZNEC/Pro+ v. 7.0 in NEC-5 format. Kept byte-for-byte as attached, CRLF included. |

A 20-segment dipole 9.144 m over real ground (`GN 0`, εr = 20, σ = 0.0303 S/m)
at 14.175 MHz, fed through a system built on EZNEC's virtual wire (tag 2,
AK#1577). The deck names each network itself:

    CM ! NT #1 is EZNEC lossy transmission line
    CM ! NT #2 is EZNEC transformer
    CM ! NT #3-4 are EZNEC L networks

So the chain from the source is: `EX 4` on virtual segment 1 → the two L
networks (1↔4, 4↔2; together a high-pass T) → the transformer (2↔3) → 100 ft
of lossy line (3 → the dipole's segment 10).

## What it pins

**The transformer.** `NT 2,2,2,3,20.,0.,-10.,0.,5.,0.` is all-real and rank 1
(20·5 = (−10)²): exactly `Transformer(n = ½, r = 0.05 Ω)`, i.e. 1:2 turns (1:4
impedance) with 0.2 Ω referred to the high side. Its resistive pi — what every
all-real NT imported as before — has a **−0.2 Ω** shunt leg at port b, and the
plane at that node read **−0.201 Ω**: the negative leg in parallel with the
line.

**Fixed-frequency NTs.** NT #1, #3 and #4 carry susceptance, so each is a 2×2
admittance EZNEC evaluated at the deck's `FR` frequency, 14.175 MHz. They are
exact there and wrong anywhere else.

## The numbers

Measured 2026-09-23 through the app's NEC-5 engine (the multiport-Y route,
licensed NEC5CL as the instrument), at 14.175 MHz on the deck's own segment
counts and ground:

| plane | node | NEC-5 |
|---|---|---|
| `feed` | the source (virtual segment 1) | **50.010 + 0.003j Ω** |
| `nt3b` | between the L networks (segment 4) | 46.930 − 71.246j Ω |
| `nt2a` | transformer, low side (segment 2) | 7.209 − 0.861j Ω |
| `nt1a` | transformer high side = line input (segment 3) | **28.635 − 3.442j Ω** |
| `nt1b` | the dipole's feedpoint | 75.315 − 30.879j Ω |

`nt2a` is `nt1a / 4 + 0.05` to every printed digit, which is the transformer.
Before AK#1681, `nt1a` read −0.201 Ω and the rest were unchanged.
