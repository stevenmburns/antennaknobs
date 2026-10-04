# Two models EZNEC's NEC-4.2 slot refuses: multiple current sources

Regression fixtures for momwire#1295. Found 2026-10-04 during the 0.71.0
pre-tag check, by Steve opening a model nobody had tried in that slot.

Both decks were written by **EZNEC Pro/2+ v7.0.4** with its External NEC-4.2
slot pointed at momwire, and both came back refused:

> `***** NEC ERROR - N sources in one run with an EX 6 current source among
> them is not supported by this engine: a current source is served as its
> port's voltage drive rescaled, which is exact for one source only, and no
> EZNEC NEC-4.2 capture writes more than one`

**The last clause is false**, and these two decks are the proof. It was an
artifact of the 2026-10-03 replay sitting, every deck of which happened to
carry one source.

## Why this matters more than a missing feature

**The NEC-5 slot has served exactly these models since August.** From
`scratch/eznec-capture/`:

| capture | model | sources | NEC-5 slot |
|---|---|---|---|
| 0032 | Cardioid | `EX` x2 | serves, 525 lines |
| 0031 | 40-meter four-square array | `EX` x4 | serves, 558 lines |
| 0069 / 0070 | W8JK | `EX` x2 | serve |
| 0075 / 0076 | Field Day Special | `EX` x2 | serve |

Capture 0032 **is the same `Cardioid.ez`** as `decks/cardioid-2-current-sources.nec`
here. The two slots write the same two sources and differ only in dialect:

```
NEC-5 slot    EX 4,1,-1,0,1.414214,0.      EX 4,2,-1,0,0.,-1.414214
NEC-4.2 slot  EX 6,1, 1,0,1.414214,0.      EX 6,2, 1,0,0.,-1.414214
```

So a user moving a phased array from the NEC-5 slot to the NEC-4.2 slot — which
the 0.71.0 README actively encourages, presenting `momwire-nec4` as a peer of
`momwire-nec5` — hits a wall on a model that worked the day before. Phased
arrays are not an edge case in the EZNEC world.

## The workaround, until the fix lands

Only **current** drive is refused. The identical Cardioid deck rewritten with
`EX 0` (voltage) **serves**: 182 lines, both ports solved, 23.979 + 3.661j and
14.680 + 45.976j. In EZNEC terms: set the sources to **type V**.

## The targets

NEC-4.2 solves both decks itself, exit 0. These are the numbers a fix has to
reproduce. Currents come back pinned at the cards' own +/-1.41421, confirming
current drive.

**Cardioid** (2 wires, 2 sources, 299.7925 MHz) — `printouts-nec42/`, 182 lines:

| source | tag / seg | Z |
|---|---|---|
| 1 | 1 / 1 | 21.0326 - 18.7112j |
| 2 | 2 / 7 | 51.6136 + 20.8613j |

**40-meter four-square** (4 wires, 4 sources, 7.15 MHz, `GN 1` + `GD`) — 230 lines:

| source | tag / seg | Z |
|---|---|---|
| 1 | 1 / 1 | **-1.38797** - 20.3048j |
| 2 | 2 / 7 | 40.9235 - 21.9351j |
| 3 | 3 / 13 | 40.9235 - 21.9351j |
| 4 | 4 / 19 | 58.7204 + 53.3152j |

**Source 1's resistance is negative.** That is correct for a driven element in
a phased array absorbing power from its neighbours, and it is the detail most
likely to be mishandled by an implementation that assumes R > 0 or clamps it.
Any fix should be checked against that row specifically.

The four-square also carries `GD` beside `GN 1`, so it draws NEC-4.2's
MININEC-type-ground warning on top — one deck exercising multiple sources,
real ground and the warning path together.

## Provenance

The decks and the momwire printouts were recovered from the engine folder
immediately after each click, **not through the capture shim** — the slot was
pointed straight at `C:\momwire-071-rc\momwire-eznec\momwire-nec4.exe`, the
Azure-signed 0.71.0 release candidate (momwire main `3db86cd8`, workflow run
37185804234; line 2 stamps 0.70.0 because the version bump had not landed).
So these are not capture-shaped and carry no `meta.tsv`; the deck is the
evidence and the layout says what it is.

`printouts-nec42/` is the licensed NEC-4.2 (LLNL `NEC42W64CL.exe`) run on this
box on the identical decks, included **with attribution**, per the licensee.
NEC-4.2 sources and binaries remain licence-restricted and are not here.
