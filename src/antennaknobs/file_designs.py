"""Builders synthesized from antenna data files — the CLI's ``@file`` specs.

``builder_from_file`` turns a NEC card deck (``.nec``) into a ready-to-run
``AntennaBuilder`` class, so every CLI subcommand can consume a file directly
wherever a builder spec goes:

    antennaknobs draw --builder @decks/yagi.nec
    antennaknobs compare_patterns --builders dipoles.invvee @measured/invvee.nec
    python -m antennaknobs.simnec_export @decks/yagi.nec   # .nec -> .ssn

The ``@`` sigil keeps the spec grammar unambiguous — a bare ``foo.nec`` would
parse as family ``foo``, design ``nec`` — and an ``@`` spec never takes a
``:variant`` suffix (a deck has no variants), so colons in paths (Windows
drive letters) pass through untouched.

Unlike a ``user.<name>`` design (arbitrary Python, gated by the trust store),
these files are pure data — ``parse_nec`` never executes anything — so an
``@`` spec loads with no allow/screen step.

The synthesized builder is the authoring guide's deck-stub recipe, generated
on the fly: ``build_wires`` returns the deck's wires with per-wire specs,
``build_network`` the deck's translated network, ``freq`` is seeded from the
deck's FR card (whose range also seeds ``ui_params["meas_freq_range"]``), and
whatever the import left behind lands under ``ui_params["notes"]``. A deck is
frozen geometry, so the only knob is ``freq`` — port the design to a real
``AntennaBuilder`` when dimensions should tune.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from .builder import AntennaBuilder
from .nec_import import parse_nec

__all__ = ["builder_from_file"]

# Seed for a file that names no frequency at all (no FR card). Arbitrary but
# common (20 m); the note tells the user to set theirs.
DEFAULT_FREQ_MHZ = 14.0


def _seed_freq(freq_range):
    """(freq, meas_freq_range, note) from a file's (lo, hi) MHz range."""
    if freq_range:
        lo, hi = freq_range
        return round(0.5 * (lo + hi), 6), (lo, hi), None
    return (
        DEFAULT_FREQ_MHZ,
        None,
        f"The file names no frequency; measurement freq defaults to "
        f"{DEFAULT_FREQ_MHZ:g} MHz — set it to the design's real band.",
    )


def _make_builder(stem, freq, meas_range, notes, wires_fn, network_fn):
    ui: dict = {}
    if meas_range:
        ui["meas_freq_range"] = tuple(meas_range)
    note = " ".join(n for n in notes if n)
    if note:
        ui["notes"] = note
    params = {"freq": freq, "design_freq": freq}
    if ui:
        params["ui_params"] = MappingProxyType(ui)

    class Builder(AntennaBuilder):
        label = stem

        default_params = MappingProxyType(params)

        def build_wires(self):
            return wires_fn()

        def build_network(self):
            return network_fn()

    # The dotted-name machinery (display titles, simnec_export's block name)
    # keys off the class identity; make it the file's, not this factory's.
    Builder.__name__ = Builder.__qualname__ = stem
    return Builder


def _nec_builder(path: Path, text: str):
    deck = parse_nec(text, name=path.name, network=True)
    freq, meas_range, freq_note = _seed_freq(deck.freq_mhz)
    return _make_builder(
        path.stem,
        freq,
        meas_range,
        [deck.skipped_note(), freq_note],
        lambda: deck.wire_tuples(specs=True),
        deck.network,
    )


# extension -> loader; the seam a future format (e.g. SimNEC .ssn) plugs into
_LOADERS = {".nec": _nec_builder}


def builder_from_file(spec: str):
    """The builder class for an ``@``-spec path (the leading ``@`` already
    stripped): dispatch on the extension, parse once, and synthesize the
    design. Raises ``SystemExit`` with a clear message for a missing file or
    an unsupported extension (matching ``get_builder``'s unknown-builder
    behavior); parse errors propagate as ``ValueError`` so the real cause —
    file, line, card — reaches the user."""
    path = Path(spec).expanduser()
    loader = _LOADERS.get(path.suffix.lower())
    if loader is None:
        raise SystemExit(
            f"@{spec}: unsupported design-file extension "
            f"{path.suffix.lower() or '(none)'!r} — an @ spec loads "
            f"{' / '.join(sorted(_LOADERS))} antenna files"
        )
    if not path.is_file():
        raise SystemExit(f"@{spec}: no such file")
    # Old decks in the wild carry cp1252/latin-1 comment text; geometry cards
    # are ASCII, so replace rather than refuse on a stray comment byte.
    text = path.read_text(encoding="utf-8", errors="replace")
    return loader(path, text)
