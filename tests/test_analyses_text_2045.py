"""AK#2045 piece 1: reading shared analyses text without running it.

A link carries analyses as the stylized ``an.Analysis(...)`` Python that
`analyses.to_code` prints, deflate-raw + base64url compressed. The reader
(`antennaknobs.analyses_text`) must NEVER execute it: these tests are the
refusals first (each names what it refused), then the bounds, then the
round trip of the catalog's own analyses.
"""

from __future__ import annotations

import base64
import zlib

import pytest

from antennaknobs import analyses as an
from antennaknobs import analyses_text as at

# ── refusals: each names the node it refused ─────────────────────────────────

REFUSED = [
    # imports and builtins
    ("import os", "does not parse"),
    ("__import__('os')", "refused: call of Name '__import__'"),
    (
        "__import__('os').system('true')",
        "refused: call of Attribute \"__import__('os').system\"",
    ),
    ("__import__", "refused: Name '__import__'"),
    ("os", "refused: Name 'os'"),
    ("open('/etc/passwd')", "refused: call of Name 'open'"),
    ("eval('1')", "refused: call of Name 'eval'"),
    # dunder and other attribute access
    ("an.__class__", "refused: Attribute 'an.__class__'"),
    ("an.__dict__", "refused: Attribute 'an.__dict__'"),
    ("an.Analysis.__init__", "refused: Attribute 'an.Analysis.__init__'"),
    ("an.Sweep.__globals__", "refused: Attribute 'an.Sweep.__globals__'"),
    ("an.os", "refused: Attribute 'an.os'"),
    ("an.Analysis", "refused: Attribute 'an.Analysis'"),
    ("().__class__", "refused: Attribute '().__class__'"),
    ("x.Analysis(name='a')", "refused: call of Attribute 'x.Analysis'"),
    # calls on attributes that are not whitelisted constructors
    ("an.to_code(1)", "refused: call of Attribute 'an.to_code'"),
    ("an.from_data({})", "refused: call of Attribute 'an.from_data'"),
    ("an.importable(1)", "refused: call of Attribute 'an.importable'"),
    ("an.__getattr__('x')", "refused: call of Attribute 'an.__getattr__'"),
    ("an.json.loads('1')", "refused: call of Attribute 'an.json.loads'"),
    ("an.Metric('m', print)", "refused: an.Metric: a callable metric"),
    ("an.Sweep('k', 1, 2)()", "refused: call of Call"),
    # lambda, comprehensions, f-strings, conditionals, walrus
    ("lambda: 0", "refused: Lambda"),
    ("[x for x in ()]", "refused: ListComp"),
    ("(x for x in ())", "refused: GeneratorExp"),
    ("{x for x in ()}", "refused: SetComp"),
    ("{x: 1 for x in ()}", "refused: DictComp"),
    ("f'{an}'", "refused: JoinedStr"),
    ("1 if True else 2", "refused: IfExp"),
    ("(y := 1)", "refused: NamedExpr"),
    ("{1, 2}", "refused: Set"),
    # starred and **kwargs
    ("an.Sweep(*('k', 1, 2))", "refused: Starred argument to an.Sweep"),
    ("an.Analysis(**{'name': 'a'})", "refused: ** argument to an.Analysis"),
    ("[*()]", "refused: Starred"),
    ("{**{}}", "refused: ** in a dict"),
    ("{1: 2}", "refused: dict key Constant"),
    # subscripts and slices
    ("an.Sweep('k', 1, 2)[0]", "refused: Subscript"),
    ("()[0:1]", "refused: Subscript"),
    # operators beyond a unary minus on a literal number
    ("1 + 2", "refused: BinOp"),
    ("2 ** 99999999", "refused: BinOp"),
    ("'a' * 10", "refused: BinOp"),
    ("-'a'", "refused: UnaryOp USub; only a minus on a literal number"),
    ("+1", "refused: UnaryOp UAdd"),
    ("~1", "refused: UnaryOp Invert"),
    ("not 1", "refused: UnaryOp Not"),
    ("--1", "refused: UnaryOp USub"),
    ("1 < 2", "refused: Compare"),
    ("1 and 2", "refused: BoolOp"),
    # other constants
    ("b'x'", "refused: Constant of type bytes"),
    ("1j", "refused: Constant of type complex"),
    ("...", "refused: Constant of type ellipsis"),
    # positional arguments beyond what the printed form writes
    (
        "an.Analysis('a', an.Sweep('k', 1, 2), (an.Rx(),))",
        "refused: positional argument 3 to an.Analysis, which takes 2",
    ),
    ("an.Sweep('k', 1, 2, 5)", "refused: positional argument 4 to an.Sweep"),
    ("an.Rx(1)", "refused: positional argument 1 to an.Rx, which takes 0"),
    ("an.convergence('x')", "refused: positional argument 1 to an.convergence"),
    ("an.State('s', 'dipoles.invvee')", "refused: positional argument 2 to an.State"),
    # a private keyword
    ("an.Rx(_x=1)", "refused: keyword '_x' to an.Rx"),
]


