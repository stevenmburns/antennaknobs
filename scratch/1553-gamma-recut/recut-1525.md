
## ΔΓ re-cut, 2026-09-16

Re-cut of this record on **ΔΓ = |Γ_a − Γ_b|**, `Γ = (Z − 50)/(Z + 50)`, the metric `docs/status/2026-07-16-nec2c-corpus-benchmark.md` uses. **No cell was re-solved** — every record stores Z per port. The relative-Z columns above are unchanged and stay; ΔΓ is reported as the **vector norm over ports**, which is what compares with the `|ΔZ|` norm used above.

| class (razor-2p vs bs2@160) | on relative Z | on ΔΓ |
|---|---:|---:|
| converging | 155 | 156 |
| reference unsettled | 30 | 29 |
| non-monotone | 12 | 12 |
| not converging | 2 | 2 |

The relative-Z column counts 5 refused and 2 skipped rows that ΔΓ's table omits (they have no Z to transform), so the ΔΓ column totals 199 where the other totals 206.

Fitted order on razor-2p's converging rows, **on ΔΓ**: median **0.89** over 156 rows (relative Z gave 0.90).

razor-2p at its ×40 rung, over converging rows: median ΔΓ **0.0123**, p90 **0.0394**, worst **0.2256** — against a relative-Z median of 2.42 %.
