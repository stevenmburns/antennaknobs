import pytest

import antennaknobs as ant

from conftest import needs_pynec

o = " --fn /dev/null"
# o = ''


def test_cli_unknown_builder_is_clear_error():
    # A mistyped builder must fail with a clear message + non-zero exit, not a
    # `TypeError: 'NoneType' object is not callable` from calling the unresolved
    # (None) builder. `draw` resolves the builder first, before any engine.
    with pytest.raises(SystemExit) as exc:
        ant.cli(f"draw --builder dipoles.invee{o}".split())
    msg = str(exc.value)
    assert "unknown builder" in msg
    assert "dipoles.invee" in msg


def test_cli_draw():
    for design in [
        "beams.moxon",
        "verticals.vertical",
        "dipoles.invvee",
        "dipoles.invvee:dipole",
        "arrays.invveearray",
        "specialty.bowtie",
        "arrays.bowtiearray",
        "arrays.bowtiearray2x4",
        "beams.yagi",
        "multiband.fandipole",
    ]:
        ant.cli(f"draw --builder {design}{o}".split())


@needs_pynec
def test_cli_sweep():
    ant.cli(
        f"sweep --param tipspacer_factor --builder beams.moxon --npoints 2{o}".split()
    )
    ant.cli(
        f"sweep --gain --param tipspacer_factor --npoints 2 --builder beams.moxon{o}".split()
    )

    ant.cli(f"sweep --markers 28.57 --npoints 0{o}".split())
    ant.cli(
        f"sweep --markers 28.57 --npoints 0 --builder arrays.invveearray{o}".split()
    )
    ant.cli(
        f"sweep --markers 28.57 --npoints 2 --builder arrays.invveearray{o}".split()
    )
    ant.cli(f"sweep --npoints 2 --builder arrays.invveearray{o}".split())

    ant.cli(f"sweep --markers 28.57 --npoints 0{o} --use_smithchart --z0=50".split())
    ant.cli(
        f"sweep --markers 28.57 --npoints 0 --builder arrays.invveearray{o} --use_smithchart --z0=50".split()
    )
    ant.cli(
        f"sweep --markers 28.57 --npoints 2 --builder arrays.invveearray{o} --use_smithchart --z0=50".split()
    )
    ant.cli(
        f"sweep --npoints 2 --builder arrays.invveearray{o} --use_smithchart --z0=50".split()
    )


@needs_pynec
def test_cli_optimize():
    ant.cli(
        f"optimize --params length_factor angle_deg --builder dipoles.invvee{o}".split()
    )
    ant.cli(
        f"optimize --opt_gain --params length_factor angle_deg --resonance --builder dipoles.invvee{o}".split()
    )


@needs_pynec
def test_cli_pattern():
    ant.cli(f"pattern --builder beams.yagi{o}".split())
    ant.cli(f"pattern --builder dipoles.invvee --wireframe{o}".split())


@needs_pynec
def test_cli_compare_patterns():
    ant.cli(f"compare_patterns{o}".split())
    ant.cli(f"compare_patterns --builders dipoles.invvee beams.moxon{o}".split())
    ant.cli(f"compare_patterns --builders dipoles.invvee beams.hexbeam{o}".split())


def test_cli_swr_sweep():
    """`sweep --swr` plots SWR against any knob: freq takes the engine's
    vectorized impedance_sweep path, geometry knobs rebuild per point."""
    dipole = "dipoles.invvee:dipole"
    ant.cli(
        f"sweep --swr --npoints 5 --builder {dipole} --engine momwire"
        f" --ground free --z0=50{o}".split()
    )
    ant.cli(
        f"sweep --swr --param base --npoints 3 --builder verticals.vertical"
        f" --engine momwire --z0=50{o}".split()
    )


def test_cli_engine_flag():
    """--engine momwire selects the momwire backend; --ground forces a
    specific ground model on either engine."""
    dipole = "dipoles.invvee:dipole"
    ant.cli(f"pattern --builder {dipole} --engine momwire --ground free{o}".split())
    ant.cli(f"pattern --builder {dipole} --engine momwire --ground pec{o}".split())
    ant.cli(
        f"compare_patterns --builders {dipole} --engine momwire --ground free{o}".split()
    )
    ant.cli(
        f"sweep --builder {dipole} --npoints 3 --engine momwire --ground free{o}".split()
    )


def test_cli_default_engine_works_without_pynec(monkeypatch):
    """The default engine must be one that's always installed (momwire), so a
    plain `pip install antennaknobs` (no pynec-accel) has a working CLI. With
    pynec absent, a command run WITHOUT --engine must still solve, not raise
    "unknown engine 'pynec'"."""
    import importlib

    # `antennaknobs.cli` the attribute is the re-exported function; grab the
    # actual module to reach ENGINE_CLASSES.
    cli_mod = importlib.import_module("antennaknobs.cli")
    monkeypatch.delitem(cli_mod.ENGINE_CLASSES, "pynec", raising=False)
    dipole = "dipoles.invvee:dipole"
    ant.cli(f"pattern --builder {dipole} --ground free{o}".split())


