"""NEC-4.2 as an external engine over a text coupling — issue #1603.

NEC-4.2 (Burke & Poggio, LLNL, LLNL-CODE-491368) is licensed software: each
user holds their own licence and supplies their own console binary, exactly as
NEC-5 users do (#825). antennaknobs ships nothing of it — no binary in the
workbench bundle, the Docker image, a wheel or the hosted app — and reaches it
the way it reaches NEC-2 and NEC-5: a deck written to a fresh temp dir, the
binary run there, its printout parsed.

A thin subclass of `NEC2Engine`, because NEC-4.2 reads NEC-2's cards and prints
NEC-2's blocks. What differs, and where each difference lives:

* **Invocation.** ``nec42cl <deck> <printout>``, both names as ARGUMENTS, run
  from the deck's directory (`run_deck`). No probing between forms: the
  binary this lane targets takes exactly one.
* **Ground cards** (`nec_export`'s ``dialect="nec42"``). The Sommerfeld card
  caches its tables to files in the cwd unless it ends ``NOFILE``, so every
  ``GN 2`` (or 4.2's newer ``GN 3``) is written ``... NOFILE`` — and the run
  happens in a temp dir that is removed afterwards regardless, never the
  user's cwd. The MININEC-type pair is refused: measured, NEC-4.2 accepts
  NEC-2's ``GN 1`` + ``GD`` and prints the perfect-ground pattern to the digit.
* **Buried wires are served.** ``GE -1`` is NEC-4's flag for a ground with
  wires below it, so a design `refuse_nec2_geometry` turns away runs here over
  the Sommerfeld ground (`refuse_nec42_geometry` holds what is still refused).
* **The power budget** prints ``WIRE LOSS`` where NEC-2 prints ``STRUCTURE
  LOSS``, and its ``NETWORK LOSS`` line appears only when the deck carries a
  network (`NEC42Engine._parse_power_budget`).

* **Graded meshes are served** (AK#1803). A `GradedSegments` wire becomes its
  panels, chained GW cards, before any tag is assigned
  (`engine.expand_graded_wires`), so the deck, the currents and the
  multiport-Y route all read the same list.
* **A current source is NEC-4's own ``EX 6``** (AK#1803), not NEC-2's
  phantom-wire gyrator: its input-parameters row is the antenna's impedance
  directly, and its drive is read in amps from the row's current columns
  (`NEC42Engine._drives`).

The deck is `nec_export.export_nec`'s ``dialect="nec42"``: one writer for both
dialects, so a NEC-2 and a NEC-4 deck of one design cannot disagree about the
antenna, only about the cards that spell it. Everything else — feeds at
segment centres (odd parity), the multiport-Y route, every other parser — is
`NEC2Engine`'s, verified against real ``nec42cl`` printouts.

**GN 3 and the near field.** Stock NEC-4.2's GN 3 evaluates the near field
wrongly close to the zenith (reported on AK#1803: ~1100x too high at 83 and 97
degrees of elevation, where GN 2 is clean). Users bring their own binaries, so
a GN 3 deck asking for a near-field point in that cone is refused by name
(`refuse_gn3_near_field`), whatever build this machine happens to run.
"""

from __future__ import annotations

import logging
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..engine import expand_graded_wires
from ..network import as_wire
from ._external import find_exe, run_exe
from .nec2 import (
    _AIP_HEADER,
    _GROUND_DEFAULT,
    _PROBE_DECK,
    NEC2Engine,
    NEC2Error,
    _identity,
)

_log = logging.getLogger(__name__)

NEC42_EXE_ENV = "NEC42_EXE"


class NEC42Error(NEC2Error):
    """NEC-4.2 is unavailable, refused the deck, or produced an unusable
    printout. A `NEC2Error`, because every NEC-2 reader this engine inherits
    raises that."""


def find_nec42(explicit: str | None = None) -> str | None:
    """Resolve the user-supplied NEC-4.2 executable: explicit path, then
    ``$NEC42_EXE``, then ``[engines] nec42_exe`` in the settings file. None when
    none resolves to an executable file."""
    return find_exe(NEC42_EXE_ENV, explicit)


