---
title: The Windows workbench
description: Download antennaknobs as a single Windows folder — no Python, no install. Double-click, and the workbench opens in your browser.
---

The workbench is antennaknobs packaged for Windows: the same program as
`pip install "antennaknobs[web]"`, frozen with its interpreter and its
compiled solver so there is nothing to install. Download, unzip,
double-click.

## Setting it up

1. Download `antennaknobs-workbench-windows.zip` from the
   [latest release](https://github.com/stevenmburns/antennaknobs/releases/latest)
   (the direct link is
   [releases/latest/download/antennaknobs-workbench-windows.zip](https://github.com/stevenmburns/antennaknobs/releases/latest/download/antennaknobs-workbench-windows.zip);
   releases before v0.73.0 shipped the Python package only).
2. Unzip it anywhere. **Keep the folder together** — the exe needs the
   `_internal` runtime beside it, and a lone copied-out `.exe` is the one way
   a correct download still fails.
3. Double-click `antennaknobs-workbench.exe`. A console window opens, the
   server starts on this computer, and your browser opens at it.

Keep the console window open while you work; closing it, or Ctrl-C, stops the
server. Nothing is installed and nothing is written outside the folder —
delete the folder to remove it. The server listens on `127.0.0.1` only, so
nothing on your network can reach it.

First launch takes appreciably longer than the rest: Windows scans the
unpacked folder once. Measured on a laptop, the self-test ran 17.7 s cold and
2.2 s warm, and the warm number is the one you live with.

Options, from a PowerShell or Command Prompt window in the folder:

```text
antennaknobs-workbench.exe --port 8000       a fixed port
antennaknobs-workbench.exe --no-browser      print the URL only
antennaknobs-workbench.exe --selftest        prove the bundle and exit
```

`--selftest` is worth running once if you are unsure the download is intact:
it solves a known antenna and checks the answer against the value the
unfrozen package produces, then exits.

## Adding your NEC-5 engine

The workbench solves with momwire out of the box. If you own a licensed
NEC-5 engine it can drive that too, as a second engine beside momwire — see
[NEC-5 as a third engine](/reference/nec5/) for what that buys you (the
workbench folder carries momwire; the PyNEC engine of the pip install is
not in it). antennaknobs never bundles, downloads, or hosts the engine.

Put the engine's full path on one line in a text file named `NEC5_EXE.txt`
beside `antennaknobs-workbench.exe`, then start the workbench again. The
NEC-5 tab appears in the solver panel.

## Adding a NEC-2 engine

The same door, for an engine you may already own: put the path to a NEC-2
console binary on one line in `NEC2_EXE.txt` beside the executable (or set
`NEC2_EXE` before starting), and antennaknobs drives it as a subprocess —
see [NEC-2 as an external engine](/reference/nec2/). 4nec2 installs one as
`nec2dxs*.exe`; `nec2c` and `nec2++` are free. No NEC-2 is bundled on
purpose: nec2++ is GPLv2, and shipping it would change this download's
licence.

The NEC-2 tab appears in the solver panel the same way the NEC-5 one does, and
`--engine nec2` reaches the same engine from the command line.

**If you run EZNEC Pro+, the engine is already on your disk.** EZNEC keeps it
in its `Docs` folder — not under `Program Files`, where people look first —
and the filename carries a build suffix, so it is `NEC5CL_x13.exe` rather
than a bare `NEC5CL.exe`. Look for:

```text
C:\EZNEC 7.0\Docs\NEC5CL_*.exe
```

and copy the name you actually find. If you are not sure which engine EZNEC
is driving, open `Docs\LastRun.log` — EZNEC records every run there as
`Running ext engine <full path>`, which is the path to paste.

The `NEC5_EXE` environment variable works too and wins over the file; that is
the form to use if you are starting the workbench from a shell rather than by
double-clicking.

## When you want the Python package instead

The workbench is the no-install path. If you want antennaknobs as a library —
to write your own designs, script a sweep, or run the CLI — install the
package and follow the [Quickstart](/start/quickstart/) instead. The two are
the same code; only the packaging differs.

## For the NEC-5 working group: the corpus tool

The NEC-5 regression-corpus tool (`scripts/nec5_corpus/` in the repository:
fetch the public NEC-2 decks, translate them for NEC-5, run them through
your engine, compare two runs) is **not** in the workbench. It is published
on its own, as a signed `nec5_corpus-windows.zip` under a release tag of its
own, `nec5-corpus-v<version>`; the newest is at the top of
[the tool's release list](https://github.com/stevenmburns/antennaknobs/releases?q=nec5-corpus&expanded=false).
Unzip it and read the README.txt inside; it runs without Python, and anyone
with a working Python 3.8 or newer can run the script itself instead. A
security review of the script ships in the zip beside the exe and the
release notes carry the checksums. It is
rebuilt when the tool changes, not with every antennaknobs release.
