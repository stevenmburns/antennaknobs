"""Four-band trapped fan dipole — combines `fandipole` geometry with the
`trap_dipole` Load(parallel=True) idiom.

Two physical fan-dipole spokes (per arm), each broken by a parallel-LC
trap segment partway out. At the trap's resonant frequency, the tank is
high-Z and interrupts the spoke's current — only the inner stub radiates,
behaving as a shorter dipole. Well below the trap, the tank looks
inductive and electrically lengthens the spoke so the full physical
length sets the low-band tuning.

Default tuning:

  spoke 0 (long)   — full length resonant near 17m (18.16 MHz);
                     trap at 12m (24.97 MHz) shortens it to a 12m dipole.
  spoke 1 (short)  — full length resonant near 15m (21.38 MHz);
                     trap at 10m (28.47 MHz) shortens it to a 10m dipole.

→ four bands (10m / 12m / 15m / 17m) from a single shared feed.

The cone geometry is the same fan layout as `fandipole.py`: each spoke
shares a common droop-angle direction (0, Zc, −Zs) from the cone apex
outward.
Each arm of each spoke is broken into

    S → A[i]              (cone segment)
    A[i] → trap_inner     (inner outer segment)
    trap_inner → trap_outer  (one segment, named "trap_<sign>_b<i>")
    trap_outer → tip      (outer segment)

with two arms per spoke (mirrored via ry()), so a 2-spoke design has
four traps total. The trap segment is wire-interior, so its basis
function carries the actual arm current and Load(parallel=True) acts
exactly as NEC2's ld_card type-1 would.
"""

from antennaknobs import AntennaBuilder
from antennaknobs.network import Driven, Load, Network, PortOnWire

import math
from types import MappingProxyType


C_LIGHT_MHZ_M = 299.792458


# Defaults: 5 µH traps, C chosen so each trap LC-resonates at its trap_freq.
# length_factor ≈ 0.49 captures the usual end-effect shortening on a fan
# spoke; tweak per band if a sweep shows the resonance off-target.
# All four bands tuned by `cli optimize --resonance`. Both traps have
# their L/C decoupled from the usual L↔C lockstep at ω₀ = trap_freq, in
# opposite directions:
#   - Band 1: L pushed DOWN to ~0.2 µH (with C → ~159 pF). The 10m trap
#     is only ~7 MHz above 15m, so the stock 5 µH puts ~+j1.4 kΩ on the
#     spoke at 15m — enough to smother every series resonance. Cutting L
#     weakens that loading; the 15m spoke can then find resonance at its
#     physical length, while the tank still LC-resonates at 28.47 to
#     interrupt the spoke at 10m.
#   - Band 0: L pushed UP to ~11.85 µH (with C → ~3.4 pF). Heavier
#     loading at 17m concentrates current toward the feed and lowers the
#     resonant Re(Z) toward 50 Ω, shaving max SWR50 from 1.31 to 1.27.
#     Beyond ~11.9 µH the 17m series resonance merges with the adjacent
#     parallel-resonance pole and disappears.
# A droop angle ≈34.2° (instead of the original ~26.6°) drops the
# resistances uniformly so they straddle 50 Ω: 17m and 10m sit at the
# extremes with
# matching SWR50≈1.21, and the in-band bands (15m/12m) come in lower.
# A small `freq_shift` = 0.98 on band 1 nudges 10m into a different mode
# where Re(Z) ≈ 50 Ω (the trap doesn't fully open at 10m, the outer
# extension joins in, and the inner settles at ~0.40·λ/2 instead of
# ~0.50). 10m's SWR50 drops from 1.20 to 1.02 with the other three
# bands largely unchanged. (Band-0 shift has near-zero leverage on
# Re17 — kept at 1.0.)
# Length factors tuned against MomwireEngine with BSplineSolver(degree=2)
# at nominal_nsegs=41. After moving to adaptive per-wire segmentation
# (target_seg_len = max_wire / nominal_nsegs, see build_wires), both Bs2
# and the (since retired) Triangular basis stay essentially flat across N=21..81 — drift ≤ 0.22 Ω
# on every band — and agree with each other to ~1 Ω at the converged
# limit. Sinusoidal still wanders 2–8 Ω over the same N range (basis-
# family issue, not segmentation). PyNEC sits ~10 Ω above the momwire
# cluster on every band — a systematic offset — and on 10m / 12m
# actually drifts UP with refinement (57.7 → 67.2 Ω at 10m from N=21 to
# N=81), which is its own discretization story.
# Final SWR50 at target freqs (Bs2 @ N=41): 17m=1.04, 15m=1.02, 12m=1.19, 10m=1.13.
# Plan to verify by measurement after build.
_BAND_17_12 = {
    "full_freq": 18.1575,
    "trap_freq": 24.97,
    "full_length_factor": 0.442400,
    "inner_length_factor": 0.498100,
    # L=3 µH well below the parallel-resonance "cliff" (the regime
    # where the 17m series resonance merges with the adjacent parallel-
    # resonance pole at L ≳ 11.9 µH). The high-L cliff gives a marginally
    # better ideal SWR50 (1.05 vs 1.07) but the resonance Q is so high
    # there that ±1 cm length error sends SWR to 3-5. At L=3 the ±1 cm
    # tolerance is ≤ 1.17 SWR — buildable. C tracks at LC-resonance for
    # 24.97 MHz given this L.
    "trap_L_uH": 3.0,
    # Per-band trap resonant-freq multiplier (dimensionless). The tank's
    # C is computed from L and (trap_freq × freq_shift) at network-build
    # time, so freq_shift detunes ω₀ without an explicit C knob. Band-0's
    # shift has near-zero leverage on Re(Z) at 17m so it stays at 1.0.
    "freq_shift": 1.0,
}

