// dipoles.two_wire_doublet as an opened NEC-5 deck with SY knobs L and M, its
// three catalog analyses and the catalog's knob ranges (AK#2045): what the
// real server answered, so the session tests run the issue's case on its
// own shapes. Written from tests/test_deck_link_analyses_2045.py's DOUBLET,
// _doublet_text() and DOUBLET_RANGES: POST /deck (the two SY knobs of its
// param_schema), POST /analyses (the three "link" entries) and POST /keep's
// `expr` for each entry's spec. Regenerate by running those three requests
// through fastapi's TestClient and pasting the answers here.
import type { SchemaParamSpec } from "../../lib/params";

export const DOUBLET_DECK_TEXT = "CM dipoles.two_wire_doublet as a NEC-5 deck, L and M as SY knobs (AK#2045)\nCM NEC-5\nCE\nSY long_ft=17.066\nSY short_ft=17.066\nGW 1 20 0 -short_ft*0.3048 10 0 0 10 6.452E-04\nGW 2 20 0 0 10 0 long_ft*0.3048 10 6.452E-04\nGE 0 0\nLD 5 0 0 0 5.8E+07 0. 0.\nEX 0 2 1 1 1.0 0.0\nFR 0 1 0 0 14.0 0\nXQ 0\nEN\n";
/** The deck as a link carries it (deflate-raw, base64url). */
export const DOUBLET_Z = "TY1Ni8IwEIbv-RUv7GV1t2GaTaoXD1Kze9AK6kH3VOq2ftDSSFPx75uQFUqGDLzPMzNphvJ6M01lef8w-ePaVXlp7sem6lFYFFjrNFIoq7_6EysUbYnMg90v6tYcLd7nyzdBUo1YmgWZpZo53Jj2nJ_6WTzhlCQ-sRfT9YPoZ48YgkCIXmhM_IvkFLFPybeESyV0RNLrIugU-P-FwcxA1t5jqwUUwojiU_1BExB3xfTBRcLdd487zIl9b_3isF76jB027tNr9gQ";
/** The three analyses as `analyses_text.write` prints them. */
export const DOUBLET_ANALYSES_TEXT = "[\n    an.Analysis(\n        \"resonance map\",\n        (\n            an.Sweep(\"sy_long_ft\", 16.0, 36.0, points=41),\n            an.Sweep(\"sy_short_ft\", 1.0, 34.0, points=34),\n        ),\n        views=(an.Map(),),\n        references=an.Ref(x=(0,)),\n        ground=\"free\",\n        group=\"Resonant splits\",\n    ),\n    an.Analysis(\n        \"low-R branch (dipole to OCF)\",\n        an.Sweep(\"sy_long_ft\", 17.066, 32.5, points=32),\n        views=(an.Rx(), an.Knobs()),\n        ground=\"free\",\n        hold=an.Hold(\"resonance\", adjust=(\"sy_short_ft\",)),\n        group=\"Resonant splits\",\n    ),\n    an.Analysis(\n        \"high-R branch (1-wavelength doublet to EFHW)\",\n        an.Sweep(\"sy_short_ft\", 33.0, 3.5, points=31),\n        views=(an.Rx(), an.Knobs()),\n        ground=\"free\",\n        hold=an.Hold(\"resonance\", adjust=(\"sy_long_ft\",)),\n        group=\"Resonant splits\",\n    ),\n]\n";
/** That text as a link's analyses= carries it. */
export const DOUBLET_ANALYSES = "vZLPa8MgFMfv_SvEk4E0NE2WnTyMsVIYY5Addhij2OXlx3Aqapr2v5_JQutKA9sO86Die9-n38_zZYbcYCK6EYwfTGPIcNAPrMFIwcQboA-mcHgMnFJG7VMHoAg2hw2XotqUFocozqJFiJJhVrIR1tA0DsJpqamltqN2kKaeNEk9qbfdNdAZSlyhB6ZIEHohDSVocK831IVzKMmekkUYeCmVlq0oKC41AP5-rCjOv-xbZBRvrBkTRvllYlx28xxttYNWI1I0SnJAVqLH21XgXTCF7DpaZJlzvoyuTs6XF-3me-e2L3Qv5NaQH7iqJS96Emu3klNv3b2seG-NpWddOC_5NyJ1U9UeknjesR1wEJWtUSHbLQfbA7pbrZ8nCXk_I0mGr-Hzif-Vz7Fbv8HzOvsE";
/** The link's knob ranges as the page sends /deck them. */
export const DOUBLET_RANGES = "sy_long_ft:15:36,sy_short_ft:1:34";
/** The deck's SY knobs, with the link's ranges as their min/max. */
export const DOUBLET_SCHEMA: SchemaParamSpec[] = [
  {
    "name": "sy_long_ft",
    "label": "long_ft",
    "default": 17.066,
    "kind": "float",
    "min": 15.0,
    "max": 36.0,
    "step": 0.02,
    "precision": 3,
    "unit": null,
    "visible_when": null,
    "enum_options": null,
    "range_from_enum_option": null,
    "on_change_set": null,
    "linked_to_design_freq": false,
    "link_meas_freq_to_param": null,
    "layout": null,
    "description": null,
    "auto_range": false,
    "role": null,
    "sweep": null
  },
  {
    "name": "sy_short_ft",
    "label": "short_ft",
    "default": 17.066,
    "kind": "float",
    "min": 1.0,
    "max": 34.0,
    "step": 0.05,
    "precision": 3,
    "unit": null,
    "visible_when": null,
    "enum_options": null,
    "range_from_enum_option": null,
    "on_change_set": null,
    "linked_to_design_freq": false,
    "link_meas_freq_to_param": null,
    "layout": null,
    "description": null,
    "auto_range": false,
    "role": null,
    "sweep": null
  }
] as SchemaParamSpec[];
/** /analyses' entries for the link's analyses. */
export const DOUBLET_ENTRIES = [
  {
    "name": "resonance map",
    "group": "Resonant splits",
    "summary": "sy_long_ft 16..36, 41 points x sy_short_ft 1..34, 34 points; 1 map; views Map",
    "code": "an.Analysis(\n    \"resonance map\",\n    (\n        an.Sweep(\"sy_long_ft\", 16.0, 36.0, points=41),\n        an.Sweep(\"sy_short_ft\", 1.0, 34.0, points=34),\n    ),\n    views=(an.Map(),),\n    references=an.Ref(x=(0,)),\n    ground=\"free\",\n    group=\"Resonant splits\",\n)",
    "spec": {
      "an": "Analysis",
      "name": "resonance map",
      "sweep": [
        {
          "an": "Sweep",
          "knob": "sy_long_ft",
          "lo": 16.0,
          "hi": 36.0,
          "points": 41,
          "values": null,
          "spacing": null
        },
        {
          "an": "Sweep",
          "knob": "sy_short_ft",
          "lo": 1.0,
          "hi": 34.0,
          "points": 34,
          "values": null,
          "spacing": null
        }
      ],
      "cross": [],
      "views": [
        {
          "an": "Map"
        }
      ],
      "references": {
        "an": "Ref",
        "r": [],
        "x": [
          0
        ],
        "swr": null
      },
      "ground": "free",
      "engine": null,
      "hold": null,
      "group": "Resonant splits"
    },
    "problems": [],
    "workbench": {
      "runs": true,
      "kind": "map",
      "x": {
        "param": "sy_long_ft",
        "values": [
          16.0,
          16.5,
          17.0,
          17.5,
          18.0,
          18.5,
          19.0,
          19.5,
          20.0,
          20.5,
          21.0,
          21.5,
          22.0,
          22.5,
          23.0,
          23.5,
          24.0,
          24.5,
          25.0,
          25.5,
          26.0,
          26.5,
          27.0,
          27.5,
          28.0,
          28.5,
          29.0,
          29.5,
          30.0,
          30.5,
          31.0,
          31.5,
          32.0,
          32.5,
          33.0,
          33.5,
          34.0,
          34.5,
          35.0,
          35.5,
          36.0
        ],
        "log": false,
        "lo": 16.0,
        "hi": 36.0,
        "points": 41,
        "spacing": "lin"
      },
      "y": {
        "param": "sy_short_ft",
        "values": [
          1.0,
          2.0,
          3.0,
          4.0,
          5.0,
          6.0,
          7.0,
          8.0,
          9.0,
          10.0,
          11.0,
          12.0,
          13.0,
          14.0,
          15.0,
          16.0,
          17.0,
          18.0,
          19.0,
          20.0,
          21.0,
          22.0,
          23.0,
          24.0,
          25.0,
          26.0,
          27.0,
          28.0,
          29.0,
          30.0,
          31.0,
          32.0,
          33.0,
          34.0
        ],
        "log": false,
        "lo": 1.0,
        "hi": 34.0,
        "points": 34,
        "spacing": "lin"
      },
      "refs": {
        "r": [],
        "x": [
          0.0
        ],
        "swr": null
      },
      "views": [
        "Map"
      ],
      "limit": null,
      "engines": null,
      "grounds": [
        "free"
      ],
      "note": null
    },
    "study": null,
    "origin": "link"
  },
  {
    "name": "low-R branch (dipole to OCF)",
    "group": "Resonant splits",
    "summary": "sy_long_ft 17.066..32.5, 32 points; 1 curve; hold resonance on sy_short_ft; views Rx, Knobs",
    "code": "an.Analysis(\n    \"low-R branch (dipole to OCF)\",\n    an.Sweep(\"sy_long_ft\", 17.066, 32.5, points=32),\n    views=(an.Rx(), an.Knobs()),\n    ground=\"free\",\n    hold=an.Hold(\"resonance\", adjust=(\"sy_short_ft\",)),\n    group=\"Resonant splits\",\n)",
    "spec": {
      "an": "Analysis",
      "name": "low-R branch (dipole to OCF)",
      "sweep": {
        "an": "Sweep",
        "knob": "sy_long_ft",
        "lo": 17.066,
        "hi": 32.5,
        "points": 32,
        "values": null,
        "spacing": null
      },
      "cross": [],
      "views": [
        {
          "an": "Rx"
        },
        {
          "an": "Knobs"
        }
      ],
      "references": {
        "an": "Ref",
        "r": [],
        "x": [],
        "swr": null
      },
      "ground": "free",
      "engine": null,
      "hold": {
        "an": "Hold",
        "objective": "resonance",
        "adjust": [
          "sy_short_ft"
        ],
        "z0": null,
        "warm_start": true,
        "bands": [],
        "mean_weight": 0.5
      },
      "group": "Resonant splits"
    },
    "problems": [],
    "workbench": {
      "runs": true,
      "kind": "knob",
      "param": "sy_long_ft",
      "values": [
        17.066,
        17.563870967741934,
        18.06174193548387,
        18.559612903225805,
        19.05748387096774,
        19.555354838709675,
        20.05322580645161,
        20.551096774193546,
        21.048967741935485,
        21.546838709677417,
        22.044709677419355,
        22.54258064516129,
        23.040451612903226,
        23.53832258064516,
        24.036193548387097,
        24.534064516129032,
        25.031935483870967,
        25.529806451612902,
        26.027677419354838,
        26.525548387096773,
        27.02341935483871,
        27.521290322580647,
        28.01916129032258,
        28.517032258064518,
        29.01490322580645,
        29.51277419354839,
        30.01064516129032,
        30.50851612903226,
        31.006387096774194,
        31.50425806451613,
        32.00212903225807,
        32.5
      ],
      "log": false,
      "views": [
        "Rx",
        "Knobs"
      ],
      "metric": null,
      "hold": {
        "objective": "resonance",
        "knobs": [
          "sy_short_ft"
        ],
        "bounds": {
          "sy_short_ft": [
            1.0,
            34.0
          ]
        },
        "z0": null,
        "warm_start": true,
        "spec": {
          "an": "Hold",
          "objective": "resonance",
          "adjust": [
            "sy_short_ft"
          ],
          "z0": null,
          "warm_start": true,
          "bands": [],
          "mean_weight": 0.5
        }
      },
      "engines": null,
      "grounds": [
        "free"
      ],
      "axes": [],
      "planes": null,
      "designs": null,
      "states": null,
      "cells": null,
      "step": null,
      "note": null
    },
    "study": null,
    "origin": "link"
  },
  {
    "name": "high-R branch (1-wavelength doublet to EFHW)",
    "group": "Resonant splits",
    "summary": "sy_short_ft 33..3.5, 31 points; 1 curve; hold resonance on sy_long_ft; views Rx, Knobs",
    "code": "an.Analysis(\n    \"high-R branch (1-wavelength doublet to EFHW)\",\n    an.Sweep(\"sy_short_ft\", 33.0, 3.5, points=31),\n    views=(an.Rx(), an.Knobs()),\n    ground=\"free\",\n    hold=an.Hold(\"resonance\", adjust=(\"sy_long_ft\",)),\n    group=\"Resonant splits\",\n)",
    "spec": {
      "an": "Analysis",
      "name": "high-R branch (1-wavelength doublet to EFHW)",
      "sweep": {
        "an": "Sweep",
        "knob": "sy_short_ft",
        "lo": 33.0,
        "hi": 3.5,
        "points": 31,
        "values": null,
        "spacing": null
      },
      "cross": [],
      "views": [
        {
          "an": "Rx"
        },
        {
          "an": "Knobs"
        }
      ],
      "references": {
        "an": "Ref",
        "r": [],
        "x": [],
        "swr": null
      },
      "ground": "free",
      "engine": null,
      "hold": {
        "an": "Hold",
        "objective": "resonance",
        "adjust": [
          "sy_long_ft"
        ],
        "z0": null,
        "warm_start": true,
        "bands": [],
        "mean_weight": 0.5
      },
      "group": "Resonant splits"
    },
    "problems": [],
    "workbench": {
      "runs": true,
      "kind": "knob",
      "param": "sy_short_ft",
      "values": [
        33.0,
        32.016666666666666,
        31.033333333333335,
        30.05,
        29.066666666666666,
        28.083333333333336,
        27.1,
        26.116666666666667,
        25.133333333333333,
        24.15,
        23.166666666666668,
        22.183333333333334,
        21.200000000000003,
        20.21666666666667,
        19.233333333333334,
        18.25,
        17.266666666666666,
        16.283333333333335,
        15.3,
        14.316666666666666,
        13.333333333333336,
        12.350000000000001,
        11.366666666666667,
        10.383333333333333,
        9.400000000000002,
        8.416666666666668,
        7.433333333333334,
        6.450000000000003,
        5.466666666666669,
        4.483333333333334,
        3.5
      ],
      "log": false,
      "views": [
        "Rx",
        "Knobs"
      ],
      "metric": null,
      "hold": {
        "objective": "resonance",
        "knobs": [
          "sy_long_ft"
        ],
        "bounds": {
          "sy_long_ft": [
            15.0,
            36.0
          ]
        },
        "z0": null,
        "warm_start": true,
        "spec": {
          "an": "Hold",
          "objective": "resonance",
          "adjust": [
            "sy_long_ft"
          ],
          "z0": null,
          "warm_start": true,
          "bands": [],
          "mean_weight": 0.5
        }
      },
      "engines": null,
      "grounds": [
        "free"
      ],
      "axes": [],
      "planes": null,
      "designs": null,
      "states": null,
      "cells": null,
      "step": null,
      "note": null
    },
    "study": null,
    "origin": "link"
  }
];
/** /keep's `expr` for each entry's spec, by name. */
export const DOUBLET_EXPRS: Record<string, string> = {
  "resonance map": "an.Analysis(\n    \"resonance map\",\n    (\n        an.Sweep(\"sy_long_ft\", 16.0, 36.0, points=41),\n        an.Sweep(\"sy_short_ft\", 1.0, 34.0, points=34),\n    ),\n    views=(an.Map(),),\n    references=an.Ref(x=(0,)),\n    ground=\"free\",\n    group=\"Resonant splits\",\n)",
  "low-R branch (dipole to OCF)": "an.Analysis(\n    \"low-R branch (dipole to OCF)\",\n    an.Sweep(\"sy_long_ft\", 17.066, 32.5, points=32),\n    views=(an.Rx(), an.Knobs()),\n    ground=\"free\",\n    hold=an.Hold(\"resonance\", adjust=(\"sy_short_ft\",)),\n    group=\"Resonant splits\",\n)",
  "high-R branch (1-wavelength doublet to EFHW)": "an.Analysis(\n    \"high-R branch (1-wavelength doublet to EFHW)\",\n    an.Sweep(\"sy_short_ft\", 33.0, 3.5, points=31),\n    views=(an.Rx(), an.Knobs()),\n    ground=\"free\",\n    hold=an.Hold(\"resonance\", adjust=(\"sy_long_ft\",)),\n    group=\"Resonant splits\",\n)"
};
