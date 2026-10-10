"""`wire.doublet_remote_tuner`: WA7ARK's doublet on window line, through a
balun into a remote L-network tuner whose parts are knobs.

What is pinned:

* the manual tuner: the stock parts match the stock station at 7.15 MHz,
  the parts are FIXED across a sweep (no retune anywhere: the momwire sweep,
  the external engines' per-point sweep), and Optimize at a measurement
  frequency finds the parts that match there (the AK#1664 refusal no longer
  fires, and is shown to fire in the auto mode, the red control);
* the design has no design frequency: the workbench shows no band row, and
  the mesh does not move with the band;
* the auto mode (the per-band analysis, ``band-loss``): the auto-tuner
  presents 50 Ω at the rig (SWR 1) on every band it can reach, the load it
  reports is what a VNA on its output jack reads (the ``tuner`` measurement
  plane), a 1:4 balun divides that load by 4 (with a RED CONTROL: the
  impedance ratio used as the voltage ratio divides it by 16), fed Mike's own
  loads the tuner arithmetic chooses his parts, and a part out of range is
  flagged;
* the losses band by band (`band_loss`) and the line-length search.
"""

from __future__ import annotations

import importlib
import warnings

import numpy as np
import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.auto_match import (
    TunerAdvisory,
    design_l_match,
    tuner_design,
    tuner_rows,
)
from antennaknobs.designs.wire import doublet_remote_tuner as mod
from antennaknobs.designs.wire.doublet_remote_tuner import Builder
from antennaknobs.cli import cli

cli_mod = importlib.import_module("antennaknobs.cli")

GROUND = ("finite", 13.0, 0.005)
#: One frequency per character of load: 80 m (inductive, R > 50), 40 m
#: (R < 50: the capacitor moves to the rig side), 20 m and 10 m.
FREQS = (3.6, 7.0, 14.0, 28.0)


def _builder(cls=Builder, **kw):
    """The design in its AUTO mode, as the per-band analysis and band-loss
    solve it: the tuner tunes itself at ``freq``."""
    return cls(params={**Builder.default_params, "tuner_mode": "auto", **kw})


def _manual(**kw):
    """The design as the workbench has it: the knobs' parts."""
    return Builder(params={**Builder.default_params, **kw})


def _solve(builder):
    from antennaknobs.engines import MomwireEngine

    eng = MomwireEngine(builder, ground=GROUND)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        z = complex(np.atleast_1d(eng.impedance())[0])
    advisories = [w for w in caught if issubclass(w.category, TunerAdvisory)]
    return eng, z, advisories


def _swr(z, z0=50.0):
    g = abs((z - z0) / (z + z0))
    return (1 + g) / (1 - g)


@pytest.mark.parametrize("ratio", ["1:1", "1:4"])
@pytest.mark.parametrize("f", FREQS)
def test_the_autotuner_matches_the_rig_on_every_band(f, ratio):
    eng, z, advisories = _solve(_builder(freq=f, balun_ratio=ratio))
    d = tuner_design(eng)
    assert d is not None and d.matched and not d.bypass and d.best_swr is None
    assert not advisories
    assert _swr(z) == pytest.approx(1.0, abs=1e-6)
    # Inside the MFJ-926B's ranges, which the design states.
    assert 0 < d.series <= 24.86e-6 and 0 < d.shunt <= 3961e-12
    # It retuned HERE: the tuning is at this band, not the design frequency.
    assert d.f_mhz == pytest.approx(f)


def test_the_capacitor_side_follows_the_load():
    """The relay of a switched-L auto-tuner: the capacitor across the balun
    when the load's R is above 50 Ω, across the rig when it is below."""
    for f in FREQS:
        d = tuner_design(_solve(_builder(freq=f))[0])
        assert d.shunt_at == ("out" if d.z_load.real > 50.0 else "rig")
    # On 40 m this model's load is below 50 Ω even at 1:1 (module docstring).
    assert tuner_design(_solve(_builder(freq=7.0))[0]).shunt_at == "rig"


