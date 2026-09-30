"""Studies: analyses over several designs (AK#1757, sweep-framework step 7).

A design's ``build_analyses()`` is a METHOD: an analysis there may omit
``designs=`` and mean "this design". A **study** is the same `analyses.Analysis`
returned by a module-level FUNCTION, ``build_studies()``, which has no
``self``: so a study must name its designs (``an.Cross(designs=(...))``), and
one that does not is refused by name. Otherwise it is the same spec, the same
runner (`analysis_run.run`), the same views and the same ``to_code()``.

A study has two forms (Steve, 2026-09-30):

- a MODULE-LEVEL ``build_studies()`` function: a study of peers, naming every
  design it crosses (E7: the two feed spellings of the inverted vee). Listed
  on every design tab it crosses;
- a ``Builder.build_studies(self)`` METHOD: this design against a few
  references. ``self`` is implicit, as in ``build_analyses()``: ``designs=``
  lists only the references, and the cross's cells are this design FIRST,
  then them (an explicit self among them is dropped, not drawn twice). Listed
  on its own design's tab only (`Study.includes`), and in ``analyze
  --list-studies --builder <that design>``.

Where module-level studies are found (docs/design/sweep-framework-step7.md,
ruling 1):

- a ``build_studies()`` in a catalog design module (E7 sits beside the two
  designs it compares, in ``designs/dipoles/invvee.py``);
- ``.py`` files in the user **studies folder**, ``~/.antennaknobs/studies/``
  (``$ANTENNAKNOBS_STUDIES_DIR``), a sibling of the designs folder. Subfolders
  are name parts, as the catalog's ``family.design`` is: ``feeds/e7.py`` is
  the source ``feeds/e7``. A study file is Python, so it goes through the
  user designs' trust gate (`design_trust`, with the studies folder's own
  store) and is never imported until allowed.

Names. A study is ``<source>:<analysis name>``: ``dipoles.invvee:feed
spelling (E7)``, ``feeds/e7:my study``, and a method study's source is its
design (``user.my_vee:vs yagi``). Unique by construction, because a catalog
source is ``family.design`` (a dot, never a slash), a user source is the
file's path under the folder, whose parts may hold neither a dot nor a colon
(`_user_source`), a method study's source is a design name, which only that
design module's own module-level studies share, and the name after the FIRST
colon is the analysis's own, unique within its source (two alike are both
refused, as `analyses.problems` refuses two alike in one design; `pool`
applies that across the two forms). The colon is the split
because a source can never contain one, while an analysis name may contain
anything. The picker shows the short part (the analysis name) under its
Studies group, since the group and the tab already say where it is from;
`find` takes the full name, the source when it holds one study, or the bare
analysis name when only one study has it.

Listing is cheap: a catalog module is imported only when its source text
defines ``build_studies`` at module level (a text check, not an import of all
113 catalog modules), and the catalog's studies are cached for the process,
since the installed package does not change under it. The user folder is
re-read on every call, as the user designs are, so an edit is seen live.
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import os
import re
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from . import analyses as an
from . import design_screen, design_trust

#: Separates a study's source from its analysis name (module docstring).
SEP = ":"
_MODULE_PREFIX = "antennaknobs._user_studies"
_DEFINES = re.compile(r"^def build_studies\s*\(", re.MULTILINE)


def default_studies_dir() -> Path:
    """The user studies folder: ``$ANTENNAKNOBS_STUDIES_DIR`` if set, else
    ``~/.antennaknobs/studies``, as `user_designs.default_user_dir` resolves
    the designs folder. Read fresh each call so tests can redirect it."""
    env = os.environ.get("ANTENNAKNOBS_STUDIES_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".antennaknobs" / "studies"


@dataclass(frozen=True)
class Study:
    """One runnable study: ``analysis`` from ``source`` (a catalog module's
    ``family.design``, a user file's path under the studies folder without
    ``.py``, or, for a method study, the design it is hosted on); ``path``
    the user file, None otherwise. ``host`` is set on a METHOD study only:
    the design whose ``Builder.build_studies()`` returned it."""

    source: str
    analysis: an.Analysis
    path: Path | None = None
    host: str | None = None

    @property
    def name(self) -> str:
        return f"{self.source}{SEP}{self.analysis.name}"

    @property
    def designs(self) -> tuple[str, ...]:
        """The designs it crosses, as written."""
        return next(c.designs for c in self.analysis.crosses if c.kind == "designs")

    def includes(self, design: str) -> bool:
        """Whether ``design``'s tab lists this study (a registry name,
        ``family.design[:variant]``): a module-level study on every design it
        crosses; a method study on its own design only, so a reference design
        (a Yagi everyone compares against) is not filled with everyone's
        comparisons (Steve, 2026-09-30). A study names designs, not variants:
        a variant's tab shows the studies of its design."""
        me = self_name(design)
        if self.host is not None:
            return me == self.host
        return me in self.designs