def test_cli_export_writes_utf8_even_under_a_non_utf8_default(
    tmp_path, monkeypatch, cp1252_default_open
):
    """`export` writes the NEC deck verbatim; NEC decks are ASCII by spec and
    `export`'s CLI has no --title flag to inject through, so there is no live
    user-facing vector today (issue #772 says as much). export_nec's return
    value is the only thing stubbed here — the CLI dispatch and the
    open(args.out, "w") write site both run for real — so this still fails
    against an unpinned write site, guarding the case a future --title (or
    similar) flag opens up.

    Deliberately NOT @needs_pynec: `export` builds a deck and never solves,
    so requiring the reference engine would skip this guard on exactly the
    bare checkout the issue blames for the bug staying hidden."""
    monkeypatch.setattr("antennaknobs.nec_export.export_nec", lambda *a, **k: "CM Ω\n")

    out = tmp_path / "deck.nec"
    ant.cli(f"export --builder dipoles.invvee --out {out}".split())

    text = out.read_text(encoding="utf-8")
    assert "Ω" in text


# ---------------------------------------------------------------------------
# Mesh density beside the engine name (antennaknobs#1543)
# ---------------------------------------------------------------------------


def _meshed_at(monkeypatch, argv):
    """Run `argv` and return the nominal_nsegs each engine's builder carried.

    Reads the BUILDER the engine was handed, which is the thing a solve
    actually meshes from — a test that read `engine_density` would only be
    asking the table what the table says.
    """
    import importlib

    cli_mod = importlib.import_module("antennaknobs.cli")
    seen = []
    real = cli_mod.MomwireEngine

    class Spy(real):
        def __init__(self, builder, *a, **kw):
            seen.append(builder.nominal_nsegs)
            super().__init__(builder, *a, **kw)

    monkeypatch.setitem(cli_mod.ENGINE_CLASSES, "momwire", Spy)
    ant.cli(argv.split())
    return seen


def test_cli_engine_default_density_reaches_the_builder(monkeypatch, capsys):
    """`--engine momwire:razor-2p` runs at the razor density without a flag,
    and says so beside the engine name."""
    seen = _meshed_at(
        monkeypatch,
        f"pattern --builder dipoles.invvee --engine momwire:razor-2p{o}",
    )
    assert seen and set(seen) == {40}
    assert "engine momwire:razor-2p: N=40 segments/wire" in capsys.readouterr().err


def test_cli_bspline_density_follows_the_degree(monkeypatch):
    """The degree IS the basis, so the density follows the degree spelling."""
    assert set(
        _meshed_at(
            monkeypatch, f"pattern --builder dipoles.invvee --engine momwire:bspline{o}"
        )
    ) == {15}
    assert set(
        _meshed_at(
            monkeypatch,
            f"pattern --builder dipoles.invvee --engine momwire:bspline-d1{o}",
        )
    ) == {20}


def test_cli_nominal_nsegs_overrides_the_engine_default(monkeypatch, capsys):
    seen = _meshed_at(
        monkeypatch,
        f"pattern --builder dipoles.invvee --engine momwire:razor-2p "
        f"--nominal-nsegs 25{o}",
    )
    assert set(seen) == {25}
    assert "N=25 segments/wire (--nominal-nsegs)" in capsys.readouterr().err


def test_cli_without_an_engine_change_meshes_exactly_as_before(monkeypatch, capsys):
    """THE REGRESSION GUARD for the catalog and the status pages (#1543).

    Every published antennaknobs number was produced by a command line that
    named no engine, or named `momwire` with no basis. Both must keep the
    Builder framework default of 21, and must print nothing — a density line
    on the default engine would be a claim that something had changed.
    """
    from antennaknobs.builder import AntennaBuilder

    n = AntennaBuilder.FRAMEWORK_PARAMS["nominal_nsegs"]
    assert set(_meshed_at(monkeypatch, f"pattern --builder dipoles.invvee{o}")) == {n}
    assert capsys.readouterr().err == ""
    assert set(
        _meshed_at(monkeypatch, f"pattern --builder dipoles.invvee --engine momwire{o}")
    ) == {n}
    assert capsys.readouterr().err == ""


def test_cli_a_design_pinning_its_own_density_wins(monkeypatch):
    """A design that names `nominal_nsegs` in its own `default_params` has
    measured something about its mesh the engine default cannot know."""
    import importlib

    from antennaknobs.builder import AntennaBuilder

    cli_mod = importlib.import_module("antennaknobs.cli")
    base = cli_mod.get_builder("dipoles.invvee")

    class Pinned(base):
        default_params = dict(base.default_params, nominal_nsegs=9)

    monkeypatch.setattr(cli_mod, "get_builder", lambda nm: Pinned)
    assert set(
        _meshed_at(
            monkeypatch,
            f"pattern --builder dipoles.invvee --engine momwire:razor-2p{o}",
        )
    ) == {9}
    assert AntennaBuilder.FRAMEWORK_PARAMS["nominal_nsegs"] == 21


def test_the_pulse_basis_is_on_the_cli_roster_at_its_served_density(
    monkeypatch, capsys
):
    """`--engine momwire:pulse` is the app's Pulse tab (HarringtonSolver,
    AK#1148) and runs at the density table's 41 without a flag; the roster
    used to stop at the momwire-0.32.0 exclusion of the bare PulseSolver."""
    seen = _meshed_at(
        monkeypatch,
        f"pattern --builder dipoles.invvee --engine momwire:pulse{o}",
    )
    assert seen and set(seen) == {41}
    assert "engine momwire:pulse: N=41 segments/wire" in capsys.readouterr().err