def test_the_reported_load_is_what_a_vna_at_the_tuner_jack_reads():
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.plane import driven_at, planes_of

    b = _builder(freq=14.0)
    assert "tuner" in planes_of(b.build_network())
    d = tuner_design(_solve(b)[0])
    pruned = driven_at(b.build_network(), "tuner")
    vna = _builder(freq=14.0)
    object.__setattr__(vna, "build_network", lambda: pruned)
    z_jack = complex(np.atleast_1d(MomwireEngine(vna, ground=GROUND).impedance())[0])
    assert z_jack == pytest.approx(d.z_load, rel=1e-9)


def test_the_readout_shows_the_load_and_the_parts():
    rows = {r["label"]: r for r in tuner_rows(_solve(_builder(freq=3.6))[0])}
    assert rows["load"]["unit"] == "Ω" and " + j" in rows["load"]["value"]
    assert rows["series L"]["unit"] == "µH" and rows["shunt C"]["unit"] == "pF"


def _load(cls, f, ratio):
    return tuner_design(_solve(_builder(cls, freq=f, balun_ratio=ratio))[0]).z_load


def _assert_balun_divides_by_four(cls):
    for f in (3.6, 14.0):
        z1, z4 = _load(cls, f, "1:1"), _load(cls, f, "1:4")
        assert z1 / z4 == pytest.approx(4.0, rel=1e-9), f"{f} MHz: {z1 / z4}"


def test_a_1_4_balun_quarters_the_load_at_the_tuner():
    _assert_balun_divides_by_four(Builder)


class _ImpedanceRatioAsTurns(Builder):
    """The red control: the balun's impedance ratio used as its VOLTAGE
    ratio (n = 4 for a 1:4), so the load is divided by 16."""

    def balun_n(self) -> float:
        return mod.BALUN_RATIOS[self.balun_ratio]


def test_red_control_a_wrongly_applied_ratio_fails_the_balun_check():
    z1, z4 = (
        _load(_ImpedanceRatioAsTurns, 3.6, "1:1"),
        _load(_ImpedanceRatioAsTurns, 3.6, "1:4"),
    )
    assert z1 / z4 == pytest.approx(16.0, rel=1e-9)
    with pytest.raises(AssertionError):
        _assert_balun_divides_by_four(_ImpedanceRatioAsTurns)


#: Mike's 1:1 table (EZNEC/AutoEZ): the load at the tuner, then the parts
#: he gives for it.
MIKE = {
    3.6: (75.60 + 289.84j, 10.37, 323.4),
    7.0: (62.75 - 26.89j, 0.793, 83.2),
    14.0: (561.21 + 443.56j, 2.33, 62.3),
    28.0: (195.33 - 3.91j, 0.483, 49.3),
}


@pytest.mark.parametrize("f", sorted(MIKE))
def test_fed_mikes_loads_the_tuner_chooses_his_parts(f):
    z, l_uH, c_pF = MIKE[f]
    d = design_l_match(z, 50.0, f, "low", shunt_at="auto")
    # His tuner never switches at 1:1: every load of his is above 50 Ω.
    assert d.shunt_at == "out"
    assert d.series * 1e6 == pytest.approx(l_uH, rel=0.02)
    assert d.shunt * 1e12 == pytest.approx(c_pF, rel=0.02)


def test_mikes_80m_load_is_reproduced():
    """Where the antenna models agree (80 m, the doublet near a half wave),
    the load at the tuner is his to a few percent; the upper bands differ
    in the antenna model (module docstring)."""
    z = _load(Builder, 3.6, "1:1")
    assert abs(z - MIKE[3.6][0]) / abs(MIKE[3.6][0]) < 0.03


def test_a_part_out_of_range_is_flagged_and_the_swr_shows_it():
    # 80 m needs ~315 pF; give the tuner a 200 pF capacitor.
    eng, z, advisories = _solve(_builder(freq=3.6, tuner_c_max_pF=200.0))
    d = tuner_design(eng)
    assert not d.matched and d.best_swr is not None and d.best_swr > 1.05
    assert advisories and "above its maximum" in str(advisories[0].message)
    assert _swr(z) == pytest.approx(d.best_swr, rel=1e-3)


