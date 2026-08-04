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

Two rig models share the same wire and geometry idiom, picked by `rig_model`;
`rig_solutions()` is the single method that solves either one, and
`rig_report()` (issue #698 unit 3) reports the tension/sag readout for
whichever model is active.

Model 1 — tensioned halyard (catenary's "model 1", the default)
-----------------------------------------------------------------
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

Model 2 — anchored heavy rope (catenary's "model 2")
------------------------------------------------------
Each arm is `catenary.solve_anchored`: the SAME fixed-cut-length antenna
wire (same `WireSpec` weight as model 1), followed by a second chain segment
— a rope of its own length and weight, `rope_weight_g_per_m` — whose far end
must land exactly on a fixed **ground anchor**. That anchor reuses
`stake_dist` / `stake_height`, the same rig-point params model 1 calls a
"stake": for this model they name where the rope is staked to the ground,
not a pull direction.

Fixed endpoints plus two inextensible fixed lengths leave **no tension
freedom** — `tension_n` is ignored entirely in this model. The knob a winch
actually turns is the rope's take-up, which raises the apex tension and
lowers the sag as an **output**, not an input; `rig_report()` is where that
readout surfaces (issue #698's "tension readout in N and lbf; sag reported"
acceptance criterion, plus the derived `rope_length_m` — what you'd actually
cut).

The knob is SLACK, not absolute rope length
----------------------------------------------
`rope_slack_mm` — not a rope length — is the UI knob, for a reason a first
pass at this design got wrong (an absolute `rope_length_m` knob failed
review): the rope's cut length is derived inside `rig_solutions()` from the
CURRENT geometry, not stored as its own param —

    reach = hypot(stake_dist - EPS, base - stake_height)   # apex -> anchor
    rope_length_m = (reach - arm_length_m) + rope_slack_mm * 1.0e-3

An absolute `rope_length_m` param cannot span the geometry knobs' own
ranges: `reach - arm_length_m` (the shortest rope that can possibly reach)
moves with `length_factor`, `stake_dist`, and `stake_height`, so any single
fixed length is infeasible across large parts of their sliders — scrub
`length_factor` to its 0.8 UI minimum, or `stake_dist` to its 6.0 UI
maximum, and a `rope_length_m` picked for the stock geometry raises "chain
cannot reach the anchor" for every value in a reasonably sized UI range.
Slack is feasible **by construction** instead: the total chain arc is always
`reach + rope_slack_mm * 1e-3`, strictly more than `reach`, for every
positive slack and every combination of the geometry knobs — the one
remaining way to fail is `reach <= arm_length_m` (the wire ALONE already
reaches past the anchor, so no rope length, slack or otherwise, rescues it);
`rig_solutions()` raises a `ValueError` naming that constraint rather than
clamping it away. It does not occur anywhere in the tested UI cross-product
(`length_factor` in `{0.8, 1.25}` x `stake_dist` in `{1.0, 6.0}` x
`stake_height` in `{0, 3}`, all eight corners, at stock `base`) — see the
module tests — but a knob combination well outside those ranges (a stake
dragged nearly under the apex, or a very long arm) can still reach it.

This also turns the taut-limit's hypersensitivity from a liability into the
slider's whole point: at the stock geometry the shortest feasible rope is
~4.101182 m of arc, and (per the shallow-catenary relation
`H ~ w*L^2/(8*sag)`) apex tension is only a fraction of a newton until slack
shrinks to millimetre scale — not a numerical artifact, the ordinary
behaviour of any lightly loaded near-taut catenary (see `catenary.py`'s own
numerics discussion). `rope_slack_mm`'s range (0.05-200.0 mm) puts that
whole taut-to-slack transition inside one slider: its low end is a
hand-tensioned halyard's tens-of-newtons regime, its high end a visibly
saggy rope carrying almost nothing. The stock default, 0.5 mm of slack,
lands the stock apex tension at ~5.18 N (see the module tests for the exact
number) — inside a real halyard's range without sitting at either the
reach floor or the slider's own edge.

Neither `tension_n` nor `rope_slack_mm` / `rope_weight_g_per_m` is hidden
from the UI even though only one set is "live" per `rig_model`: the
`ui_params` `hidden` hint (see `dipoles.invvee`'s `angle_deg` or
`wire.doublet_ladder_tuner`) is an unconditional, per-param override applied
once at schema-derivation time — it cannot key off another param's value, so
there is no way to hide `tension_n` only when `rig_model == "anchored_rope"`.
Both knobs stay visible; this docstring (and each param's own comment below)
says which one is live in which model.

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
`samples_per_segment = chords_per_arm + 1` to the active model's solve, so
the solver's own uniform-in-arc-length sampling IS the chord split.

`build_wires()` emits ONLY the wire segment's chords as antenna geometry —
`ChainSolution.segments[0].points` is always the wire, in both models. Under
`rig_model="anchored_rope"` the rope is a second chain segment, but it is
rigging, not a conductor: its shape is `rig_report()` diagnostics only and
never reaches `build_wires()`, so the wire count emitted is identical
between the two models.

See also
--------
`antennaknobs.catenary` for the chain solver and its numerics/sign
conventions; `dipoles.invvee` for the base design and param conventions;
`specialty.faceted_helix` for the chord-polyline-as-geometry precedent.
Issue #698.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.catenary import (
    ChainSegment,
    ChainSolution,
    solve_anchored,
    solve_tensioned,
    weight_n_per_m,
)
from antennaknobs.network import WIRES, Wire

# lbf per newton (exact: 1 lbf = 0.45359237 kg * 9.80665 m/s^2).
_N_PER_LBF = 4.4482216152605

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
            # Which rig closure solves each arm (issue #698 unit 3):
            # "halyard" (model 1, tensioned massless rope, tension_n live) or
            # "anchored_rope" (model 2, heavy rope to a ground anchor,
            # rope_slack_mm/rope_weight_g_per_m live). See the module
            # docstring for why both knob sets stay visible in both models.
            "rig_model": "halyard",
            # Rope tension holding each arm's far end. LIVE under
            # rig_model="halyard" only; ignored entirely under
            # "anchored_rope", where tension is a rig_report() readout, not
            # an input. The default is deliberately LIGHT: this wire is only
            # ~5 g/m, so a real hand-tensioned halyard (tens of newtons)
            # pulls it straight to within a millimetre and the catenary —
            # the design's whole point — becomes invisible. 0.3 N sags the
            # stock arm ~7.5 cm (visibly bowed at stock zoom) and happens to
            # sit near resonance at the stock length_factor; the slider's
            # top end is the taut-halyard regime that straightens it.
            "tension_n": 0.3,
            # Stake / ground-anchor position in the arm's vertical plane,
            # horizontal distance from the mast and height above ground.
            # Shared by both models (see the module docstring): model 1
            # calls it the stake the halyard runs to; model 2 calls it the
            # ground anchor the rope's far end must land on. Defaults chosen
            # so hypot(stake_dist, base - stake_height) clears the longest
            # arm the length_factor UI range can produce (see the module
            # docstring and the feasibility test).
            "stake_dist": 2.94,
            "stake_height": 1.0,
            # Rope take-up (issue #698 model 2), in MILLIMETRES of slack
            # above the shortest rope that can reach the anchor at all — the
            # actual winch knob, and feasible by construction across the
            # geometry knobs' full ranges (see the module docstring for why
            # an absolute rope_length_m param cannot be). LIVE under
            # rig_model="anchored_rope" only; unused under "halyard". 0.5 mm
            # lands the stock apex tension at ~5.18 N, inside a real
            # halyard's range (see the module docstring's derivation and the
            # module tests for the exact number).
            "rope_slack_mm": 0.5,
            # Rope weight per metre (issue #698 model 2): typical 3 mm
            # dacron. LIVE under rig_model="anchored_rope" only.
            "rope_weight_g_per_m": 5.5,
            # Chord count per arm: geometric fidelity, orthogonal to the
            # electrical mesh density (nominal_nsegs / auto_mesh).
            "chords_per_arm": 14,
            # Real wire is mandatory (a weightless wire has no catenary);
            # 18 AWG PVC is a common real-world halyard-fed hookup wire.
            "wire_type": "18-awg-pvc",
            "ui_params": MappingProxyType(
                {
                    "length_factor": {"min": 0.8, "max": 1.25},
                    "rig_model": {
                        "enum_options": ("halyard", "anchored_rope"),
                    },
                    # 0.1 N (barely restrained, ~11 cm of sag on the stock
                    # arm) up to 40 N (~9 lbf, a hand-tensioned dacron
                    # halyard — visibly straight). The old 2–400 N range put
                    # the ENTIRE visible-droop regime below the slider's
                    # floor: at ~5 g/m of wire, sag is already under 2 cm at
                    # 2 N and sub-millimetre at 400 N.
                    "tension_n": {"min": 0.1, "max": 40.0},
                    "stake_dist": {"min": 1.0, "max": 6.0},
                    "stake_height": {"min": 0.0, "max": 3.0},
                    # 0.05 mm (near the taut/high-tension extreme a real
                    # cleated halyard shows) to 200 mm (visibly saggy,
                    # carrying almost nothing) — feasible for every value at
                    # every combination of the geometry knobs above (see the
                    # module docstring's feasibility derivation).
                    "rope_slack_mm": {"min": 0.05, "max": 200.0},
                    "rope_weight_g_per_m": {"min": 1.0, "max": 50.0},
                    "chords_per_arm": {"min": 6, "max": 32, "step": 1},
                    "wire_type": {"enum_options": tuple(sorted(WIRES))},
                }
            ),
        }
    )

    def rig_solutions(self) -> ChainSolution:
        """Solve one arm's catenary (both arms are mirror images in y, so
        one solve in the shared vertical plane covers both) under whichever
        `rig_model` is selected. Single source of truth for both models —
        `build_wires()` and `rig_report()` both call this same method, so the
        rigged shape and any diagnostics a caller reads off it (sag,
        tension, arc length) can never drift apart, and the two models can
        never disagree about the wire segment.
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
        apex = (_EPS, self.base)
        samples_per_segment = int(self.chords_per_arm) + 1

        if self.rig_model == "anchored_rope":
            anchor = (self.stake_dist, self.stake_height)
            reach = math.hypot(anchor[0] - apex[0], anchor[1] - apex[1])
            if reach <= arm_length_m:
                raise ValueError(
                    f"{type(self).__name__}: the wire alone (arc length "
                    f"{arm_length_m:.6g} m) already reaches past the anchor "
                    f"(straight-line distance {reach:.6g} m) -- no rope "
                    "length, slack or otherwise, can rescue this; move the "
                    "anchor farther out (larger stake_dist / lower "
                    "stake_height) or shorten the arm (smaller "
                    "length_factor)."
                )
            # SLACK is the knob, not the rope's cut length (issue #698 unit
            # 3 review fix): the cut length is derived from the CURRENT
            # geometry every solve, never stored as its own param, so it is
            # feasible by construction for every combination of the
            # geometry knobs above -- see the module docstring's "knob is
            # slack" section.
            rope_length_m = reach - arm_length_m + self.rope_slack_mm * 1.0e-3
            rope_weight = weight_n_per_m(self.rope_weight_g_per_m)
            segments = (
                ChainSegment(
                    length_m=arm_length_m,
                    weight_n_per_m=wire_weight,
                    name="invvee_catenary_arm",
                ),
                ChainSegment(
                    length_m=rope_length_m,
                    weight_n_per_m=rope_weight,
                    name="rope",
                ),
            )
            return solve_anchored(
                apex=apex,
                segments=segments,
                anchor=anchor,
                samples_per_segment=samples_per_segment,
            )

        if self.rig_model != "halyard":
            raise ValueError(
                f"{type(self).__name__}: unknown rig_model {self.rig_model!r}; "
                "expected 'halyard' or 'anchored_rope'"
            )

        return solve_tensioned(
            apex=apex,
            wire_length_m=arm_length_m,
            wire_weight_n_per_m=wire_weight,
            stake=(self.stake_dist, self.stake_height),
            rope_tension_n=self.tension_n,
            samples_per_segment=samples_per_segment,
            name="invvee_catenary_arm",
        )

    def rig_report(self) -> dict:
        """Tension/sag readout for whichever `rig_model` is active (issue
        #698's "tension readout in N and lbf; sag reported" acceptance
        criterion) — the same shape for both models so a caller (the web
        adapter's solve response, issue #318's `wire_length_m` precedent)
        never has to branch on which model produced it.

        `wire_end_height_m` is the z coordinate of the wire segment's own
        far end — the wire/rope junction under "anchored_rope", or simply
        the wire's end (there is nothing downstream of it) under "halyard".
        `rope_sag_m` / `rope_length_m` are `None` under "halyard" (there is
        no rope segment there — model 1's rope is massless and its length is
        never solved for, only its direction). Under "anchored_rope",
        `rope_length_m` is the CUT length `rig_solutions()` derived from
        `rope_slack_mm` and the current geometry — what you would actually
        cut and tie off, read back off the already-solved chain rather than
        recomputed (so it can never drift from what was actually solved).
        """
        solution = self.rig_solutions()
        wire_seg = solution.segments[0]
        rope_seg = solution.segments[1] if len(solution.segments) > 1 else None
        apex_tension_n = solution.apex_tension
        end_tension_n = solution.end_tension
        return {
            "rig_model": self.rig_model,
            "apex_tension_n": apex_tension_n,
            "apex_tension_lbf": apex_tension_n / _N_PER_LBF,
            "end_tension_n": end_tension_n,
            "end_tension_lbf": end_tension_n / _N_PER_LBF,
            "horizontal_tension_n": solution.horizontal_tension_n,
            "wire_sag_m": wire_seg.max_sag_m,
            "rope_sag_m": rope_seg.max_sag_m if rope_seg is not None else None,
            "rope_length_m": rope_seg.arc_length_m if rope_seg is not None else None,
            "wire_end_height_m": float(wire_seg.points[-1][1]),
        }

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
