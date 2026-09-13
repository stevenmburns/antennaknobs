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
    centre is a knot; an even count already has a centre knot. An off-centre
    feed (or load, or line port) gets the cheapest segment count between N
    and 2N that puts it on a knot exactly: the centre of segment k sits at
    (2k-1)/(2N) of the wire, so any multiple of 2N/gcd(N, 2k-1) works, and
    the smallest one not below N is chosen (`--offcenter exact`, the default;
    `shift` moves the feed half a segment toward the centre instead and keeps
    the mesh, `double` always doubles).
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

VERSION = "1.11"
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
    r"^\s*(GW|GA|GH|CW|SP|SM|GM|GR|GX|GC)\s*[\d,\s.+-]", re.I | re.M
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
        rel = relpath.replace("\\", "/")
        rel = re.sub(r"[^\w./ ()+-]", "_", rel)  # Windows-hostile characters
        # A member name is the archive's to choose, and `..` in it would
        # write outside raw/<source>/ (found by the 1.3 security review,
        # antennaknobs#1376): keep only the plain path components.
        parts = [c for c in rel.split("/") if c not in ("", ".", "..")]
        if not parts:
            self.skipped += 1
            return
        dest = self.dir.joinpath(*parts)
        if not dest.resolve().is_relative_to(self.dir.resolve()):
            self.skipped += 1
            return
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


class InvalidNEC(ValueError):
    """The deck is not legal NEC input of ANY dialect (antennaknobs#1386).

    A THIRD thing, and the distinction is the point: `Refused` says something
    about NEC-5 ("no card for this"), `DeckError` says something about this tool
    ("could not read it"), and this says something about the DECK -- so it
    belongs on no engine's ledger and on no ledger of ours.

    Raised only where the fault is checkable from the file alone, with no
    assumption about any dialect: a count or an address the deck itself
    contradicts. A non-numeric field or an unrecognised line stays a
    `DeckError` even though NEC would reject it too, because our own symbol
    evaluator is the likelier explanation and calling it the deck's fault would
    be a claim about 4nec2 this tool cannot make.
    """


_PLAIN_NUM_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\Z")

# The only NEC fields that are WORDS rather than numbers. Everything else that
# survives SY substitution as a non-number is an unresolved symbol or a typo
# (antennaknobs#1391) -- and writing one into the deck verbatim turns our bug
# into the engine's error message.
#
# The cards that carry a FILE NAME, exempt whole rather than by position:
# a name's index moves with the card's optional fields, and guessing it is how a
# real deck gets refused. Measured over the 3,168-file corpus, these four are
# exactly the exemptions the decks need --
#
#   GN  the ground-screen file (the `NOFILE` sentinel, or a path)
#   GF  read a numerical Green's function   (`R2-H18-V14.WGF`, `RADIAL8.NGF`)
#   WG  write one                           (14 decks in the corpus)
#   PL  the plot output file                (`m20-12-currents.dat`)
#
# -- and getting the list wrong is not a silent matter: with only GN exempt, 30
# decks that this tool REFUSES by name for GF/WG (a precise statement about
# NEC-5's vocabulary) reported "unreadable" instead (a vague one about our
# reader), and two Cebik tutorial decks that translate fine stopped translating.
_WORD_FIELD_CARDS = frozenset(("GN", "GF", "WG", "PL"))
_WORD_FIELDS = frozenset(("NOFILE",))

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


_NUMBER_TOKEN = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?$")


