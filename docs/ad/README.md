# QRZ.com banner ads

Marketing assets for a [QRZ.com](https://www.qrz.com/page/advertising.html)
**top-slot leaderboard** campaign for AntennaKNoBs. QRZ picks one banner per page
view and holds it, so we run **several variants** and will add more over a
campaign; each is a thin script over the shared `_adkit.py` (fonts, palette, the
live Moxon panels, and the delta-frame GIF encoder).

| File | Variant | What | Size |
| --- | --- | --- | --- |
| `antennaknobs_728x90.gif` | animated | 3 knob-driven panels sweeping the Moxon spacing | ~34 KB |
| `antennaknobs_728x90.png` | animated | frozen hero frame (static fallback) | ~15 KB |
| `antennaknobs_728x90_cycling.gif` | cycling | frozen panels + a big line cycling every 2 s | ~35 KB |
| `antennaknobs_728x90_cycling.png` | cycling | hero frame (the value-prop line) | ~12 KB |

## QRZ top-slot spec (verify current values with sales@qrz.com)

- **Dimensions:** 728 × 90 px
- **Formats:** JPG, GIF, or PNG · **max file size 48 KB** (both assets are well under)
- **Rate (as read from QRZ's page, June 2026):** top slot **$200 / month**
  ($540 / 3 mo, $2040 / yr); 10% off for 3+ units, 15% for 1 yr+. Confirm before buying.

## What the panels show

Both variants share the same three panels, left to right, all computed live by
this repo's `momwire` engine from the catalog `beams.moxon` design:

1. **A labelled dial** ("spacing") with a live readout below it — the Moxon's
   element spacing in wavelengths.
2. **The Moxon geometry** — its real top view (driven element + feed gap,
   reflector, bent tips) from `build_wires()`.
3. **The radiation pattern** — an azimuth cut from `far_field()`.

As `aspect_ratio` (element spacing) widens, the boom deepens and the back lobe
collapses into a clean forward beam — the actual Moxon spacing/front-to-back
tradeoff. Turn a knob, the antenna responds: the point of AntennaKNoBs, drawn by
AntennaKNoBs.

## Variants

- **`animated`** — the panels *move*: the dial sweeps the spacing and all three
  panels reshape together, ping-ponging across the range.
- **`cycling`** — the panels are *frozen* at the widest spacing (clean forward
  beam) and a single **big line** cycles on the right at 2 s each, a four-step
  pitch: `Parameterize antennas in Python` → `Turn knobs to adjust parameters` →
  `See effects in real-time charts` → `Download at antennaknobs.dev`. Because
  only the right-hand line changes between frames, the delta-frame GIF stays
  small even with large type; each line auto-fits the text column so the short
  lines render big.

## Messaging (deliberate)

- The ad links to **antennaknobs.dev**, the main site, so visitors land on the
  installable open-source tool rather than the throwaway web demo.
- Says **"open source"** / points at the download (no "free trial" framing that
  would imply a future paywall).
- Avoids the word **"tune"** — turning a design parameter is not antenna tuning.
- KK7KNB credit for QRZ cred.

## Typography

IBM Plex Sans + IBM Plex Mono — the same family the web app loads — with the
**numeric readout in Plex Mono**, matching the app's value displays. (Plex Mono
ships without a λ glyph, so the unit is drawn in Plex Sans.) The fonts are **not
committed** (OFL 1.1, ~1 MB); fetch them first:

```bash
docs/ad/fetch_fonts.sh        # downloads IBM Plex into docs/ad/fonts/ (gitignored)
```

## Regenerate

```bash
pip install -e ".[web]"        # needs antennaknobs (for the momwire patterns) + Pillow
docs/ad/fetch_fonts.sh
python docs/ad/generate_animated.py   # animated variant: .gif + hero .png
python docs/ad/generate_cycling.py    # cycling variant: _cycling.gif + _cycling.png
```

Each variant writes both its `.gif` and a static hero-frame `.png` fallback.
Rendered at 3× and downscaled (LANCZOS) for antialiasing; the GIFs are
delta-frame encoded (only the changing region is stored per frame), which keeps
them under the 48 KB limit. Shared drawing lives in `_adkit.py`. Override the
font location with the `AD_FONTS` env var if your TTFs live elsewhere.
