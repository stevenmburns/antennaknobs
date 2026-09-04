// GENERATED FROM THE LIVE PAYLOAD — do not hand-edit.
//
// THIS FILE EXISTS BECAUSE A SHARED BASE DRIFTED. The roster fixture built
// each entry's axes by spreading one `BSPLINE_AXES` constant, so fixing the
// b-spline family's `feed_model` silently gave `sinusoidal` a choice it does
// not have — and every gate passed, because they compared kwarg tuples and
// constraints, never axes. Generating them removes the inheritance rather
// than detecting it afterwards, which is the better of the two.
//
// Regenerate with:
//   .venv/bin/python -c "import antennaknobs.web.server, json; \
//     from antennaknobs.web.adapter import backend_roster; \
//     print(json.dumps({r['name']: r['axes'] for r in \
//       backend_roster(have_pynec=True, have_nec5=True)}, indent=2))"
//
// Pinned Python-side by tests/test_frontend_option_spec_fixture.py.

export const SERVED_AXES: Record<string, Record<string, string[]> | null> =
{
  "sinusoidal": {
    "basis": [
      "sinusoidal-3term"
    ],
    "testing": [
      "point-matching"
    ],
    "charge_support": [
      "basis-implied"
    ],
    "kernel": [
      "extended",
      "reduced"
    ],
    "quadrature": [
      "converged"
    ],
    "solve_strategy": [
      "dense"
    ],
    "feed_model": [
      "segment-gap"
    ],
    "ground_model": [
      "free",
      "pec",
      "refl-coef",
      "sommerfeld"
    ],
    "wire_position": [
      "above",
      "contact"
    ]
  },
  "sinusoidal-galerkin": {
    "basis": [
      "sinusoidal-3term"
    ],
    "testing": [
      "galerkin"
    ],
    "charge_support": [
      "basis-implied"
    ],
    "kernel": [
      "extended",
      "reduced"
    ],
    "quadrature": [
      "converged"
    ],
    "solve_strategy": [
      "dense"
    ],
    "feed_model": [
      "point-gap",
      "segment-gap"
    ],
    "ground_model": [
      "free",
      "pec",
      "refl-coef",
      "sommerfeld"
    ],
    "wire_position": [
      "above",
      "contact"
    ]
  },
  "bspline": {
    "basis": [
      "bspline-1",
      "bspline-2"
    ],
    "testing": [
      "galerkin"
    ],
    "charge_support": [
      "spline"
    ],
    "kernel": [
      "extended",
      "reduced"
    ],
    "quadrature": [
      "converged"
    ],
    "solve_strategy": [
      "dense"
    ],
    "feed_model": [
      "point-gap",
      "segment-gap"
    ],
    "ground_model": [
      "free",
      "pec",
      "refl-coef",
      "sommerfeld"
    ],
    "wire_position": [
      "above",
      "buried",
      "contact"
    ]
  },
  "hmatrix": {
    "basis": [
      "bspline-1",
      "bspline-2"
    ],
    "testing": [
      "galerkin"
    ],
    "charge_support": [
      "spline"
    ],
    "kernel": [
      "extended",
      "reduced"
    ],
    "quadrature": [
      "converged"
    ],
    "solve_strategy": [
      "aca"
    ],
    "feed_model": [
      "point-gap",
      "segment-gap"
    ],
    "ground_model": [
      "free",
      "pec",
      "refl-coef",
      "sommerfeld"
    ],
    "wire_position": [
      "above",
      "contact"
    ]
  },
  "arrayblock": {
    "basis": [
      "bspline-1",
      "bspline-2"
    ],
    "testing": [
      "galerkin"
    ],
    "charge_support": [
      "spline"
    ],
    "kernel": [
      "extended",
      "reduced"
    ],
    "quadrature": [
      "converged"
    ],
    "solve_strategy": [
      "element-block"
    ],
    "feed_model": [
      "point-gap",
      "segment-gap"
    ],
    "ground_model": [
      "free",
      "pec",
      "refl-coef",
      "sommerfeld"
    ],
    "wire_position": [
      "above",
      "contact"
    ]
  },
  "razor-2p": {
    "basis": [
      "tent"
    ],
    "testing": [
      "path"
    ],
    "charge_support": [
      "basis-implied"
    ],
    "kernel": [
      "extended",
      "reduced"
    ],
    "quadrature": [
      "converged",
      "nec5"
    ],
    "solve_strategy": [
      "dense"
    ],
    "feed_model": [
      "node-port"
    ],
    "ground_model": [
      "free",
      "pec",
      "refl-coef",
      "sommerfeld"
    ],
    "wire_position": [
      "above",
      "contact"
    ]
  },
  "pynec": null,
  "nec5": null
};
