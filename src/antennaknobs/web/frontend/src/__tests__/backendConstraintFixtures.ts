// GENERATED FROM THE LIVE PAYLOAD — do not hand-edit the strings.
//
// Regenerate with:
//   .venv/bin/python -c "import antennaknobs.web.server, json; \
//     from antennaknobs.web.adapter import backend_roster; \
//     print(json.dumps({r['name']: r['constraints'] for r in \
//       backend_roster(have_pynec=True, have_nec5=True)}, indent=2))"
//
// The `reason` fields are momwire's OWN refusal prose, referenced by
// `_couplings.py` rather than retyped there — so a paraphrase here would be
// the only copy in the chain, and the one place drift could enter. The
// session test matches a fragment of these; if momwire rewords a refusal,
// this file and that assertion move together and deliberately not silently.
import type { BackendConstraint } from "../lib/backends";

export const SERVED_CONSTRAINTS: Record<string, BackendConstraint[] | null> =
{
  "sinusoidal": [
    {
      "axis": "testing",
      "value": "point-matching",
      "forbids_axis": "feed_model",
      "forbids_value": "point-gap",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "feed_model='point' is not supported on SinusoidalSolver: a zero-width gap has no collocation RHS \u2014 the drive is E_app sampled AT a match point and the source is a delta there, so the pairing is undefined (momwire#212). Under point matching NEC's segment gap already is the zero-width gap at the mesh's own resolution. For the zero-width source use SinusoidalGalerkinSolver(feed_model='point'), whose test integral is what makes a delta source admissible",
      "issue": "momwire#212"
    }
  ],
  "sinusoidal-galerkin": [
    {
      "axis": "kernel",
      "value": "extended",
      "forbids_axis": "near_correction",
      "forbids_value": "False",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "extended_kernel=True requires near_correction=True on SinusoidalGalerkinSolver: the extended kernel's delta is resolved on the near-pair path, and M1 mode would leave the self and node-sharing pairs on the far tier's rule (momwire#246)",
      "issue": "momwire#246"
    },
    {
      "axis": "kernel",
      "value": "extended",
      "forbids_axis": "junction_ports",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": "a radius step at the junction",
      "reason": "extended_kernel=True with a radius step at a junction is not implemented on SinusoidalGalerkinSolver: measured DIVERGENT, not merely inaccurate. On momwire#435's two-wire step deck (10:1 radius step at the midspan junction, 10.19 m dipole @ 14.2 MHz) the extrapolated continuum limit is 7.110 - 483.925j against NEC-5's 132.560 - 11.921j, with the residual GROWING every rung refined (23.2 Ohm -> 285.8 Ohm) and a 286 Ohm dX spread down the ladder \u2014 materially worse than the reduced `sg` row's ~20 Ohm walk-away #435 already documents (that is a formulation gap; this is a divergence). The mechanism is under the mixed end-condition constants the extended delta's end bracket takes at a stepped node \u2014 the same node kind momwire#299 gates for the UNIFORM-radius case, not yet derived here for a step. Use `extended_kernel=False` (the reduced `sg` row, correctly documented as NEC-2-identified rather than NEC-5-accurate on any radius step), or `BSplineSolver(extended_kernel=True)` / `SinusoidalSolver(extended_kernel=True)`, both of which are served on a step (taper-readiness study Sec 2-3, maintainer decision D2, stevenmburns/momwire#398)",
      "issue": "momwire#398"
    }
  ],
  "bspline": [
    {
      "axis": "kernel",
      "value": "extended",
      "forbids_axis": "wire_position",
      "forbids_value": "buried",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "extended_kernel=True + a wire below the ground plane is not served: the extended kernel's eligibility is a COAXIAL-AND-EQUAL-RADIUS grouping scored across the whole geometry, and momwire#553 measured neither what that grouping means for a pair spanning two media (the tube expansion's O(a^2) term is written at one wavenumber) nor what the mirror labels mean when the image of a buried source lands in the OTHER medium. Solve the buried deck with extended_kernel=False, which is the default",
      "issue": "momwire#553"
    }
  ],
  "hmatrix": [
    {
      "axis": "solve_strategy",
      "value": "aca",
      "forbids_axis": "wire_position",
      "forbids_value": "buried",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "this deck has a wire below the ground plane, and the fast operator has no per-segment medium. Admissibility is a purely geometric distance test with no notion of which side of the interface a cluster is on; the fused near/far block kernels take a `double k` and would truncate the in-medium k_m = k0*sqrt(eps_tilde) to its real part; and the Sommerfeld composition is carried as ONE global low-rank remainder over ONE grid, where a buried deck needs three blocks over three grids (momwire#553 U5). BSplineSolver serves the deck through its dense fill - this class deliberately does NOT fall back to it, because it exists for decks the dense fill cannot hold, and a silent fallback on a buried array is an out-of-memory rather than a slow answer",
      "issue": "momwire#553"
    }
  ],
  "arrayblock": [
    {
      "axis": "solve_strategy",
      "value": "element-block",
      "forbids_axis": "wire_position",
      "forbids_value": "buried",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "this deck has a wire below the ground plane, and the fast operator has no per-segment medium. Admissibility is a purely geometric distance test with no notion of which side of the interface a cluster is on; the fused near/far block kernels take a `double k` and would truncate the in-medium k_m = k0*sqrt(eps_tilde) to its real part; and the Sommerfeld composition is carried as ONE global low-rank remainder over ONE grid, where a buried deck needs three blocks over three grids (momwire#553 U5). BSplineSolver serves the deck through its dense fill - this class deliberately does NOT fall back to it, because it exists for decks the dense fill cannot hold, and a silent fallback on a buried array is an out-of-memory rather than a slow answer",
      "issue": "momwire#553"
    }
  ],
  "razor-2p": [],
  "pynec": null,
  "nec5": null
};
