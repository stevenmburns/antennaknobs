"""AK#1510 unit 1: `site_count` in closed form.

A position p/q in lowest terms is a knot of an m-segment wire iff q divides m,
and a segment centre iff q is even and m is an odd multiple of q/2. The closed
form must return exactly what the search it replaced returns for every count up
to the cap, so the search is kept here, verbatim and independent of the module,
as the reference. The uncapped rule underneath is checked on its own against
rational arithmetic, because a count it wrongly offers is caught by `on_site`
before `site_count` returns it.
"""

from __future__ import annotations

import itertools
import math
from fractions import Fraction

import pytest

from antennaknobs.wire_catalog import _first_site_count, site_count

CAPS = (2, 3)
FAMILIES = ("centre", "knot")
COUNTS = range(1, 41)


def _search(n_seg, positions, family, cap):
    """The AK#1469 search: every count from `n_seg` to ``cap * n_seg``, each
    position tested for a site within 1e-9 of the wire's length."""

    def on_site(m, at):
        x = (0.5 if at is None else float(at)) * m
        if family == "centre":
            x -= 0.5
        return abs(x - round(x)) <= 1e-9 * max(m, 1)

    n = max(int(n_seg), 1)
    for m in range(n, cap * n + 1):
        if all(on_site(m, at) for at in positions):
            return m
    return None


def _mismatches(cases):
    return [
        (n, positions, family, cap, got, want)
        for n, positions, family, cap in cases
        if (got := site_count(n, positions, family, cap=cap))
        != (want := _search(n, positions, family, cap))
    ]


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("cap", CAPS)
def test_every_integer_percentage_matches_the_search(cap, family):
    cases = [(n, [pct / 100], family, cap) for n in COUNTS for pct in range(1, 100)]
    assert _mismatches(cases) == []


# A deck's percentage can come through SY arithmetic, and a design port is any
# float: none of these is exactly the rational it stands for.
SY_PERCENTAGES = (100 / 3, 200 / 3, 50 / 3, 100 / 7, 12.5, 37.5, 62.5, 87.5)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("cap", CAPS)
def test_a_middle_port_and_arithmetic_percentages_match_the_search(cap, family):
    cases = [(n, [None], family, cap) for n in COUNTS]
    cases += [(n, [p / 100], family, cap) for n in COUNTS for p in SY_PERCENTAGES]
    cases += [(n, [1 / 3], family, cap) for n in COUNTS]
    assert _mismatches(cases) == []


TWO_PORT_POSITIONS = (
    None,
    0.5,
    0.25,
    0.75,
    0.125,
    0.375,
    0.3,
    0.1,
    0.2,
    0.6,
    0.05,
    1 / 3,
    1 / 6,
)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("cap", CAPS)
def test_two_ports_on_one_wire_match_the_search(cap, family):
    cases = [
        (n, list(pair), family, cap)
        for n in COUNTS
        for pair in itertools.combinations(TWO_PORT_POSITIONS, 2)
    ]
    assert _mismatches(cases) == []


@pytest.mark.parametrize("cap", CAPS)
def test_centres_whose_halves_differ_in_their_power_of_two_never_fit(cap):
    # 0.25 needs an odd multiple of 2, the middle an odd count: no count is both.
    for n in COUNTS:
        assert site_count(n, [0.25, None], "centre", cap=cap) is None
        assert _search(n, [0.25, None], "centre", cap) is None
    # 0.25 and 0.75 share their half, 2, so 2 mod 4 serves both.
    assert site_count(20, [0.25, 0.75], "centre") == 22


@pytest.mark.parametrize("at", [0.3183, 0.123456789, math.pi / 10])
@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("cap", CAPS)
def test_an_arbitrary_float_is_a_site_at_no_count_up_to_the_cap(at, family, cap):
    for n in COUNTS:
        assert site_count(n, [at], family, cap=cap) is None
        assert _search(n, [at], family, cap) is None


@pytest.mark.parametrize(
    ("n", "at", "knot", "centre"),
    [
        (2, 0.5, 2, 3),
        (10, 0.3, 10, 15),
        (10, 0.31, 100, 50),
        (10, 1 / 3, 12, None),  # an odd denominator is a centre at no count
    ],
)
def test_the_issue_table_past_the_cap(n, at, knot, centre):
    assert site_count(n, [at], "knot", cap=400) == knot
    assert site_count(n, [at], "centre", cap=400) == centre


def test_a_position_close_to_two_fractions_on_a_long_wire_searches_every_count():
    """2/50001 is within 1e-9 of 1/25000, a knot of 25000 segments, and the
    closest fraction with a small enough denominator is itself, which no count
    up to the cap has as a knot. The closed form alone would answer None; the
    search accepts 25000, and so must `site_count`."""
    at = 2 / 50001
    assert _search(20000, [at], "knot", 2) == 25000
    assert site_count(20000, [at], "knot") == 25000


def _first_exact(n, fractions, family):
    """The first count from n up at which every fraction is exactly a site, by
    rational arithmetic. Each condition repeats with period 2q, so one period
    of their lcm past n settles "no count at all"."""
    half = Fraction(1, 2) if family == "centre" else 0
    period = math.lcm(*(2 * f.denominator for f in fractions))
    for m in range(n, n + period + 1):
        if all((f * m - half).denominator == 1 for f in fractions):
            return m
    return None


SMALL_FRACTIONS = sorted(
    {Fraction(p, q) for q in range(1, 25) for p in range(q + 1)},
)


@pytest.mark.parametrize("family", FAMILIES)
def test_the_uncapped_rule_is_exact_for_every_small_fraction(family):
    bad = [
        (n, f, got, want)
        for n in range(1, 31)
        for f in SMALL_FRACTIONS
        if (got := _first_site_count(n, [f], family))
        != (want := _first_exact(n, [f], family))
    ]
    assert bad == []


@pytest.mark.parametrize("family", FAMILIES)
def test_the_uncapped_rule_is_exact_for_pairs(family):
    pool = [Fraction(s) for s in "1/2 1/4 3/4 1/3 1/6 3/10 1/8 5/12 7/20".split()]
    bad = [
        (n, pair, got, want)
        for n in range(1, 31)
        for pair in itertools.combinations(pool, 2)
        if (got := _first_site_count(n, list(pair), family))
        != (want := _first_exact(n, list(pair), family))
    ]
    assert bad == []


def test_no_positions_keep_the_count():
    assert site_count(7, [], "centre") == _search(7, [], "centre", 2) == 7
