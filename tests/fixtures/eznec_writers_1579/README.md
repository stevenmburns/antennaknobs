# EZNEC's other two writers (AK#1579)

EZNEC drives three engine slots and writes a different deck for each. The
NEC-5 export is the whole EZNEC capture corpus (momwire's
`tests/fixtures/eznec/`); these two are the other writers, captured so the
stamp rule has a member for every token it accepts.

`Dipole1-nec2-export.nec` — EZNEC Pro/2+ 7.0.4, File > Save As (.nec),
2026-09-18, model Dipole1 — the same antenna as capture 0183 (momwire
`tests/fixtures/eznec/decks/0183_*.nec` has `EX 4` on one wire, NEC-5 format;
at the submodule pointer this branch runs against, the same deck is
`0010_dipole-in-free-space.nec`). NEC-2 has no current source, so this writer
synthesizes one: virtual wire 2, `EX 0` on it, `NT` injector Y12 = j1.
sha256 65659c90d592e40211108fa711db0da2ce7cbe0c7c2b40854bdc3f331b8a7c30,
1087 bytes, CRLF. Byte-exact: line 8 carries a literal TAB after `CM `, line 9
is `CM` plus one trailing space. Do not normalise it — the stamp rule is
whitespace-tolerant and this deck is the proof.

`Dipole1-nec42-deck.nec` — EZNEC Pro/2+ 7.0.4, External NEC-4.2 slot,
2026-09-18 08:31, same model. Transcribed from the Windows session's message,
to be verified against branch `capture/2026-09-18-writers`. sha256
a25d7d20067f7cb54f7778af087ae5d02a60ac078414527cef0a58985f31504b, 278 bytes,
CRLF. It is 0183's NEC-5 deck with `EX 6,1,6,0,1.414214,0.` in place of
`EX 4,1,6,0,...`, otherwise identical (two-field `GE`, `PQ`, version line).

## What the three say about one antenna

`tests/test_nec5_eznec_declaration_1579.py` runs all three through
momwire:bspline. The `NT` here is an ideal gyrator (Y11 = Y22 = 0,
Y12 = Y21 = j1, so a 1 Ω gyration resistance), which inverts: the impedance at
its driven virtual node is `1 / Z_antenna`, and undoing that recovers the
antenna.

| deck | reading | feed lands at | momwire:bspline |
|---|---|---|---|
| `0010` (NEC-5) | declared NEC-5 | knot 6 of 11 = 0.5454 | 85.1086 + 45.8302j |
| `Dipole1-nec42-deck` (`EX 6`) | NEC-2 | centre of segment 6 = 0.5 | 82.1202 + 45.9154j |
| `Dipole1-nec2-export` (`NT` injector) | NEC-2 | centre of segment 6 = 0.5 | 1/Z = 82.1202 + 45.9154j |

The two NEC-2-reading writers agree to **7.2e-13** — the injector translation
is exact and the two decks are the same antenna fed at the same point. The
NEC-5 writer's deck lands **3.18e-02** away, and all of that is the
half-segment: `EX 4,1,6,0` is NEC-5's end 2 of segment 6, i.e. knot 6 of an
11-segment wire (0.5454 of it), while `EX 6,1,6,0` and `NT …,1,6` are NEC-2's
centre of segment 6 (0.5). AK's NEC-5 engine reproduces `0010`'s printout
exactly (79.948 + 29.919j, rel 0.0), so the card is being re-emitted where
NEC-5 read it. Whether EZNEC means a centre-fed odd-segment model to feed at
6/11 in its NEC-5 export is a question about EZNEC, not about this importer —
momwire's own EZNEC seam reads the same knot. Recorded, not tuned.

The equality class here is the 4.2 deck against the NEC-2 export: same
reading, same source position, two spellings, so the only thing between them
is the virtual-wire detector and the injector. A 10-segment Dipole1 NEC-2
export — where the wire's centre IS a knot and the NEC-5 and NEC-2 writers
would be co-located — is the follow-up fixture that would make the NEC-5 row
an equality case too; it has been requested from the Windows box and is not
here yet.
