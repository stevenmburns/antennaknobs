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
  on errors).

The printout layout is not documented in the manual; the parsers below are
pinned by captured printouts committed under ``tests/fixtures/nec5/``
(End-User Reports per the license, cited LLNL-CODE-746721).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..engine import SimulationEngine, WireCurrents
from ..network import as_wire

C_LIGHT = 299_792_458.0

NEC5_EXE_ENV = "NEC5_EXE"

_AIP_HEADER = "ANTENNA INPUT PARAMETERS"
_CURRENTS_HEADER = "- - - Wire Currents - - -"


def find_nec5(explicit: str | None = None) -> str | None:
    """Resolve the licensed NEC-5 executable: explicit path first, then
    ``$NEC5_EXE``. Returns None when unset or not an executable file —
    callers decide whether that is an error (engine ctor) or an absence
    (CLI roster, test skip)."""
    cand = explicit or os.environ.get(NEC5_EXE_ENV)
    if not cand:
        return None
    p = Path(cand).expanduser()
    if p.is_file() and os.access(p, os.X_OK):
        return str(p)
    return None


class NEC5Error(RuntimeError):
    """NEC-5 is unavailable, refused the deck, or produced an unusable
    printout."""


def _num(x) -> str:
    return f"{float(x):.6E}"


class NEC5Engine(SimulationEngine):
    """Drive a licensed NEC-5 binary through intermediate files.

    Stage 1 scope (#825): free space, plain ``Wire.ex`` feeds, impedance
    and currents. Grounds, port networks, patterns and NEC-5-specific
    physics are later stages and refuse loudly here.
    """

    supports_far_field = False  # stage 3: RP parsing
    # NEC-5 sources sit at segment ends; an even count puts a knot at the
    # fed wire's midpoint (see module docstring).
    segment_parity = "even"

    def __init__(self, builder, *, ground=None, nec5_exe=None, timeout=120.0):
        super().__init__(builder)
        if ground is not None:
            raise NotImplementedError(
                "NEC5Engine stage 1 is free-space only (grounds are #825 stage 2)"
            )
        exe = find_nec5(nec5_exe)
        if exe is None:
            raise NEC5Error(
                "NEC-5 executable not found. NEC-5 is licensed software that "
                "antennaknobs cannot bundle: point NEC5_EXE (or nec5_exe=) at "
                "your licensed nec5cl binary."
            )
        self._exe = exe
        self._timeout = float(timeout)
        if builder.build_network() is not None:
            raise NotImplementedError(
                "NEC5Engine stage 1 supports plain-fed designs only "
                "(port networks are a later #825 stage)"
            )
        if builder.build_tls():
            raise NotImplementedError(
                "NEC5Engine stage 1 does not model transmission lines"
            )
        self.tups = self._coerce_wire_tuples(builder.build_wires())
        self._wires = [as_wire(t) for t in self.tups]
        self._feeds = [(i, w) for i, w in enumerate(self._wires) if w.ex is not None]
        if not self._feeds:
            raise ValueError(
                "design has no excitation (no Wire.ex entry) — nothing to solve"
            )
        spec = builder.build_wire_material()
        default_radius = spec.radius if spec is not None else 0.0005
        self._radii = [
            w.spec.radius if w.spec is not None else default_radius for w in self._wires
        ]

    # ---------- deck ----------

    def deck(self, freqs) -> str:
        """The NEC-5 input deck for this model at the given frequencies
        (MHz). Multiple frequencies must be uniformly spaced (NEC-5's FR
        does linear stepping); callers with a ragged grid run one deck per
        frequency."""
        freqs = np.atleast_1d(np.asarray(freqs, dtype=float))
        if freqs.size > 1:
            steps = np.diff(freqs)
            if not np.allclose(steps, steps[0], rtol=1e-9, atol=0.0):
                raise ValueError("deck() needs a uniformly spaced frequency grid")
            df = float(steps[0])
        else:
            df = 0.0
        lines = ["CM antennaknobs NEC5Engine deck", "CE"]
        for i, w in enumerate(self._wires):
            tag, r = i + 1, self._radii[i]
            p0, p1 = w.p0, w.p1
            lines.append(
                f"GW {tag} {w.n_seg} "
                f"{_num(p0[0])} {_num(p0[1])} {_num(p0[2])} "
                f"{_num(p1[0])} {_num(p1[1])} {_num(p1[2])} {_num(r)}"
            )
        lines.append("GE 0 0")
        for i, w in self._feeds:
            # Source at end 2 of the middle segment = the wire's center
            # knot (even parity guarantees n_seg is even).
            ex = complex(w.ex)
            lines.append(
                f"EX 0 {i + 1} {w.n_seg // 2} 2 {_num(ex.real)} {_num(ex.imag)}"
            )
        lines.append(f"FR 0 {freqs.size} 0 0 {_num(freqs[0])} {_num(df)}")
        lines.append("XQ 0")
        lines.append("EN")
        return "\n".join(lines) + "\n"

    # ---------- run ----------

    def _run(self, deck: str) -> str:
        """Run one deck through the binary and return the printout text.

        NEC-5 reads the input and output file names from stdin and works
        in intermediate files; exit codes are not trusted (Fortran STOP) —
        the printout's presence and parseability are the health signal."""
        with tempfile.TemporaryDirectory(prefix="nec5_") as td:
            tdp = Path(td)
            (tdp / "model.nec").write_text(deck)
            try:
                proc = subprocess.run(
                    [self._exe],
                    input="model.nec\nmodel.out\n\n",
                    text=True,
                    capture_output=True,
                    cwd=td,
                    timeout=self._timeout,
                )
            except subprocess.TimeoutExpired as e:
                raise NEC5Error(f"NEC-5 timed out after {self._timeout:.0f}s") from e
            out = tdp / "model.out"
            if not out.is_file():
                tail = (proc.stdout or "")[-500:] + (proc.stderr or "")[-500:]
                raise NEC5Error(f"NEC-5 produced no printout; stdout/stderr: {tail}")
            return out.read_text(errors="replace")

    # ---------- parse ----------

    @staticmethod
    def _parse_input_parameters(text: str) -> list[list[tuple[int, int, complex]]]:
        """All ANTENNA INPUT PARAMETERS sections, one list per frequency,
        each row as (tag, seg, Z). Row layout (pinned by fixtures):
        tag seg sub Vre Vim Ire Iim Zre Zim Yre Yim P — 12 tokens."""
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
                    z = complex(float(toks[7]), float(toks[8]))
                except ValueError:
                    if rows:
                        break
                    continue
                rows.append((tag, seg, z))
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

    def _impedances_from(self, rows: list[tuple[int, int, complex]]) -> list[complex]:
        """Match one frequency's AIP rows against this model's feeds, in
        feed order. Tags must line up — a mismatch means the deck writer
        and the printout disagree about the model, which is a bug, not a
        tolerance."""
        # The printout's SEG. NO. is the ABSOLUTE segment number (pinned by
        # fixture: a feed at relative segment 1 of tag 3 after two 20-segment
        # wires prints as segment 41), while the deck's EX addresses
        # tag-relative — translate before comparing.
        offsets = np.cumsum([0] + [w.n_seg for w in self._wires[:-1]])
        expect = [(i + 1, int(offsets[i]) + w.n_seg // 2) for i, w in self._feeds]
        got = [(tag, seg) for tag, seg, _ in rows]
        if got != expect:
            raise NEC5Error(
                f"NEC-5 source rows {got} do not match the deck's feeds {expect}"
            )
        return [z for _, _, z in rows]

    # ---------- SimulationEngine API ----------

    def impedance(self):
        text = self._run(self.deck([self.builder.freq]))
        return self._impedances_from(self._parse_input_parameters(text)[0])

    def impedance_sweep(self, freqs):
        freqs = np.asarray(freqs, dtype=float)
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
        text = self._run(self.deck([self.builder.freq]))
        per_tag = self._parse_wire_currents(text)[0]

        def _key(p):
            return tuple(np.round(np.asarray(p, dtype=float), 6))

        endpoint_count: dict = {}
        for w in self._wires:
            for p in (w.p0, w.p1):
                endpoint_count[_key(p)] = endpoint_count.get(_key(p), 0) + 1

        out = []
        for i, w in enumerate(self._wires):
            cur_per_seg = np.asarray(per_tag.get(i + 1, []), dtype=np.complex128)
            if cur_per_seg.shape[0] != w.n_seg:
                raise NEC5Error(
                    f"tag {i + 1}: expected {w.n_seg} segment currents, "
                    f"got {cur_per_seg.shape[0]}"
                )
            knots = np.linspace(w.p0, w.p1, w.n_seg + 1)
            knot_cur = np.zeros(w.n_seg + 1, dtype=np.complex128)
            if w.n_seg >= 2:
                knot_cur[1:-1] = 0.5 * (cur_per_seg[:-1] + cur_per_seg[1:])
            if cur_per_seg.shape[0] >= 1:
                if endpoint_count.get(_key(w.p0), 0) >= 2:
                    knot_cur[0] = cur_per_seg[0]
                if endpoint_count.get(_key(w.p1), 0) >= 2:
                    knot_cur[-1] = cur_per_seg[-1]
            out.append(WireCurrents(knot_positions=knots, knot_currents=knot_cur))
        return out