@dataclass(frozen=True)
class Blocked:
    """What was found but cannot run, and why: a user file not allowed yet
    (``allow`` set, the command that allows it), a module that fails to
    load, or one study refused by name (``name`` set)."""

    source: str
    reason: str
    path: Path | None = None
    name: str | None = None
    allow: str | None = None

    @property
    def label(self) -> str:
        return f"{self.source}{SEP}{self.name}" if self.name else self.source


@dataclass(frozen=True)
class Found:
    studies: tuple[Study, ...]
    blocked: tuple[Blocked, ...]


def _names_designs(a: an.Analysis) -> bool:
    return any(c.kind == "designs" for c in a.crosses)


def self_name(design: str) -> str:
    """The design name a tab or ``--builder`` stands for, as a design cross
    names it: without a variant (a cross builds each design at its own
    defaults, and ``/analyses`` crosses registry names), an ``@file`` spec
    whole (its path may hold a colon)."""
    return design if design.startswith("@") else design.partition(":")[0]


def _with_self(a: an.Analysis, me: str) -> an.Analysis:
    """A method study's analysis with its design cross made whole: this
    design first, then the references as written, an explicit ``me`` among
    them dropped (it is already the first cell, and a design named twice is
    two curves drawn over each other)."""
    crosses = tuple(
        an.Cross(designs=(me, *(d for d in c.designs if d != me)))
        if c.kind == "designs"
        else c
        for c in a.crosses
    )
    return dataclasses.replace(a, cross=crosses)


def _collect(
    source: str, fn, path: Path | None, host: str | None = None
) -> tuple[list, list]:
    """``fn()``'s studies, each refused by name where it breaks the rule.
    ``host`` set: ``fn`` is that design's ``Builder.build_studies`` (the
    method form), whose ``designs=`` lists only the references."""
    try:
        got = list(fn())
    except Exception as e:  # noqa: BLE001 — a user's study function, reported by name
        return [], [Blocked(source, f"build_studies() raised {e!r}", path)]
    studies, blocked = [], []
    names = [a.name for a in got if isinstance(a, an.Analysis)]
    for a in got:
        if not isinstance(a, an.Analysis):
            blocked.append(
                Blocked(
                    source,
                    f"build_studies() returned {a!r}, not an an.Analysis",
                    path,
                )
            )
            continue
        if names.count(a.name) > 1:
            # Names pick one study (`find`); two alike is a spec to fix.
            reason = (
                f"REFUSED: {names.count(a.name)} studies in {source} are named "
                f"{a.name!r}; give one a name="
            )
        elif not _names_designs(a) and host is not None:
            reason = (
                "REFUSED: a Builder's study names the designs it compares "
                "this one with, an.Cross(designs=(...)); without them it is "
                "an analysis of this design, which belongs in build_analyses()"
            )
        elif not _names_designs(a):
            reason = (
                "REFUSED: a study names its designs, an.Cross(designs=(...)); "
                "it is a function, with no 'this design' to fall back on "
                "(an analysis of one design belongs in its build_analyses())"
            )
        elif host is not None:
            studies.append(Study(source, _with_self(a, host), path, host=host))
            continue
        else:
            studies.append(Study(source, a, path))
            continue
        blocked.append(Blocked(source, reason, path, name=a.name))
    return studies, blocked


