"""The engine names antennaknobs reads, and the deprecated spellings of them
(momwire#2091, adopted with the momwire 0.97.0 pin).

A momwire basis's SHORT name carries no dash and names the basis alone:
``bs2`` (the B-spline, degree 2, the default), ``bs1`` (degree 1), ``sg``
(sinusoidal-Galerkin), ``razor2p`` (NEC-5's formulation twin); ``sinusoidal``,
``pulse``, ``hmatrix`` and ``arrayblock`` are unchanged. A LONG name is
dialect then basis (``nec5-bs2``, ``nec42-sinusoidal``), the form momwire's
launchers take. ``bs42`` and ``sin42`` are not names: they fold the dialect
into the basis.

THE ONE TABLE. `DEPRECATED_NAMES` maps each spelling that shipped before the
rename to the name it now answers as; it is momwire's ``BASIS_ALIASES``
restated, not imported, because the momwire this repo's CI runs at its
recorded pointer may predate it. ``tests/test_engine_names_2091.py`` holds the
two equal wherever the installed momwire carries the table.

Every reader canonicalises at its entry (the CLI's ``--engine``, the web
request's ``momwire_model``, a saved slot's ``backend`` through the served
``backend_aliases``, an analysis's engine specs, a keep file), so nothing past
the entry sees an alias and nothing antennaknobs prints names one. The
aliases go no earlier than two minor momwire releases after 0.97.0, with
momwire's.

`RETIRED_NAMES` are refused BY NAME wherever an engine is read, with the name
to use, as momwire refuses them: ``razor-nec5`` (deprecated since momwire#785)
is not carried forward as an alias.

Stdlib only: `analyses` imports this, and it stays light.
"""

from __future__ import annotations

from types import MappingProxyType

__all__ = [
    "DEPRECATED_NAMES",
    "RETIRED_NAMES",
    "RetiredEngineName",
    "canonical_basis",
    "canonical_engine_spec",
    "canonical_model",
    "retired_refusal",
]

DEPRECATED_NAMES = MappingProxyType(
    {
        "bspline": "bs2",
        "bspline-d1": "bs1",
        "sinusoidal-galerkin": "sg",
        "razor-2p": "razor2p",
    }
)

RETIRED_NAMES = MappingProxyType({"razor-nec5": "razor2p"})


class RetiredEngineName(ValueError):
    """A retired basis name, refused with the name to use instead."""


def retired_refusal(name: str | None) -> str | None:
    """The sentence refusing a retired basis name, or None for any other."""
    replacement = RETIRED_NAMES.get(name or "")
    if replacement is None:
        return None
    return (
        f"basis {name!r} was renamed and is no longer accepted; "
        f"use {replacement!r} (momwire#2091)"
    )


def canonical_basis(name: str) -> str:
    """The canonical short name `name` answers as: `name` itself unless it is
    a deprecated spelling. A retired name raises `RetiredEngineName`; an
    unknown one passes through, so each reader still refuses it in its own
    words."""
    refusal = retired_refusal(name)
    if refusal is not None:
        raise RetiredEngineName(refusal)
    return DEPRECATED_NAMES.get(name, name)


def canonical_model(name: object) -> object:
    """A web request's ``momwire_model`` (or a saved slot's ``backend``) as
    its canonical name: a deprecated spelling mapped, anything else -- an
    unknown name, None, a non-string -- returned as given, for the reader to
    judge. ``razor-nec5`` was never a web name, so it is not refused here."""
    if isinstance(name, str):
        return DEPRECATED_NAMES.get(name, name)
    return name


def canonical_engine_spec(spec: str) -> str:
    """An ``--engine`` spec with its momwire basis canonicalised
    (``momwire:razor-2p`` -> ``momwire:razor2p``). Any other engine's spec,
    and a bare ``momwire``, pass through unchanged."""
    name, sep, basis = spec.partition(":")
    if name != "momwire" or not sep:
        return spec
    return f"{name}:{canonical_basis(basis)}"
