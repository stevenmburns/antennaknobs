"""Parametric rebuild of the ELT whip on a 96-inch rounded ground-plane grid
— the heavier of the two classic NEC performance benchmarks
(``whip_antenna_8ft_groundplane.nec`` from the W8IO NEC benchmarks page,
http://www.w8io.com/nec-benchmarks.htm): 434 deck wires, ~4,400 segments.
It is in the catalog to stress the solvers, not to be a usable antenna —
expect seconds-per-solve knob response.

Where the source deck hand-authors 434 GW cards, this design *generates*
the same geometry from knobs. At the default parameter values the wire
paths and segment boundaries reproduce the deck to well under 0.1 mm
(the only differences are ~1e-8 m, from the deck writing cos(30 deg) as the
truncated literal .216506). The structure:

  * **Whip** — a thin lower section (fed on its bottom segment, exactly where
    the deck's EX card drives it) and a thicker upper section.
  * **Cage/sleeve** — a ring of ``num_cage_wires`` verticals at
    ``cage_radius`` around the lower whip, tied by a polygon ring every
    ``cage_ring_spacing``, bonded to the whip by ``num_spokes`` spokes at
    ``cage_base`` and to the ground mesh by ``num_posts`` grounded posts.
  * **Ground plane** — a wire grid at ``grid_pitch``, trimmed to a rounded
    outline of radius ``plane_radius``, with the central row/column and the
    centre 2x2 cells re-meshed at ``fine_pitch``, and the feed row split
    at the post feet (at ``cage_radius``-length segments, as in the deck).

Every mesh crossing is emitted as a wire *endpoint* junction (unit cell
edges), so the geometry survives the engines' odd-parity re-segmentation —
the same form a NEC deck import's junction-splitting pass would produce
(mid-wire junctions don't survive resegmentation; see the NEC-import docs).

**The outline is data, not a formula.** The deck's "rounded" boundary is
hand-drawn: no circle radius reproduces its column extents (it isn't even
x/y symmetric — the node at (28", 40") is inside, (40", 28") is not). The
profile is therefore kept as a table of the deck's 25 column half-extents,
normalized, and resampled linearly when the knobs change the column count;
rows are derived as its exact transpose, as in the deck. At the default 24
cells it is used verbatim.

Constraints worth knowing:
  * Keep ``num_cage_wires`` a multiple of 4 if you use posts/spokes on all
    four axes: posts bond to the ground mesh only where their feet land on
    the centre mesh lines (the +/-x and +/-y axes). An off-axis post is still
    drawn but its foot floats above the mesh.
  * ``num_posts``/``num_spokes`` pick evenly spaced cage wires starting at
    +x, so 2 posts land on +/-x (the deck) and 4 spokes on +/-x/+/-y (the
    deck's two crossed diameter bars).
  * The deck's LD matching network IS modelled (unlike a raw deck import,
    which records the LD cards in ``deck.ignored``): ``build_network``
    puts ``post_l_nh`` (deck: 90 nH) in series with the first grounded
    post and ``post_c_pf`` (deck: 3 pF) in series with the second — the
    cage's two grounded legs are the matching network. Set a knob to 0 to
    omit that element.
  * The upper whip carries its own per-wire spec (issue #388) with the
    deck's true 0.035" = 0.889 mm radius (``whip_upper_radius``); everything
    else uses ``wire_radius`` (the deck's 0.254 mm). PyNEC honors both, and
    momwire's default (BSpline) and sinusoidal solvers honor both since
    momwire#147 — the whip solves at its true radius. (The H-matrix family
    still collapses to the length-dominant 0.254 mm with a warning until
    its block fills are ported.)
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder, Wire, WireSpec
from antennaknobs.network import Driven, Load, Network, PortOnWire

# Half-extent of each ground-grid column, in cells: column i (x = i * pitch)
# runs to y = +/-extent * pitch. Sampled from the source deck's hand-drawn
# outline; index 0 is the centre column, index 24 the rim.
_GRID_PROFILE = (
    24,
    24,
    24,
    24,
    24,
    24,
    23,
    23,
    23,
    23,
    22,
    22,
    21,
    21,
    20,
    19,
    18,
    17,
    16,
    15,
    13,
    12,
    10,
    8,
    5,
)


def _column_extent(i, n):
    """Half-extent, in cells, of column ``|i|`` on a plane ``n`` cells in
    radius: the deck profile resampled to ``n``. Exact for n == 24."""
    m = len(_GRID_PROFILE) - 1
    x = abs(i) * m / n
    k = min(int(x), m - 1)
    e = _GRID_PROFILE[k] + (x - k) * (_GRID_PROFILE[k + 1] - _GRID_PROFILE[k])
    return max(0, round(e * n / m))


class Builder(AntennaBuilder):
    label = "ELT whip on 8 ft ground grid (NEC benchmark)"

    default_params = MappingProxyType(
        {
            "freq": 406.0,  # MHz — deck FR sweep centre (400-412)
            "height": 1.0,  # metres above the app's ground plane
            # Whip (deck: 7" thin fed section + 15.75" thick top section)
            "whip_lower_len": 0.1778,
            "whip_upper_len": 0.40005,
            "whip_upper_segs": 28,
            # Cage/sleeve around the lower whip (deck: 12 wires at 0.25",
            # rings every 0.5", 2 grounded posts, 4 spokes at z = 0.5")
            "cage_radius": 0.00635,
            "cage_base": 0.0127,
            "cage_ring_spacing": 0.0127,
            "num_cage_wires": 12,
            "num_posts": 2,
            "num_spokes": 4,
            # Matching network (deck: LD cards put 90 nH in series with the
            # +x post and 3 pF in series with the -x post — the cage's two
            # grounded legs ARE the matching network). 0 = element omitted,
            # leaving that post a plain wire.
            "post_l_nh": 90.0,
            "post_c_pf": 3.0,
            # Ground-plane grid (deck: 48" radius, 2" mesh, 1" fine mesh)
            "plane_radius": 1.2192,
            "grid_pitch": 0.0508,
            "fine_pitch": 0.0254,
            "wire_radius": 0.000254,
            # The thick top whip section's own radius (deck: 0.035");
            # rides as a per-wire spec on just that wire (issue #388).
            "whip_upper_radius": 0.000889,
            "ui_params": MappingProxyType(
                {
                    "default_view": "xz",
                    "meas_freq_range": (400.0, 412.0),
                    # 406 MHz sits outside every HF amateur band; without a
                    # containing band the UI's design-switch snap would drag
                    # design_freq down to the first HF band (160 m!). One
                    # custom band covering the deck's FR sweep keeps the
                    # tabs honest: (key, label, freq, min, max).
                    "bands": (("406", "406 MHz", 406.0, 400.0, 412.0),),
                    # integer knobs, not continuous lengths
                    "whip_upper_segs": {"min": 4, "max": 56, "step": 1},
                    "num_cage_wires": {"min": 4, "max": 24, "step": 1},
                    "num_posts": {"min": 0, "max": 4, "step": 1},
                    "num_spokes": {"min": 0, "max": 12, "step": 1},
                    "post_l_nh": {"min": 0.0, "max": 200.0, "step": 1.0},
                    "post_c_pf": {"min": 0.0, "max": 20.0, "step": 0.1},
                }
            ),
        }
    )

    def build_wires(self):
        h = self.height
        pitch = self.grid_pitch
        n = max(2, round(self.plane_radius / pitch))  # plane radius, in cells
        s = max(1, round(pitch / self.fine_pitch))  # fine cells per cell
        r = max(1e-6, self.cage_radius)
        base = self.cage_base
        spacing = self.cage_ring_spacing
        l1 = self.whip_lower_len
        m_cage = max(3, round(self.num_cage_wires))
        n_posts = max(0, round(self.num_posts))
        n_spokes = max(0, round(self.num_spokes))

        wires = []

        def add(p0, p1, nseg, ex=None, name=None):
            wires.append((p0, p1, nseg, ex, name) if name else (p0, p1, nseg, ex))

        # Unit direction of each cage wire. Snap the on-axis components to
        # exact zeros: wires are recognised as connected only where endpoint
        # coordinates match bitwise, and the post feet must land exactly on
        # the split points of the centre mesh lines below.
        dirs = []
        for m in range(m_cage):
            th = 2.0 * math.pi * m / m_cage
            c, si = math.cos(th), math.sin(th)
            dirs.append((0.0 if abs(c) < 1e-15 else c, 0.0 if abs(si) < 1e-15 else si))

        def cage_pt(m, z):
            c, si = dirs[m % m_cage]
            return (r * c, r * si, z + h)

        # --- whip: driven on its bottom segment, as the deck's EX card
        # (via the network's Driven port — see build_network) ---
        add((0.0, 0.0, h), (0.0, 0.0, base + h), 1, name="feed")
        add(
            (0.0, 0.0, base + h),
            (0.0, 0.0, l1 + h),
            max(1, round((l1 - base) / spacing)),
        )
        # The thick top section keeps the deck's own 0.035" radius as a
        # per-wire spec; every other wire falls back to `wire_radius` via
        # build_wire_material (issue #388).
        wires.append(
            Wire(
                (0.0, 0.0, l1 + h),
                (0.0, 0.0, l1 + self.whip_upper_len + h),
                max(1, round(self.whip_upper_segs)),
                spec=WireSpec(radius=self.whip_upper_radius),
            )
        )

        # --- cage: verticals in ring-to-ring pieces, a polygon per ring ---
        n_levels = max(1, int((l1 - base) / spacing + 1e-9) + 1)
        levels = [base + l * spacing for l in range(n_levels)]
        for m in range(m_cage):
            for za, zb in zip(levels, levels[1:]):
                add(cage_pt(m, za), cage_pt(m, zb), 1)
        for z in levels:
            for m in range(m_cage):
                add(cage_pt(m, z), cage_pt(m + 1, z), 1)

        post_idx = sorted(
            {round(k * m_cage / n_posts) % m_cage for k in range(n_posts)}
        )
        spoke_idx = sorted(
            {round(k * m_cage / n_spokes) % m_cage for k in range(n_spokes)}
        )
        # grounded posts: mesh up to the first ring. Named so build_network
        # can insert the deck's LD elements in series (post0 gets the coil,
        # post1 the capacitor — with the deck's 2 posts that is +x and −x).
        for k, m in enumerate(post_idx):
            c, si = dirs[m]
            add((r * c, r * si, h), cage_pt(m, base), 1, name=f"post{k}")
        for m in spoke_idx:  # spokes: whip out to the first ring
            add((0.0, 0.0, base + h), cage_pt(m, base), 1)

        # --- coarse ground grid, as unit cell edges so every crossing is a
        # wire-endpoint junction; the centre row/column and their +/-1
        # neighbours carry the deck's finer segmentation ---
        ecol = [_column_extent(i, n) for i in range(n + 1)]

        def row_extent(j):
            # transpose of the column profile: the row at |j| reaches the
            # outermost column that reaches |j|
            return max((i for i in range(n + 1) if ecol[i] >= j), default=0)

        for i in range(-n, n + 1):
            x = i * pitch
            dense = abs(i) <= 1
            e = ecol[abs(i)]
            for j in range(-e, e):
                if dense and j in (-1, 0):
                    continue  # covered by the fine centre mesh below
                add((x, j * pitch, h), (x, (j + 1) * pitch, h), s if dense else 1)
        for j in range(-n, n + 1):
            y = j * pitch
            dense = abs(j) <= 1
            e = row_extent(abs(j))
            for i in range(-e, e):
                if dense and i in (-1, 0):
                    continue
                add((i * pitch, y, h), ((i + 1) * pitch, y, h), s if dense else 1)

        # --- fine centre mesh: the central +/-1-cell square at fine pitch ---
        def fine(k):
            # k-th fine node; the +/-s rim is written as +/-pitch itself so
            # the fine mesh and the coarse grid share exact coordinates
            return math.copysign(pitch, k) if abs(k) == s else k * pitch / s

        x_feet = sorted({r * dirs[m][0] for m in post_idx if dirs[m][1] == 0.0})
        y_feet = sorted({r * dirs[m][1] for m in post_idx if dirs[m][0] == 0.0})

        def line_pieces(feet):
            """Split points and per-piece segment counts for a centre mesh
            line that hosts post feet: break at each foot, and keep the whole
            line at ~foot-offset-length segments, as the deck's feed row."""
            pts = [fine(k) for k in range(-s, s + 1)]
            pts += [
                ft
                for ft in feet
                if -pitch < ft < pitch and not any(abs(ft - p) < 1e-12 for p in pts)
            ]
            pts.sort()
            seg = min(r, pitch / s)
            return [(a, b, max(1, round((b - a) / seg))) for a, b in zip(pts, pts[1:])]

        for u in range(-s, s + 1):
            x = fine(u)
            if u == 0 and y_feet:
                for a, b, nseg in line_pieces(y_feet):
                    add((x, a, h), (x, b, h), nseg)
            else:
                for v in range(-s, s):
                    add((x, fine(v), h), (x, fine(v + 1), h), 1)
        for v in range(-s, s + 1):
            y = fine(v)
            if v == 0 and x_feet:
                for a, b, nseg in line_pieces(x_feet):
                    add((a, y, h), (b, y, h), nseg)
            else:
                for u in range(-s, s):
                    add((fine(u), y, h), (fine(u + 1), y, h), 1)

        return wires

    def build_network(self):
        """The deck's matching network: LD cards put 90 nH in series with
        the +x grounded post and 3 pF in series with the −x one (ld_card
        type 0 → `Load`, a series element in the named 1-segment post wire).
        A zero knob omits that element, leaving the post a plain wire; the
        feed is the whip's bottom segment, as the deck's EX card."""
        ports = {"feed": PortOnWire("feed")}
        branches = []
        n_posts = max(0, round(self.num_posts))
        elems = [
            ("post0", self.post_l_nh * 1e-9, None),
            ("post1", None, self.post_c_pf * 1e-12),
        ]
        for k, (pname, l, c) in enumerate(elems):
            if k >= n_posts or not (l or c):
                continue
            ports[pname] = PortOnWire(pname)
            branches.append(Load(port=pname, l=l or None, c=c or None))
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )

    def build_wire_material(self):
        return WireSpec(radius=self.wire_radius)
