"""Shared building blocks for the AntennaKNoBs QRZ banner variants.

Every 728x90 variant reuses the same ingredients: the IBM Plex fonts the web app
loads, the app's colour palette, the three knob-driven Moxon panels (dial ->
geometry -> pattern) computed live by `momwire`, and a delta-frame GIF encoder
that keeps the file under QRZ's 48 KB ceiling. Each variant script (e.g.
`generate_animated.py`, `generate_cycling.py`) imports this kit and only decides
*what moves* and *what text* to show.

Everything is drawn at `S`x supersampling and downscaled (LANCZOS) for
antialiasing. Fonts are not committed (OFL 1.1); run `./fetch_fonts.sh` first or
point `AD_FONTS` at the IBMPlex*.ttf directory.
"""

import math
import os

import numpy as np
from PIL import Image, ImageFont

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

SANS, SEMI, BOLD = (
    "IBMPlexSans-Regular.ttf",
    "IBMPlexSans-SemiBold.ttf",
    "IBMPlexSans-Bold.ttf",
)
MONO = "IBMPlexMono-SemiBold.ttf"  # the app sets numeric readouts in Plex Mono
S, W, H = 3, 728, 90

# App palette.
BG, PANEL, ACCENT, LIGHT = (13, 16, 23), (20, 25, 34), (56, 189, 248), (125, 211, 252)
WHITE, MUTED, DARK, GRID = (242, 246, 251), (150, 165, 185), (9, 12, 17), (40, 49, 62)

# Panel geometry (1x coords; the text column is everything to the right).
DCX, DCY, DRr = 40, 44, 19  # dial centre + radius
GCX, GCY, GW, GH = 112, 44, 30, 13  # geometry centre + half-extents
PCX, PCY, PR = 188, 44, 27  # pattern centre + radius
TX = 230  # text column left edge (just past the pattern panel)
TW = 720 - TX  # text column width

# Moxon far-field / normalization constants (cover every frame's extent).
IT, DYN, EL, BM = 89, 26.0, 2.02, 0.82


def fnt(name, pt):
    return ImageFont.truetype(FONTS + name, round(pt * S))


def s(v):
    return round(v * S)


def lw(v):
    return max(1, round(v * S))


def moxon_data(ar):
    """The live Moxon geometry, feed, azimuth pattern and element spacing for a
    given aspect_ratio (element spacing), from the real catalog design."""
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


def _arrow(dr, x0, x1, y):  # small flow arrow between panels
    dr.line([s(x0), s(y), s(x1), s(y)], fill=GRID, width=lw(1))
    dr.polygon(
        [(s(x1), s(y)), (s(x1) - s(4), s(y) - s(3)), (s(x1) - s(4), s(y) + s(3))],
        fill=GRID,
    )


