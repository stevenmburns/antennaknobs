"""ASCII for the free text a NEC deck carries on its comment cards.

A NEC card deck is ASCII. The engines that read one are Fortran or C console
programs reading fixed-column records, and the decks they are handed are files
the workbench writes with an explicit encoding, never the platform default:
Windows' cp1252 has no Ω or λ, so a default-encoded write of such a deck
raised before the engine ever ran. The only free text a writer puts on a card
is a ``CM`` comment, chiefly a design's name, which for a dropped-in file is
its file name and can be anything the user typed. So every writer folds that
text here and the deck stays ASCII: the readable folds below first, then
accents dropped (é to e), then ``?`` for anything left.
"""

from __future__ import annotations

import unicodedata

_FOLD = {
    "–": "-",  # en dash
    "—": "-",  # em dash
    "−": "-",  # minus sign
    "µ": "u",  # micro sign
    "μ": "u",  # Greek mu
    "°": " deg",
    "Ω": "ohm",
    "Ω": "ohm",  # ohm sign
    "λ": "lambda",
    "½": "1/2",
    "¼": "1/4",
    "¾": "3/4",
    "×": "x",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
}


def card_text(text: str) -> str:
    """``text`` as ASCII for a comment card."""
    folded = "".join(_FOLD.get(c, c) for c in text)
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(c)
    )
    return plain.encode("ascii", errors="replace").decode("ascii")
