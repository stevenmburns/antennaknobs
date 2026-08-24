# scratch/ — tracked study evidence

**This directory is checked in, and most of it cannot be regenerated. Do not
add `scratch/` to `.gitignore`.**

The name is a historical accident and the contents outgrew it. It was created
on 2026-06-19 (`784f00562`, "Add cross-engine evaluation harness for design
cross-checks") holding exactly one throwaway file — `eval_engines.py`, 81
lines. The name was honest then. Two months later it holds ~6,700 tracked
files and is the evidence layer for published claims, so the name now reads
as an invitation to delete work that several other things depend on.

Renaming it was considered and declined: 107 in-repo references, momwire
source docstrings pointing in from another repo, and four GitHub issue bodies
a rename cannot fix. This file is the cheaper repair.

## What depends on what is in here

- **`tests/fixtures/eznec_nec5/manifest.json`** cites `eznec-capture/` as the
  provenance of the W7EL signed-node oracle. Those NEC-5 printouts were made
  by EZNEC Pro/2+ driving a **licensed** `NEC5CL_x13.exe`; the binary is
  never distributed and the captures cannot be re-made without it.
- **momwire's own source** reaches in here. `_sommerfeld_below.py` and
  `_sommerfeld_transmitted.py` cite `524-phase0/` for the formulation they
  implement, and `524-phase0/proto/EQUATIONS.md` is where those equations are
  transcribed. `momwire/tests/golden_below_below_524.py` names the prototype
  it was generated from.
- **~15 `docs/status/*.md`** cite `scratch/*.json` / `*.jsonl` as the artifact
  behind a published finding.

## The two tiers wearing one name

| | what | rule |
|---|---|---|
| `4nec2-capture/`, `eznec-capture/`, `524-phase0/`, `qrz-lfa-thread/`, `n4pc-study/`, `553-arc/`, `simnec/` | captures, oracle runs and study artifacts backing claims made elsewhere | **tracked**; treat as append-only |
| loose harnesses and probe scripts at the top level | one-off tooling | tracked, but genuinely disposable |

If the tiers are ever worth separating, the honest split is to promote the
first group to `evidence/` and let `scratch/` go back to meaning scratch —
about two directories of path updates rather than all 107 references.

## What is deliberately NOT tracked

Governed by `.gitignore`, and all of it is regenerable from what IS tracked:

- **`*.NEX`** — NEC-5 Sommerfeld interpolation caches. A grid keyed to medium
  and frequency, rebuilt by the engine on demand. The deck and the printout
  beside it are the evidence; 33 MB of cache is not. `eznec-capture` already
  works this way (244 `.NEC` + 241 `.OUT`, zero `.NEX`).
- **`*.png`** — figures are OUTPUT. The script that draws one lives here
  (`qrz-lfa-thread/fig_residual_emf.py`, `n4pc-study/figure.py`); the PNG is
  reproducible from it, and the repo ignores `*.png` globally.
- **`*.log`**, **`__pycache__/`** — run noise.

## Adding to it

Commit the deck, the printout, and the script that produced the reading.
Leave out caches, figures and logs. If a study's numbers are quoted anywhere
outside this directory — a status doc, an issue, a docstring, a post — the
artifact behind them belongs in here, committed, before the quote goes out.