def _split_fields(line: str) -> list:
    """Card fields. A TAB-delimited 4nec2 card may carry an expression with
    spaces around its operators inside one field (`Fz + 0.24529`), so tabs
    and commas split first; a tab field is then split on spaces, and only a
    bare operator token glues its two neighbours back together (a mixed
    tab/space deck keeps its plain numbers apart)."""
    if "\t" not in line:
        return line.replace(",", " ").split()
    out = []
    for field in re.split(r"[\t,]+", line):
        parts = field.split()
        i = 0
        while i < len(parts):
            if parts[i] in ("+", "-", "*", "/", "^") and 0 < i < len(parts) - 1 and out:
                out[-1] = out[-1] + parts[i] + parts[i + 1]
                i += 2
                continue
            # A number followed by a unit symbol in the SAME tab field (`-68 ft`,
            # `60.7 uh`) is the juxtaposed product the SY evaluator already
            # reads (`SY X=135 ft`). Splitting it shifted every later column: a
            # sloper became a wire 68 m underground. Glued, it evaluates as one
            # value; a number followed by anything else (`4.0 #12`) stays apart.
            if (
                i + 1 < len(parts)
                and _NUMBER_TOKEN.match(parts[i])
                and parts[i + 1].lower() in _SY_UNITS
            ):
                out.append(parts[i] + parts[i + 1])
                i += 2
                continue
            out.append(parts[i])
            i += 1
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
        # Trailing comments. `'` was always stripped; `!` was not, and 60 decks
        # in the corpus use it — `GW 1 5 ... 81.0E-3 ! Drive connection 118.35
        # 23.67 4.73`. Through 1.6 that prose was read as MORE FIELDS and written
        # into the output deck verbatim, so `4nec2-models/Objects/747plane.nec`
        # came out as `GW 1 10 ... 81.0E-3 ! Drive connection 118.35 ...` and
        # reported `translated` (found while measuring #1391 — the same class of
        # bug as an unresolved symbol, reached by a different road).
        for marker in ("'", "!"):
            stripped = stripped.split(marker, 1)[0].rstrip()
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
                # A token that survives substitution is either a legitimate
                # WORD field or an unresolved symbol, and the difference matters
                # (antennaknobs#1391). Written out verbatim, an unresolved symbol
                # leaves the deck reading `GW 1 6 0 0 0 0 0 nosuch .001`, the
                # deck reports `translated`, and the failure arrives at the
                # engine as an engine error that is ours. So only the word
                # fields NEC actually has are kept; anything else makes the deck
                # unreadable, with the token named.
                if mn in _WORD_FIELD_CARDS or tok.upper() in _WORD_FIELDS:
                    fields.append(tok)
                else:
                    raise DeckError(
                        f"{where}: {mn} field {len(fields) + 1} {tok!r} is not a "
                        "number and is not a NEC word field — an unresolved SY "
                        "symbol or a typo; it would have been written into the "
                        "deck as-is"
                    ) from None
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
    "VC": "VC (NEC-4 card) dropped: not a NEC-5 command",
    "MX": "MX (NEC-4 matrix memory allocation) dropped: not a NEC-5 command",
    "PS": "PS (NEC-4 print of segment electrical lengths) dropped: not a NEC-5 command",
    "MP": "MP (nec2++ medium-parameters card) dropped: not a NEC-5 command",
}
_REFUSE_CARDS = {
    # CW (catenary wire) is deliberately NOT here. This tool used to refuse it
    # as NEC-4-only, which the NEC-5 manual contradicts: NEC-5 has a CW card in
    # the structure-geometry section, spelled field for field as NEC-4.2 spells
    # it -- CW ITG NS X1 Y1 Z1 X2 Y2 Z2 RAD ICAT RHM ZM, ICAT selecting height
    # / sag / total length -- so the card passes through with no note. It does
    # go through `Geometry` (below), because it carries segments that EX/LD
    # address by (tag, segment) (antennaknobs#1369).
    # SP / SC are NEC-2 / NEC-4 surface-patch cards. NEC-5 spells a DIFFERENT
    # card with the mnemonic SP (a sphere), so a patch deck is not a syntax
    # error there: it is silently read as something else. Fed through
    # untranslated, the manual's Example 4 (T on a box) solves on stock x13
    # as three bare wires with no box, and dies on the a43 beta with an
    # integer divide by zero in the geometry phase — and this tool reported
    # that as an a43 regression (Ward note of 2026-09-08, finding 1;
    # corrected 2026-09-09, AC6LA's catch). 42 decks in the public
    # collections carry SP/SC in the patch form.
    # SP itself is handled by _classify_sp below: NEC-5 has its own SP (a
    # sphere), so the card refuses only in its NEC-2/NEC-4 patch form.
    "SC": "SC (NEC-2/NEC-4 patch continuation) is not a NEC-5 command; a patch deck cannot be translated",
    "SM": "SM (NEC-2 multiple-patch surface) is rejected by NEC-5 (DATAGN input error); a patch deck cannot be translated",
    "GF": "GF (NEC-2 numerical Green's function read) has no NEC-5 counterpart",
    "WG": "WG (NEC-2 numerical Green's function write) has no NEC-5 counterpart",
}
_SYNTHETIC_TAG_BASE = 9001

# NEC's PROGRAM CONTROL cards: everything that belongs after GE. NEC reads the
# cards before GE as geometry, so one of these above it is not a NEC-5 gap --
# it is a deck no NEC of any dialect reads (antennaknobs#1382).
_CONTROL_CARDS = frozenset(
    (
        "GN",
        "EX",
        "FR",
        "LD",
        "RP",
        "XQ",
        "NE",
        "NH",
        "PT",
        "PQ",
        "KH",
        "EK",
        "TL",
        "NT",
        "CP",
        "PL",
    )
)
_INVALID = "not valid NEC input: "


def _validate_nec(cards: list) -> None:
    """Refuse a deck that is not legal NEC input in ANY dialect.

    The 8 decks both NEC-5 binaries answered with `DATAGN: Input data error` on
    the 2026-09-09 corpus run were all of this class, and nec2c rejects every
    one of them too -- so they were 8 rows in each binary's error column that
    said nothing about the binary. Refused with the fault NAMED, never
    repaired: moving a stray GN below GE would make the model ours rather than
    the author's, and the working group is comparing binaries on the decks
    their authors published.

    The three faults, in the order they are checked, which is the order of how
    much they say about the deck:

    * **No GE at all.** A geometry fragment, not a model (`g1ojs/Clutter
      file.nec` is one, meant to be pasted into another deck). Checked first,
      and checked as "no GE anywhere" rather than "no GE before the first
      control card or EN": Clutter has neither of those, so the narrower rule
      would pass it.
    * **A control card above GE.** Named, because which card it is says what
      the author was doing (`GN` in four of the eight, `EX` in one).
    * **A GW with radius 0 and no GC after it.** In NEC a zero radius means
      "the taper is on the GC card that follows"; with no GC the wire has no
      radius. `rchacker`'s turnstil writes the field away entirely -- eight
      fields, not nine -- and follows with GS, so an absent radius counts as
      zero here, the way NEC's fixed-format reader counts it.
    """
    if not any(c.mn == "GE" for c in cards):
        raise InvalidNEC(
            _INVALID + "no GE card anywhere (a geometry fragment, not a model)"
        )
    for c in cards:
        if c.mn == "GE":
            break
        if c.mn in _CONTROL_CARDS:
            raise InvalidNEC(
                _INVALID + f"{c.mn} (a program-control card) on line {c.line}, above GE"
            )
    for i, c in enumerate(cards):
        if c.mn != "GW":
            continue
        try:
            if c.num(8, 0.0) != 0.0:
                continue
        except DeckError:
            continue  # a non-numeric radius is a different complaint
        after = cards[i + 1].mn if i + 1 < len(cards) else ""
        if after != "GC":
            raise InvalidNEC(
                _INVALID
                + f"GW on line {c.line} has radius 0, which means a GC follows with the "
                + (
                    f"taper, and the next card is {after}"
                    if after
                    else "taper, and it is the last card"
                )
            )


