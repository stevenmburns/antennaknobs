---
title: Quickstart
description: Install antennaknobs and solve your first antenna in a few lines of Python.
---

## Run the workbench with Docker

The fastest path needs nothing but Docker — the published image serves the
full workbench, no install (new in v0.34):

```bash
docker run --rm -p 8000:8000 stevenmburns/antennaknobs:latest
# -> http://localhost:8000
```

(See [DOCKER.md](https://github.com/stevenmburns/antennaknobs/blob/main/DOCKER.md)
for compose, mounting your own designs, and the optional NEC2 engine.)

## Install with Python

To use the library — or hack on designs in your editor — install from PyPI.
`antennaknobs` and its engine `momwire` ship prebuilt wheels, so a plain
install needs no compiler:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip

pip install "antennaknobs[web]"
```

### On Windows

The same install in PowerShell. Use **Python 3.12** — it is the version every
antennaknobs test lane runs — or 3.14, which was exercised by hand on Windows
for v0.72.0 (wheels exist for 3.10 through 3.15). If `py -3.12` reports nothing,
install 3.12 from [python.org](https://www.python.org/downloads/windows/) and
tick *Add python.exe to PATH*.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "antennaknobs[web]"
python -m uvicorn antennaknobs.web.server:app      # then open http://127.0.0.1:8000
```

If PowerShell refuses to run `Activate.ps1`, allow scripts for your user once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Always run pip as
`python -m pip` so it installs into the venv you just activated and not into
whichever Python is first on PATH. If the install seems to compile for
minutes, pip did not pick a wheel — stop and paste the output of
`python -m pip debug --verbose` into an issue, with
`python -X faulthandler -c "import antennaknobs; print('IMPORT OK')"` after it.
With a licensed NEC-5, see [NEC-5](/reference/nec5/) for the one variable that
adds it as a solver.

:::note
`momwire` (the solver) comes along as a dependency. Optionally, add the NEC2
solver (PyNEC) as an alternative to momwire:

```bash
pip install "pynec-accel>=1.7.4.post2"
```
:::

This install serves the same web workbench as the Docker image:

```bash
uvicorn antennaknobs.web.server:app      # then open http://127.0.0.1:8000
```

Pick a design from the dropdown and drag its knobs — the pattern, SWR, and
impedance re-solve live.

## Solve from Python

Every design is an [`AntennaBuilder`](/concepts/model/). Wrap one in an
`Antenna` and ask for its feed-point impedance:

```python
from antennaknobs import Antenna
from antennaknobs.designs.dipoles.invvee import Builder

ant = Antenna(Builder())  # an inverted-vee dipole, default parameters
print(ant.impedance())  # -> [(55.1-10.1j)]  ohms in free space, one entry per feed port
```

Tune a knob and re-solve — parameters are plain attributes:

```python
b = Builder()
b.length_factor = 1.0  # stretch the arms
print(Antenna(b).impedance())  # -> [(60.5+32.3j)]

# over real earth — the workbench's default soil:
print(Antenna(b, ground=("finite", 13.0, 0.005)).impedance())  # -> [(53.6+34.1j)]
```

`Antenna` also gives you the far-field pattern, a frequency sweep of the
impedance, and the current distribution:

```python
ant.far_field()  # full-sphere far-field rings
ant.impedance_sweep(...)  # impedance across a frequency range
```

By default `Antenna` uses a finite ground; pass `ground="free"` (or a
`("finite", eps_r, sigma)` tuple) to change it.

:::tip[Next]
- [The model](/concepts/model/) — `build_wires()` and the knob system.
- [Many ways to express geometry](/concepts/authoring/) — the same loop, five ways.
- [Command line](/reference/cli/) — sweeps, patterns, and `.nec` export from the terminal.
:::
