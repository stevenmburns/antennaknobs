# AK#1705 fixtures — the four decks that drive SY knobs

Byte-exact copies from the nec-wild corpus (`~/antennas/nec-wild/`); the
provenance is that tree's `opensource/MANIFEST.md`. They are `-text` in
`.gitattributes` because `moxon435_optimised.nec` is CRLF and a copy that git
normalised would no longer be the file.

| file | corpus path | origin |
|---|---|---|
| `3el-inverted-V.nec` | `opensource/4nec2/HFbeams/3el-inverted-V.nec` | the `models/` library bundled with Arie Voors' freeware 4nec2, via the GitHub mirror handiko/AntennaFiles-OLD (`4nec2_models/`) |
| `GndScreen.nec` | `opensource/4nec2/HFvertical/GndScreen.nec` | the same 4nec2 model library |
| `3elYagiGain.nec` | `opensource/4nec2/Equations/3elYagiGain.nec` | the same 4nec2 model library; the deck credits L. B. Cebik, W4RNL |
| `moxon435_optimised.nec` | `opensource/rchacker-antennas/UHF/moxon435_optimised.nec` | github.com/rchacker/antennas (FPV antenna models, no license stated) |

What each one exercises:

- `3el-inverted-V.nec` — the primary deck: nine commented constants (height,
  lengths, angle, spacings, guy angles) and twelve derived symbols (trig).
  Its junctions come from endpoints computed from the same expressions, so the
  topology has to survive every knob move.
- `moxon435_optimised.nec` — five labelled constants and nothing derived,
  in millimetres through `GS 0 0 0.001`.
- `GndScreen.nec` — segment counts written as `int(hgh)`, the literal-only
  `ra=360/16`, a conductivity (`cu`) that reaches `LD 5`, an unused constant
  (`fe`), and a radius (`wrad`).
- `3elYagiGain.nec` — `Fr` drives both the `FR` card and every dimension,
  `Inp=mm` and `Scal` (the `GS` scale) are unit selectors, and `Hgh=0` is a
  zero-valued constant.