_SP_PATCH_REFUSAL = (
    "SP in its NEC-2/NEC-4 surface-patch form (two integers then real "
    "coordinates) is not legal NEC-5 syntax — NEC-5's SP is a sphere card; "
    "a patch deck cannot be translated"
)


def _classify_sp_fields(fields) -> str:
    """``"nec5"`` for NEC-5's sphere spelling of SP, ``"patch"`` for NEC-2/4's.

    `fields` is the card's fields AS WRITTEN (the tokens after the mnemonic),
    because the literal spelling carries the signal: an integral value is not
    an integer literal.

    The two cards share a mnemonic and nothing else. NEC-2/NEC-4:
    ``SP I1 I2 F1 .. F6`` — two integers (I2 = patch shape 0..3) then real
    coordinates, at most 8 fields. NEC-5 (Users Manual, "SP – Sphere"):
    ``SP ITAG NTH NPH IALT X0 Y0 Z0 RAD TH1 TH2 PH1 PH2`` — FOUR integers, two
    of them patch-edge counts (so >= 1), then eight reals with radius > 0.
    So fields 3 and 4 are integer counts in NEC-5 and real coordinates in
    NEC-2; a decimal point or exponent in either settles it on sight, and when
    both are integer literals the field count and a positive radius do. The
    manual's Example 4 card, ``SP 0 0 .1 .05 .05 0. 0.``, is a patch on sight.

    TWIN of `antennaknobs.nec_import.classify_sp`. The rule was born here,
    lifted into the importer by antennaknobs#1337 (which then imported it
    back), and returned here by #1376 so that this file needs nothing
    installed — "one file, standard library only" is the promise the working
    group runs it under, and an import of antennaknobs broke it. Two copies
    are how they drift, so `tests/test_nec_import.py` pins the two function
    bodies equal, token for token; edit both or fail the suite.
    """
    if len(fields) < 8 or not all(_is_int_literal(t) for t in fields[:4]):
        return "patch"
    try:
        nth, nph, radius = int(fields[1]), int(fields[2]), float(fields[7])
    except ValueError:
        return "patch"
    if nth < 1 or nph < 1 or radius <= 0:
        return "patch"
    return "nec5"


def _is_int_literal(token: str) -> bool:
    return token.lstrip("+-").isdigit()


def _classify_sp(c: Card) -> str:
    """NEC-5 sphere vs NEC-2/NEC-4 patch, on `Card.f`: the fields as written."""
    return _classify_sp_fields(c.f)


