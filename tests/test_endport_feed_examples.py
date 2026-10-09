"""dipoles.invvee_endport and beams.yagi_endport — the end-port feed.

The arms stop a real gap apart and the source sits across their two ENDS
(two `PortAtEnd` junction ports joined by a 1:1 `FloatingBalun`). Values
measured 2026-10-09 at the stock 10 m defaults in free space, momwire bs2.

The load-bearing check is the limit: the end-port reading is linear in the
gap (the missing metal), and its gap → 0 extrapolation lands on the apex
feed, which is the same vee with the arms closed and a series gap at the
vertex. Two independent port mechanisms meeting there is what says the
FloatingBalun-across-two-ends construction reads the differential Z.
"""

import pytest

from antennaknobs.designs.beams.yagi import Builder as StockYagi
from antennaknobs.designs.beams.yagi_endport import Builder as EndYagi
from antennaknobs.designs.dipoles.invvee_apex import Builder as Apex
from antennaknobs.designs.dipoles.invvee_endport import Builder as EndVee
from antennaknobs.engines.momwire import MomwireEngine

# At the default 1 cm gap, and at 0.1 m (the stock bridge length).
Z_VEE_END = 53.946 - 16.399j
Z_YAGI_END = 34.213 - 41.423j
Z_VEE_END_10CM = 49.432 - 49.045j
Z_YAGI_END_10CM = 31.703 - 78.913j


def _z(builder):
    return complex(MomwireEngine(builder, ground=None).impedance()[0])


def _with(cls, **kw):
    b = cls()
    for k, v in kw.items():
        setattr(b, k, v)
    return b


@pytest.mark.antenna_computation_check
def test_endport_readings_are_pinned():
    assert EndVee().gap == EndYagi().gap == 0.01
    assert abs(_z(EndVee()) - Z_VEE_END) < 0.5
    assert abs(_z(EndYagi()) - Z_YAGI_END) < 0.5
    assert abs(_z(_with(EndVee, gap=0.1)) - Z_VEE_END_10CM) < 0.5
    assert abs(_z(_with(EndYagi, gap=0.1)) - Z_YAGI_END_10CM) < 0.5


@pytest.mark.antenna_computation_check
def test_endport_vee_extrapolates_to_the_apex_feed():
    z2 = _z(_with(EndVee, gap=0.02))
    z1 = _z(_with(EndVee, gap=0.01))
    extrap = 2 * z1 - z2
    za = _z(Apex())
    assert abs(extrap - za) < 0.5, (extrap, za)
    # and the gap is not free: 0.1 m of missing metal is tens of ohms of X
    assert _z(_with(EndVee, gap=0.1)).imag < za.imag - 20


@pytest.mark.antenna_computation_check
def test_endport_yagi_keeps_the_stock_parasitics():
    stock, end = StockYagi(), _with(EndYagi, gap=0.1)
    ws, we = stock.build_wires(), end.build_wires()
    assert len(we) == len(ws) - 1  # the bridge is gone, nothing else
    assert list(we[1:3]) == list(ws[1:3]) and list(we[4:]) == list(ws[5:])
    gs = MomwireEngine(stock, ground=None).far_field().max_gain
    ge = MomwireEngine(end, ground=None).far_field().max_gain
    assert abs(gs - ge) < 0.3  # the feed model moves Z, barely the pattern


def test_endport_designs_get_the_junction_port_backends():
    import antennaknobs.web.examples  # noqa: F401 — registration order, as the adapter needs
    from antennaknobs.web import adapter

    for cls in (EndVee, EndYagi):
        assert adapter._required_backends(cls) == adapter._JUNCTION_PORT_BACKENDS