# ── the catalog ────────────────────────────────────────────────────────────


def _catalog_modules() -> list[str]:
    """``family.design`` of each catalog module whose source defines
    ``build_studies`` at module level. A text check, so listing does not
    import the whole catalog (module docstring)."""
    import antennaknobs.designs as designs

    out = []
    for root in map(Path, designs.__path__):
        for f in sorted(root.glob("*/*.py")):
            if f.name.startswith("_") or f.parent.name.startswith(("_", ".")):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if _DEFINES.search(text):
                out.append(f"{f.parent.name}.{f.stem}")
    return sorted(set(out))


@cache
def _catalog() -> Found:
    studies, blocked = [], []
    for source in _catalog_modules():
        mod = importlib.import_module(f"antennaknobs.designs.{source}")
        fn = getattr(mod, "build_studies", None)
        # A module that imports another's function is not its source.
        if fn is None or getattr(fn, "__module__", None) != mod.__name__:
            continue
        s, b = _collect(source, fn, None)
        studies += s
        blocked += b
    return Found(tuple(studies), tuple(blocked))


# ── the user folder ────────────────────────────────────────────────────────


def _user_source(path: Path, root: Path) -> tuple[str | None, str | None]:
    """``path``'s source (its path under ``root``, ``/``-joined, no
    ``.py``), or None and why its name cannot be one."""
    parts = path.relative_to(root).with_suffix("").parts
    bad = [p for p in parts if "." in p or SEP in p]
    if bad:
        return None, (
            f"the name part {bad[0]!r} holds a '.' or a '{SEP}': a study file's "
            "path parts are plain names ('.' is the catalog's family.design, "
            f"'{SEP}' separates a study's source from its name)"
        )
    return "/".join(parts), None


def study_files(root: Path | None = None) -> list[tuple[str | None, Path, str | None]]:
    """``(source, path, why_not)`` for every ``.py`` under the studies folder,
    recursively, skipping private names (``_x``, ``.x``, as the designs
    folder does) at any level."""
    root = default_studies_dir() if root is None else root
    if not root.is_dir():
        return []
    out = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).parts
        if any(p.startswith(("_", ".")) for p in rel):
            continue
        source, why = _user_source(path, root)
        out.append((source, path, why))
    return out


def find_study_file(name: str) -> Path | None:
    """The user study file ``name`` names: its source (``feeds/e7``) or its
    path under the folder (``feeds/e7.py``), or None."""
    name = name.removesuffix(".py")
    for source, path, _ in study_files():
        if source == name:
            return path
    return None


def allow_command(source: str) -> str:
    return f"antennaknobs allow {source}"


def _load(path: Path, source: str):
    """Import a trusted study file by path (re-executed each call, so edits
    are seen) and return the module."""
    modname = f"{_MODULE_PREFIX}.{source.replace('/', '__')}"
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create an import spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(modname, None)
        raise
    return mod


def _user() -> Found:
    studies, blocked = [], []
    for source, path, why in study_files():
        label = source or path.name
        if why:
            blocked.append(Blocked(label, why, path))
            continue
        if not design_trust.is_trusted(path):
            # Never imported: the advisory screen reads the text only.
            report = design_screen.screen_file(path)
            blocked.append(
                Blocked(
                    source,
                    f"NOT ALLOWED: not allowed to run yet ({report.summary()}); "
                    f"review it, then `{allow_command(source)}`",
                    path,
                    allow=allow_command(source),
                )
            )
            continue
        try:
            mod = _load(path, source)
        except Exception as e:  # noqa: BLE001 — a user's file, reported by name
            blocked.append(Blocked(source, f"failed to load: {e!r}", path))
            continue
        fn = getattr(mod, "build_studies", None)
        if fn is None:
            blocked.append(Blocked(source, "defines no build_studies() function", path))
            continue
        s, b = _collect(source, fn, path)
        studies += s
        blocked += b
    return Found(tuple(studies), tuple(blocked))