def test_the_line_common_mode_return_does_not_move_the_load():
    """The doublet is symmetric about its feed, so no common-mode current
    flows and the required ``line_zcomm`` is a formality."""
    z = [_load(Builder, 14.0, "1:1")]
    z.append(tuner_design(_solve(_builder(freq=14.0, line_zcomm=100.0))[0]).z_load)
    assert z[1] == pytest.approx(z[0], rel=1e-6)


def _run(a, capsys):
    def factory_for(engine, ground, density):
        return cli_mod.make_engine_factory(
            engine, cli_mod.parse_ground(ground) if ground else None
        )

    out = ar.run(
        a,
        lambda: Builder(),
        factory_for=factory_for,
        ground_label_for=lambda spec: spec or "free",
        session_engine="momwire",
    )
    return out, capsys.readouterr().out


def test_the_per_band_table_retunes_at_every_frequency(capsys):
    """The design's analysis, cut to two bands and one balun: a ``freq``
    KNOB sweep builds once per point, so the tuner retunes at each, and the
    Table prints what it saw and chose beside the rig's 50 Ω."""
    (own,) = Builder().build_analyses()
    a = an.Analysis(
        own.name,
        an.Sweep("freq", values=(3.6, 28.0)),
        cross=(an.Cross(states=(own.crosses[0].states[0],)), own.crosses[1]),
        views=own.views,
        ground=own.ground,
    )
    out, text = _run(a, capsys)
    # Only the rig cell has a tuner: the tuner-jack plane cuts it away.
    ((label, bands),) = out["tunings"].items()
    assert label == "1:1 balun, rig"
    assert [b.tuning.f_mhz for b in bands] == [3.6, 28.0]
    assert "-- tuner and losses, retuned at each freq: 1:1 balun, rig --" in text
    rows = [ln.split() for ln in text.splitlines() if ln.strip().startswith("28 ")]
    # The rig's row (50 Ω), the jack's row (the load), the tuner table's row.
    assert any(r[1] == "50.000" for r in rows)
    assert any("series" in r for r in rows)
    jack = out["curves"]["1:1 balun, tuner"][1]
    for b, z in zip(bands, jack, strict=True):
        assert b.tuning.matched and b.tuning.best_swr is None
        assert z == pytest.approx(b.tuning.z_load, rel=1e-9)
        assert 0.85 < b.antenna_fraction < 1.0


def test_a_frequency_sweep_shows_the_fixed_parts(capsys):
    """Swept as the frequency ROLE on the stock (manual) design: the parts
    are the knobs', so nothing retunes and nothing reports a tuning. The
    stock parts match at 7.15 MHz and the SWR rises off it."""
    a = an.Analysis(
        "fixed",
        an.Sweep(an.FREQUENCY, values=(7.15, 7.3)),
        views=(an.Table(),),
        ground="finite:13,0.005",
    )
    out, text = _run(a, capsys)
    assert "tunings" not in out and "retuned" not in text
    ((xs, zs),) = out["curves"].values()
    assert _swr(zs[0]) < 1.01
    assert _swr(zs[1]) > 1.5


@pytest.mark.antenna_computation_check
def test_the_design_analysis_runs_from_the_command_line(capsys):
    """``antennaknobs analyze --builder wire.doublet_remote_tuner --analysis
    "tuner per band"``: every band of Mike's table, both baluns, every band
    in range of the stock tuner."""
    cli(
        [
            "analyze",
            "--builder",
            "wire.doublet_remote_tuner",
            "--analysis",
            "tuner per band",
        ]
    )
    text = capsys.readouterr().out
    for cell in ("1:1 balun, rig", "1:4 balun, rig"):
        assert f"-- tuner and losses, retuned at each freq: {cell} --" in text
    assert "best effort" not in text and "bypassed" not in text
    assert text.count(" 50.000 ") == 2 * len(mod.BAND_FREQS)


# ── the losses, band by band (`band_loss`), and the line-length search ──────


def _engine(**kw):
    from antennaknobs.engines import MomwireEngine

    return MomwireEngine(_builder(**kw), ground=GROUND)


