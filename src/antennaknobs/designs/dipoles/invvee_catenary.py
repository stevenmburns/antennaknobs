"""Inverted-vee dipole whose arms hang as real catenaries (issue #698, unit 2).

Every other inv-vee in the catalog (`dipoles.invvee`) treats an arm as a
straight chord at a fixed droop angle. A real wire does not do that: strung
from the apex to a stake under some rope tension, it sags into the shape
`antennaknobs.catenary` solves for — a hanging-chain equilibrium set by the
wire's own weight per metre and how hard the halyard pulls. This design wires
that solve into the geometry: `build_wires()` emits each arm as a chord
polyline sampled uniformly along the solved catenary's arc length, following
the `specialty.faceted_helix` curved-wire idiom (`Wire(p_i, p_{i+1},
n_seg=None)`, `auto_mesh` owning the electrical density — issue #630's
lesson: never hand-freeze `n_seg` on a chorded curve).

The model: tensioned halyard (catenary's "model 1")
----------------------------------------------------
Each arm is `catenary.solve_tensioned`: a wire of *fixed cut length*
`0.25 * design_wavelength * length_factor` — the same length law
`dipoles.invvee` uses for its straight arm — hangs from the apex, and its far
end is held by a massless rope of specified tension `tension_n` running to a
fixed stake. The wire's end position is not an input; equilibrium places it,
which is the whole point of the model: `tension_n` is the design knob and the
arm's droop is the answer.

This keeps the **electrical knob and the mechanical knob orthogonal by
construction** — `length_factor` sets how much wire is up there;
`tension_n` sets how it hangs. Scrubbing tension never changes the cut
length, only the shape, exactly as issue #698 requires ("the electrical
knob must not move when tension changes"). As `tension_n -> infinity` the
arm's shape converges to the straight chord from the apex toward the stake,
which is the design's own built-in regression oracle against a straight-arm
inv-vee of the same geometry (see `tests/test_invvee_catenary.py`).

Feasibility: the stake must be beyond the arm
----------------------------------------------
`solve_tensioned` requires the stake to be farther from the apex than the
wire is long — a taut wire reaching for a stake it has already overshot has
no equilibrium at any tension. With the apex at `(0, base)` and the stake at
`(stake_dist, stake_height)` in the arm's own vertical plane, this needs

    hypot(stake_dist, base - stake_height) > 0.25 * design_wavelength * length_factor

The stock `stake_dist` (~1.15x the default arm length) and `stake_height`
(1.0 m) satisfy this with a comfortable margin even at the top of the
`length_factor` UI range, because most of the reach comes from the mast
height (`base - stake_height`) rather than the horizontal offset — see the
module tests for the numeric check. Push the knobs hard enough (a very long
arm, a stake dragged close to directly under the apex) and the solver's own
`ValueError` explains exactly why no rig exists; this design does not
second-guess or clamp that error.

Geometry
--------
The apex sits on the mast at `(0, 0, base)`. A short feed wire (the
`doublet_ladder_tuner` / `invvee` idiom: `eps = 0.05` m either side of
centre) carries the driven gap; each catenary arm starts from that feed
wire's end and runs in the +y or -y azimuth (no azimuth knob in this unit —
the two arms are always 180 deg apart). The catenary solve itself works in
the arm's 2-D vertical plane (`horizontal`, `z`); the design maps
`horizontal -> +-y` and holds `x = 0`.

Requires a real `WireSpec`: a weightless wire has no catenary
(`solve_tensioned` raises `ValueError` for `wire_weight_n_per_m <= 0`, and
this module raises its own clear error first if `build_wire_material()`
returns `None`). The stock wire is `18-awg-pvc` (via `wire_type`), which
carries a real `weight_g_per_m` — swap the catalog entry and the antenna
sags differently AND its loss/insulation electrical behaviour changes in one
move (the same one-knob-two-effects story as `dipoles.pota_invvee`, issue
#316).

`chords_per_arm` (default 14) is the *geometric* fidelity knob, independent
of the electrical mesh: it is passed straight through as
`samples_per_segment = chords_per_arm + 1` to `solve_tensioned`, so the
solver's own uniform-in-arc-length sampling IS the chord split.

See also
--------
`antennaknobs.catenary` for the chain solver and its numerics/sign
conventions; `dipoles.invvee` for the base design and param conventions;
`specialty.faceted_helix` for the chord-polyline-as-geometry precedent.
Issue #698.
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.catenary import ChainSolution, solve_tensioned, weight_n_per_m
from antennaknobs.network import WIRES, Wire

# Half-gap either side of the mast centreline for the driven feed wire — the
# same value `dipoles.invvee` and `wire.doublet_ladder_tuner` use.
_EPS = 0.05


class Builder(AntennaBuilder):
    """A subclass of `AntennaBuilder` directly, not `dipoles.invvee`: the
    variant-discovery convention (`web.adapter._discover_variants`) walks
    `dir(cls)`, so subclassing `InvVee` would silently inherit its
    `dipole_params` / `three_halves_params` / `classic_edz_params`
    overlays — every one of which sets `angle_deg`, a knob this design does
    not have (droop is physics here, not a param). Subclassing
    `AntennaBuilder` sidesteps that entirely; the param *conventions* (name
    the length knob `length_factor`, keep `design_freq`/`freq`/`base`) are
    still reused, per the issue's brief.
    """

    default_params = MappingProxyType(
        {
            # Same band/height/length-law defaults as dipoles.invvee.
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            "length_factor": 0.9719,
            # Rope tension holding each arm's far end (issue #698 model 1).
            # ~9 lbf: a realistic hand-tensioned dacron halyard pull.
            "tension_n": 40.0,
            # Stake position in the arm's vertical plane, horizontal
            # distance from the mast and height above ground. Defaults
            # chosen so hypot(stake_dist, base - stake_height) clears the
            # longest arm the length_factor UI range can produce (see the
            # module docstring and the feasibility test).
            "stake_dist": 2.94,
            "stake_height": 1.0,
            # Chord count per arm: geometric fidelity, orthogonal to the
            # electrical mesh density (nominal_nsegs / auto_mesh).
            "chords_per_arm": 14,
            # Real wire is mandatory (a weightless wire has no catenary);
            # 18 AWG PVC is a common real-world halyard-fed hookup wire.
            "wire_type": "18-awg-pvc",
            "ui_params": MappingProxyType(
                {
                    "length_factor": {"min": 0.8, "max": 1.25},
                    "tension_n": {"min": 2.0, "max": 400.0},
                    "stake_dist": {"min": 1.0, "max": 6.0},
                    "stake_height": {"min": 0.0, "max": 3.0},
                    "chords_per_arm": {"min": 6, "max": 32, "step": 1},
                    "wire_type": {"enum_options": tuple(sorted(WIRES))},
                }
            ),
        }
    )

    def rig_solutions(self) -> ChainSolution:
        """Solve one arm's catenary (both arms are mirror images in y, so
        one solve in the shared vertical plane covers both).

        `build_wires()` calls this same method for its geometry, so the
        rigged shape and any diagnostics a caller reads off it (sag,
        tension, arc length) can never drift apart.
        """
        spec = self.build_wire_material()
        if spec is None or not spec.weight_g_per_m:
            raise ValueError(
                f"{type(self).__name__}: catenary sag needs a real WireSpec "
                "with weight_g_per_m > 0 (a weightless wire has no "
                f"catenary); got {spec!r} from build_wire_material() — set "
                "wire_type to a catalog entry such as '18-awg-pvc'."
            )

        arm_length_m = 0.25 * self.design_wavelength * self.length_factor
        wire_weight = weight_n_per_m(spec.weight_g_per_m)

        return solve_tensioned(
            apex=(_EPS, self.base),
            wire_length_m=arm_length_m,
            wire_weight_n_per_m=wire_weight,
            stake=(self.stake_dist, self.stake_height),
            rope_tension_n=self.tension_n,
            samples_per_segment=int(self.chords_per_arm) + 1,
            name="invvee_catenary_arm",
        )

    # build_wire_material() is intentionally NOT overridden: the inherited
    # AntennaBuilder default already resolves a `wire_type` param via
    # `wire_from_catalog` (the same mechanism `dipoles.pota_invvee` relies
    # on), and the stock `wire_type` above already names a real WireSpec.

    def build_wires(self):
        b = self.base
        solution = self.rig_solutions()
        # (horizontal, z) samples, uniform in arc length, apex-first.
        plane_points = solution.segments[0].points

        wires = [
            # Driven gap at the apex — the invvee/doublet_ladder_tuner
            # idiom: a short wire from -eps to +eps carries the excitation,
            # and each catenary arm starts from one of its ends.
            Wire((0.0, -_EPS, b), (0.0, _EPS, b), ex=1 + 0j),
        ]
        for sign in (1.0, -1.0):
            arm_points = [(0.0, sign * h, z) for h, z in plane_points]
            wires.extend(
                Wire(p0, p1) for p0, p1 in zip(arm_points[:-1], arm_points[1:])
            )
        return wires
