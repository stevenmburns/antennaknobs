"""The import note for a deck that asks for a momwire feature (Steve, 11-26).

momwire 0.98.0 lets a NEC deck turn a feature on for itself with a comment
card, ``CM momwire: pair_reuse``, and its drop-ins and executables act on it.
antennaknobs does not: it passes every momwire feature explicitly from its own
checkboxes, and an option that changes an answer is never turned on by deck
text. What an import does instead is say so, once, and name the checkbox that
does the same thing.

This module reads nothing into any request. It returns sentences for
``ui_params["notes"]`` and has no other effect, so the engine keywords and the
served defaults are the same with a card as without one
(`tests/test_deck_pragma_note.py`).

The card grammar is momwire's (`momwire._features.deck_pragmas`, reached
through ``antennaknobs.mw``): a momwire that has no reader gives no note,
decided by a live probe and never by a version. Which names are offered is the
served roster's: a name no momwire engine here takes as an option (unknown to
this momwire, or not certified on this platform) is reported as not available
rather than silently dropped.
"""

from __future__ import annotations

from collections.abc import Iterable

from . import mw

#: The prefix of the environment variable momwire's drop-ins read for a
#: feature (``MOMWIRE_X_<NAME>``); SimNEC's NEC portal can set one with
#: ``NECOptions.OSEnv`` (`simnec_import`).
ENV_PREFIX = "MOMWIRE_X_"


def env_feature(name: str, value: str) -> str | None:
    """The feature an ``OSEnv`` assignment of ``name`` to ``value`` asks for,
    or None when it is another variable or a false-looking value.

    The name must be spelled as momwire reads it, upper case throughout; a
    value is false when it is empty, zero, or one of no/false/off."""
    if not name.startswith(ENV_PREFIX) or name != name.upper():
        return None
    feature = name[len(ENV_PREFIX) :].lower()
    word = value.strip().strip("\"'").strip().lower()
    if not feature or word in ("", "0", "0.0", "no", "n", "false", "off"):
        return None
    return feature


def _served_labels() -> dict[str, str]:
    """Feature name -> the label of the option the app serves for it, over the
    momwire engines the roster offers it on. Computed on use: the roster
    follows live probes of the installed momwire."""
    # On use: the adapter loads every engine. Through `web.examples`, never
    # the adapter first: the adapter imports `web.examples` part way down and
    # that module calls `adapter.register_all()`, so entering at the adapter
    # meets a half-built module (an import from the CLI, with no web server).
    from .web import examples  # noqa: F401, PLC0415
    from .web import adapter  # noqa: PLC0415

    labels: dict[str, str] = {}
    for row in adapter.backend_roster(have_pynec=False):
        if row["kind"] != "momwire":
            continue
        for key in row["model_kwargs"]:
            spec = adapter._OPTION_SPECS.get(key)
            if spec is not None and spec.kind == "bool":
                labels.setdefault(key, spec.label)
    return labels


def pragma_notes(
    deck_text: str = "", *, also: Iterable[tuple[str, str]] = ()
) -> list[str]:
    """One note per feature the deck asks for, in the order asked.

    ``deck_text`` is scanned for ``CM momwire: <name>`` cards; ``also`` is
    ``(name, how it was asked)`` pairs from a source that is not a card (an
    ``.ssn``'s ``OSEnv`` line). A feature asked twice, in either way, gets one
    note. No request and no momwire reader give ``[]``."""
    asked: dict[str, str] = {}
    for name in mw.deck_pragmas(deck_text):
        asked.setdefault(name, f"momwire: {name}")
    for name, how in also:
        asked.setdefault(name, how)
    if not asked:
        return []
    labels = _served_labels()
    notes = []
    for name, how in asked.items():
        words = name.replace("_", " ")
        if name in labels:
            notes.append(
                f"This file asks for {words} ({how}). antennaknobs does not "
                f"act on it; tick '{labels[name]}' in the speed "
                "options to use it."
            )
        else:
            notes.append(
                f"This file asks for {words} ({how}), which is not available "
                "here. antennaknobs does not act on it."
            )
    return notes
