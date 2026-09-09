"""The `Antenna` alias behind the quick start's first example.

`Antenna(builder).impedance()` has to work on a plain `pip install
antennaknobs`. Until 2026-09-10 the alias was `PyNECEngine`, which is `None`
unless the optional `pynec-accel` extra is installed — so the documented
first example raised "'NoneType' object is not callable" for every user
without it (antennaknobs#1323; found through AC6LA's install attempt and
reproduced on a fresh Python 3.14 venv from PyPI, on Linux, so it was never
a Windows or a 3.14 problem). Our own venvs all carry PyNEC, which is why
no one here ever saw it.

It is now the momwire B-spline engine, the solver every install has. Free
space by default, as `MomwireEngine` is; pass `ground=("finite", 13.0,
0.005)` (or any ground spec) for real earth. `PyNECEngine` stays where it
always was, `antennaknobs.engines.pynec`, for callers that want NEC-2.
"""

from .engines.momwire import MomwireEngine as Antenna

__all__ = ["Antenna"]
