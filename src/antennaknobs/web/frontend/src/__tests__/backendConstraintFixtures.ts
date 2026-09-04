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
    },
    {
      "axis": "wire_position",
      "value": "contact",
      "forbids_axis": "ground_model",
      "forbids_value": "refl-coef",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "ground CONTACT under ground_model='refl-coef' is refused (momwire#282 stage 1, 2026-08-18): the reflection-coefficient ground's Phi-term weight is a specular-angle approximation with no validity at zero clearance (momwire#153), and at contact it does not approximate the answer at all. Measured on a base-fed quarter-wave vertical over average soil (eps_r 13, sigma 0.005 S/m) at 14 MHz, N=41: refl-coef gives 27.0+12.6j ohm against this solver's own sommerfeld answer of 51.5+23.2j ohm on the same deck and the NEC-5 binary's printed 52.4+22.7j ohm \u2014 27 ohm out, and on the WRONG SIDE of the 40.7+23.3j ohm PEC answer, so it is not a degraded approximation but a different number. This row was served and silently wrong; docs/design/contact-over-finite-ground.md 3.6 has the measurement. The MODEL is what has no story at the plane, not momwire's implementation of it: NEC-2's own reflection-coefficient ground (nec2c, GN 0) prints 175-779j ohm over average soil and 155-1248j ohm over poor soil on the same contact monopole, against a sane 39.4+22.1j ohm over GN 1 \u2014 a reflection coefficient is a plane-wave object evaluated on a specular ray, and at zero clearance there is no such ray. Use ground_model='sommerfeld', which is contact-capable (momwire#151) and gated there against the binary, or raise the wire clear of the plane \u2014 refl-coef stays served, and stays the default, for wires standing clear in its 0.1-0.5 lambda validity window",
      "issue": "momwire#282"
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
    },
    {
      "axis": "wire_position",
      "value": "contact",
      "forbids_axis": "ground_model",
      "forbids_value": "refl-coef",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "ground CONTACT under ground_model='refl-coef' is refused (momwire#282 stage 1, 2026-08-18): the reflection-coefficient ground's Phi-term weight is a specular-angle approximation with no validity at zero clearance (momwire#153), and at contact it does not approximate the answer at all. Measured on a base-fed quarter-wave vertical over average soil (eps_r 13, sigma 0.005 S/m) at 14 MHz, N=41: refl-coef gives 27.0+12.6j ohm against this solver's own sommerfeld answer of 51.5+23.2j ohm on the same deck and the NEC-5 binary's printed 52.4+22.7j ohm \u2014 27 ohm out, and on the WRONG SIDE of the 40.7+23.3j ohm PEC answer, so it is not a degraded approximation but a different number. This row was served and silently wrong; docs/design/contact-over-finite-ground.md 3.6 has the measurement. The MODEL is what has no story at the plane, not momwire's implementation of it: NEC-2's own reflection-coefficient ground (nec2c, GN 0) prints 175-779j ohm over average soil and 155-1248j ohm over poor soil on the same contact monopole, against a sane 39.4+22.1j ohm over GN 1 \u2014 a reflection coefficient is a plane-wave object evaluated on a specular ray, and at zero clearance there is no such ray. Use ground_model='sommerfeld', which is contact-capable (momwire#151) and gated there against the binary, or raise the wire clear of the plane \u2014 refl-coef stays served, and stays the default, for wires standing clear in its 0.1-0.5 lambda validity window",
      "issue": "momwire#282"
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
    },
    {
      "axis": "kernel",
      "value": "extended",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "extended_kernel=True + use_singular_enrichment=True not supported yet \u2014 the enrichment DOFs bypass the moment kernels entirely (they carry their own \u03a6_sing quadrature), they exist only at K >= 3 junctions where NEC's own gating turns EK off, and the O(a\u00b2) tube expansion was never derived for the s^(-1/2) shapes (stevenmburns/momwire#249 follow-up C)",
      "issue": "momwire#249"
    },
    {
      "axis": "per_wire_radius",
      "value": "True",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "use_singular_enrichment + mixed per-wire radii together not supported yet \u2014 the enrichment kernels take a single radius (stevenmburns/momwire#147)",
      "issue": "momwire#147"
    },
    {
      "axis": "wire_loading",
      "value": "True",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "use_singular_enrichment + distributed wire loading together not supported yet \u2014 the enrichment bases don't carry the loading overlap term",
      "issue": null
    },
    {
      "axis": "wire_position",
      "value": "contact",
      "forbids_axis": "ground_model",
      "forbids_value": "refl-coef",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "ground CONTACT under ground_model='refl-coef' is refused (momwire#282 stage 1, 2026-08-18): the reflection-coefficient ground's Phi-term weight is a specular-angle approximation with no validity at zero clearance (momwire#153), and at contact it does not approximate the answer at all. Measured on a base-fed quarter-wave vertical over average soil (eps_r 13, sigma 0.005 S/m) at 14 MHz, N=41: refl-coef gives 27.0+12.6j ohm against this solver's own sommerfeld answer of 51.5+23.2j ohm on the same deck and the NEC-5 binary's printed 52.4+22.7j ohm \u2014 27 ohm out, and on the WRONG SIDE of the 40.7+23.3j ohm PEC answer, so it is not a degraded approximation but a different number. This row was served and silently wrong; docs/design/contact-over-finite-ground.md 3.6 has the measurement. The MODEL is what has no story at the plane, not momwire's implementation of it: NEC-2's own reflection-coefficient ground (nec2c, GN 0) prints 175-779j ohm over average soil and 155-1248j ohm over poor soil on the same contact monopole, against a sane 39.4+22.1j ohm over GN 1 \u2014 a reflection coefficient is a plane-wave object evaluated on a specular ray, and at zero clearance there is no such ray. Use ground_model='sommerfeld', which is contact-capable (momwire#151) and gated there against the binary, or raise the wire clear of the plane \u2014 refl-coef stays served, and stays the default, for wires standing clear in its 0.1-0.5 lambda validity window",
      "issue": "momwire#282"
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
    },
    {
      "axis": "kernel",
      "value": "extended",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "extended_kernel=True + use_singular_enrichment=True not supported yet \u2014 the enrichment DOFs bypass the moment kernels entirely (they carry their own \u03a6_sing quadrature), they exist only at K >= 3 junctions where NEC's own gating turns EK off, and the O(a\u00b2) tube expansion was never derived for the s^(-1/2) shapes (stevenmburns/momwire#249 follow-up C)",
      "issue": "momwire#249"
    },
    {
      "axis": "per_wire_radius",
      "value": "True",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "use_singular_enrichment + mixed per-wire radii together not supported yet \u2014 the enrichment kernels take a single radius (stevenmburns/momwire#147)",
      "issue": "momwire#147"
    },
    {
      "axis": "wire_loading",
      "value": "True",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "use_singular_enrichment + distributed wire loading together not supported yet \u2014 the enrichment bases don't carry the loading overlap term",
      "issue": null
    },
    {
      "axis": "wire_position",
      "value": "contact",
      "forbids_axis": "ground_model",
      "forbids_value": "refl-coef",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "ground CONTACT under ground_model='refl-coef' is refused (momwire#282 stage 1, 2026-08-18): the reflection-coefficient ground's Phi-term weight is a specular-angle approximation with no validity at zero clearance (momwire#153), and at contact it does not approximate the answer at all. Measured on a base-fed quarter-wave vertical over average soil (eps_r 13, sigma 0.005 S/m) at 14 MHz, N=41: refl-coef gives 27.0+12.6j ohm against this solver's own sommerfeld answer of 51.5+23.2j ohm on the same deck and the NEC-5 binary's printed 52.4+22.7j ohm \u2014 27 ohm out, and on the WRONG SIDE of the 40.7+23.3j ohm PEC answer, so it is not a degraded approximation but a different number. This row was served and silently wrong; docs/design/contact-over-finite-ground.md 3.6 has the measurement. The MODEL is what has no story at the plane, not momwire's implementation of it: NEC-2's own reflection-coefficient ground (nec2c, GN 0) prints 175-779j ohm over average soil and 155-1248j ohm over poor soil on the same contact monopole, against a sane 39.4+22.1j ohm over GN 1 \u2014 a reflection coefficient is a plane-wave object evaluated on a specular ray, and at zero clearance there is no such ray. Use ground_model='sommerfeld', which is contact-capable (momwire#151) and gated there against the binary, or raise the wire clear of the plane \u2014 refl-coef stays served, and stays the default, for wires standing clear in its 0.1-0.5 lambda validity window",
      "issue": "momwire#282"
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
    },
    {
      "axis": "kernel",
      "value": "extended",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "extended_kernel=True + use_singular_enrichment=True not supported yet \u2014 the enrichment DOFs bypass the moment kernels entirely (they carry their own \u03a6_sing quadrature), they exist only at K >= 3 junctions where NEC's own gating turns EK off, and the O(a\u00b2) tube expansion was never derived for the s^(-1/2) shapes (stevenmburns/momwire#249 follow-up C)",
      "issue": "momwire#249"
    },
    {
      "axis": "per_wire_radius",
      "value": "True",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "use_singular_enrichment + mixed per-wire radii together not supported yet \u2014 the enrichment kernels take a single radius (stevenmburns/momwire#147)",
      "issue": "momwire#147"
    },
    {
      "axis": "wire_loading",
      "value": "True",
      "forbids_axis": "singular_enrichment",
      "forbids_value": "True",
      "forbids_is_axis": false,
      "condition": null,
      "reason": "use_singular_enrichment + distributed wire loading together not supported yet \u2014 the enrichment bases don't carry the loading overlap term",
      "issue": null
    },
    {
      "axis": "wire_position",
      "value": "contact",
      "forbids_axis": "ground_model",
      "forbids_value": "refl-coef",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "ground CONTACT under ground_model='refl-coef' is refused (momwire#282 stage 1, 2026-08-18): the reflection-coefficient ground's Phi-term weight is a specular-angle approximation with no validity at zero clearance (momwire#153), and at contact it does not approximate the answer at all. Measured on a base-fed quarter-wave vertical over average soil (eps_r 13, sigma 0.005 S/m) at 14 MHz, N=41: refl-coef gives 27.0+12.6j ohm against this solver's own sommerfeld answer of 51.5+23.2j ohm on the same deck and the NEC-5 binary's printed 52.4+22.7j ohm \u2014 27 ohm out, and on the WRONG SIDE of the 40.7+23.3j ohm PEC answer, so it is not a degraded approximation but a different number. This row was served and silently wrong; docs/design/contact-over-finite-ground.md 3.6 has the measurement. The MODEL is what has no story at the plane, not momwire's implementation of it: NEC-2's own reflection-coefficient ground (nec2c, GN 0) prints 175-779j ohm over average soil and 155-1248j ohm over poor soil on the same contact monopole, against a sane 39.4+22.1j ohm over GN 1 \u2014 a reflection coefficient is a plane-wave object evaluated on a specular ray, and at zero clearance there is no such ray. Use ground_model='sommerfeld', which is contact-capable (momwire#151) and gated there against the binary, or raise the wire clear of the plane \u2014 refl-coef stays served, and stays the default, for wires standing clear in its 0.1-0.5 lambda validity window",
      "issue": "momwire#282"
    }
  ],
  "razor-2p": [
    {
      "axis": "wire_position",
      "value": "contact",
      "forbids_axis": "ground_model",
      "forbids_value": "refl-coef",
      "forbids_is_axis": true,
      "condition": null,
      "reason": "ground CONTACT under ground_model='refl-coef' is refused (momwire#282 stage 1, 2026-08-18): the reflection-coefficient ground's Phi-term weight is a specular-angle approximation with no validity at zero clearance (momwire#153), and at contact it does not approximate the answer at all. Measured on a base-fed quarter-wave vertical over average soil (eps_r 13, sigma 0.005 S/m) at 14 MHz, N=41: refl-coef gives 27.0+12.6j ohm against this solver's own sommerfeld answer of 51.5+23.2j ohm on the same deck and the NEC-5 binary's printed 52.4+22.7j ohm \u2014 27 ohm out, and on the WRONG SIDE of the 40.7+23.3j ohm PEC answer, so it is not a degraded approximation but a different number. This row was served and silently wrong; docs/design/contact-over-finite-ground.md 3.6 has the measurement. The MODEL is what has no story at the plane, not momwire's implementation of it: NEC-2's own reflection-coefficient ground (nec2c, GN 0) prints 175-779j ohm over average soil and 155-1248j ohm over poor soil on the same contact monopole, against a sane 39.4+22.1j ohm over GN 1 \u2014 a reflection coefficient is a plane-wave object evaluated on a specular ray, and at zero clearance there is no such ray. Use ground_model='sommerfeld', which is contact-capable (momwire#151) and gated there against the binary, or raise the wire clear of the plane \u2014 refl-coef stays served, and stays the default, for wires standing clear in its 0.1-0.5 lambda validity window",
      "issue": "momwire#282"
    }
  ],
  "pynec": null,
  "nec5": null
};
