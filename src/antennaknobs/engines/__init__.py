try:
    from .pynec import PyNECEngine
except ImportError:
    PyNECEngine = None

from .momwire import MomwireEngine
from .nec2 import NEC2Engine, find_nec2, probe_nec2
from .nec5 import NEC5Engine, find_nec5, probe_nec5

__all__ = [
    "PyNECEngine",
    "MomwireEngine",
    "NEC5Engine",
    "find_nec5",
    "probe_nec5",
    "NEC2Engine",
    "find_nec2",
    "probe_nec2",
]
