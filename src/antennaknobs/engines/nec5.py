"""NEC-5 (LLNL) as an external-oracle engine — issue #825, stage 1.

NEC-5 is licensed software: this engine drives a **user-supplied**
executable and antennaknobs never bundles, ships, or hosts it (the EULA
recorded on #824 forbids SaaS use, so this engine must never join the
hosted web roster). The binary is located via the ``NEC5_EXE`` environment
variable or the ``nec5_exe=`` constructor argument.

Deck dialect facts come from the NEC-5 Users Manual only — never from the
Fortran source that ships beside the binary (clean-room rule, #824). The
stage-1 dialect deltas vs NEC-2 that shape this module:

- Voltage sources sit at a segment END (a knot), not a segment center:
  ``EX 0 tag seg 2`` places the source at end 2 of ``seg``. Center-feeding
  therefore wants an EVEN segment count with the source at end 2 of
  segment ``n_seg // 2`` — hence ``segment_parity = "even"``.
- Input is near-free-format (comma/space separated); blanks inside a
  record are NOT zero-defaults.
- ``GE I1 I2`` grew an error-check flag I2 (0 = default: check and stop
  on errors). Buried decks ride ``I2 = -1`` so the below-plane geometry
  is accepted — the spelling the momwire#567 anchor captures pinned
  against the binary's own printouts (the buried stage of this wrapper).

The printout layout is not documented in the manual; the parsers below are
pinned by captured printouts committed under ``tests/fixtures/nec5/``
(End-User Reports per the license, cited LLNL-CODE-746721).
"""

from __future__ import annotations

import hashlib
import os
import re
import logging
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from ..engine import FarField, SimulationEngine, WireCurrents, vertex_only_names
from ._external import find_exe, run_exe
from ._nec_wire import (
    BURIED_JACKET_ADVISORY_CARDS,
    JACKET_COMMENT_CARDS,
    has_buried_jacketed_wire,
    nec_wire_material,
)
from ..wire_catalog import gap_knot, port_at, port_wire
from ..network import (
    Driven,
    DrivenCurrent,
    GradedSegments,
    Load,
    PortAtVertex,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    as_wire,
)
from . import _multiport

C_LIGHT = 299_792_458.0

NEC5_EXE_ENV = "NEC5_EXE"

_AIP_HEADER = "ANTENNA INPUT PARAMETERS"
_CURRENTS_HEADER = "- - - Wire Currents - - -"
_PATTERN_HEADER = "- - - RADIATION PATTERNS - - -"

# NEC-5 prints -999.99 dB for a true pattern null (zero field on axis).
NULL_GAIN_DB = -999.99


# The reference switch for #1280's route. On (the default), a network NEC-5
# has no native cards for takes the multiport-Y + shared `NetworkReducer`
# path; off, it refuses with the pre-#1280 sentence. Flipped by gates, never
# by callers — the native and reduced routes are not a user choice, they are
# what the engine can express.
_NEC5_REDUCER_ROUTE = True

# How far Y may sit from symmetric before `_compute_y_matrix` refuses.
#
# Every entry of Y is a current NEC-5 itself reports (AK#1629), so nothing
# here is interpolated any more; what is left to break symmetry is NEC-5's
# testing, which is not Galerkin, and the five-figure printout. The gate is a
# tripwire on the bookkeeping instead: a source row read into the wrong port
# breaks Y[i, j] == Y[j, i], because the two entries come from different runs.
#
# It is NOT evidence that the entries are right. The interpolation this route
# used before AK#1629 was 2.4 % out at an undriven knot, and on a symmetric
# array the error is symmetric too — the four-squares passed this gate at a
# residual of exactly 0.0 while their impedances were 10 % wrong.
_Y_RECIPROCITY_RTOL = 1e-2

# The amplitude of a PROBE source (AK#1629): an `EX` whose only job is to make
# NEC-5 print the current at an undriven port's knot. Its ANTENNA INPUT
# PARAMETERS row carries that knot's current, which the `Wire Currents` table
# cannot — it has segment centres only, and NEC-5's basis is a tent on the
# knots. 1e-20 V moves every current by 1e-20 of a port admittance, far below
# the printout's five figures. It cannot be zero: NEC-5 reads a zero-amplitude
# EX as 1 V (measured on the licensed binary), which would drive the port.
_PROBE_VOLTS = 1e-20


# The distributed-port refusal, one spelling (antennaknobs#1410): the engine
# raises it with the port's name, and the coverage grid quotes it to grey the
# NEC-5 tab before a click, so the two cannot drift apart.
DISTRIBUTED_PORT_REFUSAL = (
    "distributed (a finite-gap port spanning its whole named wire) — the NEC-5 "
    "multiport-Y route serves delta-gap ports only. PyNEC serves this by driving "
    "every segment at V/S and reading the weighted current; NEC-5's EX addresses "
    "KNOTS, so the same expansion needs a knot-weighting rule that has not been "
    "derived. Run this design on bspline or PyNEC."
)


def _network_needs_reducer(net) -> bool:
    """True iff this network carries something NEC-5 has no native card for.

    Deliberately the COMPLEMENT of what was native before #1280 rather than a
    restatement of PyNEC's list: NEC-5's native surface is sources plus plain
    `LD` loads (#825 stage 1), so anything else reduces. Writing it as "not
    natively expressible" instead of enumerating TL / TwoPort / Transformer /
    ... is what stops a new branch type silently defaulting to the native
    path and emitting no card at all.
    """
    if net is None:
        return False
    for br in net.branches:
        if not isinstance(br, Load):
            return True
        if br.ql is not None or br.qc is not None:
            # A finite-Q load re-derives R = wL/Q at every frequency; there is
            # no LD form for it, and the reducer has one (issue #298).
            return True
    for port in net.ports.values():
        if isinstance(port, PortVirtual):
            return True
        if isinstance(port, PortOnWire) and port.distributed:
            return True
    return False


def find_nec5(explicit: str | None = None) -> str | None:
    """Resolve the licensed NEC-5 executable: explicit path first, then
    ``$NEC5_EXE``. Returns None when unset or not an executable file —
    callers decide whether that is an error (engine ctor) or an absence
    (CLI roster, test skip)."""
    return find_exe(NEC5_EXE_ENV, explicit)


