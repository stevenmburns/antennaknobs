# Buried-flow unit 1: the efficiency leg — power balance and an outside reference

Measured 2026-09-03 on the laptop, AK main 42f5a04 (v0.67.0), momwire v0.47.0.
Gate: `tests/test_buried_flow_power_balance.py`.

## Power balance on the catalog deck (momwire, auto mesh, auto quadrature)

eta = hemispherical integral of linear gain = P_rad / P_in
(`antennaknobs.far_field.radiated_fraction`).

| soil (eps_r/sigma) | N | Z_in (Ω) | P_in (W) | eta |
|---|---|---|---|---|
| A 13/0.005 | 1 | 168.186+43.070j | 0.0028 | 0.0766 |
| A 13/0.005 | 2 | 107.964+43.057j | 0.0040 | 0.1189 |
| A 13/0.005 | 3 | 87.020+41.693j | 0.0047 | 0.1479 |
| A 13/0.005 | 4 | 75.850+40.451j | 0.0051 | 0.1699 |
| poor 5/0.001 | 1 | 160.861+106.980j | 0.0022 | 0.0602 |
| poor 5/0.001 | 2 | 85.967+59.813j | 0.0039 | 0.0979 |
| poor 5/0.001 | 3 | 66.450+43.351j | 0.0053 | 0.1254 |
| poor 5/0.001 | 4 | 58.063+35.530j | 0.0063 | 0.1428 |
| good 20/0.03 | 1 | 89.052+46.426j | 0.0044 | 0.2225 |
| good 20/0.03 | 2 | 68.034+40.224j | 0.0054 | 0.2920 |
| good 20/0.03 | 3 | 60.742+37.325j | 0.0060 | 0.3273 |
| good 20/0.03 | 4 | 56.947+35.679j | 0.0063 | 0.3494 |

eta ≤ 1 everywhere, monotone in N, good > A > poor at every N. These are
"where do the watts go" fractions: they include the far-field ground
absorption of a vertical over lossy earth, not only the screen's near-field
loss, which is why four buried radials over average soil read 17 %.

## Outside reference: nec2++ on the raised vertical (both engines serve it)

| ground | engine | Z_in (Ω) | max gain (dBi) | eta | eta·R_in |
|---|---|---|---|---|---|
| pec | momwire | 51.408−0.274j | 6.095 | 0.9632 | 49.52 |
| pec | nec2++ | 46.910−0.563j | 6.496 | 1.0566 | 49.57 |
| A 13/0.005 | momwire | 49.797−3.611j | 1.234 | 0.2989 | 14.88 |
| A 13/0.005 | nec2++ | 45.551−3.643j | 1.625 | 0.3270 | 14.90 |
| good 20/0.03 | momwire | 51.237−2.854j | 1.616 | 0.3505 | 17.96 |
| good 20/0.03 | nec2++ | 46.830−2.922j | 2.011 | 0.3839 | 17.98 |

For a fixed drive current the radiated power is eta·R_in. The two engines
agree on it to 0.10–0.13 % over PEC and both soils, while disagreeing by 9 %
on R_in itself. So the far-field integration and the Sommerfeld/Fresnel
ground reflection in momwire's pattern code match an independent
implementation; the 9 % is the impedance leg (nec2 vs bspline at this deck's
auto mesh) and is not this unit's question.

Recorded: nec2++'s radiated fraction over PEC is 1.057 — above unity by
5.7 % — where momwire's is 0.963. Over PEC the vertical's gain peaks at the
horizon, which the 1° grid's trapezoid clips; clipping loses power, it does not
add it, so the nec2++ figure is a normalisation question in the NEC-2 engine
(gain relative to which input power). Filed as an AK issue.

## What this settles

The efficiency leg now has (a) a physics gate on the catalog deck across the
radial count and three soils, and (b) an outside reference for the pattern
code over a Sommerfeld ground at the 0.1 % level. What it does NOT give is a
MEASURED efficiency: BLE 1937 measured resistance, and the far-field ground
loss is not in that ledger. A measured efficiency reference (field-strength
based) is a separate unit if one is wanted.
