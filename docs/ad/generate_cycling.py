"""AntennaKNoBs QRZ banner — the *cycling-text* variant (728x90).

The three knob-driven panels sit **frozen** on the left (the dial at its widest
spacing, its Moxon geometry and forward-beam pattern), and a single **big line**
cycles on the right at 2 s each — a four-step pitch:

    Parameterize antennas in Python
    Turn knobs to adjust parameters
    See effects in real-time charts
    Download at antennaknobs.dev

Because only the right-hand line changes between frames, the delta-frame GIF
stores just that band per frame, so four big lines land comfortably under QRZ's
48 KB ceiling. Each line auto-fits the text column (largest wins, capped) so the
short lines render big; the longest line sets its own size.

    python docs/ad/generate_cycling.py    # writes the _cycling .gif and .png

Fonts: run ./fetch_fonts.sh first, or point AD_FONTS at the IBMPlex*.ttf dir.
Shared drawing lives in _adkit.py.
"""

import os

from PIL import ImageDraw

import _adkit as K

OUT_GIF = os.path.join(K.HERE, "antennaknobs_728x90_cycling.gif")
OUT_PNG = os.path.join(K.HERE, "antennaknobs_728x90_cycling.png")

# (text, accent-substring-or-None). The accent word is drawn in the app's accent
# blue, the rest white. Keep lines short so they render big (one shared column).
LINES = [
    ("Parameterize antennas in Python", "Python"),
    ("Turn knobs to adjust parameters", None),
    ("See effects in real-time charts", None),
    ("Download at antennaknobs.dev", "antennaknobs.dev"),
]

SIZE_CAP = 32  # keep the short lines from ballooning past the panels' height
DURATION_MS = 2000  # 2 s per line


def base():
    """Frozen left panels + the fixed brandmark; the cycling line is added on
    top per frame."""
    im = K.new_canvas()
    dr = ImageDraw.Draw(im)
    K.accent_bar(dr)
    K.draw_panels(dr, K.HERO, len(K.SWEEP))  # frozen at the widest spacing
    K.brandmark(dr, K.TX, 8)
    return im


def render(base_im, text, accent):
    im = base_im.copy()
    dr = ImageDraw.Draw(im)
    pt = K.fit_pt(dr, text, SIZE_CAP, K.TW)
    f = K.fnt(K.BOLD, pt)
    bb = dr.textbbox((0, 0), text, font=f)
    th = bb[3] - bb[1]
    y = K.s(26) + (K.s(58) - th) // 2 - bb[1]  # centre in the band below the brand
    x = K.s(K.TX)
    if accent and accent in text:
        pre, post = text.split(accent, 1)
        dr.text((x, y), pre, font=f, fill=K.WHITE)
        x += dr.textlength(pre, font=f)
        dr.text((x, y), accent, font=f, fill=K.ACCENT)
        x += dr.textlength(accent, font=f)
        dr.text((x, y), post, font=f, fill=K.WHITE)
    else:
        dr.text((x, y), text, font=f, fill=K.WHITE)
    return K.downscale(im)


b = base()
frames = [render(b, text, accent) for text, accent in LINES]

gif_bytes = K.save_gif(frames, OUT_GIF, duration=DURATION_MS)
png_bytes = K.save_png(frames[0], OUT_PNG)  # hero: the value-prop line + brand
print(f"cycling gif {gif_bytes} B ({gif_bytes / 1024:.1f} KB), png {png_bytes} B")