def _antenna_port_power(eng) -> float:
    """The power the antenna's ports accept, from the MoM side alone: the
    excited state's port voltages against the antenna's own port admittance,
    ½·Re(Vᴴ·Y·V). No network branch enters it."""
    wl = eng._wavelength_for(eng.builder.freq)
    Y = eng._compute_y_matrix(wl)
    eng._reducer.driven_impedance(Y, wl)
    v, _eff, _p_in, _rows = eng._reducer.excited_state(Y, wl)
    v = np.asarray(v)[: Y.shape[0]]
    return 0.5 * float(np.real(np.conj(v) @ Y @ v))


def _assert_energy_balance(band, p_antenna):
    assert band.p_in == pytest.approx(
        sum(w for _, w in band.losses) + p_antenna, rel=1e-6
    )


@pytest.mark.parametrize("f", [3.6, 7.0, 28.0])
def test_the_losses_and_the_antenna_add_up_to_the_input(f):
    """Energy balance: the source's power is the budget's loss rows (line,
    balun, tuner coil) plus what the antenna's ports accept, the latter
    computed independently on the MoM side."""
    from antennaknobs.band_loss import engine_band_loss

    eng = _engine(freq=f, line_k1=0.1)  # a lossier line, to make it count
    band, _ = engine_band_loss(eng)
    assert {g for g, _ in band.losses} == {"tuner", "FloatingBalun", "BalancedLine"}
    assert all(w > 0 for _, w in band.losses)
    p_ant = _antenna_port_power(eng)
    _assert_energy_balance(band, p_ant)
    assert band.antenna == pytest.approx(p_ant, rel=1e-6)


def test_red_control_a_dropped_loss_row_breaks_the_balance():
    from antennaknobs.band_loss import BandLoss, engine_band_loss

    eng = _engine(freq=7.0)
    band, _ = engine_band_loss(eng)
    short = BandLoss(
        band.f_mhz,
        band.p_in,
        tuple((g, w) for g, w in band.losses if g != "BalancedLine"),
        band.tuning,
    )
    with pytest.raises(AssertionError):
        _assert_energy_balance(short, _antenna_port_power(eng))


def test_more_line_loses_more_in_the_line():
    from antennaknobs.band_loss import engine_band_loss

    short = engine_band_loss(_engine(freq=14.0, line_ft=30.0))[0]
    long_ = engine_band_loss(_engine(freq=14.0, line_ft=90.0))[0]
    assert long_.fraction("BalancedLine") > short.fraction("BalancedLine")


SEARCH_FREQS = (3.6, 7.0, 14.0, 28.0)


def _factory(b):
    from antennaknobs.engines import MomwireEngine

    return MomwireEngine(b, ground=GROUND)


def test_the_line_length_search_beats_mikes_30_ft():
    """With a 1:4 balun, 30 ft is not the best line for the worst band:
    the search, from 30 ft up (the line has to reach the ground), finds a
    length whose worst band delivers more to the antenna."""
    from antennaknobs import band_loss as bl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", TunerAdvisory)
        b = _builder(balun_ratio="1:4")
        at_30 = bl.worst(bl.band_losses(b, _factory, SEARCH_FREQS))
        res = bl.search(b, _factory, SEARCH_FREQS, "line_ft", 30.0, 100.0, step=2.0)
    assert res.reused_y
    assert res.best != pytest.approx(30.0, abs=0.5)
    assert res.worst.antenna_fraction > at_30.antenna_fraction + 0.005
    # It is the max-min of what it tried.
    assert res.worst.antenna_fraction == pytest.approx(max(v for _, v in res.tried))
    assert b.line_ft == pytest.approx(res.best)


def _key_at(b, knob, value):
    from antennaknobs import band_loss as bl

    setattr(b, knob, value)
    return bl.antenna_key(b)


