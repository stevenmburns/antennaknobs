# The live SimNEC session ritual (issue #804)

Everything in `antennaknobs.nec_portal` is bench-tested against committed
oracle printout (32/32 byte-layout, differential harness green). What has
never happened is a real SimNEC session driving the momwire engine end to
end. This is the script for that session. Run it at the box with SimNEC
installed; record the outcome in the table at the bottom. **This is the last
gate before the notes in `2026-08-08-ward-simnec-momwire-notes.md` go out.**

## 0a. Running this on a Windows box instead

The ritual works unchanged on any machine with SimNEC — and Windows is
arguably the stronger test (SimNEC's user base, the `cmd.exe /c` launch
path, CRLF through `Execute.readLine()`). Windows translation of the setup:

```bat
py -3.12 -m venv %USERPROFILE%\momwire-portal
%USERPROFILE%\momwire-portal\Scripts\pip install https://github.com/stevenmburns/antennaknobs/archive/refs/heads/main.zip
%USERPROFILE%\momwire-portal\Scripts\momwire-nec2c.exe -version
%USERPROFILE%\momwire-portal\Scripts\momwire-nec2c.exe --selftest
```

(momwire ships `win_amd64` wheels for CPython 3.10–3.14; the zip install
needs no git client; the `.exe` name still contains `nec2c` so the portal's
filename check passes.) `--selftest` replaces the bash smoke script — it
needs no checkout: it spawns one resident copy of itself, runs three
embedded decks (plain dipole, two-source Y probe, TL station) down the one
process, and PASSes only if every solve answered with its NX sentinel. In
step 1, paste the full `...\Scripts\momwire-nec2c.exe` path into the portal
dialog; SimNEC's per-user state lives under `%USERPROFILE%\.SimNEC`. If the
box has less RAM than 16 GB, drop `necCrewSize` accordingly (~90 MB per
resident engine before solve data). Everything from step 2 on is identical.

## 0. Pre-flight (no GUI needed)

```bash
cd ~/antennas/antennaknobs
bash scripts/nec_portal_smoke.sh          # must say PASS
.venv/bin/python -m antennaknobs.nec_portal -version   # nec2c.ae6ty.9.1
ls -la .venv/bin/momwire-nec2c            # the script SimNEC will run
```

If `momwire-nec2c` is missing, the editable install predates the entry
point: `.venv/bin/pip install -e . --no-deps` once, then re-check.

## 1. Point SimNEC at momwire

Launch SimNEC (`/home/smburns/SimNEC/SimNEC`). Open **view → NEC2 Portal**.
Note the current `necCommand` (write it down — this is the revert path),
then click the field and select:

```
/home/smburns/antennas/antennaknobs/.venv/bin/momwire-nec2c
```

Expected: SimNEC accepts it (the filename contains `nec2c`; the `-version`
probe answers `nec2c.ae6ty.9.1`, above its 1.23 floor). The portal dialog
should display the probe string. If it refuses with "version too old" or
"NO NEC SERVICE FOUND", capture the exact message — that's a finding, not a
failure to shrug at.

Set `necCrewSize` to **4** (momwire processes are faster but heavier than
nec2c's; 16 Python+numpy residents on a 16 GB box is asking for trouble).

## 2. The session

Use the ladder-tuner circuit from the .ssn round-trip validation
(`~/antennas/simnec_696_validation/doublet_ladder_tuner.ssn`) — its
correct answer is already known from three sources (our engine, SimNEC's
MNA over its own nec2c, and the antennaknobs workbench).

1. **Load it.** The NEC block should solve on momwire. Rig-side Z at
   7.1 MHz should land near **41.9 − j5.8 Ω** (the Track-1 number; a few
   percent of drift vs the nec2c-backed session is the cross-basis gap the
   differential harness bounds at ≤ ~3%).
2. **Turn a knob** (a tuner cap). The readout must track — this exercises
   the resident-process loop under SimNEC's own cadence, which no bench
   test reproduces.
3. **Run a frequency sweep.** Watch for: both progress wheels behaving,
   no stalls (a stall = the sentinel contract failed under some deck we
   never captured — grab `~/.SimNEC/…/badNEC.nec` if SimNEC writes one),
   and a smooth SWR curve.
4. **Open the NEC display** and look at the far-field pattern. Shape
   should match the antennaknobs workbench's pattern for the same design;
   absolute dB should agree within ~0.3 dB (bench-measured worst 0.12).
   If the absolute level is off by exactly the antenna's efficiency,
   that's the FieldStore gain-vs-directivity question (#803) answering
   itself — record the number.
5. **Multi-feed check.** Load any 2+ source design (or the jar's own test
   circuit): per-source runs are where one-fill-N-sources pays off; verify
   the Y-driven readouts look sane and nothing hangs between XQ groups.
6. **Abuse it once.** Load a design the portal refuses (anything with
   surface patches, or a GN radial screen). SimNEC must show an engine
   error and stay alive — not hang. This validates the error path + NX
   sentinel under the real parser.
7. **Revert** `necCommand` to the bundled nec2c and confirm SimNEC still
   works (leave no surprises for the next session).

## 3. Record the outcome

| Step | Result | Notes |
| --- | --- | --- |
| Pre-flight smoke | **PASS** | `--selftest` 8/8, after the EK fix (PR #814) |
| Portal accepts command + version | **PASS** | `nec2c.ae6ty.9.1` accepted, above the 1.23 floor |
| Ladder tuner Z @ 7.1 MHz | **42.56 − j4.765** | vs ~40 − j5.7 nec2c-backed; few-% through the high-Q tee |
| Knob tracking | **PASS** | |
| Sweep completes, no stalls | **PASS** | (first run slowed by nec logging — that was the log, not the engine) |
| Pattern shape / level | **PASS** | 2.431 dBi / 2.044 dB split = 0.387 dB = the coil-loss efficiency (ours: 0.378 dB) — #803 empirically resolved |
| Multi-source design | **PASS** | SimNEC's own `lindenblad.ssn` (4 quadrature sources): momwire 27 − j4 vs nec2c 27 − j3. (Our w8jk export exposed exporter gap #815, not an engine fault: live 384.7 + j505.3 = in-phase drive, predicted 379.3 + j504.8 from our own Y.) |
| Refusal stays alive | **PASS with a finding** | patch deck: session healthy, doublet loaded fine after — but the refusal was SILENT in the UI (→ Ward ask 2) |
| Reverted cleanly | **PASS** | nec2c re-verified on the lindenblad |

**Session date: 2026-08-08, Windows box, SimNEC 5.1a0, crew 4.** Live
discoveries: `EK` sent unconditionally by `NECSource` (fixed same-day,
PR #814, selftest now gates on it); `GD` + `RP 3` in EZNEC-derived examples
still refused (cardioid / 4-square blocked; GD fix has since landed —
grammar doc §18, selftest now gates on it too; RP 3 = #802);
multi-feed `.ssn` export loses drive phasing (#815). Every row green —
the Ward notes are cleared to send.

Findings that need code changes get filed as issues; the outcome table and
date get appended here; when every row is green, send the Ward notes.
