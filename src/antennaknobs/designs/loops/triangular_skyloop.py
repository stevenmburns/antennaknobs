r"""Triangular horizontal full-wave loop ("skyloop"), fed at a corner.

A single closed loop whose perimeter is about one wavelength, lying FLAT in a
plane of constant height (z = base) like the square horizontal_loop skywire --
but bent into an EQUILATERAL TRIANGLE and fed at one CORNER rather than at the
midpoint of a side. Strung over real ground it is a strong NVIS radiator (it
fires nearly straight up, filling the close-in skip zone); in free space it is
horizontally polarised with its main lobe broadside to the loop plane, along
+/- z. A full-wave loop presents a moderate, near-resistive feed; a corner feed
on a triangle runs a touch higher than the ~100 ohm of a side-fed loop.

The wire mesh is SYMMETRIC on all three sides AND across each vertex: every
corner is chamfered by the same short one-segment wire, centred ON the vertex
and perpendicular to its bisector, so the loop is really an equiangular
hexagon alternating long runs with short chamfers (a triangle with its
corners clipped). Only the apex chamfer is driven; the other two are plain
structural wire, so the three corners are meshed identically and the feed
straddles its vertex symmetrically (compare horizontal_loop_drone's diagonal
feed across a corner).

Default design frequency is 3.8 MHz -- the centre of the 75 m voice band (the
3.6-4.0 MHz phone segment of 80 m), where a full-size triangular skyloop is a
classic high-and-flat NVIS/rag-chew antenna.

Methodology purpose: a LARGE single closed loop with the feed placed ACROSS A
VERTEX (the driven chamfer bridges the corner, half on each side of it),
exercising the engines' closed-loop assembly with a corner-symmetric feed
rather than the mid-side gap of horizontal_loop. Authored with the Drone (3D
turtle): the hexagon is one continuous pen-down flight -- feed chamfer, then
alternating -60 deg yaws between runs and chamfers, and a close.

Geometry, in the framework's (x, y, z) convention:
  - z : height; the whole triangle sits in the plane z = base (HORIZONTAL)
  - x, y : the equilateral triangle, apex at the ORIGIN, hanging toward -y
  - feed F straddling the apex corner at (0, 0) (a short chamfer centred on
    it, running along x); main lobe along +/- z (toward zenith)

              V_top                   feed F straddles this corner
               /\
              /  \
             /    \                   (triangle lies flat at z = base;
            /      \                   viewed from above)
           /        \
     V_left ---------- V_right
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder, Drone


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # Centre of the 75 m voice band (3.6-4.0 MHz phone segment).
            "design_freq": 3.8,
            "freq": 3.8,
            # Height of the (flat) loop plane above ground. In free space this
            # only shifts the structure; over real ground it sets the NVIS
            # takeoff. A full-size 75 m loop typically hangs high in tall trees.
            "base": 15.0,
            # Perimeter in wavelengths, and the single scale/tuning knob. Each
            # side is length_factor/3 of a wavelength, so length_factor = 1 is a
            # nominal one-wavelength loop; a full-wave loop resonates a few
            # percent long, so the free-space feed is near resonant (X ~ 0,
            # ~113 ohm) at length_factor = 1.05.
            "length_factor": 1.05,
            "ui_params": MappingProxyType(
                {
                    # Full-wave loop, corner-fed -> moderate near-resistive feed.
                    # Free-space solve at the default 1.05 is ~113 - j5 ohm, so
                    # 112 shows a near-1:1 SWR there.
                    "target_z0": 112.0,
                    # The triangle lies flat in z = base; its x and y spans are
                    # the two largest, so the xy view shows the loop face-on.
                    "default_view": "xy",
                    "length_factor": {
                        "min": 0.95,
                        "max": 1.15,
                    },
                }
            ),
        }
    )

    # Band-locked variant: identical geometry to default, but the frontend
    # clamps the freq sweep to the amateur band containing the anchor (80 m,
    # which holds the 3.8 MHz default) instead of the wide ±multiplier window.
    # Only ui_params is stated — it deep-merges over default_params.ui_params
    # (inheriting target_z0 / default_view / length_factor) and flips just
    # sweep_policy.band_locked; every regular param overlays from default.
    band_locked_params = MappingProxyType(
        {"ui_params": MappingProxyType({"sweep_policy": {"band_locked": True}})}
    )

    def build_wires(self):
        eps = 0.05

        wavelength = 299.792458 / self.design_freq

        # Equilateral triangle, so each side is a third of the perimeter; the
        # perimeter is length_factor wavelengths (length_factor = 1 -> a nominal
        # one-wavelength loop).
        side = (wavelength / 3.0) * self.length_factor

        # Every vertex is chamfered by the same short one-segment wire, centred
        # ON the vertex and perpendicular to its bisector; only the apex
        # chamfer carries the source. Runs of side - gap between chamfers keep
        # the total perimeter at exactly length_factor wavelengths.
        gap = 2 * eps
        run = side - gap

        # Fly the hexagon clockwise (viewed from above) as one pen-down stroke,
        # with the feed point at the origin and the triangle hanging toward -y.
        # The drone's default pose faces +x with up = +z -- at the apex that is
        # exactly the chamfer direction (perpendicular to the bisector), so no
        # face() is needed: back up half a gap, lay the driven chamfer
        # straddling the vertex, then alternate -60 deg yaws between runs and
        # chamfers, staying in the z = base plane throughout.
        drone = Drone(position=(0.0, 0.0, self.base))
        drone.jump(-gap / 2.0)

        drone.feed(1 + 0j).forward(gap)  # driven chamfer across apex
        drone.pay_out()
        drone.yaw(-60).forward(run)  # -> v_right
        drone.yaw(-60).forward(gap)  # passive chamfer across v_right
        drone.yaw(-60).forward(run)  # -> v_left
        drone.yaw(-60).forward(gap)  # passive chamfer across v_left
        drone.yaw(-60).close()  # final run, home to the apex chamfer

        return drone.wires()