def test_the_antenna_key_moves_with_the_antenna_and_only_with_it():
    """The reuse key: a network knob (line length, balun) leaves it; the
    doublet's length, its wire, and a feed moved along a wire change it."""
    from antennaknobs.cli import get_builder

    b = _builder()
    for knob, a, c in (("line_ft", 30.0, 90.0), ("balun_ratio", "1:1", "1:4")):
        assert _key_at(b, knob, a) == _key_at(b, knob, c), knob
    for knob, a, c in (("length_ft", 120.0, 140.0), ("wire_type", "ideal", "18-awg")):
        assert _key_at(b, knob, a) != _key_at(b, knob, c), knob
    # The OCF feed sits on ONE wire whose geometry never moves: only the
    # feed port's position does (review of #1967).
    ocf = get_builder("dipoles.ocf_dipole")()
    assert repr(ocf.build_wires()) == repr(
        (setattr(ocf, "feed_frac", 0.33), ocf.build_wires())[1]
    )
    assert _key_at(ocf, "feed_frac", 0.18) != _key_at(ocf, "feed_frac", 0.33)


def test_red_control_a_feed_moved_along_its_wire_is_solved_afresh():
    """``dipoles.ocf_dipole``'s ``feed_frac``: a wires-only guard called it
    unchanged and reused the admittance of the old feed position, a p_in
    several times off. The keyed cache solves it afresh and agrees with a
    fresh solve; the stale admittance (the red control) does not."""
    from antennaknobs import band_loss as bl
    from antennaknobs.cli import get_builder

    ocf = get_builder("dipoles.ocf_dipole")()
    cache: dict = {}
    ocf.feed_frac = 0.18
    bl.band_losses(ocf, _factory, (7.0,), cache)
    ((_k, y_old),) = [(k, v) for k, v in cache.items() if k != "hits"]
    ocf.feed_frac = 0.33
    cached = bl.band_losses(ocf, _factory, (7.0,), cache)[0]
    fresh = bl.band_losses(ocf, _factory, (7.0,))[0]
    assert cache.get("hits", 0) == 0
    assert cached.p_in == pytest.approx(fresh.p_in, rel=1e-12)
    ocf.freq = 7.0
    stale, _ = bl.engine_band_loss(_factory(ocf), y=y_old)
    assert abs(stale.p_in / fresh.p_in - 1.0) > 0.2


def test_the_search_reuses_the_antenna_across_line_lengths():
    from antennaknobs import band_loss as bl

    cache: dict = {}
    b = _builder()
    for line in (30.0, 40.0, 50.0):
        b.line_ft = line
        bl.band_losses(b, _factory, (7.0, 14.0), cache)
    assert cache["hits"] == 4


def test_a_mismatched_band_scores_its_reflected_power():
    """The score is a share of the power a 50 Ω rig makes AVAILABLE: with a
    200 pF capacitor the tuner cannot reach 80 m's match, the rig sees SWR
    ~6.8, and most of the available power is reflected. Scored on the power
    the station accepts instead, that band read 96.8 %, better than matched
    (review of #1967)."""
    from antennaknobs import band_loss as bl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", TunerAdvisory)
        (matched,) = bl.band_losses(_builder(), _factory, (3.6,))
        (short,) = bl.band_losses(_builder(tuner_c_max_pF=200.0), _factory, (3.6,))
    assert matched.swr == pytest.approx(1.0, abs=1e-3)
    assert short.swr > 5.0
    assert short.antenna_fraction < 0.6 < matched.antenna_fraction
    # Accepted-power scoring (the bug) would have ranked it above matched.
    assert short.antenna / short.p_in > matched.antenna / matched.p_in
    for band in (matched, short):
        total = band.gamma2 + sum(band.fraction(g) for g, _ in band.losses)
        assert total + band.antenna_fraction == pytest.approx(1.0, rel=1e-9)
    lines = bl.format_table([matched, short])
    assert any(ln.startswith("!! MHz 3.6: the tuner cannot match") for ln in lines)


