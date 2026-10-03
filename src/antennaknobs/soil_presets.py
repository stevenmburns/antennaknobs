"""The named soil ladder the workbench serves (``/capabilities``'
``soil_presets``, issue #1173) and the fresh-water medium the terrain panel
shares with it.

Pure data, so the command line can word a soil exactly as the catalog names
it (`analysis_run.ground_words`, AK#1867) without importing the web adapter,
which re-exports both names as it always did.
"""

from __future__ import annotations

# Fixed terrain water (issue #534's QTH numbers): ARRL Antenna Book 25th ed.,
# Table 3.1 (#1175), and the fresh-water preset's own row below.
TERRAIN_WATER = (80.0, 0.001)

# The named ladder. Every row is the ARRL Antenna Book's Table 3.1,
# "Conductivities and Dielectric Constants for Common Types of Earth" (25th
# edition, p. 3.3), checked against the book on 2026-09-08 (issue #1175):
#   very poor  -- "Cities, industrial areas", 5 / 0.001 (the book's Very Poor;
#                 the 3 / 0.0001 that shipped with #1173 had the Extremely
#                 poor row's eps_r and a sigma ten times too low);
#   poor       -- "Rocky soil, steep hills, typ mountainous", 12-14 / 0.002
#                 (the book's Poor; 13 is the middle of its eps_r range);
#   average    -- "Pastoral, medium hills and forestation, heavy clay soil,
#                 typ central VA", 13 / 0.005 (the book's Average);
#   good       -- "Pastoral, low hills, rich soil, typ OH and IL", 14 / 0.01.
#                 The book labels no row Good; this is the row between its
#                 Average and Very good that the name is used for elsewhere;
#   very good  -- "Pastoral, low hills, rich soil, typ Dallas TX to Lincoln
#                 NE", 20 / 0.0303 (the book's Very good);
#   fresh water -- 80 / 0.001, and TERRAIN_WATER above follows the same row
#                 so the soil menu and the terrain panel agree about water;
#   salt water -- 81 / 5.0.
# The book also lists Saline (80 / 0.5 or more), marshy flat country
# (12 / 0.0075), medium hills MD/PA/NY (13 / 0.006), sandy dry coastal
# (10 / 0.002) and heavy industrial cities (3 / 0.001, Extremely poor); none
# of those is served as a preset (Steve's call, 2026-09-08). Dial them in by
# hand.
SOIL_PRESETS: tuple[tuple[str, str, float, float, str], ...] = (
    (
        "very-poor",
        "very poor",
        5.0,
        0.001,
        "Cities, industrial areas (ARRL Table 3.1: very poor).",
    ),
    (
        "poor",
        "poor",
        13.0,
        0.002,
        "Rocky soil, steep hills, mountainous (ARRL Table 3.1: poor).",
    ),
    (
        "average",
        "average",
        13.0,
        0.005,
        "Pastoral, medium hills, heavy clay soil — the usual default (ARRL Table 3.1: average).",
    ),
    (
        "good",
        "good",
        14.0,
        0.01,
        "Pastoral, low hills, rich soil, typ. Ohio and Illinois (ARRL Table 3.1).",
    ),
    (
        "very-good",
        "very good",
        20.0,
        0.0303,
        "Pastoral, low hills, rich soil, Dallas to Lincoln (ARRL Table 3.1: very good).",
    ),
    (
        "fresh-water",
        "fresh water",
        *TERRAIN_WATER,
        "Fresh water (ARRL Table 3.1), matching the terrain panel's water medium.",
    ),
    ("salt-water", "salt water", 81.0, 5.0, "Sea water (ARRL Table 3.1)."),
)
