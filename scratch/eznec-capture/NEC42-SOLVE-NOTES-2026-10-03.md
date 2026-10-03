# The captured NEC-4.2 decks, solved — target numbers and printout layout

Companion to the 0223–0239 capture sitting (momwire#1295). Every deck EZNEC's
External NEC-4.2 slot wrote in that sitting, run on the licensed NEC-4.2 on the
Windows box.

**No printout, and no excerpt of one, appears in this file or anywhere in the
repository.** NEC-4.2 is home-use licensed; its output stayed on that machine.
What follows is numbers and a description of layout in prose — enough for a
black-box match by `momwire-nec4*`, and nothing more.

Engine: the LLNL console build, invoked exactly as EZNEC invokes it — two
positional paths, deck in and printout out.

## Every deck solved

The 17 captures reduce to **15 unique decks** (0223 and 0236 share one; 0225 and
0226 are the identical pair noted in the capture PR). **All 15 exited 0.** None
produced an error line. Three produced one warning apiece, described below.

## Target impedances

The feed-point value from each deck, with the source quantities that produced it.
These are the numbers `momwire-nec4*` has to reproduce.

| capture | R + jX (Ω) | V (volts) | I (amps) |
|---|---|---|---|
| 0223 / 0236 | 81.7499 + 46.0034j | 115.6120 + 65.0586j | 1.414210 + 0.000000j |
| 0224 | 81.7499 + 46.0034j | 1.4142 + 0.0000j | 0.013139 − 0.007394j |
| 0225 / 0226 | 106.1310 + 40.2981j | 1.4142 + 0.0000j | 0.011646 − 0.004422j |
| 0227 | 82.1757 + 46.3603j | 1.4142 + 0.0000j | 0.013055 − 0.007365j |
| 0228 | 81.7499 + 46.0034j | 1.4142 + 0.0000j | 0.013139 − 0.007394j |
| 0229 | 81.6310 + 44.9372j | 1.4142 + 0.0000j | 0.013295 − 0.007319j |
| 0230 | 81.6310 + 44.9372j | 1.4142 + 0.0000j | 0.013295 − 0.007319j |
| 0231 | 81.6784 + 45.4004j | 1.4142 + 0.0000j | 0.013228 − 0.007352j |
| 0232 | 81.6784 + 45.4004j | 1.4142 + 0.0000j | 0.013228 − 0.007352j |
| 0233 | 0.1118 − 9078.8200j | 1.4142 + 0.0000j | 0.000000 + 0.000156j |
| 0234 | 31.3773 + 25.9276j | 44.3742 + 36.6672j | 1.414210 + 0.000000j |
| 0235 | 13.6484 + 4.4250j | 19.3018 + 6.2580j | 1.414210 + 0.000000j |
| 0237 | 81.7499 + 46.0034j | 115.6120 + 65.0586j | 1.414210 + 0.000000j |
| 0238 | 81.7499 + 46.0034j | 115.6120 + 65.0586j | 1.414210 + 0.000000j |
| 0239 | 149.7710 + 143.2080j | 211.8090 + 202.5270j | 1.414210 + 0.000000j |

### What the source columns confirm

`EX 6` and `EX 0` are current and voltage drive respectively, and the solved
numbers prove it rather than inferring it from the card:

- Where the deck carries **`EX 6`**, the current comes back fixed at exactly
  1.414210 + 0j — the card's own amplitude — and the voltage is whatever the
  antenna demanded. It is a **current source**.
- Where it carries **`EX 0`**, the voltage is pinned at 1.4142 + 0j and the
  current falls out. It is a **voltage source**.

0223 and 0224 are the decisive pair: the same antenna, the same frequency, the two
source cards, and **the same impedance to four decimals in both**. So the slot's
two source spellings are two drives on one problem, not two different problems.

### Reading the rest of the table

- **0225/0226 vs 0228** isolates the R+jX load: 106.1310 + 40.2981j against the
  unloaded 81.7499 + 46.0034j.
- **0227** is the copper wire-loss deck, and moves the unloaded value only
  slightly — 82.1757 + 46.3603j against 81.7499 + 46.0034j, i.e. about half an ohm
  of added resistance. That is the expected size for copper at this frequency and
  a useful low-amplitude check.
- **0229 and 0230 agree exactly** — the two spellings of perfect ground
  (`GN 1` bare, and `GN 1` with the full parameter tail) are the same ground.
- **0231 and 0232 also agree exactly**, at 81.6784 + 45.4004j. So on this geometry
  **NEC-4.2 gives `GN 2` and `GN 3` the same answer**, even though EZNEC presents
  them as different ground methods. Worth knowing before treating `GN 3` as a
  distinct physics path — on this model it is not.
- **0233** is the SWR-sweep deck and sits far from the others at
  0.1118 − 9078.8200j. That is correct rather than alarming: the model is the
  299.7925 MHz dipole, and the sweep set 13.9 MHz, so the antenna is electrically
  tiny and almost purely capacitive.
- **0237 and 0238 reproduce 0223 exactly.** Changing the pattern request from
  azimuth to elevation to 3D does not touch the solved impedance, as it should not.

## Printout layout

Four distinct heading sequences across the 15 decks. The first six sections are
identical everywhere, so a reader can rely on that prefix.

**The common prefix, in order:** structure specification; segmentation data;
frequency; antenna environment; structure impedance loading; matrix timing.

Then the layouts diverge:

**Layout A — the baseline** (10 decks: 0223/0236, 0224, 0225/0226, 0227, 0228,
0229, 0231, 0232, 0237, 0238). After the prefix: antenna input parameters;
currents and location, which carries its own column banner naming segment, tag,
segment-centre coordinates and segment current; charge densities; power budget;
radiation patterns, likewise introduced by its own column banner naming the angle
pair, the power gains, the polarization group and the two field components.

**Layout B — no pattern requested** (0233 and 0239, the two `XQ` decks). Identical
to layout A up to and including power budget, and then it simply **stops**. No
far-field section of any kind. A reader looking for a pattern must tolerate its
absence rather than treat it as truncation.

**Layout C — transmission lines and networks** (0234 and 0235). Two extra sections
appear **before** antenna input parameters: a network-data section, and a section
giving the structure excitation at the network connection points. After power
budget a far-field ground-parameters section appears, and only then the radiation
pattern. So the presence of `TL`/`NT` in the deck moves the input-parameters
section later in the file — anything locating it by position rather than by
heading will mis-read these.

**Layout D — ground parameters without networks** (0230). Layout A plus the same
far-field ground-parameters section between power budget and radiation patterns.

### What triggers the far-field ground-parameters section

It appears in exactly the three decks that carry a `GD` card — 0230, 0234 and
0235 — and in no others. So `GD` in the deck predicts that section in the
printout.

### The 3D pattern (mode 1001)

0238 is the only deck using the 1001 mode integer. The pattern block's **column
layout is byte-for-byte the one the 1000-mode decks use** — same banner, same
columns, same order. What changes is volume: the azimuth and elevation decks
produce a printout of 542 lines, of which roughly 374 are pattern rows, while the
3D deck produces 2887 lines with roughly 2719 pattern rows, from its 37 × 73 grid.

That is the useful finding for a drop-in: **3D needs no special formatting**, only
the capacity to emit far more rows. A reader keying on the column banner will find
it unchanged.

## The warnings

Three decks — 0230, 0234 and 0235 — each produced a single warning, and they are
the same three that carry a `GD` card alongside `GN 1`. The warning cautions that
a MININEC-type ground may not behave properly in that combination. All three still
solved and exited 0.

Worth flagging to whoever owns the EZNEC side: this is NEC-4.2 objecting to a card
combination **EZNEC itself generated**, unprompted, from ordinary ground settings.
It does not appear to have harmed the result — 0230's impedance matches 0229's
exactly, and 0229 is the same ground without the `GD` card — but a drop-in
reproducing this slot's behaviour will meet the combination and should decide
deliberately what to do with it.

## What the GE −1 and GN 3 decks do differently

**0239, the buried wire (`GE -1,-1`).** It solved without complaint, 181 lines,
exit 0, giving 149.7710 + 143.2080j. Structurally it is layout B — the common
prefix through power budget and nothing further — because it was run from SrcDat
and so carries `XQ` rather than `RP`. Being buried changed **nothing about the
printout's shape**; it is a wholly ordinary run that happens to sit below ground.
The impedance is far from the free-space value, which is expected for a wire a
metre inside soil.

**0232, the `GN 3` deck.** Structurally indistinguishable from the `GN 2` deck
0231 — same layout A, same section order, and as noted above the identical
impedance. On this geometry `GN 3` is not a distinct path through the engine, so
there is no separate behaviour for a drop-in to reproduce. Whether that holds for
geometries where the two ground models genuinely diverge is untested here.

## Caveats

- One model family dominates: ten of the fifteen decks are the shipped free-space
  dipole with small variations. The two multi-wire models with lines and networks
  (0234, 0235) are the only structurally rich cases, and there is no buried-radial
  model in the set.
- 0233's 13.9 MHz value is a real solved number but an odd operating point, being
  a 300 MHz antenna driven far below resonance. It is a poor choice for a
  tolerance comparison.
- The sitting has no RLC-series load capture, so no target number for that path.
- Impedances are quoted as the printout gives them; no rounding or re-derivation.