@pytest.mark.parametrize("engine", ["momwire", "pynec"])
def test_wire_loss_is_a_loss_row_on_every_engine(engine):
    """A lossy antenna wire's I²R is its own budget row on both engines (the
    in-process momwire path used to count it as reaching the antenna), and
    the two engines agree on it."""
    from antennaknobs import band_loss as bl
    from antennaknobs.engines import MomwireEngine
    from antennaknobs.engines.pynec import PyNECEngine

    cls = {"momwire": MomwireEngine, "pynec": PyNECEngine}[engine]
    (band,) = bl.band_losses(
        _builder(wire_type="18-awg"),
        lambda b: cls(b, ground=GROUND),
        (3.6,),
    )
    wire = dict(band.losses)["wire loss"]
    assert wire > 0.01 * band.p_in
    # Measured 2026-10-10: momwire 6.062e-4 W, PyNEC 6.058e-4 W of 10 mW.
    assert wire == pytest.approx(6.06e-4, rel=0.01)


def test_a_command_line_bool_reads_false_as_false():
    from antennaknobs.band_loss import parse_knob_value

    assert parse_knob_value(True, "False") is False
    assert parse_knob_value(False, "yes") is True
    assert parse_knob_value(1.0, "2.5") == 2.5
    assert parse_knob_value("1:1", "1:4") == "1:4"
    with pytest.raises(ValueError):
        parse_knob_value(True, "maybe")


def test_a_floating_port_is_found_on_the_load_side():
    """`auto_match._port_node`: a floating gap is wired as feed.p / feed.n,
    so both the load-side port filter and the source check look it up by its
    ``.p`` terminal. (A source on a floating gap is refused by the network
    itself, so the source check cannot be reached with one.)"""
    from antennaknobs.auto_match import _load_side, _port_node, find_tuners

    net = _builder().build_network()
    assert _port_node(net, "feed") == "feed.p"
    assert _port_node(net, "rig") == "rig"
    (t,) = find_tuners(net)
    assert "feed" in _load_side(net, t).ports


def test_band_loss_puts_the_tuner_in_its_auto_mode(capsys):
    """``band-loss`` asks what an AUTO-tuner picks, so it applies the
    design's ``band_loss_params`` (tuner_mode=auto) before its own --set:
    on 80 m the table shows the parts the tuner chose and SWR 1, not the
    stock (40 m) manual parts' mismatch."""
    cli(["band-loss", "--builder", "wire.doublet_remote_tuner", "--freqs", "3.6"])
    text = capsys.readouterr().out
    (row,) = [ln for ln in text.splitlines() if ln.strip().startswith("3.6 ")]
    assert "series L 10.7 µH" in row and "(C at out)" in row
    assert row.split("(C at out)")[1].split()[0] == "1.00"
    # The user's --set still wins: back in manual mode there is no tuning.
    cli(
        [
            "band-loss",
            "--builder",
            "wire.doublet_remote_tuner",
            "--freqs",
            "3.6",
            "--set",
            "tuner_mode=manual",
        ]
    )
    (row,) = [
        ln
        for ln in capsys.readouterr().out.splitlines()
        if ln.strip().startswith("3.6 ")
    ]
    assert "series L" not in row and "!!" not in row


@pytest.mark.antenna_computation_check
def test_band_loss_from_the_command_line(capsys):
    """``antennaknobs band-loss``: the per-band table, and the search over
    line length for both baluns, as the module docstring writes it."""
    cli(
        [
            "band-loss",
            "--builder",
            "wire.doublet_remote_tuner",
            "--each",
            "balun_ratio=1:1,1:4",
            "--search",
            "line_ft=30:100:1",
        ]
    )
    text = capsys.readouterr().out
    assert "best of balun_ratio=1:1,1:4: balun_ratio = 1:4" in text
    assert text.count("the antenna's Y reused") == 2


# ── the manual tuner on the workbench: fixed parts, no design frequency ────


def _example():
    import antennaknobs.web.examples  # noqa: F401 — registers the catalog
    from antennaknobs.web.examples import example_for

    return example_for("wire.doublet_remote_tuner")


SESSION = {
    "geometry": "wire.doublet_remote_tuner",
    "measurement_freq_mhz": 7.15,
    "ground": True,
}
SWEEP = [round(6.9 + 0.05 * i, 4) for i in range(11)]  # 7.15 is index 5


