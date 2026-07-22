---
title: Quickstart
description: Install antennaknobs and solve your first antenna in a few lines of Python.
---

## Install

The fastest path needs nothing but Docker — the published image serves the
full workbench (new in v0.34):

```bash
docker run --rm -p 8000:8000 stevenmburns/antennaknobs:latest
# -> http://localhost:8000
```

(See [DOCKER.md](https://github.com/stevenmburns/antennaknobs/blob/main/DOCKER.md)
for compose, mounting your own designs, and the optional NEC2 engine.)

Prefer a Python install? `antennaknobs` and its engine `momwire` are
published to PyPI with prebuilt wheels — a plain install needs no compiler:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip

pip install "antennaknobs[web]"
```

:::note
`momwire` (the solver) comes along as a dependency. Optionally, add the NEC2
solver (PyNEC) as an alternative to momwire:

```bash
pip install "pynec-accel>=1.7.4.post2"
```
:::

## Launch the web workbench

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

ant = Antenna(Builder())     # an inverted-vee dipole, default parameters
print(ant.impedance())       # -> [(48.6-8.8j)]  ohms, one entry per feed port
```

Tune a knob and re-solve — parameters are plain attributes:

```python
b = Builder()
b.length_factor = 1.0        # stretch the arms
print(Antenna(b).impedance())
```

`Antenna` also gives you the far-field pattern, a frequency sweep of the
impedance, and the current distribution:

```python
ant.far_field()          # full-sphere far-field rings
ant.impedance_sweep(...)  # impedance across a frequency range
```

By default `Antenna` uses a finite ground; pass `ground="free"` (or a
`("finite", eps_r, sigma)` tuple) to change it.

:::tip[Next]
- [The model](/concepts/model/) — `build_wires()` and the knob system.
- [Many ways to express geometry](/concepts/authoring/) — the same loop, five ways.
- [Command line](/reference/cli/) — sweeps, patterns, and `.nec` export from the terminal.
:::
