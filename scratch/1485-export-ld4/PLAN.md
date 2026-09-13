# antennaknobs#1485: `export_nec` writes LD 4 for a fixed complex-impedance Load

Registered before the source change, on `fix/1485-export-ld4` from origin/main
5363bbbe5.

## The defect

- `nec_export.export_nec` turns `Load` branches into LD cards in a loop that
  reads only `br.r`, `br.l` and `br.c`.
- A `Load(z=…)`, which is what an LD 4 reactive load imports as (#422), has all
  three set to None. It reaches the all-zero `continue`, and no card is written.
  Nothing warns.
- `engines/nec2.py`, the NEC-2 tab (#1354), writes its deck through
  `export_nec` by design. So today the NEC-2 tab solves a z-load design as if
  the load were absent, while PyNEC in process solves it with the load.
- That shows up as an engine disagreement, but it is really an export bug.

## The change

- **What is added.** In that loop, a branch with `z is not None` writes
  `LD 4 {tag} {seg} {seg} {_num(R)} {_num(X)} {_num(0)}`, and a branch with
  `z == 0` writes nothing.
- **Why that shape.** It is exactly `PyNECEngine._emit_load_card`, which calls
  `ld_card(4, tag, seg, seg, z.real, z.imag, 0.0)` and skips `z == 0`.
  `export_nec` is meant to be the text twin of what PyNECEngine hands PyNEC.
- **What is left alone.** The RLC path does not change.
- **Already right, and not touched:**
  - `ql`/`qc` loads send PyNECEngine to the reducer, so `export_nec` already
    refuses them.
  - `simnec_export` already refuses z-loads by name (`SsnUnsupported`), and its
    LD filter keeps only types 0 and 1.

## Gates (predictions fixed now)

Measured with `census_export.py` and `nec2tab_gate.py`, once on this commit's
tree before the fix and once after it.

| id | prediction |
|---|---|
| PC1 | **Catalog: 0 designs' NEC-2 export text changes.** An AST scan of `src/antennaknobs/designs/` finds 0 `Load(…, z=…)` calls, and 0 default-built catalog designs carry a z-load branch. Every export text, or refusal, is byte-identical before and after. |
| PC2 | **nec_portal (65 decks in `momwire/tests/fixtures/nec_portal`): the export text changes only on decks that carry an LD 4 with X ≠ 0.** Exactly one deck does: `dipole_load_ld4.deck` (`LD 4 1 3 3 100. -75.`). Every other deck's export text, or refusal, is byte-identical. On that deck, the one change is an added `LD 4 1 3 3` line. |
| PC3 | **PyNEC Z is unchanged everywhere, bit for bit**, because PyNEC never reads the exporter. Checked on `dipole_load_ld4.deck`. |
| PC4 | **The NEC-2 tab's Z moves onto PyNEC's.** nec2c is on this box (`~/.local/bin/nec2c`), so the gate runs. The engine is `NEC2Engine` with `$NEC2_EXE` set to nec2c, on `dipole_load_ld4.deck` in free space. **Before the fix,** it reads the load-free value: within 0.1 Ω of PyNEC on the same deck with its LD card removed, and more than 1 Ω from PyNEC on the loaded deck. **After the fix,** it reads PyNEC's loaded value within 0.1 Ω. |

**The 0.1 Ω bar** is the repo's existing bar for nec2c against PyNEC, from
`test_nec_export.py::test_export_matches_nec2c` ("agree to a few mΩ; allow
0.1 Ω abs"). `test_nec2_engine_1354` has its own PyNEC-agreement bar of 5 %, but
that one is for momwire's portal stand-in, not a real NEC-2 binary, so it is not
the bar that applies here.

## Tests (added to `tests/test_ld4_reactive_load.py`)

- **T1.** The export of a z-load design contains the LD 4 line at the load's
  tag and segment, with R, X and 0 as its three values.
- **T2.** `parse_nec(export, network=True)` gives back the same `Load` z, at the
  same place.
- **T3.** A `z == 0` load writes no LD card.
- **T4 (the NEC-2 engine against a real binary).**
  - **Agreement:** `NEC2Engine` on the z-load deck agrees with PyNEC within
    0.1 Ω, and differs from the load-free Z.
  - **Skip:** it skips cleanly when no nec2c is on PATH, using the
    `shutil.which("nec2c")` skip from `test_nec_export.py`.
  - **Binary:** `$NEC2_EXE` is set by monkeypatch, the way
    `test_nec2_engine_1354`'s fixtures set it.

## Conventions

- Both `uvx ruff@0.16.5 check .` and `format --check .` must be clean.
- Stage explicit paths only.
- Use `gh -R stevenmburns/antennaknobs`.
- The PR describes this as "the hole in #1485".

## Results [2026-09-13]

Registered at c2d37f2cc (19:55:22Z), before the source change. Before and after
records are `census_before.json` / `census_after.json` (diff in
`census_diff.txt`) and `nec2tab_before.json` / `nec2tab_after.json`.

| id | result |
|---|---|
| PC1 | **HIT.** 0 of 112 catalog entries changed: 73 export, 30 refuse, 9 have no builder, and every text and refusal is byte-identical. The AST scan finds 0 `Load(…, z=…)` calls, and 0 designs carry a z-load. |
| PC2 | **HIT on which decks, MISS on the literal line.** 1 of 65 nec_portal decks changed, `dipole_load_ld4.deck`, by one added LD 4 line; the other 64 are byte-identical (54 export, 9 refuse, 2 do not parse). The line was registered as `LD 4 1 3 3` and is written as `LD 4 2 1 1`. The importer gives the loaded segment a one-segment wire of its own, and the export numbers wires by the GW cards it writes: exported `GW 2 1` spans z −1.389 to −0.833 m, which is original segment 3 of 9. The feed moved the same way (`EX 0 4 1`, original segment 5), and that part was already true before this change. |
| PC3 | **HIT.** PyNEC Z on the loaded deck is 128.31031511549654−8.79422339748376j before and after, bit for bit. |
| PC4 | **HIT.** Before the fix, the NEC-2 tab (nec2c) read 79.24+45.364j: 0.020 Ω from PyNEC with the LD card removed, and 73.1 Ω from PyNEC loaded. After the fix it reads 128.31−8.813j, 0.019 Ω from PyNEC loaded. |

**The tests, and a miss in their first draft.** T1 and T2 as first written
asserted the imported deck's numbering (tag 1, segment 2), for the same reason
PC2's literal line missed. They failed on that assumption, not on the fix, and
were rewritten before any commit:
- **T1** now asserts the row sits at PyNECEngine's `_network_port_loc` for the
  load, which is where PyNEC's `ld_card` goes.
- **T2** imports the export, checks that the same z comes back, and checks that
  a second export repeats the first card for card.
- **T3 and T4** passed as written. T4 ran against the real nec2c: agreement
  within 0.1 Ω, and far from the load-free Z.

**Lanes.**
- ruff 0.16.5 `check` and `format --check` are clean over the whole tree.
- `test_ld4_reactive_load`, `test_nec2_engine_1354`, and every test file that
  touches the exporter: 350 passed, 45 skipped, 0 failed.
- The skips are environment gates: 21 need a NEC-5 binary, and 19 in
  `test_port_position_1469` need momwire#1059 in the submodule pointer.