def test_the_stock_parts_match_the_stock_station_at_7_15():
    """The stock knobs are what the auto mode's arithmetic chooses at
    7.15 MHz, rounded to the dials (0.01 µH, 1 pF): SWR ≈ 1 there."""
    auto = tuner_design(_solve(_builder(freq=7.15))[0])
    d = Builder.default_params
    assert d["tuner_c_side"] == "rig" and auto.shunt_at == "rig"
    assert d["tuner_l_uH"] == pytest.approx(auto.series * 1e6, abs=0.005)
    assert d["tuner_c_pF"] == pytest.approx(auto.shunt * 1e12, abs=0.5)
    eng, z, advisories = _solve(Builder())
    assert tuner_design(eng) is None and not advisories
    assert _swr(z) < 1.01


def test_the_manual_parts_do_not_retune_across_a_sweep():
    """The momwire sweep on the stock design: the parts are the knobs', so
    SWR ≈ 1 at 7.15 MHz only, and rising either side."""
    re, im = _example().momwire_sweep(SESSION, SWEEP)
    swr = [_swr(complex(r, i)) for r, i in zip(re, im, strict=True)]
    assert swr[5] < 1.01
    assert all(s > 1.1 for i, s in enumerate(swr) if i != 5), swr
    assert swr[0] > 2.0 and swr[-1] > 2.0


def test_a_per_point_sweep_does_not_retune_on_pynec():
    """The external engines sweep one request per point. The parts are
    knobs, so a point off the matched frequency reads the mismatch, as the
    momwire sweep does (no held-frequency plumbing is needed)."""
    from antennaknobs.web import pynec_backend

    _example()
    at = pynec_backend._sweep_at(SESSION, 7.15)
    off = pynec_backend._sweep_at(SESSION, 7.3)
    assert _swr(at) < 1.1
    assert _swr(off) > 1.8


def test_the_tuner_plane_sweep_is_the_load():
    """At the ``tuner`` plane the sweep is the load the tuner faces across the
    band (no tuner in it), slowly varying and nowhere near 50 Ω on 40 m."""
    re, im = _example().momwire_sweep({**SESSION, "plane": "tuner"}, SWEEP)
    z = np.array(re) + 1j * np.array(im)
    assert np.all(z.real < 35.0) and np.all(z.imag < -20.0)
    assert np.max(np.abs(np.diff(z))) < 10.0


def test_the_design_has_no_design_frequency():
    """No design_freq knob: the workbench shows no band row and no lock
    (``has_design_freq`` false on GET /examples), and the wire meshes at
    10 m's density whatever band it is used on."""
    from fastapi.testclient import TestClient

    from antennaknobs.web.server import app

    assert "design_freq" not in Builder.default_params
    assert _example().has_design_freq is False
    served = TestClient(app).get("/examples").json()
    rows = served["examples"] if isinstance(served, dict) else served
    (row,) = [r for r in rows if r["name"] == "wire.doublet_remote_tuner"]
    assert row["has_design_freq"] is False
    counts = {f: _manual(freq=f).build_wires()[0][2] for f in (3.6, 7.15, 28.5)}
    assert len(set(counts.values())) == 1
    # λ/4 at 29.7 MHz carries nominal_nsegs segments.
    b = Builder()
    quarter = 0.25 * b.c_light_mhz_m / mod.MESH_MHZ
    assert counts[3.6] == round(b.nominal_nsegs * 130 * mod.FT / quarter)


def test_the_sweep_spans_the_band_the_session_is_on():
    # Band-locked at the measurement frequency: the fixed parts' SWR across
    # the whole band in use, edge to edge, on every band.
    from antennaknobs.frequency_range import design_range

    for freq, lo, hi in ((3.6, 3.5, 4.0), (7.15, 7.0, 7.3), (14.2, 14.0, 14.35)):
        r = design_range(_manual(freq=freq)._params)
        assert (r.lo, r.hi) == (lo, hi), (freq, r)