@pytest.mark.parametrize(("text", "words"), REFUSED)
def test_refused_by_name(text, words):
    wrapped = f"an.Analysis('a', an.Sweep('k', 1, 2), views=({text},))"
    for t in (text, wrapped, f"[{text}]"):
        with pytest.raises(at.AnalysesTextError) as e:
            at.read(t)
        assert words in str(e.value), (t, str(e.value))


def test_nothing_is_built_before_the_whole_text_is_checked():
    # A refusal late in the text stops the read before the first value is
    # constructed: the check walks the whole tree first.
    good = "an.Analysis('a', an.Sweep('k', 1, 2), views=(an.Rx(),))"
    with pytest.raises(at.AnalysesTextError, match="Name 'os'"):
        at.read(f"[{good}, os]")


def test_a_non_analysis_at_the_top_level_is_refused():
    with pytest.raises(at.AnalysesTextError, match="Sweep at the top level"):
        at.read("an.Sweep('k', 1, 2)")
    with pytest.raises(at.AnalysesTextError, match="int at the top level"):
        at.read("[1]")


def test_a_constructors_own_refusal_reads_through():
    with pytest.raises(at.AnalysesTextError, match="an.Role: Role: one of"):
        at.read("an.Analysis('a', an.Sweep(an.Role('height_x')), views=(an.Rx(),))")
    with pytest.raises(at.AnalysesTextError, match="an.Analysis"):
        at.read("an.Analysis('a', an.Sweep('k', 1, 2), nope=1)")


def test_not_text():
    with pytest.raises(at.AnalysesTextError, match="does not parse"):
        at.read("an.Analysis(")
    with pytest.raises(at.AnalysesTextError, match="must be a string"):
        at.read(b"[]")


# ── bounds ───────────────────────────────────────────────────────────────────


def test_oversized_text_is_refused_unparsed():
    text = "[" + "1," * at.MAX_TEXT_CHARS + "]"
    with pytest.raises(at.AnalysesTextError, match="byte limit"):
        at.read(text)


def test_deep_nesting_is_refused_before_parsing():
    deep = "(" * (at.MAX_DEPTH + 1) + "1" + ")" * (at.MAX_DEPTH + 1)
    with pytest.raises(
        at.AnalysesTextError, match=f"nesting deeper than {at.MAX_DEPTH}"
    ):
        at.read(deep)
    # far past the parser's own limit, still a refusal by name
    deeper = "[" * 50_000
    with pytest.raises(at.AnalysesTextError, match="nesting deeper"):
        at.read(deeper)


def test_brackets_inside_a_string_do_not_count_toward_depth():
    name = "(" * (at.MAX_DEPTH * 4)
    (a,) = at.read(f"an.Analysis({name!r}, an.Sweep('k', 1, 2), views=(an.Rx(),))")
    assert a.name == name


def test_long_operator_chains_are_refused_not_crashed():
    for text in ("-" * 30_000 + "1", "1" + "+1" * 30_000, "an" + ".a" * 20_000):
        with pytest.raises(at.AnalysesTextError):
            at.read(text)


def test_too_many_nodes():
    text = "[" + ",".join(["1"] * (at.MAX_NODES + 1)) + "]"
    assert len(text) < at.MAX_TEXT_CHARS
    with pytest.raises(at.AnalysesTextError, match="tree nodes"):
        at.read(text)


def _raw_deflate(data: bytes) -> str:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.urlsafe_b64encode(c.compress(data) + c.flush()).decode().rstrip("=")


