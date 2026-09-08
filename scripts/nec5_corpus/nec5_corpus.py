#!/usr/bin/env python3
"""nec5_corpus.py -- a NEC-5 regression corpus from the public NEC-2 decks.

Three steps, one file, standard library only (Python 3.8 or newer):

    python nec5_corpus.py fetch     --out raw
    python nec5_corpus.py translate --src raw  --out nec5
    python nec5_corpus.py check     --exe NEC5CL.exe --src nec5

`fetch` downloads the deck collections listed in SOURCES straight from their
publishers (GitHub repositories, the ARRL and Cebik archives, a few personal
sites) into raw/<source>/..., keeping the original file names, and writes
raw/LICENSES.md saying where each set came from and under what terms. Nothing
is redistributed by this script; every deck comes from its own source.

`translate` turns each NEC-2 / 4nec2-dialect deck into a deck NEC-5 reads:

  * dialect: 4nec2 `SY` symbols are evaluated and substituted, comma and tab
    separators become spaces, fused mnemonics (`GW1,8,...`) are split,
    `'` comments and `#nn` AWG gauges are resolved, Fortran D exponents fixed;
  * sources at KNOTS: NEC-2 puts a source at the CENTRE of a segment, NEC-5
    puts it at a segment END (a knot). A wire fed at the centre of its middle
    segment with an odd segment count gets one more segment so that its
    centre is a knot; an even count already has a centre knot. Off-centre
    feeds move half a segment toward the wire's centre (`--offcenter shift`,
    the default, with the move recorded in a CM card) or the wire's mesh is
    doubled so the old centre is a knot exactly (`--offcenter double`).
    The same rule addresses discrete loads and TL/NT ports, which NEC-5 also
    attaches at knots. The NEC-2 print flag in the EX card's 4th field is
    replaced by NEC-5's end selector (a leftover `10` there makes NEC-5 stop);
  * excitation types: EX 0 stays a voltage source; 4nec2's EX 6 current
    source becomes NEC-5's EX 4 knot current source; EX 5 (current-slope
    voltage source) becomes EX 0; EX 1-3 plane waves pass through; a NEC-2
    EX 4 (elementary current source in space) has no NEC-5 counterpart and
    the deck is refused;
  * ground: GN -1 / GN 1 / GN 2 pass; NEC-2's GN 0 reflection-coefficient
    ground becomes NEC-5's GN 0, which is a Sommerfeld ground (noted); the
    radial-screen and second-medium fields NEC-2 carries on GN, and the GD
    card, are dropped with a note -- NEC-5 has no spelling for them and
    misreads the fields if they are left in;
  * cards NEC-5 does not have (EK, KH, CP, IS) are dropped with a note;
    NX multi-structure decks are split into one deck per structure.

Every transformation is written into the output deck as a `CM nec5_corpus:`
line, and a JSON-lines report records it per deck.

`check` runs every translated deck through a NEC-5 executable (file names on
stdin, the way NEC5CL asks for them) and reports which decks it reads, which
it refuses and with what message, and the driving-point impedance of each.

Conventions were verified against a NEC-5 executable, not taken from its
source: TL/NT (tag, seg) addresses knot `seg` (= end 2 of segment `seg`);
LD's 4th field is an end selector for discrete loads (a NEC-2 segment RANGE
collapses to one load unless expanded, which this script does); distributed
loads (LD 2/3/5) keep segment ranges; GN 2 and GN 0 are the same Sommerfeld
ground; EX 5 and EX 6 are rejected; EK, KH and CP stop the run.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.0"
DECK_EXTS = (".nec", ".inp")  # matched case-insensitively

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
# kind "github": owner/repo archive of the default branch, `subtree` selects a
# folder (empty = whole repo). kind "zips": direct zip URLs. kind "index": an
# HTML page whose links to .nec files are followed. kind "files": individual
# files, renamed. kind "html": decks published inline in web pages.
SOURCES = [
    {
        "name": "arrl",
        "kind": "zips",
        "urls": [
            "https://www.arrl.org/files/file/Technology/Antenna%20Models/dipoles.zip",
            "https://www.arrl.org/files/file/Technology/Antenna%20Models/other.zip",
        ],
        "licence": "ARRL public-domain antenna models (arrl.org/antenna-modeling-files).",
    },
    {
        "name": "cebik-w4rnl",
        "kind": "zips",
        "urls": [
            "https://antenna2.github.io/cebik/content/download/nec2-examples.zip",
            "https://antenna2.github.io/cebik/content/download/nec4-examples.zip",
            "https://antenna2.github.io/cebik/content/classes/models.zip",
            "https://antenna2.github.io/cebik/books/Basic-Intermediate-Tutorial-Models.zip",
            "https://antenna2.github.io/cebik/books/Moxon-Rectangle-Notes-Models.zip",
        ],
        "licence": (
            "Copyright L. B. Cebik, W4RNL (SK). Course and article models, distributed "
            "free on his site and mirrored at antenna2.github.io/cebik; no redistribution "
            "grant is stated. Fetch for your own use."
        ),
    },
    {
        "name": "4nec2-models",
        "kind": "github",
        "repo": "handiko/AntennaFiles-OLD",
        "subtree": "4nec2_models",
        "licence": (
            "The models folder bundled with Arie Voors' 4nec2 (freeware); no separate "
            "licence statement for the models. Mirror repository is GPL-3.0."
        ),
    },
    {
        "name": "necpp",
        "kind": "github",
        "repo": "tmolteno/necpp",
        "subtree": "testharness/data",
        "licence": "nec2++ regression decks, GPL-2.0.",
    },
    {
        "name": "nec2c",
        "kind": "github",
        "repo": "KJ7LNW/nec2c",
        "subtree": "Input",
        "licence": "nec2c distribution input decks (5B4AZ), GPL-3.0.",
    },
    {
        "name": "g1ojs",
        "kind": "github",
        "repo": "G1OJS/G1OJS",
        "subtree": "nec files",
        "licence": "Alan G1OJS's model library, GPL-3.0.",
    },
    {
        "name": "antenna-modeling",
        "kind": "github",
        "repo": "sconklin/Antenna-Modeling",
        "subtree": "",
        "licence": "Steve Conklin's ham antenna models; no licence stated.",
    },
    {
        "name": "sokyrad",
        "kind": "github",
        "repo": "nathanielbutts/SOKYRAD",
        "subtree": "antenna_analysis",
        "licence": "SOKYRAD antenna analysis decks, GPL-3.0.",
    },
    {
        "name": "rchacker-antennas",
        "kind": "github",
        "repo": "rchacker/antennas",
        "subtree": "",
        "licence": "FPV / drone antenna models; no licence stated.",
    },
    {
        "name": "qantenna",
        "kind": "github",
        "repo": "groleo/qantenna",
        "subtree": "examples",
        "licence": "QAntenna example decks, GPL-2.0.",
    },
    {
        "name": "nec-simulations",
        "kind": "github",
        "repo": "maestroque/nec-simulations",
        "subtree": "",
        "licence": "University coursework decks (AUTh); no licence stated.",
    },
    {
        "name": "arthurcadore",
        "kind": "github",
        "repo": "arthurcadore/antenna-modelling",
        "subtree": "4nec2files",
        "licence": "MIT.",
    },
    {
        "name": "nec2-toys",
        "kind": "github",
        "repo": "LordPythonn/nec2-toys",
        "subtree": "",
        "licence": "MIT.",
    },
    {
        "name": "opennec",
        "kind": "github",
        "repo": "maurymarkowitz/OpenNEC",
        "subtree": "examples",
        "toplevel_only": True,
        "licence": "OpenNEC examples (top level only; the DL5SAY folder duplicates nec2c); no licence stated.",
    },
    {
        "name": "arcanum",
        "kind": "github",
        "repo": "OpenResearchInstitute/Arcanum",
        "subtree": "docs/nec-import/reference-decks",
        "licence": "Open Research Institute Arcanum reference decks, GPL-3.0.",
    },
    {
        "name": "xnec2c-fixtures",
        "kind": "github",
        "repo": "KJ7LNW/xnec2c",
        "subtree": "t/fixtures",
        "licence": "xnec2c parser fixtures, GPL-3.0.",
    },
    {
        "name": "icecube-dbesson",
        "kind": "index",
        "urls": ["https://user-web.icecube.wisc.edu/~dbesson/antcal/nec-files/"],
        "licence": (
            "Open directory on Prof. Dave Besson's IceCube antenna-calibration page; mostly "
            "a mirror of the 4nec2 example library plus K6STI's classic set; no licence stated."
        ),
    },
    {
        "name": "w8io",
        "kind": "index",
        "urls": [
            "http://www.w8io.com/VHF-antennas.htm",
            "http://www.w8io.com/Optimized-LPDA.htm",
            "http://www.w8io.com/nec-benchmarks.htm",
        ],
        "licence": (
            "W8IO's VHF/UHF Yagi and LPDA archive, including designs he re-modelled from "
            "many designers (per-file callsign in the CM cards); no licence stated."
        ),
    },
    {
        "name": "nec2org",
        "kind": "files",
        "files": [
            ("https://www.nec2.org/biqdfeed.txt", "biquad_2440MHz.nec"),
            ("https://www.nec2.org/coffee.txt", "coffee_can_2.4GHz.nec"),
        ],
        "licence": "nec2.org (Trevor Marshall) example decks; no licence stated.",
    },
    {
        "name": "kk4obi-bent-dipoles",
        "kind": "html",
        "files": [
            (
                "https://www.qsl.net/kk4obi/Models/KK4OBI bend model - Std Vertical Dipole.html",
                "std-vertical-dipole.nec",
            ),
            (
                "https://www.qsl.net/kk4obi/Models/KK4OBI model - Folded-End Dipoles.html",
                "folded-end-dipole.nec",
            ),
            (
                "https://www.qsl.net/kk4obi/Models/KK4OBI model - OCF Vertical 4-Radials.html",
                "ocf-vertical-4radials.nec",
            ),
            (
                "https://www.qsl.net/kk4obi/Models/KK4OBI model - EFHW Straight.html",
                "efhw-straight.nec",
            ),
        ],
        "licence": "KK4OBI's bent-dipole models, published inline on qsl.net/kk4obi; no licence stated.",
    },
]

_GEOMETRY_CARD = re.compile(
    r"^\s*(GW|GA|GH|SP|SM|GM|GR|GX|GC)\s*[\d,\s.+-]", re.I | re.M
)
_USER_AGENT = "nec5_corpus.py/" + VERSION


def _log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
def _get(url: str, retries: int = 3) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310 — https/http URLs from the SOURCES table only
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — same
                return r.read()
        except (urllib.error.URLError, OSError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"download failed after {retries} attempts: {url}: {last}")


def _looks_like_deck(data: bytes) -> bool:
    if b"\x00" in data[:4096]:
        return False
    text = data.decode("latin-1")
    if not _GEOMETRY_CARD.search(text):
        return False
    cards = sum(1 for ln in text.splitlines() if ln[:2].isalpha())
    return cards >= 5


def _is_deck_name(name: str) -> bool:
    return name.lower().endswith(DECK_EXTS)


class _Sink:
    """Writes fetched decks under raw/<source>/, deduplicating by content."""

    def __init__(self, out: Path, source: str):
        self.dir = out / source
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seen = set()
        self.kept = 0
        self.skipped = 0

    def put(self, relpath: str, data: bytes) -> None:
        if not _looks_like_deck(data):
            self.skipped += 1
            return
        h = hashlib.sha1(data).hexdigest()
        if h in self.seen:
            self.skipped += 1
            return
        self.seen.add(h)
        rel = relpath.replace("\\", "/").lstrip("/")
        rel = re.sub(r"[^\w./ ()+-]", "_", rel)  # Windows-hostile characters
        dest = self.dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest = dest.with_name(dest.stem + "_" + h[:6] + dest.suffix)
        dest.write_bytes(data)
        self.kept += 1


def _fetch_zip_members(
    data: bytes, sink: _Sink, prefix_strip: int, subtree: str, toplevel_only: bool
):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir() or not _is_deck_name(info.filename):
                continue
            parts = info.filename.split("/")[prefix_strip:]
            rel = "/".join(parts)
            if subtree:
                if not rel.startswith(subtree.rstrip("/") + "/"):
                    continue
                rel = rel[len(subtree.rstrip("/")) + 1 :]
            if toplevel_only and "/" in rel:
                continue
            sink.put(rel, zf.read(info))


def _links(page: bytes, base: str) -> list:
    text = page.decode("latin-1")
    out = []
    for m in re.finditer(r"""href\s*=\s*["']?([^"'\s>]+)""", text, re.I):
        href = html.unescape(m.group(1))
        if _is_deck_name(href):
            out.append(urllib.parse.urljoin(base, href))
    return sorted(set(out))


def _deck_from_html(page: bytes) -> bytes:
    """A deck published inline in a web page (qsl.net/kk4obi): one card per
    `<br>`, physical line breaks INSIDE a card, `&nbsp;` as spacing. Cards
    are rejoined, tags stripped, entities decoded, and the lines that read
    as NEC cards from the first CM/CE/SY to EN are kept."""
    text = page.decode("latin-1")
    text = re.sub(r"[\r\n]+", " ", text)  # wrapped card continues on the same line
    text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = []
    started = False
    for ln in text.splitlines():
        s = re.sub(r"\s+", " ", ln).strip()
        if not s:
            continue
        if not started and re.match(r"^(CM\b|CE$|CE\s|SY\s+\w+\s*=|GW\s*\d)", s):
            started = True
        if not started:
            continue
        if re.match(r"^[A-Z]{2}(\s|$|[\d,.+-])", s) or s.startswith("'"):
            lines.append(s)
        if s.upper().startswith("EN") and len(s) <= 3:
            break
    return ("\n".join(lines) + "\n").encode("latin-1", errors="replace")


def cmd_fetch(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None
    licences = [
        "# Sources and terms",
        "",
        "Fetched by nec5_corpus.py " + VERSION + ".",
        "",
    ]
    failures = 0
    for src in SOURCES:
        name = src["name"]
        if only and name not in only:
            continue
        sink = _Sink(out, name)
        origin = src.get("repo") or ", ".join(
            src.get("urls", []) or [u for u, _ in src.get("files", [])]
        )
        _log(f"[{name}] {origin}")
        try:
            if src["kind"] == "github":
                url = f"https://github.com/{src['repo']}/archive/HEAD.zip"
                _fetch_zip_members(
                    _get(url),
                    sink,
                    1,
                    src.get("subtree", ""),
                    src.get("toplevel_only", False),
                )
            elif src["kind"] == "zips":
                for url in src["urls"]:
                    _fetch_zip_members(_get(url), sink, 0, "", False)
            elif src["kind"] == "index":
                for url in src["urls"]:
                    for link in _links(_get(url), url):
                        try:
                            sink.put(
                                urllib.parse.unquote(link.rsplit("/", 1)[-1]),
                                _get(link),
                            )
                        except RuntimeError as e:  # one dead link is not a dead source
                            _log(f"    skip {link}: {e}")
            elif src["kind"] == "files":
                for url, fname in src["files"]:
                    sink.put(fname, _get(url))
            elif src["kind"] == "html":
                for url, fname in src["files"]:
                    quoted = urllib.parse.quote(url, safe=":/")
                    sink.put(fname, _deck_from_html(_get(quoted)))
        except (RuntimeError, zipfile.BadZipFile, OSError) as e:
            failures += 1
            _log(f"    FAILED: {e}")
        _log(
            f"    kept {sink.kept} decks, skipped {sink.skipped} (duplicates / not decks)"
        )
        licences.append(
            f"## {name}\n\n{src['licence']}\n\nFrom: {origin}\n\nDecks kept: {sink.kept}\n"
        )
    (out / "LICENSES.md").write_text("\n".join(licences), encoding="utf-8")
    _log(f"\nwrote {out / 'LICENSES.md'}; {failures} source(s) failed")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# dialect normalisation (4nec2 SY symbols, commas, fused mnemonics, comments)
# ---------------------------------------------------------------------------
class DeckError(ValueError):
    """The deck cannot be read (malformed card, undefined symbol, ...)."""


class Refused(ValueError):
    """The deck is readable but has no faithful NEC-5 spelling."""


_PLAIN_NUM_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\Z")

_SY_FUNCS = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "atn": lambda x: math.degrees(math.atan(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "sqr": math.sqrt,
    "sqrt": math.sqrt,
    "abs": abs,
    "int": lambda x: float(int(x)),
    "log": math.log,
    "exp": math.exp,
}
_SY_CONSTANTS = {
    "pi": math.pi,
    "mm": 1e-3,
    "cm": 1e-2,
    "dm": 0.1,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
    "pf": 1e-12,
    "nf": 1e-9,
    "uf": 1e-6,
    "nh": 1e-9,
    "uh": 1e-6,
    "mh": 1e-3,
}
_SY_UNITS = frozenset(
    ("mm", "cm", "dm", "m", "in", "ft", "pf", "nf", "uf", "nh", "uh", "mh")
)
_SY_TOKEN = re.compile(
    r"\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|([A-Za-z_]\w*)|([()+\-*/^%]))"
)
_SY_BP = {
    "+": (10, 11),
    "-": (10, 11),
    "*": (20, 21),
    "/": (20, 21),
    "%": (20, 21),
    "^": (40, 39),
}
_SY_UNARY_BP = 30


def _eval_sy_expr(expr: str, syms: dict, where: str) -> float:
    """4nec2's BASIC-flavoured expression grammar: `^` power (right-assoc,
    tighter than unary minus), trig in degrees, `sqr` = sqrt, juxtaposed
    units (`135 ft`, `36.6pF`). Precedence climbing, no eval()."""
    text = expr.strip()

    def err(msg):
        return DeckError(f"{where}: SY expression {expr!r}: {msg}")

    # `#14` / `#12/ft` wire-gauge shorthand inside an expression
    # (`SY rw=#14/in`): substitute its value before tokenising.
    text = re.sub(
        r"#(\d+)(?:/([A-Za-z]+))?",
        lambda m: repr(_value(m.group(0), where, syms)),
        text,
    )

    if not text:
        raise err("empty")
    tokens = []
    pos = 0
    while pos < len(text):
        m = _SY_TOKEN.match(text, pos)
        if m is None or m.end() == m.start():
            rest = text[pos:].lstrip()
            if not rest:
                break
            raise err(f"unexpected character {rest[0]!r}")
        pos = m.end()
        num, ident, op = m.group(1), m.group(2), m.group(3)
        if num is not None:
            tokens.append(("num", float(num)))
        elif ident is not None:
            tokens.append(("ident", ident.lower()))
        else:
            tokens.append(("op", op))
        if len(tokens) > 128:
            raise err("more than 128 tokens")
    if not tokens:
        raise err("empty")
    idx = [0]

    def peek():
        return tokens[idx[0]] if idx[0] < len(tokens) else (None, None)

    def take():
        t = tokens[idx[0]]
        idx[0] += 1
        return t

    def finite(v, what):
        if not math.isfinite(v):
            raise err(f"{what} is not finite")
        return v

    def lookup(name):
        if name in syms:
            return syms[name]
        if name in _SY_CONSTANTS:
            return _SY_CONSTANTS[name]
        raise DeckError(f"{where}: undefined symbol {name!r}")

    def primary(depth):
        kind, val = peek()
        if kind == "num":
            take()
            v = float(val)
            k2, v2 = peek()
            if k2 == "ident" and v2 in _SY_UNITS:
                nxt = tokens[idx[0] + 1] if idx[0] + 1 < len(tokens) else (None, None)
                if nxt != ("op", "("):
                    take()
                    v *= lookup(v2)
            return v
        if kind == "ident":
            take()
            if peek() == ("op", "("):
                fn = _SY_FUNCS.get(val)
                if fn is None:
                    raise err(f"unknown function {val!r}")
                take()
                arg = climb(0, depth + 1)
                if peek() != ("op", ")"):
                    raise err(f"expected ')' after {val}(...)")
                take()
                try:
                    return finite(float(fn(arg)), f"{val}(...)")
                except (ArithmeticError, ValueError) as e:
                    raise err(f"{val}({arg:g}) failed: {e}") from None
            return lookup(val)
        if kind == "op" and val == "(":
            take()
            v = climb(0, depth + 1)
            if peek() != ("op", ")"):
                raise err("unbalanced parenthesis")
            take()
            return v
        if kind == "op" and val in ("-", "+"):
            take()
            v = climb(_SY_UNARY_BP, depth + 1)
            return -v if val == "-" else v
        if kind is None:
            raise err("ends unexpectedly")
        raise err(f"unexpected {val!r}")

    def apply(op, a, b):
        try:
            if op == "+":
                r = a + b
            elif op == "-":
                r = a - b
            elif op == "*":
                r = a * b
            elif op == "/":
                r = a / b
            elif op == "%":
                if b == 0.0:
                    raise ZeroDivisionError("modulo by zero")
                r = math.fmod(a, b)
            else:
                r = a**b
        except (ArithmeticError, ValueError) as e:
            raise err(f"'{a:g} {op} {b:g}' failed: {e}") from None
        return finite(r, f"'{a:g} {op} {b:g}'")

    def climb(min_bp, depth):
        if depth > 32:
            raise err("nested deeper than 32")
        lhs = primary(depth)
        while True:
            kind, val = peek()
            if kind != "op" or val not in _SY_BP:
                return lhs
            lbp, rbp = _SY_BP[val]
            if lbp < min_bp:
                return lhs
            take()
            rhs = climb(rbp, depth + 1)
            lhs = apply(val, lhs, rhs)

    result = climb(0, 0)
    if idx[0] != len(tokens):
        raise err(f"unexpected {tokens[idx[0]][1]!r} after a complete expression")
    return finite(float(result), "result")


def _define_sy(rest: str, syms: dict, where: str) -> None:
    body = rest.split("'", 1)[0].strip()
    if not body:
        raise DeckError(f"{where}: SY card without an assignment")
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    for part in parts:
        if "=" not in part:
            raise DeckError(f"{where}: SY assignment {part.strip()!r} has no '='")
        name, expr = part.split("=", 1)
        name = name.strip()
        if not name.isidentifier():
            raise DeckError(f"{where}: SY name {name!r} is not a valid symbol")
        syms[name.lower()] = _eval_sy_expr(expr, syms, where)


def _value(token: str, where: str, syms: dict) -> float:
    if token.startswith("#"):
        # 4nec2 AWG shorthand: `#14` is the wire RADIUS in metres; `#12/ft`
        # or `#14/in` is that radius in the deck's own length unit (decks
        # that scale with GS 0 0 0.3048 write their radii in feet too).
        gauge_txt, _, unit = token[1:].partition("/")
        try:
            gauge = int(gauge_txt)
        except ValueError:
            raise DeckError(f"{where}: bad wire gauge {token!r}") from None
        radius_m = 0.5 * 0.127e-3 * 92.0 ** ((36.0 - gauge) / 39.0)
        if unit:
            factor = _SY_CONSTANTS.get(unit.lower())
            if factor is None:
                raise DeckError(f"{where}: unknown unit in wire gauge {token!r}")
            return radius_m / factor
        return radius_m
    try:
        return float(token)
    except ValueError:
        pass
    try:
        return float(token.upper().replace("D", "E"))
    except ValueError:
        pass
    if any(c.isalpha() or c in "()*/+-^" for c in token):
        return _eval_sy_expr(token, syms, where)
    raise DeckError(f"{where}: bad number {token!r}")


def _format_field(v: float) -> str:
    """A resolved card field as NEC-5's parser reads it: integral values
    without a decimal point, everything else to 10 significant digits (a
    17-digit Python repr such as 1.8069109999999999E-06 is rejected as an
    INVALID NUMBER)."""
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.10g}"


class Card:
    __slots__ = ("mn", "f", "line")

    def __init__(self, mn: str, fields: list, line: int):
        self.mn = mn
        self.f = fields
        self.line = line

    def num(self, k: int, default: float = 0.0) -> float:
        if k >= len(self.f):
            return default
        try:
            return float(self.f[k])
        except ValueError:
            raise DeckError(
                f"line {self.line}: {self.mn} field {k + 1} {self.f[k]!r} is not numeric"
            ) from None

    def int(self, k: int, default: int = 0) -> int:
        """An integer field. A fractional value (a 4nec2 SY expression that
        did not come out whole, e.g. a segment count of 20.3) is truncated
        the way 4nec2 reads it, and the card is rewritten with the integer."""
        v = self.num(k, float(default))
        if v != int(v):
            self.f[k] = str(int(v))
        return int(v)

    def text(self) -> str:
        return " ".join([self.mn, *self.f])


def _split_fields(line: str) -> list:
    """Card fields. A TAB-delimited 4nec2 card may carry an expression with
    spaces inside one field (`GM 0 0 0 0 0 Fx 0 Fz + 0.24529 100`), so tabs
    and commas split first and a tab field is only split further on spaces
    when it is plain numbers (a mixed tab/space deck)."""
    if "\t" not in line:
        return line.replace(",", " ").split()
    out = []
    for field in re.split(r"[\t,]+", line):
        field = field.strip()
        if not field:
            continue
        if " " in field and not re.search(r"[A-Za-z_#^*/]", field):
            out.extend(field.split())
        elif (
            " " in field and re.search(r"[+\-*/^]", field) and not field.startswith("'")
        ):
            out.append(field.replace(" ", ""))
        else:
            out.extend(field.split()) if " " in field else out.append(field)
    return out


def _close_parens(line: str) -> str:
    """Remove whitespace (and separating commas) inside balanced parentheses."""
    out, depth = [], 0
    for ch in line:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth > 0 and ch in " \t,":
            continue
        out.append(ch)
    return "".join(out)


def normalize(text: str, name: str) -> tuple:
    """(comment lines, cards) with SY resolved, separators normalised."""
    syms = {}
    comments = []
    cards = []
    in_comments = True
    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("'"):
            continue
        where = f"{name}, line {line_no}"
        head = stripped[:2].upper()
        if head == "CM":
            if in_comments:
                comments.append(stripped[2:].strip())
            continue
        if head == "CE":
            if in_comments:
                rest = stripped[2:].strip()
                if rest:
                    comments.append(rest)
                in_comments = False
            continue
        stripped = stripped.split("'", 1)[0].rstrip()
        if not stripped:
            continue
        # 4nec2 allows spaces inside a parenthesised expression
        # (`GM 0 0 0 0 0 (rH - 0.0655 - clSep) 0 0.1032 1`); close them up
        # so the expression stays one field.
        if "(" in stripped:
            stripped = _close_parens(stripped)
        tokens = _split_fields(stripped)
        if (
            len(tokens[0]) > 2
            and tokens[0][:2].isalpha()
            and tokens[0][2] in "0123456789.+-"
        ):
            tokens = [tokens[0][:2], tokens[0][2:], *tokens[1:]]
        mn = tokens[0].upper()
        if len(mn) != 2 or not mn.isalpha():
            raise DeckError(f"{where}: expected a NEC card mnemonic, got {tokens[0]!r}")
        if mn == "SY":
            _define_sy(stripped[2:], syms, where)
            continue
        in_comments = False
        fields = []
        for tok in tokens[1:]:
            if _PLAIN_NUM_RE.fullmatch(tok):
                # Kept byte-for-byte unless it is longer than NEC-5's field
                # parser accepts (a 17-digit 5.3125128000000016E-14 is an
                # INVALID NUMBER to it).
                fields.append(tok if len(tok) <= 12 else _format_field(float(tok)))
                continue
            try:
                fields.append(_format_field(_value(tok, where, syms)))
            except DeckError:
                fields.append(tok)  # filename fields (GN ... NOFILE) look like symbols
        cards.append(Card(mn, fields, line_no))
        if mn == "EN":
            break
    return comments, cards


# ---------------------------------------------------------------------------
# translation
# ---------------------------------------------------------------------------
_DROP_CARDS = {
    "EK": "EK (NEC-2 extended thin-wire kernel) dropped: not a NEC-5 command",
    "KH": "KH (NEC-2 interaction-approximation distance) dropped: not a NEC-5 command",
    "CP": "CP (NEC-2 coupling calculation) dropped: not a NEC-5 command",
    "GD": "GD (NEC-2 second medium / cliff) dropped: NEC-5 has no second-medium spelling",
    "IS": "IS (NEC-4 insulated sheath) dropped: NEC-5 has no insulated-wire card; the wire is bare here",
    "JN": "JN (NEC-4 junction card) dropped: not a NEC-5 command",
}
_REFUSE_CARDS = {
    "CW": "CW (NEC-4 catenary wire) has no NEC-5 counterpart",
    "SM": "SM (NEC-2 multiple-patch surface) is rejected by NEC-5 (DATAGN input error); rewrite as SP patches",
    "GF": "GF (NEC-2 numerical Green's function read) has no NEC-5 counterpart",
    "WG": "WG (NEC-2 numerical Green's function write) has no NEC-5 counterpart",
}
_SYNTHETIC_TAG_BASE = 9001


class Geometry:
    """Segment counts per geometry card, tag GROUPS (NEC numbers the segments
    of a tag across every card and copy carrying it, in order), and the
    absolute segment order -- from the NEC-2 geometry cards including the
    copies GM / GX / GR generate."""

    def __init__(self):
        self.root_n = {}  # root card id -> segment count (as authored)
        self.root_card = {}  # root card id -> Card (GW/GA/GH) to rewrite
        self.groups = {}  # tag -> [root, root, ...] in tag-relative order
        self.order = []  # (tag, root, index in group) per absolute segment
        self.notes = []
        self._next_synthetic = _SYNTHETIC_TAG_BASE

    def _append(self, tag: int, root: int):
        grp = self.groups.setdefault(tag, [])
        grp.append(root)
        self.order.extend([(tag, root, len(grp) - 1)] * self.root_n[root])

    def _add_wire(self, card: Card):
        tag = card.int(0)
        n = card.int(1)
        if n <= 0:
            raise DeckError(f"line {card.line}: {card.mn} with {n} segments")
        if tag == 0:
            tag = self._next_synthetic
            self._next_synthetic += 1
            card.f[0] = str(tag)
            self.notes.append(
                f"untagged {card.mn} on line {card.line} given tag {tag} (NEC-5 addresses by tag)"
            )
        root = id(card)
        self.root_n[root] = n
        self.root_card[root] = card
        self._append(tag, root)

    def _copy(self, tag_inc: int, which):
        for tag, root, _ in which:
            self._append(tag + tag_inc if tag_inc > 0 else tag, root)

    @staticmethod
    def _its_range(field: str):
        """GM's last field: ITS, or NEC-4's ITS1.ITS2 tag range (`004.006`)."""
        if field in ("", "-", "+"):
            return 0, 0
        m = re.fullmatch(r"(\d+)\.(\d{3})", field)
        if m:
            return int(m.group(1)), int(m.group(2))
        try:
            return int(float(field)), 0
        except ValueError:
            return 0, 0

    def _instances(self):
        """One (tag, root, gidx) per card instance, in absolute order."""
        out = []
        for entry in self.order:
            if not out or out[-1] != entry:
                out.append(entry)
        return out

    def feed(self, card: Card):
        mn = card.mn
        if mn in ("GW", "GA", "GH"):
            self._add_wire(card)
        elif mn == "GM":
            itsi, nrpt = card.int(0), card.int(1)
            its1, its2 = self._its_range(card.f[8]) if len(card.f) > 8 else (0, 0)
            if nrpt > 0:
                which = [
                    e
                    for e in self._instances()
                    if its1 <= 0 or (e[0] >= its1 and (its2 <= 0 or e[0] <= its2))
                ]
                for i in range(1, nrpt + 1):
                    self._copy(itsi * i if itsi > 0 else 0, which)
        elif mn == "GX":
            its = card.int(0)
            planes = str(card.int(1)).zfill(3)
            k = 1
            for bit in planes:
                if bit == "1":
                    self._copy(its * k if its > 0 else 0, self._instances())
                    k *= 2
        elif mn == "GR":
            its, nrpt = card.int(0), card.int(1)
            base = self._instances()
            for i in range(1, max(nrpt, 1)):
                self._copy(its * i if its > 0 else 0, base)

    def group_size(self, tag: int) -> int:
        return sum(self.root_n[r] for r in self.groups[tag])

    def resolve(self, tag: int, seg: int, what: str, line: int):
        """(tag, root, group index, local seg) for a NEC-2 (tag, seg)
        address; tag 0 means an absolute segment number."""
        if tag == 0:
            if not 1 <= seg <= len(self.order):
                raise DeckError(
                    f"line {line}: {what} absolute segment {seg} outside 1..{len(self.order)}"
                )
            t, root, gidx = self.order[seg - 1]
            local = 1
            i = seg - 2
            while i >= 0 and self.order[i] == (t, root, gidx):
                local += 1
                i -= 1
            return t, root, gidx, local
        grp = self.groups.get(tag)
        if grp is None:
            raise DeckError(
                f"line {line}: {what} addresses tag {tag}, which no geometry card defines"
            )
        total = self.group_size(tag)
        if not 1 <= seg <= total:
            raise DeckError(
                f"line {line}: {what} addresses segment {seg} of tag {tag}, which has {total}"
            )
        left = seg
        for gidx, root in enumerate(grp):
            n = self.root_n[root]
            if left <= n:
                return tag, root, gidx, left
            left -= n
        raise AssertionError("unreachable")

    def all_segments(self, tag: int):
        """Every (tag, root, gidx, local) of a tag, for tag-wide addressing."""
        out = []
        for gidx, root in enumerate(self.groups[tag]):
            out.extend((tag, root, gidx, s) for s in range(1, self.root_n[root] + 1))
        return out


class Remesh:
    """Per geometry card: the NEC-2 segment count, the NEC-5 count, and the
    knot each referenced segment centre maps to."""

    def __init__(self, geo: Geometry, policy: str):
        self.geo = geo
        self.policy = policy
        self.refs = {}  # root -> set of local segment numbers referenced as centres
        self.new_n = {}
        self.notes = []

    def want(self, ref):
        self.refs.setdefault(ref[1], set()).add(ref[3])

    @staticmethod
    def _knot_of(seg: int, n: int, n2: int) -> int:
        pos = (seg - 0.5) / n * n2
        if abs(pos - round(pos)) < 1e-9:
            return int(round(pos))
        k = math.ceil(pos) if pos < n2 / 2 else math.floor(pos)
        return min(max(k, 1), n2 - 1) if n2 > 1 else 1

    def decide(self):
        for root, segs in self.refs.items():
            n = self.geo.root_n[root]
            card = self.geo.root_card[root]
            if self.policy == "double":
                exact = all(n % 2 == 0 and s in (n // 2, n // 2 + 1) for s in segs)
                n2 = n if exact else 2 * n
            else:
                odd_centre = any(n % 2 == 1 and s == (n + 1) // 2 for s in segs)
                n2 = n + 1 if odd_centre else n
                # Distinct segments must stay distinct knots: two TL ports
                # on adjacent segments of a short stub would otherwise land
                # on one knot (a shorted stub merging with an open one).
                knots = {self._knot_of(s, n, n2) for s in segs}
                if len(knots) < len(segs):
                    n2 = 2 * n
                    self.notes.append(
                        f"{card.mn} tag {card.f[0]}: mesh doubled so {len(segs)} referenced "
                        "segments map to distinct knots"
                    )
            self.new_n[root] = n2
            if n2 != n:
                card.f[1] = str(n2)
                self.notes.append(
                    f"{card.mn} tag {card.f[0]}: {n} -> {n2} segments so the referenced "
                    "feed/load/port sits on a knot"
                )

    def _offset(self, tag: int, gidx: int) -> int:
        """Segments of the same tag that precede card `gidx` on the NEW mesh."""
        return sum(
            self.new_n.get(r, self.geo.root_n[r]) for r in self.geo.groups[tag][:gidx]
        )

    def knot(self, ref, what: str) -> int:
        """NEC-5 tag-relative segment whose END 2 is the knot nearest the
        NEC-2 segment centre `ref` addresses (exact after the remesh for a
        centre feed; half a segment toward the wire centre otherwise)."""
        tag, root, gidx, seg = ref
        n = self.geo.root_n[root]
        n2 = self.new_n.get(root, n)
        pos = (seg - 0.5) / n * n2
        k = self._knot_of(seg, n, n2)
        if abs(pos - round(pos)) >= 1e-9:
            self.notes.append(
                f"{what} on tag {tag} segment {seg} of {n} sat mid-segment: moved "
                f"{abs(k - pos):.2f} segment(s) to knot {k} of {n2} (toward the wire centre)"
            )
        return self._offset(tag, gidx) + k

    def map_seg(self, tag: int, s: int) -> int:
        """A NEC-2 tag-relative segment number on the NEW mesh (for ranges)."""
        _, root, gidx, local = self.geo.resolve(tag, s, "range", 0)
        n = self.geo.root_n[root]
        n2 = self.new_n.get(root, n)
        local2 = max(1, min(n2, int(round((local - 0.5) / n * n2 + 0.5))))
        return self._offset(tag, gidx) + local2

    def remap_range(self, tag: int, a: int, b: int):
        """A NEC-2 segment range on a tag (distributed load, PT) on the new mesh."""
        if a == 0 and b == 0:
            return a, b
        total = self.geo.group_size(tag)
        if not 1 <= a <= total:
            return a, b
        b2 = self.map_seg(tag, min(b, total)) if b else 0
        return self.map_seg(tag, a), b2


def _gn(card: Card, nofile: bool, notes: list):
    iperf = card.int(0)
    nradl = card.int(1) if len(card.f) > 1 else 0
    eps = card.f[4] if len(card.f) > 4 else "0"
    sig = card.f[5] if len(card.f) > 5 else "0"
    if iperf == -1:
        return "GN -1"
    if iperf == 1:
        if nradl > 0:
            notes.append(
                f"GN 1: radial screen ({nradl} radials) dropped: NEC-5 has no ground-screen spelling"
            )
        return "GN 1"
    if iperf in (0, 2):
        if iperf == 0:
            notes.append(
                "GN 0: NEC-2's reflection-coefficient ground is NEC-5's Sommerfeld ground "
                "(no reflection-coefficient option exists)"
            )
        if nradl > 0:
            notes.append(
                f"GN {iperf}: radial screen ({nradl} radials) dropped: NEC-5 has no "
                "ground-screen spelling; model radials as wires"
            )
        extra = [x for x in card.f[6:] if x not in ("0", "0.")]
        if extra:
            notes.append(
                "GN: second-medium / cliff fields dropped: NEC-5 has no second-medium spelling"
            )
        line = f"GN 0 0 0 0 {eps} {sig}"
        if nofile:
            line += " 1 0 NOFILE"
        return line
    notes.append(
        f"GN {iperf}: ground type not in the NEC-2 vocabulary, passed through unchanged"
    )
    return card.text()


def _expand_flat_gh(cards: list, notes: list) -> list:
    """4nec2 spells a circular loop as a one-turn helix with turn spacing and
    length of 1e-300 (`GH tag n 1e-300 1e-300 r r 0.99r 0.99r rad`). NEC-5's
    GH computes a zero total wire length from that and stops (ELEMPAR: edge
    length zero). Such a card is written out as the n straight GW pieces
    NEC-2's GH would have generated: angle 2*pi*(i/n)*(HL/S), radius linear
    from (A1, B1) to (A2, B2), z linear over HL -- one segment each, all
    carrying the GH tag, so (tag, seg) addressing is unchanged."""
    out = []
    for c in cards:
        if c.mn != "GH" or len(c.f) < 9:
            out.append(c)
            continue
        ns = c.int(1)
        spacing, length = c.num(2), c.num(3)
        a1, b1, a2, b2 = c.num(4), c.num(5), c.num(6), c.num(7)
        scale = max(abs(a1), abs(b1), abs(a2), abs(b2), 1e-30)
        if ns <= 0 or abs(length) > 1e-6 * scale or spacing == 0.0:
            out.append(c)
            continue
        turns = length / spacing
        pts = []
        for i in range(ns + 1):
            t = i / ns
            ang = 2.0 * math.pi * t * turns
            pts.append(
                (
                    (a1 + (a2 - a1) * t) * math.cos(ang),
                    (b1 + (b2 - b1) * t) * math.sin(ang),
                    length * t,
                )
            )
        for i in range(ns):
            (x1, y1, z1), (x2, y2, z2) = pts[i], pts[i + 1]
            out.append(
                Card(
                    "GW",
                    [c.f[0], "1"]
                    + [_format_field(v) for v in (x1, y1, z1, x2, y2, z2)]
                    + [c.f[8]],
                    c.line,
                )
            )
        notes.append(
            f"GH tag {c.f[0]}: flat one-turn loop (length {length:g}) written as {ns} GW "
            "pieces; NEC-5's GH gives it zero wire length"
        )
    return out


def translate_deck(
    comments: list, cards: list, name: str, policy: str, nofile: bool
) -> tuple:
    """(deck text, notes) for ONE structure (no NX inside)."""
    notes = []
    cards = _expand_flat_gh(cards, notes)
    geo = Geometry()
    in_geometry = True
    for c in cards:
        if in_geometry:
            if c.mn == "GE":
                in_geometry = False
                continue
            if c.mn in _REFUSE_CARDS:
                raise Refused(_REFUSE_CARDS[c.mn])
            if c.mn in ("GW", "GA", "GH", "GM", "GX", "GR"):
                geo.feed(c)
        elif c.mn in _REFUSE_CARDS:
            raise Refused(_REFUSE_CARDS[c.mn])
    notes.extend(geo.notes)
    if not geo.order:
        raise Refused("no wire segments (patch-only or geometry-less deck)")

    # Pass 1: collect every knot reference so each wire is remeshed once.
    rm = Remesh(geo, policy)
    resolved = {}  # id(card) -> [(tag, root, gidx, local seg), ...]

    def addr(card, k_tag, k_seg, what):
        r = geo.resolve(card.int(k_tag), card.int(k_seg), what, card.line)
        rm.want(r)
        return r

    for c in cards:
        if c.mn == "EX":
            typ = c.int(0)
            if typ == 4:
                raise Refused(
                    "EX 4 (NEC-2 elementary current source in space) has no NEC-5 counterpart; "
                    "NEC-5's EX 4 is a knot current source"
                )
            if typ in (0, 5, 6):
                resolved[id(c)] = [addr(c, 1, 2, "EX")]
        elif c.mn == "LD":
            typ = c.int(0)
            tag = c.int(1) if len(c.f) > 1 else 0
            a = c.int(2) if len(c.f) > 2 else 0
            b = c.int(3) if len(c.f) > 3 else 0
            if typ in (0, 1, 4) and not (tag == 0 and a == 0):
                if tag != 0 and a == 0:
                    if tag not in geo.groups:
                        raise DeckError(
                            f"line {c.line}: LD addresses tag {tag}, which no geometry card defines"
                        )
                    resolved[id(c)] = geo.all_segments(tag)
                else:
                    hi = b if b >= a else a
                    resolved[id(c)] = [
                        geo.resolve(tag, s, "LD", c.line) for s in range(a, hi + 1)
                    ]
                for r in resolved[id(c)]:
                    rm.want(r)
        elif c.mn in ("TL", "NT"):
            resolved[id(c)] = [
                addr(c, 0, 1, c.mn + " port 1"),
                addr(c, 2, 3, c.mn + " port 2"),
            ]
    rm.decide()
    notes.extend(rm.notes)

    # Pass 2: emit.
    out = []
    for c in cards:
        mn = c.mn
        if mn in _DROP_CARDS:
            notes.append(_DROP_CARDS[mn])
            continue
        if mn == "EX":
            typ = c.int(0)
            if typ in (0, 5, 6):
                ref = resolved[id(c)][0]
                k = rm.knot(ref, "EX")
                vr = c.f[4] if len(c.f) > 4 else "1"
                vi = c.f[5] if len(c.f) > 5 else "0"
                if typ == 6:
                    notes.append(
                        "EX 6 (4nec2 current source) written as NEC-5's EX 4 knot current source"
                    )
                    out.append(f"EX 4 {ref[0]} {k} 2 {vr} {vi}")
                else:
                    if typ == 5:
                        notes.append(
                            "EX 5 (current-slope-discontinuity source) written as an EX 0 "
                            "knot voltage source"
                        )
                    out.append(f"EX 0 {ref[0]} {k} 2 {vr} {vi}")
                continue
            out.append(c.text())
            continue
        if mn == "LD":
            typ = c.int(0)
            if typ not in (-1, 0, 1, 2, 3, 4, 5):
                # 4nec2 writes LD 6 / LD 7 (its own load kinds; LD 7 is its
                # insulated-wire load); NEC-5 has no such types and crashes
                # (SIGSEGV / free()) reading them.
                what = "insulation (4nec2 LD 7)" if typ == 7 else f"4nec2 LD {typ}"
                notes.append(
                    f"{what} dropped: not a NEC-2 load type and NEC-5 crashes on it"
                    + ("; the wire is bare here" if typ == 7 else "")
                )
                continue
            if id(c) in resolved:
                seen = set()
                for ref in resolved[id(c)]:
                    k = rm.knot(ref, "LD")
                    if (ref[0], k) in seen:
                        continue
                    seen.add((ref[0], k))
                    out.append(f"LD {typ} {ref[0]} {k} 2 " + " ".join(c.f[4:7]))
                if len(resolved[id(c)]) > 1:
                    notes.append(
                        f"LD {typ} over a segment range written as one knot load per segment "
                        "(NEC-5's 4th LD field is an end selector, not a range)"
                    )
                continue
            if typ in (2, 3, 5) and len(c.f) > 3 and c.int(1) in geo.groups:
                a, b = rm.remap_range(c.int(1), c.int(2), c.int(3))
                c.f[2], c.f[3] = str(a), str(b)
            out.append(c.text())
            continue
        if mn in ("TL", "NT"):
            r1, r2 = resolved[id(c)]
            k1 = rm.knot(r1, mn + " port 1")
            k2 = rm.knot(r2, mn + " port 2")
            out.append(f"{mn} {r1[0]} {k1} {r2[0]} {k2} " + " ".join(c.f[4:]))
            continue
        if mn == "GN":
            out.append(_gn(c, nofile, notes))
            continue
        if mn == "PT" and len(c.f) >= 4 and c.int(1) in geo.groups:
            a, b = rm.remap_range(c.int(1), c.int(2), c.int(3))
            c.f[2], c.f[3] = str(a), str(b)
        out.append(c.text())
    if out and out[-1] == "EN":
        out.pop()
    if not any(ln.split()[0] in ("XQ", "RP", "NE", "NH") for ln in out if ln.strip()):
        # 4nec2 adds the execution request itself; NEC-5 reads to EN and
        # computes nothing without one.
        out.append("XQ 0")
        notes.append("XQ 0 added: the deck had no execution request (XQ/RP/NE/NH)")
    out.append("EN")
    header = [f"CM {ln}" if ln else "CM" for ln in comments]
    header.append(f"CM nec5_corpus {VERSION}: translated from {name}")
    header.extend(f"CM nec5_corpus: {n}" for n in notes)
    header.append("CE")
    return "\n".join(header + out) + "\n", notes


def _split_nx(cards: list) -> list:
    parts, cur = [], []
    for c in cards:
        if c.mn == "NX":
            parts.append(cur)
            cur = []
            continue
        cur.append(c)
    parts.append(cur)
    return [p for p in parts if p]


def translate_file(path: Path, rel: str, policy: str, nofile: bool) -> dict:
    """Translate one file; returns the report record with the output texts."""
    rec = {"file": rel, "status": "translated", "outputs": [], "notes": []}
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
        comments, cards = normalize(text, rel)
        parts = _split_nx(cards)
        if len(parts) > 1:
            rec["notes"].append(
                f"NX: split into {len(parts)} decks (one structure each)"
            )
        for i, part in enumerate(parts, 1):
            deck, notes = translate_deck(comments, part, rel, policy, nofile)
            rec["notes"].extend(
                notes if len(parts) == 1 else [f"[{i}] {n}" for n in notes]
            )
            rec["outputs"].append((i if len(parts) > 1 else 0, deck))
    except Refused as e:
        rec["status"] = "refused"
        rec["reason"] = str(e)
    except DeckError as e:
        rec["status"] = "unreadable"
        rec["reason"] = str(e)
    except (ValueError, IndexError, RecursionError) as e:
        rec["status"] = "unreadable"
        rec["reason"] = f"{type(e).__name__}: {e}"
    return rec


def _iter_decks(src: Path):
    for p in sorted(src.rglob("*")):
        if p.is_file() and _is_deck_name(p.name) and p.name != "LICENSES.md":
            yield p


def cmd_translate(args) -> int:
    src, out = Path(args.src), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = open(
        args.report or (out / "translate-report.jsonl"), "w", encoding="utf-8"
    )
    counts = {"translated": 0, "refused": 0, "unreadable": 0, "decks_written": 0}
    reasons = {}
    note_kinds = {}
    n_files = 0
    for p in _iter_decks(src):
        rel = p.relative_to(src).as_posix()
        if args.only and args.only not in rel:
            continue
        n_files += 1
        if args.limit and n_files > args.limit:
            break
        rec = translate_file(p, rel, args.offcenter, args.nofile)
        counts[rec["status"]] += 1
        if rec["status"] != "translated":
            key = re.sub(r"\d+", "N", rec["reason"])[:90]
            reasons[key] = reasons.get(key, 0) + 1
        written = []
        for idx, deck in rec.pop("outputs", []):
            stem = re.sub(r"\.(nec|inp)$", "", rel, flags=re.I)
            dest = out / (stem + (f"_{idx}" if idx else "") + ".nec")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(deck, encoding="ascii", errors="replace")
            written.append(dest.relative_to(out).as_posix())
            counts["decks_written"] += 1
        rec["written"] = written
        for n in rec["notes"]:
            key = re.sub(
                r"\d+(\.\d+)?", "N", re.sub(r"^\[N\] ", "", re.sub(r"^\[\d+\] ", "", n))
            )[:80]
            note_kinds[key] = note_kinds.get(key, 0) + 1
        report.write(json.dumps(rec) + "\n")
    report.close()
    _log(
        f"files: {n_files}  translated: {counts['translated']}  refused: {counts['refused']}  unreadable: {counts['unreadable']}  decks written: {counts['decks_written']}"
    )
    if reasons:
        _log("\nrefused / unreadable, by reason:")
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:25]:
            _log(f"  {v:5d}  {k}")
    if note_kinds:
        _log("\ntransformations applied (count of decks x notes):")
        for k, v in sorted(note_kinds.items(), key=lambda kv: -kv[1])[:30]:
            _log(f"  {v:5d}  {k}")
    _log(f"\nreport: {report.name}")
    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
_ERROR_RE = re.compile(
    r"\bERROR\b|FAULTY|INVALID|STOP INPUT|Input data error|illegal value|Singular matrix"
    r"|Segmentation fault|SIGSEGV|out of range|no basis function|Definition not found",
    re.I,
)
# Lines that match the pattern above but are not failures: the Sommerfeld
# table cache probe (NEC-5 looks for SOMMPD.NEX before computing the tables,
# then writes it), the mesh-calibration remark ("... less than 1% error"),
# the all-clear, and gfortran's floating-point summary.
_NOT_ERROR_RE = re.compile(r"GMPINO: Unable to open|% error|NO ERRORS|IEEE_", re.I)
_AIP_HEADER = "ANTENNA INPUT PARAMETERS"
_SOURCE_CARD_RE = re.compile(r"^EX\s+[046]\b", re.M)


def _aip(text: str) -> list:
    """[(tag, seg, Zre, Zim)] for the first frequency's ANTENNA INPUT PARAMETERS."""
    chunks = text.split(_AIP_HEADER)[1:]
    rows = []
    if not chunks:
        return rows
    for line in chunks[0].splitlines():
        toks = line.split()
        if len(toks) != 12:
            if rows:
                break
            continue
        try:
            rows.append((int(toks[0]), int(toks[1]), float(toks[7]), float(toks[8])))
        except ValueError:
            if rows:
                break
    return rows


def run_exe(exe: str, deck_text: str, timeout: float, keep: Path = None) -> dict:
    """Run one deck (file names on stdin, printout in the working directory).
    Status: ok (impedance printed), ok-no-source (nothing to print: plane-wave
    or geometry-only deck), no-impedance (a source but no ANTENNA INPUT
    PARAMETERS section), error (NEC-5 said so), timeout. With `keep`, the
    printout of a deck that is not ok is saved there."""
    with tempfile.TemporaryDirectory(prefix="nec5c_") as td:
        tdp = Path(td)
        (tdp / "model.nec").write_text(deck_text, encoding="ascii", errors="replace")
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [exe],
                input="model.nec\nmodel.out\n\n",
                text=True,
                capture_output=True,
                cwd=td,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "wall_s": time.perf_counter() - t0}
        wall = time.perf_counter() - t0
        outp = tdp / "model.out"
        printout = outp.read_text(errors="replace") if outp.is_file() else ""
        console = (proc.stdout or "") + (proc.stderr or "")
        errs = [
            ln.strip()
            for ln in (printout + "\n" + console).splitlines()
            if _ERROR_RE.search(ln) and not _NOT_ERROR_RE.search(ln)
        ]
        rows = _aip(printout)
        if errs:
            status = "error"
        elif rows:
            status = "ok"
        elif not _SOURCE_CARD_RE.search(deck_text):
            status = "ok-no-source"
        else:
            status = "no-impedance"
        if keep is not None and status not in ("ok", "ok-no-source"):
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_text(
                printout + "\n--- console ---\n" + console, errors="replace"
            )
        return {
            "status": status,
            "wall_s": wall,
            "error": errs[0][:200] if errs else None,
            "z": [[r[0], r[1], r[2], r[3]] for r in rows[:8]],
        }


def cmd_check(args) -> int:
    exe = str(Path(args.exe).resolve())
    src = Path(args.src)
    decks = [p for p in _iter_decks(src) if not args.only or args.only in p.as_posix()]
    if args.limit:
        decks = decks[: args.limit]
    report = open(args.report or (src / "check-report.jsonl"), "w", encoding="utf-8")
    keep_dir = Path(args.keep_dir) if args.keep_dir else None
    counts = {}
    errors = {}
    t0 = time.perf_counter()

    def one(p):
        rel = p.relative_to(src)
        keep = (keep_dir / rel.with_suffix(".out")) if keep_dir else None
        rec = run_exe(exe, p.read_text(errors="replace"), args.timeout, keep)
        rec["file"] = rel.as_posix()
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for i, rec in enumerate(pool.map(one, decks), 1):
            counts[rec["status"]] = counts.get(rec["status"], 0) + 1
            if rec.get("error"):
                key = re.sub(r"[-+]?\d+(\.\d+)?", "N", rec["error"])[:80]
                errors[key] = errors.get(key, 0) + 1
            report.write(json.dumps(rec) + "\n")
            if i % 100 == 0:
                _log(f"  {i}/{len(decks)}  {counts}")
    report.close()
    _log(f"\n{len(decks)} decks in {time.perf_counter() - t0:.0f} s: {counts}")
    if errors:
        _log("\nerrors, by message:")
        for k, v in sorted(errors.items(), key=lambda kv: -kv[1])[:25]:
            _log(f"  {v:5d}  {k}")
    _log(f"\nreport: {report.name}")
    return 0


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="download the public deck collections into --out")
    f.add_argument("--out", default="raw")
    f.add_argument(
        "--only", default=None, help="comma-separated source names (see --list)"
    )
    f.set_defaults(fn=cmd_fetch)

    t = sub.add_parser(
        "translate", help="translate every deck under --src into NEC-5 form under --out"
    )
    t.add_argument("--src", default="raw")
    t.add_argument("--out", default="nec5")
    t.add_argument(
        "--offcenter",
        choices=("shift", "double"),
        default="shift",
        help="off-centre feeds: move half a segment toward the centre (default) or double the wire's mesh",
    )
    t.add_argument(
        "--nofile",
        action="store_true",
        help="append NOFILE to Sommerfeld GN cards so NEC-5 does not write SOMMPD.NEX tables in the working directory",
    )
    t.add_argument("--report", default=None)
    t.add_argument("--only", default=None, help="substring filter on the relative path")
    t.add_argument("--limit", type=int, default=0)
    t.set_defaults(fn=cmd_translate)

    c = sub.add_parser(
        "check", help="run every deck under --src through a NEC-5 executable"
    )
    c.add_argument("--exe", required=True)
    c.add_argument("--src", default="nec5")
    c.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    c.add_argument("--timeout", type=float, default=300.0)
    c.add_argument("--report", default=None)
    c.add_argument(
        "--keep-dir",
        default=None,
        help="save the printout of every deck that did not solve cleanly under this directory",
    )
    c.add_argument("--only", default=None)
    c.add_argument("--limit", type=int, default=0)
    c.set_defaults(fn=cmd_check)

    ls = sub.add_parser("list", help="list the sources fetch knows about")
    ls.set_defaults(
        fn=lambda a: (
            [
                _log(
                    f"{s['name']:22s} {s.get('repo') or ', '.join(s.get('urls', []) or [u for u, _ in s.get('files', [])])}"
                )
                for s in SOURCES
            ]
            and 0
        )
    )

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
