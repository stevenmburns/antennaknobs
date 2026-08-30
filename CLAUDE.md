# antennaknobs — working notes for Claude Code

Scope: things that are easy to get wrong here and are not obvious from the
code. This is deliberately not a codebase tour.

## Linting: the contract

CI runs **two** gates (`.github/workflows/ruff.yml`): `ruff check` **and**
`ruff format --check`. A green `check` does not mean the lint job passes —
that mistake has shipped a red main more than once.

Locally, match CI exactly with the pinned version rather than whatever is in
the venv:

```
uvx ruff@0.16.5 check .
uvx ruff@0.16.5 format --check .
```

**`select` is pinned explicitly** in `[tool.ruff.lint]`. This is the load-
bearing decision in the whole setup. Ruff's implicit default is not a
constant — between 0.15.21 and 0.16.5 it grew from 59 enabled rules to 414,
which is why an unpinned bump used to turn CI red on unchanged code. With
`select` written down, a bump changes how a rule *behaves* but never *which*
rules run.

Consequences:

- **Bumping ruff is now cheap** — the two `version:` fields in `ruff.yml`.
  It is not the repo-wide cleanup the old comments implied.
- **Adding a rule is a deliberate edit** to `extend-select`, never a side
  effect of a version bump.
- **Formatting is NOT governed by `select`.** After a bump, re-run
  `ruff format` and take the diff. Ruff 0.16 added Markdown to the
  formatter's scope, so a bump can reformat `.md` files that no earlier ruff
  touched (0.16.5 formats 528 files here; 0.15.21 formats 404).

### `unfixable = ["F401", "RUF100"]` must stay

Both rules' autofixes destroy information.

- `F401` — a multi-pass edit that adds an import before the code using it
  gets the import deleted in between by format-on-save or an auto-fix hook.
- `RUF100` — its fix deletes the **whole comment, prose included**. A
  directive like `# noqa: PLC0415 — optional extra, imported on use` is
  documentation of *why* an import is lazy. Worse, RUF100 reads a rule's
  annotations as dead whenever that rule is not *currently* selected, so a
  `--fix` run before adopting a rule deletes exactly the annotations that
  were the argument for adopting it.

When auditing dead directives, measure with **`--extend-select RUF100`**, not
`--select RUF100`. The latter *replaces* the rule set, so every directive
naming a now-unselected rule reads as unused.

### Rules deliberately not selected

- **`PLC0415` (import-outside-top-level)** reports **940** violations,
  because lazy imports are an architectural choice here (startup cost). The
  rule contradicts the design rather than finding bugs. Two annotated sites
  survive in `vna.py` as prose; they are documentation, not suppression.
- **`E741`** is in `ignore`: 33 sites, all `I` (current) and `l` (length /
  inductance), which are the correct physics names.

`BLE001` **is** selected repo-wide: a new `except Exception` fails lint until
it carries `# noqa: BLE001 — <reason>`.

`scratch/` is linted on purpose (not excluded): the study scripts under it are
the record of what produced a published number, and a record worth keeping is
worth keeping readable.

## Two repos, one working tree

`momwire/` is a git submodule with **its own** ruff config, excluded here via
`extend-exclude`. Two hazards follow:

- **Never `git add -A`.** It sweeps the momwire submodule pointer (kept
  intentionally modified during development) and untracked `scratch/*.jsonl`
  into the commit. Stage explicit paths.
- **Always pass `gh -R <owner>/<repo>`.** The two repos have overlapping
  issue numbers and the shell's cwd persists across calls, so a bare
  `gh issue` can land on the wrong tracker.

## Frontend

The app's frontend is `src/antennaknobs/web/frontend/` (Vite + React).
`site/` is a separate Astro marketing site — greps there return misleading
zeros when you meant the app.
