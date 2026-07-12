"""POTA wire-gauge tradeoff: a 20 m inverted-V where the wire is a knob.

The park-activation question, as numbers (issue #318): a half-wave
inverted-V on a 7 m telescoping pole, with the **wire itself** selectable
from the `WIRES` catalog — 28/22/18 AWG, bare or PVC-insulated. Flip the
`wire_type` dropdown and watch three things move at once:

* **weight** — the Info pane reports the total wire run and its grams
  (jacket included). 28 AWG is a tenth the copper of 18 AWG.
* **radiated power** — skin-effect loss (momwire#131 distributed loading;
  PyNEC's native LD 5) shows up as a *wire loss (I²R)* row in the power
  budget and as lost tenths of a dB. Thin wire pays roughly −0.3 dB on
  this antenna; thick wire nearly nothing.
* **SWR bandwidth** — two stacked effects the sweep untangles honestly:
  thicker wire widens the resonance *geometrically* (lower ln(L/a) Q),
  while thinner wire widens it *dissipatively* — bandwidth you pay for
  in watts. The band-locked sweep shows 20 m edge-to-edge.

The PVC variants also land visibly lower in frequency than bare copper
cut to the same length — the insulated-wire velocity factor (a few
percent, King's jacket inductance), i.e. why a cut-to-formula insulated
dipole tunes long. The default `length_factor` is tuned so the stock
22 AWG PVC wire resonates near 14.1 MHz at 7 m over average ground;
switching to bare wire moves resonance UP — retune with the length knob
and note how much shorter the insulated antenna is.

Geometry is the stock `dipoles.invvee` V (same knobs) at 20 m scale.
PyNEC models the conductor loss but not the jacket (no NEC-2 card), so
engine-switching on a PVC variant shifts resonance — momwire is the
fidelity engine there.
"""

from types import MappingProxyType

from ...network import WIRES
from .invvee import Builder as InvVee


class Builder(InvVee):
    default_params = MappingProxyType(
        {
            **InvVee.default_params,
            # 20 m: the bread-and-butter POTA band.
            "design_freq": 14.1,
            "freq": 14.1,
            # Apex on a 7 m telescoping pole (≈0.33λ up on 20 m).
            "base": 7.0,
            # Tuned for the DEFAULT wire below (22 AWG PVC) to resonate
            # near 14.1 MHz at this height over average ground — insulated
            # wire is a few percent electrically longer than bare, so this
            # sits below the bare-wire invvee factor.
            "length_factor": 0.9440,
            "wire_type": "22-awg-pvc",
            "ui_params": MappingProxyType(
                {
                    **InvVee.default_params["ui_params"],
                    "wire_type": {"enum_options": tuple(sorted(WIRES))},
                    # The story lives inside the band: lock the sweep to the
                    # band being measured so the SWR-bandwidth comparison
                    # reads edge-to-edge on 20 m.
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                }
            ),
        }
    )
