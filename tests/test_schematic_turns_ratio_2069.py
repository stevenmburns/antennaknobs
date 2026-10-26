"""The schematic reads a transformer's turns primary:secondary (AK#2069).

momwire's `Transformer.n` is a:b with v_a = n·v_b, port a the primary, so a
1:7 step-up is n = 1/7 and must draw as 1:7, not 1:0.143 (Dan AC6LA's report
on Mike WA7ARK's EFHW). `FloatingBalun.n` runs the other way, secondary per
primary, and keeps its label.
"""

from __future__ import annotations

import pytest

from antennaknobs.network import FloatingBalun, Transformer
from antennaknobs.schematic import default_elements


@pytest.mark.parametrize(
    "n, label",
    [
        (1.0 / 7.0, "1:7"),
        (0.1428571, "1:7"),
        (1.0 / 3.0, "1:3"),
        (2.0, "1:0.5"),
        (1.0, "1:1"),
    ],
)
def test_a_transformer_draws_primary_to_secondary(n, label):
    (el,) = default_elements(Transformer(a="rig", b="feed", n=n))
    assert (el.kind, el.label) == ("transformer", label)


def test_a_floating_balun_keeps_its_secondary_per_primary_label():
    (el,) = default_elements(FloatingBalun(primary="rig", a="p", b="q", n=2.0))
    assert el.label == "balun 1:2"
