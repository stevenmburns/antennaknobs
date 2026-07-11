---
title: Release notes
description: Where to find what changed in each antennaknobs and momwire release, and what a release means for the hosted simulator.
---

antennaknobs ships as **two packages**, each with its own version and release
notes:

- **[antennaknobs releases](https://github.com/stevenmburns/antennaknobs/releases)** —
  the designs, engines, CLI, and web workbench. This is the version shown by
  the hosted simulator.
- **[momwire releases](https://github.com/stevenmburns/momwire/releases)** —
  the in-house MoM engine (basis functions, ground models, accelerated
  solvers). Solver-level capabilities — a new ground model, a faster
  assembly path — land here first.

Notes are generated from the pull requests that went into each release, with a
full-changelog diff link between tags, so every entry traces back to the code
and discussion behind it.

## What a release means for the hosted simulator

The live simulator and this documentation site deploy **from release tags,
not from every merge**: cutting an antennaknobs release publishes the package
to PyPI and deploys the same tagged commit to the hosted app and docs. The
version number therefore always names exactly what is running — if the
release notes say a solver capability landed in the current version, the
hosted simulator has it.

## How the two versions relate

Each antennaknobs release pins an **exact momwire version** — the engine
release it was tested and deployed against. A `pip install antennaknobs`
installs that engine automatically, so the pair you run locally is the pair
running on the hosted simulator. (Earlier releases declared a minimum
version instead; the exact pin replaced it so a new engine release can't
silently change solver behavior under an already-published antennaknobs.)
