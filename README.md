# AntennaKNoBs &nbsp;·&nbsp; *by KK7KNB*

### Script your antenna. Explore it in real time by turning knobs.

AntennaKNoBs is a Python package for **parametric, programmatic antenna design**.
You describe an antenna once as a small Python *builder* — its geometry expressed
in terms of named parameters — and then explore the design space two ways:

- **In code**, from the command line or a Python script: draw geometry, sweep a
  parameter, compare radiation patterns, optimize for match or gain, export a
  NEC deck.
- **In the browser**, from a live workbench: drag a knob and watch the 3D wire
  model, far-field patterns, and Smith chart redraw in real time.

Its built-in engine is **momwire**, a new in-house set of method-of-moments
engines. You can *optionally* add **PyNEC** (the battle-tested NEC2 engine) as a
second backend and solve the same design both ways to trust the answer.

[![Test Python package](https://github.com/stevenmburns/antennaknobs/actions/workflows/test.yml/badge.svg)](https://github.com/stevenmburns/antennaknobs/actions/workflows/test.yml)
[![Ruff](https://github.com/stevenmburns/antennaknobs/actions/workflows/ruff.yml/badge.svg)](https://github.com/stevenmburns/antennaknobs/actions/workflows/ruff.yml)
[![Coverage](https://raw.githubusercontent.com/stevenmburns/antennaknobs/python-coverage-comment-action-data/badge.svg)](https://github.com/stevenmburns/antennaknobs/actions/workflows/test.yml)

---

## The live web workbench

It's live at **[app.antennaknobs.dev](https://app.antennaknobs.dev/)** — open
it, pick a design, and drag a knob (no install).

The workbench is the fastest way to feel a design. Pick an antenna, and its
parameters appear as a panel of *knobs*. Drag one and every view
updates live over a WebSocket: the solver re-runs and the browser redraws.

<!-- TODO: add a screenshot/gif of the web workbench here (web-workbench.png) -->

What you get:

- **A panel of knobs.** Every builder parameter becomes a knob (or dropdown,
  or checkbox) with sensible min/max/step. Drag and the design re-solves.
- **3D wire geometry** with current visualization, viewable from three
  orthogonal projections (top / front / side).
- **Azimuth and elevation** far-field pattern slices.
- **A Smith chart** of input impedance, with optional frequency-sweep and
  convergence overlays.
- **Three solver slots (A / B / C)** you can point at different backends and
  compare side by side on the same antenna, at once. The defaults are already
  a cross-check: B-spline d=2 (the working solver) vs. B-spline d=1 (same
  physics through an independent basis) vs. PyNEC.
- **A ground plane, on by default** — real antennas hang over real ground, so
  the workbench starts there (free space is one click away). The ground is
  described by what it *is* — finite (εr=10, σ=0.002) or PEC — independent of
  solver; each backend solves it as best it can (PyNEC additionally offers
  Sommerfeld-Norton vs. the faster reflection-coefficient method), and the
  solve readout reports the model that actually ran.

Live updates stay responsive because rapid knob drags are coalesced into one
solve per round-trip, so the solver is never buried under stale requests.

### Running it

The workbench is a FastAPI backend plus a React (Vite) frontend.

**Installed (no Node needed).** A wheel install bundles the pre-built frontend,
so one process serves the whole app:

```bash
pip install "antennaknobs[web]"
uvicorn antennaknobs.web.server:app      # open http://127.0.0.1:8000
```

The backend serves the UI at `/` and the JSON/`/ws` API on the same origin;
`/docs` is the interactive API explorer.

**Development (two terminals, hot-reload).** When editing the frontend, run the
Vite dev server alongside the backend so you get HMR:

```bash
# Terminal 1 — backend (from the repo root, in your .venv)
pip install -e ".[web]"
uvicorn antennaknobs.web.server:app --reload   # API on http://127.0.0.1:8000

# Terminal 2 — frontend dev server
cd src/antennaknobs/web/frontend
npm install
npm run dev                              # open http://localhost:5173
```

The Vite dev server proxies the API and the `/ws` live-solve channel to the
backend on port 8000, so you only ever open `http://localhost:5173`. (A source
checkout has no pre-built bundle, so the backend alone runs API-only until you
`npm run build` — which writes `src/antennaknobs/web/static/`, the same bundle the wheel ships.)

> The `[web]` extra pulls in `uvicorn[standard]`, which includes the WebSocket
> support the live-solve channel needs — plain `uvicorn` fails the `/ws`
> handshake.

---

## Two simulation backends

AntennaKNoBs can solve any design with either backend, selected per-run with
`--engine` (CLI) or per-slot (web). Solving the same antenna two ways is the
point — agreement between independent engines is your confidence check.

| | **PyNEC** | **momwire** |
|---|---|---|
| What | Python binding to the compiled C++ **NEC2** engine | In-house **method-of-moments** engines, pure-Python core with optional C++ accelerators |
| Basis | NEC2 thin-wire (pulse/sinusoidal) | Three bases — triangular (tent), sinusoidal, B-spline — plus H-matrix and array-block accelerators built on them |
| Speed | Very fast single-frequency solves | Fast; C++ accelerators (pybind11) for assembly/quadrature, pure-Python fallback |
| Ground | Sommerfeld–Norton finite ground (default) or the faster reflection-coefficient approximation | Reflection-coefficient finite ground on the B-spline family; PEC image on the other bases; the engine API defaults to free space (the web workbench turns ground on) |
| Install | Prebuilt wheel from the `python-necpp` fork release (OpenBLAS vendored) | C++ accelerator built from the `momwire` submodule |
| Use it for | The established reference; finite-ground patterns | Basis-flexible cross-validation; geometries where NEC2 reactance fails to converge |

**Selecting an engine** (CLI):

```bash
--engine momwire                 # momwire (default), default triangular basis
--engine momwire:triangular      # piecewise-linear (tent) basis  — the momwire default
--engine momwire:sinusoidal      # NEC2-style three-term basis (cross-validator)
--engine momwire:bspline         # degree-1/2 B-spline Galerkin basis
--engine momwire:hmatrix         # B-spline + hierarchical-matrix (ACA) acceleration
--engine momwire:arrayblock      # element-aware block solver for arrays
--engine pynec                   # NEC2 via PyNEC (needs the optional pynec-accel)
```

In Python, instantiate an engine directly:

```python
from antennaknobs.engines import PyNECEngine, MomwireEngine
from momwire import BSplineSolver

engine = PyNECEngine(builder)
engine = MomwireEngine(builder, solver=BSplineSolver, solver_kwargs={"degree": 2})
```

**momwire** lives in its own repository and is vendored here as a git submodule;
its `BSplineSolver` (the web workbench's default) is validated against the
independent triangular (tent) basis, which converges to NEC accuracy in ~80
segments. The H-matrix and array-block engines are newer and aimed at large
arrays. **PyNEC** is an
*optional* second backend — the `python-necpp` fork, distributed as a
self-contained wheel (OpenBLAS vendored, so no SWIG/BLAS/autotools toolchain is
required at install time). It is licensed **GPL-2.0** and installed separately
from its own release; antennaknobs (MIT) neither bundles nor depends on it,
and loads it only if present.

---

## Designing antennas in code

An antenna is a subclass of `AntennaBuilder` that declares named parameters and
builds its wires from them. Because the geometry is *computed* from parameters
in ordinary Python, you specify physical coordinates a minimal number of times —
the rest follow by reflection and relative position. (Most antenna tools make
you type six absolute coordinates per wire.)

For path-shaped geometry (loops, vees, rhombics) you can describe the *walk*
instead of the coordinates, with the `Drone` 3D-turtle — see the
[Drone & Transform reference](https://antennaknobs.dev/reference/drone-transform/).

Here is the built-in Moxon beam (`beams.moxon`), abbreviated. Four parameters
describe the rectangle; helper functions negate coordinates (`rx`, `ry`) and
chain nodes into wires (`build_path`):

```python
from ... import AntennaBuilder
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "freq": 28.57,
            "base": 7.0,
            "halfdriver": 2.4597430629596713,   # length of one radiating side
            "aspect_ratio": 0.3646010186757216,  # short side / long side
            "tipspacer_factor": 0.07729647745945359,
            "t0_factor": 0.4078045966770739,
        }
    )

    def build_wires(self):
        eps = 0.05
        base = self.base

        long = 2 * self.halfdriver / (1 + 2 * self.aspect_ratio * self.t0_factor)
        short = self.aspect_ratio * long
        tipspacer = short * self.tipspacer_factor
        t0 = short * self.t0_factor

        def build_path(lst, ns, ex):
            return ((a, b, ns, ex) for a, b in zip(lst[:-1], lst[1:]))
        def rx(p): return -p[0], p[1], p[2]   # mirror across x
        def ry(p): return p[0], -p[1], p[2]   # mirror across y

        S = (short / 2, eps, base)
        A = (S[0], long / 2, base)
        B = (A[0] - t0, A[1], base)
        C = (B[0] - tipspacer, B[1], base)
        D = rx(A)
        E, F, G, H, T = ry(D), ry(C), ry(B), ry(A), ry(S)

        n_seg0, n_seg1 = 21, 1
        tups = []
        tups.extend(build_path([S, A, B], n_seg0, None))
        tups.extend(build_path([C, D, E, F], n_seg0, None))
        tups.extend(build_path([G, H, T], n_seg0, None))
        tups.append((T, S, n_seg1, 1 + 0j))   # the driven segment
        return tups
```

The top-level package re-exports the workhorse functions, so a full
design-explore-compare loop is a short script. This optimizes an inverted-V
dipole at several heights and overlays the resulting patterns:

```python
import antennaknobs as ant
from antennaknobs.designs.dipoles.invvee import Builder

p = dict(Builder.default_params)
bounds = ((p['length_factor'] * .8, p['length_factor'] * 1.25), (0, 60))

builders = (
    ant.optimize(
        Builder(dict(p, base=base)),
        ['length_factor', 'angle_deg'], z0=50, bounds=bounds,
    )
    for base in [5, 6, 7, 8]
)

ant.compare_patterns(builders)
```

---

## Command-line usage

Everything is under `python -m antennaknobs <subcommand>`. Designs are named
`family.name` (with an optional `:variant`) — run `list` to see them all.

```bash
# Draw a Moxon's wire geometry to a file
python -m antennaknobs draw --builder beams.moxon --fn moxon.png

# Sweep frequency and plot impedance on a Smith chart
python -m antennaknobs sweep --builder beams.moxon --param freq \
    --use_smithchart --npoints 21 --fn moxon_smith.png

# Far-field pattern of a Yagi, solved with momwire
python -m antennaknobs pattern --builder beams.yagi --engine momwire:triangular

# Overlay patterns of three beams
python -m antennaknobs compare_patterns \
    --builders beams.moxon beams.hexbeam beams.yagi --fn beams.png

# Cross-check one design across two backends
python -m antennaknobs compare_patterns \
    --builders beams.moxon beams.moxon --engines pynec momwire:bspline --fn check.png

# Optimize length and arm angle of an inverted-V dipole for a 50 Ω match
python -m antennaknobs optimize --builder dipoles.invvee \
    --params length_factor angle_deg

# Export a NEC2 card deck for use in external tools
python -m antennaknobs export --builder beams.hexbeam --out hexbeam.nec

# List the available designs (optionally filter)
python -m antennaknobs list
python -m antennaknobs list dipole
```

Shared flags: `--engine` (backend, see above), `--ground`
(`free` | `pec` | `finite` | `finite:<eps_r>,<sigma>`), `--builder`/`--builders`,
and `--fn` (save to file instead of showing on screen).

Below is a typical far-field plot produced by the `pattern`/`compare_patterns`
commands:

![Radiation pattern](RadiationPattern.png)

### Available designs

Roughly 70 built-in designs across nine families — run
`python -m antennaknobs list` for the authoritative list:

| Family | Examples |
|---|---|
| `dipoles` | invvee, folded_invvee, ocf_dipole, koch_dipole, dipole_turnstile |
| `beams` | moxon, hexbeam, yagi, hb9cv |
| `loops` | quad, delta_loop, diamond_loop, horizontal_loop, bisquare |
| `verticals` | vertical, jpole, inverted_l, bobtail, four_square, bruce |
| `arrays` | yagiarray, moxonarray, invveearray, bowtiearray, delta_looparray |
| `multiband` | fandipole, trap_dipole, hexbeam_5band, twoband_fan_dipole |
| `broadband` | discone, g5rv, lpda, t2fd |
| `wire` | sterba, rhombic, vbeam, w8jk, zepp, lazy_h, longwire |
| `specialty` | hentenna, bowtie, helix, hourglass |

User-authored designs (in the `user.*` namespace) appear here too; filter with
`list --builtin-only` / `list --user-only`. Drop a Python file in
`~/.antennaknobs/designs/` and it shows up in the workbench — see
[Writing designs with Claude Code](https://antennaknobs.dev/concepts/authoring-with-claude/)
for the contract and how to have Claude Code write one from a plain-language
description.

---

## Install

### From PyPI (prebuilt wheels — no toolchain)

`antennaknobs` and its C++ engine `momwire` are published to **PyPI** with
prebuilt wheels, so a plain install needs no compiler:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip

# antennaknobs + the web workbench; momwire (the engine) comes along as a dep
pip install "antennaknobs[web]"
```

Optionally, add the **NEC2 solver** (PyNEC) as an alternative to momwire:

```bash
# optional NEC2 solver (Linux / Windows / macOS-arm64 wheels)
pip install "pynec-accel>=1.7.4.post2"
```

Then launch the workbench with `uvicorn antennaknobs.web.server:app` (see
[Running it](#running-it)). On **macOS**, `brew install libomp` is required —
the `momwire` and `pynec-accel` wheels link Homebrew's OpenMP runtime (and share
it, so cross-engine use is fully multithreaded; details under [macOS](#macos)).

The sections below build from source instead (a development checkout, or a
platform without prebuilt wheels).

### Ubuntu (22.04 / 24.04)

PyNEC installs as a prebuilt wheel, so no
SWIG/BLAS/autotools toolchain is needed; only the momwire C++ accelerator compiles
from source (hence `g++`).

**1. System dependencies**

```bash
sudo apt-get update
sudo apt-get install \
    python3 python3-pip python3-venv python3-dev \
    g++ build-essential git
```

**2. Clone and create a virtual environment**

```bash
git clone https://github.com/stevenmburns/antennaknobs
cd antennaknobs
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install setuptools numpy scipy pytest matplotlib icecream scikit-rf
```

**3. Install momwire (the engine)**

```bash
# momwire: a git submodule; its C++ accelerator builds from source.
pip install pybind11
git submodule update --init momwire
pip install --no-build-isolation -e ./momwire
```

> The submodule pointer tracks the exact momwire release the pyproject pins.
> If it ever drifts behind the pin, step 4 below silently replaces your
> editable momwire with the PyPI wheel (pip resolving `momwire==X`) and edits
> under `momwire/` stop taking effect — verify with
> `python -c "import momwire; print(momwire.__file__)"`, which must point into
> the checkout, and re-run this step after `git submodule update --remote
> momwire` if it doesn't.

**3b. (Optional) Install PyNEC for cross-validation**

PyNEC is an optional second backend — **GPL-2.0**, installed separately from its
own release, and never bundled with or required by antennaknobs. Skip it and
momwire is still fully functional; install it only if you want to cross-check
against NEC2.

```bash
# The fork is published to PyPI as `pynec-accel` (a distinct name from upstream
# PyNEC/pynec, whose builds are broken on current Python; the import name stays
# `import PyNEC`). Its wheels vendor OpenBLAS + libgfortran.
#
# Use >= 1.7.4.post2: earlier builds vendored their own libgomp, which clashes
# with momwire's system libgomp via a static-TLS limit and silently knocks
# momwire's C++ accelerator onto its slow pure-Python path whenever both backends
# load in one process. post2 binds the system libgomp instead (universal on glibc
# Linux — the GCC OpenMP runtime).
pip install "pynec-accel>=1.7.4.post2"
```

**4. Install AntennaKNoBs**

```bash
pip install -e ".[test]"         # core + test deps (pytest, the web test client)
# or  pip install -e ".[web]"    # just the web workbench, no test extras
# or  pip install -e .           # library only
```

**5. Run the tests**

```bash
pytest -vv --durations=0 -- tests/
```

(The `[test]` extra above is what makes this step work from a clean clone — it
pulls in `pytest`, the `[web]` server deps, and `httpx2` for the web-server
tests' TestClient.)

> The authoritative, always-tested version of this whole sequence is the CI
> workflow at [`.github/workflows/test.yml`](.github/workflows/test.yml) — it
> installs both engines and runs the suite on every push. If anything here
> drifts, that file is the source of truth.

### macOS

Tested on Apple Silicon (arm64), macOS 14+. The momwire C++ accelerator compiles
from source against Homebrew's OpenMP runtime (`libomp`); PyNEC installs as a
prebuilt wheel. CI only runs Ubuntu, so the Ubuntu sequence above is the
source of truth — the steps below are the same with macOS system packages.

**1. System dependencies**

```bash
xcode-select --install              # clang/clang++ + git (skip if already installed)
brew install python git libomp      # libomp = the OpenMP runtime the momwire accelerator links
```

**2. Clone and create a virtual environment.** Use a venv — on macOS it is
effectively required, not just good hygiene: Homebrew's Python is marked
externally managed (PEP 668), so `pip install` into it fails with an
`error: externally-managed-environment`. A venv sidesteps that and keeps the
project's dependencies off your system Python.

```bash
git clone https://github.com/stevenmburns/antennaknobs
cd antennaknobs
python3 -m venv .venv
source .venv/bin/activate         # re-run this in each new shell before using the project
pip install --upgrade pip setuptools wheel
pip install numpy scipy pytest matplotlib icecream scikit-rf
```

**3. Install momwire (the engine)** — same as Ubuntu:

```bash
pip install pybind11
git submodule update --init momwire
pip install --no-build-isolation -e ./momwire
```

The build finds Homebrew's `libomp` at `/opt/homebrew/opt/libomp`, the Apple
Silicon default. On an Intel Mac, Homebrew lives under `/usr/local`, so point the
build there with `LIBOMP_PREFIX`:

```bash
LIBOMP_PREFIX=/usr/local/opt/libomp pip install --no-build-isolation -e ./momwire
```

If the accelerator fails to build for any reason, momwire still installs and runs
in its slower pure-Python mode.

**3b. (Optional) Install PyNEC for cross-validation**

The same optional **GPL-2.0** second backend as on Linux. The fork ships prebuilt
macOS wheels for **Apple Silicon (arm64), macOS 14+, Python 3.10–3.14** only —
there are no Intel-Mac wheels, so on an Intel Mac skip PyNEC and use momwire alone.

```bash
pip install "pynec-accel>=1.7.4.post2"
```

With **pynec-accel ≥ 1.7.4.post2** and **momwire ≥ 0.2.1**, neither wheel vendors
its own `libomp` — both link Homebrew's by absolute path, so a process that loads
both (any cross-engine run, including the tests) shares a *single* OpenMP runtime
and stays fully multithreaded, with no env vars. That shared runtime is why
`brew install libomp` is required.

> Older macOS wheels each bundled a private `libomp`; two copies in one process
> abort with `OMP: Error #15` (or, with `KMP_DUPLICATE_LIB_OK=TRUE`, deadlock). If
> you're pinned to a pre-`1.7.4.post2` pynec-accel or pre-`0.2.1` momwire, the
> stopgap is `export KMP_DUPLICATE_LIB_OK=TRUE` and `export OMP_NUM_THREADS=1`
> before any cross-engine run — at the cost of a single-threaded accelerator.

**4. Install AntennaKNoBs** and **5. Run the tests** — identical to the Ubuntu
steps:

```bash
pip install -e ".[test]"
pytest -vv --durations=0 -- tests/
```

(For the web workbench's frontend dev server, also `brew install node`.)

---

## Acknowledgments

Most of this codebase — the `AntennaBuilder` framework, the design catalog, the
momwire engine bindings, the web workbench, and these docs — was written with
**[Claude Code](https://claude.com/claude-code)**, Anthropic's agentic coding
tool, working from KK7KNB's direction and antenna-engineering judgment.

## License

MIT — see [LICENSE](LICENSE).