def draw_panels(dr, step, n):
    """Draw the dial + geometry + pattern for sweep index ``step`` of ``n`` onto a
    3x ImageDraw. ``step``/``n`` set the dial-hand angle; the panels themselves
    come from the live Moxon at ``SWEEP[step]``. Variants that want a *frozen*
    left panel just call this once with a fixed step."""
    _arrow(dr, DCX + DRr + 3, GCX - GW - 3, DCY)  # dial -> geometry
    _arrow(dr, GCX + GW + 3, PCX - PR - 3, DCY)  # geometry -> pattern
    struct, fmid, r, ph, boom_l = SWEEP_DATA[step]
    dcx, dcy, drr = s(DCX), s(DCY), s(DRr)
    # dial
    dr.ellipse(
        [dcx - drr, dcy - drr, dcx + drr, dcy + drr],
        fill=PANEL,
        outline=ACCENT,
        width=lw(2),
    )
    for a in range(-135, 136, 27):
        ra = math.radians(a - 90)
        dr.line(
            [
                dcx + (drr - s(4)) * math.cos(ra),
                dcy + (drr - s(4)) * math.sin(ra),
                dcx + (drr - s(1)) * math.cos(ra),
                dcy + (drr - s(1)) * math.sin(ra),
            ],
            fill=GRID,
            width=lw(1),
        )
    ang = math.radians(-120 + 240 * (step / (n - 1)) - 90)
    pxp, pyp = dcx + (drr - s(6)) * math.cos(ang), dcy + (drr - s(6)) * math.sin(ang)
    dr.line([dcx, dcy, pxp, pyp], fill=LIGHT, width=lw(3))
    dr.ellipse([pxp - s(3), pyp - s(3), pxp + s(3), pyp + s(3)], fill=ACCENT)
    dr.ellipse([dcx - s(3), dcy - s(3), dcx + s(3), dcy + s(3)], fill=ACCENT)
    # static label + live readout under the knob (number in Plex Mono, λ in Sans)
    lbl, flbl = "spacing", fnt(SANS, 9.5)
    dr.text((dcx - dr.textlength(lbl, font=flbl) / 2, s(5)), lbl, font=flbl, fill=MUTED)
    num, fnum, fun = f"{boom_l:.2f} ", fnt(MONO, 10.5), fnt(SANS, 10.5)
    wn = dr.textlength(num, font=fnum)
    x0 = dcx - (wn + dr.textlength("λ", font=fun)) / 2
    dr.text((x0, s(67)), num, font=fnum, fill=LIGHT)
    dr.text((x0 + wn, s(67)), "λ", font=fun, fill=LIGHT)

    # geometry (Moxon top view; element -> horizontal, boom -> vertical)
    def gp(pt):
        return (s(GCX) + (pt[1] / EL) * s(GW), s(GCY) - (pt[0] / BM) * s(GH))

    for a, b in struct:
        dr.line([gp(a), gp(b)], fill=ACCENT, width=lw(2), joint="curve")
    fx, fy = gp((fmid[0], fmid[1]))
    dr.ellipse([fx - s(2.6), fy - s(2.6), fx + s(2.6), fy + s(2.6)], fill=WHITE)
    # pattern (azimuth-cut outline)
    pcx, pcy, pr = s(PCX), s(PCY), s(PR)
    for fr in (0.5, 1.0):
        dr.ellipse(
            [pcx - pr * fr, pcy - pr * fr, pcx + pr * fr, pcy + pr * fr],
            outline=GRID,
            width=lw(1),
        )
    dr.line([pcx - pr, pcy, pcx + pr, pcy], fill=GRID, width=lw(1))
    dr.line([pcx, pcy - pr, pcx, pcy + pr], fill=GRID, width=lw(1))
    pts = [
        (pcx + pr * rr * math.cos(p), pcy - pr * rr * math.sin(p))
        for rr, p in zip(r, ph)
    ]
    dr.line(pts + [pts[0]], fill=ACCENT, width=lw(2), joint="curve")


# The aspect_ratio sweep (element spacing); index into it with draw_panels' step.
SWEEP = [0.300, 0.335, 0.370, 0.400, 0.420, 0.440]
SWEEP_DATA = [moxon_data(v) for v in SWEEP]
HERO = len(SWEEP) - 1  # widest spacing: clean forward beam, deep null, tallest geometry


def brandmark(dr, x, y, semi_pt=15, tag=True):
    """Draw the 'AntennaKNoBs · by KK7KNB' wordmark at (x, y) in 1x coords."""
    fb = fnt(SEMI, semi_pt)
    dr.text((s(x), s(y)), "Antenna", font=fb, fill=WHITE)
    wA = dr.textlength("Antenna", font=fb)
    dr.text((s(x) + wA, s(y)), "KNoBs", font=fb, fill=ACCENT)
    wK = dr.textlength("KNoBs", font=fb)
    if tag:
        dr.text(
            (s(x) + wA + wK + s(7), s(y) + s(2)),
            "· by KK7KNB",
            font=fnt(SANS, 10.5),
            fill=MUTED,
        )


def accent_bar(dr):
    dr.rectangle([0, 0, W * S, s(2)], fill=ACCENT)


def fit_pt(dr, text, start, maxw, weight=BOLD):
    """Largest point size (from ``start``, stepping down) at which ``text`` fits
    within ``maxw`` 1x px in ``weight``."""
    p = start
    while dr.textlength(text, font=fnt(weight, p)) > s(maxw) and p > 10:
        p -= 0.5
    return p


def new_canvas():
    """A fresh 3x RGB canvas filled with the app background."""
    return Image.new("RGB", (W * S, H * S), BG)


def downscale(im):
    return im.resize((W, H), Image.LANCZOS)


def save_gif(frames, out, *, duration, colors=200):
    """Delta-frame encode 1x RGB ``frames`` to ``out`` (disposal=1, shared
    palette, optimize) and return the file size in bytes."""
    master = Image.new("RGB", (W, H * len(frames)))
    for i, fr in enumerate(frames):
        master.paste(fr, (0, i * H))
    pal = master.quantize(colors=colors, dither=Image.Dither.NONE)
    fp = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    fp[0].save(
        out,
        save_all=True,
        append_images=fp[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=1,
    )
    return os.path.getsize(out)


def save_png(frame, out, colors=200):
    frame.quantize(colors=colors, dither=Image.Dither.NONE).save(out, optimize=True)
    return os.path.getsize(out)
