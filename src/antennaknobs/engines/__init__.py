try:
    from .pynec import PyNECEngine
except ImportError:
    PyNECEngine = None

# OpenNECEngine imports with or without pyopennec (it subclasses PyNECEngine
# and records its cards either way), so whether it can SOLVE is
# `opennec.porty is not None`, not this name.
try:
    from .opennec import OpenNECEngine
except ImportError:
    OpenNECEngine = None

from .momwire import MomwireEngine
from .nec2 import NEC2Engine, find_nec2, probe_nec2
from .nec42 import NEC42Engine, find_nec42, probe_nec42
from .nec5 import NEC5Engine, find_nec5, probe_nec5

__all__ = [
    "PyNECEngine",
    "OpenNECEngine",
    "MomwireEngine",
    "NEC5Engine",
    "find_nec5",
    "probe_nec5",
    "NEC2Engine",
    "find_nec2",
    "probe_nec2",
    "NEC42Engine",
    "find_nec42",
    "probe_nec42",
]
