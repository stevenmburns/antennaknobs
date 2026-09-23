"""Builders synthesized from antenna data files — the CLI's ``@file`` specs.

``builder_from_file`` turns a NEC card deck (``.nec``) or a SimNEC circuit
(``.ssn``) into a ready-to-run ``AntennaBuilder`` class, so every CLI
subcommand can consume a file directly wherever a builder spec goes:

    antennaknobs draw --builder @decks/yagi.nec
    antennaknobs sweep --builder @station.ssn
    antennaknobs compare_patterns --builders dipoles.invvee @measured/invvee.nec
    python -m antennaknobs.simnec_export @decks/yagi.nec   # .nec -> .ssn
    antennaknobs export --builder @dip.ssn                 # .ssn -> .nec

The ``@`` sigil keeps the spec grammar unambiguous — a bare ``foo.nec`` would
parse as family ``foo``, design ``nec`` — and an ``@`` spec never takes a
``:variant`` suffix (a deck has no variants), so colons in paths (Windows
drive letters) pass through untouched.

Unlike a ``user.<name>`` design (arbitrary Python, gated by the trust store),
these files are pure data — ``parse_nec`` / ``parse_ssn`` never execute
anything — so an ``@`` spec loads with no allow/screen step.

The synthesized builder is the authoring guide's deck-stub recipe, generated
on the fly: ``build_wires`` returns the deck's wires with per-wire specs,
``build_network`` the deck's (or station ``.ssn``'s) translated network,
``freq`` is seeded from the file (the FR card / the Generator's MHz), the FR
range or an armed Generator sweep seeds ``ui_params["meas_freq_range"]``, and
whatever the import left behind lands under ``ui_params["notes"]``. A deck is
frozen geometry, so the only knob is ``freq`` — port the design to a real
``AntennaBuilder`` when dimensions should tune.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from .builder import AntennaBuilder
from .nec_import import NEC_C_LIGHT_MHZ_M, parse_nec
from .simnec_import import parse_ssn

__all__ = ["builder_from_file"]

# Seed for a file that names no frequency at all (no FR card, no Generator
# MHz). Arbitrary but common (20 m); the note tells the user to set theirs.
DEFAULT_FREQ_MHZ = 14.0


def _seed_freq(freq_range):
    """(freq, meas_freq_range, note) from a file's (lo, hi) MHz range.

    A single frequency (one FR point, lo == hi) seeds no measurement window. A
    zero-width window pinned both the dial and the design slider to that one
    value (#1487); without one, the adapter's ±1.5 % synthetic band and the
    dial's usual window apply."""
    if freq_range:
        lo, hi = freq_range
        if hi <= lo:
            return float(lo), None, None
        return round(0.5 * (lo + hi), 6), (lo, hi), None
    return (
        DEFAULT_FREQ_MHZ,
        None,
        f"The file names no frequency; measurement freq defaults to "
        f"{DEFAULT_FREQ_MHZ:g} MHz — set it to the design's real band.",
    )


def _make_builder(
    stem,
    freq,
    meas_range,
    notes,
    wires_fn,
    network_fn,
    *,
    extended_kernel=False,
    ground=None,
    ground_method=None,
    file_deck=None,
    ground_card=None,
):
    ui: dict = {}
    # A zero-width range seeds nothing: one FR point, or an .ssn with no armed
    # sweep. It pinned both the measurement dial and the design slider to that
    # one value (#1487 for decks, #1489 for .ssn), so the adapter's ±1.5 %
    # synthetic band applies instead. The guard lives here, where every loader
    # stores its range.
    if meas_range and meas_range[1] > meas_range[0]:
        ui["meas_freq_range"] = tuple(meas_range)
    # AK#1432: the deck says what ground it models, so the folder route seeds
    # the app's switch from it instead of the app's default finite ground
    # (which made NEC-5 refuse a free-space dipole at z = 0). The wires carry
    # the deck's own segment counts, which the app honours regardless of its
    # per-wire N — the flag lets the label say so.
    ui["ground_seed"], medium = ground_seed(ground, ground_method)
    if medium is not None:
        ui["ground_medium"] = medium
        # The card the finite seed came from, when the default label would
        # name the wrong one: a NEC-5 deck's GN 0 is Sommerfeld, which the
        # panel otherwise spells "Sommerfeld (GN 2)" (AC6LA, 2026-09-13).
        if ground_card:
            ui["ground_card"] = ground_card
    ui["fixed_segment_counts"] = True
    note = " ".join(n for n in notes if n)
    if note:
        ui["notes"] = note
    params = {"freq": freq, "design_freq": freq}
    if ui:
        params["ui_params"] = MappingProxyType(ui)

    class Builder(AntennaBuilder):
        label = stem

        default_params = MappingProxyType(params)

        # The deck's own metre-megahertz product, not the SI one (AK#1607).
        # A file design's frequencies come from the file, and the file is a
        # document in NEC's dialect: solving it at the SI c models a
        # slightly different antenna than its author wrote down. Set here
        # rather than in either loader because BOTH of them hand this
        # factory NEC cards -- a `.ssn`'s geometry is the deck embedded in
        # it, the same reason `file_deck` is set for both (AK#1576). A
        # loader for a format that is NOT NEC cards must say so here.
        c_light_mhz_m = NEC_C_LIGHT_MHZ_M

        # The file's own EK card (NecDeck.extended_kernel), issue #849: the
        # CLI's `--extended-kernel` handling ORs this in for a momwire engine
        # (see `cli.engine_factory_from_args`) so a deck that asks for the
        # extended thin-wire kernel gets it without an extra flag, and a
        # deck that doesn't still honors an explicit `--extended-kernel`.
        file_extended_kernel = extended_kernel
        # The deck's ground in the CLI's `--ground` shape (AK#1432): the
        # `@file` route applies it when `--ground` is not given.
        file_ground = ground
        # The parsed deck the design was built from (U2): the `ladder`
        # command reads its segment counts and fed segments for the report.
        file_deck_parsed = file_deck

        def build_wires(self):
            return wires_fn()

        def build_network(self):
            return network_fn()

    # The dotted-name machinery (display titles, simnec_export's block name)
    # keys off the class identity; make it the file's, not this factory's.
    Builder.__name__ = Builder.__qualname__ = stem
    return Builder


def _nec_builder(path: Path, text: str, refine: int = 1):
    deck = parse_nec(text, name=path.name, network=True).refined(refine)
    freq, meas_range, freq_note = _seed_freq(deck.freq_mhz)
    return _make_builder(
        path.stem,
        freq,
        meas_range,
        [deck.skipped_note(), deck.fixed_frequency_note(), freq_note],
        lambda: deck.wire_tuples(specs=True),
        deck.network,
        extended_kernel=deck.extended_kernel,
        ground=deck.ground_spec,
        ground_method=deck.ground_method,
        ground_card=(
            f"NEC-5 {deck.ground_card}"
            if deck.nec5_dialect and deck.ground_card
            else None
        ),
        file_deck=deck,
    )


def ground_seed(ground, method=None):
    """The ``ui_params`` pair a file design publishes for the app (AK#1432):
    ``(seed, medium)`` with seed one of "free" / "pec" / "sommerfeld" /
    "fast" / "mininec" and medium ``{"eps_r", "sigma"}`` for the seeds with a
    soil, None otherwise. `ground` is the CLI's `--ground` shape."""
    if ground is None:
        return "free", None
    if ground == "pec":
        return "pec", None
    kind, eps_r, sigma = ground
    if kind == "mininec":
        seed = "mininec"
    else:
        seed = "fast" if kind == "finite-fast" else (method or "sommerfeld")
    return seed, {"eps_r": float(eps_r), "sigma": float(sigma)}


def _ground_note(ground) -> str | None:
    """Ground is an app/engine setting, not a design output — so a file that
    models one gets an actionable pointer at the matching ``--ground`` spec."""
    if ground is None:
        return None
    if ground == "pec":
        arg, desc = "pec", "a perfect (PEC)"
    elif ground[0] == "mininec":
        _, eps_r, sigma = ground
        arg = f"mininec:{eps_r:g},{sigma:g}"
        desc = f"a MININEC-type (eps_r {eps_r:g}, sigma {sigma:g} S/m)"
    else:
        _, eps_r, sigma = ground
        arg = f"finite:{eps_r:g},{sigma:g}"
        desc = f"a Sommerfeld (eps_r {eps_r:g}, sigma {sigma:g} S/m)"
    return f"The file models {desc} ground — run with --ground {arg} to match."


def _ssn_builder(path: Path, text: str, refine: int = 1):
    if refine != 1:
        raise SystemExit(
            f"{path.name}: a SimNEC circuit has no refinement path; "
            "export it to .nec and refine the deck"
        )
    circuit = parse_ssn(text, name=path.name, network=True)
    if circuit.conductivity is not None and circuit.deck.conductivity is None:
        # NECOptions.mhosPerMeter is the wire material; bake it into the deck
        # so wire_tuples(specs=True) carries it per wire, exactly as a deck
        # LD 5 would.
        circuit = replace(
            circuit, deck=replace(circuit.deck, conductivity=circuit.conductivity)
        )
    deck = circuit.deck
    # The Generator's MHz is the authoritative solve frequency; the deck's FR
    # is advisory. Either can seed the measurement range (an armed sweep wins).
    if circuit.freq_mhz is not None:
        freq, freq_note = round(circuit.freq_mhz, 6), None
    else:
        freq, _, freq_note = _seed_freq(deck.freq_mhz)
    meas_range = circuit.sweep or deck.freq_mhz
    return _make_builder(
        path.stem,
        freq,
        meas_range,
        [
            circuit.skipped_note(),
            circuit.mesh_note(),
            _ground_note(circuit.ground),
            freq_note,
        ],
        lambda: deck.wire_tuples(specs=True),
        circuit.network,
        extended_kernel=deck.extended_kernel,
        ground=circuit.ground,
        ground_method="sommerfeld",
        # AK#1576: `_nec_builder` sets this; a re-imported `.ssn` is exactly
        # as much a parsed file deck as the `.nec` it came from, and leaving
        # it unset here was the one place the two loaders disagreed about
        # that fact. `file_deck_parsed` is a general "this design came from
        # parsing a file" signal other code reads (`_refuse_ge_minus_one_contact`
        # applies the GE -1 ground-contact refusal only when it is set, and
        # `ladder` reads its segment counts for `.nec` decks) — a `.ssn`
        # round trip of a GE -1 deck used to lose that refusal on the second
        # hop purely because this loader forgot to carry the fact forward.
        file_deck=deck,
    )


# extension -> loader
_LOADERS = {".nec": _nec_builder, ".ssn": _ssn_builder}


def builder_from_file(spec: str, refine: int = 1):
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
    return loader(path, text, refine=refine)
