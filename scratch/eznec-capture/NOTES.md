# EZNEC capture session — 2026-08-20 (momwire#456, Target 1)

Ground-type cycle on `Vert1`, closing the 2026-08-16 capture doc's "perfect ground
and MININEC-type ground unsampled" gap. I/O observation only; no interpretation of
results here — that belongs against the oracle.

**Captures `0043`–`0048`.** Harness: `scripts/eznec_spy`, shim rebuilt from source
this session (capture root baked to `scratch/eznec-capture`), installed 08:12 local,
uninstalled 08:24 with the hash-verify passing. Engine restored to its original
10,804,224 bytes / Aug-16 mtime, no `.real.exe` residue.

Model `C:\EZNEC 7.0\Docs\Ant\Vert1.ez` — `CM Vertical over real ground`, a single
`GW 1,10,0.,0.,0.,0.,0.,10.3,.02`. Engine `External NEC-5`, invoked argv-form as
`"…\NEC5CL_x13.exe" "EZN5.NEC" "NEC5.OUT"`, cwd `C:\EZNEC 7.0\Docs`, stdin unused,
exit 0 throughout.

## What was clicked, in order

| # | capture | ground setting | click | `FR` | ground card | request tail | ms | printout |
|---|---|---|---|---|---|---|---|---|
| 1 | — | Free space | Src Dat | — | — | — | — | **refused, no launch** |
| 2 | — | Free space | FF Plot | — | — | — | — | **refused, no launch** |
| 3 | `0043` | Perfect | Src Dat | `7.` | `GN 1` | `XQ 0` | 118 | 6,904 B |
| 4 | `0044` | Perfect | FF Plot | `7.` | `GN 1` | `RP 0,181,1,1000,90.,0.,-1.,0.,0.` | 21 | 29,443 B |
| 5 | — | Real/MININEC | Src Dat | — | — | — | — | **skipped launch** |
| 6 | `0045` | Real/MININEC | FF Plot | `7.` | `GD 0,0,0,0,13.,.005,1.,0.` | `RP 0,181,1,1000,90.,0.,-1.,0.,0.` | 30 | 29,851 B |
| 7 | — | Real/MININEC | Src Dat (retry, window closed first) | — | — | — | — | **skipped launch** |
| 8 | `0046` | Real/MININEC | Src Dat (after `FR` nudge) | `7.01` | `GD 0,0,0,0,13.,.005,1.,0.` | `XQ 0` | 19 | 7,312 B |
| 9 | `0047` | Real/High Accuracy | FF Plot | `7.` | `GN 0,0,0,0,13.,.005,1.,0.` | `RP 0,181,1,1000,90.,0.,-1.,0.,0.` | 122 | 29,944 B |
| 10 | — | Real/High Accuracy | Src Dat | — | — | — | — | **skipped launch** |
| 11 | `0048` | Real/High Accuracy | Src Dat (after `FR` nudge) | `7.02` | `GN 0,0,0,0,13.,.005,1.,0.` | `XQ 0` | 101 | 7,405 B |

Launch accounting: `LastRun.log` ended with **6** `Running ext engine` lines against
**6** capture directories. Every launch is accounted for and no capture is missing.

## Ground card per menu setting

The card each menu setting emits, payload verbatim, same model and same session:

| menu setting | emitted ground card |
| --- | --- |
| Free space | *(not obtainable on this model — see anomaly 1; `GN -1` elsewhere in corpus)* |
| Perfect | `GN 1` |
| Real / MININEC type | `GD 0,0,0,0,13.,.005,1.,0.` |
| Real / High Accuracy | `GN 0,0,0,0,13.,.005,1.,0.` |

The MININEC decks (`0045`, `0046`) carry a `GD` card and **no `GN` card at all**.
Stated as an observation about the emitted bytes, not a claim about what it means.

This settles a `GD`-vs-`GN 0,…` ambiguity the earlier Vert1 captures left open:
`0015` emitted the bare `GD` form and `0021`/`0022` the `GN 0,…` form, with no record
of which menu setting produced which.

## Anomalies

1. **Free space is unrunnable on this model.** Both clicks raised EZNEC's
   "sources incorrectly placed" popup. `LastRun.log` records `MM SD` / `MM CR` with
   no `Running ext engine` between them — EZNEC refused at its own validation stage,
   nothing crossed the process boundary, no deck was emitted. Not a harness failure,
   and not a coverage loss: free space (`GN -1`) is already sampled 14× in this
   corpus.
2. **Src Dat skipped its launch on both real-ground settings** — twice under
   MININEC (plain click, then again after closing and reopening the Src Dat window)
   and once under High Accuracy. Under perfect ground the same click launched
   normally. In each skip `LastRun.log` shows `MM SD` … `MM Done SD` with no launch.
   The README's documented remedy worked both times: nudge `FR` so the model leaves
   an already-computed state, then click again.
3. **Consequence of that remedy:** `0046` sits at 7.01 MHz and `0048` at 7.02 MHz,
   so neither is byte-comparable to its FF Plot partner — they differ in `FR` as well
   as the request tail. `0043`/`0044` (perfect ground) *are* a clean pair: byte
   identical apart from timestamp and tail.
4. **Ground-contact warning on selecting Real/High Accuracy** — advisory, not
   blocking; the run proceeded and captured. The engine's own printout in `0047`
   echoes the same caveat verbatim:
   `WHERE WIRE ENDS TOUCH GROUND, CURRENT WILL BE INTERPOLATED TO IMAGE IN GROUND PLANE.`
   followed by `Will compute Sommerfeld-ground tables` /
   `FINITE GROUND.  SOMMERFELD SOLUTION`.
5. **The capture doc's premise was partly stale.** Perfect ground was *not*
   unsampled — `GN 1` already appears in captures `0019` (Vert1), `0027` and `0032`.
   What today's run adds there is the first perfect-ground *pattern* deck on this
   model; `0019` was Src Dat (`XQ 0`) only. MININEC-type was a genuine gap.
