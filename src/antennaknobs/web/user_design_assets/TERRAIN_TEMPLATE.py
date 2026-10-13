"""A complete, working example terrain. Copy it and make it your own.

A terrain is the shape of the ground around your antenna: a bluff over a
lake, a rooftop edge, a slope behind the shack. The app has three built in
(levee, cliff, hillside). A file like this one adds another.

HOW TO USE THIS FILE
--------------------
1. Copy it to a new file in this same folder, e.g. ``lake_bluff.py``. The
   file name (lowercase, words joined by underscores) is the terrain's name
   in the app.
2. Change the fields (the sliders) and the ``build`` function (the shape).
3. Reload the web page, allow the file to run when asked, then choose
   ground type "terrain". Your terrain is in the list with the built-in
   ones, for every antenna. If you made a mistake, the page shows the error
   so you can fix it.

THE RULES
---------
- One file = one terrain. The file name is the terrain's name. It cannot be
  ``levee``, ``cliff`` or ``hillside``: those are the built-in ones.
- Bind it to the name ``TERRAIN``, exactly. Leave ``name`` and ``label`` out.
- Do not define a ``Builder`` in the same file. An antenna goes in its own
  file.
- Only import from ``antennaknobs`` and the Python standard library.

HOW A TERRAIN IS DESCRIBED
--------------------------
Stand at the mast and look out along one compass bearing. The ground is a
chain of straight pieces called facets. Each facet says how far out it ends
(``x1``, metres from the mast), how high the ground is there (``z1``, metres,
negative means below the ground at the mast), and what it is made of
(relative permittivity and conductivity in S/m). The first facet starts at
the mast at height 0. The last facet has ``x1=None``: it runs on forever.

A ``Sector`` applies one such chain to a range of bearings, in degrees
counter-clockwise from +x. The sectors together must cover the full circle,
and they must all start on the same kind of ground at the mast.

What the app does with it: the feed impedance is worked out over flat ground
of the kind at the mast, and the pattern reflects each ray off the facet it
lands on.
"""

from antennaknobs.terrain import (
    Facet,
    Sector,
    Terrain,
    TerrainField,
    TerrainMarker,
    TerrainPreset,
)

# What the ground is made of: (relative permittivity, conductivity in S/m).
SOIL = (13.0, 0.005)
LAKE = (80.0, 0.001)


def build(v):
    """The terrain for one setting of the sliders. ``v`` holds each field's
    value by its key, already kept inside that field's min and max."""
    edge = v["edge_m"]
    drop = v["drop_m"]
    run = drop / 0.5  # the bank falls 1 m for every 2 m out
    half = v["width_deg"] / 2.0
    toward = v["lake_bearing_deg"]

    lake_side = (
        Facet(edge, 0.0, *SOIL),  # flat ground out to the edge
        Facet(edge + run, -drop, *SOIL),  # the bank
        Facet(None, -drop, *LAKE),  # the lake, to the horizon
    )
    land_side = (Facet(None, 0.0, *SOIL),)  # flat ground all the way out

    if half >= 180.0:
        return Terrain((Sector(0.0, 360.0, lake_side),))
    return Terrain(
        (
            Sector(toward - half, toward + half, lake_side),
            Sector(toward + half, toward - half + 360.0, land_side),
        )
    )


TERRAIN = TerrainPreset(
    # Shown when the mouse rests on the terrain's name.
    tooltip=(
        "Flat ground out to the edge of a bluff, a bank falling 1 in 2, then "
        "lake. Away from the lake the ground stays flat."
    ),
    # The line under the sliders. Say what ground and water you assumed.
    media_note="media: lake εr=80 σ=0.001 · soil εr=13 σ=0.005",
    # One slider each: key, label, default, min, max, step, unit.
    fields=(
        TerrainField("edge_m", "edge of the bluff", 15.0, 1.0, 500.0, 1.0, "m"),
        TerrainField("drop_m", "drop to the lake", 6.0, 0.5, 100.0, 0.5, "m"),
        TerrainField("lake_bearing_deg", "lake bearing", 0.0, -360.0, 360.0, 5.0, "°"),
        TerrainField(
            "width_deg", "width of the lake side", 180.0, 10.0, 360.0, 10.0, "°"
        ),
    ),
    build=build,
    # Optional: marks the lake's bearing on the pattern charts.
    marker=TerrainMarker(
        "lake_bearing_deg", "lake", "land", hide_when_ge=("width_deg", 360.0)
    ),
)
