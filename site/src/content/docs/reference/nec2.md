---
title: NEC-2 as an external engine
description: Point antennaknobs at a NEC-2 console binary you already have — nec2c, nec2++ or 4nec2's nec2dxs — and get NEC-2 physics without a GPL library in the install.
---

antennaknobs has had NEC-2 physics from the start, through the optional
`pynec-accel` package and the [PyNEC engine](/reference/solver/). What it
could never do is **ship** it. `pynec-accel` wraps nec2++, which is GPLv2,
so putting it inside a distributed artefact — the frozen Windows workbench,
the published Docker image — would make that artefact a combined work with
the source-offer and notice obligations that carries. The published image
has always been built `INCLUDE_PYNEC=0` for exactly this reason.

So there are now two ways to reach NEC-2, and they differ only in the
coupling:

| | how it is reached | what antennaknobs distributes |
|---|---|---|
| `pynec` | linked into the process, via `pip install pynec-accel` | nothing; you install it |
| `nec2` | a console binary you own, run as a subprocess | nothing at all |

The second is the shape the [NEC-5 engine](/reference/nec5/) already proved:
a deck written to a temporary directory, your executable run over it, its
printout parsed back into the same impedance, current and pattern readouts
every other engine serves. Text in, text out, nothing linked — so a bundle
can offer NEC-2 without inheriting its licence.

**You very likely already have a binary.** 4nec2 installs a console NEC-2 as
`nec2dxs*.exe` beside its GUI; `nec2c` is in most Linux distributions'
package repositories; `nec2++` is a free download.

## Pointing at it

One environment variable:

```bash
export NEC2_EXE=/usr/bin/nec2c
antennaknobs sweep dipoles.invvee --engine nec2
```

On Windows, in the same PowerShell window that starts the workbench:

```powershell
$env:NEC2_EXE = "C:\4nec2\exe\nec2dxs11.exe"
```

And for someone who double-clicks the workbench rather than typing a
command, a one-line text file `NEC2_EXE.txt` beside
`antennaknobs-workbench.exe` holding the path does the same. The variable
wins when both are set.

`nec2` joins the engine roster only when the binary **runs** — not merely
when the path exists. The engine writes a one-wire deck, runs it once, and
requires a parseable printout back. That is deliberate and was learned the
hard way on the NEC-5 lane: a variable pointing at the wrong executable used
to produce an engine tab that failed only at the first solve, with the wrong
program's error text. A path is a fact about your filesystem; being a NEC-2
is not.

## Two command lines, and why you do not have to say which

There is no single NEC-2 invocation. `nec2c` and `nec2++` take the file names
as arguments:

```
nec2c -i model.nec -o model.out
```

while 4nec2's `nec2dxs*.exe` reads the input and output file names from
standard input, the way NEC-5's `NEC5CL` does. antennaknobs tries the
argument form, then the standard-input form, and remembers which one your
binary answered — keyed on the file itself, so replacing it in place is
noticed. **The choice is never made from the file name**, because a renamed
binary, a wrapper script and a symlink are all ordinary things.

A build that writes its report to standard output instead of to the named
file works too. That is a working NEC-2, and treating it as a failed run
would be our bug, not yours.

## What it refuses, and why that is the point

The engine refuses three geometries **by name**, before your binary sees
them:

- a wire **below** the ground plane;
- a wire **crossing** the plane mid-span;
- a wire **lying in** the plane, where its own image coincides with it.

The first two matter more than they look. NEC-2's ground is a boundary
condition on the fields above it — there is no below-ground medium in the
formulation at all. Handed a buried wire, nec2++ does not complain: it
solves the wire **as if it were in air** and prints a number. For an engine
you are using as a cross-check, a confident wrong answer is the worst
possible failure, so the wrapper declines rather than pass it on. For buried
conductors use the momwire engine, whose buried serve is certified, or
NEC-5, whose Sommerfeld path serves them.

In free space there is no plane and nothing to refuse: a free-space model may
sit anywhere, `z = 0` and below included.

Two more refusals come from the deck itself, and both are shared with the
`.nec` download button, because they come from the same writer:

- **graded meshes** (the per-edge segment spelling) — a card deck numbers
  wires by tag, and expanding a graded wire into several cards would shift
  every `EX` / `LD` / `NT` reference that names one;
- **TL and virtual-driver networks** — the PyNEC engine solves those by a
  multiport-Y reduction outside the field solve, and there is no faithful
  single-deck spelling of that. A design `pynec` serves and `nec2` refuses is
  almost always this one.

## The deck is the download button's deck

`nec2` does not have a deck writer of its own. It uses
`antennaknobs.nec_export.export_nec` — the module behind **Download .nec** —
so the deck your binary runs is the same text you would have downloaded, wire
tuple for wire tuple. That is not a convenience: a second writer is how the
two would drift apart, and the drift would show up looking like an engine
disagreement rather than like a bug in one of ours.

It also means a `nec2` result is reproducible by hand. Download the deck, run
your own binary over it, and you should get the printout antennaknobs parsed.

## What to expect from the numbers

`nec2` and `pynec` are the same code family reached two ways, so on a design
both serve they should agree closely — nec2c and nec2++ are independent
implementations of one formulation, and a few tenths of a percent is the
normal spread. A larger gap is worth reading as a finding rather than noise:
the [solver page](/reference/solver/) is how antennaknobs treats
cross-engine differences generally.

Against **momwire** or **NEC-5** the spread is a formulation difference, not
an error in either. That is the whole reason for having three.
