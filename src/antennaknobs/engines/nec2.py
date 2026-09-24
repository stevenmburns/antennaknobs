"""NEC-2 as an external-oracle engine over a text coupling — issue #1354.

antennaknobs already has NEC-2 physics in process, through `PyNECEngine` and
the `pynec-accel` wheel. What it cannot do is SHIP it: pynec-accel wraps
nec2++, which is GPLv2, so putting it in the frozen Windows workbench (#1349)
would make that zip a combined work with the source-offer and notice
obligations that carries — and would reverse the stance the published Docker
image already takes (``INCLUDE_PYNEC=0``, MIT/BSD only). Decision 2026-09-10
(Steve): leave it out.

This is the way round it, and it is the shape `NEC5Engine` already proved: drive
a **user-supplied** console binary over text — a deck written to a temp dir, the
binary run as a subprocess, its printout parsed — and never link to it.
antennaknobs then distributes nothing GPL, the in-process PyNEC lane stays for
people who install it, and the frozen bundle gains NEC-2 the moment a user
points it at a binary they very likely already have: 4nec2 ships one.

The deck is written by `nec_export.export_nec`, NOT by a second writer. That
module was built for the download button and emits the same NEC-2 dialect a
`PyNECEngine` solve resolves to, wire tuple for wire tuple, so a deck this
engine runs is a text twin of what PyNEC would have solved in process. A second
writer here is how the two would drift apart, and the drift would look like an
engine disagreement. The multiport-Y route's structure decks (AK#1678) come from
the same lines, through `nec_export.export_nec_structure`.

Two invocation forms, chosen by PROBING
---------------------------------------
There is no one NEC-2 command line, and the difference is not something a file
name can be trusted to say (a renamed binary, a wrapper script, a symlink):

* the **argument** form, ``nec2c -i deck.nec -o deck.out``, which nec2c and
  nec2++ take;
* the **stdin** form, the input and output file names on standard input — what
  4nec2's ``nec2dxs*.exe`` reads, and what NEC5CL reads too, so
  `nec5.run_deck`'s shape carries over.

So `run_deck` tries the argument form, then the stdin form, and remembers which
one answered for that binary (keyed on its identity, not its name, so replacing
it in place re-probes). Two details are load-bearing. Stdin is closed on the
argument form — a binary that accepts the flags AND would also read a file name
from stdin otherwise hangs on a pipe nobody writes to. And a printout is taken
from the output FILE if one appeared, else from stdout: some nec2c builds write
the report to standard output and leave no file, which is a working binary and
must not read as a failed run.

Exit codes are not trusted, for the reason NEC-5's wrapper does not trust them
either: these are Fortran (or Fortran-descended) programs that ``STOP`` on input
errors. The health signal is a parseable printout.

Printout format
---------------
Pinned against momwire's portal, which writes a column-exact NEC-2 printout
(``momwire/tests/fixtures/nec_portal/*.out``) because SimNEC reads it as nec2c.
The three blocks this engine parses, and how they differ from NEC-5's — which is
why the parsers are not shared:

* ``ANTENNA INPUT PARAMETERS``: ``TAG SEG Vre Vim Ire Iim Zre Zim Yre Yim P`` —
  two integers and nine numbers, the impedance at numbers 4/5. NEC-5's row has
  a third leading index, so a shared parser would read the admittance as the
  impedance on one of the two. The numbers are read by PATTERN, not by
  splitting on whitespace (AK#1641): 4nec2's ``nec2dxs`` prints fixed-width
  ``E12.5`` fields, and a negative value's minus sign takes the one separating
  space, fusing it to the field before (``7.18272E+01-8.10563E+00``). nec2c
  spaces its columns, which is why a token count passed on it and read none of
  the 861 input-parameter blocks in 1,010 real 4nec2 printouts.
* ``CURRENTS AND LOCATION``: ``SEG TAG X Y Z len Ire Iim mag phase`` — 10
  tokens, the same layout NEC-5 prints under a different heading.
* ``RADIATION PATTERNS``: angles then gains, ``TOTAL`` at index 4, and the
  ``SENSE`` word absent on a true null row, so 11 or 12 tokens. Same shape as
  NEC-5's.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import time
import tempfile
from pathlib import Path

import numpy as np

from ..engine import FarField, SimulationEngine, WireCurrents, refuse_graded_wires
from ..network import as_wire
from ..network_reduce import C_LIGHT
from . import _multiport
from ._external import find_exe, run_exe

_log = logging.getLogger(__name__)

NEC2_EXE_ENV = "NEC2_EXE"

_AIP_HEADER = "ANTENNA INPUT PARAMETERS"
# One ANTENNA INPUT PARAMETERS data row: TAG and SEG, then the rest of the line,
# whose nine numbers `_NUMBER` finds however many separators a minus sign took.
# The rest must be NOTHING but numbers: NEC-5's row carries a third leading
# index, a bare integer, and a row with a stray field is the wrong dialect, to be
# refused rather than read (a shared parser read it at the wrong columns).
_AIP_ROW_RE = re.compile(r"^\s*(\d+)\s+(\d+)(?=[\s+-])(.*)$")
_NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+)(?:[EeDd][-+]?\d+)?")
_NUMBERS_ONLY = re.compile(rf"(?:\s*{_NUMBER.pattern})+\s*")
_CURRENTS_HEADER = "CURRENTS AND LOCATION"
_PATTERN_HEADER = "RADIATION PATTERNS"

# How far the multiport Y may sit from symmetric before `_compute_y_matrix`
# refuses (AK#1678). NEC-5's tripwire, for NEC-5's reason — Y[i, j] and Y[j, i]
# come from different runs, and a current read into the wrong port breaks the
# symmetry — but NOT NEC-5's 1e-2 bar. NEC-2 tests by point matching, so its
# discrete Y is not symmetric, and on `multiband.hexbeam_5band`'s closely
# spaced feeds the asymmetry is 1.96e-2 of the ports' scale: PyNEC's own Y
# (nec2++, in process) reads 1.9557e-2 and nec2c's 1.9554e-2, the two Y
# agreeing to 5.6e-5. That is the formulation, and a gate at 1e-2 refused a
# design both NEC-2s solve identically. 1e-1 sits 5x above the worst catalog
# design and still catches a row read into the wrong port of a coupled pair.
_Y_RECIPROCITY_RTOL = 1e-1

# NEC prints -999.99 dB for a true pattern null. Kept verbatim: it is already a
# dB floor, and inventing -inf here would change what a caller plots.
NULL_GAIN_DB = -999.99

# What a NEC-2 shouts when it will not run a deck. Case-sensitive on purpose:
# the printout echoes the deck's own CM comments, and a design whose title says
# "error" must not read as one.
_ENGINE_ERROR_RE = re.compile(
    r"\bERROR\b|FAULTY|INVALID|STOP INPUT|GEOMETRY DATA CARD ERROR"
    r"|DATA CARD ERROR|not supported"
)


def _gyrator_phantoms(deck: str) -> dict[tuple[int, int], float]:
    """``{(tag, absolute segment): B}`` for every gyrator port in ``deck`` that
    carries a source: an ``NT`` with a zero diagonal and ``Y12 = Y21 = jB``
    whose port 1 is driven by an ``EX`` (AK#1648).

    That is the shape ``export_nec`` writes for a ``DrivenCurrent`` (AK#1597),
    because NEC-2 has no current-source card. The printout's ANTENNA INPUT
    PARAMETERS row for such a source is the PHANTOM's, 1/(B^2 Z) of the antenna
    behind it, so the readers map it back exactly. The deck is our own, so this
    is a lookup, not a recognition heuristic: it reads what was written.

    Keyed by the ABSOLUTE segment number, which is what the printout's rows
    carry, so each tag's segment offset comes from the deck's own GW cards.
    """
    base: dict[int, int] = {}
    acc = 0
    driven: set[tuple[int, int]] = set()
    nts = []
    for line in deck.splitlines():
        toks = line.split()
        if not toks:
            continue
        if toks[0] == "GW" and len(toks) >= 3:
            base[int(toks[1])] = acc
            acc += int(toks[2])
        elif toks[0] == "EX" and len(toks) >= 4 and toks[1] == "0":
            driven.add((int(toks[2]), int(toks[3])))
        elif toks[0] == "NT" and len(toks) >= 11:
            nts.append(toks)
    out: dict[tuple[int, int], float] = {}
    for toks in nts:
        tag, seg = int(toks[1]), int(toks[2])
        y11r, y11i, y12r, y12i, y22r, y22i = (float(x) for x in toks[5:11])
        if y11r or y11i or y22r or y22i or y12r or not y12i:
            continue
        if (tag, seg) not in driven or tag not in base:
            continue
        out[(tag, base[tag] + seg)] = y12i
    return out


# The two ways to hand a deck to a NEC-2 binary; see the module docstring.
FORM_ARGS = "args"
FORM_STDIN = "stdin"


class NEC2Error(RuntimeError):
    """NEC-2 is unavailable, refused the deck, or produced an unusable
    printout."""


def find_nec2(explicit: str | None = None) -> str | None:
    """Resolve the user-supplied NEC-2 executable: explicit path first, then
    ``$NEC2_EXE``. None when unset or not an executable file — callers decide
    whether that is an error (engine ctor) or an absence (roster, test skip).

    The same helper `find_nec5` uses, for the same reason: the two engines are
    found the same way and a second copy of the rule would drift.
    """
    return find_exe(NEC2_EXE_ENV, explicit)


def _printout(td: Path, out_name: str, proc) -> str | None:
    """The report this run produced: the output file if it appeared, else
    stdout if that carries the report. None when neither does."""
    out = td / out_name
    if out.is_file():
        text = out.read_text(errors="replace")
        if text.strip():
            return text
    stdout = proc.stdout or ""
    return stdout if _AIP_HEADER in stdout else None


def _run_form(exe: str, deck: str, form: str, timeout: float) -> str | None:
    with tempfile.TemporaryDirectory(prefix="nec2_") as td:
        tdp = Path(td)
        (tdp / "model.nec").write_text(deck)
        argv = [exe]
        stdin_text = ""
        if form == FORM_ARGS:
            argv += ["-i", "model.nec", "-o", "model.out"]
        else:
            # NEC5CL's convention: input name, output name, then a blank line.
            stdin_text = "model.nec\nmodel.out\n\n"
        try:
            # run_exe, not subprocess.run: a solve's cancel kills the binary
            # (AK#1712) instead of letting a stale run go to completion.
            proc = run_exe(argv, stdin_text=stdin_text, cwd=td, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise NEC2Error(f"NEC-2 timed out after {timeout:.0f}s") from e
        return _printout(tdp, "model.out", proc)


# path -> (mtime, size, form). Which invocation form answered for this binary,
# so a solve does not pay for the discovery every deck.
_FORM_CACHE: dict[str, tuple[float, int, str]] = {}


def _identity(exe: str) -> tuple[float, int] | None:
    try:
        st = os.stat(exe)
    except OSError:  # pragma: no cover - it existed a moment ago
        return None
    return (st.st_mtime, st.st_size)


def run_deck(exe: str, deck: str, *, timeout: float, form: str | None = None) -> str:
    """One deck through the binary, returning the printout text.

    Module-level for the reason `nec5.run_deck` is: the availability probe must
    run a deck exactly the way a solve does, because "is this the right binary"
    is not a question the filesystem can answer.

    `form` forces one invocation form; the default tries the argument form and
    then the stdin form, and caches whichever answered.
    """
    ident = _identity(exe)
    forms: tuple[str, ...]
    if form is not None:
        forms = (form,)
    else:
        cached = _FORM_CACHE.get(exe)
        if cached is not None and ident is not None and cached[:2] == ident:
            forms = (cached[2],)
        else:
            forms = (FORM_ARGS, FORM_STDIN)

    errors = []
    for f in forms:
        try:
            text = _run_form(exe, deck, f, timeout)
        except OSError as e:
            raise NEC2Error(f"{exe} could not be executed: {e}") from e
        if text is not None:
            if ident is not None:
                _FORM_CACHE[exe] = (ident[0], ident[1], f)
            return text
        errors.append(f)
    raise NEC2Error(
        f"NEC-2 produced no printout from {exe} (tried the "
        + " and the ".join(errors)
        + " form)"
    )


# A one-wire deck the probe runs to prove the binary IS a NEC-2. Half a
# wavelength at 300 MHz, three segments, centre-fed on segment 2 — the smallest
# input that prints an ANTENNA INPUT PARAMETERS block, which is what every
# solve path here parses.
#
# `XQ` is load-bearing, the same way it is in NEC-5's probe: without an
# execution request NEC reads every card, echoes the geometry and computes
# nothing, so a probe on an EN-terminated deck rejects a GENUINE binary.
_PROBE_DECK = """CM antennaknobs NEC2_EXE probe
CE
GW 1 3 0. -.25 0. 0. .25 0. .001
GE 0
EX 0 1 2 0 1. 0.
FR 0 1 0 0 300. 0.
XQ
EN
"""

# path -> (mtime, size, verdict, reason), keyed on the file's identity rather
# than its name so replacing the binary in place re-probes.
_PROBE_CACHE: dict[str, tuple[float, int, bool, str]] = {}


def probe_nec2(explicit: str | None = None, *, timeout: float = 20.0) -> str | None:
    """The resolved NEC-2 executable, or None with the reason logged.

    `find_nec2` answers "is there an executable file at $NEC2_EXE", which is a
    question about the filesystem and not about NEC-2 — and the NEC-5 lane
    already paid for that distinction: on 2026-09-09 `NEC5_EXE` pointed at an
    18 KB spy shim, the roster offered a NEC-5 tab, and the failure arrived at
    the first solve as the shim's own error text (#1339). Any wrong file does
    that.

    So this RUNS a one-wire deck once per (path, mtime, size) and requires a
    parseable printout. It doubles as the invocation-form discovery: whichever
    form answered here is cached for the solves that follow.
    """
    exe = find_nec2(explicit)
    if exe is None:
        return None
    ident = _identity(exe)
    if ident is None:
        return None
    cached = _PROBE_CACHE.get(exe)
    if cached is not None and cached[:2] == ident:
        return exe if cached[2] else None

    reason = ""
    try:
        text = run_deck(exe, _PROBE_DECK, timeout=timeout)
        ok = _AIP_HEADER in text
        if not ok:
            reason = (
                f"{exe} ran but produced no {_AIP_HEADER} block; "
                f"printout head: {text[:300]!r}"
            )
    except NEC2Error as e:
        ok, reason = False, f"{exe} is not a working NEC-2 binary: {e}"
    except OSError as e:  # not executable on this platform, bad format, ...
        ok, reason = False, f"{exe} could not be executed: {e}"

    _PROBE_CACHE[exe] = (ident[0], ident[1], ok, reason)
    if not ok:
        _log.warning("NEC-2 unavailable: %s", reason)
    return exe if ok else None


def refuse_nec2_geometry(tups, ground, *, suggest_download: bool = False) -> None:
    """Refuse geometry a NEC-2 deck cannot carry, by name, rather than let the
    binary answer.

    NEC-2's ground is a half-space boundary condition on the fields ABOVE it; the
    formulation has no below-ground medium at all. A buried wire is not rejected
    by nec2++ — it is solved **as if it were in air** and a number is printed with
    no warning, the worst failure available to an oracle. So the wrapper refuses,
    and so does the deck WRITER: handing a user a .nec of a buried antenna is the
    same wrong answer one step further away from anyone who could catch it
    (antennaknobs#1389).

    One function for both, so the app cannot offer a download of a deck its own
    NEC-2 lane would refuse. A wire lying IN the plane is refused for a related
    reason — its image coincides with itself. A wire with ONE end at z=0 is
    ordinary NEC-2 (every ground-mounted vertical) and is not refused.

    With no ground there is no plane and nothing to refuse: a free-space model may
    sit anywhere, below z=0 included.

    `suggest_download` adds the sentence the gear menu needs — the NEC-5 deck of
    the same design, which is the one the user actually wanted.
    """
    if ground is None or ground == "free":
        return
    instead = (
        " — download the NEC-5 deck instead, whose ground serves buried conductors"
        if suggest_download
        else ""
    )
    for i, t in enumerate(tups):
        w = as_wire(t)
        z0, z1 = float(w.p0[2]), float(w.p1[2])
        if z0 == 0.0 and z1 == 0.0:
            raise ValueError(
                f"wire {i + 1} lies in the ground plane (z=0), where its own "
                "image coincides with it — NEC-2's ground forbids it"
            )
        if (z0 < 0.0 < z1) or (z1 < 0.0 < z0):
            raise NotImplementedError(
                f"wire {i + 1} crosses the ground plane mid-span: NEC-2 has no "
                "below-ground medium and solves the buried part as if it were in "
                "air, so the wrapper refuses rather than report a number nothing "
                "warns about — split the wire at z=0 and run the buried part on "
                "momwire (or NEC-5)" + instead
            )
        if z0 < 0.0 or z1 < 0.0:
            raise NotImplementedError(
                f"wire {i + 1} dips below z=0: NEC-2 has no below-ground medium "
                "and solves a buried conductor as if it were in air — use the "
                "momwire engine, whose buried serve is certified, or NEC-5, whose "
                "Sommerfeld path serves it" + instead
            )


# The constructor's bare-default marker. PyNEC's DEFAULT_GROUND is what it
# resolves to, imported lazily INSIDE __init__: this module must not import
# pynec at module scope (`test_subprocess_is_the_only_coupling`).
_GROUND_DEFAULT = object()


class NEC2Engine(SimulationEngine):
    """A user-supplied NEC-2 console binary, driven over text.

    Same physics as `PyNECEngine` — it is the same code family — reached
    without linking to it. A network no card expresses (a line, a transformer,
    a virtual driver, a self-tuning tuner) is solved the way PyNEC and NEC-5
    solve it (AK#1678): one structure deck per real port, each driving that
    port's segment centre at 1 V with the others shorted, the segment currents
    read into the multiport Y, and the shared `NetworkReducer` stamping the
    network on it. A single-deck download of such a design is still refused
    (`nec_export.export_nec`), because no single deck says it.
    """

    supports_far_field = True
    # NEC-2 puts a voltage source at a segment CENTRE, so a centre feed wants
    # an odd count with the source on the middle segment — PyNECEngine's parity,
    # not NEC-5's "even" (whose source sits at a segment end).
    segment_parity = "odd"
    splits_wire_at_feed = True

    def __init__(
        self,
        builder,
        *,
        ground=_GROUND_DEFAULT,
        nec2_exe: str | None = None,
        timeout: float = 120.0,
        capture_dir=None,
    ):
        """`ground` takes PyNECEngine's spellings with PyNECEngine's meaning:
        None or "free" is free space, "pec", ("finite", eps_r, sigma)
        Sommerfeld-Norton, ("finite-fast", eps_r, sigma) reflection-
        coefficient, ("mininec", eps_r, sigma) EZNEC's MININEC-type ground
        (`GN 1` + `GD`, patterns in cliff mode; AK#1655). The bare default is the finite ground, as on PyNEC.
        An explicit None used to be folded into that default — the one
        engine on which `--ground free` silently meant finite (AK#1563)."""
        super().__init__(builder)
        if ground is _GROUND_DEFAULT:
            from .pynec import DEFAULT_GROUND

            ground = DEFAULT_GROUND
        self.ground = ground
        self._refuse_ge_minus_one_contact(self.ground)
        self.timeout = float(timeout)
        # AK#1428: with a capture dir (or `ANTENNAKNOBS_CAPTURE_DIR/nec2` from
        # the environment) every run writes `<hash>.nec` and `<hash>.out`
        # beside each other. Write-only — unlike NEC-5's #872 cache, a
        # captured NEC-2 printout is never served back.
        if capture_dir is None:
            from ..engine_capture import capture_dir_from_env

            capture_dir = capture_dir_from_env("nec2")
        self._capture_dir = Path(capture_dir).expanduser() if capture_dir else None
        if self._capture_dir is not None:
            self._capture_dir.mkdir(parents=True, exist_ok=True)
        # AK#1428: one {"deck", "printout", "cached"} per _run call, kept in
        # memory for the web lane's Files view. A run the binary faulted on is
        # recorded too: its printout is where the reason is written.
        self.io_runs: list[dict] = []
        exe = find_nec2(nec2_exe)
        if exe is None:
            raise NEC2Error(
                "no NEC-2 binary: set $NEC2_EXE (or pass nec2_exe=) to a NEC-2 "
                "console executable — nec2c, nec2++, or 4nec2's nec2dxs*.exe"
            )
        self.exe = exe
        # COERCED, not raw: `export_nec` builds its deck through a
        # `PyNECEngine`, which applies `segment_parity` to every fed or named
        # wire, so a raw `build_wires()` here would disagree with the deck the
        # binary actually ran and mis-map its currents wire by wire.
        self.tups = self._coerce_wire_tuples(builder.build_wires())
        refuse_graded_wires(self.tups, "NEC-2")
        self._check_geometry_against_ground()
        self._init_route()

    # -- the multiport-Y route (AK#1678) ------------------------------------
    def _init_route(self) -> None:
        """Choose between the single-deck route and the multiport-Y one.

        THE ROUTE DECISION is `export_nec`'s, asked the same way: a network
        whose only reducer reason is its current sources has a single-deck
        spelling (the gyrator idiom, AK#1597) and stays on `export_nec`, deck
        text unchanged; any other reason reduces. So every design this engine
        solved before is solved by the same deck, and the route only takes the
        designs `export_nec` refused.

        The PORTS are PyNEC's, resolved by a `PyNECEngine` that never solves:
        its real ports (every `PortOnWire`, a distributed one included), the
        wire each names, and the segments each drives with what weight
        (issue #477). NEC-2 and PyNEC address a port identically — a source at
        a segment CENTRE, the middle segment of an odd count (AK#1598's
        convention) — so reusing that bookkeeping is what makes this engine a
        text twin of PyNEC on this route too, rather than a second opinion on
        where a port is. The same engine then writes the structure decks
        (`nec_export.export_nec_structure`), so the wires, ground and material
        come from the one writer. The reducer is this engine's own: a
        self-tuning tuner must tune from NEC-2's Y, not PyNEC's.
        """
        self._use_reducer = False
        if self.builder.build_network() is None:
            return
        from .pynec import PyNECEngine

        probe = PyNECEngine(self.builder, ground=self.ground)
        reasons = probe._reducer_reasons()
        if not reasons or reasons == frozenset({"current-source"}):
            return
        if [as_wire(t).n_seg for t in probe.tups] != [
            as_wire(t).n_seg for t in self.tups
        ]:
            raise NEC2Error(
                "the structure decks' mesh differs from this engine's "
                "(PyNECEngine and NEC2Engine coerced the wires differently), so "
                "the currents would be read against the wrong segments"
            )
        tag_of = {
            as_wire(t).name: tag
            for tag, t in enumerate(probe.tups, start=1)
            if as_wire(t).name is not None
        }
        self._real_port_names = list(probe._real_port_names)
        # Per port: [(tag, segment, weight)], the segments its drive spans.
        self._port_drive = {
            name: [
                (tag_of[probe._port_wire_of[name]], int(seg), float(w))
                for seg, w in probe._port_drive_points[name]
            ]
            for name in self._real_port_names
        }
        self._deck_engine = probe
        # PyNEC's attribute, read the same way by the web lane: the budget
        # rows group under their instance paths, and the drives come from the
        # network's sources (`_reduced_snapshot`).
        self._network = probe._network
        self._reducer = _multiport.make_port_reducer(
            self, probe._network, self._real_port_names
        )
        self._use_reducer = True

    def _compute_y_matrix(self, wavelength):
        """Multiport short-circuit Y at the real ports: one NEC-2 run per
        port, that port driven at 1 V and every other port shorted, reading
        the current at every port into column j.

        A shorted port is simply a segment with no source: NEC-2's source is
        a delta gap at a segment centre, so an undriven segment is that gap
        closed, and its printed CENTRE current is the port's current. That is
        the reading `PyNECEngine._compute_y_matrix` takes, and it is exact on
        this basis, unlike NEC-5's knot-addressed route, which needs a probe
        source per port (AK#1629). A distributed port drives each of its
        segments at its weight and reads the weighted sum (issue #477).

        Sign convention: each wire is a GW card in its authored p0->p1
        direction and NEC-2's EX and current readout follow it, so this Y is
        in the authored-direction port convention, as PyNEC's is.
        """
        freq = C_LIGHT / wavelength / 1e6
        names = self._real_port_names
        n = len(names)
        Y = np.zeros((n, n), dtype=np.complex128)
        for j, drv in enumerate(names):
            sources = [(tag, seg, complex(w)) for tag, seg, w in self._port_drive[drv]]
            text = self._run(self.deck(freq, sources=sources))
            per_tag = self._parse_currents(text)[0]
            for i, name in enumerate(names):
                Y[i, j] = sum(
                    w * per_tag[tag][seg - 1] for tag, seg, w in self._port_drive[name]
                )
        self._y_reciprocity_rel = _multiport.check_reciprocity(
            Y, names, _Y_RECIPROCITY_RTOL, NEC2Error, "NEC-2"
        )
        return Y

    def _port_sources(self, V):
        """EX sources driving every real port at its network-resolved voltage
        `V[i]`, in `_real_port_names` order. A port the network leaves at
        exactly 0 V gets no card: an undriven segment already is that short."""
        sources = []
        for i, name in enumerate(self._real_port_names):
            v = complex(V[i])
            if v != 0:
                sources.extend(
                    (tag, seg, w * v) for tag, seg, w in self._port_drive[name]
                )
        if not sources:
            raise NEC2Error(
                "the network resolves every real port to 0 V, so there is "
                "nothing to drive the structure with"
            )
        return sources

    def _excitation(self, freq_mhz):
        """``(sources, p_source)`` for a single-deck reading at `freq_mhz`.

        On the multiport-Y route: every real port at the voltage the network
        resolves for it, and the power the network's SOURCES deliver, which is
        what a gain is per (AK#1637). ``(None, None)`` on the single-deck
        route, where the deck carries its own feeds and NEC-2's input power
        already is the source's."""
        if not self._use_reducer:
            return None, None
        state = _multiport.reduced_state(self, freq_mhz)
        return self._port_sources(state.V), float(state.p_in)

    def _to_source_gain(self, text, p_source):
        """P_structure / P_source for this run (see `_excitation`), with
        P_structure the INPUT POWER its own POWER BUDGET reports; 1.0 on the
        single-deck route."""
        if p_source is None:
            return 1.0
        return _multiport.source_gain_factor(
            self._parse_power_budget(text)["input_w"], p_source, NEC2Error
        )

    # -- refusals ---------------------------------------------------------
    def _check_geometry_against_ground(self) -> None:
        return refuse_nec2_geometry(self.tups, self.ground)

    # -- running ----------------------------------------------------------
    def deck(
        self,
        freq: float,
        *,
        npoints: int = 1,
        df: float = 0.0,
        rp=None,
        sources=None,
    ) -> str:
        """The deck for one run, from `nec_export.export_nec`.

        `rp` is (n_theta, n_phi, del_theta, del_phi) for a pattern run; None
        asks for impedance only, which `export_nec` spells as `XQ`.

        On the multiport-Y route (AK#1678) the deck is the bare structure from
        `nec_export.export_nec_structure`, driven by `sources`
        (``[(tag, segment, volts)]``) — or, when None, by every real port at
        the voltage the network resolves for it, which costs the Y runs.
        `sources` is refused on the single-deck route, whose feeds are the
        design's own.
        """
        from ..nec_export import export_nec, export_nec_structure, rp_mode

        if self._use_reducer:
            if sources is None:
                sources = self._excitation(freq)[0]
            text = export_nec_structure(
                self._deck_engine, freq=freq, sources=sources, df=df, npoints=npoints
            )
        elif sources is not None:
            raise ValueError(
                "sources= drives the multiport-Y route's structure decks; this "
                "design is solved by its own single deck"
            )
        else:
            text = export_nec(
                self.builder,
                ground=self.ground,
                freq=freq,
                df=df,
                npoints=npoints,
                include_rp=False,
            )
        if rp is None:
            return text
        n_theta, n_phi, del_theta, del_phi = rp
        card = (
            f"RP {rp_mode(self.ground)} {n_theta} {n_phi} 1000 0 0 "
            f"{del_theta:g} {del_phi:g}"
        )
        # export_nec closes with XQ then EN; the pattern card replaces the XQ
        # (an RP triggers the solve itself) so the deck runs once, not twice.
        lines = [ln for ln in text.splitlines() if ln.split()[:1] != ["XQ"]]
        assert lines[-1] == "EN", lines[-1]
        lines[-1:] = [card, "EN"]
        return "\n".join(lines) + "\n"

    def _run(self, deck: str) -> str:
        h = hashlib.sha256(deck.encode()).hexdigest()[:16]
        _log.debug(
            "NEC-2 %s: deck for %s (%d lines)\n%s", h, self.exe, deck.count("\n"), deck
        )
        t0 = time.perf_counter()
        text = run_deck(self.exe, deck, timeout=self.timeout)
        self.io_runs.append({"deck": deck, "printout": text, "cached": False})
        _log.info(
            "NEC-2 %s: %.2f s, printout %d lines",
            h,
            time.perf_counter() - t0,
            text.count("\n"),
        )
        _log.debug("NEC-2 %s: printout\n%s", h, text)
        if self._capture_dir is not None:
            (self._capture_dir / f"{h}.nec").write_text(deck)
            (self._capture_dir / f"{h}.out").write_text(text)
            _log.info(
                "NEC-2 %s: deck and printout captured under %s", h, self._capture_dir
            )
        if _AIP_HEADER not in text:
            # The binary ran and reported a fault. Say WHAT it said: without
            # this the first parser to look raises "no ANTENNA INPUT
            # PARAMETERS" or "no POWER BUDGET", which is true and useless —
            # it names the block that is missing rather than the reason.
            # Found on a design carrying an `LD 2` card, where the answer was
            # "LD type 2 is not supported by this engine".
            for line in text.splitlines():
                if _ENGINE_ERROR_RE.search(line):
                    raise NEC2Error(f"{Path(self.exe).name}: {line.strip()}")
        return text

    # -- parsers ----------------------------------------------------------
    @staticmethod
    def _parse_input_parameters(text: str) -> list[list[tuple[int, int, complex]]]:
        """Every ANTENNA INPUT PARAMETERS section, one list per frequency, each
        row (tag, seg, Z). Row layout: TAG SEG Vre Vim Ire Iim Zre Zim Yre Yim
        POWER, the impedance the 5th and 6th numbers (see the module docstring
        on why this is not NEC-5's parser, and on reading it by pattern)."""
        chunks = text.split(_AIP_HEADER)[1:]
        if not chunks:
            raise NEC2Error(f"no {_AIP_HEADER} in NEC-2 printout; tail: " + text[-500:])
        out = []
        for chunk in chunks:
            rows = [
                (tag, seg, complex(nums[4], nums[5]))
                for tag, seg, nums in NEC2Engine._aip_rows(chunk)
            ]
            if not rows:
                raise NEC2Error(f"unparseable {_AIP_HEADER} section")
            out.append(rows)
        return out

    @staticmethod
    def _aip_rows(chunk: str) -> list[tuple[int, int, list[float]]]:
        """The data rows of one ANTENNA INPUT PARAMETERS block, as (tag, seg,
        [Vre, Vim, Ire, Iim, Zre, Zim, Yre, Yim, P]), stopping at the first
        line after them that is not one.

        By pattern rather than by token count (AK#1641): see the module
        docstring for the fused ``nec2dxs`` fields. A header line has no two
        leading integers, a row with anything but numbers after them (NEC-5's
        third index) is refused, and so is one whose numbers are not nine."""
        rows: list[tuple[int, int, list[float]]] = []
        for line in chunk.splitlines():
            m = _AIP_ROW_RE.match(line)
            rest = m.group(3) if m else ""
            nums = (
                [float(x) for x in _NUMBER.findall(rest)]
                if _NUMBERS_ONLY.fullmatch(rest)
                else []
            )
            if len(nums) != 9:
                if rows:
                    break
                continue
            rows.append((int(m.group(1)), int(m.group(2)), nums))
        return rows

    @staticmethod
    def _parse_currents(text: str) -> list[dict[int, list[complex]]]:
        """Every CURRENTS AND LOCATION section, one dict per frequency mapping
        tag -> segment-centre currents in segment order. Row layout: SEG TAG X
        Y Z len Ire Iim mag phase — 10 tokens."""
        chunks = text.split(_CURRENTS_HEADER)[1:]
        out = []
        for chunk in chunks:
            per_tag: dict[int, list[complex]] = {}
            started = False
            for line in chunk.splitlines():
                toks = line.split()
                if len(toks) != 10:
                    if started:
                        break
                    continue
                try:
                    tag = int(toks[1])
                    cur = complex(float(toks[6]), float(toks[7]))
                except ValueError:
                    if started:
                        break
                    continue
                started = True
                per_tag.setdefault(tag, []).append(cur)
            if per_tag:
                out.append(per_tag)
        if not out:
            raise NEC2Error(f"no {_CURRENTS_HEADER} section in NEC-2 printout")
        return out

    @staticmethod
    def _parse_radiation_patterns(text: str) -> dict[tuple[float, float], float]:
        """The RADIATION PATTERNS section as {(theta, phi): total gain dB}.

        Row layout: THETA PHI VERT HORIZ TOTAL AXIAL TILT [SENSE] E(TH)mag
        phase E(PHI)mag phase — 12 tokens with the SENSE word, 11 when it is
        blank on a true null row. The angles and TOTAL sit at fixed leading
        positions either way, which is what makes the count tolerance safe.
        """
        try:
            chunk = text.split(_PATTERN_HEADER, 1)[1]
        except IndexError:
            raise NEC2Error(
                f"no {_PATTERN_HEADER} in NEC-2 printout; tail: " + text[-500:]
            ) from None
        gains: dict[tuple[float, float], float] = {}
        started = False
        for line in chunk.splitlines():
            toks = line.split()
            if len(toks) not in (11, 12):
                if started:
                    break
                continue
            try:
                theta, phi = float(toks[0]), float(toks[1])
                total = float(toks[4])
            except ValueError:
                if started:
                    break
                continue
            started = True
            gains[(round(theta, 2), round(phi, 2))] = total
        if not gains:
            raise NEC2Error(f"unparseable {_PATTERN_HEADER} section")
        return gains

    @staticmethod
    def _parse_feed_voltages(text: str) -> list[complex]:
        """The DRIVE VALUE of each feed, from the printout's own VOLTAGE columns.

        Taken from the report rather than reconstructed from the deck, because
        the report is what the binary was actually driven with — and because
        this engine has no resolved-feed list of its own to reconstruct from:
        `nec_export.export_nec` builds and discards the `PyNECEngine` that
        resolves them. Row layout as `_parse_input_parameters`: V the first two
        numbers.
        """
        chunks = text.split(_AIP_HEADER)[1:]
        if not chunks:
            raise NEC2Error(f"no {_AIP_HEADER} in NEC-2 printout")
        return [
            complex(nums[0], nums[1])
            for _t, _s, nums in NEC2Engine._aip_rows(chunks[0])
        ]

    @staticmethod
    def _parse_power_budget(text: str) -> dict:
        """The POWER BUDGET block, in the same keys `NEC5Engine` returns.

        NEC-2's block, and the spellings are its own::

            INPUT POWER   =  1.1068E-02 Watts
            RADIATED POWER=  1.1068E-02 Watts
            STRUCTURE LOSS=  0.0000E+00 Watts
            NETWORK LOSS  =  0.0000E+00 Watts
            EFFICIENCY    =  100.00 Percent

        Two differences from NEC-5's that a shared parser would get wrong: the
        conductor loss is ``STRUCTURE LOSS`` rather than ``WIRE LOSS``, and
        there is a ``NETWORK LOSS`` line NEC-5 has no counterpart for. The
        label match is on the label text and not on a column, because
        ``RADIATED POWER=`` carries no space before its ``=``.

        Raises rather than returning partial: a budget with a missing line is
        how an efficiency of 1.0 gets shipped as if it were measured.
        """
        try:
            chunk = text.split("POWER BUDGET", 1)[1]
        except IndexError:
            raise NEC2Error("no POWER BUDGET in NEC-2 printout") from None
        keys = {
            "INPUT POWER": "input_w",
            "RADIATED POWER": "radiated_w",
            "STRUCTURE LOSS": "wire_loss_w",
            "NETWORK LOSS": "network_loss_w",
            "EFFICIENCY": "efficiency_pct",
        }
        out: dict = {}
        for line in chunk.splitlines()[:12]:
            for label, key in keys.items():
                if label in line and "=" in line:
                    out[key] = float(line.split("=", 1)[1].split()[0])
        missing = set(keys.values()) - set(out)
        if missing:
            raise NEC2Error(
                f"incomplete POWER BUDGET section: missing {sorted(missing)}, "
                f"parsed {out}"
            )
        return out

    def solve_snapshot(self):
        """One binary run serving the whole web-solve contract: impedances,
        knot currents and the power budget from ONE printout.

        `impedance()` and `current_distribution()` each spawn a process, and a
        web solve must not pay twice. Also stamps the duck-typed
        ``_excited_efficiency`` / ``_excited_p_in`` / ``_excited_power_budget``
        the web adapter's efficiency and budget helpers read on every engine.

        **ONLY this method stamps them** — not `impedance()`, not
        `current_distribution()`. `PyNECEngine` differs here: its
        `current_distribution()` stamps them as a side effect of the in-process
        solve it already has, so a caller that works on the PyNEC engine can
        read nothing on this one. The web lane calls `solve_snapshot`, so it is
        served; `cli.py`'s ``--power`` schematic annotation and the pattern
        command call `current_distribution()` and then read the attributes, so
        on this engine they find None and omit the power table. That is a
        missing annotation and not a wrong number — both sites guard with
        ``if budget and p_in`` — but it is why a NEC-2 or NEC-5 run prints no
        budget there where a PyNEC run does.

        THE BUDGET IS NOT OPTIONAL. Those attributes have plausible fallbacks —
        `getattr(eng, "_excited_efficiency", 1.0)` — and a NEC-2 tab reporting
        100 % efficiency because nothing was parsed is the same shape of wrong
        answer as the buried wire this engine refuses: confident, unwarned, and
        indistinguishable from a real result. So a printout with no budget
        raises, and the sentence names what was missing.

        A plain ``XQ`` deck already carries the block — measured through
        momwire's portal, which writes nec2c's printout column for column, on a
        43-segment and a 1376-segment deck. A build that needs a pattern
        request to print one gets ONE retry with the smallest possible ``RP``
        (1x1, measured at ~10 ms of the 0.45 s / 1.10 s those decks cost, i.e.
        inside the process-startup noise); if that printout has no budget
        either, the solve refuses.
        """
        if self._use_reducer:
            return self._reduced_snapshot()
        deck, text, budget = self._run_with_budget(self.builder.freq)
        zs = self._impedances(self._parse_input_parameters(text)[0], deck)
        currents = self._currents_from(self._parse_currents(text)[0])
        self._excited_efficiency = budget["efficiency_pct"] / 100.0
        self._excited_p_in = budget["input_w"]
        # LOSSES ONLY — see the power-budget protocol comment in
        # `antennaknobs.engine`. The radiated power is NOT a budget row: every
        # consumer subtracts the rows from the input to get what reaches the
        # antenna, so listing P_rad there printed "antenna (accepted): 0 %" on a
        # lossless design where momwire printed 100 % (issue #1354).
        self._excited_power_budget = [("Wire loss", budget["wire_loss_w"])]
        if budget["network_loss_w"]:
            # NEC-5's block has no counterpart, so this row only appears here.
            self._excited_power_budget.append(
                ("Network loss", budget["network_loss_w"])
            )
        self._excited_p_radiated = budget["radiated_w"]
        # The per-feed drive values and their units ("V" / "A"), for the web
        # lane's multi-feed response.
        drives = self._drives(text, deck)
        self._excited_feed_values = [v for v, _ in drives]
        self._excited_feed_units = [u for _, u in drives]
        return zs, currents, budget

    def _run_with_budget(self, freq, sources=None):
        """``(deck, printout, budget)`` for one run that must carry a POWER
        BUDGET, with `solve_snapshot`'s one 1x1-RP retry for a build that
        prints the budget only on a pattern request."""
        deck = self.deck(freq, sources=sources)
        text = self._run(deck)
        try:
            budget = self._parse_power_budget(text)
        except NEC2Error:
            text = self._run(self.deck(freq, rp=(1, 1, 0, 0), sources=sources))
            self.io_runs[-1]["note"] = (
                "re-run with a 1x1 RP card: the first printout had no power budget"
            )
            budget = self._parse_power_budget(text)
        return deck, text, budget

    def _reduced_snapshot(self):
        """`solve_snapshot` on the multiport-Y route: the Y runs once, for the
        impedances AND the port voltages, then one deck driving every real port
        for the currents and NEC-2's structure loss. NEC-5's
        `_reduced_snapshot`, with the budget assembled by the same helper: the
        network's input power and losses from the reducer, which the structure
        deck cannot see, and NEC-2's conductor loss folded in."""
        f = self.builder.freq
        state = _multiport.reduced_state(self, f, impedances=True)
        _deck, text, budget = self._run_with_budget(
            f, sources=self._port_sources(state.V)
        )
        currents = self._currents_from(self._parse_currents(text)[0])
        # LOSSES ONLY (issue #1354). The structure deck carries no NT card, so
        # NEC-2's NETWORK LOSS line is zero here; the network's losses are the
        # reducer's rows.
        self._excited_efficiency, self._excited_power_budget = (
            _multiport.fold_wire_loss(
                state.efficiency, state.p_in, state.budget, budget["wire_loss_w"]
            )
        )
        self._excited_p_in = state.p_in
        self._excited_p_radiated = budget["radiated_w"]
        # The drives are the network's SOURCES, one per impedance: the
        # structure deck's EX cards carry the resolved port voltages, which are
        # not what the user drives (AK#1657's units come with them).
        drives = [
            (complex(s.current), "A")
            if hasattr(s, "current")
            else (complex(s.voltage), "V")
            for s in self._network.sources
        ]
        self._excited_feed_values = [v for v, _ in drives]
        self._excited_feed_units = [u for _, u in drives]
        return state.zs, currents, budget

    # -- the engine surface ----------------------------------------------
    def _impedances(self, rows, deck: str | None = None) -> list[complex]:
        """One impedance per EX row; a row on one of the deck's own gyrator
        phantoms reads as the antenna behind it, 1/(B^2 Z) (AK#1648)."""
        phantoms = _gyrator_phantoms(deck) if deck else {}
        out = []
        for tag, seg, z in rows:
            b = phantoms.get((tag, seg))
            out.append(z if b is None or z == 0 else 1.0 / (b * b * z))
        return out

    def _drives(self, text: str, deck: str) -> list[tuple[complex, str]]:
        """Each feed's drive value (`_parse_feed_voltages`) and its unit, with
        a gyrator phantom's EMF V read back as the current it forces,
        I = -jB V (AK#1648), since that is the feed's drive: amps there, volts
        everywhere else (AK#1657). Both readers walk the same ANTENNA INPUT
        PARAMETERS rows in the same order."""
        values = self._parse_feed_voltages(text)
        phantoms = _gyrator_phantoms(deck)
        if not phantoms:
            return [(v, "V") for v in values]
        rows = self._parse_input_parameters(text)[0]
        out = []
        for (tag, seg, _z), v in zip(rows, values, strict=True):
            b = phantoms.get((tag, seg))
            out.append((v, "V") if b is None else (-1j * b * v, "A"))
        return out

    def impedance(self):
        """One impedance per driven port, in EX-card order.

        A LIST even for a single feed, which is `PyNECEngine`'s and
        `NEC5Engine`'s contract: a caller that unpacks the sequence works on
        every engine, where a scalar-for-one special case makes the shape
        depend on the design.
        """
        if self._use_reducer:
            return list(_multiport.reduced_impedance(self, self.builder.freq))
        deck = self.deck(self.builder.freq)
        rows = self._parse_input_parameters(self._run(deck))
        zs = self._impedances(rows[0], deck)
        if not zs:
            raise NEC2Error("NEC-2 printed no driving-point impedance")
        return zs

    def impedance_sweep(self, freqs):
        """(n_freqs, n_ports) impedances — one binary run per frequency.

        NEC-2's FR card can step a uniform grid in one run, and this
        deliberately does not: the sweep endpoints ask for arbitrary frequency
        lists, and a per-point run is the shape that always answers. Batching a
        uniform grid is an optimisation, not a correctness change.
        """
        if self._use_reducer:
            return _multiport.reduced_impedance_sweep(self, freqs)
        freqs = np.asarray(freqs, dtype=float)
        if freqs.ndim != 1 or freqs.size == 0:
            raise ValueError("freqs must be a 1-D non-empty array")
        out = []
        for f in freqs:
            deck = self.deck(float(f))
            rows = self._parse_input_parameters(self._run(deck))
            out.append(self._impedances(rows[0], deck))
        return np.array(out)

    def current_distribution(self):
        text = self._run(self.deck(self.builder.freq))
        per_tag = self._parse_currents(text)[0]
        return self._currents_from(per_tag)

    def _currents_from(self, per_tag) -> list[WireCurrents]:
        """One `WireCurrents` per exported wire: n_seg+1 KNOT positions, with
        interior knots the average of the two adjacent segment-centre currents.

        `PyNECEngine.current_distribution`'s rule exactly, because this is the
        same physics reached a different way and the web UI renders both with
        one renderer: a boundary knot goes to zero at a genuine free end (the
        open-wire boundary condition) but carries the adjacent centre current at
        a JUNCTION, where the current is continuous through the shared point.
        Without that, a one-segment feed stub — both ends junctions — would
        render zero current along its whole length while sitting at a current
        maximum, opening a visible gap right at the feed. An end on the ground
        plane is joined too: `export_nec` writes ``GE 1``, which bonds it
        (issue #1638: a vertical's base read 0 A).

        `export_nec` writes one GW per wire tuple with tag = index + 1, so the
        tag IS the wire.
        """

        def _key(p):
            return tuple(np.round(np.asarray(p, dtype=float), 6))

        endpoint_count: dict = {}
        for t in self.tups:
            for p in (as_wire(t).p0, as_wire(t).p1):
                endpoint_count[_key(p)] = endpoint_count.get(_key(p), 0) + 1
        bonded = self.ground not in (None, "free")

        def _joined(p):
            return endpoint_count.get(_key(p), 0) >= 2 or (
                bonded and float(p[2]) == 0.0
            )

        out = []
        for i, t in enumerate(self.tups):
            w = as_wire(t)
            n_seg = int(w.n_seg)
            cur_per_seg = np.asarray(per_tag.get(i + 1, []), dtype=np.complex128)
            if cur_per_seg.shape[0] != n_seg:
                raise NEC2Error(
                    f"tag {i + 1}: expected {n_seg} segment currents, got "
                    f"{cur_per_seg.shape[0]}"
                )
            knots = np.linspace(
                np.asarray(w.p0, dtype=float), np.asarray(w.p1, dtype=float), n_seg + 1
            )
            knot_cur = np.zeros(n_seg + 1, dtype=np.complex128)
            if n_seg >= 2:
                knot_cur[1:-1] = 0.5 * (cur_per_seg[:-1] + cur_per_seg[1:])
            if n_seg >= 1:
                if _joined(w.p0):
                    knot_cur[0] = cur_per_seg[0]
                if _joined(w.p1):
                    knot_cur[-1] = cur_per_seg[-1]
            out.append(WireCurrents(knot_positions=knots, knot_currents=knot_cur))
        return self._authored_currents(out)

    def far_field(self, *, n_theta=90, n_phi=360, del_theta=1, del_phi=1):
        # Same grid contract as PyNECEngine._collect_pattern: the upper
        # hemisphere in theta (0 .. 90-del from zenith), full circle in phi
        # with the 360-degree seam duplicated.
        assert 90 % n_theta == 0 and 90 == del_theta * n_theta
        assert 360 % n_phi == 0 and 360 == del_phi * n_phi
        f = self.builder.freq
        # On the multiport-Y route the deck drives every real port at its
        # network-resolved voltage, and the gain is rescaled per SOURCE watt,
        # as NEC-5's and PyNEC's are (AK#1637).
        sources, p_source = self._excitation(f)
        text = self._run(
            self.deck(f, rp=(n_theta, n_phi, del_theta, del_phi), sources=sources)
        )
        gains = self._parse_radiation_patterns(text)
        if p_source is not None:
            shift_db = 10.0 * np.log10(self._to_source_gain(text, p_source))
            gains = {
                k: g if g <= NULL_GAIN_DB else g + shift_db for k, g in gains.items()
            }
        thetas = np.arange(n_theta) * del_theta
        phis = np.arange(n_phi + 1) * del_phi
        rings = []
        for th in thetas:
            ring = [
                gains[(round(float(th), 2), round(float(ph % 360.0), 2))] for ph in phis
            ]
            rings.append(ring)
        flat = [g for ring in rings for g in ring if g > NULL_GAIN_DB]
        return FarField(
            rings=rings,
            max_gain=max(flat) if flat else NULL_GAIN_DB,
            min_gain=min(flat) if flat else NULL_GAIN_DB,
            thetas=thetas.astype(float),
            phis=phis.astype(float),
        )
