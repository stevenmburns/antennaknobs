"""`NetworkReducer`: the spec layer stamped into the MNA core.

Arrived from antennaknobs per ``docs/design/networks-move-into-the-engine.md``
(momwire#456 workstream 2, phase B), near-verbatim — the tail of that repo's
``network_reduce.py``. The type-free half it stands on (the TL/chain math and
the MNA primitives) landed first in `._reduce`; the ports, branches, sources
and flat `Network` it reads live in `._spec`. Three modules rather than the
one the file came from, because a single module could not both define the
spec and be imported by it: `._spec` reuses `._reduce`'s
`_series_rlc_impedance`, so the reducer — which needs BOTH — is its own
module and the arrows stay acyclic.

A caller's engine assembles the antenna's short-circuit Y at the real
(`PortOnWire`) ports, then hands it here with a port-name -> matrix-index map.
Everything below stamps the network branches and sources into one Modified
Nodal Analysis system and solves it once for everything: driven-port
impedances, physical port voltages for the excited far-field/current solve,
and the source-power / load-dissipation bookkeeping. The only engine-specific
work is producing the raw Y and the index map.

The power-budget label strings the probes carry are a FROZEN cross-repo
contract (antennaknobs#956): antennaknobs' schematic layer pattern-matches
them, so they moved here spelled exactly as they were and are not to be
reworded until the structured-probe replacement lands. That replacement's
momwire half is in: every probe `apply_branches` emits is a `_Probe`, a
3-tuple carrying a structured `(instance_path, branch_index, subprobe)` key
beside its label, and `excited_state`'s ``budget`` re-exposes that key as
`_BudgetEntry.key`.

The freeze stays ON here, for two reasons rather than one. The antennaknobs
schematic consumer has not switched to the structured key yet — and even once
it does, the budget list it receives is MIXED: that repo's engine layer
appends unkeyed plain 2-tuples of its own (see `excited_state`'s docstring).
So the migration cannot finish until those appenders carry keys too; until
then a consumer must tolerate rows without `.key`, and the labels stay as
they are spelled.
"""

from __future__ import annotations

import math

import numpy as np

from . import _reduce
from ._reduce import (
    C_LIGHT,
    Z_REF_DEFAULT,
    MNASystem,
    _Group2Element,
    _GStamps,
    _series_group2,
    _stamp_abcd,
    frequency_mhz,
    magnetizing_impedance,
    tl_abcd,
)
from ._spec import (
    TL,
    Admittance,
    Autotransformer,
    BalancedLine,
    Driven,
    DrivenCurrent,
    FloatingBalun,
    Load,
    PortAtVertex,
    PortOnWire,
    PortOnWireFloating,
    Shunt,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
    _parallel_rlc_admittance,
    load_impedance,
    load_series_admittance,
)


class _BudgetEntry(tuple):  # noqa: SLOT001 — `.key` lives in the instance dict; a tuple subclass cannot slot it
    """One `excited_state` budget row (issue #956).

    Unpacks as the historical `(label, watts)` pair — arity 2, so every
    existing `for label, watts in budget` site (this module, antennaknobs'
    `schematic.py`/`cli.py`, the test suites on both sides of the submodule
    boundary) keeps working unchanged. The probe's structured identity rides
    along as the `.key` attribute instead of a third tuple slot, because a
    third slot IS an arity change and those call sites destructure by
    position.

    `key` is `(instance_path, branch_index, subprobe)` (see
    `NetworkReducer.apply_branches`): the same triple that already drives the
    label string, but independent of its spelling — a schematic-side
    consumer can key on `.key` and stop pattern-matching `label`.
    """

    def __new__(cls, label, watts, key):
        self = super().__new__(cls, (label, watts))
        self.key = key
        return self

    def __getnewargs__(self):
        # tuple's inherited __getnewargs__ hands `__new__` ONE argument (the
        # plain tuple), so pickle/copy/deepcopy would call this 3-arg
        # `__new__` with 1 and raise TypeError. Spelling the real arguments
        # is what makes a budget row survive a round trip — with its key.
        return (self[0], self[1], self.key)


class _Probe(tuple):  # noqa: SLOT001 — `.key` lives in the instance dict; a tuple subclass cannot slot it
    """One power-budget probe: `(label, kind, payload)` plus `.key`.

    Indexes and unpacks exactly as the historical 3-tuple — `MNASystem.
    branch_power` destructures all three positions and antennaknobs'
    `tests/test_gamma_reference.py` reads `system.probes[0][0]` and hands
    the whole thing back to `branch_power`, so the arity is a contract of
    its own. The structured identity (issue #956) rides as an attribute for
    the same reason it does on `_BudgetEntry`: an added slot would be an
    arity change.

    A subclass rather than a fourth list running alongside `probes`:
    hand-paired lists have to be kept aligned at every emission site, and
    the failure mode of a missed pairing is a silently misattributed key
    rather than an error.
    """

    def __new__(cls, label, kind, payload, key):
        self = super().__new__(cls, (label, kind, payload))
        self.key = key
        return self

    def __getnewargs__(self):
        return (self[0], self[1], self[2], self.key)


