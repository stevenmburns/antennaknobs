# Thread-pool wait policy, set before anything below loads NumPy/SciPy/libgomp.
# Each native pool reads these ONCE, when its library loads: OpenBLAS (every
# bundled copy) OPENBLAS_THREAD_TIMEOUT, libgomp OMP_WAIT_POLICY and
# GOMP_SPINCOUNT. Left at their defaults, the idle workers busy-spin after
# every factorization and steal cores from the next solve's fill -- measured
# on momwire 0.63.0 (Skylake, 4 threads, paired runs, 2026-09-24): +29 %
# Sommerfeld, +60 % refl-coef, +77 % free space per repeated solve (#1050,
# scratch/openblas-spin). Setting them here, rather than in the web server
# (#377: too late there, the package has loaded NumPy), covers every launch
# -- bare `uvicorn antennaknobs.web.server:app`, the install scripts, scripts
# that import antennaknobs first. setdefault keeps a caller's own values, and
# a process that loaded NumPy before importing antennaknobs is unaffected:
# the pools have already read their environment.
import os as _os

for _k, _v in (
    ("OMP_WAIT_POLICY", "PASSIVE"),
    ("GOMP_SPINCOUNT", "0"),
    ("OPENBLAS_THREAD_TIMEOUT", "1"),
):
    _os.environ.setdefault(_k, _v)
del _os, _k, _v

__all__ = [
    "Transform",
    "TransformStack",
    "Drone",
    "Antenna",
    "AntennaBuilder",
    "C_LIGHT_MHZ_M",
    "Array2x2Builder",
    "Array2x4Builder",
    "Array1x4Builder",
    "Array1x4GroupedBuilder",
    "merge_params",
    "diff_params",
    "resolve_variant_params",
    "read_data",
    "read_json",
    "read_nec",
    "read_ssn",
    "read_touchstone",
    "read_measured",
    "MeasuredTrace",
    "WireSpec",
    "Wire",
    "as_wire",
    "Composite",
    "Instance",
    "Cell",
    "Placement",
    "flatten_placements",
    "Module",
    "ModuleInstance",
    "Assembly",
    "expand_modules",
    "lattice",
    "plot_patterns",
    "compare_patterns",
    "pattern_metrics",
    "refined_pattern_metrics",
    "radiated_fraction",
    "average_gain",
    "rdf_db",
    "resolve_range",
    "gen_xs",
    "sweep",
    "sweep_freq",
    "sweep_swr",
    "sweep_gain",
    "sweep_patterns",
    "optimize",
    "pattern",
    "pattern3d",
    "params_source",
    "builder_params_source",
    "cli",
]

from .builder import (
    AntennaBuilder,
    C_LIGHT_MHZ_M,
    Array2x2Builder,
    Array2x4Builder,
    Array1x4Builder,
    Array1x4GroupedBuilder,
    merge_params,
    diff_params,
    resolve_variant_params,
)
from .design_data import read_data, read_json
from .nec_import import read_nec
from .simnec_import import read_ssn
from .touchstone import read_touchstone
from .measured import MeasuredTrace, read_measured
from .network import Composite, Instance, Wire, WireSpec, as_wire
from .transform import Transform, TransformStack
from .cell import Cell, Placement, flatten_placements
from .module import (
    Assembly,
    Module,
    ModuleInstance,
    expand_modules,
    lattice,
)
from .drone import Drone
from .sim import Antenna
from .opt import optimize
from .sweep import (
    sweep,
    sweep_freq,
    sweep_swr,
    sweep_gain,
    sweep_patterns,
    resolve_range,
    gen_xs,
)
from .far_field import (
    compare_patterns,
    pattern_metrics,
    refined_pattern_metrics,
    plot_patterns,
    pattern,
    pattern3d,
    radiated_fraction,
    average_gain,
    rdf_db,
)
from .serialize import params_source, builder_params_source
from .cli import cli

# Re-enable Builder debug prints (now `logger.debug` calls under
# `antennaknobs.designs.*`) when the env var is set:
#   ANTENNAKNOBS_LOG=debug python -m antennaknobs ...
# Unset → default WARNING level keeps the live UI quiet.
#
# We pin the root logger at WARNING and only flip the antennaknobs
# namespace; otherwise basicConfig(level=DEBUG) bleeds into matplotlib,
# PIL, and every other library that uses the stdlib logger.
import logging as _logging
import os as _os

if _level := _os.getenv("ANTENNAKNOBS_LOG"):
    _logging.basicConfig(level=_logging.WARNING)
    _logging.getLogger("antennaknobs").setLevel(_level.upper())
