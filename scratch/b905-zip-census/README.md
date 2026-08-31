# B905 zip census — deciding 171 sites with evidence instead of reading

Record of how [#1061](https://github.com/stevenmburns/antennaknobs/issues/1061)
was decided. Kept because the numbers below are the argument for the
`strict=` value at every site, and a claim you cannot re-derive is a claim
nobody can check.

## The problem

`B905` flags every `zip()` without an explicit `strict=`. There were **171**.
Each needs a real decision — `strict=True` says a length mismatch is a bug,
`strict=False` says truncation is intended — and in this codebase getting it
wrong is expensive: a mismatch between, say, segments and currents is not a
crash, it is a shorter answer that still looks like an answer.

Reading 171 sites and judging each is slow and unverifiable. So don't read
them: **watch them run.**

## The instrument

`sitecustomize.py` replaces `builtins.zip` with a wrapper that records the
caller's `file:line` and whether the arguments had equal `len()`, then returns
the **real, non-strict** `zip`. Behaviour is completely unchanged, so nothing
breaks and one run yields a complete census rather than stopping at the first
raise. Arguments without `__len__` are counted separately rather than
materialised, so generators are never consumed.

```
PYTHONPATH=scratch/b905-zip-census \
ZIPCENSUS_ROOT=$PWD \
ZIPCENSUS_OUT=scratch/b905-zip-census/census.json \
  .venv/bin/python -m pytest -m "not heavy_mesh" -q tests/
```

`census.json` is the run banked here: 3,890 tests passed, 109 in-repo sites
observed.

## What it found

| bucket | sites | decision |
|---|---|---|
| observed, always equal | 93 | `strict=True`, verified by execution |
| observed, ever unequal | 16 | all one idiom — see below |
| never executed | 62 | read individually; all parallel-by-construction |

**Every observed mismatch was N vs N−1, and every one was `zip(xs, xs[1:])`** —
the successive-pairs idiom, which is definitionally off-by-one and can never
take `strict=True`. So they were not 16 judgments but one, and the right fix
was not `strict=False`: `RUF007` flags exactly this shape, and
`itertools.pairwise(xs)` removes the `zip` entirely, so the finding disappears
instead of being suppressed. Both rules are now selected.

One site needed a real decision, and the suite found it rather than a reviewer:
`wire_catalog.py:428` zipped **three** operands, `(cuts, cuts[1:], counts)`, so
`pairwise` did not drop in and the mismatch was hidden behind the third
argument. It is now
`zip(itertools.pairwise(cuts), self.counts, strict=True)`, which turns a silent
truncation into a checked invariant — `counts` must have exactly one entry per
interval.

## Two traps worth not re-discovering

**B905's autofix inserts `strict=False`.** It is offered only under
`--unsafe-fixes`, and it preserves current behaviour — running it would silence
all 171 findings while changing nothing, locking in precisely the truncation
the rule exists to catch.

**The asymmetry is what makes the whole approach safe.** A wrong `strict=True`
raises, and the suite catches it. A wrong `strict=False` is silent, and nothing
does. So `True` is the default and `False` has to be argued per site — the
opposite of what the autofix does.

## Coverage, stated honestly

The census only sees what runs. 62 of the 171 were never executed — 52 in
`scratch/` and `scripts/`, which CI never runs, plus a handful in `src/` and
`tests/` (two of those only because the `zip` sits inside an
`assert ..., dict(zip(...))` message, evaluated only on failure). Those were
decided by reading, and none was an intentional truncation, but they carry
weaker evidence than the 93 and should be treated that way if one ever raises.
