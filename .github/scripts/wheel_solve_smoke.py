"""Solve smoke test for a wheel-only install (PyPI deps, no git submodule).

Run by the `wheel-smoke` job in test.yml after `pip install <wheel>[web]` in an
environment with NO momwire submodule — momwire resolves from PyPI per the
version floor in pyproject.toml. Dev and the other CI jobs install the
submodule, so they can never notice code that uses a momwire API the floor
does not guarantee. That exact split shipped v0.13.0 broken: server.solve()
passed cancel=momwire.CancelToken() while the floor still admitted momwire
0.2.3, which predates the cancel API — every solve on Fly raised
AttributeError and the readout never populated.

This script exercises precisely that seam: the web server's solve entry point,
with a cancel token, against whatever momwire pip actually resolved.
"""

import momwire

from antennaknobs.web import server

req = {
    "geometry": "loops.triangular_skyloop",
    "measurement_freq_mhz": 3.8,
    "design_freq_mhz": 3.8,
    "momwire_model": "triangular",
    "n_per_wire": 20,
    "ground": False,
}
out = server.solve(req, cancel=momwire.CancelToken())

assert "error" not in out, f"solve returned an error: {out.get('error')}"
assert isinstance(out.get("z_in_re"), float), f"no impedance in response: {sorted(out)}"
assert out.get("wires"), "no wire geometry in response"

print(
    f"wheel smoke OK: momwire {getattr(momwire, '__version__', '?')}, "
    f"Z = {out['z_in_re']:.2f} {'+' if out['z_in_im'] >= 0 else '-'} "
    f"j{abs(out['z_in_im']):.2f} ohm, solve {out['solve_ms']:.1f} ms"
)
