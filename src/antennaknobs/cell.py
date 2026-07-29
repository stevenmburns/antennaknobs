"""Hierarchical geometry authoring — the geometry-layer analog of the
:class:`~antennaknobs.network.Composite` / :class:`~antennaknobs.network.Instance`
circuit hierarchy (issue #489).

This is "Suggestion A": a reusable geometry template (:class:`Cell`) plus a
placement of it (:class:`Placement`) that carries a pose (:class:`Transform`)
and a formal/actual **feed-wire rename map**. It exists so an array of N
elements is authored once (the element `Cell`) and stamped N times, instead of
the three unreconciled styles in the tree today (hand-unrolled offset loops in
``builder.py``, index-templated f-strings duplicated across ``build_wires`` and
``build_network``, and per-test inline builders).

The parallel to the circuit hierarchy is deliberate and near line-for-line:

    circuit (network.py)                 geometry (this module)
    ------------------------------------ ------------------------------------
    Composite(ports, branches, aliases)  Cell(feeds, wires, children)
    Instance(name, of, **portmap)        Placement(name, of, transform,
                                                   **feedmap)
    portmap {formal: actual}             feedmap {formal: actual}
    "<instance>.<node>" namespacing      "<instance>.<wire>" namespacing
    aliases (nominal node merge)         Transform (positional endpoint weld)
    _expand_instance                     _place
    Network._expand_instances            flatten_placements

The one structural difference is the last two rows: circuit connectivity is
*nominal* (nodes join by name-equality, so the hierarchy needs ``aliases`` to
merge names), while geometry connectivity is *positional* (endpoints join when
they coincide within ``eps`` downstream in ``geometry.py``, so the hierarchy
needs a ``Transform`` to decide which endpoints physically land together).
``Transform`` is therefore not decoration — it plays the structural role here
that ``aliases`` plays in ``Composite``.

Two intentional divergences from :class:`Instance`:

  * A ``feedmap`` may be **partial**. A formal feed left unbound keeps a
    namespaced default name ``"<instance>.<feed>"`` — the same treatment an
    internal node gets. This is correct because a feed *wire* exists whether or
    not it is renamed; renaming only changes the external handle. (An unbound
    circuit port, by contrast, is a floating terminal, so ``Instance`` requires
    every formal be bound.)
  * Binding two feeds to the same actual is rejected, not fused: two feed wires
    sharing a name is an ambiguous ``PortOnWire`` target, not a weld.
"""

from dataclasses import dataclass

from .network import Wire, as_wire
from .transform import Transform


@dataclass(frozen=True)
class Cell:
    """A reusable geometry template in LOCAL coordinates — the geometry-layer
    analog of :class:`~antennaknobs.network.Composite`.

    - ``feeds`` are the formal, externally-addressable wire names. At placement
      each formal is bound (via :class:`Placement` kwargs — the feedmap) to an
      actual name in the parent's namespace, exactly as ``Composite`` formals
      bind to parent nodes.
    - ``wires`` are local-frame ``build_wires()`` entries (``Wire`` or plain
      4-6 tuples; normalized on expansion). A wire whose ``name`` is a feed is
      renamed to that feed's actual; any other ``name`` is an internal wire,
      namespaced ``"<instance>.<name>"``; ``name is None`` stays structural.
    - ``children`` are nested :class:`Placement` s — this is what makes it a
      real hierarchy, flattened recursively with a compounded prefix.

    A formal feed must actually be produced by the cell: it must name a local
    wire, or be surfaced by a child (a child feed bound to it). A dangling
    formal is rejected at construction.
    """

    feeds: tuple[str, ...] = ()
    wires: tuple = ()
    children: tuple = ()

    def __post_init__(self):
        # Coerce the ergonomic list-literal call sites to tuples (frozen, so
        # go through object.__setattr__, the Composite idiom).
        object.__setattr__(self, "feeds", tuple(self.feeds))
        object.__setattr__(self, "wires", tuple(self.wires))
        object.__setattr__(self, "children", tuple(self.children))

        if len(set(self.feeds)) != len(self.feeds):
            raise ValueError(f"duplicate formal feed in {self.feeds!r}")
        for child in self.children:
            if not isinstance(child, Placement):
                raise ValueError(f"Cell.children hold Placements, got {child!r}")

        local_names = {as_wire(w).name for w in self.wires} - {None}
        surfaced = {a for c in self.children for a in c.feedmap.values()}
        dangling = [f for f in self.feeds if f not in local_names | surfaced]
        if dangling:
            raise ValueError(
                f"cell feed(s) {sorted(dangling)} name no local wire and are "
                "surfaced by no child placement; a formal feed must be "
                "produced by the cell it belongs to"
            )


