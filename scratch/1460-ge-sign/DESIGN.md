# antennaknobs#1460: the importer drops the GE sign (registered before coding)

Registered 2026-09-13, on branch `fix/1460-ge-sign` from `2da6093e3`, before any
`src/` edit.

## The defect

`parse_nec` reads GE as `ground = ground or card.i(0) != 0`, so a file design
with `GE -1` reaches every engine exactly like `GE 1`. For a free wire end
standing in the ground plane that is momwire#489's silently different answer:
under GE −1 the end gets no ground-contact current expansion, but every engine
here serves the interpolated (GE 1) contact. nec2c prints 39.8+23.3j and
57−4012j for the two readings of a grounded quarter-wave.

## The rule, mirrored from momwire#1052 (U3; open at registration)

An in-plane end under `GE -1` is a CROSSING JUNCTION, and is served, when its
node has a wire continuing ABOVE the plane and a wire continuing BELOW it. Any
other in-plane end, under `GE -1` plus a ground, refuses by name in #489's
wording.

The tests mirror momwire's too:

- **In the plane:** |z| ≤ `SMIN` × the end's segment length, with `SMIN` = 1e-3
  (nec2c's `conect`).
- **Coincident ends:** every coordinate within the larger of the two wires'
  tolerances.
- **Continues above or below:** the other end's z is beyond that tolerance on the
  corresponding side.

## The design point: where the refusal lives

**At engine construction, whenever the engine actually applies a ground. Not at
parse time.**

- **The deck isn't the only source of a ground in antennaknobs.** The CLI's
  `--ground` and the app's ground switch apply one after parsing. A `GE -1` deck
  run with `--ground free` has no image to disagree about and must serve; the
  same deck under the app's finite switch must refuse. Only the engine knows
  which.
- **"Applied" is the engine's own resolved ground.** NEC-2 reads `None` as its
  default finite ground; momwire, NEC-5 and PyNEC read it as free space. So the
  check reads what each engine resolved, after its own normalisation, and
  `None` or `"free"` means no ground.
- **Only `GE -1` carries the no-expansion meaning.** A `GE 0` or `GE 1` deck
  under a ground applied later is served as today.
- **All four engines refuse.** momwire, NEC-2, NEC-5 and PyNEC each serve the
  interpolated contact for a free end. NEC-5 writes `GE -1` only when a wire is
  buried, so a free end with nothing below would go out as `GE 1`.
- **The check runs first.** It runs right after the engine resolves its ground,
  before any binary probe, so a refused deck is refused for its geometry
  whatever is installed.

## Where the code goes

| place | change |
|---|---|
| `NecDeck` | `ground_contact_interpolates: bool = True`, False when the deck's GE card is negative |
| `NecDeck.free_plane_ends()` | `(wire index, "p1"/"p2")` for every in-plane end that is not a crossing junction |
| `nec_import.ge_minus_one_contact_refusal(deck, ground)` | pure: the refusal message, or None. None when `deck` is None, the ground is None or `"free"`, the deck interpolates, or it has no free plane end |
| `SimulationEngine._refuse_ge_minus_one_contact(ground)` | reads the builder's `file_deck_parsed` (the file design's parsed deck; catalog designs have none), raises `ValueError` with the message. `ValueError` is momwire's `DeckError` base |
| the four engines | call it right after resolving their ground: momwire at `_normalise_ground`, NEC-2 after its default ground, NEC-5 after `_normalise_ground`, PyNEC after its ground is set |

## Tests, registered: `tests/test_nec_import_ge_sign_1460.py`

1. A grounded quarter-wave (30 MHz, 2.5 m, `GN 1`) REFUSES under `GE -1` on the
   momwire engine, naming the wire and #489's wording. NEC-2, NEC-5 and PyNEC
   refuse at construction too, before any binary is needed; PyNEC skips if it
   is not importable.
2. The same deck under `GE 1` serves (momwire, a finite Z).
3. `GE -1` with the structure clear of the plane serves.
4. `GE -1` in free space serves: the grounded vertical run with the ground
   `"free"`.
5. **Known answer:** a `GE -1` crossing junction (2.5 m above, 0.5 m below, soil
   A `GN 2`) serves with Z bit-identical to its `GE 1` twin. The sign never
   reaches the solver, so the bar is exact equality.
6. **Unit:** `ground_contact_interpolates` is False for `GE -1` and True for
   `GE 1`, `GE 0` and no GE. `free_plane_ends()` excludes a crossing junction,
   includes a free end, and includes a buried wire that only reaches up to the
   plane (#1052's second case).

**Gates:** `ruff check` and `ruff format --check` (0.16.5), the new tests, and the
importer and file-design suites. The PR goes up unmerged, for Steve.