def run_deck(exe: str, deck: str, *, timeout: float) -> str:
    """One deck through the binary, returning the printout text.

    Runs in a FRESH temp dir per call, removed on the way out: NEC-4.2 writes
    what it writes into its cwd (the Sommerfeld table files, when a card lacks
    NOFILE), and the user's working directory is never that place. Exit codes
    are not trusted — the health signal is a printout, as on NEC-2 and NEC-5.
    """
    with tempfile.TemporaryDirectory(prefix="nec42_") as td:
        tdp = Path(td)
        (tdp / "model.nec").write_text(deck)
        try:
            proc = run_exe(
                [exe, "model.nec", "model.out"], stdin_text="", cwd=td, timeout=timeout
            )
        except subprocess.TimeoutExpired as e:
            raise NEC42Error(f"NEC-4.2 timed out after {timeout:.0f}s") from e
        except OSError as e:
            raise NEC42Error(f"{exe} could not be executed: {e}") from e
        out = tdp / "model.out"
        text = out.read_text(errors="replace") if out.is_file() else ""
    if not text.strip():
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-300:]
        raise NEC42Error(
            f"NEC-4.2 produced no printout from {exe} (exit {proc.returncode}); "
            f"output tail: {tail!r}"
        )
    return text


# path -> (mtime, size, verdict, reason), keyed on the file's identity.
_PROBE_CACHE: dict[str, tuple[float, int, bool, str]] = {}


def probe_nec42(explicit: str | None = None, *, timeout: float = 20.0) -> str | None:
    """The resolved NEC-4.2 executable, or None with the reason logged.

    `probe_nec2`'s discipline (#1339): a path that resolves is not evidence the
    file is a NEC, so this RUNS NEC-2's one-wire probe deck once per (path,
    mtime, size) and requires an ANTENNA INPUT PARAMETERS block.
    """
    exe = find_nec42(explicit)
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
        ok, reason = False, f"{exe} is not a working NEC-4.2 binary: {e}"
    _PROBE_CACHE[exe] = (ident[0], ident[1], ok, reason)
    if not ok:
        _log.warning("NEC-4.2 unavailable: %s", reason)
    return exe if ok else None


def _ex6_segments(deck: str) -> set[tuple[int, int]]:
    """``{(tag, absolute segment)}`` of every ``EX 6`` card in `deck`, with
    each tag's offset from the deck's own GW cards."""
    base: dict[int, int] = {}
    acc = 0
    ex6 = []
    for line in deck.splitlines():
        toks = line.split()
        if toks[:1] == ["GW"] and len(toks) >= 3:
            base[int(toks[1])] = acc
            acc += int(toks[2])
        elif toks[:2] == ["EX", "6"] and len(toks) >= 4:
            ex6.append((int(toks[2]), int(toks[3])))
    return {(t, base[t] + g) for t, g in ex6 if t in base}


def refuse_nec42_geometry(tups, ground) -> None:
    """Refuse geometry a NEC-4.2 deck from this writer cannot carry, by name.

    Buried wires are SERVED — the difference from `refuse_nec2_geometry` — over
    the Sommerfeld ground, under ``GE -1``. What stays refused, each measured or
    documented rather than guessed:

    * a wire crossing z=0 MID-SPAN. Measured on a 6 m vertical from z=-1 m: at
      30 segments (a segment end on the interface) the crossing wire and the
      same wire split at z=0 print the same impedance to the digit; at 29, one
      segment straddles the interface and the binary prints 38-621j ohm for
      the 167-125j ohm answer, without a word. Splitting at z=0 is the fix;
    * a wire lying IN the plane (both ends z=0), as on NEC-2;
    * buried wires under any ground but the Sommerfeld one: PEC and the
      reflection-coefficient ground have no below-ground medium;
    * a conductor that ENDS on the plane in a deck that also has buried wires.
      ``GE -1`` leaves the current expansion alone at z=0, so that end has no
      basis function there and the conductor reads as open-circuited — NEC-5's
      flag, with NEC-5's measured consequence (`NEC5Engine`, #1025). A
      conductor that continues below the plane (a rise from a buried hub) is
      served.
    """
    if ground is None or ground == "free":
        return
    wires = [as_wire(t) for t in tups]
    buried = False
    contacts = []
    for i, w in enumerate(wires):
        z0, z1 = float(w.p0[2]), float(w.p1[2])
        if z0 == 0.0 and z1 == 0.0:
            raise ValueError(
                f"wire {i + 1} lies in the ground plane (z=0), where its own "
                "image coincides with it — NEC-4.2's ground forbids it"
            )
        if (z0 < 0.0 < z1) or (z1 < 0.0 < z0):
            raise NotImplementedError(
                f"wire {i + 1} crosses the ground plane mid-span: split it AT "
                "z=0. NEC-4.2 serves buried wires, but a segment straddling the "
                "interface is solved wrong without a warning (measured), so the "
                "wrapper refuses it rather than report that number"
            )
        if z0 < 0.0 or z1 < 0.0:
            buried = True
            if not (isinstance(ground, tuple) and ground[0] == "finite"):
                raise NotImplementedError(
                    f"wire {i + 1} dips below z=0: NEC-4.2 serves buried wires "
                    "only over its Sommerfeld ground — choose the Sommerfeld "
                    "(finite) ground, not PEC, the reflection-coefficient or "
                    "the MININEC-type ground, none of which has a medium below "
                    "the plane"
                )
        for p in (w.p0, w.p1):
            if float(p[2]) == 0.0:
                contacts.append(tuple(float(c) for c in p))
    if not buried:
        return
    for node in contacts:
        continues_below = any(
            (tuple(float(c) for c in end) == node and float(other[2]) < 0.0)
            for w in wires
            for end, other in ((w.p0, w.p1), (w.p1, w.p0))
        )
        if not continues_below:
            x, y, _z = node
            raise NotImplementedError(
                f"a conductor ends ON the ground plane at ({x:g}, {y:g}, 0) while "
                "this design also has buried wires: the ground flag buried wires "
                "need (GE -1) gives a wire ending at z=0 no basis function there, "
                "so NEC-4.2 would read the conductor as open-circuited. Continue "
                "the conductor BELOW the interface (a rise from the buried hub up "
                "to this node is the served spelling), or lift it clear of the "
                "plane"
            )


