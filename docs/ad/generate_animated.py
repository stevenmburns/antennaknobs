"""AntennaKNoBs QRZ banner — generates BOTH the 728x90 animated GIF and its
frozen hero-frame PNG.

Three knob-driven panels, all from the real `beams.moxon` design as the dial
sweeps the element spacing (`aspect_ratio`): a labelled dial with a live
spacing readout -> the Moxon top-view geometry (rectangle + feed gap) ->
the radiation pattern. As the spacing widens, the boom deepens and the back
lobe collapses into a clean forward beam — the actual Moxon spacing/F-B
tradeoff, computed live by momwire. No URL (the ad is clickable).

Rendered at 3x and downscaled (LANCZOS) for antialiasing; the GIF is
delta-frame encoded (disposal=1, shared palette) so only the changing left
panels are stored per frame, keeping it under QRZ's 48 KB limit. IBM Plex Sans
+ Mono match the app (numbers in Plex Mono, like the app's readouts).

    python docs/ad/generate_animated.py     # writes both .gif and .png

Fonts: run ./fetch_fonts.sh first, or point AD_FONTS at the IBMPlex*.ttf dir.
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from antennaknobs.designs.beams.moxon import Builder
from antennaknobs.engines.momwire import MomwireEngine

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = (
    next(
        (
            p
            for p in (
                os.environ.get("AD_FONTS"),
                os.path.join(HERE, "fonts"),
                "/tmp/fonts",
            )
            if p and os.path.isdir(p)
        ),
        os.path.join(HERE, "fonts"),
    )
    + "/"
)
OUT_GIF = os.path.join(HERE, "antennaknobs_728x90.gif")
OUT_PNG = os.path.join(HERE, "antennaknobs_728x90.png")

SANS, SEMI = "IBMPlexSans-Regular.ttf", "IBMPlexSans-SemiBold.ttf"
MONO = "IBMPlexMono-SemiBold.ttf"  # the app sets numeric readouts in Plex Mono
S, W, H = 3, 728, 90


def fnt(n, p):
    return ImageFont.truetype(FONTS + n, round(p * S))


def s(v):
    return round(v * S)


def lw(v):
    return max(1, round(v * S))


BG, PANEL, ACCENT, LIGHT = (13, 16, 23), (20, 25, 34), (56, 189, 248), (125, 211, 252)
WHITE, MUTED, DARK, GRID = (242, 246, 251), (150, 165, 185), (9, 12, 17), (40, 49, 62)

# Sweep aspect_ratio (element spacing): visibly grows the boom depth AND deepens
# the back-null — the real Moxon spacing-vs-F/B tradeoff, so all three panels move.
VALS = [0.300, 0.335, 0.370, 0.400, 0.420, 0.440]
IT, DYN = 89, 26.0  # azimuth cut at the peak-gain elevation row; dB dynamic range
EL, BM = 2.02, 0.82  # geometry normalization (covers every frame's extent)


def data(ar):
    b = Builder(dict(Builder.default_params, aspect_ratio=ar))
    ws = b.build_wires()
    struct = [(e[0], e[1]) for e in ws if e[3] is None]
    feed = [e for e in ws if e[3] is not None][0]
    fmid = ((feed[0][0] + feed[1][0]) / 2, (feed[0][1] + feed[1][1]) / 2)
    ff = MomwireEngine(b).far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
    c = np.array(ff.rings)[IT]
    ph = np.deg2rad(np.array(ff.phis))
    r = np.clip((c - (c.max() - DYN)) / DYN, 0, 1)  # per-frame normalize
    P = np.array([p for ab in struct for p in ab])
    lam = 299.792458 / Builder.default_params["freq"]
    boom_l = (P[:, 0].max() - P[:, 0].min()) / lam  # element spacing in wavelengths
    return struct, fmid, r, ph, boom_l


DATA = [data(v) for v in VALS]

# ---- static base frame (everything that doesn't move) ----
base = Image.new("RGB", (W * S, H * S), BG)
d = ImageDraw.Draw(base)
d.rectangle([0, 0, W * S, s(2)], fill=ACCENT)


def fit(text, ff_, start, maxw):
    p = start
    while d.textlength(text, font=fnt(ff_, p)) > s(maxw) and p > 9:
        p -= 0.5
    return fnt(ff_, p)


tx, TW = s(232), 720 - 232
fb = fnt(SEMI, 16)
d.text((tx, s(13)), "Antenna", font=fb, fill=WHITE)
wA = d.textlength("Antenna", font=fb)
d.text((tx + wA, s(13)), "KNoBs", font=fb, fill=ACCENT)
wK = d.textlength("KNoBs", font=fb)
d.text((tx + wA + wK + s(8), s(15)), "· by KK7KNB", font=fnt(SANS, 11), fill=MUTED)
h1, h2 = "Your antennas, as ", "code."
fh = fit(h1 + h2, SEMI, 31, TW)
d.text((tx, s(33)), h1, font=fh, fill=WHITE)
d.text((tx + d.textlength(h1, font=fh), s(33)), h2, font=fh, fill=ACCENT)
sub = "Open-source MoM wire-antenna modeling in Python — cross-checked vs NEC."
d.text((tx, s(71)), sub, font=fit(sub, SANS, 12.5, TW), fill=MUTED)

DCX, DCY, DRr = s(40), s(44), s(19)  # dial
GCX, GCY, GW, GH = s(112), s(44), s(30), s(13)  # geometry
PCX, PCY, PR = s(188), s(44), s(27)  # pattern

# static label above the knob (the value below it changes per frame)
lbl, flbl = "spacing", fnt(SANS, 9.5)
d.text((DCX - d.textlength(lbl, font=flbl) / 2, s(5)), lbl, font=flbl, fill=MUTED)


def arrow(dr, x0, x1, y):  # small flow arrow between panels
    dr.line([x0, y, x1, y], fill=GRID, width=lw(1))
    dr.polygon([(x1, y), (x1 - s(4), y - s(3)), (x1 - s(4), y + s(3))], fill=GRID)


def frame(step, n):
    im = base.copy()
    dr = ImageDraw.Draw(im)
    arrow(dr, DCX + DRr + s(3), GCX - GW - s(3), DCY)  # dial -> geometry
    arrow(dr, GCX + GW + s(3), PCX - PR - s(3), DCY)  # geometry -> pattern
    # ---- dial ----
    dr.ellipse(
        [DCX - DRr, DCY - DRr, DCX + DRr, DCY + DRr],
        fill=PANEL,
        outline=ACCENT,
        width=lw(2),
    )
    for a in range(-135, 136, 27):
        ra = math.radians(a - 90)
        dr.line(
            [
                DCX + (DRr - s(4)) * math.cos(ra),
                DCY + (DRr - s(4)) * math.sin(ra),
                DCX + (DRr - s(1)) * math.cos(ra),
                DCY + (DRr - s(1)) * math.sin(ra),
            ],
            fill=GRID,
            width=lw(1),
        )
    ang = math.radians(-120 + 240 * (step / (n - 1)) - 90)
    pxp = DCX + (DRr - s(6)) * math.cos(ang)
    pyp = DCY + (DRr - s(6)) * math.sin(ang)
    dr.line([DCX, DCY, pxp, pyp], fill=LIGHT, width=lw(3))
    dr.ellipse([pxp - s(3), pyp - s(3), pxp + s(3), pyp + s(3)], fill=ACCENT)
    dr.ellipse([DCX - s(3), DCY - s(3), DCX + s(3), DCY + s(3)], fill=ACCENT)
    # ---- live spacing readout under the knob (number in Plex Mono, λ in Sans) ----
    struct, fmid, r, ph, boom_l = DATA[step]
    num = f"{boom_l:.2f} "
    fnum, fun = fnt(MONO, 10.5), fnt(SANS, 10.5)
    wn = dr.textlength(num, font=fnum)
    x0 = DCX - (wn + dr.textlength("λ", font=fun)) / 2
    dr.text((x0, s(67)), num, font=fnum, fill=LIGHT)
    dr.text((x0 + wn, s(67)), "λ", font=fun, fill=LIGHT)

    # ---- geometry (Moxon top view; element -> horizontal, boom -> vertical) ----
    def gp(pt):
        return (GCX + (pt[1] / EL) * GW, GCY - (pt[0] / BM) * GH)

    for a, b in struct:
        dr.line([gp(a), gp(b)], fill=ACCENT, width=lw(2), joint="curve")
    fx, fy = gp((fmid[0], fmid[1]))
    dr.ellipse(
        [fx - s(2.6), fy - s(2.6), fx + s(2.6), fy + s(2.6)], fill=WHITE
    )  # feed gap
    # ---- pattern (azimuth-cut outline) ----
    for fr in (0.5, 1.0):
        dr.ellipse(
            [PCX - PR * fr, PCY - PR * fr, PCX + PR * fr, PCY + PR * fr],
            outline=GRID,
            width=lw(1),
        )
    dr.line([PCX - PR, PCY, PCX + PR, PCY], fill=GRID, width=lw(1))
    dr.line([PCX, PCY - PR, PCX, PCY + PR], fill=GRID, width=lw(1))
    pts = [
        (PCX + PR * rr * math.cos(p), PCY - PR * rr * math.sin(p))
        for rr, p in zip(r, ph, strict=True)
    ]
    dr.line(pts + [pts[0]], fill=ACCENT, width=lw(2), joint="curve")
    return im.resize((W, H), Image.LANCZOS)


order = list(range(len(VALS))) + list(range(len(VALS) - 2, 0, -1))  # ping-pong
frames = [frame(i, len(VALS)) for i in order]

master = Image.new("RGB", (W, H * len(frames)))
for i, fr in enumerate(frames):
    master.paste(fr, (0, i * H))
pal = master.quantize(colors=220, dither=Image.Dither.NONE)
fp = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
fp[0].save(
    OUT_GIF,
    save_all=True,
    append_images=fp[1:],
    duration=500,
    loop=0,
    optimize=True,
    disposal=1,
)
HERO = len(VALS) - 1  # widest spacing: clean forward beam, deep null, tallest geometry
frames[HERO].quantize(colors=200, dither=Image.Dither.NONE).save(OUT_PNG, optimize=True)
print("gif", os.path.getsize(OUT_GIF), "png", os.path.getsize(OUT_PNG))
