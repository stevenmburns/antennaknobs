"""The designs the porty rework is held to the pybind engine on.

test_opennec_parity.py's set, plus network designs on every reducer feature
(lossy line, virtual port, tuner two-ports, distributed ports) and native
multi-feed arrays over each ground.
"""

SOMMERFELD = ("finite", 13.0, 0.005)
REFL_COEF = ("finite-fast", 13.0, 0.005)
MININEC = ("mininec", 13.0, 0.005)

# (id, design, ground, engine kwargs)
CASES = [
    ("invvee-free", "dipoles.invvee", "free", {}),
    ("invvee-pec", "dipoles.invvee", "pec", {}),
    ("invvee-sommerfeld", "dipoles.invvee", SOMMERFELD, {}),
    ("vertical-reflcoef", "verticals.vertical", REFL_COEF, {}),
    ("yagi-free", "beams.yagi", "free", {}),
    ("trap-dipole-LD", "multiband.trap_dipole", "free", {}),
    ("loaded-short-LD", "dipoles.short_dipole_loaded", "free", {}),
    ("rhombic-LD-sommerfeld", "wire.rhombic", SOMMERFELD, {}),
    ("g5rv-TL", "broadband.g5rv", "free", {}),
    ("hb9cv-network", "beams.hb9cv", "free", {}),
    ("coupled-pair-reducer", "arrays.lumped_coupled_pair", "free", {}),
    ("coupled-pair-NT", "arrays.lumped_coupled_pair", "free", {"native_nt": True}),
    ("bowtie-1x2-multiport", "arrays.bowtiearray1x2", "free", {}),
    ("four-square-multiport-pec", "verticals.four_square", "pec", {}),
    # networks on the multiport-Y route
    ("coax-station-lossy-TL", "dipoles.invvee_coax_station", "free", {}),
    ("challenger-virtual-sommerfeld", "verticals.challenger", SOMMERFELD, {}),
    ("skyloop-lmatch-tuner", "loops.skyloop_lmatch", "free", {}),
    ("invl-tmatch-pec", "verticals.inverted_l_tmatch", "pec", {}),
    ("zepp-distributed", "wire.zepp", "free", {}),
    ("sterba-tl-distributed", "wire.sterba_tl", "free", {}),
    ("tri-moxon-3port-reflcoef", "verticals.tri_moxon", REFL_COEF, {}),
    ("lpda-10port", "broadband.lpda", "free", {}),
    # native multi-feed arrays
    ("phased-verticals-sommerfeld", "verticals.phased_verticals", SOMMERFELD, {}),
    ("delta-looparray-free", "arrays.delta_looparray", "free", {}),
    # the MININEC-type ground: impedance and currents only (the pattern refuses)
    ("invvee-mininec", "dipoles.invvee", MININEC, {}),
]

PATTERN = {"n_theta": 18, "n_phi": 36, "del_theta": 5, "del_phi": 10}
SWEEP_SPAN = (0.97, 1.0, 1.03)
NO_PATTERN = {"invvee-mininec"}


def builder(design):
    from antennaknobs.web import server  # noqa: F401 — registers the catalog
    from antennaknobs.web.examples import REGISTRY

    return REGISTRY.get(design).builder_cls()
