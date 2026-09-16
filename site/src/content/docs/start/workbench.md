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
   releases before v0.73.0 shipped the Python package only). The release also
   carries `antennaknobs-workbench-windows-v<version>.zip`: the same file,
   named with its version so a saved copy says which release it is. The
   version-less name is what keeps the link above pointing at the newest
   release, so either download is fine.
2. Unzip it anywhere. **Keep the folder together** — the exe needs the
   `_internal` runtime beside it, and a lone copied-out `.exe` is the one way
   a correct download still fails.
3. Double-click `antennaknobs-workbench.exe`. A console window opens, the
   server starts on this computer at `http://127.0.0.1:8000`, and your browser
   opens at it.

Keep the console window open while you work; closing it, or Ctrl-C, stops the
server. Nothing is installed and nothing is written outside the folder —
delete the folder to remove it. The server listens on `127.0.0.1` only, so
nothing on your network can reach it.

The page shows the running version just below the bold "AntennaKNoBs" in the
upper left, so you can always tell which release you launched. **To update to
a new release, extract the whole new zip into a fresh folder rather than
copying just the `.exe` over an old one** — the exe runs whatever `_internal`
sits beside it, so a copied-in `.exe` next to an old `_internal` runs the old
code under the new file name, with no sign of that beyond the version shown
on the page and in the console's startup line.

First launch takes appreciably longer than the rest: Windows scans the
unpacked folder once. Measured on a laptop, the self-test ran 17.7 s cold and
2.2 s warm, and the warm number is the one you live with.

Options, from a PowerShell or Command Prompt window in the folder:

```text
antennaknobs-workbench.exe --port 8123       serve somewhere else
antennaknobs-workbench.exe --no-browser      print the URL only
antennaknobs-workbench.exe --selftest        prove the bundle and exit
antennaknobs-workbench.exe --nec5-exe PATH   use the NEC-5 engine at PATH
antennaknobs-workbench.exe --nec2-exe PATH   use the NEC-2 engine at PATH
antennaknobs-workbench.exe --settings PATH   start from this settings.toml
```

A `settings.toml` sets where the workbench starts: its switches, ground,
solver slots and engine paths. See [Where the workbench starts](/reference/web/#where-the-workbench-starts-settingstoml).

The port is worth leaving alone. Your browser keeps what *it* remembers about
the workbench — which views are pinned to the rail, rail or grid, light or
dark — against the address it visited, and the address is the port. Launching
on 8000 every time is what carries those across restarts. If something else on
the machine already holds 8000, the workbench takes a free port instead and
the console says so; that window starts with the default rail.

`--selftest` is worth running once if you are unsure the download is intact:
it solves a known antenna and checks the answer against the value the
unfrozen package produces, then exits.

## A shortcut for each way you work

Each settings file is one way of starting, so two shortcuts can start the
workbench two ways. Say one run should leave every engine deck and printout
in a folder with the frequency sweep off, and the other should sweep and
capture nothing. Keep the everyday settings in `settings.toml`, and write the
other way into a second file beside it, `capture.toml`:

```toml
[switches]
freq_sweep = false

[capture]
dir = 'C:\ak-captures'
```

Then make a shortcut that starts from it:

1. Right-click `antennaknobs-workbench.exe` and choose **Send to → Desktop
   (create shortcut)**. On Windows 11, **Send to** is under **Show more
   options**.
2. Right-click the new shortcut, choose **Properties**, and at the end of the
   **Target** box type a space and
   `--settings "C:\Users\you\.antennaknobs\capture.toml"`, with your own user
   folder in place of `you`.
3. Rename the shortcut to say which it is, such as `antennaknobs (capture)`.

A second shortcut made the same way, without the flag, starts from
`settings.toml`. The capture folder is created on the first run, and the
console window's startup summary names the settings file each shortcut
started from. *Save as my defaults* writes to that same file, so each shortcut
keeps its own defaults. An `[engines]` table serves only the file it is in,
while a `NEC5_EXE.txt` beside the program serves both shortcuts.

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
console binary on one line in `NEC2_EXE.txt` beside the executable (or start
with `--nec2-exe PATH`, or set `NEC2_EXE`), and antennaknobs drives it as a subprocess —
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

If you start the workbench from a window rather than by double-clicking, you
can name the engine on the command line instead. The flag reads the same in
PowerShell and Command Prompt, and wins over the file:

```text
antennaknobs-workbench.exe --nec5-exe "C:\EZNEC 7.0\Docs\NEC5CL_x13.exe"
```

The `NEC5_EXE` environment variable works too: it wins over the file and
loses to the flag. So does `nec5_exe` under `[engines]` in
[`settings.toml`](/reference/web/#where-the-workbench-starts-settingstoml), which loses to the variable and wins over
`NEC5_EXE.txt`.

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