def test_the_workbench_shows_the_station_knobs_only():
    # The antenna and its wire, the line's length, the balun and the tuner's
    # three controls; every other assumption stays a knob, pinned in the app.
    import antennaknobs.web.examples  # noqa: F401  — primes the adapter
    from antennaknobs.web.adapter import _derive_schema

    specs = {s.name: s for s in _derive_schema(Builder.default_params)}
    assert set(specs) == {
        "length_ft",
        "height_ft",
        "wire_type",
        "line_ft",
        "balun_ratio",
        "tuner_l_uH",
        "tuner_c_pF",
        "tuner_c_side",
    }
    # Optimize searches the MFJ-926B's ranges, and nothing outside them.
    assert (specs["tuner_l_uH"].min, specs["tuner_l_uH"].max) == (0.0, 24.86)
    assert (specs["tuner_c_pF"].min, specs["tuner_c_pF"].max) == (0.0, 3961.0)


# ── Optimize at the measurement frequency finds the parts ──────────────────


def _optimize_at(f_mhz, **kw):
    from antennaknobs import band_opt
    from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

    b = _manual(**kw)
    free = band_opt.free_for(b, ["tuner_l_uH", "tuner_c_pF"], bounds={})
    base = {k: getattr(b, k) for k in ("tuner_l_uH", "tuner_c_pF")}
    return optimize_bands(
        base,
        free,
        parse_bands(f"{f_mhz}"),
        sweep_fn=band_opt.builder_sweep_fn(b, _factory, 50.0),
        mode="minimax",
    )


def test_a_match_objective_is_not_refused_on_the_manual_tuner():
    """AK#1664 refuses a match objective at a self-tuning tuner's own
    frequency (it is met whatever the knobs do). The manual tuner has no
    such tuner, so nothing refuses; the RED CONTROL: the same design in its
    auto mode is refused, by the same check."""
    from antennaknobs import band_opt
    from antennaknobs.auto_match import tuner_holding_match
    from antennaknobs.web.optimize import DegenerateObjective
    from antennaknobs.web.optimize_bands import optimize_bands, parse_bands

    assert tuner_holding_match(_factory(_manual(freq=14.2))) is None
    assert tuner_holding_match(_factory(_builder(freq=14.2))) is not None

    b = _builder(freq=14.2)
    free = band_opt.free_for(b, ["line_ft"], bounds={})
    with pytest.raises(DegenerateObjective):
        optimize_bands(
            {"line_ft": b.line_ft},
            free,
            parse_bands("14.2"),
            sweep_fn=band_opt.builder_sweep_fn(b, _factory, 50.0),
            mode="minimax",
        )


@pytest.mark.antenna_computation_check
def test_optimize_finds_the_parts_at_14_2_with_the_capacitor_across_the_balun():
    """(Main lane: the run is ~160 solves, ~17 s.) On 20 m the load's resistance is far above 50 Ω, so the capacitor
    belongs across the balun: switched there, Optimize from the stock (40 m)
    parts reaches SWR ≈ 1 inside the MFJ-926B's ranges; left on the rig side,
    no setting of the two parts matches, and Optimize says so."""
    res = _optimize_at(14.2, tuner_c_side="balun")
    assert res["worst_swr_before"] > 100.0
    assert res["worst_swr_after"] < 1.01, res["bands_after"]
    p = res["params"]
    assert 0 < p["tuner_l_uH"] <= 24.86 and 0 < p["tuner_c_pF"] <= 3961.0
    wrong = _optimize_at(14.2, tuner_c_side="rig")
    assert wrong["worst_swr_after"] > 10.0, wrong["bands_after"]


@pytest.mark.antenna_computation_check
def test_optimize_from_the_command_line(capsys):
    """``antennaknobs optimize --bands 14.2 --params tuner_l_uH tuner_c_pF
    --set tuner_c_side=balun``: SWR ≈ 1 at 14.2 MHz, the parts printed."""
    cli(
        [
            "optimize",
            "--builder",
            "wire.doublet_remote_tuner",
            "--bands",
            "14.2",
            "--params",
            "tuner_l_uH",
            "tuner_c_pF",
            "--set",
            "tuner_c_side=balun",
        ]
    )
    text = capsys.readouterr().out
    (line,) = [ln for ln in text.splitlines() if "worst SWR" in ln]
    assert float(line.rsplit("->", 1)[1]) < 1.01, line
    assert "'tuner_c_side': 'balun'" in text
