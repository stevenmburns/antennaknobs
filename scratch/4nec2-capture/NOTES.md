# 4nec2 capture session — 2026-08-20 (momwire#456, Targets 2 and 3)

Two questions: which `RP` card 4nec2 emits for a MiniNec-ground model's pattern run
(Target 2), and the card order of the `Coax.nec` deck that carries both hand-written
`TL` and a manufactured `NT` (Target 3). I/O observation only; card payloads are
recorded verbatim and not interpreted.

**Captures `0039`–`0041`.** Harness: `scripts/eznec_spy`, shims rebuilt from source
this session with the capture root baked to `scratch/4nec2-capture`, installed over
`nec2dxs500`, `nec2dxs1K5` and `nec2dxs3k0` — three rather than one so an auto-select
fallback could not slip a run past the shim. `watchdirs.txt` already carried
`C:\4nec2\out`, without which no deck or printout is captured.

Engine reached through `Settings → Nec engine → Manual select` →
`C:\4nec2\exe\nec2dxs1K5.exe`. **4nec2 prompts for the engine's segment capacity when
a manual path is set** — answered `1500`, matching the real `nec2dxs1K5` build's
announced `MAXMAT=1500`, so the host's expectations stay matched to the engine
actually solving behind the shim. Worth carrying into the ritual; the 08-18 write-up
does not mention this prompt.

Protocol reproduced exactly as documented: no argv, cwd `C:\4nec2\exe`, two-line
CRLF response file on stdin, exit 0 throughout.

## What was clicked, in order

| # | capture | model | run | engine | ms | stdin response file | printout |
|---|---|---|---|---|---|---|---|
| 1 | `0039` | `HFvertical\GP80.nec` | far-field pattern, single point | `Nec2dXS1k5.exe` | 231 | `..\out\GP80.inp` / `..\out\GP80.out` | 15,600 → 233,037 B |
| 2 | `0040` | `HFvertical\GP80.nec` | frequency sweep with gain | `Nec2dXS1k5.exe` | 227 | `..\out\GP80.inp` / `..\out\GP80.out` | 233,037 → 443,253 B |
| 3 | `0041` | `HFsimple\Coax.nec` | impedance | `Nec2dXS1k5.exe` | 103 | `..\out\Coax.inp` / `..\out\Coax.out` | 25,070 B |

GP80 is 51 segments (`GW` 12+13+8+13+5, no `GX`/`GR`), consistent with the 08-18
finding that `nec2dxs500` is never selected and `1K5` is the effective floor.

## Target 2 — the `RP` card

Both GP80 pattern runs emit **`RP` with mode digit 3**:

```
0039  RP 3 19 73 1503 -90 0 5 5        (single point)
0040  RP 3 37 1 1500 -90 0 5           (swept)
```

Recorded, not interpreted. Emitted `0039` deck in full, against its source:

| source | emitted |
| --- | --- |
| `SY len=23.5` + `GW 1 12 … len .04` | `GW 1 12 0.0 0.0 0.0 0.0 0.0 23.5 .04` |
| `SY Cap=378pF` + `LD 0 1 1 1 0 0 Cap` | `LD 0 1 1 1 0 0 3.78e-10` |
| `GN 3 0 0 0 13 0.005 0.0 0.0` | `GN 1` + `GD 0 0 0 0 13 0.005` |
| `FR 0 1 0 0 3.55 1` | `FR 0 1 0 0 3.55 0` |
| `EN` | *(absent)* |
| — | `RP 3 19 73 1503 -90 0 5 5` |

The `GN 3` → `GN 1` + `GD` translation reproduces the 08-18 finding exactly.

The sweep (`0040`) is **one launch** for the whole 30-point run, again as 08-18
recorded, and shows the two-phase body:

```
FR 0 1 0 0 3.55 0
XQ
FR 0 30 0 0 1 1
RP 3 37 1 1500 -90 0 5
```

Two incidental differences between the run modes: the swept deck gains an injected
second comment line `CM forw: 65, 0 ; back:-65, 0`, and it carries `XQ` where the
single-point deck carries none — so `XQ` injection tracks the run mode here, not the
model.

## Target 3 — `Coax.nec` card order

Emitted `0041` deck, 1,198 bytes, card order verbatim:

```
CM ×15
CE                       (line 16, carrying trailing text: "CE wiring.")
GW 1 20 0 -5.11 10 0 -0.03 10 1.026e-3
GW 2 1 0 -0.03 10 0 0.03 10 1.026e-3
GW 3 20 0 0.03 10 0 5.11 10 1.026e-3
GW 4 1 0 -0.03 1 0 0.03 1 1.026e-3
GW 5 40 0 0.03 10 0 0.03 1 1.026e-3
GW 9901 1 -0.0109213 0 9901 0.01092129 0 9901 5.46064e-4
GE 0
NT 9901 1 4 1 0 0 0 1
TL 2 1 4 1 50 13.636364
EX 0 9901 1 0 0 1
GN 2 0 0 0 20 0.0303
FR 0 1 0 0 14 0
XQ
```

Both card kinds are present as the target required: the hand-written `TL` (with
`SY Z0=50` and `Elen=Tlen/Vf` resolved to `50` and `13.636364`) and a manufactured
`NT` block. **`NT` precedes `TL`**, and both sit after `GE 0`, contiguous. The
source's `EX 6 4 1 0 1 0` came out as `EX 0 9901 1 0 0 1` — relocated onto the
phantom wire `GW 9901`, parked at z = 9901 m, which is 4nec2's anchoring idiom.

## Anomalies

1. **No `EN` card in any of the three emitted decks.** Byte-checked, not merely
   grepped: `0039` ends `… 5 5\r\n`, `0041` ends `… 14 0\r\nXQ\r\n`. Both sources
   carry `EN`. `0040` likewise ends at its `RP`.
2. **A "use original file" dialog appeared on opening `Coax.nec`** and was answered
   before the impedance run. *Which way it was answered is not recorded* — see the
   open question below. No such dialog appeared for `GP80.nec`.
3. No engine errors, no segment-check popups, no skipped launches: three clicks,
   three captures, three delegations at exit 0.

## Open question

The `Coax.nec` "use original file" answer is unrecorded, so it is not currently
possible to say whether `0041` is the regenerated-deck path or the pass-through path.
The deck's contents argue it was regenerated — `SY` symbols are resolved, an `NT`
block and a phantom wire were manufactured, and `EN` was dropped, none of which a
verbatim pass-through would do — but that is inference, not observation, and the
click should be confirmed rather than deduced.
