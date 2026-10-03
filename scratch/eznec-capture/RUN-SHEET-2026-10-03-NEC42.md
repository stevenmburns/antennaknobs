# EZNEC capture sitting: the External NEC-4.2 slot (momwire#1295)

Captures continue at **`0219`**. Corpus is `0000`–`0218` today.

**Goal of this sitting:** the decks EZNEC's **External NEC-4.2** slot writes, and how it calls the engine. That is the input dialect for `momwire-nec4*`. The printout layout comes later, in two steps:
- On the laptop, the licensed NEC-4.2 solves these captured decks.
- A second sitting replays those printouts to EZNEC to see what it accepts.

**If you only have time for one item, do items 0–2.**

## Setup (the Windows-builder session does this before you start)

There is no real Windows NEC-4.2 engine on this box, and the spy shim refused to capture without one (`NOTES.md`, "How each was obtained"). The session adds a **capture-only mode** to `scripts/eznec_spy/Nec5Spy.cs`:
- With no `<name>.real.exe` beside it, the shim records argv, cwd, stdin and the files before and after, plus a copy of the deck.
- It then writes nothing and exits 0.
- EZNEC will report "Unable to read NEC output file". **That is expected this sitting.**

It then installs the shim at a path whose name carries `nec4`, e.g. `C:\EZNEC 7.0\Docs\momwire-nec4-capture.exe`.

In EZNEC: **Options → Calculating engine → External NEC-4.2**, then browse to that exe.

Things that cost clicks before:
- **The engine selection lives in the `.ez`, per model.** Re-set it every time you open a model. Skipping it gives a normal result and *no capture*.
- **One EZNEC instance only**, or the captures interleave.
- The 4.2 slot writes **`EZ.NEC` in the ENGINE's folder** (not `Docs\EZN5.NEC` as the NEC-5 slot does). The shim copies it per run, so nothing gets overwritten.

For each item: set the engine, click **FF Plot once** (or the sweep where it says so), and tick the box. One click is one capture.

## Item 0: the call itself (Dipole1, as shipped)
- [ ] `Dipole1.ez`, free space, voltage source, **FF Plot once**.

  The session reads, and tells Claude:
  - the argv form (two paths? which names?);
  - the deck's file name and folder;
  - the output file name EZNEC expects (`NEC.OUT`?);
  - any stdin or console use;
  - the exit code EZNEC tolerates.

## Item 1: current source (the `EX 6` of the QRZ #71 report)
- [ ] `Dipole1.ez`, change the source to **current** (Sources window: type I), **FF Plot once**.

## Item 2: loads
- [ ] `Dipole1.ez` + an **R+jX load** (R = 50, X = 0) at **wire 1, 25 %**, FF Plot once.
- [ ] Same model, load changed to **RLC, series, R = 18, L = 1 µH, C = 0**, FF Plot once. (A probe `EX` per load?)
- [ ] `Dipole1.ez`, no loads, **Wire Loss = Copper**, FF Plot once. (LD 5?)

## Item 3: grounds (Dipole1 raised to 10 m, horizontal)
- [ ] Ground **Perfect**, FF Plot once.
- [ ] Ground **Real, MININEC**, average soil (13 / 0.005), FF Plot once.
- [ ] Ground **Real, High Accuracy**, same soil, FF Plot once.
- [ ] If the 4.2 slot offers a **GN 3** or a "NEC-4.2 ground method" choice anywhere, one capture of each setting, with a note of where you found it.

## Item 4: frequency sweep
- [ ] `Dipole1.ez`, **SWR sweep, 3 points** (e.g. 13.9 / 14.0 / 14.1 MHz). Note: one capture per frequency, or one deck with an `FR` loop?

## Item 5: transmission lines and networks
- [ ] `Cardioid L Network Feed ARRL Example.ez`, FF Plot once. (TL ×2, NT ×1 in the NEC-5 slot.)
- [ ] `4sqtl.ez` if present, FF Plot once.

## Item 6: patterns
- [ ] `Dipole1.ez`, **3D plot**, once.
- [ ] `Dipole1.ez`, **2D elevation only**, once.

## Item 7 (optional): ground contact
- [ ] A ground-mounted vertical with buried radials (Dan's `Buried-radials` model if you have the `.ez`), FF Plot once.

  Does the 4.2 slot accept wires below ground? Note any EZNEC error before the launch.

## After the sitting
The session commits the captures (as in earlier sittings) and runs `index_captures.py`. The laptop then:
- tabulates the NEC-4.2 slot's card vocabulary into #1295;
- solves each captured deck on the licensed NEC-4.2 (black box) to get the target printouts;
- prepares the **replay** sitting, where the shim hands each recorded printout back to EZNEC to confirm what its NEC-4 reader accepts.