class Placement:
    """One placement of a :class:`Cell` — the geometry-layer analog of
    :class:`~antennaknobs.network.Instance`:
    ``Placement("e0", element, Transform.translate(0, y, 0), feed="e0_feed")``.

    - ``name`` becomes the namespace prefix for the cell's internal wire names
      (``"e0.stub"``) and, later, the per-element attribution path.
    - ``transform`` is the pose. It is applied to every endpoint of the cell's
      wires (via ``Transform.hit``) and composed onto any child transforms
      down the tree (``parent.postmult(child)``, the ``TransformStack``
      semantics). Defaults to identity.
    - Keyword arguments are the formal/actual feed-wire rename map. Every key
      must be a formal feed of ``of``; the map may be partial (see the module
      docstring). Unknown formals raise immediately.
    """

    def __init__(self, name, of: Cell, transform: Transform | None = None, **feedmap):
        if not name or "." in name:
            raise ValueError(
                f"placement name {name!r} must be non-empty and contain no '.'"
                " (dots are the namespace separator)"
            )
        extra = set(feedmap) - set(of.feeds)
        if extra:
            raise ValueError(
                f"placement {name!r} binds unknown feed(s) {sorted(extra)};"
                f" cell feeds are {of.feeds!r}"
            )
        self.name = name
        self.of = of
        self.transform = transform if transform is not None else Transform()
        self.feedmap = dict(feedmap)


def _feed_map(inst, prefix, resolve):
    """Resolve ``inst``'s formal feeds to their FINAL names. A bound feed maps
    to its actual (run through ``resolve`` when nested — the actual is a name in
    the parent's namespace — or taken verbatim at the top level, where actuals
    are already final). An unbound feed defaults to ``prefix + feed``."""
    final = {}
    for f in inst.of.feeds:
        if f in inst.feedmap:
            actual = inst.feedmap[f]
            final[f] = resolve(actual) if resolve is not None else actual
        else:
            final[f] = prefix + f
    return final


def _place(inst, parent_ctm, prefix, feed_to_final, out):
    """Recursively flatten ``inst`` into ``out``. Mirrors
    ``network._expand_instance``: ``feed_to_final`` maps the cell's formals to
    FINAL names; ``prefix`` is the instance path (``"e0."`` / ``"e0.sub."``).
    Endpoints get the composed transform where circuit nodes get nothing; wire
    names get the identical formal→actual + dotted-prefix rewrite."""
    ctm = parent_ctm.postmult(inst.transform)

    def resolve(name):
        if name is None:
            return None
        if name in feed_to_final:
            return feed_to_final[name]
        return prefix + name

    for w in inst.of.wires:
        w = as_wire(w)
        out.append(
            w._replace(
                p0=ctm.hit(tuple(w.p0)),
                p1=ctm.hit(tuple(w.p1)),
                name=resolve(w.name),
            )
        )
    for child in inst.of.children:
        cprefix = prefix + child.name + "."
        child_map = _feed_map(child, cprefix, resolve)
        _place(child, ctm, cprefix, child_map, out)


def flatten_placements(placements) -> list[Wire]:
    """Flatten top-level :class:`Placement` s into a world-coordinate ``Wire``
    list ready to return from ``build_wires()`` — the design-layer analog of
    ``Network._expand_instances``.

    Every non-``None`` wire name in the result must be unique: a name is a
    ``PortOnWire``/``PortAtEnd`` target, so two wires sharing one is an
    ambiguous feed binding. This is the by-construction check that the current
    "same f-string typed in two methods" convention lacks — a collision is
    raised here instead of surfacing later as a silent open gap.
    """
    out: list[Wire] = []
    for inst in placements:
        prefix = inst.name + "."
        feed_to_final = _feed_map(inst, prefix, None)
        _place(inst, Transform(), prefix, feed_to_final, out)

    seen: dict[str, int] = {}
    for w in out:
        if w.name is not None:
            seen[w.name] = seen.get(w.name, 0) + 1
    dupes = sorted(n for n, c in seen.items() if c > 1)
    if dupes:
        raise ValueError(
            f"placements produced duplicate wire name(s) {dupes}; each feed/"
            "named wire must resolve to a unique name (bind distinct actuals)"
        )
    return out
