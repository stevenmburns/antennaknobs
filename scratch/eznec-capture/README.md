# EZNEC capture corpus

Each capture is one EZNEC run: the deck EZNEC wrote, the command line it
used, and the metadata in `index.json`.

## The printouts are not stored, deliberately

`index.json` names a `printout` for every capture. That field records **what
EZNEC wrote at capture time** — it is not a path to a file in this repo.

The `.OUT` files are licensed NEC-5 engine output, and they are *derived*: the
deck in the same capture directory, pushed through the licensed engine,
reproduces one exactly. Storing them banked 12 MB of another vendor's engine
output in a public repository to avoid a re-run, which momwire#553's standing
rule already argues against — the licensed engine enters as a data oracle, and
public artifacts carry conclusions rather than its tables.

They are ignored (see the repository `.gitignore`) so a wide `git add` cannot
bank them again. They remain in git history prior to their removal.

## Regenerating one

Run the capture's own deck through the licensed engine with the command line
`index.json` records for it. Nothing in this repository reads a `.OUT`:
`scripts/eznec_serve_sweep.py`, the only consumer of this corpus, reads the
**deck** and pushes it through `momwire.eznec.render`.

## What is deliberately kept

The decks. They are the input, they are ours, and they are what every gate and
sweep actually consumes — a capture without its printout is still a complete
test case.