# Half-width, in degrees from the vertical, of the cone `refuse_gn3_near_field`
# refuses. The reported fault sits 7 degrees off the zenith on either side (83
# and 97 degrees of elevation); its extent was never mapped, and the binary
# here cannot map it, so the window is twice that, rounded up.
GN3_ZENITH_WINDOW_DEG = 15.0


def refuse_gn3_near_field(ground, sommerfeld, points, centres) -> None:
    """Refuse a near-field request under NEC-4.2's GN 3 with any field point
    near the zenith of the structure, by name (AK#1803).

    Stock NEC-4.2's GN 3 evaluates the near field wrongly there: the report on
    AK#1803 has it ~1100x too high at 83 and 97 degrees of elevation, where
    GN 2 on the same deck is clean. A NEC-4.2 binary is the user's own, so
    the refusal holds whichever build runs. Refused rather than served from
    GN 2: the two grounds print different impedances (a few parts in 1e4 on
    the check set's inverted vee), so a silent swap would hand back a deck
    that is not the one asked for.

    "Near the zenith" is measured from every segment centre, because the
    ground term of a Sommerfeld evaluation is a function of source and field
    point together, and in both of the two geometries it sees: the direct
    one (field point minus source) and the image one (field point minus the
    source mirrored in z=0). A point within `GN3_ZENITH_WINDOW_DEG` of the
    vertical through any segment centre, in either, is refused. Where the
    fault's edge lies was never measured, so the window errs wide.

    `points` and `centres` are ``(n, 3)`` arrays. Nothing is refused unless
    the ground is the Sommerfeld one and `sommerfeld` is 3.
    """
    if int(sommerfeld) != 3:
        return
    if not (isinstance(ground, tuple) and ground and ground[0] == "finite"):
        return
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    cen = np.asarray(centres, dtype=float).reshape(-1, 3)
    tan_w = math.tan(math.radians(GN3_ZENITH_WINDOW_DEG))
    for c in cen:
        rho = np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1])
        for dz in (pts[:, 2] - c[2], pts[:, 2] + c[2]):
            hit = rho <= tan_w * np.abs(dz)
            if np.any(hit):
                x, y, z = pts[int(np.argmax(hit))]
                raise NotImplementedError(
                    f"NEC-4.2's GN 3 ground with a near-field point at "
                    f"({x:g}, {y:g}, {z:g}), within {GN3_ZENITH_WINDOW_DEG:g} "
                    "degrees of the vertical through a segment: stock NEC-4.2 "
                    "evaluates GN 3's near field wrongly near the zenith (about "
                    "1000x too high, AK#1803), where GN 2 is clean. Ask for the "
                    "near field over GN 2, or keep the grid off the zenith"
                )


