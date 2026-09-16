<!-- Comment text for AK#1525. NOT posted by this session: the standing
     rule is that Steve decides what is quoted and where. Paste verbatim. -->

## The bspline family at the densities #1547 serves

**Builds.** antennaknobs main `54ca0978b` (v0.79.0); momwire `a6a67f93a` (`v0.56.0-9-ga6a67f9`, v0.56.0), detached at the briefed commit and rebuilt; accelerator `_accelerators_avx2`. **Reference: bs2@160 from the AK#1525 ladder**, re-validated on this build before use — 32 cells across 7 designs × 2 grounds spanning buried, Sommerfeld, multi-port, network and the largest catalog design are bit-identical to the stored records. Provenance is the first line of `records.jsonl`.

**Metric.** `|ΔZ|` over all ports as a vector; the percentage is that over `|Z_ref|`. Identical to the AK#1525 ladder's, so these rows and razor-2p's sit on one footing.

> **One rung per degree, so there is no convergence class and no fitted order here.** The AK#1525 ladder classified rows because it had four rungs; this has one. The only classification available is **admissibility** — whether bs2's own ×80→×160 move stayed under a third of the error being judged, so the reference can arbitrate the row at all. A row that is not admissible is *unresolved*, not *failing*.

## Error at the served density

| basis | served N | admissible rows | median | p90 | worst |
|---|---:|---:|---:|---:|---:|
| B-spline d=1 | 20 | 149 | 1.53 % | 6.01 % | 20.2 % |
| B-spline d=2 | 15 | 147 | 0.964 % | 8.51 % | 133 % |
| B-spline d=3 | 12 | 158 | 1.11 % | 18.3 % | 240 % |

For comparison, on the same metric, the same reference **and the same admissibility rule**, **razor-2p at its served 40** measures a median **2.72 %** over 145 admissible rows. AK#1525 quotes **2.42 %** for razor-2p at 40; that is a median over its *converging* rows, a different population, and over all 199 comparable rows it is 1.97 %. The 2.72 % above is the only one of the three that is like-for-like with this table.

## Rows the reference cannot arbitrate

| basis | admissible | unresolved (one-third rule) | not solved |
|---|---:|---:|---:|
| B-spline d=1 | 149 | 55 | 2 |
| B-spline d=2 | 147 | 57 | 2 |
| B-spline d=3 | 158 | 46 | 2 |

Unresolved means bs2 itself had not settled between ×80 and ×160 on that design by more than a third of the error being judged. It is a statement about the reference, not about the basis under test.

## Cost at the served density

| basis | served N | catalog cold total | median cold | worst single | worst peak RSS |
|---|---:|---:|---:|---:|---:|
| B-spline d=1 | 20 | 96.2 s | 0.095 s | 34.73 s | 2540 MB |
| B-spline d=2 | 15 | 174.8 s | 0.095 s | 80.60 s | 5180 MB |
| B-spline d=3 | 12 | 68.6 s | 0.149 s | 5.79 s | 776 MB |

