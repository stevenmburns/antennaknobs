"""Export an antennaknobs builder to a NEC-5 card deck (``.nec``).

The NEC-2 twin of this is `nec_export.export_nec`. Both exist for the same
reason — a user wants the file, whatever engines are on their machine — and
neither needs an engine binary to write one: `NEC5Engine(require_exe=False)` is
the deck-writer mode issue #1376 added for the catalog export.

**One writer, two callers.** `scripts/nec5_corpus/export_catalog_nec5.py` wrote
the header and stripped the engine's own ``CM`` line itself, and the app's
Download button (#1389) needs the same bytes — so the header lives here and both
call it. A second copy is how the download and the corpus tool's
``catalog-nec5/`` would come to disagree about the same design, and the
disagreement would look like a bug in one of the engines rather than in a
comment.

What this refuses, and it is a different list from the NEC-2 writer's:

* **TL / virtual-driver networks** — refused by BOTH writers. NEC-5 has no
  native card for them either; the app solves them by a multiport-Y reduction
  outside the field solve, one deck per driven port, so there is no faithful
  SINGLE deck. (The catalog export writes the per-port decks instead, which is
  a set of files rather than a download.)
* **Buried, ground-contact and graded designs** — served here and refused by
  the NEC-2 writer. That asymmetry is the whole point of #1389: the user who
  most needs a deck for `verticals.buried_radial_vertical` was being handed
  PyNEC's refusal for a deck they never asked for.
"""

from __future__ import annotations

from .engines.nec5 import NEC5Engine, _network_needs_reducer

# The engine stamps its own comment line; the exported deck carries a header
# that says which design, mesh and ground it is instead.
_ENGINE_CM = "CM antennaknobs NEC5Engine deck\n"

_LICENCE_CM = "MIT licence, github.com/stevenmburns/antennaknobs"


def catalog_header(design: str, rung: str, ground_name: str, freq_mhz, note: str = ""):
    """The two (or three) ``CM`` lines every exported NEC-5 deck opens with.

    Byte-for-byte the header `export_catalog_nec5.py` has written since #1376,
    because the app's download of a design at a catalog rung and ground must be
    the same file the corpus tool's zip ships for it — that equality is the gate
    on #1389, and it only holds if there is one spelling of this text.
    """
    header = (
        f"CM antennaknobs catalog design {design} ({rung} mesh, {ground_name} ground)\n"
        f"CM {freq_mhz} MHz; {_LICENCE_CM}\n"
    )
    if note:
        header += f"CM {note}\n"
    return header


def export_nec5(
    builder,
    *,
    ground=None,
    freq=None,
    design: str,
    rung: str,
    ground_name: str,
    header_freq=None,
    note: str = "",
    sources=None,
) -> str:
    """Return a NEC-5 card deck (str) for ``builder``.

    ground       : NEC5Engine's spec — None/"free", "pec",
                   ("finite", eps_r, sigma).
    freq         : solve frequency in MHz for the FR card; defaults to
                   ``builder.freq``.
    design       : dotted design name for the header.
    rung / ground_name : the header's words for this mesh and ground.
    header_freq  : the frequency the HEADER names, when it differs from the
                   card's — the catalog export names the design's own frequency
                   while writing a rung-scaled builder. Defaults to ``freq``.
    sources      : passed through to `NEC5Engine.deck` for a per-port deck.
    """
    freq = float(builder.freq if freq is None else freq)
    eng = NEC5Engine(builder, ground=ground, require_exe=False)
    if sources is None and _network_needs_reducer(builder.build_network()):
        raise NotImplementedError(
            "NEC-5 export of TL/virtual-driver networks (and distributed "
            "finite-gap ports) is not supported: the app solves those by a "
            "multiport-Y reduction over one deck per driven port, not by native "
            "NEC-5 cards, so there is no faithful single-deck representation."
        )
    deck = eng.deck([freq], sources=sources)
    header = catalog_header(
        design,
        rung,
        ground_name,
        freq if header_freq is None else header_freq,
        note=note,
    )
    return header + deck.replace(_ENGINE_CM, "", 1)
