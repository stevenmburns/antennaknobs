# Draft note to M0AGP (Mike) — the diffracted pages

Accompanies `mike_hillside_elevation_utd_2026-09-10.pdf` (probe10 `--diffraction`)
and `mike_hill_ladder_utd_2026-09-10.pdf` (probe12 `--diffraction`). Kept here
with the probes that made the figures. **Not sent** — Steve's to send, edit or
drop.

---

Mike — a follow-up to the hillside pages I sent. You'll remember the hatched
wedge on the uphill side, with the note that those numbers weren't worth
quoting: the model reflected each ray off whichever bit of ground it hit and had
no way to express the hill actually being *in the way*. That gap is now closed —
the model shadows each ray, reflects off the sloping ground properly rather than
off a flat mirror at the same height, and diffracts over the crest and the toe —
so the hatch is gone and the uphill numbers are ones I'm willing to stand behind.

The honest headline is that they went **down**, not up. The old page showed about
−6 dBi at 30° uphill with the mast mid-slope; the new one shows about −15. That
is the correction working rather than a new problem: there is a 45° hill between
you and that patch of sky, and the previous answer was the one that didn't know
it. What the hill gives back shows up a little higher — between roughly 50° and
85° uphill the new page is up to 6 dB *brighter* than the old one, because the
slope works as a tilted mirror and throws a lobe where a flat-ground model has
none. The downhill side, your good direction, barely moves at all, and the feed
impedance doesn't move by a thousandth of an ohm in any case — the ground under
the radials is the only ground the matching ever sees.

Two things to hold lightly. Straight up, a plumb vertical radiates essentially
nothing, so whatever else is around fills that null in — the crest's diffraction
puts the 89° sample at −4 dBi where flat ground gives −35. Read the dip, not how
deep it is. And of the two mast positions, **mid-slope is the one to quote**: a
mast right on the crest edge is sitting inside that edge's near zone, where
treating the break as a diffracting edge is the weakest assumption in the whole
calculation. If you have a choice, a metre or two back from the break is both
the better model and, I'd guess, the better antenna.

If it's useful, the same thing is now on the web workbench under the terrain
ground: drag a knob and you get the fast geometric answer, let go and it
recomputes the full one a moment later. The corner of each polar plot tells you
which of the two you're looking at.
