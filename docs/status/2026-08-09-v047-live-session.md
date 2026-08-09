# 2026-08-09 — v0.47.0 pre-release live SimNEC session

**Setup:** local Linux SimNEC (`~/SimNEC/SimNEC`, jar dated 2026-01), engine =
this checkout's `momwire-nec2c` at main (post-#843), driven through wrapper
scripts in `~/nec-wrappers/` (see findings). Every deck the crew sent was
captured verbatim by a tee wrapper (`/tmp/nec-decks.log`, 16 decks); the
oracle for cross-checks was SimNEC's own bundled `nec2c-ubuntu-x86`
(`5b4az.ae6ty.1.17`).

## Scorecard

| item | result |
| --- | --- |
| Honest identity (#828) | **✓** portal dialog's NECVersion row reads `NEC2momwire.0.46`; decks arrive stamped `CM version NEC2momwire.0.46` |
| NEC ERROR frame (#829) | **✓** SimNEC surfaces our token-0 `ERROR:` refusal as an actual **error dialog** ("NEC ERROR (1)"), session stays alive. Trigger: a debug wrapper injecting a refused card, since no organically-reachable deck refuses anymore (see findings) |
| Cliff modes (#802) | **✓** `Cardioid (EZNEC).ssn` — previously fatal — runs: `RP 3` on a 46×181 grid + `GD` second medium + 4-source EX probe arrived verbatim and answered. Feed impedance on the exact logged deck: momwire **32.022+j16.195** vs bundled nec2c **32.104+j16.386** (**0.6%**). Azimuth display shows a proper cardioid |
| Regression anchor (#696 ladder tuner) | **✓ exact**: rig-side **42.56 − j4.765 Ω**, the v0.46 session's figure to the third decimal |
| Surfaces examples | `monopoleOverPatch.ssn` runs — SimNEC wire-grids its Surface elements for NEC-2 engines (~3.7k one-segment `GW`s) and momwire solves the grid |
| Cache dry run (#823) | measured — see below |

## Findings (all new)

1. **The engine is selected with a file dialog** in this build — no room for
   command-line flags. Wrapper scripts are the mechanism (name must contain
   `nec2c`, path must avoid the substring `out`). Documented in
   `reference/simnec.md`.
2. **SimNEC silently deletes `SP` cards from N-element scripts** before the
   deck reaches a NEC2C engine: a pasted patch model solves as bare wire with
   no warning from any layer (our refusal can never fire — the cards never
   arrive). Distinct from Surface *elements*, which are wire-gridded
   properly. One for the next note to Ward.
3. **SimNEC's script parser errors on apostrophes in `CM` lines** ("Don't put
   single quotes in a comment line").
4. **The crew fragments per-process state**: SimNEC runs several daemon
   processes; anything keyed per-process (the cache, a stats file path) sees
   only its own stream. Stats paths need `$$`-style uniqueness; the deck log
   is the true global stream.

## Cache dry-run analysis (decides #823's default)

From the 16 captured decks, keyed by the shipped `_operator_key`:

- 4 unique operators → **75%** of decks would have reused parse+mesh;
- 6 unique (operator, frequency) pairs → **62% fully servable** (zero fills);
- one identical (deck, frequency) request was sent **5×**, another 4×.

Caveats: a verification session is reload-heavy relative to design work, and
the crew fragmentation above means per-process realized rates sit below the
global ceiling. Verdict: the opt-in default ships as decided; the numbers go
in the docs as the evidence for turning `--cache` on; revisit default-on
after a longer natural session (and a protocol-v2 conversation about the
crew).
