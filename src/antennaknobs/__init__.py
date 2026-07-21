__all__ = [
    "Transform",
    "TransformStack",
    "Drone",
    "Antenna",
    "AntennaBuilder",
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
    "WireSpec",
    "Wire",
    "as_wire",
    "Composite",
    "Instance",
    "plot_patterns",
    "compare_patterns",
    "pattern_metrics",
    "radiated_fraction",
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
from .network import Composite, Instance, Wire, WireSpec, as_wire
from .transform import Transform, TransformStack
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
    plot_patterns,
    pattern,
    pattern3d,
    radiated_fraction,
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
import logging as _logging  # noqa: E402
import os as _os  # noqa: E402

if _level := _os.getenv("ANTENNAKNOBS_LOG"):
    _logging.basicConfig(level=_logging.WARNING)
    _logging.getLogger("antennaknobs").setLevel(_level.upper())