class Geometry:
    """Segment counts per geometry card, tag GROUPS (NEC numbers the segments
    of a tag across every card and copy carrying it, in order), and the
    absolute segment order -- from the NEC-2 geometry cards including the
    copies GM / GX / GR generate."""

    def __init__(self):
        self.root_n = {}  # root card id -> segment count (as authored)
        self.root_card = {}  # root card id -> Card (GW/GA/GH/CW) to rewrite
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
            raise InvalidNEC(
                _INVALID + f"{card.mn} on line {card.line} has {n} segments"
            )
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
        if mn in ("GW", "GA", "GH", "CW"):
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
                raise InvalidNEC(
                    _INVALID + f"{what} on line {line} addresses absolute segment "
                    f"{seg}, outside 1..{len(self.order)}"
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
            raise InvalidNEC(
                _INVALID + f"{what} on line {line} addresses tag {tag}, which no "
                "geometry card defines"
            )
        total = self.group_size(tag)
        if not 1 <= seg <= total:
            raise InvalidNEC(
                _INVALID + f"{what} on line {line} addresses segment {seg} of tag "
                f"{tag}, which has {total}"
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
        self.centre = {}  # root -> the references read as a centre feed
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

    @staticmethod
    def _centre_segs(n: int, segs) -> set:
        """The references read as a NEC-2 CENTRE feed: the middle segment of
        an odd count, or ONE of the two segments beside the middle knot of an
        even count (the nearest NEC-2 could get to the centre). When both of
        those are referenced they are two distinct positions, not a centre."""
        if n % 2 == 1:
            return {(n + 1) // 2} & set(segs)
        both = {n // 2, n // 2 + 1} & set(segs)
        return both if len(both) == 1 else set()

    def _exact_count(self, n: int, segs) -> int:
        """The smallest count N' in [N, 2N] that puts every referenced
        segment centre on a knot. The centre of segment k sits at
        (2k-1)/(2N) of the wire, a knot of an N'-mesh iff N' is a multiple
        of 2N/gcd(N, 2k-1); over several references the gcd runs over all
        of them. A centre feed asks only for an even N' (the middle knot):
        N+1 for an odd count, which is the usual case."""
        centre = self._centre_segs(n, segs)
        g = n
        for s in segs:
            if s not in centre:
                g = math.gcd(g, 2 * s - 1)
        base = 2 * n // g
        n2 = base * max(1, -(-n // base))  # smallest multiple of base >= n
        while centre and n2 % 2:
            n2 += base
        return n2

    def decide(self):
        for root, segs in self.refs.items():
            n = self.geo.root_n[root]
            card = self.geo.root_card[root]
            centre = self._centre_segs(n, segs)
            self.centre[root] = centre
            if self.policy == "double":
                n2 = n if (n % 2 == 0 and centre == set(segs)) else 2 * n
            elif self.policy == "exact":
                n2 = self._exact_count(n, segs)
            else:  # shift: half a segment toward the centre, mesh kept
                n2 = n + 1 if (n % 2 == 1 and centre) else n
                knots = {self._knot_of(s, n, n2) for s in segs}
                if len(knots) < len(segs):
                    n2 = n + 1  # one more segment always separates two centres
                    self.notes.append(
                        f"{card.mn} tag {card.f[0]}: one segment added so {len(segs)} "
                        "referenced segments map to distinct knots"
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
        if seg in self.centre.get(root, ()) and n2 % 2 == 0:
            return self._offset(tag, gidx) + n2 // 2  # the wire's centre knot
        k = self._knot_of(seg, n, n2)
        if abs(pos - round(pos)) >= 1e-9:
            self.notes.append(
                f"{what} on tag {tag} segment {seg} of {n} sat mid-segment: moved "
                f"{abs(k - pos):.2f} segment(s) to knot {k} of {n2} (toward the wire centre)"
            )
        return self._offset(tag, gidx) + k

    def _range_edge(self, tag: int, s: int, *, upper: bool) -> int:
        """One END of a NEC-2 segment range, on the new mesh.

        A range edge is NOT a segment centre, and mapping it as one is the hole
        in #1416. Old segment `k` of an N-mesh occupies the fraction
        [(k-1)/N, k/N] of the wire; on an N'-mesh that span starts inside new
        segment ``(k-1)*N'//N + 1`` and ends inside new segment
        ``ceil(k*N'/N)``. Taking those two edges gives the SMALLEST new range
        that covers the old one — which is what a distributed load wants, since
        under-covering silently unloads part of the wire the author loaded.

        The property that matters most falls out of it: a range that covered the
        whole wire still does. a=1 gives (1-1)*N'//N + 1 = 1 and b=N gives
        ceil(N*N'/N) = N', for every N and N'. The old code mapped each edge as
        if it were a centre — (k-0.5)/N*N' + 0.5, rounded — which sent 1..25 of
        a 25-segment wire to 2..50 of a 50-segment one, dropping the first half
        segment of a whole-wire load and turning it into a partial range. That
        cost the AK#896 census 175 decks, because a partial `LD 5` range is a
        thing momwire's nec2 dialect refuses by name where a whole-wire one is
        its per-wire conductivity.

        Integer arithmetic throughout: `(k-1)*N'//N` and `-(-k*N'//N)` are exact
        where the float form needed a 1e-9 guard and still rounded 1.5 to 2.
        """
        _, root, gidx, local = self.geo.resolve(tag, s, "range", 0)
        n = self.geo.root_n[root]
        n2 = self.new_n.get(root, n)
        local2 = -(-local * n2 // n) if upper else (local - 1) * n2 // n + 1
        return self._offset(tag, gidx) + max(1, min(n2, local2))

    def remap_range(self, tag: int, a: int, b: int):
        """A NEC-2 segment range on a tag (distributed load, PT) on the new mesh.

        `0 0` is NEC's "the whole tag" spelling and is returned untouched: it
        names no segment numbers, so there is nothing to remap and rewriting it
        as an explicit range would only be a chance to get it wrong.
        """
        if a == 0 and b == 0:
            return a, b
        total = self.geo.group_size(tag)
        if not 1 <= a <= total:
            return a, b
        b2 = self._range_edge(tag, min(b, total), upper=True) if b else 0
        return self._range_edge(tag, a, upper=False), b2


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
        # GN 2 stays GN 2 (antennaknobs#1442). NEC-5 reads GN 0 and GN 2 as the same
        # Sommerfeld ground, but a NEC-2 reader of this tree (momwire's portal)
        # takes GN 0 as reflection coefficients, so rewriting 2 as 0 swapped the
        # ground model the author asked for on every cross-engine row.
        line = f"GN {iperf} 0 0 0 {eps} {sig}"
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


# Two GW cards whose endpoints coincide are the same wire written twice, and
# they make the moment matrix EXACTLY singular: two basis functions with
# identical kernels of opposite sign. That is an invalid deck, not a hard one
# (antennaknobs#1430).
#
# Why it is worth refusing rather than passing on. `qantenna/airplane.nec` has
# GW 116 and GW 117 as one wire with reversed endpoints, and its "answer"
# depended on the fill order: a row-order fill leaves ~1e-13 of rounding
# residue for the LU to pivot on, and three NEC-5 builds returned three
# different impedances for it (80.9-83.1j, 92.2-61.5j, 74.2+105.4j). It was the
# public corpus's widest engine-vs-engine mover, and the disagreement was
# entirely about which rounding residue each build happened to produce. A
# column-order fill gets exact zero rows and says so. Comparing engines on a
# deck like this measures floating point, not electromagnetics.
#
# TOLERANCE: a millionth of the wire's own length, with a tiny absolute floor
# for a degenerate zero-length card. Deliberately tight. The defect being caught
# is a deck listing the same wire twice — in both corpus cases the coordinates
# agree to every printed digit — and a LOOSER, radius-scaled test would start
# refusing decks whose wires are merely close, which is a modelling judgement
# this tool has no business making.
#
# LIMIT, stated rather than implied: only the AUTHORED GW/CW cards are checked.
# `Geometry` tracks the tag groups and segment order that GM / GX / GR copies
# produce but never materialises their coordinates, so a duplicate created BY a
# transform slips through. Both known cases are authored pairs. Catching the
# transformed kind means computing the transforms, which is a different and much
# larger change.
_COINCIDENT_REL = 1e-6
_COINCIDENT_ABS = 1e-12


def _gm_separates(cards, t1: int, t2: int) -> bool:
    """Does some `GM` move exactly ONE of tags `t1`, `t2`?

    This guard is why the check above is sound, and measuring the corpus is what
    put it here: without it, three valid decks are wrongly refused. Both
    `dscn2.nec` copies write `GW 1` and `GW 2` with identical coordinates and
    then carry `GM ... 2.0` — a tag range naming tag 2 alone — which moves the
    second away from the first. `2m Circular Slot Cube V Pol.nec` does the same
    with tags 100 and 200. Authored as coincident, separated before the solve,
    and not duplicates at all.

    Conservative in the safe direction: any GM whose tag range covers one of the
    pair and not the other makes the tool DECLINE to refuse, without asking
    whether that GM's transform is non-zero or where it actually lands the wire.
    Declining to refuse a deck that may be invalid costs a comparison; refusing
    a deck that is valid loses it, and would be the tool telling a user their
    model is broken when it is not.
    """
    for c in cards:
        if c.mn != "GM" or len(c.f) <= 8:
            continue
        a, b = Geometry._its_range(c.f[8])
        covers = lambda t: a <= 0 or (t >= a and (b <= 0 or t <= b))  # noqa: E731
        if covers(t1) != covers(t2):
            return True
    return False


def _duplicate_wire(cards) -> str | None:
    """`"GW a / GW b"` for the first coincident authored wire pair, else None."""
    wires = []
    for c in cards:
        if c.mn not in ("GW", "CW") or len(c.f) < 9:
            continue
        try:
            a = tuple(float(x) for x in c.f[2:5])
            b = tuple(float(x) for x in c.f[5:8])
        except (TypeError, ValueError):
            continue
        length = math.dist(a, b)
        wires.append((c, a, b, max(length * _COINCIDENT_REL, _COINCIDENT_ABS)))
    for i, (ci, ai, bi, ti) in enumerate(wires):
        for cj, aj, bj, tj in wires[i + 1 :]:
            tol = min(ti, tj)
            if (math.dist(ai, aj) <= tol and math.dist(bi, bj) <= tol) or (
                math.dist(ai, bj) <= tol and math.dist(bi, aj) <= tol
            ):
                try:
                    if _gm_separates(cards, int(ci.f[0]), int(cj.f[0])):
                        continue
                except (TypeError, ValueError):
                    pass
                return (
                    f"{ci.mn} tag {ci.f[0]} (line {ci.line}) / "
                    f"{cj.mn} tag {cj.f[0]} (line {cj.line})"
                )
    return None


def translate_deck(
    comments: list, cards: list, name: str, policy: str, nofile: bool
) -> tuple:
    """(deck text, notes) for ONE structure (no NX inside)."""
    _validate_nec(cards)
    dup = _duplicate_wire(cards)
    if dup:
        raise InvalidNEC(
            _INVALID + f"the same wire is listed twice ({dup}), which makes the "
            "moment matrix singular"
        )
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
            if c.mn == "SP":
                if _classify_sp(c) == "patch":
                    raise Refused(_SP_PATCH_REFUSAL)
                notes.append(f"line {c.line}: SP kept as a NEC-5 sphere card")
            if c.mn in ("GW", "GA", "GH", "CW", "GM", "GX", "GR"):
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
                        raise InvalidNEC(
                            _INVALID + f"LD on line {c.line} addresses tag {tag}, "
                            "which no geometry card defines"
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
    except InvalidNEC as e:
        rec["status"] = "invalid"
        rec["reason"] = str(e)
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


# The environment an OpenMP binary's answer can depend on (antennaknobs#1344).
# Recorded on every `check` report — PRESENT or explicitly absent — because
# two runs of the same binary on the same decks on the same box gave
# different crash/hang splits on 38 decks (2026-09-08 vs 09-09) and the
# older report could not say what environment produced it. A report that
# cannot say cannot be compared.
_ENV_KEYS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "OMP_WAIT_POLICY",
    "OMP_PROC_BIND",
    "OMP_PLACES",
    "OMP_DYNAMIC",
    "KMP_AFFINITY",
    "KMP_BLOCKTIME",
    "GOMP_CPU_AFFINITY",
    "GOMP_SPINCOUNT",
    "MKL_DYNAMIC",
    "PYTHONUTF8",
)


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# The three thread counts an OpenMP / OpenBLAS / MKL engine reads. Pinned to 1
# per worker when `--jobs > 1`, unless the user set them (antennaknobs#1403).
_THREAD_KEYS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


def _engine_env(jobs: int) -> tuple[dict, dict, bool]:
    """(env for the engine, the effective thread values, timings worth reading).

    `--jobs N` runs N engine processes at once, and an OpenMP engine with the
    thread count left to the environment then asks for N x threads of CPU.
    Measured on the laptop 2026-09-11: the clean-room OpenMP build took 1,651 s
    for the corpus under `--jobs 4` against a single-threaded reference's
    1,447 s, while one deck at a time on an idle box the same binary is 1.8-2.3x
    FASTER. So a per-deck `wall_s` from an oversubscribed run is not a speed
    measurement, and nothing in the report used to say so (#1403).

    Two things follow, and the second matters more than the first. The thread
    counts are pinned to 1 per worker when `--jobs > 1` — unless the user set
    them, because someone who asks for a thread count has a reason and the tool
    is not the place to overrule it. And `timing_valid` records whether
    jobs x threads fits in `os.cpu_count()`, so a report whose wall times cannot
    be compared SAYS it, rather than leaving a reader to know.
    """
    env = dict(os.environ)
    user_set = {k: os.environ.get(k) for k in _THREAD_KEYS if os.environ.get(k)}
    if jobs > 1:
        for k in _THREAD_KEYS:
            env.setdefault(k, "1")
    effective = {k: env.get(k) for k in _THREAD_KEYS}
    # An unset count means the runtime picks, and what it picks is a core per
    # thread — so treat it as cpu_count rather than as 1, which is the
    # assumption that hid this.
    cpus = os.cpu_count() or 1
    per_worker = max(
        (int(v) if v and v.isdigit() else cpus) for v in effective.values()
    )
    return (
        env,
        {"effective": effective, "user_set": sorted(user_set)},
        (jobs * per_worker <= cpus),
    )


def _environment_meta(exe: str, jobs: int | None = None) -> dict:
    """What a `check` report must carry to be comparable with another day's
    (antennaknobs#1344): the thread-relevant environment with absent keys
    stated as absent, the launching interpreter, the platform, the exe's
    size and sha256, the sha256 of every DLL beside it (the crash the 09-09
    run kept lives in libiomp5md), and the job count."""
    import platform

    env = {k: os.environ.get(k) for k in _ENV_KEYS}
    env["_other_omp_like"] = sorted(
        k
        for k in os.environ
        if k.startswith(("OMP_", "KMP_", "GOMP_", "MKL_", "OPENBLAS_"))
        and k not in _ENV_KEYS
    )
    exe_path = Path(exe)
    binaries = {}
    if exe_path.is_file():
        binaries[exe_path.name] = {
            "bytes": exe_path.stat().st_size,
            "sha256": _sha256(exe_path),
        }
        for dll in sorted(exe_path.parent.glob("*.dll")):
            binaries[dll.name] = {"bytes": dll.stat().st_size, "sha256": _sha256(dll)}
    return {
        "env": env,
        "python": {"executable": sys.executable, "version": platform.python_version()},
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
        "jobs": jobs,
        "binaries": binaries,
    }


# Fields of the recorded environment that make two `check` reports
# incomparable when they differ (antennaknobs#1344). The interpreter path is
# deliberately NOT here: the 09-09 probe ran 44 decks under two interpreters
# and got identical buckets, so it is recorded but does not refuse.
_COMPARE_FIELDS = ("env", "platform", "machine", "binaries", "jobs")


def _read_report(path: Path) -> tuple[dict, dict]:
    """(meta, {deck: row}) from a check or translate report.

    Accepts BOTH row keys, and the reason is antennaknobs#1404: this read
    `rec["deck"]` while every writer here has written `rec["file"]`, so it
    returned an EMPTY dict from every report and `compare` printed
    "decks: 0 vs 0; moved: 0" — a clean pass over nothing, in the published
    signed exe. Keying on either is the fix; `cmd_compare` refusing an empty
    comparison is what makes the class of mistake loud next time.
    """
    meta, rows = {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "_meta" in rec:
                meta = rec["_meta"]
                continue
            key = rec.get("deck") or rec.get("file")
            if key is not None:
                rows[key] = rec
    return meta, rows


# Below this, a relative change on |Z| is a large percentage of nothing.
# `necpp/ga_pjw_1.nec` reports -0.53 ohm in one build and -0.51 in another: a 5 %
# "move" on a deck whose resistance is NEGATIVE and unphysical to begin with.
_DEGENERATE_OHMS = 1.0


def _first_z(row: dict):
    """The deck's FIRST reported impedance, or None when it has none.

    First, and named as such, because of the trap that cost a wrong figure on
    2026-09-11: a deck carrying a multi-point `FR` sweep prints one row per
    frequency, and comparing one report's LAST row with another's FIRST reads a
    72 % disagreement into two builds that agree to the last digit.
    """
    z = row.get("z") or []
    if not z:
        return None
    row0 = z[0]
    if not isinstance(row0, (list, tuple)) or len(row0) < 4:
        return None
    try:
        return complex(float(row0[2]), float(row0[3]))
    except (TypeError, ValueError):
        return None


def _z_str(z: complex) -> str:
    return f"{z.real:.6g}{z.imag:+.6g}j"


def cmd_compare(args) -> int:
    """Diff two check reports deck by deck — after refusing, by name, to
    compare reports whose recorded environments differ (antennaknobs#1344).
    `--ignore-env` compares anyway and prints the differences first.

    Compares STATUS and the first IMPEDANCE row. Status alone was the whole of
    this until 1.7, and status alone is not the question a build A/B asks: two
    reports with identical buckets differed on 25 decks' impedances, four of them
    materially, and `compare` called that no change (antennaknobs#1404).
    """
    meta_a, rows_a = _read_report(Path(args.a))
    meta_b, rows_b = _read_report(Path(args.b))
    env_a, env_b = meta_a.get("environment"), meta_b.get("environment")
    differing = []
    if env_a is None or env_b is None:
        differing.append(
            "one report carries no recorded environment (written before 1.2)"
        )
    else:
        for field in _COMPARE_FIELDS:
            if env_a.get(field) != env_b.get(field):
                differing.append(
                    f"{field}: {env_a.get(field)!r} != {env_b.get(field)!r}"
                )
    if differing:
        print("environments differ:")
        for d in differing:
            print("  " + d)
        if not args.ignore_env:
            print("refusing to compare (pass --ignore-env to compare anyway)")
            return 2
    # An empty comparison is never a successful one (antennaknobs#1404). Said
    # before any verdict, and non-zero, because "moved: 0" over no decks at all
    # is the most convincing wrong answer this tool can give.
    for label, meta in ((args.a, meta_a), (args.b, meta_b)):
        if meta.get("timing_valid") is False:
            print(
                f"WARNING: {label} was written with jobs x threads over the CPU "
                "count (timing_valid: false) — its wall times are not a speed "
                "measurement; statuses and impedances are unaffected"
            )
    if not rows_a or not rows_b:
        print(
            f"no decks to compare: {args.a} has {len(rows_a)} deck rows, "
            f"{args.b} has {len(rows_b)} — a report with no decks in it is not "
            "a comparison. Check that both files are check reports written by "
            "this tool."
        )
        return 2
    # Read with a default rather than off the namespace directly:
    # `cmd_compare` is called with a hand-built namespace by
    # tests/test_nec5_corpus_meta_1344.py, and a CLI function that breaks on a
    # caller predating one of its flags is a trap for the next one.
    tol = getattr(args, "tol", 1e-4)
    moved = []
    z_moved, z_degenerate, z_absent = [], [], 0
    for deck in sorted(set(rows_a) | set(rows_b)):
        ra, rb = rows_a.get(deck, {}), rows_b.get(deck, {})
        sa = ra.get("status", "<absent>")
        sb = rb.get("status", "<absent>")
        if sa != sb:
            moved.append((deck, sa, sb))
        za, zb = _first_z(ra), _first_z(rb)
        if za is None or zb is None:
            z_absent += 1
            continue
        if abs(za) < _DEGENERATE_OHMS or abs(zb) < _DEGENERATE_OHMS:
            if za != zb:
                z_degenerate.append((deck, za, zb))
            continue
        rel = abs(za - zb) / abs(za)
        if rel > tol:
            z_moved.append((rel, deck, za, zb))
    print(
        f"decks: {len(rows_a)} vs {len(rows_b)}; moved: {len(moved)}; "
        f"impedance moved (> {tol:g}): {len(z_moved)}"
    )
    for deck, sa, sb in moved:
        print(f"  {deck}: {sa} -> {sb}")
    for rel, deck, za, zb in sorted(z_moved, reverse=True):
        print(f"  {deck}: {_z_str(za)} -> {_z_str(zb)}   dZ/|Z| = {rel:.3e}")
    for deck, za, zb in z_degenerate:
        # The ga_pjw_1 lesson: that deck reports -0.53 ohm in one build and
        # -0.51 in the other. A relative change on |Z| under an ohm is a large
        # percentage of nothing, and printing it as a mover puts an unphysical
        # deck at the top of the list where a real one should be.
        print(
            f"  {deck}: {_z_str(za)} -> {_z_str(zb)}   degenerate "
            f"(|Z| < {_DEGENERATE_OHMS:g} ohm), percentage meaningless"
        )
    if z_absent:
        print(f"impedance not compared: {z_absent} decks with no row on one side")
    return 0


def _meta_row(step: str, **fields) -> str:
    """First line of every report: which instrument produced it. Reports are
    compared across boxes and builds, and the verdict on a deck can change
    between versions (1.0 scored a crash that left a partial printout as a
    clean run; 1.1 scores it as "crash"), so a report must say."""
    meta = {"tool": "nec5_corpus.py", "version": VERSION, "step": step}
    meta.update(fields)
    meta["started"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return json.dumps({"_meta": meta}) + "\n"


def _output_collisions(rels: list) -> dict:
    """{losing source: kept source} for sources that translate to one output path.

    `translate` names a deck's output by replacing its extension with `.nec`,
    so `foo.inp` and `foo.nec` (or `foo.NEC` and `foo.nec` on a case-insensitive
    filesystem) land on the same file, and before antennaknobs#1435 the second
    one written silently replaced the first. The kept source is decided before
    anything is written: an exact `.nec` source wins, because that is what the
    tree held before this rule existed and deck paths are every report's join
    key; otherwise the first in sorted order.
    """
    groups = {}
    for rel in rels:
        stem = re.sub(r"\.(nec|inp)$", "", rel, flags=re.I).casefold()
        groups.setdefault(stem, []).append(rel)
    kept_over = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = next((r for r in members if r.endswith(".nec")), members[0])
        for r in members:
            if r != keep:
                kept_over[r] = keep
    return kept_over


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
    report.write(
        _meta_row("translate", offcenter=args.offcenter, nofile=bool(args.nofile))
    )
    counts = {
        "translated": 0,
        "refused": 0,
        "invalid": 0,
        "unreadable": 0,
        "collision": 0,
        "decks_written": 0,
    }
    reasons = {}
    note_kinds = {}
    sources = []
    for p in _iter_decks(src):
        rel = p.relative_to(src).as_posix()
        if args.only and args.only not in rel:
            continue
        sources.append((p, rel))
        if args.limit and len(sources) >= args.limit:
            break
    n_files = len(sources)
    kept_over = _output_collisions([rel for _, rel in sources])
    claimed = {}  # output path, case-folded -> the source that wrote it
    for p, rel in sources:
        if rel in kept_over:
            rec = {
                "file": rel,
                "status": "collision",
                "notes": [],
                "reason": f"translates to the same output path as {kept_over[rel]}, "
                "which is kept (a .nec source over a same-named .inp; otherwise the "
                "first in sorted order)",
            }
        else:
            rec = translate_file(p, rel, args.offcenter, args.nofile)
        stem = re.sub(r"\.(nec|inp)$", "", rel, flags=re.I)
        dests = [
            (out / (stem + (f"_{idx}" if idx else "") + ".nec"), deck)
            for idx, deck in rec.pop("outputs", [])
        ]
        taken = [
            claimed[d.relative_to(out).as_posix().casefold()]
            for d, _ in dests
            if d.relative_to(out).as_posix().casefold() in claimed
        ]
        if taken:
            # An NX split's `_N` output landing on another source's path: the
            # stem check above cannot see it, so it is caught here, and nothing
            # of this deck is written rather than part of it.
            rec["status"] = "collision"
            rec["reason"] = (
                f"an output path of this deck was already written from {taken[0]}; "
                "not overwritten"
            )
            dests = []
        counts[rec["status"]] += 1
        if rec["status"] != "translated":
            key = re.sub(r"\d+", "N", rec["reason"])[:90]
            reasons[key] = reasons.get(key, 0) + 1
        written = []
        for dest, deck in dests:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(deck, encoding="ascii", errors="replace")
            written.append(dest.relative_to(out).as_posix())
            claimed[written[-1].casefold()] = rel
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
        f"files: {n_files}  translated: {counts['translated']}"
        f"  refused: {counts['refused']}  invalid: {counts['invalid']}"
        f"  unreadable: {counts['unreadable']}  collision: {counts['collision']}"
        f"  decks written: {counts['decks_written']}"
    )
    if reasons:
        _log("\nrefused / unreadable, by reason:")
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:25]:
            _log(f"  {v:5d}  {k}")
    if (
        counts["refused"]
        or counts["invalid"]
        or counts["unreadable"]
        or counts["collision"]
    ):
        # Three unlike claims, so a census can put each on the right ledger
        # (antennaknobs#1382, #1386). Spelled out every run, because the words
        # alone do not say whose fault the deck is.
        _log(
            "\n  refused    = no NEC-5 card for it (about NEC-5)"
            "\n  invalid    = not valid NEC input of any dialect (about the deck; no engine's fault)"
            "\n  unreadable = this tool could not read it (about this tool; NOT a claim that no program can)"
            "\n  collision  = another source translates to the same output path (about the source tree)"
        )
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
    r"|Segmentation fault|SIGSEGV|out of range|no basis function|Definition not found"
    r"|invalid pointer|double free|corrupted"
)  # case-sensitive: NEC-5 shouts its errors; a CM comment echoed in the printout may say "error"
# Lines that match the pattern above but are not failures: the Sommerfeld
# table cache probe (NEC-5 looks for SOMMPD.NEX before computing the tables,
# then writes it), the mesh-calibration remark ("... less than 1% error"),
# the all-clear, and gfortran's floating-point summary.
_NOT_ERROR_RE = re.compile(r"GMPINO: Unable to open|% error|NO ERRORS|IEEE_")
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


def run_exe(
    exe: str, deck_text: str, timeout: float, keep: Path = None, env: dict = None
) -> dict:
    """Run one deck (file names on stdin, printout in the working directory).
    Status: ok (impedance printed), ok-no-source (nothing to print: plane-wave
    or geometry-only deck), no-impedance (a source but no ANTENNA INPUT
    PARAMETERS section), error (NEC-5 said so, exit 0), crash (non-zero exit,
    code recorded, any partial printout ignored), timeout. With `keep`, the
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
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "wall_s": time.perf_counter() - t0}
        wall = time.perf_counter() - t0
        rc = proc.returncode
        outp = tdp / "model.out"
        printout = outp.read_text(errors="replace") if outp.is_file() else ""
        console = (proc.stdout or "") + (proc.stderr or "")
        errs = [
            ln.strip()
            for ln in (printout + "\n" + console).splitlines()
            if _ERROR_RE.search(ln) and not _NOT_ERROR_RE.search(ln)
        ]
        rows = _aip(printout)
        # A non-zero exit is a crash whatever the printout says: a binary that
        # dies after writing the impedance block would otherwise be scored as
        # a clean run. Windows reports an access violation as 0xC0000005 and
        # heap corruption as 0xC0000374; Linux reports the signal (-11, -6).
        if rc != 0:
            status = "crash"
            code = f"exit code {rc} (0x{rc & 0xFFFFFFFF:08X})"
            errs = [code + (": " + errs[0] if errs else "")]
            rows = []
        elif errs:
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
                printout + f"\n--- console (exit code {rc}) ---\n" + console,
                errors="replace",
            )
        return {
            "status": status,
            "exit_code": rc,
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
    engine_env, threads, timing_valid = _engine_env(args.jobs)
    report = open(args.report or (src / "check-report.jsonl"), "w", encoding="utf-8")
    environment = _environment_meta(exe, jobs=args.jobs)
    environment["engine_threads"] = threads
    report.write(
        _meta_row(
            "check",
            exe=exe,
            platform=sys.platform,
            timeout_s=args.timeout,
            timing_valid=timing_valid,
            environment=environment,
        )
    )
    if args.jobs > 1:
        pinned = [k for k in _THREAD_KEYS if k not in threads["user_set"]]
        if pinned:
            _log(
                f"--jobs {args.jobs}: pinned {', '.join(pinned)}=1 for the engine "
                "so the workers do not contend (#1403)"
            )
    if not timing_valid:
        _log(
            f"NOTE: jobs x threads exceeds {os.cpu_count()} CPUs — the per-deck "
            "wall_s in this report is NOT a speed measurement, and the report "
            "records timing_valid: false"
        )
    keep_dir = Path(args.keep_dir) if args.keep_dir else None
    counts = {}
    errors = {}
    t0 = time.perf_counter()

    def one(p):
        rel = p.relative_to(src)
        keep = (keep_dir / rel.with_suffix(".out")) if keep_dir else None
        rec = run_exe(
            exe, p.read_text(errors="replace"), args.timeout, keep, env=engine_env
        )
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
    # The version the reports record; the frozen exe (antennaknobs#1376) has
    # no other way to say which tool it is.
    ap.add_argument("--version", action="version", version="nec5_corpus.py " + VERSION)
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
        choices=("exact", "shift", "double"),
        default="exact",
        help="off-centre feeds: the cheapest count in [N, 2N] that puts them on knots (default), "
        "a half-segment move toward the centre, or a doubled mesh",
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

    d = sub.add_parser(
        "compare",
        help="diff two check reports deck by deck, refusing if their recorded "
        "environments differ (antennaknobs#1344)",
    )
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--ignore-env", action="store_true")
    d.add_argument(
        "--tol",
        type=float,
        default=1e-4,
        help="relative |dZ|/|Z| above which an impedance counts as moved "
        "(default 1e-4; last-digit printout noise sits near 1e-5)",
    )
    d.set_defaults(fn=cmd_compare)

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
