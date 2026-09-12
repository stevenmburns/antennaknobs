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
engine disagreement.

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
  **11** tokens with the impedance at 6/7. NEC-5's row has a third leading
  index and 12 tokens with the impedance at 7/8, so a shared parser would read
  the admittance as the impedance on one of the two.
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
from ._external import find_exe

_log = logging.getLogger(__name__)

NEC2_EXE_ENV = "NEC2_EXE"

_AIP_HEADER = "ANTENNA INPUT PARAMETERS"
_CURRENTS_HEADER = "CURRENTS AND LOCATION"
_PATTERN_HEADER = "RADIATION PATTERNS"

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
            proc = subprocess.run(
                argv,
                input=stdin_text,
                text=True,
                capture_output=True,
                cwd=td,
                timeout=timeout,
            )
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


class NEC2Engine(SimulationEngine):
    """A user-supplied NEC-2 console binary, driven over text.

    Same physics as `PyNECEngine` — it is the same code family — reached
    without linking to it. Where the two differ is worth knowing before
    comparing numbers: PyNEC solves TL / virtual-driver networks by a
    multiport-Y reduction outside the field solve, and there is no faithful
    single-deck spelling of that, so `nec_export.export_nec` refuses those and
    so does this engine. A design PyNEC serves and this refuses is that.
    """

    supports_far_field = True
    # NEC-2 puts a voltage source at a segment CENTRE, so a centre feed wants
    # an odd count with the source on the middle segment — PyNECEngine's parity,
    # not NEC-5's "even" (whose source sits at a segment end).
    segment_parity = "odd"

    def __init__(
        self,
        builder,
        *,
        ground=None,
        nec2_exe: str | None = None,
        timeout: float = 120.0,
        capture_dir=None,
    ):
        super().__init__(builder)
        from .pynec import DEFAULT_GROUND

        self.ground = DEFAULT_GROUND if ground is None else ground
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

    # -- refusals ---------------------------------------------------------
    def _check_geometry_against_ground(self) -> None:
        return refuse_nec2_geometry(self.tups, self.ground)

    # -- running ----------------------------------------------------------
    def deck(self, freq: float, *, npoints: int = 1, df: float = 0.0, rp=None) -> str:
        """The deck for one run, from `nec_export.export_nec`.

        `rp` is (n_theta, n_phi, del_theta, del_phi) for a pattern run; None
        asks for impedance only, which `export_nec` spells as `XQ`.
        """
        from ..nec_export import export_nec

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
        card = f"RP 0 {n_theta} {n_phi} 1000 0 0 {del_theta:g} {del_phi:g}"
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
        POWER — 11 tokens, impedance at 6/7 (see the module docstring on why
        this is not NEC-5's parser)."""
        chunks = text.split(_AIP_HEADER)[1:]
        if not chunks:
            raise NEC2Error(f"no {_AIP_HEADER} in NEC-2 printout; tail: " + text[-500:])
        out = []
        for chunk in chunks:
            rows: list[tuple[int, int, complex]] = []
            for line in chunk.splitlines():
                toks = line.split()
                if len(toks) != 11:
                    if rows:
                        break
                    continue
                try:
                    tag, seg = int(toks[0]), int(toks[1])
                    z = complex(float(toks[6]), float(toks[7]))
                except ValueError:
                    if rows:
                        break
                    continue
                rows.append((tag, seg, z))
            if not rows:
                raise NEC2Error(f"unparseable {_AIP_HEADER} section")
            out.append(rows)
        return out

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
        resolves them. Row layout as `_parse_input_parameters`: V at 2/3.
        """
        chunks = text.split(_AIP_HEADER)[1:]
        if not chunks:
            raise NEC2Error(f"no {_AIP_HEADER} in NEC-2 printout")
        out: list[complex] = []
        for line in chunks[0].splitlines():
            toks = line.split()
            if len(toks) != 11:
                if out:
                    break
                continue
            try:
                int(toks[0]), int(toks[1])
                out.append(complex(float(toks[2]), float(toks[3])))
            except ValueError:
                if out:
                    break
                continue
        return out

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
        text = self._run(self.deck(self.builder.freq))
        try:
            budget = self._parse_power_budget(text)
        except NEC2Error:
            text = self._run(self.deck(self.builder.freq, rp=(1, 1, 0, 0)))
            budget = self._parse_power_budget(text)
        zs = self._impedances(self._parse_input_parameters(text)[0])
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
        # The per-feed drive values, for the web lane's multi-feed response.
        self._excited_feed_values = self._parse_feed_voltages(text)
        return zs, currents, budget

    # -- the engine surface ----------------------------------------------
    def _impedances(self, rows) -> list[complex]:
        return [z for _tag, _seg, z in rows]

    def impedance(self):
        """One impedance per driven port, in EX-card order.

        A LIST even for a single feed, which is `PyNECEngine`'s and
        `NEC5Engine`'s contract: a caller that unpacks the sequence works on
        every engine, where a scalar-for-one special case makes the shape
        depend on the design.
        """
        rows = self._parse_input_parameters(self._run(self.deck(self.builder.freq)))
        zs = self._impedances(rows[0])
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
        freqs = np.asarray(freqs, dtype=float)
        if freqs.ndim != 1 or freqs.size == 0:
            raise ValueError("freqs must be a 1-D non-empty array")
        out = []
        for f in freqs:
            rows = self._parse_input_parameters(self._run(self.deck(float(f))))
            out.append(self._impedances(rows[0]))
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
        maximum, opening a visible gap right at the feed.

        `export_nec` writes one GW per wire tuple with tag = index + 1, so the
        tag IS the wire.
        """

        def _key(p):
            return tuple(np.round(np.asarray(p, dtype=float), 6))

        endpoint_count: dict = {}
        for t in self.tups:
            for p in (as_wire(t).p0, as_wire(t).p1):
                endpoint_count[_key(p)] = endpoint_count.get(_key(p), 0) + 1

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
                if endpoint_count.get(_key(w.p0), 0) >= 2:
                    knot_cur[0] = cur_per_seg[0]
                if endpoint_count.get(_key(w.p1), 0) >= 2:
                    knot_cur[-1] = cur_per_seg[-1]
            out.append(WireCurrents(knot_positions=knots, knot_currents=knot_cur))
        return out

    def far_field(self, *, n_theta=90, n_phi=360, del_theta=1, del_phi=1):
        # Same grid contract as PyNECEngine._collect_pattern: the upper
        # hemisphere in theta (0 .. 90-del from zenith), full circle in phi
        # with the 360-degree seam duplicated.
        assert 90 % n_theta == 0 and 90 == del_theta * n_theta
        assert 360 % n_phi == 0 and 360 == del_phi * n_phi
        text = self._run(
            self.deck(self.builder.freq, rp=(n_theta, n_phi, del_theta, del_phi))
        )
        gains = self._parse_radiation_patterns(text)
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