def run_deck(exe: str, deck: str, *, timeout: float) -> str:
    """One deck through the binary, returning the printout text.

    Module-level because the availability probe must run a deck the same way a
    solve does — NEC-5 reads its input and output FILE NAMES from stdin and
    works in intermediate files, so "is this the right binary" is not a
    question the filesystem can answer. Exit codes are not trusted (Fortran
    STOP); the printout's presence and parseability are the health signal.
    """
    with tempfile.TemporaryDirectory(prefix="nec5_") as td:
        tdp = Path(td)
        (tdp / "model.nec").write_text(deck)
        try:
            # run_exe, not subprocess.run: a solve's cancel kills the binary
            # (AK#1712) instead of letting a stale fill run to completion.
            proc = run_exe(
                [exe],
                stdin_text="model.nec\nmodel.out\n\n",
                cwd=td,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise NEC5Error(f"NEC-5 timed out after {timeout:.0f}s") from e
        out = tdp / "model.out"
        if not out.is_file():
            tail = (proc.stdout or "")[-500:] + (proc.stderr or "")[-500:]
            raise NEC5Error(f"NEC-5 produced no printout; stdout/stderr: {tail}")
        return out.read_text(errors="replace")


# A one-wire deck the probe runs to prove the binary IS NEC-5 (#1339). Half a
# wavelength at 300 MHz, three segments, centre-fed: the smallest input that
# produces an ANTENNA INPUT PARAMETERS block, which is what every solve path
# parses.
#
# `XQ 0` is load-bearing and is why this deck is copied from the shape our own
# fixtures use rather than hand-written. Without it NEC-5 reads every card,
# echoes them, prints `RUN TIME = 0.000` and exits having solved nothing — so a
# probe on an EN-terminated deck rejects the GENUINE binary, which is worse
# than the bug this fixes. Measured against the real nec5cl while writing it.
_PROBE_DECK = """CM antennaknobs NEC5_EXE probe
CE
GW 1 3 0.000000E+00 -2.500000E-01 0.000000E+00 0.000000E+00 2.500000E-01 \
0.000000E+00 1.000000E-03
GE 0
EX 0 1 2 0 1.000000E+00 0.000000E+00
FR 0 1 0 0 3.000000E+02 0.000000E+00
XQ 0
EN
""".replace("\\\n", "")

# path -> (mtime, size, verdict, reason). Keyed on the file's identity rather
# than its name so replacing the binary in place re-probes; the probe costs a
# process launch and `have_nec5()` is called per request.
_PROBE_CACHE: dict[str, tuple[float, int, bool, str]] = {}


def probe_nec5(explicit: str | None = None, *, timeout: float = 20.0) -> str | None:
    """The resolved NEC-5 executable, or None with the reason logged.

    `find_nec5` answers "is there an executable file at $NEC5_EXE", which is a
    question about the filesystem, not about NEC-5. Measured on the Windows box
    2026-09-09: NEC5_EXE pointed at an 18 KB C# spy shim, `have_nec5()` said
    yes, the app showed a NEC-5 tab, and the failure arrived at the first solve
    as the shim's own error text (#1339). Any wrong file does that — the EZNEC
    GUI exe, a copy in the wrong folder.

    So this RUNS the thing once and requires a parsable printout. On failure it
    returns None and logs the path with the head of stdout/stderr, so the
    sentence names the actual file rather than saying NEC-5 is missing.
    """
    exe = find_nec5(explicit)
    if exe is None:
        return None
    try:
        st = os.stat(exe)
        key = (st.st_mtime, st.st_size)
    except OSError:  # pragma: no cover - it existed a line ago
        return None
    cached = _PROBE_CACHE.get(exe)
    if cached is not None and (cached[0], cached[1]) == key:
        return exe if cached[2] else None

    reason = ""
    try:
        text = run_deck(exe, _PROBE_DECK, timeout=timeout)
        ok = _AIP_HEADER in text
        if not ok:
            reason = (
                f"{exe} ran but produced no ANTENNA INPUT PARAMETERS block; "
                f"printout head: {text[:300]!r}"
            )
    except NEC5Error as e:
        ok, reason = False, f"{exe} is not a working NEC-5 binary: {e}"
    except OSError as e:  # not executable on this platform, bad format, ...
        ok, reason = False, f"{exe} could not be executed: {e}"

    _PROBE_CACHE[exe] = (key[0], key[1], ok, reason)
    if not ok:
        _log.warning("NEC-5 unavailable: %s", reason)
    return exe if ok else None


_log = logging.getLogger(__name__)


class NEC5Error(RuntimeError):
    """NEC-5 is unavailable, refused the deck, or produced an unusable
    printout."""


def _num(x) -> str:
    return f"{float(x):.6E}"


def _expand_graded(w):
    """One authored wire as the GW cards it needs: ``[(p0, p1, n_seg), ...]``.

    An ordinary wire is one card and is emitted byte-identically to what this
    writer emitted before the expansion existed. A `graded_wire`
    (`GradedSegments`, momwire#674's node grading) becomes ONE CARD PER PANEL,
    chained end to end at the panel boundaries, each with that panel's own
    segment count — the same vertices and the same counts
    `flat_wires_to_polylines` puts inside a momwire polyline, so all three
    engines mesh the deck identically (issue #1108).

    This is what a card deck can express and a polyline cannot: NEC has no
    per-edge count within one GW, so the grading has to become geometry. The
    cost is that tags no longer equal "authored wire index + 1", which is why
    every tag-addressed site in this engine goes through `_tag_of`.
    """
    n_seg = w.n_seg
    if not isinstance(n_seg, GradedSegments):
        return [
            (np.asarray(w.p0, dtype=float), np.asarray(w.p1, dtype=float), int(n_seg))
        ]
    p0 = np.asarray(w.p0, dtype=float)
    p1 = np.asarray(w.p1, dtype=float)
    bounds = [0.0, *n_seg.fracs, 1.0]
    return [
        (p0 + bounds[k] * (p1 - p0), p0 + bounds[k + 1] * (p1 - p0), int(c))
        for k, c in enumerate(n_seg.counts)
    ]


def _tent_knot_currents(centres, ends, kinds):
    """Knot currents from NEC-5's printed segment-centre currents, exactly
    (issue #1638).

    NEC-5's basis is the tent, so the current is linear along every segment
    and each printed centre current is the MEAN of its two knots:
    ``k_j + k_(j+1) = 2 c_j``. Averaging adjacent centres instead, the rule
    this replaced, smooths the current twice (the far field averages knots
    back to midpoints), and zeroed a base on the ground plane outright.

    Along one wire the centres fix the knots up to a single alternating term:
    ``k_j = p_j + (-1)^j a`` with ``p_0 = 0``. The per-wire ``a`` come from
    the nodes: a FREE end's knot is zero, a JUNCTION's knots obey KCL, and a
    CONTACT (an end bonded to the ground plane) adds no equation, since the
    ground takes whatever current flows there. What the nodes leave open (a
    wire grounded at both ends, a closed loop) is exactly the alternating mode,
    which moves no midpoint; it goes to the smoothest solution.

    ``centres[i]`` is wire i's centre currents in order, ``ends[i]`` its
    (start, end) node ids, ``kinds[node]`` one of "free" / "junction" /
    "contact". Returns one knot array per wire (``len(centres[i]) + 1``).
    """
    n_w = len(centres)
    parts = []
    for c in centres:
        p = np.zeros(c.size + 1, dtype=np.complex128)
        for j in range(c.size):
            p[j + 1] = 2.0 * c[j] - p[j]
        parts.append(p)

    at: dict = {}
    for i, (a, b) in enumerate(ends):
        at.setdefault(a, []).append((i, False))
        at.setdefault(b, []).append((i, True))

    # One row per equation, in the per-wire unknowns `a`. Current flows
    # start -> end, so at a node an END contributes +k_n and a START -k_0.
    rows, rhs = [], []
    for node, touching in at.items():
        kind = kinds[node]
        if kind == "contact":
            continue
        if kind == "free":
            for i, is_end in touching:
                row = np.zeros(n_w)
                if is_end:
                    row[i] = (-1.0) ** centres[i].size
                    rhs.append(-parts[i][-1])
                else:
                    row[i] = 1.0
                    rhs.append(0.0)
                rows.append(row)
            continue
        row = np.zeros(n_w)
        r = 0.0
        for i, is_end in touching:
            if is_end:
                row[i] += (-1.0) ** centres[i].size
                r -= parts[i][-1]
            else:
                row[i] -= 1.0
        rows.append(row)
        rhs.append(r)

    A = np.array(rows, dtype=float).reshape(len(rows), n_w)
    b = np.array(rhs, dtype=np.complex128)
    if A.shape[0]:
        U, S, Vt = np.linalg.svd(A, full_matrices=True)
        rank = int(np.sum(S > 1e-9 * max(1.0, float(S[0]))))
        a = Vt[:rank].T @ ((U[:, :rank].T @ b) / S[:rank])
    else:
        Vt = np.eye(n_w)
        rank = 0
        a = np.zeros(n_w, dtype=np.complex128)
    null = Vt[rank:].T
    if null.shape[1]:
        # Smoothest: minimise sum |k_(j+1) - k_j|^2 over the free directions.
        # Per wire, dk_j = dp_j + a * d_j with d_j = 2(-1)^(j+1), so the
        # roughness is diagonal in `a`: H = 4n, gradient term g = <d, dp>.
        h = np.array([4.0 * c.size for c in centres])
        g = np.array(
            [
                np.dot(2.0 * (-1.0) ** (np.arange(c.size) + 1), np.diff(p))
                for c, p in zip(centres, parts, strict=True)
            ],
            dtype=np.complex128,
        )
        z = np.linalg.solve(null.T @ (h[:, None] * null), -null.T @ (h * a + g))
        a = a + null @ z
    return [p + (-1.0) ** np.arange(p.size) * a[i] for i, p in enumerate(parts)]


class NEC5Engine(SimulationEngine):
    """Drive a licensed NEC-5 binary through intermediate files.

    Stages 1-4 of #825: impedance, currents and radiation patterns, in
    free space or over ground (``"pec"`` / NEC-5's native Sommerfeld
    ``("finite", eps_r, sigma)`` / EZNEC's MININEC-type
    ``("mininec", eps_r, sigma)``, a bare ``GD``), fed by legacy ``Wire.ex`` entries or a
    ``build_network()`` spec whose sources sit on ``PortOnWire`` delta
    gaps — ``Driven`` as ``EX 0``, ``DrivenCurrent`` as NEC-5's native
    ``EX 4`` current source. Network branches (loads, lines) and
    NEC-5-specific physics are later stages and refuse loudly here.
    """

    supports_far_field = True  # stage 3: RP parsing
    # NEC-5 sources sit at segment ends; an even count puts a knot at the
    # fed wire's midpoint (see module docstring).
    segment_parity = "even"
    splits_wire_at_feed = True

    def __init__(
        self,
        builder,
        *,
        ground=None,
        nec5_exe=None,
        timeout=120.0,
        capture_dir=None,
        require_exe=True,
    ):
        super().__init__(builder)
        self.ground = self._normalise_ground(ground)
        self._refuse_ge_minus_one_contact(self.ground)
        exe = find_nec5(nec5_exe)
        if exe is None and require_exe:
            raise NEC5Error(
                "NEC-5 executable not found. NEC-5 is licensed software that "
                "antennaknobs cannot bundle: point NEC5_EXE (or nec5_exe=) at "
                "your licensed nec5cl binary."
            )
        # ``require_exe=False`` is for deck WRITERS — the catalog export the
        # corpus tool's release zip carries (#1376) runs on a box with no
        # engine and never solves. ``deck()`` needs no binary; a solve on an
        # engine built this way raises the same NEC5Error at run time.
        self._exe = exe
        self._timeout = float(timeout)
        # Printout capture-and-cache (issue #872 phase 0): with capture_dir
        # set, every run stores its deck and printout keyed by the deck
        # text's content hash, and a run whose printout is already captured
        # is served from disk without invoking the binary — re-analysis
        # never re-solves. The stored printouts are End-User Reports under
        # the NEC-5 license (LLNL-CODE-746721); the binary itself is never
        # copied or distributed.
        if capture_dir is None:
            # AK#1428: `ANTENNAKNOBS_CAPTURE_DIR/nec5` when the caller passes
            # nothing — the workbench exe's `--capture-dir`, the server's and
            # the CLI's launch environment all land here.
            from ..engine_capture import capture_dir_from_env

            capture_dir = capture_dir_from_env("nec5")
        self._capture_dir = Path(capture_dir).expanduser() if capture_dir else None
        if self._capture_dir is not None:
            self._capture_dir.mkdir(parents=True, exist_ok=True)
        # One dict per _run call: {"hash", "cached", "seconds"} — the
        # per-solve time log the census machinery records (#872 phase 0).
        self.run_log: list[dict] = []
        # AK#1428: one {"deck", "printout", "cached"} per _run call — the texts
        # themselves, so the web lane can show the user exactly what the binary
        # was given and what it printed. Apart from run_log, which the census
        # records as JSON and must stay small.
        self.io_runs: list[dict] = []
        if builder.build_tls():
            raise NotImplementedError(
                "NEC5Engine stage 1 does not model transmission lines"
            )
        # The network is read BEFORE parity coercion so vertex-only wires
        # can be exempted (their EX sits at an end knot, which every count
        # provides — bumping the author's mesh would be gratuitous, #898).
        network = builder.build_network()
        self._vertex_only_names = vertex_only_names(network)
        self.tups = self._coerce_wire_tuples(builder.build_wires())
        self._wires = [as_wire(t) for t in self.tups]
        network = self._network_as_meshed(network)
        # Sources, in excitation order: (wire_index, ex_type, value, knot)
        # with ex_type NEC-5's EX I1 — 0 voltage, 4 current (native in
        # NEC-5; NEC-2 has no current source) — and knot naming which knot
        # of the wire hosts the source: "center" (PortOnWire's delta gap at
        # the middle, the legacy Wire.ex spelling too) or "p0"/"p1"
        # (PortAtVertex, issue #898 — NEC-5's native series feed at the
        # wire end's junction knot).
        self._loads = []  # (wire_index, Load), filled by the network resolver
        if network is not None:
            self._sources = self._resolve_network_sources(network)
        else:
            self._sources = [
                (i, 0, complex(w.ex), "center")
                for i, w in enumerate(self._wires)
                if w.ex is not None
            ]
        if not self._sources and not getattr(self, "_use_reducer", False):
            # The reducer route carries no EX card of its own — its drive is
            # resolved from the network onto the multiport Y — so "no sources"
            # is its normal state, not a design with nothing to solve.
            raise ValueError(
                "design has no excitation (no Wire.ex entry or network "
                "source) — nothing to solve"
            )
        spec = builder.build_wire_material()
        default_radius = spec.radius if spec is not None else 0.0005
        self._radii = [
            w.spec.radius if w.spec is not None else default_radius for w in self._wires
        ]
        # Wire material (stage 5): the same LD cards export_nec emits —
        # conductor loss as LD 5 (bulk conductivity, distributed over every
        # segment) and an insulation jacket as momwire's coated-wire pair.
        # NEC-5 has NO native insulated-wire card (the full 3.2/3.3 command
        # roster carries no IS — NEC-4's card did not survive), so the pair is
        # spelled with the cards it has: the equivalent radius on GW, LD 2 for
        # the jacket's inductance, and LD 5 rescaled for the larger radius
        # (issue #1523; `_nec_wire` says why each is needed). `_radii` stays
        # the conductor's; `_gw_radii` is what the GW cards carry.
        self._gw_radii = [
            nec_wire_material(r, None, w.spec if w.spec is not None else spec).radius
            for r, w in zip(self._radii, self._wires, strict=True)
        ]
        self._wire_spec = spec
        self._has_buried_wires = False
        # Coincident-bundle first: its refusal names the `detached`
        # variant this engine DOES serve (the design-level message);
        # the generic graded-mesh refusal is the fallback for graded
        # decks with no bundle.
        self._check_no_coincident_wires()
        # A graded wire is expanded into consecutive GW cards (issue #1108)
        # rather than refused, so `_cards` — not `_wires` — is what the deck
        # is written from, and `_tag_of` is the only way to name a tag.
        self._cards = []
        self._tags_of = []
        for i, w in enumerate(self._wires):
            sub = _expand_graded(w)
            self._tags_of.append(
                tuple(range(len(self._cards) + 1, len(self._cards) + 1 + len(sub)))
            )
            self._cards.extend((i, *c) for c in sub)
        self._material_lines = self._build_material_lines()
        if self.ground is not None:
            self._check_geometry_against_ground()

    def _build_material_lines(self) -> list[str]:
        """The LD cards for wire material, built once the tags exist.

        Issue #1427: a design loaded from a file carries its material PER WIRE
        (`wire_tuples(specs=True)` — each `Wire.spec` has that GW card's
        radius and LD 5 conductivity) and defines no design-level
        `build_wire_material()`. The radius was already read per wire; the
        conductivity was read from the design-level spec only, so an imported
        deck's copper loss never reached NEC-5 (AC6LA's Example 2: 68.6−j17.8
        on the tab against 70.5−j16.2 with the load). Same rule as PyNEC's
        `_emit_wire_material` (#388): with no per-wire spec, one global card
        per effect, byte-identical to before; when any wire carries its own
        spec, every wire gets per-tag cards from its effective spec (its own,
        else the design default), one card per GW card of a graded wire. The
        two paths are exclusive — NEC stacks LD cards on a segment in series,
        so a global card plus a per-tag card would double the loss.
        """
        spec = self._wire_spec
        lines: list[str] = []
        if any(w.spec is not None for w in self._wires):
            for i, w in enumerate(self._wires):
                eff = w.spec if w.spec is not None else spec
                if eff is None:
                    continue
                mat = nec_wire_material(self._radii[i], eff.conductivity, eff)
                for tag in self._tags_of[i]:
                    if mat.conductivity is not None:
                        lines.append(f"LD 5 {tag} 0 0 {_num(mat.conductivity)} 0. 0.")
                    if mat.inductance is not None:
                        lines.append(f"LD 2 {tag} 0 0 0. {_num(mat.inductance)} 0.")
            return lines
        if spec is None:
            return lines
        mat = nec_wire_material(spec.radius, spec.conductivity, spec)
        if mat.conductivity is not None:
            lines.append(f"LD 5 0 0 0 {_num(mat.conductivity)} 0. 0.")
        if mat.inductance is not None:
            lines.append(f"LD 2 0 0 0 0. {_num(mat.inductance)} 0.")
        return lines

    def _resolve_network_sources(self, network):
        """Map a build_network() spec onto NEC-5 edge sources — stage 4 of
        #825, and the place NEC-5 natively out-expresses NEC-2: a
        ``PortOnWire`` delta gap becomes a source at the named wire's
        center knot, ``Driven`` as ``EX 0`` (volts) and ``DrivenCurrent``
        as ``EX 4`` (amps, no NEC-2 counterpart). Branches (loads, lines,
        two-ports) are #825 stage 5+ and refuse here."""
        # THE ROUTE DECISION (#1280). Everything NEC-5 has no native card for
        # — lines, two-ports, transformers, baluns, shunts, virtual ports,
        # Q-derived loads — goes through the multiport-Y + shared
        # `NetworkReducer` path PyNEC has used since #575, instead of
        # refusing. What stays native is exactly what was native before: a
        # network whose branches are all plain `Load`s, which keeps emitting
        # LD cards and is bit-identical to today.
        self._use_reducer = _NEC5_REDUCER_ROUTE and _network_needs_reducer(network)
        if not self._use_reducer:
            for br in network.branches:
                if not isinstance(br, Load):
                    raise NotImplementedError(
                        f"NEC5Engine cannot stamp a {type(br).__name__} branch "
                        "(only Load is served natively; lines/two-ports have "
                        "no NEC-5 native cards on this path)"
                    )
                if br.ql is not None or br.qc is not None:
                    raise NotImplementedError(
                        "Load ql/qc (Q-derived series R) is frequency-dependent "
                        "and has no NEC-5 LD form; spell the loss as an explicit "
                        "r= at the frequency of interest"
                    )
        by_name = {w.name: i for i, w in enumerate(self._wires) if w.name}
        if any(w.ex is not None for w in self._wires):
            raise ValueError(
                "design mixes legacy Wire.ex feeds with a build_network() "
                "spec — use one excitation style"
            )

        def wire_attachment(port_name):
            """(wire_index, knot) for a port: PortOnWire at "center",
            PortAtVertex at its authored end (issue #898 — NEC-5's native
            EX-at-knot, the series feed at a junction)."""
            port = network.ports.get(port_name)
            if port is None:
                raise ValueError(f"network names unknown port {port_name!r}")
            if isinstance(port, PortOnWireFloating):
                raise NotImplementedError(
                    "NEC5Engine cannot expose a floating port's second "
                    "terminal (no circuit stamping on this engine)"
                )
            if isinstance(port, PortAtVertex):
                idx = by_name.get(port.wire)
                if idx is None:
                    raise ValueError(
                        f"port {port_name!r} names wire {port.wire!r} which "
                        "the geometry does not carry"
                    )
                return idx, port.end
            if not isinstance(port, PortOnWire):
                raise NotImplementedError(
                    f"port {port_name!r} is virtual — NEC5Engine only serves "
                    "ports on real wires"
                )
            if port.distributed:
                raise NotImplementedError(
                    f"port {port_name!r} is distributed (finite gap) — "
                    "NEC5Engine only serves delta-gap ports"
                )
            wire = port_wire(port)
            idx = by_name.get(wire)
            if idx is None:
                raise ValueError(
                    f"port {port_name!r} names wire {wire!r} which the "
                    "geometry does not carry"
                )
            # A position along the wire is a float knot token (AK#1469); the
            # middle stays "center".
            at = port_at(port)
            return idx, "center" if at is None else float(at)

        if self._use_reducer:
            # NO EX CARDS FROM THE NETWORK on this route. The drive is the
            # reducer's to resolve — a source may even sit on a VIRTUAL port,
            # which is a circuit node no EX card can address — and the Y runs
            # below supply their own single source per port. Resolving the
            # authored sources here would refuse a legitimate design and, on
            # the ones it did not refuse, put a second feed in every Y deck.
            self._init_reducer(network, wire_attachment)
            self._loads = []
            return []
        sources = []
        for src in network.sources:
            idx, knot = wire_attachment(src.port)
            if isinstance(src, Driven):
                sources.append((idx, 0, complex(src.voltage), knot))
            elif isinstance(src, DrivenCurrent):
                sources.append((idx, 4, complex(src.current), knot))
            else:
                raise NotImplementedError(f"unsupported source type {type(src)}")
        # Loads land at the same knot as a source on that port — NEC-5's
        # series-with-the-source semantics (manual, EX card) is exactly the
        # MNA Driven+Load termination convention. A load on a VERTEX port
        # (issue #910) uses the port's own end-knot address, so a loaded
        # apex feed keeps the load in series with the source at the vertex.
        self._loads = []
        for br in network.branches:
            idx, knot = wire_attachment(br.port)
            self._loads.append((idx, knot, br))
        return sources

    # ---------- the multiport-Y route (#1280) ----------

    def _init_reducer(self, network, wire_attachment):
        """Port index map + the shared `NetworkReducer`, exactly the objects
        `PyNECEngine._init_network` builds.

        REAL PORTS ARE NOT PyNEC's SET. PyNEC's real ports are its
        `PortOnWire`s; NEC-5 also serves `PortAtVertex` natively (an EX at the
        shared knot, issue #898), and a vertex port is as real a terminal pair
        here as a centre gap. So the real set is "every port this engine can
        address with an EX card", which is what `wire_attachment` already
        answers — reusing it means the Y route and the single-source route
        cannot disagree about where a port IS.
        """
        real = [
            n
            for n, p in network.ports.items()
            if isinstance(p, (PortOnWire, PortAtVertex))
            and not (isinstance(p, PortOnWire) and p.distributed)
        ]
        self._real_port_names = real
        self._port_attach = {n: wire_attachment(n) for n in real}
        for name, port in network.ports.items():
            if name in real or isinstance(port, PortVirtual):
                continue
            if isinstance(port, PortOnWire) and port.distributed:
                raise NotImplementedError(
                    f"port {name!r} is {DISTRIBUTED_PORT_REFUSAL}"
                )
            raise NotImplementedError(
                f"port {name!r} ({type(port).__name__}) cannot be addressed on "
                "the NEC-5 multiport-Y route: it is neither an EX-addressable "
                "port on a real wire nor a virtual circuit node"
            )
        # AFTER the per-port refusals above, deliberately: a design whose only
        # real port is distributed or floating must hear WHICH port and why,
        # not the generic "no real port" sentence that excluding it produces.
        if not real:
            raise NotImplementedError(
                "this network has no port on a real wire — the NEC-5 "
                "multiport-Y route drives real terminals and reduces the "
                "circuit onto them, so a network of virtual nodes alone has "
                "nothing for it to drive. Give the design a PortOnWire or "
                "PortAtVertex terminal, or run it on bspline or PyNEC."
            )
        # A self-tuning tuner (AK#1646, #1661) is tuned here, from this engine's
        # own port admittance; a plain network gets a plain reducer. Shared
        # with NEC-2 (AK#1678).
        self._reducer = _multiport.make_port_reducer(self, network, real)

    def _compute_y_matrix(self, wavelength):
        """Multiport short-circuit Y at the real ports: one NEC-5 run per
        port, that port driven at 1 V and every other port shorted, reading
        the current at every port into column j.

        EVERY ENTRY IS A CURRENT NEC-5 REPORTS (AK#1629). A shorted port is
        spelled as a `_PROBE_VOLTS` source at its knot rather than as no card
        at all — the same short, to far below the printout's precision — so
        that its ANTENNA INPUT PARAMETERS row carries the knot's own current.

        The `Wire Currents` table cannot supply it. It carries segment CENTRES
        only, and NEC-5's basis is a tent on the knots, so a centre is the mean
        of two knot values and no interpolation between centres recovers one.
        The interpolation this replaced was 2.4 % out at an undriven centre
        knot of a ten-segment dipole and took the first segment's centre for a
        port at a wire's p0 — worst on the four-squares, whose ports all sit
        there. The DRIVEN entry always came from this block, because a delta
        gap makes dI/ds discontinuous at its knot; a probe is the same reading
        for every other port.

        Rows print in EX card order and are checked against the sources by
        tag and absolute segment, the check `_impedances_from` makes.

        Sign convention: each wire is a GW card in its authored p0→p1
        direction and NEC-5's EX and current readout follow it, so this Y is
        in the authored-direction port convention, as PyNEC's is.
        """
        freq = C_LIGHT / wavelength / 1e6
        names = self._real_port_names
        attach = [self._port_attach[name] for name in names]
        n = len(names)
        Y = np.zeros((n, n), dtype=np.complex128)
        for j in range(n):
            sources = [
                (idx, 0, complex(1.0 if i == j else _PROBE_VOLTS), knot)
                for i, (idx, knot) in enumerate(attach)
            ]
            text = self._run(self.deck([freq], sources=sources))
            rows = self._parse_input_parameters(text, current=True)[0]
            self._check_source_rows(rows, sources)
            # Driven at 1 V, a port's current IS its column of Y.
            Y[:, j] = [cur for _tag, _seg, cur in rows]
        self._check_reciprocity(Y, names)
        return Y

    def _check_reciprocity(self, Y, names):
        """Y must be symmetric, to within `_Y_RECIPROCITY_RTOL`.

        Y[i, j] and Y[j, i] come from DIFFERENT runs, so nothing about the
        arithmetic makes them agree by construction, and a row read into the
        wrong port breaks the symmetry. Agreement is not evidence the entries
        are right, though: an error that is itself symmetric passes, which is
        how the interpolated route passed this gate on the four-squares while
        10 % wrong (AK#1629). The external gate is the licensed printout.

        The gap is measured against sqrt(|Y[i,i]| |Y[j,j]|), the ports' own
        scale, not against the coupling itself (AK#1629). Measured the old way
        it refused four corpus decks NEC-5 solves correctly: on 0028 a port
        coupled at 1e-14 compared two roundoff-level entries and read 55 %, and
        on 0011/0029/0030 a weak coupling at junction ports carries an
        asymmetry that is NEC-5's own (1.8 % of Y[i,j], 1.2e-3 of the ports'
        scale) — its testing is not Galerkin, so its discrete Y need not be
        symmetric. With the gate lifted, all four reproduce the licensed
        engine run on EZNEC's own deck to 1.8e-4.
        """
        self._y_reciprocity_rel = _multiport.check_reciprocity(
            Y, names, _Y_RECIPROCITY_RTOL, NEC5Error, "NEC-5"
        )

    def _real_port_sources(self, V):
        """EX cards driving every real port at its network-resolved voltage
        `V[i]`, in `_real_port_names` order (AK#1627). A port the network
        leaves at exactly 0 V gets no card: an unfed knot is already that
        short, and NEC-5 would read a zero-amplitude EX as 1 V."""
        sources = []
        for i, name in enumerate(self._real_port_names):
            v = complex(V[i])
            if v != 0:
                idx, knot = self._port_attach[name]
                sources.append((idx, 0, v, knot))
        if not sources:
            raise NEC5Error(
                "the network resolves every real port to 0 V, so there is "
                "nothing to drive the structure with"
            )
        return sources

    def _drive_sources(self, freq_mhz):
        """The EX cards that excite this model at `freq_mhz`: its own feeds,
        or on the multiport-Y route (#1280) every real port at the voltage the
        network resolves for it (AK#1627).

        That route writes no EX of its own, which is right for the Y runs,
        which bring their own. But every single-deck reading (the pattern, the
        currents, the power budget, the web solve) went out with NO EX, so
        NEC-5 solved an unexcited structure. AC6LA's failEZN5 ended its deck
        at `***** INPUT LINE 6 EN`. PyNEC drives the same route the same way
        (`_excited_real_context`)."""
        return self._excitation(freq_mhz)[0]

    def _excitation(self, freq_mhz):
        """``(sources, p_source)``: `_drive_sources`' cards, and on the
        multiport-Y route the power the network's SOURCES deliver, which is
        what a gain is per (None on the native route, where NEC-5's own input
        power is already that).

        NEC-5 normalises gain by the power into the STRUCTURE, the sum over
        its EX cards. On this route the network sits between the sources and
        those cards, and a lossy one burns its share first: failEZN5's line
        and transformer take 48 %, and NEC-5's pattern read 2.00 dBi where the
        licensed engine, solving EZNEC's deck with the network inside it,
        reads -0.86. `_to_source_gain` takes the ratio back out."""
        if not getattr(self, "_use_reducer", False):
            return self._sources, None
        state = _multiport.reduced_state(self, freq_mhz)
        return self._real_port_sources(state.V), float(state.p_in)

    def _to_source_gain(self, text, p_source):
        """The factor turning NEC-5's gain per structure watt into gain per
        SOURCE watt (see `_excitation`): P_structure / P_source, with
        P_structure the INPUT POWER this run's own POWER BUDGET reports. 1.0
        on the native route."""
        if p_source is None:
            return 1.0
        return _multiport.source_gain_factor(
            self._parse_power_budget(text)["input_w"], p_source, NEC5Error
        )

    # ---------- ground ----------

    @staticmethod
    def _normalise_ground(ground):
        """The repo's shared ground-spec spellings, mapped onto what NEC-5
        natively serves. DIALECT TRAP: NEC-2's ``GN 0`` is the
        reflection-coefficient approximation, but NEC-5's ``IPERF 0`` is a
        full Sommerfeld solution — NEC-5 has no reflection-coefficient
        option at all, so ``("finite-fast", ...)`` refuses rather than
        silently upgrading the physics."""
        if ground is None or ground == "free":
            return None
        if ground == "pec":
            return ("pec",)
        if isinstance(ground, tuple) and len(ground) == 3 and ground[0] == "finite":
            eps_r, sigma = float(ground[1]), float(ground[2])
            if eps_r < 1.5:
                # Captured live: eps_r → 1 (with tiny sigma) returns
                # impedances in the 1e5-ohm range — the Sommerfeld table
                # machinery degenerates as the ground vanishes. Refuse the
                # corner instead of serving nonsense; real grounds sit well
                # above this bound.
                raise ValueError(
                    f"eps_r={eps_r} is too close to free space for NEC-5's "
                    "Sommerfeld tables (degenerate limit); use ground=None "
                    "for free space"
                )
            return ("finite", eps_r, sigma)
        if isinstance(ground, tuple) and len(ground) == 3 and ground[0] == "mininec":
            # EZNEC's MININEC-type ground (AK#1655): GE 1 with a bare GD.
            # The currents are the PEC ones, so no Sommerfeld table is built
            # and the near-free-space corner above cannot degenerate.
            return ("mininec", float(ground[1]), float(ground[2]))
        if isinstance(ground, tuple) and ground and ground[0] == "finite-fast":
            raise NotImplementedError(
                "NEC-5 has no reflection-coefficient ground (its IPERF 0 is "
                "a full Sommerfeld solution): use ('finite', eps_r, sigma) "
                "for NEC-5's native Sommerfeld ground"
            )
        raise ValueError(f"unrecognised ground spec: {ground!r}")

    def _check_no_coincident_wires(self):
        """Refuse geometrically coincident wires (same endpoint pair) BY
        NAME. The N-coincident-rise bundle is momwire's crossing-serve
        spelling — N coincident thin wires are deliberately a DIFFERENT
        conductor than one wire there, exactly regularized at rho_eff =
        sqrt(rho^2 + a^2) — but NEC-5 runs the overlap without complaint
        and prints garbage (measured on the buried-radial catalog design:
        3271-3374j ohm with a 2e+25 % radiated power, against the ~90 ohm
        class its own detached-radial convention prints). Same philosophy
        as the mid-span check: the wrapper refuses what the binary will
        not."""
        seen: dict[tuple, int] = {}
        for i, w in enumerate(self._wires):
            key = tuple(sorted((tuple(map(float, w.p0)), tuple(map(float, w.p1)))))
            j = seen.get(key)
            if j is not None:
                raise NotImplementedError(
                    f"wires {j + 1} and {i + 1} are geometrically "
                    "coincident (identical endpoints): the N-coincident-"
                    "rise bundle is momwire's crossing-serve spelling and "
                    "NEC-5 prints garbage for it silently — de-duplicate "
                    "the bundle, or use the detached-radial spelling "
                    "NEC-5's own convention serves (the momwire#567 "
                    "anchor deck class; on the buried-radial catalog "
                    "design that is the `detached` variant, "
                    "`verticals.buried_radial_vertical:detached`)"
                )
            seen[key] = i

    def _check_geometry_against_ground(self):
        """NEC-5's ground geometry rules, enforced at construction rather
        than by the binary's looser-than-documented checks (the stage-1
        lesson: it ran a mid-segment wire crossing without complaint).

        Above the plane nothing changed. BELOW it is the buried stage:
        wires wholly below z=0 (an end AT z=0 is legal, and is how a
        buried screen meets a contact monopole) ride NEC-5's native
        buried-wire support — the ``GE`` card's FIRST field goes ``-1``
        (the burial flag; #1025 found this wrapper had the two fields
        transposed) and the Sommerfeld ``GN 0`` card carries the medium.
        The momwire#567 anchor captures (momwire
        ``tests/golden_buried_anchor_nec5.py``, 90.051-70.731j for the
        four-radial anchor) are prints under the TRANSPOSED card and are
        banked there as such (momwire#929), not as the engine's answer;
        under the documented card a conductor stopping on the plane reads
        open-circuited, which is the third refusal below. Three refusals
        remain, each a real limit rather than an unpinned one:

        * a wire crossing the plane MID-SPAN — the binary runs it
          without complaint and prints garbage (stage-1 capture), so
          the wrapper refuses what the binary will not;
        * a wire lying IN the plane (both ends z=0);
        * buried wires under the PEC ground — image theory has no
          buried side; NEC-5's buried serve is its Sommerfeld path.
        """
        self._has_buried_wires = False
        self._has_ground_contact = False
        contact_nodes = []
        for i, w in enumerate(self._wires):
            z0, z1 = float(w.p0[2]), float(w.p1[2])
            if (z0 < 0.0 < z1) or (z1 < 0.0 < z0):
                raise NotImplementedError(
                    f"wire {i + 1} crosses the ground plane mid-span: "
                    "split it AT z=0 — NEC-5 runs a straddling wire "
                    "without complaint and prints garbage (stage-1 "
                    "capture), so the wrapper refuses it outright"
                )
            if z0 == 0.0 and z1 == 0.0:
                raise ValueError(
                    f"wire {i + 1} lies in the ground plane (z=0), which "
                    "NEC-5's ground forbids"
                )
            if z0 == 0.0:
                self._has_ground_contact = True
                contact_nodes.append(np.asarray(w.p0, dtype=float))
            if z1 == 0.0:
                self._has_ground_contact = True
                contact_nodes.append(np.asarray(w.p1, dtype=float))
            if z0 < 0.0 or z1 < 0.0:
                if self.ground[0] != "finite":
                    raise NotImplementedError(
                        f"wire {i + 1} dips below z=0: NEC-5 serves buried "
                        "conductors only over its Sommerfeld ground — use "
                        "ground=('finite', eps_r, sigma), not PEC or the "
                        "MININEC-type ground, whose currents are PEC's"
                    )
                self._has_buried_wires = True

        if self._has_buried_wires and contact_nodes:
            self._refuse_contact_without_continuation(contact_nodes)

    def _refuse_contact_without_continuation(self, contact_nodes):
        """A conductor that STOPS on the interface, in a deck that also has
        buried wires, has no NEC-5 spelling we can defend (#1025).

        The ground flag is the whole of it. A deck with buried wires must ride
        flag -1, and flag -1 leaves the current expansion unmodified — so a
        wire ending at z=0 has its current forced to zero there and no basis
        function at that node. Feeding it is refused by the binary outright,
        and a source elsewhere sees the conductor open-circuited: the
        `detached` buried-radial variant reads 598.320-54434.000j that way
        against 77.805+44.468j for the same deck with a rise.

        The other flag is not an escape. Flag 1 bonds the node and produces a
        number, which is what this wrapper used to ship — but it is documented
        as unusable when wires are buried, and the number it gives is the one
        that made NEC-5 look flat in radial count (34.6 % from momwire in R on
        the four-radial screen; the flat-curve reading on the 1937 geometry).
        A deck served under it is not served, it is answered wrong.

        So the honest answer is a refusal with the way out named: give the
        conductor something below the plane to continue into. The connected
        buried-radial spelling — a rise from the buried hub UP to the node —
        is exactly that, and it agrees with momwire to 2.6 % in R.
        """
        tol = 1e-9
        for node in contact_nodes:
            for w in self._wires:
                p0 = np.asarray(w.p0, dtype=float)
                p1 = np.asarray(w.p1, dtype=float)
                for here, other in ((p0, p1), (p1, p0)):
                    if np.allclose(here, node, atol=tol) and other[2] < -tol:
                        break
                else:
                    continue
                break
            else:
                raise NotImplementedError(
                    f"a conductor ends ON the ground plane at "
                    f"({node[0]:g}, {node[1]:g}, 0) while this deck also has "
                    "buried wires: NEC-5 has no documented spelling for that "
                    "combination. Buried wires require the ground flag that "
                    "leaves the current expansion alone, which gives a wire "
                    "ending at z=0 no basis function there — the conductor "
                    "reads as open-circuited. Continue the conductor BELOW "
                    "the interface instead (a rise from the buried hub up to "
                    "this node is the served spelling), or lift it clear of "
                    "the plane"
                )

    def _ground_lines(self) -> tuple[str, list[str]]:
        """(GE line, GN lines) for the current ground spec.

        Sommerfeld table files: NEC-5 caches its interpolation tables to
        ``SOMMPD.NEX``-style files in the cwd by default. The runner works
        in a throwaway tempdir, so the cache could never be reused anyway —
        pass the magic name NOFILE to skip writing it (manual, GN card).
        A persistent cross-run table cache (keyed by complex epsilon, which
        is all the tables depend on) is a possible later optimisation."""
        if self.ground is None:
            return "GE 0 0", []
        if self.ground[0] == "pec":
            return "GE 1 0", ["GN 1 0 0 0"]
        if self.ground[0] == "mininec":
            # The whole of EZNEC's "Real, MININEC type" ground in NEC-5 is a
            # bare GD after GE 1, no GN card at all: PEC currents, and the
            # medium on every pattern request (AK#1655). It is NOT NEC-2's
            # GD. The trailing 1, 0 are mu_r, which EZNEC writes too.
            _, eps_r, sigma = self.ground
            return "GE 1 0", [
                f"GD 0 0 0 0 {_num(eps_r)} {_num(sigma)} {_num(1.0)} {_num(0.0)}"
            ]
        _, eps_r, sigma = self.ground
        # FMUR/FMUI are written explicitly (free space's mu) so the NOFILE
        # token cannot be misread into the permeability fields — the file
        # name is positional after F4.
        #
        # GE's FIRST field is the ground flag and its SECOND is the
        # segment-check flag (antennaknobs#1025, verified against our
        # licensed materials). This wrapper used to write `GE 1 -1` for a
        # buried deck, believing the -1 selected buried support; it does
        # not, and the two settings of the first field mean opposite things
        # about a wire END that lands on z=0:
        #
        #   1  — ends at z=0 are BONDED to ground. Required by the contact
        #        class, and not usable when wires go below the surface.
        #  -1  — the ground is present but the current expansion is not
        #        modified, so a wire ending at z=0 has its current forced to
        #        ZERO there. Correct for wires that never touch the plane.
        #
        # So the flag follows the deck, not merely the presence of burial:
        #
        #   wholly buried, nothing touching z=0  ->  -1
        #   a contact end at z=0 (with or without buried wires)  ->  1
        #
        # Measured on `specialty.buried_dipole` (5.9 m dipole, 15 cm down,
        # eps_r 13 / sigma 0.005, 7.1 MHz), holding the mesh fixed: the old
        # `GE 1 ...` printed 0.0004+0.8459j and did not move with depth at
        # all (0.8459 / 0.8459 / 0.8458 at 0.15 / 1 / 2 m down), which is
        # the tell — a buried impedance must depend on depth. Its current
        # distribution carried a factor-37 spike at the source segment with
        # the phase inverted against both neighbours, so V/I there collapsed.
        # With the first field at -1 the same deck prints 146.39+44.38j /
        # 138.32+53.89j / 135.64+57.16j, which tracks momwire to 0.14/0.17/
        # 0.18 % in R across those depths.
        #
        # The second field is physics-irrelevant here: -1, 0 and 2 print the
        # same impedance to every digit. It stays 0 (the default, checks on)
        # so both spellings match the above-ground card.
        ge = "GE -1 0" if self._has_buried_wires else "GE 1 0"
        return ge, [
            f"GN 0 0 0 0 {_num(eps_r)} {_num(sigma)} {_num(1.0)} {_num(0.0)} NOFILE"
        ]

    # ---------- deck ----------

    def _parity_exempt_names(self):
        """Wires whose only attachment is a `PortAtVertex` keep their
        authored segment count: the vertex source sits at an END knot
        (segment 1 end 1 / segment n end 2), which every count provides —
        even parity exists to put a knot at the MIDDLE (issue #898)."""
        return self._vertex_only_names

    def _tag_of(self, idx):
        """The GW tag naming authored wire ``idx``.

        Not ``idx + 1`` since issue #1108: a graded wire expands into one card
        per panel, so every tag after the first graded wire shifts. A source
        or load can never address a graded wire — the geometry layer rejects
        an excitation or a port name on one, which is what makes "the FIRST
        tag" the whole answer here rather than a per-knot search.
        """
        tags = self._tags_of[idx]
        if len(tags) != 1:
            raise NEC5Error(
                f"wire {idx} is graded ({len(tags)} GW cards) and cannot host a "
                "source or a load: a port inside a graded chain would re-mesh "
                "the feed model, which is why the geometry layer rejects an "
                "excitation or a port name on a graded wire"
            )
        return tags[0]

    def _source_address(self, idx, knot):
        """NEC-5 EX addressing (tag-relative segment, end code) for a knot
        of wire ``idx``: the center knot is end 2 of the middle segment
        (even parity guarantees n_seg is even); a vertex knot is the
        wire's own end — segment 1 end 1 for ``p0``, segment n_seg end 2
        for ``p1`` (issue #898, the series apex feed)."""
        n_seg = self._wires[idx].n_seg
        if isinstance(knot, float):
            # End 2 of segment k is knot k (AK#1469). Knot 0, a port at the
            # wire's p0, has no segment 0 to name it, so it is segment 1 end 1:
            # the address `p0` takes (AK#1629).
            k = gap_knot(n_seg, knot)
            return (1, 1) if k == 0 else (k, 2)
        if knot == "center":
            return n_seg // 2, 2
        if knot == "p0":
            return 1, 1
        assert knot == "p1", knot
        return n_seg, 2

    def deck(self, freqs, *, rp=None, sources=None) -> str:
        """The NEC-5 input deck for this model at the given frequencies
        (MHz). Multiple frequencies must be uniformly spaced (NEC-5's FR
        does linear stepping); callers with a ragged grid run one deck per
        frequency.

        ``rp=(n_theta, n_phi, del_theta, del_phi)`` swaps the plain ``XQ``
        execution for an ``RP`` request on the antennaknobs pattern grid
        (theta 0..90-del from zenith, phi 0..360 inclusive of the seam
        duplicate — the same grid PyNECEngine collects).

        ``sources`` overrides the model's own feed list for ONE call, in the
        same ``(wire_index, ex_type, value, knot)`` shape `_sources` carries.
        The multiport-Y route (#1280) uses it to drive one port at a time
        without mutating the engine; every other caller passes nothing and
        gets today's deck byte for byte."""
        freqs = np.atleast_1d(np.asarray(freqs, dtype=float))
        if freqs.size > 1:
            steps = np.diff(freqs)
            if not np.allclose(steps, steps[0], rtol=1e-9, atol=0.0):
                raise ValueError("deck() needs a uniformly spaced frequency grid")
            df = float(steps[0])
        else:
            df = 0.0
        lines = ["CM antennaknobs NEC5Engine deck"]
        if self._gw_radii != self._radii:
            lines.extend(JACKET_COMMENT_CARDS)
        # AK#1677: `_has_buried_wires` is only ever True over a real
        # Sommerfeld ground (`_check_geometry_against_ground` refuses a
        # below-z=0 wire under any other ground), so this is exactly "an
        # insulated wire actually buried in soil" — the momwire#1154 gap
        # neither writer nor the a'+L' pair above can close.
        if self._has_buried_wires and has_buried_jacketed_wire(
            self._wires, self._wire_spec
        ):
            lines.extend(BURIED_JACKET_ADVISORY_CARDS)
        lines.append("CE")
        for tag, (i, p0, p1, n_seg) in enumerate(self._cards, start=1):
            r = self._gw_radii[i]
            lines.append(
                f"GW {tag} {n_seg} "
                f"{_num(p0[0])} {_num(p0[1])} {_num(p0[2])} "
                f"{_num(p1[0])} {_num(p1[1])} {_num(p1[2])} {_num(r)}"
            )
        ge_line, gn_lines = self._ground_lines()
        lines.append(ge_line)
        lines.extend(gn_lines)
        lines.extend(self._material_lines)
        for idx, knot, br in self._loads:
            # Discrete LD addressing: LDTAGF picks the segment, LDTAGT the
            # segment END (manual, LD card) — the SAME knot the port's
            # source occupies: end 2 of the middle segment for center
            # ports, the wire's own end knot for vertex ports (#910).
            seg, end = self._source_address(idx, knot)
            where = f"{self._tag_of(idx)} {seg} {end}"
            if br.z is not None:
                z = complex(br.z)
                lines.append(f"LD 4 {where} {_num(z.real)} {_num(z.imag)} 0.")
            else:
                ldtyp = 1 if br.parallel else 0
                r = float(br.r) if br.r is not None else 0.0
                el = float(br.l) if br.l is not None else 0.0
                c = float(br.c) if br.c is not None else 0.0
                lines.append(f"LD {ldtyp} {where} {_num(r)} {_num(el)} {_num(c)}")
        for idx, ex_type, value, knot in self._sources if sources is None else sources:
            seg, end = self._source_address(idx, knot)
            lines.append(
                f"EX {ex_type} {self._tag_of(idx)} {seg} {end} "
                f"{_num(value.real)} {_num(value.imag)}"
            )
        lines.append(f"FR 0 {freqs.size} 0 0 {_num(freqs[0])} {_num(df)}")
        if rp is None:
            lines.append("XQ 0")
        else:
            n_theta, n_phi, del_theta, del_phi = rp
            # RP initiates execution itself (manual: RP card). XNDA=0:
            # major/minor/total columns, no normalized table, power gain.
            lines.append(
                f"RP 0 {n_theta} {n_phi + 1} 0 0.0 0.0 "
                f"{_num(del_theta)} {_num(del_phi)}"
            )
        lines.append("EN")
        return "\n".join(lines) + "\n"

    # ---------- run ----------

    @staticmethod
    def _deck_hash(deck: str) -> str:
        """Content key for the capture cache: the deck text fully determines
        a run (same binary), so its hash names the printout."""
        return hashlib.sha256(deck.encode()).hexdigest()[:16]

    def _run(self, deck: str) -> str:
        """Run one deck through the binary and return the printout text.

        NEC-5 reads the input and output file names from stdin and works
        in intermediate files; exit codes are not trusted (Fortran STOP) —
        the printout's presence and parseability are the health signal.

        With ``capture_dir`` set, a previously captured printout for this
        exact deck is returned without invoking the binary, and fresh
        printouts are captured beside their decks (``<hash>.nec`` /
        ``<hash>.out``)."""
        h = self._deck_hash(deck)
        if self._capture_dir is not None:
            cached = self._capture_dir / f"{h}.out"
            if cached.is_file():
                self.run_log.append({"hash": h, "cached": True, "seconds": 0.0})
                _log.info("NEC-5 %s: printout served from capture %s", h, cached)
                text = cached.read_text(errors="replace")
                self.io_runs.append({"deck": deck, "printout": text, "cached": True})
                return text
        # AK#1428: at DEBUG the log carries exactly what the binary is given
        # and exactly what it prints; at INFO one line per run.
        _log.debug(
            "NEC-5 %s: deck for %s (%d lines)\n%s", h, self._exe, deck.count("\n"), deck
        )
        t0 = time.perf_counter()
        text = self._run_binary(deck)
        seconds = time.perf_counter() - t0
        self.run_log.append({"hash": h, "cached": False, "seconds": seconds})
        self.io_runs.append({"deck": deck, "printout": text, "cached": False})
        _log.info("NEC-5 %s: %.2f s, printout %d lines", h, seconds, text.count("\n"))
        _log.debug("NEC-5 %s: printout\n%s", h, text)
        if self._capture_dir is not None:
            (self._capture_dir / f"{h}.nec").write_text(deck)
            (self._capture_dir / f"{h}.out").write_text(text)
            _log.info(
                "NEC-5 %s: deck and printout captured under %s", h, self._capture_dir
            )
        return text

    def _run_binary(self, deck: str) -> str:
        if self._exe is None:
            raise NEC5Error(
                "NEC-5 executable not found: this engine was built with "
                "require_exe=False, which writes decks and cannot run them."
            )
        return run_deck(self._exe, deck, timeout=self._timeout)

    # ---------- parse ----------

    @staticmethod
    def _parse_input_parameters(
        text: str, *, current: bool = False
    ) -> list[list[tuple[int, int, complex]]]:
        """All ANTENNA INPUT PARAMETERS sections, one list per frequency,
        each row as (tag, seg, Z) — or (tag, seg, I), the source's own
        current, with ``current=True`` (the multiport-Y route's probe reading,
        AK#1629). Rows are in EX card order. Row layout (pinned by fixtures):
        tag seg sub Vre Vim Ire Iim Zre Zim Yre Yim P — 12 tokens."""
        col = 5 if current else 7
        chunks = text.split(_AIP_HEADER)[1:]
        if not chunks:
            raise NEC5Error(
                "no ANTENNA INPUT PARAMETERS in NEC-5 printout; tail: " + text[-500:]
            )
        out = []
        for chunk in chunks:
            rows = []
            for line in chunk.splitlines():
                toks = line.split()
                if len(toks) != 12:
                    if rows:
                        break
                    continue
                try:
                    tag, seg = int(toks[0]), int(toks[1])
                    val = complex(float(toks[col]), float(toks[col + 1]))
                except ValueError:
                    if rows:
                        break
                    continue
                rows.append((tag, seg, val))
            if not rows:
                raise NEC5Error("unparseable ANTENNA INPUT PARAMETERS section")
            out.append(rows)
        return out

    @staticmethod
    def _parse_wire_currents(text: str) -> list[dict[int, list[complex]]]:
        """All Wire Currents sections, one dict per frequency mapping
        tag -> segment-center currents in element order. Row layout
        (pinned by fixtures): elem tag X Y Z seglen Ire Iim mag phase —
        10 tokens, coordinates normalized by wavelength (unused here; knot
        positions come from the builder's geometry)."""
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
            raise NEC5Error("no Wire Currents section in NEC-5 printout")
        return out

    @staticmethod
    def _parse_radiation_patterns(text: str) -> dict[tuple[float, float], float]:
        """The RADIATION PATTERNS section as {(theta, phi): total_gain_dB}.
        Row layout (pinned by fixtures): THETA PHI MAJOR MINOR TOTAL AXIAL
        TILT [SENSE] E(TH)mag phase E(PHI)mag phase — 12 tokens when the
        SENSE word (LINEAR/RIGHT/LEFT) is present, 11 when it is BLANK on a
        true null row; angles and the TOTAL column sit at fixed leading
        positions either way. Null rows print -999.99 dB (kept verbatim:
        it is already a dB floor)."""
        try:
            chunk = text.split(_PATTERN_HEADER, 1)[1]
        except IndexError:
            raise NEC5Error(
                "no RADIATION PATTERNS in NEC-5 printout; tail: " + text[-500:]
            ) from None
        gains: dict[tuple[float, float], float] = {}
        started = False
        for line in chunk.splitlines():
            toks = line.split()
            if len(toks) not in (11, 12, 13):
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
            raise NEC5Error("unparseable RADIATION PATTERNS section")
        return gains

    def far_field(self, *, n_theta=90, n_phi=360, del_theta=1, del_phi=1):
        # Same grid contract as PyNECEngine._collect_pattern: the upper
        # hemisphere in theta (0 .. 90-del from zenith), full circle in phi
        # with the 360-degree seam duplicated.
        assert 90 % n_theta == 0 and 90 == del_theta * n_theta
        assert 360 % n_phi == 0 and 360 == del_phi * n_phi
        f = self.builder.freq
        sources, p_source = self._excitation(f)
        text = self._run(
            self.deck([f], rp=(n_theta, n_phi, del_theta, del_phi), sources=sources)
        )
        gains = self._parse_radiation_patterns(text)
        shift_db = 10.0 * np.log10(self._to_source_gain(text, p_source))
        thetas = np.linspace(0, 90 - del_theta, n_theta)
        phis = np.linspace(0, 360, n_phi + 1)
        rings = []
        for th in thetas:
            ring = []
            for ph in phis:
                # NEC-5 loops phi to 360 inclusive as requested; every grid
                # point must exist or the parse misread the section.
                key = (round(float(th), 2), round(float(ph), 2))
                if key not in gains:
                    raise NEC5Error(f"pattern grid point {key} missing from printout")
                g = gains[key]
                ring.append(g if g <= NULL_GAIN_DB else g + shift_db)
            rings.append(ring)
        flat = [g for ring in rings for g in ring if g > NULL_GAIN_DB]
        max_gain = max(flat) if flat else NULL_GAIN_DB
        min_gain = min(flat) if flat else NULL_GAIN_DB
        return FarField(
            rings=rings,
            max_gain=max_gain,
            min_gain=min_gain,
            thetas=thetas,
            phis=phis,
        )

    @staticmethod
    def _parse_power_budget(text: str) -> dict:
        """The POWER BUDGET section as a dict (input_w, radiated_w,
        wire_loss_w, efficiency_pct). Note the semantics pinned by capture:
        on a plain XQ run RADIATED = INPUT − WIRE LOSS even over lossy
        ground — ground absorption only shows through the average-gain
        route (see average_power_gain)."""
        try:
            chunk = text.split("- - - POWER BUDGET - - -", 1)[1]
        except IndexError:
            raise NEC5Error("no POWER BUDGET in NEC-5 printout") from None
        out = {}
        keys = {
            "INPUT POWER": "input_w",
            "RADIATED POWER": "radiated_w",
            "WIRE LOSS": "wire_loss_w",
            "EFFICIENCY": "efficiency_pct",
        }
        for line in chunk.splitlines()[:10]:
            for label, key in keys.items():
                if label in line and "=" in line:
                    out[key] = float(line.split("=", 1)[1].split()[0])
        if set(out) != set(keys.values()):
            raise NEC5Error(f"incomplete POWER BUDGET section: parsed {out}")
        return out

    def power_budget(self):
        """Run at the builder's frequency and return the parsed POWER
        BUDGET (input_w, radiated_w, wire_loss_w, efficiency_pct —
        conductor efficiency; ground absorption is not in this section)."""
        f = self.builder.freq
        return self._parse_power_budget(
            self._run(self.deck([f], sources=self._drive_sources(f)))
        )

    def average_power_gain(self, *, n_theta=18, n_phi=36):
        """(average power gain, solid angle in steradians) from an RP run
        with the A-digit set to average-and-suppress (XNDA=0002), sampling
        the upper hemisphere. Over a lossy ground the average gain is the
        ground-absorption story the plain power budget cannot tell: a
        lossless antenna radiating avg*Omega/(4*pi) of its input."""
        del_theta = 90.0 / n_theta
        del_phi = 360.0 / n_phi
        # Sample cell centers so the sector average is honest.
        f = self.builder.freq
        sources, p_source = self._excitation(f)
        lines = self.deck([f], sources=sources).splitlines()
        lines = [ln for ln in lines if not ln.startswith("XQ")]
        rp = (
            f"RP 0 {n_theta} {n_phi} 0002 {_num(del_theta / 2)} 0.0 "
            f"{_num(del_theta)} {_num(del_phi)}"
        )
        lines.insert(-1, rp)  # before EN
        text = self._run("\n".join(lines) + "\n")
        for line in text.splitlines():
            if "AVERAGE POWER GAIN" in line:
                toks = line.replace("=", " = ").split()
                avg = float(toks[toks.index("GAIN") + 2])
                avg *= self._to_source_gain(text, p_source)
                # "...SOLID ANGLE USED IN AVERAGING=( x.xxxx)*PI STERADIANS"
                m = re.search(r"AVERAGING=\(\s*([0-9.Ee+-]+)\)\*PI", line)
                if not m:
                    raise NEC5Error(f"unparseable solid angle in: {line!r}")
                return avg, float(m.group(1)) * np.pi
        raise NEC5Error("no AVERAGE POWER GAIN line in NEC-5 printout")

    def _impedances_from(self, rows: list[tuple[int, int, complex]]) -> list[complex]:
        """Match one frequency's AIP rows against this model's feeds, in
        feed order. Tags must line up — a mismatch means the deck writer
        and the printout disagree about the model, which is a bug, not a
        tolerance."""
        self._check_source_rows(rows, self._sources)
        return [z for _, _, z in rows]

    def _check_source_rows(self, rows, sources) -> None:
        """Refuse unless ``rows`` are ``sources``' AIP rows, one each, in card
        order, by tag and absolute segment."""
        # The printout's SEG. NO. is the ABSOLUTE segment number (pinned by
        # fixture: a feed at relative segment 1 of tag 3 after two 20-segment
        # wires prints as segment 41), while the deck's EX addresses
        # tag-relative — translate before comparing. End-knot sources (#898)
        # translate through the same offsets: their row prints the END
        # segment's absolute number (segment 1 or n_seg of the tag).
        # Over the CARDS, not the authored wires (issue #1108): a graded wire
        # contributes several, so "segments before this tag" is a card-level
        # sum and the tag is `_tag_of`'s.
        card_segs = [n for _i, _a, _b, n in self._cards]
        offsets = np.cumsum([0] + card_segs[:-1])
        expect = [
            (
                self._tag_of(idx),
                int(offsets[self._tags_of[idx][0] - 1])
                + self._source_address(idx, knot)[0],
            )
            for idx, _, _, knot in sources
        ]
        got = [(tag, seg) for tag, seg, _ in rows]
        if got != expect:
            raise NEC5Error(
                f"NEC-5 source rows {got} do not match the deck's feeds {expect}"
            )

    # ---------- raw-deck escape hatch ----------

    def run_deck(self, deck: str) -> list[list[tuple[int, int, complex]]]:
        """Run a caller-authored NEC-5 deck through the binary and return the
        parsed ANTENNA INPUT PARAMETERS sections — one list per frequency,
        each row ``(tag, abs_seg, Z)``.

        This is the mesh-ladder instrument for #872 phase 1+: studies that
        place sources on specific knots (``EX ... I4``) author deck text
        directly instead of going through ``deck()``'s center-feed
        convention. The engine's geometry is NOT consulted — the caller owns
        the deck — so none of ``_impedances_from``'s feed-row validation
        applies. The capture cache serves and stores these runs like any
        other."""
        return self._parse_input_parameters(self._run(deck))

    # ---------- SimulationEngine API ----------

    def impedance(self):
        if getattr(self, "_use_reducer", False):
            return _multiport.reduced_impedance(self, self.builder.freq)
        text = self._run(self.deck([self.builder.freq]))
        return self._impedances_from(self._parse_input_parameters(text)[0])

    def impedance_sweep(self, freqs):
        freqs = np.asarray(freqs, dtype=float)
        if getattr(self, "_use_reducer", False):
            # One reduction per frequency: NEC-5's FR stepping would give one
            # printout for the sweep rather than the per-f Y this route needs.
            return _multiport.reduced_impedance_sweep(self, freqs)
        if freqs.ndim != 1 or freqs.size == 0:
            raise ValueError("freqs must be a 1-D non-empty array")
        steps = np.diff(freqs)
        uniform = freqs.size == 1 or np.allclose(steps, steps[0], rtol=1e-9, atol=0.0)
        if uniform:
            per_freq = self._parse_input_parameters(self._run(self.deck(freqs)))
            if len(per_freq) != freqs.size:
                raise NEC5Error(
                    f"expected {freqs.size} frequency sections, got {len(per_freq)}"
                )
        else:
            per_freq = [
                self._parse_input_parameters(self._run(self.deck([f])))[0]
                for f in freqs
            ]
        return np.array([self._impedances_from(rows) for rows in per_freq])

    def current_distribution(self):
        """Per-tuple knot positions + currents, by the same segment-center →
        knot conversion PyNECEngine uses: interior knots average the two
        adjacent segment-center currents; free ends go to zero; junction
        ends carry the adjacent center current."""
        f = self.builder.freq
        text = self._run(self.deck([f], sources=self._drive_sources(f)))
        return self._currents_from(self._parse_wire_currents(text)[0])

    def solve_snapshot(self):
        """One binary run serving the whole web-solve contract: impedances,
        knot currents, and the power budget from a single printout (the
        separate impedance()/current_distribution() calls each spawn a
        process — a web solve wants one). Also stamps the duck-typed
        ``_excited_efficiency`` / ``_excited_p_in`` /
        ``_excited_power_budget`` attributes the web adapter's budget and
        efficiency helpers read on every engine."""
        if getattr(self, "_use_reducer", False):
            return self._reduced_snapshot()
        text = self._run(self.deck([self.builder.freq]))
        zs = self._impedances_from(self._parse_input_parameters(text)[0])
        currents = self._currents_from(self._parse_wire_currents(text)[0])
        budget = self._parse_power_budget(text)
        self._excited_efficiency = budget["efficiency_pct"] / 100.0
        self._excited_p_in = budget["input_w"]
        # LOSSES ONLY — see the protocol comment in `antennaknobs.engine`. This
        # used to carry ("Radiated", P_rad) as well, which every consumer then
        # subtracted from the input as if radiating were a loss: on a lossless
        # design the CLI and the web panel both read "antenna (accepted): 0 %"
        # where momwire read 100 % (issue #1354).
        self._excited_power_budget = [("Wire loss", budget["wire_loss_w"])]
        self._excited_p_radiated = budget["radiated_w"]
        return zs, currents, budget

    def _reduced_snapshot(self):
        """`solve_snapshot` on the multiport-Y route (AK#1627): the Y runs once,
        for the impedances AND the port voltages, then one deck driving every
        real port for the currents and NEC-5's wire loss.

        The budget is PyNEC's on the same route. The network's own input power
        and losses come from the reducer, which the structure deck cannot see,
        and NEC-5's conductor loss is folded in on top."""
        f = self.builder.freq
        state = _multiport.reduced_state(self, f, impedances=True)
        text = self._run(self.deck([f], sources=self._real_port_sources(state.V)))
        currents = self._currents_from(self._parse_wire_currents(text)[0])
        budget = self._parse_power_budget(text)
        # LOSSES ONLY (issue #1354), as on the native route.
        self._excited_efficiency, self._excited_power_budget = (
            _multiport.fold_wire_loss(
                state.efficiency, state.p_in, state.budget, budget["wire_loss_w"]
            )
        )
        self._excited_p_in = state.p_in
        self._excited_p_radiated = budget["radiated_w"]
        return state.zs, currents, budget

    def _currents_from(self, per_tag):
        """One `WireCurrents` per wire, its knots rebuilt EXACTLY from NEC-5's
        printed centre currents by `_tent_knot_currents` (issue #1638).

        A node's kind follows the ground card this engine writes: under
        ``GE 1`` an end on the ground plane is BONDED to it (a contact, whose
        current the ground takes); under ``GE -1`` (buried wires present) a
        z=0 node is an ordinary junction between the wires meeting there, and
        an unshared one is free (NEC-5 forces its current to zero, and
        `_refuse_contact_without_continuation` refuses the design anyway)."""

        def _key(p):
            return tuple(np.round(np.asarray(p, dtype=float), 6))

        endpoint_count: dict = {}
        for w in self._wires:
            for p in (w.p0, w.p1):
                endpoint_count[_key(p)] = endpoint_count.get(_key(p), 0) + 1

        bonded = self.ground is not None and not self._has_buried_wires
        kinds = {}
        for w in self._wires:
            for p in (w.p0, w.p1):
                if bonded and float(p[2]) == 0.0:
                    kinds[_key(p)] = "contact"
                elif endpoint_count[_key(p)] >= 2:
                    kinds[_key(p)] = "junction"
                else:
                    kinds[_key(p)] = "free"

        centres, ends, knot_positions = [], [], []
        for i, w in enumerate(self._wires):
            # One authored wire may be several tags (issue #1108); its
            # currents are their concatenation, in card order, and its knots
            # are the panel boundaries rather than a uniform linspace.
            sub = _expand_graded(w)
            cur_per_seg = np.concatenate(
                [
                    np.asarray(per_tag.get(tag, []), dtype=np.complex128)
                    for tag in self._tags_of[i]
                ]
                or [np.zeros(0, dtype=np.complex128)]
            )
            n_total = sum(c[2] for c in sub)
            if cur_per_seg.shape[0] != n_total:
                raise NEC5Error(
                    f"tags {list(self._tags_of[i])}: expected {n_total} segment "
                    f"currents, got {cur_per_seg.shape[0]}"
                )
            knot_positions.append(
                np.concatenate(
                    [np.linspace(a, b, n + 1)[:-1] for a, b, n in sub]
                    + [np.asarray(sub[-1][1], dtype=float)[None, :]]
                )
            )
            centres.append(cur_per_seg)
            ends.append((_key(w.p0), _key(w.p1)))

        knot_currents = _tent_knot_currents(centres, ends, kinds)
        out = [
            WireCurrents(knot_positions=k, knot_currents=c)
            for k, c in zip(knot_positions, knot_currents, strict=True)
        ]
        return self._authored_currents(out)