class NetworkReducer:
    """Stamps a `Network`'s branches and sources into an MNA system on top
    of the raw real-port antenna Y and reads out driven-port impedances,
    physical port voltages, and the power bookkeeping.

    Construct with the network spec, a ``port_to_idx`` mapping every port
    name (real and virtual) to its row/column in the node space, and
    ``n_total_ports`` (real feeds + virtual ports). Real ports must occupy
    indices ``0..n_real-1`` in the same order as the raw Y handed to
    :meth:`apply_branches`; virtual ports come after.
    """

    def __init__(self, network, port_to_idx, n_total_ports, *, c_light_mhz_m=None):
        self.network = network
        # The design's metre-megahertz product (antennaknobs#1685): every
        # frequency-dependent branch — a lumped part's omega, a line's loss, a
        # Touchstone file's sample frequency — reads its frequency off the
        # wavelength through this c (`frequency_mhz`). None is the SI c,
        # bit-identical to the reducer before the keyword. A deck-derived
        # design passes NEC's 299.8, so its parts sit at the deck's own f
        # while its lines keep the deck's own wavelength for their phase.
        self.c_light_mhz_m = c_light_mhz_m
        self.port_to_idx = dict(port_to_idx)
        self.n_total_ports = n_total_ports

        # Floating gap ports: the antenna Y row still lives at the port's
        # existing index (that node becomes the "+" terminal), and the "-"
        # terminal gets a freshly appended node instead of being bonded to the
        # datum. Both are exposed as dotted sub-nodes, so every branch keeps
        # resolving through port_to_idx unchanged.
        self._floating = {}
        next_node = n_total_ports
        for name, port in network.ports.items():
            if isinstance(port, PortOnWireFloating):
                p_idx = self.port_to_idx[name]
                self._floating[name] = (p_idx, next_node)
                self.port_to_idx[f"{name}.p"] = p_idx
                self.port_to_idx[f"{name}.n"] = next_node
                next_node += 1
        self.n_nodes = next_node
        for src in network.sources:
            if src.port in self._floating:
                raise NotImplementedError(
                    f"source on floating gap port {src.port!r}: drive it through "
                    f"the network instead (a branch across {src.port}.p / "
                    f"{src.port}.n), or use a plain PortOnWire"
                )

        # 0-based driven port indices, with per-source kind: "v" for a
        # Driven voltage source (value = EMF), "i" for a DrivenCurrent
        # forced-current source (value = amps into the node, issue #442).
        self.driven_port_idx = []
        self.driven_voltages = []  # voltage sources only (legacy view)
        self._source_kinds = []
        self._source_values = []
        for src in network.sources:
            if isinstance(src, Driven):
                kind, value = "v", complex(src.voltage)
                self.driven_voltages.append(value)
            elif isinstance(src, DrivenCurrent):
                kind, value = "i", complex(src.current)
            else:
                raise NotImplementedError(f"unknown source type: {src!r}")
            self.driven_port_idx.append(port_to_idx[src.port])
            self._source_kinds.append(kind)
            self._source_values.append(value)

    @property
    def n_driven(self):
        return len(self.driven_port_idx)

    def _open_ended_nodes(self):
        """Node indices that only one branch terminal touches.

        An open stub is spelled as the *absence* of a termination — a `TL`
        into a private node nothing else uses (see ``station.shunt_open_stub``)
        — so "TL with a dangling far end" is how an open stub is recognised
        here, and the same walk finds any accidentally-unterminated line.
        """
        degree = {}
        for br in self.network.branches:
            for name in getattr(br, "__dataclass_fields__", {}):
                if name in ("a", "b", "c", "a1", "a2", "b1", "b2", "port", "line"):
                    node = getattr(br, name, None)
                    if isinstance(node, str) and node in self.port_to_idx:
                        idx = self.port_to_idx[node]
                        degree[idx] = degree.get(idx, 0) + 1
        # A real feed node is never "open" however few branches touch it: the
        # antenna's own dense Y ties it to every other feed. Only a virtual
        # node can dangle, so real ports and driven ports are excluded.
        real = {
            self.port_to_idx[name]
            for name, port in self.network.ports.items()
            if isinstance(port, PortOnWire) and name in self.port_to_idx
        }
        driven = set(self.driven_port_idx)
        return {
            idx
            for idx, deg in degree.items()
            if deg == 1 and idx not in driven and idx not in real
        }

    def _singularity_report(self, wavelength):
        """Which branch drove the system singular at this wavelength (#647).

        Attribution rather than a bare "matrix is singular": a lossless line
        is singular at a *specific* electrical length, so the walk asks each
        lossless line how close it sits to its own pole — an odd λ/4 for one
        hanging open (Z_in = 0, a dead short across the port it hangs on).
        Anything with real loss is skipped, because loss is what regularises
        it, and that is also the remedy the message recommends.

        Issue #746 narrowed this to one caller. A line between two live nodes
        is stamped as its chain matrix now, finite at every length, so neither
        pole can come from such a line. Two readings of a HANGING line survive:

        * odd λ/4: the EXCITED path keeps the ideal generator, which still
          cannot drive the dead short an open stub puts across the feed — so
          when this text appears it is a far-field / power-budget solve
          talking, and the impedance of that same design is a perfectly good
          Z = 0;
        * k·λ/2 (momwire#584): an open-terminated lossless line at a whole
          number of half-wavelengths is itself an open, so the node at its near
          end floats unless something else pins it. No chain matrix can pin a
          node that only this line reaches. This is antennaknobs'
          `doublet_balanced_tuner` at 16.0387 MHz, whose common-mode return
          runs through a line open-terminated at the floating gap.
        """
        f_mhz = frequency_mhz(wavelength, self.c_light_mhz_m)
        open_nodes = self._open_ended_nodes()
        suspects = []
        for br, path in zip(
            self.network.branches,
            self.network.branch_paths or [""] * len(self.network.branches),
            strict=True,
        ):
            if isinstance(br, TL):
                z0, vf, k1, k2 = br.z0, br.vf, br.k1, br.k2
                ends = (br.a, br.b)
            elif isinstance(br, BalancedLine):
                z0, vf, k1, k2 = br.zdiff, br.vf, br.k1, br.k2
                ends = (br.a1, br.b1)
            else:
                continue
            if k1 or k2 or getattr(br, "k0", 0.0):
                continue  # a lossy line has no pole to sit on
            hanging = any(
                self.port_to_idx.get(e) in open_nodes
                for e in ends
                if isinstance(e, str)
            )
            if not hanging:
                continue
            wl_line = wavelength * vf
            n_half = br.length / (0.5 * wl_line)  # length in half-wavelengths
            # Odd quarter-waves: n_half at an odd multiple of 0.5.
            if abs(n_half % 1.0 - 0.5) < 0.02:
                name = f"{path[:-1]}: " if path else ""
                suspects.append(
                    f"  {name}open-ended line {'→'.join(str(e) for e in ends)} "
                    f"is {n_half / 2:.4f} λ at {f_mhz:.4f} MHz — an odd "
                    "multiple of λ/4, where an open stub's Z_in = 0 shorts "
                    f"the port it hangs on (z0 = {z0:g} Ω), which no IDEAL "
                    "source can drive — the impedance of this same design is "
                    "a perfectly ordinary Z = 0"
                )
            # Whole half-waves: an open-terminated line there is itself an
            # open, and the node it hangs from floats (momwire#584).
            elif n_half >= 0.98 and min(n_half % 1.0, 1.0 - n_half % 1.0) < 0.02:
                name = f"{path[:-1]}: " if path else ""
                suspects.append(
                    f"  {name}open-ended line {'→'.join(str(e) for e in ends)} "
                    f"is {n_half / 2:.4f} λ at {f_mhz:.4f} MHz — a whole number "
                    "of half-wavelengths, where an open-terminated lossless line "
                    "is itself an open, so the node at its near end floats "
                    f"unless something else pins it (z0 = {z0:g} Ω)"
                )
        if not suspects:
            return (
                "No lossless line sits on a pole at this frequency, so the "
                "cause is elsewhere in the topology — a node reachable only "
                "through open-circuited branches, or two ideal sources in "
                "contradiction."
            )
        return (
            "Suspect:\n"
            + "\n".join(suspects)
            + "\nGive the line the loss it really has (k1/k2, or cable=...): "
            "any real attenuation moves the pole off the real axis and the "
            "excitation becomes well-posed."
        )

    def _reference_node(self):
        """The one port node a ``z_ref`` may be stamped behind, or ``None``.

        A reference plane is a one-port idea: it needs the rest of the network,
        seen from this port, to be PASSIVE. Then moving the generator behind an
        impedance changes the operating point but not the ratio, and
        Z = E/j − z_ref is exactly the ideal generator's answer.

        A second *active* source breaks that, and not subtly. With two voltage
        generators, port 0's mutual term y01·E1 is a current injection fixed
        independently of v0, so any source impedance at port 0 changes v0/i0
        itself — measured 23 % on the two-source fixture in test_network_mna.
        A `DrivenCurrent` elsewhere does the same. This package's contract is
        the classical driven-array Z_k = V_k/I_k at the ideal operating point,
        so a network with more than one active source keeps the ideal stamp
        and converts Γ from Z the way `sweep` already does.

        A source at exactly 0 V is not active: `Driven(port, 0)` is the datum
        trick, a hard V = 0 pin, and it leaves the rest passive. It also never
        gets the reference itself — with no EMF there is no incident wave, so
        its Γ is undefined rather than badly conditioned.
        """
        active = [
            (k, kind)
            for k, kind, val in zip(
                self.driven_port_idx,
                self._source_kinds,
                self._source_values,
                strict=True,
            )
            if val != 0
        ]
        if len(active) != 1 or active[0][1] != "v":
            return None
        return active[0][0]

    def apply_branches(self, Y_real, wavelength, *, z_ref=0j):
        """Stamp the antenna Y and every network branch into one MNA system.

        ``z_ref`` is the source impedance the driven port's EMF sits behind
        (issue #746). The default 0 is the historical ideal generator, which
        the excited / far-field path keeps because its port voltages ARE the
        excitation; the impedance and Γ paths pass ``Z_REF_DEFAULT``. See
        :meth:`excited_state` for why the two solves are separate and
        :meth:`_reference_node` for the one network shape it applies to — a
        request to reference a network that has no reference plane is honored
        as "quote Γ against this z0", not stamped.

        Group 1 (node-admittance block G):
          - the antenna's dense multiport short-circuit Y at the real-feed
            nodes vs. datum;
          - parallel-mode Shunt (the tank admittance is the natural finite
            quantity, → 0 at trap resonance).

        Group 2 (auxiliary branch currents):
          - TwoPort and series-mode Shunt — series elements, exact for the
            ideal short z = 0 and the 0 F open;
          - TL and BalancedLine as chain-matrix 2-ports, two currents each
            (issue #746): every entry of an ABCD matrix is entire, so the
            k·λ/2 line that has no admittance matrix at all stamps as the
            ordinary through-line it is;
          - one TERMINATION branch per port that is driven and/or loaded:
            an EMF (0 if undriven) in series with the port's Load impedance
            (0 if unloaded) from the datum into the node. Its constitutive
            row v_k + (z_ref + Z_L)·j = E is the Thevenin boundary condition,
            and its current j is the delivered port current — so the
            driven-point impedance E/j − z_ref and the load dissipation
            (E − v_k − z_ref·j)·j* both read off the solution. With the
            ideal-generator z_ref = 0 a driven-only port (Z_L = 0) degenerates
            to the voltage-source pin v_k = E; loaded-only ports (E = 0) to
            the series load termination v_k = −Z_L·j. A `Load` is thus a
            series impedance between the antenna gap and the common return,
            matching NEC2's ld_card physics.

        Ports that are neither driven, loaded, nor touched by a branch keep
        plain KCL with zero injection (the floating I_ext = 0 condition).
        """
        if self.c_light_mhz_m is None:
            omega = 2.0 * np.pi * C_LIGHT / wavelength
            f_hz = C_LIGHT / wavelength
        else:
            f_hz = frequency_mhz(wavelength, self.c_light_mhz_m) * 1e6
            omega = 2.0 * np.pi * f_hz
        line = dict(c_light_mhz_m=self.c_light_mhz_m)
        couplings: list[tuple[int, int, complex]] = []
        # The node-admittance block, recorded rather than written into a dense
        # G (AK#2241): the size decision below needs the Group-2 count, and a
        # large network must never allocate n × n. `_GStamps.dense` replays
        # these stamps (the antenna Y, its floating-port congruence AᵀYA, and
        # every `add_*` below) onto zeros with the in-place operations that
        # used to be written here, in the same order.
        G = _GStamps(self.n_nodes, Y_real, self._floating.values())

        elements = []
        loads_by_node = {}
        probes = []
        # Instance paths (issue #489): branch_paths aligns with branches
        # ("" for top-level). Budget labels get a "tuner1: " prefix and the
        # instance's own namespace stripped from its port names, so a
        # composite's rows group under its instance name.
        branch_paths = getattr(self.network, "branch_paths", None) or [""] * len(
            self.network.branches
        )
        for _bidx, (br, _bpath) in enumerate(
            zip(self.network.branches, branch_paths, strict=True)
        ):
            _short = lambda n, p=_bpath: n[len(p) :] if p and n.startswith(p) else n  # noqa: E731
            lab = lambda s, p=_bpath: f"{p[:-1]}: {s}" if p else s  # noqa: E731
            # Structured probe identity (issue #956): every probe this branch
            # emits carries `(instance_path, branch_index, subprobe)` beside
            # its label. `subprobe` is a fixed vocabulary token naming WHICH
            # of a multi-probe branch's probes this is (""/"mag"/"lower"/
            # "upper"/"load"), never derived from the label string — a label
            # rewording cannot perturb the key, which is the whole point of
            # having an identity channel separate from the display one.
            probe = lambda label, kind, payload, sub="", p=_bpath, i=_bidx: _Probe(  # noqa: E731
                label, kind, payload, (p, i, sub)
            )
            if isinstance(br, TL):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                leg = _stamp_abcd(
                    elements,
                    couplings,
                    [(a, 1.0 + 0j)],
                    [(b, -1.0 + 0j if br.transposed else 1.0 + 0j)],
                    tl_abcd(
                        br.z0,
                        br.length,
                        wavelength,
                        vf=br.vf,
                        k1=br.k1,
                        k2=br.k2,
                        skin=br.skin,
                        k0=br.k0,
                        **line,
                    ),
                )
                probes.append(
                    probe(
                        lab(f"TL {_short(br.a)}→{_short(br.b)}"), "group2abcd", (leg,)
                    )
                )
            elif isinstance(br, BalancedLine):
                # Balanced 4-terminal line (issues #575/#576/#746): the same
                # even/odd decomposition `balanced_admittance_4x4` writes as a
                # 4×4 Group-1 block, stamped instead as one chain-matrix
                # 2-port per mode. The differential mode's port weights
                # (+1, −1) force I(a1) = −I(a2) at each end, so with
                # `zcomm=None` the common mode remains STRUCTURALLY open
                # (rank 2) exactly as before — that is a topological property
                # of the incidence, not of which description carries it.
                a1, a2, b1, b2 = (
                    self.port_to_idx[p] for p in (br.a1, br.a2, br.b1, br.b2)
                )
                kw = dict(vf=br.vf, k1=br.k1, k2=br.k2, **line)
                legs = [
                    _stamp_abcd(
                        elements,
                        couplings,
                        [(a1, 1.0 + 0j), (a2, -1.0 + 0j)],
                        [(b1, 1.0 + 0j), (b2, -1.0 + 0j)],
                        tl_abcd(br.zdiff, br.length, wavelength, **kw),
                    )
                ]
                if br.zcomm is not None:
                    # The pair driven as ONE conductor: voltage the pair
                    # average, current the total, splitting equally. Its
                    # ½-weights annihilate differential vectors, so the two
                    # legs never cross-couple.
                    legs.append(
                        _stamp_abcd(
                            elements,
                            couplings,
                            [(a1, 0.5 + 0j), (a2, 0.5 + 0j)],
                            [(b1, 0.5 + 0j), (b2, 0.5 + 0j)],
                            tl_abcd(br.zcomm, br.length, wavelength, **kw),
                        )
                    )
                probes.append(
                    probe(
                        lab(
                            f"BalancedLine {_short(br.a1)},{_short(br.a2)}"
                            f"→{_short(br.b1)},{_short(br.b2)}"
                        ),
                        "group2abcd",
                        tuple(legs),
                    )
                )
            elif isinstance(br, Admittance):
                # Fixed complex Y stamped verbatim — no ω scaling, no auxiliary
                # current (issue #416). A pure node-admittance block, exactly
                # like TL's 2×2 and the parallel Shunt's 1×1.
                idxs = [self.port_to_idx[p] for p in br.ports]
                yb = np.array(br.y, dtype=np.complex128)
                G.add_block(idxs, yb)
                probes.append(
                    probe(
                        lab(f"Admittance {'→'.join(map(_short, br.ports))}"),
                        "group1",
                        (idxs, yb),
                    )
                )
            elif isinstance(br, TouchstoneLoad):
                # Measured 1-port (.s2p→.s1p) as a node-to-datum admittance
                # (issue #593): y = 1/Z(f) interpolated from the file, stamped
                # verbatim like a 1-port Admittance / parallel Shunt.
                k = self.port_to_idx[br.port]
                yb = br.data.y_at(f_hz)
                G.add_diag(k, yb[0, 0])
                probes.append(
                    probe(
                        lab(f"Touchstone {_short(br.port)}"),
                        "group1",
                        ([k], np.array([[yb[0, 0]]])),
                    )
                )
            elif isinstance(br, TouchstoneTwoPort):
                # Measured 2-port (.s2p) as an in-line 2×2 admittance block
                # (issue #593): [S](f)→[Y](f) interpolated from the file, stamped
                # like TL's 2×2 — a characterized balun / coax / filter black box.
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                yb = br.data.y_at(f_hz)
                G.add_block([a, b], yb)
                probes.append(
                    probe(
                        lab(f"Touchstone {_short(br.a)}→{_short(br.b)}"),
                        "group1",
                        ([a, b], yb),
                    )
                )
            elif isinstance(br, TwoPort):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                probes.append(
                    probe(
                        lab(f"TwoPort {_short(br.a)}→{_short(br.b)}"),
                        "group2",
                        len(elements),
                    )
                )
                elements.append(
                    _series_group2(a, b, br.r, br.l, br.c, omega, ql=br.ql, qc=br.qc)
                )
            elif isinstance(br, Shunt):
                k = self.port_to_idx[br.port]
                if br.parallel:
                    y_sh = _parallel_rlc_admittance(
                        br.r, br.l, br.c, omega, br.ql, br.qc
                    )
                    G.add_diag(k, y_sh)
                    probes.append(
                        probe(
                            lab(f"Shunt {_short(br.port)}"),
                            "group1",
                            ([k], np.array([[y_sh]])),
                        )
                    )
                else:
                    probes.append(
                        probe(lab(f"Shunt {_short(br.port)}"), "group2", len(elements))
                    )
                    elements.append(
                        _series_group2(
                            k, None, br.r, br.l, br.c, omega, ql=br.ql, qc=br.qc
                        )
                    )
            elif isinstance(br, Transformer):
                if br.n == 0:
                    raise ValueError(
                        f"Transformer {br.a!r}→{br.b!r} has turns ratio n = 0; "
                        "no physical transformer pins one winding at 0 V while "
                        "open-circuiting the other"
                    )
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                nr = complex(br.n)
                z_w = complex(br.r) if br.r is not None else 0j
                # Ideal ratio + winding R referred to side a: the auxiliary
                # current j is i_a (into winding A); KCL carries j out of a
                # and n·j into b; constitutive row v_a − n·v_b − r_w·j = 0.
                probes.append(
                    probe(
                        lab(f"Transformer {_short(br.a)}→{_short(br.b)}"),
                        "group2",
                        len(elements),
                    )
                )
                elements.append(
                    _Group2Element(
                        a,
                        b,
                        c_v=0j,
                        c_j=-z_w,
                        e=0j,
                        ka=1.0 + 0j,
                        kb=nr,
                        c_va=1.0 + 0j,
                        c_vb=-nr,
                    )
                )
                zl = magnetizing_impedance(br, omega)
                if zl is not None:
                    y_mag = 1.0 / zl
                    G.add_diag(a, y_mag)
                    probes.append(
                        probe(
                            lab(f"Transformer {_short(br.a)}→{_short(br.b)} (mag)"),
                            "group1",
                            ([a], np.array([[y_mag]])),
                            "mag",
                        )
                    )
            elif isinstance(br, Autotransformer):
                if not 0.0 <= br.k <= 1.0:
                    raise ValueError(
                        f"Autotransformer {br.a!r}→{br.b!r} has k = {br.k}; "
                        "coupling must be 0 ≤ k ≤ 1. Above 1 the inductance "
                        "matrix is not positive semi-definite (M² > L₁L₂) and "
                        "the winding pair would deliver more energy than it "
                        "stores — the power budget would stop balancing"
                    )
                if br.l_lower <= 0 or br.l_upper <= 0:
                    raise ValueError(
                        f"Autotransformer {br.a!r}→{br.b!r} needs positive "
                        f"section inductances; got {br.l_lower} / {br.l_upper} H"
                    )
                a_i, b_i = self.port_to_idx[br.a], self.port_to_idx[br.b]
                # Series r per section from the shared finite-Q convention.
                r1 = omega * br.l_lower / br.ql if br.ql else 0.0
                r2 = omega * br.l_upper / br.ql if br.ql else 0.0
                z1 = r1 + 1j * omega * br.l_lower
                z2 = r2 + 1j * omega * br.l_upper
                zm = 1j * omega * br.k * math.sqrt(br.l_lower * br.l_upper)
                # Both branch currents are referenced UP the winding: j1 runs
                # datum → tap (its "a side" is the datum, absent from the node
                # space), j2 runs tap → top. Each therefore enters its section
                # at the lower terminal, so the passive-sign voltage is
                #   (v_datum − v_tap) = z1·j1 + zm·j2
                #   (v_tap   − v_top) = zm·j1 + z2·j2
                # — the node potential is the NEGATIVE of the voltage across
                # the element for j1, which is where a sign slip would hide.
                # Same reference direction up the coil ⇒ flux adds ⇒ +zm.
                i1, i2 = len(elements), len(elements) + 1
                lo = lab(f"Autotransformer {_short(br.a)}→{_short(br.b)} (lower)")
                hi = lab(f"Autotransformer {_short(br.a)}→{_short(br.b)} (upper)")
                probes.append(probe(lo, "group2r", (i1, r1), "lower"))
                probes.append(probe(hi, "group2r", (i2, r2), "upper"))
                elements.append(_Group2Element(None, a_i, c_v=1.0 + 0j, c_j=z1, e=0j))
                elements.append(_Group2Element(a_i, b_i, c_v=1.0 + 0j, c_j=z2, e=0j))
                # v_a = z1·j1 + zm·j2 and v_b − v_a = zm·j1 + z2·j2: the
                # off-diagonal pair that makes this one winding, not two.
                couplings.append((i1, i2, zm))
                couplings.append((i2, i1, zm))
            elif isinstance(br, FloatingBalun):
                if br.n == 0:
                    raise ValueError(
                        f"FloatingBalun {br.primary!r}→({br.a!r},{br.b!r}) has "
                        "turns ratio n = 0; no physical balun pins the secondary "
                        "differential voltage at 0 V"
                    )
                p = self.port_to_idx[br.primary]
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                nr = complex(br.n)
                z_w = complex(br.r) if br.r is not None else 0j
                # Floating secondary (a, b) + single-ended primary p. The
                # auxiliary current j is the secondary current (into a, out of
                # b): KCL carries j out of a, j into b, and −n·j out of the
                # primary p (reciprocity pins the primary coeff = c_vc, so the
                # ideal element absorbs zero net power for any n). The
                # constitutive row v_a − v_b − n·v_p = r_w·j refers the winding
                # R to the secondary; the ideal element is lossless.
                probes.append(
                    probe(
                        lab(
                            f"FloatingBalun {_short(br.primary)}→"
                            f"({_short(br.a)},{_short(br.b)})"
                        ),
                        "group2",
                        len(elements),
                    )
                )
                elements.append(
                    _Group2Element(
                        a,
                        b,
                        c_v=0j,
                        c_j=-z_w,
                        e=0j,
                        ka=1.0 + 0j,
                        kb=1.0 + 0j,
                        c_va=1.0 + 0j,
                        c_vb=-1.0 + 0j,
                        c=p,
                        kc=-nr,
                        c_vc=-nr,
                    )
                )
                zl = magnetizing_impedance(br, omega)
                if zl is not None:
                    y_mag = 1.0 / zl
                    G.add_diag(p, y_mag)
                    probes.append(
                        probe(
                            lab(
                                f"FloatingBalun {_short(br.primary)}→"
                                f"({_short(br.a)},{_short(br.b)}) (mag)"
                            ),
                            "group1",
                            ([p], np.array([[y_mag]])),
                            "mag",
                        )
                    )
            elif isinstance(br, Load):
                # A series load needs a real current path to sit in: a gap
                # port's segment, or (issue #910) a vertex port's through-
                # current at the junction knot — the same Group-2
                # termination branch either way.
                if not isinstance(
                    self.network.ports[br.port], (PortOnWire, PortAtVertex)
                ):
                    raise ValueError(
                        f"Load on virtual port {br.port!r}: a Load is a series "
                        "impedance in an antenna current path, which only "
                        "PortOnWire and PortAtVertex have"
                    )
                # Every Load at a node shares ONE termination branch (and so
                # one current), but each keeps its own budget row and its own
                # structured identity (issue #956) — carry the branch's path
                # and index along to the emission site below.
                loads_by_node.setdefault(self.port_to_idx[br.port], []).append(
                    (br, _bpath, _bidx)
                )
            else:
                raise NotImplementedError(f"branch type {type(br).__name__}")

        # Per-port termination branches. A port may carry BOTH a source and
        # a series load (the centre-loaded driven short dipole); they chain
        # into one branch: datum —EMF—Z_L→ node. Termination tuples are
        # (column, source value, kind, z_chain): kind "v" is the Thevenin
        # branch below, kind "i" a forced-current branch (issue #442).
        emf, forced = {}, {}
        for k, kind, val in zip(
            self.driven_port_idx, self._source_kinds, self._source_values, strict=True
        ):
            if kind == "v":
                emf[k] = val
            else:
                # Parallel current sources into one node sum (KCL).
                forced[k] = forced.get(k, 0j) + val
        clash = set(emf) & set(forced)
        if clash:
            raise ValueError(
                "a voltage source and a current source share port node(s) "
                f"{sorted(clash)}: an ideal voltage source across an ideal "
                "current source is contradictory — drive the port one way"
            )
        terminations = {}
        z_ref_at = {}
        z_ref_node = self._reference_node() if z_ref else None
        for k in sorted(set(emf) | set(forced) | set(loads_by_node)):
            loads = loads_by_node.get(k, [])  # [(Load, instance_path, branch_index)]
            zs = [load_impedance(ld, omega) for ld, _p, _i in loads]
            # ONE budget row per contributing Load (issue #956), emitted here
            # rather than twice below: the forced-current and voltage
            # terminations stamp different elements but probe the same Loads,
            # through the same shared branch current, so each Load's share is
            # ½·Re(z_i)·|j|² either way ("termination_share"). Folding several
            # co-located Loads into one row would make the second one's branch
            # identity unrepresentable, which is exactly what the structured
            # key exists to fix. Ordering is unaffected: probes are read after
            # the solve, and each iteration appends only its own node's rows.
            for (ld, ld_path, ld_idx), z_ld in zip(loads, zs, strict=True):
                probes.append(
                    _Probe(
                        f"Load {ld.port}",
                        "termination_share",
                        (k, z_ld),
                        (ld_path, ld_idx, "load"),
                    )
                )
            if k in forced:
                # Forced-current termination (DrivenCurrent, issue #442):
                # constitutive row j = I, independent of any series loads —
                # they drop voltage inside the source loop without altering
                # the current, exactly NEC's LD-in-driven-segment physics.
                if not all(np.isfinite(z) for z in zs):
                    raise ValueError(
                        f"current source at port node {k} drives an open "
                        "load chain (parallel-LC trap at resonance): forcing "
                        "a current through an open is unphysical"
                    )
                terminations[k] = (len(elements), forced[k], "i", sum(zs, 0j))
                elements.append(
                    _Group2Element(None, k, c_v=0j, c_j=1.0 + 0j, e=forced[k])
                )
                continue
            e = emf.get(k, 0j)
            # Γ-referenced source (issue #746): a DRIVEN port's EMF sits behind
            # z_ref instead of pinning its node, which is the difference
            # between an ideal generator and a real one on a real feedline. The
            # answer Z = E/j − z_ref is algebraically independent of z_ref;
            # what changes is the conditioning, because Z_s = 0 is what made a
            # dead short across the port (a lossless λ/4 open stub, a k·λ/2
            # shorted one) unsolvable rather than simply Γ = −1. Undriven,
            # load-only terminations get NO z_ref — a fictitious 50 Ω inside a
            # real load chain would be a modelling error, not a reference —
            # and neither does any port but the one reference node.
            zr = complex(z_ref) if k == z_ref_node else 0j
            if zr:
                z_ref_at[k] = zr
            if len(loads) == 1 and loads[0][0].parallel:
                # Parallel-LC trap: the tank admittance is the finite
                # quantity (→ 0 at resonance, the intended open circuit);
                # the impedance form would blow up there. Putting z_ref in
                # series is y → y/(1 + z_ref·y), which stays finite at both
                # ends (→ 0 at resonance, → 1/z_ref for a shorted tank).
                y = load_series_admittance(loads[0][0], omega)
                y = y / (1.0 + zr * y)
                el = _Group2Element(None, k, c_v=y, c_j=1.0 + 0j, e=y * e)
            elif all(np.isfinite(z) for z in zs):
                # Series composition of every load (plus the EMF). Includes
                # the no-load case z = 0: an ideal voltage-source pin.
                el = _Group2Element(None, k, c_v=1.0 + 0j, c_j=sum(zs, zr), e=e)
            else:
                # A chain containing an at-resonance trap is an open — z_ref in
                # series with an open is still an open, and its Γ is +1.
                el = _Group2Element(None, k, c_v=0j, c_j=1.0 + 0j, e=0j)
            terminations[k] = (len(elements), e, "v", 0j)
            elements.append(el)

        # Dense below the threshold (bit for bit the historical system), sparse
        # at and above it; the unit is the MNA dimension n + m.
        if not _reduce.use_sparse(self.n_nodes + len(elements)):
            G = G.dense()
        return MNASystem(
            G,
            elements,
            terminations,
            probes=probes,
            diagnose=lambda wl=wavelength: self._singularity_report(wl),
            couplings=couplings,
            z_ref=z_ref,
            z_ref_at=z_ref_at,
        )

    def _physical_port_voltages(self, v):
        """Node voltages -> PHYSICAL port voltages. They differ only for a
        floating gap port, whose voltage is the drop ACROSS the gap,
        ``v[p] - v[n]``, not the "+" node's voltage against a datum it is
        deliberately not bonded to. The excited far-field/current solve forces
        these at the real feeds, so getting it wrong under-drives the antenna
        (and silently: the driven-point impedance reads off the termination
        branch and stays correct)."""
        if not self._floating:
            return v.copy()
        out = v.copy()
        for p_idx, n_idx in self._floating.values():
            out[p_idx] = v[p_idx] - v[n_idx]
        return out

    def resolve_voltages(self, system):
        """Return the (n_total,) physical port-voltage vector of the solved
        network: voltage-driven ports at their applied voltages, current-
        driven ports at whatever gap voltage the forced current produced,
        loaded ports at the gap voltage V_k = V_src − Z_L·I_k (the load
        shapes the current the way NEC2's ld_card does), every other port
        floating with I_ext = 0.
        These are the voltages the excited far-field/current solver forces
        at the real feeds."""
        v, _j = system.solve()
        return self._physical_port_voltages(v)

    def excited_state(self, Y_real, wavelength):
        """Physical port voltages + radiation efficiency + per-branch power
        budget for the CURRENT-DISTRIBUTION / far-field solve — the same
        MNA solve as the impedance path, read out for power bookkeeping.

        Returns ``(V_full, efficiency, p_in, budget)``:
          V_full      -- (n_total,) port voltages to force in the excited solver
          efficiency  -- P_radiated / P_input = 1 - P_dissipated / P_input, the
                         fraction of input power radiated rather than burned in
                         the network. A load-free / lossless network
                         returns 1.0.
          p_in        -- input power 1/2 Re(Σ V_src · I*) in watts, the gain
                         normaliser (gain = 4π·U/P_in); it already includes the
                         power burned in the network.
          budget      -- list of ``_BudgetEntry`` per network branch, in
                         branch order (issue #299): TL and parallel-Shunt
                         stamps via ½·Re(v†·Y_br·v), TwoPort/series-Shunt
                         via their explicit branch currents, Loads via
                         ½·Re(z_load)·|j|² on the termination branch they
                         share. Lossless branches report ~0. Power delivered
                         to the antenna (radiated + any wire/ground loss
                         inside the MoM solve) is p_in − Σ watts. Each entry
                         still unpacks as ``(label, watts)`` (issue #956) and
                         additionally carries ``.key`` — ``(instance_path,
                         branch_index, subprobe)`` — a structured identity a
                         consumer can match on instead of the label string.

        A CAVEAT for anyone keying on ``.key`` (issue #956): the budget a real
        consumer sees is a MIXED list. antennaknobs' engine layer appends its
        own rows to this one — its momwire engine adds the wire-loss row as a
        plain 2-tuple, and its nec5 engine builds the whole budget out of
        plain 2-tuples — so a consumer must tolerate rows without ``.key``
        (``getattr(row, "key", None)``) rather than assume every row has one.
        Until those appenders emit keyed rows, ``.key`` is an ADDITION to the
        label channel, not a replacement for it, and the label freeze this
        module's docstring records cannot be lifted.

        The termination branches carry the physical port currents, so the
        source power reads directly off the solution vector:

            p_in   = ½ Σ Re(E_k · j_k*)          (E = 0 terms vanish)

        This path deliberately keeps the IDEAL-generator stamp (``z_ref = 0``)
        while the impedance/Γ path uses `Z_REF_DEFAULT` — a second solve, not
        an rcond-triggered fallback (issue #746). Two reasons. The port
        voltages here *are* the excitation forced into the MoM solver and the
        normaliser p_in = ½ΣRe(E·j*) is defined at the source terminals, so a
        source impedance would divide the drive and rescale every gain in the
        package. And a fallback would make those numbers depend on a
        conditioning threshold — the same design at two frequencies either
        side of it would report gains normalised differently, silently. The
        cost is one extra (n_ports + n_branches)-sized zgesvx per solve, which
        is nothing beside the MoM factorisation that produced Y, and the two
        systems were already assembled separately anyway.

        The consequence to know: a topology that shorts the driven port (a
        lossless λ/4 open stub across the feed) now has a perfectly good
        impedance answer, Z = 0 / Γ = −1, and still has no far field — the
        current an ideal source drives into a dead short is unbounded, so
        there is nothing to normalise against. That asymmetry is physical.

        Reactive elements burn nothing and report ~0 in the budget.
        Efficiency counts EVERY dissipative network branch — resistive
        TwoPort/Shunt elements and lossy TLs included (issue #299; the
        pre-#299 accounting counted Load terminations only, so designs
        with resistive coupling/matching branches now report a lower,
        physically consistent efficiency).
        """
        system = self.apply_branches(Y_real, wavelength)
        v, j = system.solve()
        p_in = 0.0
        for k, (col, e, tkind, z_chain) in system.terminations.items():
            if tkind == "i":
                # Current source: its terminal voltage sits behind the load
                # chain, v_src = v_k + z_chain·j; p = ½·Re(v_src·j*).
                v_src = v[k] + z_chain * j[col]
                p_in += 0.5 * float(np.real(v_src * np.conj(j[col])))
            else:
                p_in += 0.5 * float(np.real(e * np.conj(j[col])))
        budget = [
            _BudgetEntry(p[0], system.branch_power(p), p.key) for p in system.probes
        ]
        p_diss = sum(w for _label, w in budget)
        # A lossless network's probes read pure float noise (|w| ~ 1e-17·p_in
        # from the reactive TL stamp); snap that to exactly 1.0 so lossless
        # designs keep reporting unity efficiency.
        if p_in > 0.0 and abs(p_diss) <= 1e-9 * p_in:
            p_diss = 0.0
        efficiency = 1.0 if p_in <= 0.0 else max(0.0, min(1.0, 1.0 - p_diss / p_in))
        return self._physical_port_voltages(v), efficiency, p_in, budget

    def impedance_from_y(self, system):
        """Driven-point impedance per Driven source from an `apply_branches`
        result: Z = E / j_term − z_ref, the termination EMF over its delivered
        current less the source impedance it was stamped behind — read
        straight off the solution vector, no Y·V post-multiply. ``z_ref`` is 0
        for the ideal-generator stamp, so this is the historical E/j there."""
        v, j = system.solve()
        out = []
        for k, kind in zip(self.driven_port_idx, self._source_kinds, strict=True):
            col, e, _tkind, z_chain = system.terminations[k]
            if kind == "i":
                # Forced-current port (issue #442): the source impedance is
                # the gap voltage over the forced current, plus the series
                # load chain it drives through — mirroring how the voltage
                # form's E/j includes its series loads. A current source is
                # its own reference (Z_s = ∞), so z_ref never applies here.
                if j[col] == 0:
                    out.append(complex(float("inf"), 0.0))
                else:
                    out.append(complex(v[k] / j[col] + z_chain))
                continue
            if j[col] == 0:
                # Open-circuited source — no current path from the port
                # (e.g. a matching-network series capacitor slider at 0 F,
                # which is an open, not an absent element). The physical
                # driving-point impedance is ∞; report it as a clean real
                # infinity instead of dividing by zero (numpy would warn
                # and produce inf+nanj). Issue #289. Its Γ is a finite +1,
                # which is the whole argument for emitting Γ as well.
                out.append(complex(float("inf"), 0.0))
            else:
                out.append(complex(e / j[col] - system.z_ref_at.get(k, 0j)))
        return out

    def reflection_from_y(self, system):
        """Driven-port reflection coefficient Γ, referenced to the ``z_ref``
        the system was stamped with (issue #746).

        Γ = (2·v_ref − E)/E with v_ref = E − z_ref·j the voltage at the
        reference plane — the junction between the source impedance and
        whatever the port drives. For an unloaded port that plane IS the port
        node, so this is literally (2·v_k − E)/E; with a series `Load` the
        plane sits ahead of the load, matching `impedance_from_y`'s contract
        that Z includes the load chain.

        Read this way Γ never has a pole. The two cases that break Z break it
        by dividing: a shorted port (a lossless λ/4 open stub, a k·λ/2 shorted
        one) is Γ = −1, and an open port — where j is exactly 0 and Z is
        reported as ∞ — is Γ = +1 exactly, no sentinel and no clamp.

        A forced-current port has no z_ref (Z_s = ∞ is its reference), so its
        Γ is converted from Z; that conversion is the one that can still meet
        an infinity, and it maps to Γ = +1 by the same limit.
        """
        z_ref = system.z_ref
        if z_ref == 0:
            raise ValueError(
                "Γ is undefined for an ideal-generator solve (z_ref = 0): the "
                "reference plane has no impedance to reflect against. Stamp "
                "with apply_branches(..., z_ref=...) — driven_reflection() does"
            )
        _v, j = system.solve()
        out = []
        for k, kind, z in zip(
            self.driven_port_idx,
            self._source_kinds,
            self.impedance_from_y(system),
            strict=True,
        ):
            col, e, _tkind, _z_chain = system.terminations[k]
            zr = system.z_ref_at.get(k)
            if kind == "i" or zr is None:
                # No reference plane at this port: a forced-current source is
                # its own reference (Z_s = ∞), and a 0 V pin has no incident
                # wave. Fall back to the definition, which meets an infinity
                # only at a true open — Γ = +1 by the same limit.
                out.append(
                    complex(1.0, 0.0)
                    if not np.isfinite(z)
                    else complex((z - z_ref) / (z + z_ref))
                )
                continue
            out.append(complex((2.0 * (e - zr * j[col]) - e) / e))
        return out

    def driven_impedance(self, Y_real, wavelength, *, z_ref=None):
        """Convenience: stamp branches onto the raw real-port Y and reduce
        to the driven-port impedance(s) in one call.

        Uses the Γ-referenced source stamp by default (issue #746). Z is
        algebraically independent of ``z_ref`` — what it buys is a system that
        stays well-conditioned when the port is shorted or opened, which the
        ideal generator does not.
        """
        z_ref = Z_REF_DEFAULT if z_ref is None else z_ref
        return self.impedance_from_y(
            self.apply_branches(Y_real, wavelength, z_ref=z_ref)
        )

    def driven_reflection(self, Y_real, wavelength, *, z_ref=None):
        """Convenience: driven-port Γ referenced to ``z_ref`` in one call."""
        z_ref = Z_REF_DEFAULT if z_ref is None else z_ref
        return self.reflection_from_y(
            self.apply_branches(Y_real, wavelength, z_ref=z_ref)
        )