class NEC42Engine(NEC2Engine):
    """A user-supplied, licensed NEC-4.2 console binary, driven over text.

    `NEC2Engine` with NEC-4.2's invocation, ground cards, geometry rules and
    power-budget labels (see the module docstring). ``sommerfeld`` picks the
    Sommerfeld card for a "finite" ground: 2 (the default, the evaluation
    NEC-2 also has) or 3, NEC-4.2's newer one.
    """

    label = "NEC-4.2"
    _capture_name = "nec42"

    def __init__(
        self,
        builder,
        *,
        ground=_GROUND_DEFAULT,
        nec42_exe: str | None = None,
        timeout: float = 120.0,
        capture_dir=None,
        wire_radius: float | None = None,
        sommerfeld: int = 2,
    ):
        if sommerfeld not in (2, 3):
            raise ValueError(f"sommerfeld must be 2 or 3, not {sommerfeld!r}")
        self.sommerfeld = int(sommerfeld)
        self._nec42_exe = nec42_exe
        if isinstance(ground, tuple) and ground and ground[0] == "mininec":
            from ..nec_export import MININEC_NEC42_REFUSAL

            raise NotImplementedError(MININEC_NEC42_REFUSAL)
        super().__init__(
            builder,
            ground=ground,
            timeout=timeout,
            capture_dir=capture_dir,
            wire_radius=wire_radius,
        )

    def _resolve_exe(self, explicit: str | None) -> str:
        exe = find_nec42(self._nec42_exe)
        if exe is None:
            raise NEC42Error(
                "no NEC-4.2 binary: set $NEC42_EXE (or [engines] nec42_exe in "
                "settings.toml, or pass nec42_exe=) to your licensed NEC-4.2 "
                "console executable"
            )
        return exe

    def _coerce_wire_tuples(self, tups):
        # Graded wires as their panels (AK#1803), exactly as the deck engine
        # in `nec_export` expands them, so `self.tups` is the deck's GW list
        # tag for tag and `_currents_from` reads it without a map.
        out = super()._coerce_wire_tuples(tups)
        out, self._tup_authored = expand_graded_wires(
            out, getattr(self, "_tup_authored", None)
        )
        return out

    def _drives(self, text: str, deck: str) -> list[tuple[complex, str]]:
        """Each feed's drive value and unit, as `NEC2Engine._drives`, except
        that a row on an ``EX 6`` segment is a current source: its drive is
        the row's CURRENT, in amps (AK#1803). Rows are matched on (tag,
        absolute segment), which is what the printout's row carries."""
        ex6 = _ex6_segments(deck)
        if not ex6:
            return super()._drives(text, deck)
        chunks = text.split(_AIP_HEADER)[1:]
        if not chunks:
            raise NEC42Error(f"no {_AIP_HEADER} in NEC-4.2 printout")
        out = []
        for tag, seg, nums in self._aip_rows(chunks[0]):
            if (tag, seg) in ex6:
                out.append((complex(nums[2], nums[3]), "A"))
            else:
                out.append((complex(nums[0], nums[1]), "V"))
        return out

    def _check_geometry_against_ground(self) -> None:
        refuse_nec42_geometry(self.tups, self.ground)
        self._has_buried_wires = self.ground not in (None, "free") and any(
            float(as_wire(t).p0[2]) < 0.0 or float(as_wire(t).p1[2]) < 0.0
            for t in self.tups
        )

    def _deck_dialect(self) -> dict:
        return {"dialect": "nec42", "sommerfeld": self.sommerfeld}

    def _run_binary(self, deck: str) -> str:
        return run_deck(self.exe, deck, timeout=self.timeout)

    def _ground_bonds_z0(self) -> bool:
        # Under GE -1 (buried wires present) a z=0 node is not bonded: it is an
        # ordinary junction between the wires meeting there.
        return super()._ground_bonds_z0() and not self._has_buried_wires

    @staticmethod
    def _parse_power_budget(text: str) -> dict:
        """The POWER BUDGET block, in `NEC2Engine._parse_power_budget`'s keys.

        NEC-4.2's labels, from its own printouts::

            INPUT POWER   = 3.1574E-03 WATTS
            RADIATED POWER= 3.1574E-03 WATTS
            WIRE LOSS     = 0.0000E+00 WATTS
            NETWORK LOSS  = 1.4211E-14 WATTS     (only with a network)
            EFFICIENCY    = 100.00 PERCENT

        ``WIRE LOSS`` where NEC-2 says ``STRUCTURE LOSS``. The ``NETWORK LOSS``
        line is printed only when the deck carries a network (measured: absent
        on a plain dipole, present on the gyrator deck), so its absence reads
        as 0 W; every other line is required, and a missing one raises, for
        NEC-2's reason — a partial budget is how 100 % gets shipped as measured.
        """
        try:
            chunk = text.split("POWER BUDGET", 1)[1]
        except IndexError:
            raise NEC42Error("no POWER BUDGET in NEC-4.2 printout") from None
        keys = {
            "INPUT POWER": "input_w",
            "RADIATED POWER": "radiated_w",
            "WIRE LOSS": "wire_loss_w",
            "STRUCTURE LOSS": "wire_loss_w",
            "NETWORK LOSS": "network_loss_w",
            "EFFICIENCY": "efficiency_pct",
        }
        out: dict = {}
        for line in chunk.splitlines()[:12]:
            for label, key in keys.items():
                if label in line and "=" in line:
                    out[key] = float(line.split("=", 1)[1].split()[0])
        out.setdefault("network_loss_w", 0.0)
        missing = set(keys.values()) - set(out)
        if missing:
            raise NEC42Error(
                f"incomplete POWER BUDGET section: missing {sorted(missing)}, "
                f"parsed {out}"
            )
        return out
