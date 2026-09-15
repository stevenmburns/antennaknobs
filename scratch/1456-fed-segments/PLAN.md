# AK#1456, option 1: cross-engine rows record each engine's fed segment

Registered 2026-09-15, **before any solve**. Branch
`feat/1456-fed-segment-lengths`, off main a9c49416f.

A gate failure is a stop and a report. A missed prediction is reported as a miss
and is not re-registered.

## Scope

The issue offers three fixes. This work builds **option 1 only**:

- every cross-engine row (census, validation, gates) records each engine's
  fed-segment length;
- near-open driving points are flagged as size-sensitive, with the threshold
  taken from data.

Options 2 (harnesses matching the fed segment) and 3 (a workbench note) are a
decision. They go out as a proposal with measurements, and neither is built.

## Already measured, before this registration

- **`survey_catalog.py`** (mesh only): 103 designs, 234 fed wires.
  - 205 of them are authored 1-segment gaps.
  - After parity coercion, momwire's fed segment (odd) is 2× NEC-5's (even) at
    the median, over a range of 0.67–2.0.
  - 193 fed wires are shorter than 0.01 λ, and 24 are longer than 0.1 λ.
- **`probe_end_selector.py`**: momwire's NEC-2 portal ignores NEC-5's EX end
  selector.
  - The #896 census feeds both engines the translated decks, so momwire's source
    sits half a segment from the knot NEC-5 drives, wherever `translate` moved a
    feed onto a knot.
  - On a 10-segment dipole that is 2.2 % of R.
  - This is recorded as a caveat of that census instrument, and is not fixed
    here.

## The deliverables

1. **`SimulationEngine.fed_segments()`**, for momwire, NEC-5, PyNEC and NEC-2.
   - It returns one record per source: the wire, the count as meshed, the fed
     segment's length in metres, and the site (`centre`, `knot` or `vertex`).
   - It is read from the coerced wires, so what it reports is what the engine
     solves.
2. **A size-sensitivity flag** with a data-derived threshold (the study below).
   It is a pure function of the row's Z and frequency, so a row can carry it
   without a solve.
3. **The rows:**
   - `scripts/build_validation_report.py`: the cross-engine tables and prose
     (ByDipole1, Leeson, below ground) state each engine's fed segment, and the
     page is regenerated;
   - the #1441 buried census (`scratch/956-census/`):
     - the worker cells and CSV columns gain fed-segment fields for future runs;
     - a mesh-only addendum records them for the committed rows;
   - the #896 corpus census harness (`scratch/896-census/`):
     - `census_momwire.py` records momwire's fed segment and the end-selector
       offset;
     - `census_report.py` derives NEC-5's from the same translated deck bytes;
     - the frozen `nec5_corpus` tool is not touched;
   - the engine-comparison tests name both fed segments in their failure
     messages.
4. **`site/.../reference/nec5.md`**: the parity bullet says the two engines'
   fed segments differ, and that size-sensitive rows are flagged.

## The threshold study

### The argument, which the data may refute

- **The model.** A change in the fed segment's size changes the feed model's own
  shunt susceptance, ΔY ≈ jΔB = jωΔC, and leaves the rest of the structure
  alone. Then ΔZ = −Z²ΔY, which gives:
  - |ΔZ|/|Z| ≈ |Z|·ωΔC;
  - ΔR/R ≈ 2X·ωΔC.
- **What it predicts.** A driving point's sensitivity to fed-segment size scales
  with |Z| (and f), not with |X|/R. "Near-open" is the case where |Z| is large.
  At a resonant 70 Ω point the same ΔC is immaterial.

### The harness, `sensitivity.py`

- **Designs.** Every catalog design whose fed wires are all authored 1-segment
  gaps shorter than 0.01 λ, so that re-counting the fed wire leaves the far mesh
  alone. Designs with longer fed wires are listed and excluded.
- **Ground and frequency.** The design's defaults and its declared
  `ground_requirement`; free space when it declares none.
- **Engines.**
  - momwire's default solver, with the fed wire at **1, 3 and 7** segments.
  - NEC-5 (`nec5cl-x13-static`, sha256 7ebf343d), at **2 and 6**.
  - momwire at antennaknobs' pointer, 0.55.0.
- **Records per port:**
  - Z at each count;
  - ΔY for momwire 1→3 and for NEC-5 2→6;
  - ΔC = Im(ΔY)/ω;
  - the shunt fraction |Re ΔY|/|Im ΔY|;
  - the cross-engine split, D = |Z_mw − Z_n5| / max(|Z_mw|, |Z_n5|), at the
    inherited sizes (momwire 1 against NEC-5 2) and near-matched (momwire 7 at
    L/7 against NEC-5 6 at L/6, a size ratio of 0.857).
- **Excluded ports.** A design either engine refuses is recorded with its
  refusal and left out of the statistics.

### Predictions

| id | what | prediction |
|---|---|---|
| **P1** | Mechanism: the shunt fraction \|Re ΔY\| / \|Im ΔY\| under momwire 1→3, median over the ports | ≤ 0.1 |
| **P2** | Collapse: the relative \|ΔZ\| under momwire 1→3, rank-correlated (Spearman) over the ports with \|Z\|·f and with \|X\|/R | ρ(\|Z\|·f) ≥ 0.9, and higher than ρ(\|X\|/R) |
| **P3** | ΔC is near-constant per engine: the p90/p10 ratio of \|ΔC\| under momwire 1→3 | ≤ 10 |
| **P4** | At the defaults, the ports whose R moves > 1 % under momwire 1→3 | at most 5 designs, `elevated_buried_counterpoise` among them |
| **P5** | `elevated_buried_counterpoise`'s cross-engine B split, inherited against near-matched | inherited > 10 %, near-matched ≤ 2 % |

### How the threshold comes out

The procedure is fixed here and the numbers come from the data:

- C_ref is the 90th percentile of |ΔC| over the ports, taking for each port the
  larger of momwire 1→3 and NEC-5 2→6.
- A row is flagged size-sensitive when |Z|·2πf·C_ref ≥ 0.01, i.e. when fed-segment
  size alone could move |Z| by 1 %. The 1 % is the census's own first band edge.

If P2 fails, so that |Z|·f does not collapse the data, this procedure is
abandoned and not adjusted. The report shows what the data does collapse on,
and the threshold goes back upstream as a proposal instead of shipping.

## Order

1. Commit this registration, with the survey and the probe.
2. Write `sensitivity.py` and dry-run it on two designs; nothing is recorded.
3. The full study, under `systemd-run` with MemoryMax=24G.
4. The analysis: P1–P5, and C_ref.
5. The deliverables, the regenerated validation page, lint, and the antennaknobs
   suite at the pointer.
6. The PR, unmerged, without a closing keyword (the issue stays open for options
   2 and 3), and the proposal upstream.
