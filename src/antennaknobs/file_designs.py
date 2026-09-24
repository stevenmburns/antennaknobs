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
range or an armed Generator sweep seeds ``ui_params["meas_freq_range"]`` and,
with its spacing, ``ui_params["sweep_range"]`` (AK#1682), and
whatever the import left behind lands under ``ui_params["notes"]``.

A ``.nec`` deck written in 4nec2's ``SY`` dialect keeps its parametrisation
(AK#1705): every constant ``SY`` symbol (`nec_import.classify_sy`) is
published as a knob ``sy_<name>``, labelled from the card's ``'`` comment, and
``build_wires`` / ``build_network`` re-evaluate the deck from the knobs on
every build (`_SyKnobs`), so derived symbols, segment counts written as
``int(...)`` and everything else follow as the author wrote them. The deck's
topology is frozen at its own values: a knob value that changes which wire
ends meet, or makes the geometry invalid, is refused by name. A deck with no
such constant -- every deck without ``SY`` cards -- is frozen geometry, as
before, and a ``.ssn`` always is: port the design to a real ``AntennaBuilder``
when its dimensions should tune.
"""

from __future__ import annotations

import functools
import math
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from .builder import AntennaBuilder
from .nec_import import _NEC_SMIN, NEC_C_LIGHT_MHZ_M, classify_sy, parse_nec
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


def sweep_range_ui(lo, hi, grid=None, *, source="file") -> dict:
    """The ``ui_params["sweep_range"]`` a file's sweep publishes (AK#1682):
    ``{lo, hi, spacing}`` plus ``step`` (MHz) for a linear grid or ``points``
    (the total count) for a logarithmic one. ``grid`` is the importers'
    ``(spacing, value)`` pair (``NecDeck.freq_grid`` / ``SsnCircuit.sweep_grid``,
    already a point count for "log"); without one the spacing is linear and
    the app picks the density. ``source`` tells the app which rung of its
    range precedence this is -- a file's own range outranks a design's."""
    out: dict = {"lo": float(lo), "hi": float(hi), "spacing": "lin", "source": source}
    if grid is not None:
        spacing, value = grid
        out["spacing"] = spacing
        out["step" if spacing == "lin" else "points"] = (
            float(value) if spacing == "lin" else int(value)
        )
    return out


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
    sweep_grid=None,
    knobs=None,
):
    ui: dict = {}
    # A zero-width range seeds nothing: one FR point, or an .ssn with no armed
    # sweep. It pinned both the measurement dial and the design slider to that
    # one value (#1487 for decks, #1489 for .ssn), so the adapter's ±1.5 %
    # synthetic band applies instead. The guard lives here, where every loader
    # stores its range.
    if meas_range and meas_range[1] > meas_range[0]:
        ui["meas_freq_range"] = tuple(meas_range)
        # The same range with its grid (AK#1682): the app's sweep covers what
        # the file sweeps, at the file's spacing, and the measurement dial
        # travels it.
        ui["sweep_range"] = sweep_range_ui(*meas_range, sweep_grid)
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
    if knobs is not None:
        params.update(knobs.default_params())
        ui.update(knobs.ui_params())
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

        # The deck's SY knobs (AK#1705), None for a frozen deck. Not
        # `sy_...`: that prefix is the knobs' own.
        file_sy_knobs = knobs

        def build_wires(self):
            if knobs is not None:
                return knobs.deck_for(self).wire_tuples(specs=True)
            return wires_fn()

        def build_network(self):
            if knobs is not None:
                return knobs.deck_for(self).network()
            return network_fn()

    if knobs is not None:
        # The deck re-evaluated at an instance's knob values: `engine`,
        # `ladder` and the advisories read the instance's; class access keeps
        # the deck as imported.
        Builder.file_deck_parsed = _DeckAtParams(file_deck, knobs)

    # The dotted-name machinery (display titles, simnec_export's block name)
    # keys off the class identity; make it the file's, not this factory's.
    Builder.__name__ = Builder.__qualname__ = stem
    return Builder


# The cards a knob can reach that the design reads once, at load, rather
# than on every build (the app's ground switch and kernel flag are seeded
# from them), for the import note.
_LOAD_TIME_CARDS = ("GN", "GD", "GE", "EK")


def _wire_name(deck, i: int) -> str:
    return f"wire {i + 1} (tag {deck.wires[i].tag})"


def _topology(deck) -> dict:
    """What a knob may not change (AK#1705): which wire ends meet which, where
    each end stands against a ground plane, and which wires the feeds,
    loads and TL/NT cards land on. Segment counts may change -- the deck's
    own formulas re-mesh it (``segV=int(hgh)``) -- but a contact that exists
    only on one mesh changes the list, since NEC connects a wire end to
    another wire's interior only at a segment boundary.

    Contacts are compared EXACTLY: `parse_nec` has already snapped every end
    NEC would connect onto one shared coordinate (`_snap_nec_connections`),
    and interior boundaries use the snap's own formula, bit for bit."""
    wires = deck.wires
    at: dict[tuple, list] = {}
    for i, w in enumerate(wires):
        at.setdefault(w.p1, []).append((i, 1))
        at.setdefault(w.p2, []).append((i, 2))
    contacts = set()
    for ends in at.values():
        for a in ends:
            for b in ends:
                if a < b and a[0] != b[0]:
                    contacts.add((a, b))
    for j, w in enumerate(wires):
        n = int(w.n_seg)
        for k in range(1, n):
            p = tuple(a + (b - a) * (k / n) for a, b in zip(w.p1, w.p2, strict=True))
            for end in at.get(p, ()):
                if end[0] != j:
                    contacts.add((end, (j, 0)))
    plane = None
    if deck.ground:
        plane = {}
        for i, w in enumerate(wires):
            tol = _NEC_SMIN * math.dist(w.p1, w.p2) / max(int(w.n_seg), 1)
            for e, p in ((1, w.p1), (2, w.p2)):
                plane[(i, e)] = 0 if abs(p[2]) <= tol else (1 if p[2] > 0 else -1)
    return {
        "wires": len(wires),
        "contacts": frozenset(contacts),
        "plane": plane,
        "feeds": tuple((f.wire, f.edge, f.current) for f in deck.feeds),
        "loads": tuple(ld.wire for ld in deck.loads),
        "lines": tuple((t.wire_a, t.wire_b) for t in (*deck.tls, *deck.nts)),
        "virtual": (deck.virtual_anchors, deck.virtual_segment_wires),
    }


def _topology_change(old: dict, new: dict, deck) -> str | None:
    """The first way ``new`` differs from ``old``, in words, or None."""
    if old["wires"] != new["wires"]:
        return (
            f"the deck would have {new['wires']} wires, where it has "
            f"{old['wires']} at its own values"
        )

    def end_name(end):
        i, e = end
        return f"{_wire_name(deck, i)} " + (
            f"end {e}" if e else "at a segment boundary"
        )

    for verb, diff in (
        ("no longer meets", old["contacts"] - new["contacts"]),
        ("now meets", new["contacts"] - old["contacts"]),
    ):
        if diff:
            a, b = min(diff)
            return f"{end_name(a)} {verb} {end_name(b)}"
    if old["plane"] != new["plane"]:
        where = {1: "above", 0: "in", -1: "below"}
        for end in sorted(old["plane"]):
            if old["plane"][end] != new["plane"][end]:
                return (
                    f"{end_name(end)} moves from {where[old['plane'][end]]} the "
                    f"ground plane to {where[new['plane'][end]]} it"
                )
    for key, what in (
        ("feeds", "a feed"),
        ("loads", "an LD load"),
        ("lines", "a TL or NT card"),
        ("virtual", "the deck's virtual wires"),
    ):
        if old[key] != new[key]:
            return f"{what} would land on a different wire"
    return None


def _nice_step(x: float) -> float:
    """The power of ten at or below ``x``."""
    return 10.0 ** math.floor(math.log10(x))


class _SyKnobs:
    """A deck's constant SY symbols as the design's knobs (AK#1705).

    Every build re-parses the deck with the knobs' values as
    ``parse_nec(..., sy_overrides=)`` -- the same parse the import ran, with
    those symbols set at their definition -- so derived symbols, ``int(...)``
    segment counts and every card field follow exactly as they would from a
    hand-edited deck. Parses are cached per knob tuple (a drag, the tracker
    and the optimizer re-visit points; `build_wires` and `build_network`
    both ask).

    A value is refused, naming the knobs that moved and what broke, when the
    deck no longer parses at it (a segment count below 1, a feed or load off
    its wire, ...), when a wire collapses to zero length or a non-positive
    radius, or when the topology changes (`_topology`): it is frozen at the
    deck's own values. A refused value is never cached, so the next good one
    builds as usual.
    """

    def __init__(self, stem, name, text, refine, symbols, default_deck):
        self.stem, self.name, self.text, self.refine = stem, name, text, refine
        self.symbols = tuple(s for s in symbols if s.kind == "knob")
        self.defaults = tuple(s.default for s in self.symbols)
        self._parse = functools.lru_cache(maxsize=16)(self._checked)
        # Through the override path, not a copy of the import: `for_deck`
        # compares the two and keeps the knobs only when they agree.
        self.deck = self._parse(self._symbol_values(self.defaults), check=False)
        self.topology = _topology(self.deck)
        # A wire the deck ALREADY writes degenerate is the deck's business.
        self._degenerate = {
            i for i, w in enumerate(default_deck.wires) if w.p1 == w.p2 or w.radius <= 0
        }
        self.all_symbols = tuple(symbols)
        self.default_deck = default_deck

    @classmethod
    def for_deck(cls, path: Path, text: str, refine: int, deck, freq):
        """``(knobs, note)`` for a parsed deck: ``(None, None)`` when it has
        no knob. The knobs are dropped, with a note, if the deck at their
        defaults is not the deck as imported -- never a knob that moves the
        design before anyone touches it."""
        try:
            symbols = classify_sy(text, name=path.name)
        except ValueError:
            return None, None
        if not any(s.kind == "knob" for s in symbols):
            return None, None
        try:
            knobs = cls(path.stem, path.name, text, refine, symbols, deck)
            same = knobs.deck == deck
        except ValueError:
            same = False
        if not same:
            return None, (
                "The deck's SY symbols are not offered as knobs: re-evaluating "
                "it from them does not reproduce the import exactly."
            )
        return knobs, knobs.note(freq)

    # -- values ------------------------------------------------------------

    def _symbol_values(self, values) -> tuple[float, ...]:
        return tuple(
            s.symbol_value(v) for s, v in zip(self.symbols, values, strict=True)
        )

    def deck_for(self, builder):
        """The deck at ``builder``'s knob values, or a ValueError naming the
        knobs that moved and what the value broke."""
        values = []
        for s in self.symbols:
            v = getattr(builder, s.param)
            try:
                fv = float(v)
            except (TypeError, ValueError):
                fv = math.nan
            if not math.isfinite(fv):
                raise ValueError(f"{self.stem}: {s.param} = {v!r} is not a number")
            values.append(fv)
        symvals = self._symbol_values(values)
        try:
            return self._parse(symvals)
        except ValueError as e:
            moved = [
                f"{s.param} = {v:g} (the deck has {d:g})"
                for s, v, d, sv, dv in zip(
                    self.symbols,
                    values,
                    self.defaults,
                    symvals,
                    self._symbol_values(self.defaults),
                    strict=True,
                )
                if sv != dv
            ]
            raise ValueError(
                f"{self.stem}: {', '.join(moved)} is refused: {e}"
            ) from None

    def _checked(self, symvals, check=True):
        overrides = {s.name: v for s, v in zip(self.symbols, symvals, strict=True)}
        deck = parse_nec(
            self.text, name=self.name, network=True, sy_overrides=overrides
        ).refined(self.refine)
        if not check:
            return deck
        for i, w in enumerate(deck.wires):
            if i in self._degenerate or i >= len(self.deck.wires):
                continue
            if w.p1 == w.p2:
                raise ValueError(f"{_wire_name(deck, i)} would have zero length")
            if w.radius <= 0:
                raise ValueError(
                    f"{_wire_name(deck, i)} would have radius {w.radius:g}"
                )
        change = _topology_change(self.topology, _topology(deck), deck)
        if change is not None:
            raise ValueError(
                f"{change}; the deck's topology is frozen at its own values"
            )
        # Surface the translation's own refusals here, by name, rather than
        # from whichever consumer builds first.
        deck.wire_tuples(specs=True)
        deck.network()
        return deck

    # -- what the design publishes ----------------------------------------

    def default_params(self) -> dict:
        return {s.param: s.default for s in self.symbols}

    def ui_params(self) -> dict:
        """Per-knob metadata. The adapter's usual ±50 % window applies; a
        zero default, which has no window of its own, spans ± the deck's own
        extent (the largest coordinate it writes), the only length scale a
        zero constant -- a height, an offset -- has to go by."""
        extent = max(
            (abs(c) for w in self.deck.wires for c in (*w.p1, *w.p2)), default=0.0
        )
        span = extent if extent > 0 else 1.0
        ui = {}
        for s in self.symbols:
            meta = {"label": s.label or s.spelling}
            if s.unit:
                meta["unit"] = s.unit
            if s.default == 0 and not s.integer:
                meta.update(min=-span, max=span, step=_nice_step(span / 500.0))
            ui[s.param] = meta
        return ui

    def note(self, freq) -> str:
        knobs = self.symbols
        derived = [s for s in self.all_symbols if s.kind == "derived"]
        parts = [
            f"{len(knobs)} SY constant{'s are' if len(knobs) != 1 else ' is a'} "
            f"knob{'s' if len(knobs) != 1 else ''} "
            f"({', '.join(s.param for s in knobs)})"
            + (
                f"; {len(derived)} derived symbol"
                f"{'s follow' if len(derived) != 1 else ' follows'} them."
                if derived
                else "."
            )
        ]
        why = {
            "redefined": "assigned more than once",
            "unit": "a unit selector",
            "frequency": "sets only the FR card; the frequency dial covers it",
            "inert": "reaches nothing the design is built from",
        }
        fixed = [
            f"{s.spelling} ({why[s.kind]})" for s in self.all_symbols if s.kind in why
        ]
        if fixed:
            parts.append(f"Not knobs: {'; '.join(fixed)}.")
        for s in knobs:
            if "FR" in s.reaches:
                parts.append(
                    f"{s.param} also sets the FR card; the design and measurement "
                    f"frequencies stay at the deck's {freq:g} MHz."
                )
            late = [c for c in _LOAD_TIME_CARDS if c in s.reaches]
            if late:
                parts.append(
                    f"{s.param} also sets the {'/'.join(late)} card, which stays "
                    "at the deck's value."
                )
        parts.append(
            "The deck's topology is frozen at its own values: a knob value that "
            "changes which wires meet is refused."
        )
        return " ".join(parts)


class _DeckAtParams:
    """``file_deck_parsed`` for a design with SY knobs: the deck as imported
    on the class, the deck at the instance's knob values on an instance."""

    def __init__(self, deck, knobs: _SyKnobs):
        self.deck, self.knobs = deck, knobs

    def __get__(self, obj, owner=None):
        return self.deck if obj is None else self.knobs.deck_for(obj)


def _nec_builder(path: Path, text: str, refine: int = 1):
    deck = parse_nec(text, name=path.name, network=True).refined(refine)
    freq, meas_range, freq_note = _seed_freq(deck.freq_mhz)
    knobs, knob_note = _SyKnobs.for_deck(path, text, refine, deck, freq)
    return _make_builder(
        path.stem,
        freq,
        meas_range,
        [deck.skipped_note(), deck.fixed_frequency_note(), freq_note, knob_note],
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
        sweep_grid=deck.freq_grid,
        knobs=knobs,
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
    sweep_grid = circuit.sweep_grid if circuit.sweep else deck.freq_grid
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
        sweep_grid=sweep_grid,
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