# ── the method form ────────────────────────────────────────────────────────


def of_builder(design: str, builder) -> Found:
    """The METHOD studies of ``builder`` (an instance of ``design``): what
    its ``build_studies()`` returns, each with this design as the first cell
    of its design cross (`_with_self`), hosted on ``design`` and sourced by
    it, so ``dipoles.foo``'s method study ``vs yagi`` is
    ``dipoles.foo:vs yagi``."""
    fn = getattr(builder, "build_studies", None)
    if fn is None:
        return Found((), ())
    me = self_name(design)
    s, b = _collect(me, fn, None, host=me)
    return Found(tuple(s), tuple(b))


def pool(design: str | None = None, builder=None) -> Found:
    """Every module-level study, plus ``design``'s method studies when a
    design (and its ``builder`` instance) is given.

    One namespace per source: a design module's own module-level studies and
    its Builder's method studies are both ``family.design:name``, so a name
    the two forms share is refused, both of them, by name, as two alike in
    one form are. Every other pair of full names differs by construction
    (module docstring): a method study's source is its design's name, which
    only that design's module-level studies share."""
    found = discover()
    if design is None or builder is None:
        return found
    own = of_builder(design, builder)
    names = [s.name for s in found.studies + own.studies]
    twice = {n for n in names if names.count(n) > 1}
    keep = [s for s in found.studies + own.studies if s.name not in twice]
    refused = [
        Blocked(
            s.source,
            f"REFUSED: {names.count(s.name)} studies are named "
            f"{s.analysis.name!r} in {s.source} (its module's build_studies() "
            "and its Builder's); give one a name=",
            name=s.analysis.name,
        )
        for s in found.studies + own.studies
        if s.name in twice
    ]
    return Found(tuple(keep), found.blocked + own.blocked + tuple(refused))


# ── all of them ────────────────────────────────────────────────────────────


def discover() -> Found:
    """Every module-level study, the catalog's first, then the user
    folder's. Method studies are per design (`of_builder`, `pool`)."""
    cat, user = _catalog(), _user()
    return Found(cat.studies + user.studies, cat.blocked + user.blocked)


def including(design: str, found: Found | None = None) -> list[Study]:
    """The studies ``design``'s tab lists (`Study.includes`)."""
    found = discover() if found is None else found
    return [s for s in found.studies if s.includes(design)]


def find(name: str, found: Found | None = None) -> Study:
    """The study ``name`` names: its full name (``source:analysis``), its
    source when that holds one study, or its analysis name when one study
    has it. A SystemExit naming the candidates otherwise, and the reason
    when the name is a blocked one."""
    found = discover() if found is None else found
    by_rule = (
        [s for s in found.studies if s.name == name],
        [s for s in found.studies if s.source == name],
        [s for s in found.studies if s.analysis.name == name],
    )
    for hits in by_rule:
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise SystemExit(
                f"study {name!r} is ambiguous; give one of "
                + ", ".join(repr(s.name) for s in hits)
            )
    source = name.partition(SEP)[0]
    for b in found.blocked:
        # A whole file blocked (not allowed, failing to load) blocks every
        # study in it, named by its full name too.
        if name in (b.label, b.source, b.name) or (
            b.name is None and source == b.source
        ):
            raise SystemExit(f"study {b.label!r}: {b.reason}")
    names = ", ".join(repr(s.name) for s in found.studies) or "none"
    raise SystemExit(f"no study {name!r}; studies: {names}")


def cache_clear() -> None:
    """Forget the catalog's studies (tests that patch a catalog module)."""
    _catalog.cache_clear()