def test_a_decompression_bomb_is_stopped_at_the_bound():
    z = _raw_deflate(b" " * 50_000_000)  # 50 MB of spaces, ~50 KB packed
    z = z[: at.MAX_PACKED_CHARS]  # what fits the parameter still expands far
    with pytest.raises(at.AnalysesTextError, match="decompress past"):
        at.unpack(z)
    small_bomb = _raw_deflate(b" " * (at.MAX_TEXT_CHARS + 1))
    assert len(small_bomb) < 200
    with pytest.raises(at.AnalysesTextError, match="decompress past"):
        at.unpack(small_bomb)


def test_an_oversized_parameter_is_refused_unread():
    with pytest.raises(at.AnalysesTextError, match="over the 16000 limit"):
        at.unpack("A" * (at.MAX_PACKED_CHARS + 1))


def test_a_parameter_that_does_not_decode():
    for z in ("!!!!", "AAAA", _raw_deflate(b"\xff\xfe")):
        with pytest.raises(at.AnalysesTextError):
            at.unpack(z)
    with pytest.raises(at.AnalysesTextError, match="cut short"):
        at.unpack(_raw_deflate(b"x" * 1000)[:-4])
    with pytest.raises(at.AnalysesTextError, match="carries no analyses"):
        at.unpack("")


def test_pack_matches_the_browsers_padding_free_base64url():
    z = at.pack("[an.knob('x')]")
    assert "=" not in z and "+" not in z and "/" not in z
    assert at.unpack(z) == "[an.knob('x')]"


# ── the round trip ───────────────────────────────────────────────────────────


def _design_analyses():
    from antennaknobs.designs.dipoles import invvee, two_wire_doublet
    from antennaknobs.designs.verticals import m0agp_invl
    from antennaknobs.designs.wire import doublet_remote_tuner

    out = []
    for mod in (two_wire_doublet, invvee, m0agp_invl, doublet_remote_tuner):
        out += [(mod.__name__, a) for a in mod.Builder().build_analyses()]
    return out


def _catalog_studies():
    from antennaknobs import studies

    return [
        (s.source, s.analysis)
        for s in studies._catalog().studies
        if isinstance(s.analysis, an.Analysis)
    ]


def _round_trip(analyses):
    text = at.write(analyses)
    return at.read_link(at.pack(text))


def test_two_wire_doublets_three_analyses_round_trip():
    from antennaknobs.designs.dipoles import two_wire_doublet

    analyses = tuple(two_wire_doublet.Builder().build_analyses())
    assert len(analyses) == 3
    assert _round_trip(analyses) == analyses
    # and the text it reads is the text a design file writes
    back = at.read(at.write(analyses))
    assert [a.hold for a in back] == [
        None,
        an.Hold("resonance", adjust=("short_ft",)),
        an.Hold("resonance", adjust=("long_ft",)),
    ]


def test_every_catalog_analysis_round_trips_or_names_its_metric():
    cases = _design_analyses() + _catalog_studies()
    assert len(cases) >= 10
    read = 0
    for source, a in cases:
        if an.metrics_of(a):
            with pytest.raises(at.AnalysesTextError, match="an.Metric"):
                _round_trip((a,))
            continue
        assert _round_trip((a,)) == (a,), source
        read += 1
    assert read >= 8


def test_a_parenthesised_negative_literal_is_a_literal():
    (a,) = at.read("an.Analysis('a', an.Sweep('k', -(1), 2), views=(an.Rx(),))")
    assert a.sweep.lo == -1


def test_the_library_forms_read_back():
    for a in (an.convergence(), an.band_swr(), an.patterns(), an.knob("base")):
        assert at.read(an.to_code(a)) == (a,)
    assert at.read("an.convergence(ground='free')") == (an.convergence(ground="free"),)


def test_a_state_with_a_group_knob_and_negative_numbers():
    a = an.Analysis(
        "s",
        an.Sweep("k", -2.5, 3),
        views=(an.Rx(),),
        cross=an.Cross(
            states=(
                an.State("as built"),
                an.State("g", bands=({"freq": 14.3, "length_factor": 0.49},)),
            )
        ),
    )
    assert at.read(at.write(a)) == (a,)