_BAND_15_10 = {
    "full_freq": 21.383,
    "trap_freq": 28.47,
    "full_length_factor": 0.453200,
    "inner_length_factor": 0.447400,
    # L=1 µH — practical minimum for a hand-wound air-core coil
    # (sub-µH coils have inductance dominated by stray/lead effects and
    # are hard to build reproducibly). C tracks at LC-resonance for
    # 28.47 MHz. The freq_shift below pulls effective ω₀ slightly to
    # bring 10m into a clean mode-jump resonance.
    "trap_L_uH": 1.0,
    # Set slightly below 1.0 so the trap is just past resonance at 10m.
    # The trap doesn't fully open, the outer extension joins in, and
    # the inner sits in a different mode (~0.40·λ/2 instead of ~0.50).
    # Net effect: 10m's resonant Re(Z) jumps from ~42 Ω toward ~50 Ω,
    # SWR50 at 10m drops from 1.20 to 1.02.
    "freq_shift": 0.95,
}


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # `freq` is the measurement frequency the live solve evaluates
            # Z_in at. Geometry doesn't read it — each band sizes itself
            # from per-band full_freq / trap_freq / *_length_factor. The
            # frontend overwrites it from the meas-freq slider on every
            # tick; this default only seeds the very first response.
            "freq": _BAND_15_10["trap_freq"],
            "base": 7.0,
            # Same fan-spoke droop angle as fandipole — each spoke drops at
            # this droop angle (deg) from the cone apex outward
            # (y_dir=Zc, z_dir=−Zs). Droop angle of the inverted-vee arms
            # (descent angle from horizontal). A steeper angle lowers
            # radiation resistance for all four bands simultaneously. Tuned
            # to ~34.2° so the resonant Re(Z) values straddle 50 Ω evenly —
            # 17m and 10m end up at the two extremes (~60 Ω and ~42 Ω) with
            # matching SWR50 ≈ 1.21, the lower bound for max-SWR given the
            # geometry.
            "angle_deg": 34.2157,
            # Length (m) of the single-segment "trap wire" carrying the
            # named Load port. Should be much shorter than λ so radiation
            # from the trap segment itself is negligible.
            "trap_seg_m": 0.05,
            # Pinned at 2 — the design is hard-coded to two parallel
            # spokes. Exposed in default_params (with min=max=2 in
            # ui_params below) so the bands group has a `repeat_count`
            # to reference, satisfying the schema adapter's contract.
            "n_bands": 2,
            # UI exposure for the `bands` group + per-leaf range hints.
            # tuple-of-dicts in default_params becomes a ParamGroupSpec
            # in the schema; the `bands` dict below tells the adapter how
            # to render each band-row in the sidebar.
            "ui_params": MappingProxyType(
                {
                    "n_bands": {"min": 1, "max": 2, "step": 1},
                    "bands": {
                        "label_template": "band {i}",
                        "repeat_count": "n_bands",
                        "max_repeats": 2,
                        "link_meas_freq_to_param": "full_freq",
                        "full_freq": {
                            "min": 13.5,
                            "max": 30.2,
                            "step": 0.001,
                            "precision": 3,
                            "unit": " MHz",
                        },
                        "trap_freq": {
                            "min": 13.5,
                            "max": 30.2,
                            "step": 0.001,
                            "precision": 3,
                            "unit": " MHz",
                        },
                        "full_length_factor": {
                            "min": 0.30,
                            "max": 0.60,
                            "step": 0.0005,
                            "precision": 4,
                        },
                        "inner_length_factor": {
                            "min": 0.30,
                            "max": 0.60,
                            "step": 0.0005,
                            "precision": 4,
                        },
                        "trap_L_uH": {
                            "min": 0.1,
                            "max": 20.0,
                            "step": 0.01,
                            "precision": 3,
                            "unit": " µH",
                        },
                        # Per-band trap resonant-freq multiplier. Scales
                        # the tank's effective ω₀ (applied internally as
                        # C_eff = trap_C_pF / freq_shift²). 1.0 = no
                        # shift; values <1 push ω₀ down, >1 push it up.
                        "freq_shift": {
                            "min": 0.8,
                            "max": 1.2,
                            "step": 0.001,
                            "precision": 3,
                        },
                    },
                }
            ),
            # Per-band tuning. Each entry: low-band freq (full antenna),
            # high-band freq (trap resonance + inner stub length), per-band
            # length-factor knobs, and the trap's L/C.
            "bands": (_BAND_17_12, _BAND_15_10),
        }
    )

    # Per-band tuning variants. Each one anchors `freq` at the band's
    # target so `cli optimize --resonance --params bands.<i>.<which>_length_factor`
    # drives the right resonance into place. Used to refine defaults; once
    # the optimized length factors are folded back into the `bands` tuple
    # above these are just convenience entry points.
    # Overlay default_params, anchoring only `freq` (band1_inner's target
    # equals the default freq, so it resolves back to the default geometry).
    band0_inner_params = MappingProxyType({"freq": _BAND_17_12["trap_freq"]})
    band1_inner_params = MappingProxyType({"freq": _BAND_15_10["trap_freq"]})
    band0_full_params = MappingProxyType({"freq": _BAND_17_12["full_freq"]})
    band1_full_params = MappingProxyType({"freq": _BAND_15_10["full_freq"]})

    def build_wires(self):
        eps = 0.01
        radius = 0.12

        n_bands = int(self.n_bands)
        if n_bands != 2:
            raise ValueError(
                f"trap_fan_dipole is a 2-spoke design; got n_bands={n_bands}"
            )
        bands = tuple(self.bands)[:n_bands]

        # Zc, Zs are the cos/sin of the droop angle — the unit fan-spoke
        # direction (0, Zc, -Zs) shared by every spoke beyond the cone.
        theta = math.radians(self.angle_deg)
        Zc = math.cos(theta)
        Zs = math.sin(theta)

        def ry(p):
            return p[0], -p[1], p[2]

        S = (0, eps, 0)
        T = ry(S)

        # Each band's spoke originates from a short horizontal pigtail at
        # ±radius in x from the feed. The pigtail puts band 0 and band 1
        # on opposite sides of the feed (separated by 2·radius along x);
        # beyond the pigtail each spoke extends in the shared inverted-vee
        # direction (0, Zc, −Zs). The two spokes are then parallel
        # everywhere except the small horizontal segment near the feed,
        # which keeps the `angle_deg` parameter from also controlling the
        # band-spacing direction (a problem the original cone-apex layout
        # had — the droop angle and band spacing were entangled near the
        # feed).
        A = [
            (+radius, S[1], S[2]),  # band 0 on the +x side
            (-radius, S[1], S[2]),  # band 1 on the −x side
        ]

        def dist(p0, p1):
            return math.sqrt(sum((x0 - x1) ** 2 for x0, x1 in zip(p0, p1)))

        # Outward direction shared by every spoke beyond the cone (the
        # "fan" direction): pure (0, Zc, −Zs).
        def offset_outward(p, q):
            return (p[0], p[1] + q * Zc, p[2] - q * Zs)

        trap_seg = float(self.trap_seg_m)

        # For each spoke, derive the three outer waypoints along the
        # shared outward direction:
        #   trap_inner = A + q1
        #   trap_outer = A + q1 + trap_seg
        #   tip        = A + q1 + trap_seg + q2
        # with q1 chosen so dist(S,A) + q1 = inner half-length, and the
        # full half-length (q1 + trap_seg + q2) set by the low-band freq.
        spokes = []
        for i, b in enumerate(bands):
            full_half = float(b["full_length_factor"]) * (
                0.5 * C_LIGHT_MHZ_M / float(b["full_freq"])
            )
            inner_half = float(b["inner_length_factor"]) * (
                0.5 * C_LIGHT_MHZ_M / float(b["trap_freq"])
            )

            q1 = inner_half - dist(S, A[i])
            q2 = full_half - inner_half - trap_seg
            if q1 <= 0:
                raise ValueError(
                    f"band {i}: inner half-length {inner_half:.3f} m is "
                    f"shorter than the cone segment {dist(S, A[i]):.3f} m — "
                    "shorten the cone or pick a lower trap_freq"
                )
            if q2 <= 0:
                raise ValueError(
                    f"band {i}: full half-length {full_half:.3f} m leaves no "
                    f"room past the trap (inner {inner_half:.3f} + trap "
                    f"{trap_seg:.3f}) — pick a lower full_freq or shorter inner"
                )

            trap_in = offset_outward(A[i], q1)
            trap_out = offset_outward(A[i], q1 + trap_seg)
            tip = offset_outward(A[i], q1 + trap_seg + q2)
            spokes.append((trap_in, trap_out, tip))

        # Adaptive segmentation: size each variable-length wire (cone +
        # inner outer + outer) so segment length is near-constant across
        # the antenna. nominal_nsegs sets the count for the longest such
        # wire; everything else scales proportionally. Trap segments are
        # pinned to 1 (load-port convention — the named port lives on a
        # single basis function). The feed bridge meshes via n_for like
        # the rest (1 segment at the default mesh, which is fine for the
        # BSpline d=2 basis this design is tuned against; the retired
        # triangular basis couldn't drive a 1-segment feed gap).
        adaptive_lengths = []
        for i, (trap_in, trap_out, tip) in enumerate(spokes):
            adaptive_lengths.append(dist(S, A[i]))
            adaptive_lengths.append(dist(A[i], trap_in))
            adaptive_lengths.append(dist(trap_out, tip))
        target_seg_len = max(adaptive_lengths) / self.nominal_nsegs

        def n_for(length):
            return max(1, round(length / target_seg_len))

        tups = []
        for i, (trap_in, trap_out, tip) in enumerate(spokes):
            # +y arm
            tups.append((S, A[i], n_for(dist(S, A[i])), None))
            tups.append((A[i], trap_in, n_for(dist(A[i], trap_in)), None))
            tups.append((trap_in, trap_out, 1, None, f"trap_p_b{i}"))
            tups.append((trap_out, tip, n_for(dist(trap_out, tip)), None))

            # −y arm (mirror via ry)
            Ay = ry(A[i])
            tin_y = ry(trap_in)
            tout_y = ry(trap_out)
            tip_y = ry(tip)
            tups.append((T, Ay, n_for(dist(T, Ay)), None))
            tups.append((Ay, tin_y, n_for(dist(Ay, tin_y)), None))
            tups.append((tin_y, tout_y, 1, None, f"trap_n_b{i}"))
            tups.append((tout_y, tip_y, n_for(dist(tout_y, tip_y)), None))

        # Feed wire — named "feed", source supplied by build_network().
        # Meshed via n_for like the rest (1 segment at the default mesh);
        # the BSpline d=2 basis handles a 1-segment feed cleanly.
        tups.append((T, S, n_for(dist(T, S)), None, "feed"))

        # Lift to base height.
        zoff = self.base
        lifted = []
        for t in tups:
            (x0, y0, z0), (x1, y1, z1) = t[0], t[1]
            lifted.append(((x0, y0, z0 + zoff), (x1, y1, z1 + zoff), *t[2:]))
        return lifted

    def build_network(self):
        bands = tuple(self.bands)
        ports = {"feed": PortOnWire("feed")}
        branches = []
        for i, b in enumerate(bands):
            L = float(b["trap_L_uH"]) * 1e-6
            # Tank C is whatever LC-resonates at (trap_freq × freq_shift)
            # given L. freq_shift = 1 ⇒ tank resonates exactly at
            # trap_freq; values <1 push ω₀ down, >1 push it up.
            shift = float(b.get("freq_shift", 1.0))
            omega0 = 2 * math.pi * float(b["trap_freq"]) * 1e6 * shift
            C = 1.0 / (omega0**2 * L)
            for sign in ("p", "n"):
                name = f"trap_{sign}_b{i}"
                ports[name] = PortOnWire(name)
                branches.append(Load(port=name, l=L, c=C, parallel=True))
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
